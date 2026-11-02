"""End-to-end check of every supported app's MCP server, started through the plugin's own launcher.

    python tests/run_all_tests.py [app ...] [--any-version] [--allow-skip] [--no-sandbox] [--cli-env FILE]

Smoke tests (tests/steps/<app>.json): each app is started through the plugin's launcher with the arguments in
plugins/creative-apps-mcp/.mcp.json, with read_scope write-root-only, the run folder as the output folder and the test
inputs copied into it (so the apps that take a single read folder can read them), and with WORDCRAFT_REGION=en-US and
FIGCRAFT_NO_SYSTEM_FONTS=1 for repeatable pages and text. Each step's "expect" checks must pass; {"restart": true}
steps reopen saved files in a fresh process.
Sandbox tests (tests/sandbox/<app>.json, Windows only): the app's CLI is started directly, in its own output folder,
with the folder arguments the launcher gives a user whose extra_read_root is the inputs folder (apps that take several
read folders also get the output folder as one; apps without folder flags get none), after
tests/sandbox/<app>.setup.py <output folder> if there is one. The steps prove what is refused, or for an app that
cannot be locked, what it can reach. Junctions and device-name files the batteries leave are removed afterwards.

Every run writes to tests/out/<run-id>/ and makes contact_sheet.png (app, version and run id above each image).
Open it and the exports: a passing check is not proof the picture is right.
By default the run is strict: an app that is not found, a server that exits badly or a version that differs from
tests/versions.json fails the run (use --allow-skip / --any-version to relax). --cli-env FILE reads <APP>_CLI=path lines
(to test copies that are not installed). Needs Python 3.9+, Node 18+, ffmpeg/ffprobe for media checks.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = os.path.join(ROOT, "plugins", "creative-apps-mcp")
LAUNCHER = os.path.join(PLUGIN, "scripts", "craft-mcp.mjs")
INPUTS = os.path.join(HERE, "inputs")
VERSION = "2.0.3"


def fwd(p):
    return p.replace("\\", "/")


RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10)), "conin$", "conout$"}


def reserved(name):
    return name.split(".")[0].rstrip(" ").lower() in RESERVED


def is_link(p):
    """A symlink or a Windows junction (any reparse point; os.path.isjunction only exists from Python 3.12)."""
    if os.path.islink(p):
        return True
    try:
        return bool(getattr(os.lstat(p), "st_file_attributes", 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return False


def clean_links(folder):
    """Remove the junctions/symlinks and device-name files a sandbox battery left behind (never following a link)."""
    removed = []
    for d, dirs, fs in os.walk(folder):
        for n in list(dirs):
            p = os.path.join(d, n)
            if is_link(p):
                (os.unlink if os.path.islink(p) and sys.platform != "win32" else os.rmdir)(p)
                dirs.remove(n)
                removed.append(p)
        for n in fs:
            p = os.path.join(d, n)
            if os.path.islink(p):
                os.unlink(p)
                removed.append(p)
            elif sys.platform == "win32" and reserved(n):
                os.remove("\\\\?\\" + os.path.abspath(p))
                removed.append(p)
    return removed


def resolve(text, mapping):
    for k, v in mapping.items():
        text = text.replace("{" + k + "}", v)
    return text


def label_tile(img, header, out):
    """Scale an image into a 360x250 tile with a header line burned in above it."""
    font = "C\\:/Windows/Fonts/arial.ttf" if sys.platform == "win32" else "DejaVuSans"
    text = header.replace(":", "\\:").replace("'", "")
    vf = (f"scale=360:220:force_original_aspect_ratio=decrease,pad=360:250:(ow-iw)/2:30+(220-ih)/2:color=0x222222,"
          f"drawtext=fontfile='{font}':text='{text}':x=6:y=8:fontsize=14:fontcolor=white")
    if sys.platform != "win32":
        vf = vf.replace(f"fontfile='{font}'", f"font='{font}'")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", img, "-vf", vf, "-frames:v", "1", out], capture_output=True)


def contact_sheet(run_dir, tiles):
    if not tiles or not shutil.which("ffmpeg"):
        return None
    tdir = os.path.join(run_dir, "_tiles")
    os.makedirs(tdir, exist_ok=True)
    for i, (img, header) in enumerate(tiles):
        label_tile(img, header, os.path.join(tdir, f"tile_{i:03d}.png"))
    cols = 4
    paths = [os.path.join(tdir, f"tile_{i:03d}.png") for i in range(len(tiles))]
    blank = os.path.join(tdir, "blank.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x000000:s=360x250", "-frames:v", "1", blank],
                   capture_output=True)
    paths += [blank] * (-len(paths) % cols)
    rows = len(paths) // cols
    inputs = sum((["-i", p] for p in paths), [])
    graph = "".join(f"{''.join(f'[{r * cols + c}:v]' for c in range(cols))}hstack=inputs={cols}[r{r}];" for r in range(rows))
    graph += ("".join(f"[r{r}]" for r in range(rows)) + f"vstack=inputs={rows}[out]") if rows > 1 else "[r0]null[out]"
    sheet = os.path.join(run_dir, "contact_sheet.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]", "-frames:v", "1", sheet],
                   capture_output=True)
    return sheet if os.path.exists(sheet) else None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return
    cli_env = argv[argv.index("--cli-env") + 1] if "--cli-env" in argv and argv.index("--cli-env") + 1 < len(argv) else None
    if "--cli-env" in argv and (not cli_env or cli_env.startswith("-")):
        sys.exit("--cli-env needs a file")
    unknown = [a for a in argv if a.startswith("-") and a != cli_env and a not in ("--any-version", "--allow-skip", "--no-sandbox", "--cli-env")]
    if unknown:
        sys.exit(f"unknown option(s): {' '.join(unknown)} (see --help)")
    opts = {a for a in argv if a.startswith("--") and a != "--cli-env" and a != cli_env}
    apps = list(dict.fromkeys(a for a in argv if not a.startswith("-") and a != cli_env))
    with open(os.path.join(HERE, "versions.json"), encoding="utf-8") as f:
        bad_apps = [a for a in apps if a not in json.load(f)]
    if bad_apps:
        sys.exit(f"unknown app(s): {' '.join(bad_apps)}")
    overrides = {}
    if cli_env:
        if not os.path.isfile(cli_env):
            sys.exit(f"--cli-env: {cli_env} is not a file")
        with open(cli_env, encoding="utf-8-sig") as f:  # -sig: PowerShell 5.1 writes a BOM
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                k, eq, v = (s.strip() for s in line.partition("="))
                if not eq or not k.endswith("_CLI") or not v:
                    sys.exit(f"--cli-env {cli_env} line {n}: expected <APP>_CLI=<path>, got {line!r}")
                overrides[k] = v
    node = shutil.which("node")
    if not node:
        sys.exit("node not found on PATH (Node 18+ is required by the plugin launcher)")
    with open(os.path.join(PLUGIN, ".mcp.json"), encoding="utf-8") as f:
        servers = json.load(f)["mcpServers"]
    with open(os.path.join(HERE, "versions.json"), encoding="utf-8") as f:
        pinned = json.load(f)
    apps = apps or list(servers)
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(HERE, "out", run_id)
    if "'" in run_dir:  # the batteries paste run paths into single-quoted PowerShell strings
        sys.exit(f"the repository path contains a ' ({run_dir}); clone it to a path without one to run the tests")
    os.makedirs(run_dir)
    # a stray shell variable must not fake the launcher's plan or version, or bring in the user's PhotoCraft folders
    base_env = {k: v for k, v in os.environ.items() if k.upper() not in (
        "CRAFT_MCP_DRY_RUN", "CRAFT_MCP_TEST_VERSION", "CRAFT_MCP_TEST_REG", "CRAFT_MCP_LOG", "CRAFT_MCP_PASS_ENV",
        "CRAFT_OPT_PHOTOCRAFT_READ_ROOT", "CRAFT_OPT_PHOTOCRAFT_WRITE_ROOT", "PHOTOCRAFT_READ_ROOT", "PHOTOCRAFT_WRITE_ROOT")}
    base_env.update(overrides)
    failed, rows, tiles, ran, skipped = 0, [], [], 0, []
    for app in apps:
        out = os.path.join(run_dir, app)
        os.makedirs(out)
        shutil.copytree(INPUTS, os.path.join(out, "inputs"))
        env = dict(base_env, CRAFT_OPT_WRITE_ROOT=out, CRAFT_OPT_READ_SCOPE="write-root-only", CRAFT_OPT_EXTRA_READ_ROOT="",
                   WORDCRAFT_REGION="en-US", FIGCRAFT_NO_SYSTEM_FONTS="1")
        args = [a.replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN) for a in servers[app]["args"]]
        dry = subprocess.run([node] + args, capture_output=True, text=True, env=dict(env, CRAFT_MCP_DRY_RUN="1"))
        if dry.returncode != 0:
            msg = dry.stderr.strip()[:200]
            if "--allow-skip" in opts and "not found" in msg:
                print(f"{app:12} SKIP  {msg}")
                skipped.append(app)
                continue
            failed += 1
            print(f"{app:12} FAIL  launcher: {msg}")
            continue
        plan = json.loads(dry.stdout)
        ran += 1
        smoke_map = {"IN": fwd(os.path.join(out, "inputs")), "OUT": fwd(out), "CLI": fwd(plan["cli"])}
        # the sandbox battery keeps inputs and outputs in sibling folders, so "outside the roots" is unambiguous
        sb_in, sb_out = os.path.join(out, "sandbox_in"), os.path.join(out, "sandbox_out")
        sandbox_map = {"IN": fwd(sb_in), "OUT": fwd(sb_out), "CLI": fwd(plan["cli"])}
        row = {"app": app, "cli": plan["cli"], "rule": plan["rule"], "args": plan["args"]}
        has_sandbox = "--no-sandbox" not in opts and os.path.exists(os.path.join(HERE, "sandbox", f"{app}.json"))
        if has_sandbox and sys.platform != "win32":
            print(f"{app:12} sandbox SKIP  the sandbox batteries are Windows-only (junctions, PowerShell, device names)")
            has_sandbox = False
        sb_plan = {}
        if has_sandbox:
            shutil.copytree(INPUTS, sb_in)
            os.makedirs(sb_out)
            setup = os.path.join(HERE, "sandbox", f"{app}.setup.py")
            if os.path.exists(setup):  # builds the fixture (outside folder, junctions, links) next to the output folder
                su = subprocess.run([sys.executable, "-I", setup, sb_out], capture_output=True, text=True, timeout=300)
                if su.returncode != 0:
                    failed += 1
                    print(f"{app:12} sandbox FAIL  setup exit {su.returncode}: {su.stderr.strip()[-300:]}")
                    has_sandbox = False
        if has_sandbox:
            # the sandbox server gets exactly the arguments the launcher gives a user whose extra_read_root is the inputs
            sb_env = dict(env, CRAFT_MCP_DRY_RUN="1", CRAFT_OPT_WRITE_ROOT=sb_out, CRAFT_OPT_EXTRA_READ_ROOT=sb_in)
            sbd = subprocess.run([node] + args, capture_output=True, text=True, env=sb_env)
            if sbd.returncode != 0:
                failed += 1
                print(f"{app:12} sandbox FAIL  launcher: {sbd.stderr.strip()[:200]}")
                has_sandbox = False
            else:
                sb_plan = json.loads(sbd.stdout)
                row["sandbox_args"] = sb_plan.get("args")
        for kind, folder, mapping, cmd, cwd in (
            ("smoke", "steps", smoke_map, [node] + args, out),
            ("sandbox", "sandbox", sandbox_map, [plan["cli"]] + (sb_plan.get("args") or []), sb_out),
        ):
            steps_file = os.path.join(HERE, folder, f"{app}.json")
            if kind == "sandbox" and not has_sandbox:
                continue
            with open(steps_file, encoding="utf-8") as f:
                resolved = resolve(f.read(), mapping)
            rpath = os.path.join(out, f"_{kind}_steps.json")
            with open(rpath, "w", encoding="utf-8") as f:
                f.write(resolved)
            name = app if kind == "smoke" else f"{app}_sandbox"
            try:
                subprocess.run([sys.executable, os.path.join(HERE, "mcp_probe.py"), "--name", name, "--steps", rpath, "--outdir", out,
                                "--cwd", cwd, "--"] + cmd, capture_output=True, env=env, timeout=1800)
            except subprocess.TimeoutExpired:
                failed += 1
                print(f"{app:12} {kind:7} PROBE TIMED OUT after 1800 s")
                continue
            rep_path = os.path.join(out, f"{name}_report.json")
            if not os.path.exists(rep_path):
                failed += 1
                print(f"{app:12} {kind:7} PROBE FAILED (no report)")
                continue
            with open(rep_path, encoding="utf-8") as f:
                r = json.load(f)
            version = (r.get("server") or {}).get("version", "?")
            problems = []
            if r["failed"] or not r["steps"] or "init_error" in r:
                problems.append(f"{r['failed']} step(s) failed" if r["steps"] else f"no steps ran: {json.dumps(r.get('init_error'))[:120]}")
            bad_exits = [x.get("exit") for x in r.get("sessions", []) if x.get("exit") not in (0, None)]
            if bad_exits or r.get("exit") not in (0, None):
                problems.append(f"server exit {bad_exits or r.get('exit')}")
            if "--any-version" not in opts and pinned.get(app) and version != pinned[app]:
                problems.append(f"version {version} != pinned {pinned[app]}")
            failed += bool(problems)
            print(f"{app:12} {kind:7} {version:8} {r['passed']} ok / {r['failed']} fail  {r['total_s']}s  {'; '.join(problems) or 'PASS'}")
            for s in r["steps"]:
                if not s["ok"]:
                    bad = [c["what"] for c in s.get("checks", []) if not c["ok"]] or [(s.get("text") or "")[:160]]
                    print(f"    step {s['n']} {s['tool']}: {' | '.join(bad)[:300]}")
                for img in s.get("images", []):
                    tiles.append((img, f"{app} {version} {kind} s{s['n']} {run_id}"))
            row[kind] = {"version": version, "passed": r["passed"], "failed": r["failed"], "problems": problems}
        row["removed_links"] = [os.path.relpath(p, run_dir) for p in clean_links(out)]
        files = []
        for d, _, fs in os.walk(out):
            if os.path.join(out, "inputs") in d:
                continue
            for fn in fs:
                if reserved(fn):
                    continue
                p = os.path.join(d, fn)
                with open(p, "rb") as fh:
                    files.append({"file": os.path.relpath(p, run_dir), "bytes": os.path.getsize(p), "sha256": hashlib.sha256(fh.read()).hexdigest()})
        row["outputs"] = files
        rows.append(row)
    if ran == 0:
        failed += 1
        print("NOTHING RAN: no app was found" + (f" (skipped: {', '.join(skipped)})" if skipped else ""))
    sheet = contact_sheet(run_dir, tiles)
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "runner": VERSION, "failed": failed, "apps": rows, "contact_sheet": sheet}, f, indent=1)
    print(f"\nrun {run_id}: {ran} app(s) ran, {len(skipped)} skipped: {'FAILED' if failed else 'all passed'}; outputs: {fwd(run_dir)}" + (f"; contact sheet: {fwd(sheet)}" if sheet else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
