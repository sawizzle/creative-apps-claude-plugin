# stdio MCP probe: initialize -> scripted tools/call steps with captures and checks; image results are saved for a visual check.
# Usage: python mcp_probe.py --name N --steps steps.json --outdir DIR [--cwd DIR] -- <exe> [args...]
#
# A step is {"tool": name, "args": {...}} plus, optionally:
#   "timeout": seconds (default 180)
#   "capture": {"var": "/json/pointer"}   save a value from the reply (parsed as JSON); later args use "${var}"
#   "expect": [check, ...]                 every check must pass (see CHECKS below)
#   "expect_error": true | "text"          the call must fail (isError or a JSON-RPC error), optionally with this text
# A step {"restart": true} closes the server and starts a fresh process, so a reopen proves what is on disk.
# Images returned by a step are written to <outdir>/<name>_s<N>.png; checks can refer to that file as "$img".
# The probe exits 1 if any step or check failed, 0 otherwise; <outdir>/<name>_report.json has the details.
import base64, json, os, queue, subprocess, sys, threading, time, zipfile

VERSION = "2.0.1"
TEXT_CAP = 100_000

# CHECKS (all keys optional except the one naming the check):
#   {"json": "/ptr", "eq"|"ne"|"contains"|"gte"|"lte"|"len"|"in": value, "approx": n, "tol": t, "exists": bool}
#   {"text_contains": s} / {"text_not_contains": s}            on the reply's full text
#   {"file": path, "min_bytes": n}                              file exists (and is at least n bytes)
#   {"media": path, "width": w, "height": h, "fps": f, "frames": n, "codec": c, "duration": d, "tol": t}   via ffprobe
#   {"pixel": path, "x": x, "y": y, "rgb": [r, g, b], "tol": n} via ffmpeg
#   {"zip_text": path, "member": name, "contains": s}           text inside a zip member (docx/pptx/xlsx/...)
#   {"file_text": path, "contains": s}                          text file contains s
#   {"run": [exe, arg...], "stdout_contains": s, "exit": 0}     run a helper command (e.g. an app CLI's info/text);
#                                                               an exe of "python" means the Python running this probe


def pointer(doc, ptr):
    if ptr in ("", "/"):
        return doc
    cur = doc
    for raw in ptr.lstrip("/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            cur = cur[int(key)]
        elif isinstance(cur, dict):
            cur = cur[key]
        else:
            raise KeyError(ptr)
    return cur


def substitute(obj, env):
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}") and obj[2:-1] in env:
            return env[obj[2:-1]]
        for k, v in env.items():
            obj = obj.replace("${" + k + "}", str(v))
        return obj
    if isinstance(obj, list):
        return [substitute(x, env) for x in obj]
    if isinstance(obj, dict):
        return {k: substitute(v, env) for k, v in obj.items()}
    return obj


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_frames,duration",
                        "-of", "json", path], capture_output=True, text=True)
    s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
    s["fps"] = float(num) / float(den) if float(den or 0) else 0.0
    return s


def pixel(path, x, y):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"crop=1:1:{x}:{y},format=rgb24", "-frames:v", "1",
                        "-f", "rawvideo", "-"], capture_output=True)
    return list(r.stdout[:3])


def run_check(c, parsed, text, img):
    p = lambda v: img if v == "$img" else v
    try:
        if "json" in c:
            if parsed is None:
                return False, "reply is not JSON"
            try:
                got = pointer(parsed, c["json"])
            except (KeyError, IndexError, ValueError):
                return (c.get("exists") is False), f"{c['json']} missing"
            if c.get("exists") is False:
                return False, f"{c['json']} present: {json.dumps(got)[:200]}"
            for op, fn in (("eq", lambda g, v: g == v), ("ne", lambda g, v: g != v), ("gte", lambda g, v: g >= v),
                           ("lte", lambda g, v: g <= v), ("in", lambda g, v: g in v), ("len", lambda g, v: len(g) == v),
                           ("contains", lambda g, v: v in (g if isinstance(g, (list, str)) else json.dumps(g)))):
                if op in c and not fn(got, c[op]):
                    return False, f"{c['json']} = {json.dumps(got)[:200]}, wanted {op} {json.dumps(c[op])[:200]}"
            if "approx" in c and abs(float(got) - c["approx"]) > c.get("tol", 1e-6):
                return False, f"{c['json']} = {got}, wanted {c['approx']} +- {c.get('tol', 1e-6)}"
            return True, f"{c['json']} = {json.dumps(got)[:120]}"
        if "text_contains" in c:
            return c["text_contains"] in text, f"text contains {c['text_contains']!r}"
        if "text_not_contains" in c:
            return c["text_not_contains"] not in text, f"text lacks {c['text_not_contains']!r}"
        if "file" in c:
            f = p(c["file"])
            if not os.path.isfile(f):
                return False, f"{f} missing"
            n = os.path.getsize(f)
            return n >= c.get("min_bytes", 1), f"{f}: {n} bytes"
        if "media" in c:
            if not any(k in c for k in ("width", "height", "codec", "fps", "frames", "duration")):
                return False, "media check names no property to compare"
            s, tol, bad = ffprobe(p(c["media"])), c.get("tol", 0.01), []
            if not s.get("codec_name"):
                return False, f"{p(c['media'])}: ffprobe found no stream"
            for k in ("width", "height", "codec"):
                want = c.get(k)
                got = s.get("codec_name" if k == "codec" else k)
                if want is not None and got != want:
                    bad.append(f"{k}={got}")
            if "fps" in c and abs(s["fps"] - c["fps"]) > tol:
                bad.append(f"fps={s['fps']}")
            if "frames" in c and str(s.get("nb_frames")) != str(c["frames"]):
                bad.append(f"frames={s.get('nb_frames')}")
            if "duration" in c and abs(float(s.get("duration") or 0) - c["duration"]) > max(tol, 0.05):
                bad.append(f"duration={s.get('duration')}")
            return not bad, "media " + (", ".join(bad) if bad else "ok: " + json.dumps(s)[:160])
        if "pixel" in c:
            s = ffprobe(p(c["pixel"]))
            if not s.get("width") or not (0 <= c["x"] < s["width"] and 0 <= c["y"] < s["height"]):
                return False, f"pixel({c['x']},{c['y']}) is outside the image ({s.get('width')}x{s.get('height')})"
            got = pixel(p(c["pixel"]), c["x"], c["y"])
            ok = len(got) == 3 and all(abs(a - b) <= c.get("tol", 8) for a, b in zip(got, c["rgb"]))
            return ok, f"pixel({c['x']},{c['y']}) = {got}, wanted {c['rgb']} +- {c.get('tol', 8)}"
        if "zip_text" in c:
            with zipfile.ZipFile(p(c["zip_text"])) as z:
                body = z.read(c["member"]).decode("utf-8", "replace")
            return c["contains"] in body, f"{c['member']} contains {c['contains']!r}"
        if "file_text" in c:
            with open(p(c["file_text"]), encoding="utf-8", errors="replace") as f:
                body = f.read()
            return c["contains"] in body, f"{c['file_text']} contains {c['contains']!r}"
        if "run" in c:
            cmd = [p(a) for a in c["run"]]
            if cmd and cmd[0] == "python":  # the Python running this probe, not whatever "python" is on PATH
                cmd[0] = sys.executable
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            out = (r.stdout + r.stderr).decode("utf-8", "replace")
            ok = r.returncode == c.get("exit", 0) and c.get("stdout_contains", "") in out
            return ok, f"run exit {r.returncode}: {out.strip()[:200]}"
    except Exception as e:  # a check that cannot run is a failed check, never a pass
        return False, f"check error: {type(e).__name__}: {e}"
    return False, f"unknown check {json.dumps(c)[:120]}"


class Server:
    def __init__(self, cmd, cwd):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        self.q, self.err, self.dead = queue.Queue(), [], False
        threading.Thread(target=lambda: ([self.q.put(l) for l in self.p.stdout], self.q.put(None)), daemon=True).start()
        threading.Thread(target=lambda: [self.err.append(l.decode("utf-8", "replace").rstrip()) for l in self.p.stderr],
                         daemon=True).start()

    def send(self, obj):
        try:
            self.p.stdin.write((json.dumps(obj) + "\n").encode())
            self.p.stdin.flush()
        except OSError:
            pass  # the server died; recv() then reports EOF

    def recv(self, want_id, timeout):
        if self.dead:  # the server's stdout closed earlier: every later call fails at once instead of waiting
            return {"_eof": True}
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.q.get(timeout=max(0.05, end - time.time()))
            except queue.Empty:
                break
            if line is None:
                self.dead = True
                return {"_eof": True}
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            try:
                msg = json.loads(s)
            except json.JSONDecodeError:
                return {"_nonjson_stdout": s[:300]}
            if msg.get("id") == want_id:
                return msg
        return {"_timeout": timeout}

    def init(self):
        self.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "mcp-smoke-probe", "version": VERSION}}})
        r = self.recv(1, 60)
        if "result" in r:
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return r

    def close(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=15)
            return self.p.returncode
        except subprocess.TimeoutExpired:
            self.p.kill()
            return "HUNG (killed)"


def main():
    argv = sys.argv[1:]
    sep = argv.index("--")
    opts, cmd = argv[:sep], argv[sep + 1:]
    o = dict(zip(opts[0::2], opts[1::2]))
    name, outdir = o["--name"], o["--outdir"]
    with open(o["--steps"], encoding="utf-8") as f:
        steps = json.load(f)
    os.makedirs(outdir, exist_ok=True)

    t0 = time.time()
    rep = {"name": name, "cmd": cmd, "probe": VERSION, "steps": [], "sessions": []}
    srv = Server(cmd, o.get("--cwd"))
    r = srv.init()
    if "result" not in r:
        rep["init_error"] = r
    else:
        rep["server"] = r["result"].get("serverInfo")
        env, rid = {}, 100
        for i, st in enumerate(steps, start=1):
            t1 = time.time()
            if st.get("restart"):
                rep["sessions"].append({"exit": srv.close(), "stderr_tail": srv.err[-6:]})
                srv = Server(cmd, o.get("--cwd"))
                ri = srv.init()
                ok = "result" in ri
                rep["steps"].append({"n": i, "tool": "(restart)", "ok": ok, "s": round(time.time() - t1, 2),
                                     "text": "" if ok else json.dumps(ri)[:300]})
                if not ok:
                    break
                continue
            rid += 1
            args = substitute(st.get("args", {}), env)
            srv.send({"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": st["tool"], "arguments": args}})
            cr = srv.recv(rid, st.get("timeout", 180))
            row = {"n": i, "tool": st["tool"], "args": args, "s": round(time.time() - t1, 2), "checks": []}
            res = cr.get("result")
            texts, img = [], None
            if res is None:
                is_err, row["error"] = True, cr.get("error", cr)
                texts.append(json.dumps(row["error"]))
            else:
                is_err = bool(res.get("isError", False))
                for c in res.get("content", []):
                    if c.get("type") == "text":
                        texts.append(c.get("text", ""))
                    elif c.get("type") == "image":
                        ext = {"image/png": "png", "image/jpeg": "jpg"}.get(c.get("mimeType"), "bin")
                        img = os.path.join(outdir, f"{name}_s{i}.{ext}")
                        with open(img, "wb") as f:
                            f.write(base64.b64decode(c["data"]))
                        row["images"] = [img]
            text = "\n".join(texts)
            row["text"] = text[:TEXT_CAP]
            parsed = None
            for cand in (texts[0] if texts else None, text):
                try:
                    parsed = json.loads(cand)
                    break
                except (TypeError, json.JSONDecodeError):
                    pass
            want_err = st.get("expect_error")
            if want_err:
                # a dead, hung or garbled server is never the refusal a step expects, and neither is an unknown tool or
                # bad arguments (-32601/-32602) unless the step names that error's text
                broken = any(k in cr for k in ("_eof", "_timeout", "_nonjson_stdout"))
                rpc = (cr.get("error") or {}).get("code") in (-32601, -32602)
                ok = is_err and not broken and (str(want_err) in text if want_err is not True else not rpc)
                row["checks"].append({"ok": ok, "what": "expected an error" + ("" if want_err is True else f" containing {want_err!r}")
                                      + (" (got a dead/hung server)" if broken else "")})
            else:
                ok = not is_err
            if ok and not want_err:
                for var, ptr in (st.get("capture") or {}).items():
                    try:
                        env[var] = pointer(parsed, ptr)
                        row["checks"].append({"ok": True, "what": f"capture {var} = {json.dumps(env[var])[:80]}"})
                    except Exception:
                        ok = False
                        row["checks"].append({"ok": False, "what": f"capture {var} from {ptr} failed"})
            for c in st.get("expect", []):
                c_ok, what = run_check(substitute(c, env), parsed, text, img)
                row["checks"].append({"ok": c_ok, "what": what})
                ok = ok and c_ok
            row["ok"] = ok
            rep["steps"].append(row)
    rep["sessions"].append({"exit": srv.close(), "stderr_tail": srv.err[-6:]})
    rep["exit"] = rep["sessions"][-1]["exit"]
    rep["total_s"] = round(time.time() - t0, 2)
    rep["stderr_tail"] = rep["sessions"][-1]["stderr_tail"]
    rep["passed"] = sum(1 for s in rep["steps"] if s["ok"])
    rep["failed"] = sum(1 for s in rep["steps"] if not s["ok"])
    with open(os.path.join(outdir, f"{name}_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"{name}: {rep['passed']} ok / {rep['failed']} fail, exit {rep['exit']}, {rep['total_s']}s")
    sys.exit(0 if rep["steps"] and not rep["failed"] and "init_error" not in rep else 1)


if __name__ == "__main__":
    main()
