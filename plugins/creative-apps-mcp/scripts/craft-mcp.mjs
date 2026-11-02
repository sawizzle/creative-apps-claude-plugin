#!/usr/bin/env node
// craft-mcp: find an app's CLI and run it, passing stdio straight through.
//   node craft-mcp.mjs <app> [args...]        e.g. node craft-mcp.mjs photocraft mcp
//   node craft-mcp.mjs --where                 every CLI found per app (the first is used), with its version
// Lookup order: $<APP>_CLI (must exist if set), then absolute local PATH entries, then the install folders
// (ArtCraft\<App> for the 2026-10-27+ installers, the Craft Launcher's apps folder), then on Windows the InstallDir the
// installer wrote to the registry, then the older installers' <App> folders.
// For apps with automation roots, the launcher adds read and write roots (see withRoots()); every app starts in the
// write root, with only the environment variables it needs. Nothing is written to stdout except the child's output
// (or the CRAFT_MCP_DRY_RUN report), so the MCP stream stays clean. CRAFT_MCP_LOG=<file> appends what was started,
// or why a start was refused.
import { spawn, spawnSync } from "node:child_process";
import { accessSync, appendFileSync, constants, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, statSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const VERSION = "0.3.0";

// roots: the first version whose `mcp` takes --automation-read-root / --automation-write-root (older ones crash on them,
// or ignore them and run unlocked, so the launcher refuses to start those). multi: the first version where the read-root
// flag may be repeated (older ones get one read root). bridge: flags that make `mcp` drive a running app instead.
// Versions are from each app's release notes.
const APPS = {
  photocraft: { name: "PhotoCraft", roots: "0.2.0", bridge: ["--bridge"] },
  vectorcraft: { name: "VectorCraft", roots: "0.9.0", multi: "0.15.0", bridge: ["--connect"] },
  filmcraft: { name: "FilmCraft", bridge: ["--bridge"] },
  lightcraft: { name: "LightCraft", bridge: ["--connect"] },
  pdfcraft: { name: "PdfCraft", roots: "0.9.0", bridge: [] },
  effectcraft: { name: "EffectCraft", roots: "0.8.0", multi: "0.8.0", bridge: ["--bridge"] },
  designcraft: { name: "DesignCraft", roots: "0.9.0", multi: "0.13.0", bridge: ["--connect"] },
  figcraft: { name: "FigCraft", roots: "0.7.0", multi: "0.12.1", bridge: ["--attach"] },
  wordcraft: { name: "WordCraft", roots: "0.6.1", bridge: ["--connect"] },
  deckcraft: { name: "DeckCraft", roots: "0.8.0", multi: "0.13.1", bridge: ["--connect"] },
  gridcraft: { name: "GridCraft", bridge: ["--connect"] },
  cadcraft: { name: "CADCraft", bridge: ["--connect"] },
  soundcraft: { name: "SoundCraft", roots: "0.7.0", multi: "0.13.1", bridge: ["--connect"] },
};

const isWin = process.platform === "win32";
const exe = (app) => `${app}-cli${isWin ? ".exe" : ""}`;
const unquote = (s) => s.trim().replace(/^"(.*)"$/, "$1");
const localAbs = (p) => (isWin ? /^[A-Za-z]:[\\/]/.test(p) : path.isAbsolute(p)); // no UNC, no drive-relative, no relative
const norm = (p) => (isWin ? path.resolve(p).toLowerCase() : path.resolve(p));
const inside = (child, parent) => {
  const rel = path.relative(norm(parent), norm(child));
  return rel === "" || (rel !== ".." && !rel.startsWith(".." + path.sep) && !path.isAbsolute(rel)); // "..x" is a name, not up
};
const isFsRoot = (p) => path.dirname(path.resolve(p)) === path.resolve(p);

const parseVersion = (s) => (/(\d+)\.(\d+)\.(\d+)/.exec(s || "") || []).slice(1, 4).map(Number);
const atLeast = (v, min) => {
  const m = parseVersion(min);
  for (let i = 0; i < 3; i++) if (v[i] !== m[i]) return v[i] > m[i];
  return true;
};

function runnable(p) {
  try {
    if (!statSync(p).isFile()) return false;
    if (!isWin) accessSync(p, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function fail(msg) {
  process.stderr.write(`craft-mcp: ${msg}\n`);
  log({ app: process.argv[2], refused: msg }); // /mcp does not show stderr, so CRAFT_MCP_LOG keeps the reason too
  process.exit(1);
}

const warn = (msg) => process.stderr.write(`craft-mcp: warning: ${msg}\n`);

function realDir(p) {
  try {
    return realpathSync.native(p);
  } catch {
    return path.resolve(p);
  }
}

// The real location of a path that may not exist yet: the nearest existing ancestor resolved (junctions, symlinks,
// short names), plus the missing tail. Lets the launcher check a folder before creating it.
function realTarget(p) {
  let head = path.resolve(p);
  const tail = [];
  while (!existsSync(head) && path.dirname(head) !== head) {
    tail.unshift(path.basename(head));
    head = path.dirname(head);
  }
  return path.join(realDir(head), ...tail);
}

// $<APP>_CLI is an explicit choice: if it is set but wrong, say so instead of quietly using something else.
function fromEnv(app, strict = true) {
  const name = `${app.toUpperCase()}_CLI`;
  const v = process.env[name] ? unquote(process.env[name]) : "";
  if (!v) return null;
  const why = !localAbs(v) ? "is not an absolute path on a local drive" : !runnable(v) ? "is not an executable file" : "";
  if (why) {
    if (strict) fail(`${name}=${v} ${why}`);
    return { cli: v, rule: `${name} (${why})`, bad: true };
  }
  return { cli: v, rule: name };
}

function systemRoot() {
  const s = process.env.SystemRoot || "";
  return /^[A-Za-z]:\\/.test(s) ? s : "C:\\Windows";
}

// `reg export` text -> { valueName: string } for the first key in it. reg.exe writes the export as UTF-16, so names
// with non-ASCII letters survive (its `query` output is in the console code page and does not).
function parseRegExport(text) {
  const out = {};
  const lines = (text || "").replace(/^\uFEFF/, "").split(/\r*\n/).map((l) => l.replace(/\r+$/, ""));
  let inFirstKey = false;
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    if (line.startsWith("[")) {
      if (inFirstKey) break;
      inFirstKey = true;
      continue;
    }
    if (!inFirstKey) continue;
    while (line.endsWith("\\") && i + 1 < lines.length && /^\s*hex/.test(line.split("=")[1] || "")) line = line.slice(0, -1) + lines[++i].trim();
    const m = /^"((?:[^"\\]|\\.)*)"=(.*)$/.exec(line);
    if (!m) continue;
    const name = m[1].replace(/\\(.)/g, "$1");
    const raw = m[2];
    if (raw.startsWith('"')) {
      out[name] = raw.slice(1, -1).replace(/\\(.)/g, "$1");
    } else if (raw.startsWith("hex(2):")) {
      const bytes = raw.slice(7).split(",").filter(Boolean).map((h) => parseInt(h, 16));
      const s = Buffer.from(bytes).toString("utf16le").replace(/\0+$/, "");
      out[name] = s.replace(/%([^%]+)%/g, (all, k) => process.env[k] ?? all);
    }
  }
  return out;
}

// reg.exe is called by its full path, from the Windows folder, with a timeout, so nothing in the project folder can stand in.
function regExport(key) {
  // test hook, dry run only: a JSON file mapping registry keys to {value: data}
  if (process.env.CRAFT_MCP_DRY_RUN && process.env.CRAFT_MCP_TEST_REG) return JSON.parse(readFileSync(process.env.CRAFT_MCP_TEST_REG, "utf8"))[key] || {};
  if (!isWin || process.env.CRAFT_MCP_NO_REGISTRY) return {};
  const file = path.join(tmpdir(), `craft-mcp-${process.pid}-${Date.now()}.reg`);
  try {
    const r = spawnSync(path.join(systemRoot(), "System32", "reg.exe"), ["export", key, file, "/y", "/reg:64"], {
      cwd: systemRoot(), timeout: 3000, windowsHide: true, shell: false,
    });
    return r.status === 0 ? parseRegExport(readFileSync(file).toString("utf16le")) : {};
  } catch {
    return {};
  } finally {
    rmSync(file, { force: true });
  }
}

// The installer writes HKMU\Software\<App>\InstallDir (HKCU per user, its default; HKLM for all users); this finds a folder
// picked in the installer. HKCU comes first: an older all-users install may still be registered in HKLM. Only an absolute
// local path is accepted.
function fromRegistry(app) {
  const out = [];
  for (const hive of ["HKCU", "HKLM"]) {
    const dir = regExport(`${hive}\\Software\\${APPS[app].name}`).InstallDir;
    if (dir && localAbs(dir) && !dir.includes("%")) out.push({ cli: path.join(dir, exe(app)), rule: `registry ${hive}` });
  }
  return out;
}

// Candidate locations in order; {registry: true} marks where the registry is consulted.
function candidates(app) {
  const { name } = APPS[app];
  const bin = exe(app);
  const out = [];
  // Only absolute local PATH entries: a relative one would resolve against the project folder, a UNC one is a share.
  for (const raw of (process.env.PATH || "").split(path.delimiter)) {
    const dir = unquote(raw);
    if (dir && localAbs(dir)) out.push({ cli: path.join(dir, bin), rule: "PATH" });
  }
  const home = homedir();
  if (isWin) {
    const pf = [...new Set([process.env.ProgramFiles, process.env.ProgramW6432].filter(Boolean))];
    const x86 = process.env["ProgramFiles(x86)"];
    const local = process.env.LOCALAPPDATA;
    for (const base of pf) out.push({ cli: path.join(base, "ArtCraft", name, bin), rule: "Program Files\\ArtCraft" });
    if (local) out.push({ cli: path.join(local, "Programs", "ArtCraft", name, bin), rule: "LocalAppData\\Programs\\ArtCraft" });
    if (x86) out.push({ cli: path.join(x86, "ArtCraft", name, bin), rule: "Program Files (x86)\\ArtCraft" });
    // the Craft Launcher unpacks a portable zip (its fallback when the installer fails) into <LocalAppData>\ArtCraft Launcher\apps\<id>
    if (local) out.push({ cli: path.join(local, "ArtCraft Launcher", "apps", app, bin), rule: "Craft Launcher apps" });
    out.push({ registry: true });
    for (const base of pf) out.push({ cli: path.join(base, name, bin), rule: "Program Files (older installer)" });
    if (x86) out.push({ cli: path.join(x86, name, bin), rule: "Program Files (x86) (older installer)" });
    if (local) out.push({ cli: path.join(local, "Programs", name, bin), rule: "LocalAppData\\Programs (older installer)" });
  } else if (process.platform === "darwin") {
    // The macOS CLI ships as its own zip (it is not inside the .app, and the Craft Launcher does not install it).
    for (const dir of ["/opt/homebrew/bin", "/usr/local/bin", path.join(home, ".local", "bin"), path.join(home, "bin")]) {
      out.push({ cli: path.join(dir, bin), rule: dir });
    }
  } else {
    for (const dir of ["/usr/bin", "/usr/local/bin", path.join(home, ".local", "bin")]) out.push({ cli: path.join(dir, bin), rule: dir });
    // the Craft Launcher (a Flatpak) unpacks tarball installs into its own data folder, <data>/apps/<app>/bin
    const flat = path.join(home, ".var", "app", "ai.storyteller.artcraft-launcher", "data", "artcraft-launcher", "apps", app, "bin", bin);
    out.push({ cli: flat, rule: "Craft Launcher apps" });
  }
  return out.filter((c) => c.registry || localAbs(c.cli));
}

// Every runnable match in order (the first is used). The registry is read only if nothing before it matched, unless all=true.
function found(app, strict = true, all = false) {
  const env = fromEnv(app, strict);
  if (env) return [env];
  const seen = new Set();
  const hits = [];
  for (const c of candidates(app)) {
    const list = c.registry ? (hits.length && !all ? [] : fromRegistry(app)) : [c];
    for (const x of list) {
      const k = norm(x.cli);
      if (!seen.has(k) && runnable(x.cli)) {
        seen.add(k);
        hits.push(x);
      }
    }
  }
  return hits;
}

// An unset plugin option can arrive empty or as an unexpanded "${user_config.*}"; treat both as unset.
const setting = (...names) => {
  for (const n of names) {
    const v = unquote(process.env[n] || "");
    if (v && !v.startsWith("${")) return v;
  }
  return "";
};

const hasFlag = (args, flag) => args.some((a) => a === flag || a.startsWith(`${flag}=`));

// Folders no root may be inside (and the write root may not contain): credentials, settings, programs, the OS.
// For the write root also the chosen CLI's folder and this launcher's folder (an app must not replace the programs that
// run next time); reading them is harmless. A system folder that contains the home folder (e.g. /var on systems with
// /var/home) is not on the list.
let protectedExtra = []; // set in main()
function sensitive(forWrite = false) {
  const home = homedir();
  const list = [".claude", ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".config"].map((d) => path.join(home, d));
  list.push(process.env.CLAUDE_CONFIG_DIR, process.env.CLAUDE_PLUGIN_DATA, ...(forWrite ? protectedExtra : []));
  if (isWin) {
    list.push(process.env.APPDATA, process.env.LOCALAPPDATA, process.env.ProgramFiles, process.env.ProgramW6432,
      process.env["ProgramFiles(x86)"], process.env.ProgramData, systemRoot());
  } else {
    list.push(path.join(home, "Library"), path.join(home, ".local"), path.join(home, "bin"), path.join(home, "Applications"),
      "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/opt", "/System", "/Library", "/Applications",
      "/private/etc", "/var/root", "/var/db", "/var/lib", "/var/log");
  }
  const realHome = realDir(home);
  return list.filter((s) => s && localAbs(s)).map(realTarget).filter((s) => !inside(realHome, s));
}

// .git, .claude or CLAUDE.md within two levels: a code project, or a folder of them.
function projectMarker(dir, depth = 2) {
  let names;
  try {
    names = readdirSync(dir, { withFileTypes: true });
  } catch {
    return null;
  }
  for (const d of names) if ([".git", ".claude", "claude.md"].includes(d.name.toLowerCase())) return path.join(dir, d.name);
  if (depth > 0) {
    for (const d of names) {
      if (d.isDirectory() && !d.isSymbolicLink()) {
        const hit = projectMarker(path.join(dir, d.name), depth - 1);
        if (hit) return hit;
      }
    }
  }
  return null;
}

function checkWriteRoot(w) {
  if (norm(w) === norm(realDir(homedir())) || isFsRoot(w)) fail(`write root ${w} is your home folder or a drive root; choose a dedicated outputs folder`);
  for (const s of sensitive(true)) {
    if (inside(w, s) || inside(s, w)) fail(`write root ${w} overlaps ${s}; choose a dedicated outputs folder`);
  }
}

// The write root: checked (with its real location) before it is created, created if missing, checked again.
function writeRoot(app) {
  const legacy = app === "photocraft" ? setting("CRAFT_OPT_PHOTOCRAFT_WRITE_ROOT", "PHOTOCRAFT_WRITE_ROOT") : "";
  const chosen = legacy || setting("CRAFT_OPT_WRITE_ROOT") || path.join(homedir(), "CreativeApps");
  if (!localAbs(chosen)) fail(`write root ${chosen} must be an absolute path on a local drive`);
  checkWriteRoot(realTarget(chosen));
  if (process.env.CRAFT_MCP_DRY_RUN && !existsSync(chosen)) return realTarget(chosen); // a dry run creates nothing
  try {
    mkdirSync(chosen, { recursive: true });
  } catch (e) {
    fail(`cannot create the write root ${chosen}: ${e.message}`);
  }
  const w = realDir(chosen);
  checkWriteRoot(w);
  const marker = projectMarker(w);
  if (marker) fail(`write root ${w} holds a code project or Claude settings (${marker}); files the apps write there could act as instructions or settings later. Choose an outputs-only folder`);
  return w;
}

// A read root the user named (extra_read_root, or PhotoCraft's from 0.2.0): absolute, local, existing, not a drive root,
// never inside or containing a sensitive folder (read_scope "home" is the explicit way to open the home folder).
function namedReadRoot(value, label) {
  if (!localAbs(value)) fail(`${label} ${value} must be an absolute path on a local drive`);
  if (!existsSync(value)) fail(`${label} ${value} does not exist`);
  const r = realDir(value);
  const s = sensitive();
  for (const x of s) if (inside(r, x)) fail(`${label} ${r} is inside ${x}`);
  const wide = isFsRoot(r) || s.some((x) => inside(x, r));
  if (wide) fail(`${label} ${r} is a drive root or contains your home folder's settings; choose a narrower folder (to read your whole home folder, clear it and set read_scope to home)`);
  return r;
}

// Known folders: Windows' real (possibly redirected) ones from User Shell Folders, Linux's from user-dirs.dirs. Entries
// that are the home folder itself (user-dirs.dirs disables a folder with "$HOME/"), a drive root, or that contain or sit
// inside a sensitive folder are dropped.
function contentFolders() {
  const home = realDir(homedir());
  const s = sensitive();
  return knownFolders().filter((d) => {
    if (!localAbs(d)) return false;
    const r = realTarget(d);
    return !isFsRoot(r) && !inside(home, r) && !s.some((x) => inside(r, x) || inside(x, r));
  });
}

function knownFolders() {
  const home = homedir();
  const names = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "Movies"].map((d) => path.join(home, d));
  if (isWin) {
    const v = regExport("HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders");
    for (const k of ["Desktop", "Personal", "My Pictures", "My Video", "My Music", "{374DE290-123F-4565-9164-39C4925E467B}"]) {
      if (v[k] && localAbs(v[k]) && !v[k].includes("%")) names.push(v[k]);
    }
  } else if (process.platform !== "darwin") {
    try {
      const text = readFileSync(path.join(process.env.XDG_CONFIG_HOME || path.join(home, ".config"), "user-dirs.dirs"), "utf8");
      for (const m of text.matchAll(/^XDG_(DESKTOP|DOCUMENTS|DOWNLOAD|PICTURES|VIDEOS|MUSIC)_DIR="(.*)"$/gm)) {
        names.push(m[2].replace(/^\$HOME/, home));
      }
    } catch {}
  }
  return names;
}

// Read roots by scope (plugin option read_scope): content-folders (default), write-root-only, or home.
// Apps that take one read root get extra_read_root if set (then they cannot read the write root, unless it is inside),
// else the write root, or the home folder for scope "home".
function readRoots(app, w, multi) {
  const home = homedir();
  const legacy = app === "photocraft" ? setting("CRAFT_OPT_PHOTOCRAFT_READ_ROOT", "PHOTOCRAFT_READ_ROOT") : "";
  if (legacy) return [namedReadRoot(legacy, "PhotoCraft's read folder (photocraft_read_root, from 0.2.0)")];
  const scope = setting("CRAFT_OPT_READ_SCOPE") || "content-folders";
  if (!["content-folders", "write-root-only", "home"].includes(scope)) fail(`read_scope must be content-folders, write-root-only or home (got ${scope})`);
  const extraSet = setting("CRAFT_OPT_EXTRA_READ_ROOT");
  const extra = extraSet ? namedReadRoot(extraSet, "extra_read_root") : "";
  if (!multi) {
    if (extra && !inside(w, extra)) warn(`${APPS[app].name} reads one folder only, now ${extra}; it cannot reopen files in the output folder ${w} (set write_root to a folder inside ${extra} to keep that)`);
    return [extra || (scope === "home" ? home : w)];
  }
  const list = [w];
  if (scope === "content-folders") list.push(...contentFolders());
  else if (scope === "home") list.push(home);
  if (extra) list.push(extra);
  const seen = new Set();
  return list.filter((d) => {
    const k = norm(realDir(d));
    if (seen.has(k) || (d !== w && !existsSync(d))) return false; // apps refuse a root that does not exist (w is created first)
    seen.add(k);
    return true;
  });
}

// The CLI's version as [major, minor, patch], or null if it cannot be read.
function cliVersion(cli, env, cwd) {
  if (process.env.CRAFT_MCP_DRY_RUN && process.env.CRAFT_MCP_TEST_VERSION) return parseVersion(process.env.CRAFT_MCP_TEST_VERSION);
  const r = spawnSync(cli, ["--version"], { timeout: 10000, windowsHide: true, encoding: "utf8", shell: false, env,
    cwd: cwd && existsSync(cwd) ? cwd : tmpdir() }); // a dry run does not create the write root
  const v = parseVersion((r.stdout || "") + (r.stderr || ""));
  return v.length === 3 ? v : null;
}

function withRoots(app, args, w, cli, env) {
  const { name, roots, multi, bridge } = APPS[app];
  if (!roots || args[0] !== "mcp") return { args };
  if (bridge.some((f) => hasFlag(args, f))) return { args }; // a running app enforces its own roots
  if (hasFlag(args, "--automation-read-root") || hasFlag(args, "--automation-write-root")) return { args }; // set by hand
  const v = cliVersion(cli, env, w);
  if (!v) fail(`could not read the version of ${cli}, so it cannot be locked to folders safely; run \`node craft-mcp.mjs --where\` to check it`);
  if (!atLeast(v, roots)) {
    fail(`${name} ${v.join(".")} at ${cli} cannot be locked to folders (that needs ${roots} or newer), so this plugin does not ` +
      `start it. Update it from https://getartcraft.com/apps/${app} (\`node craft-mcp.mjs --where\` lists every copy found), then run /mcp and Reconnect.`);
  }
  const fwd = (p) => p.replace(/\\/g, "/");
  const a = [...args];
  for (const r of readRoots(app, w, !!multi && atLeast(v, multi))) a.push("--automation-read-root", fwd(r));
  a.push("--automation-write-root", fwd(w));
  return { args: a, version: v.join(".") };
}

// The child gets the variables a desktop program needs (paths, locale, display, GPU selection, proxy and CA settings for
// the apps' downloads), never the session's tokens or keys. A live-bridge server (bridge flag given) also gets its own
// app's <APP>_CONTROL_* variables. CRAFT_MCP_PASS_ENV=A,B passes more by name.
const PASS = new Set(["PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "USERPROFILE", "USERNAME",
  "HOMEDRIVE", "HOMEPATH", "HOME", "USER", "LOGNAME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
  "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "SYSTEMDRIVE", "PUBLIC", "ALLUSERSPROFILE",
  "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "OS",
  "COMPUTERNAME", "LANG", "LANGUAGE", "TZ", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "FONTCONFIG_PATH",
  "FONTCONFIG_FILE", "LD_LIBRARY_PATH", "RUST_LOG", "RUST_BACKTRACE", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "DRI_PRIME", "__NV_PRIME_RENDER_OFFLOAD", "__GLX_VENDOR_LIBRARY_NAME", "__VK_LAYER_NV_OPTIMUS",
  "CADCRAFT_CONFIG_DIR", "CADCRAFT_FONTALT", "CADCRAFT_FONTFALLBACK", "FIGCRAFT_NO_SYSTEM_FONTS", "WORDCRAFT_REGION"]);
const PASS_PREFIX = ["LC_", "XDG_", "WGPU_", "VK_", "MESA_"];

function childEnv(app, args) {
  const live = APPS[app].bridge.some((f) => hasFlag(args, f));
  const extra = new Set((process.env.CRAFT_MCP_PASS_ENV || "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean));
  const own = `${app.toUpperCase()}_CONTROL_`;
  const env = {};
  for (const [k, v] of Object.entries(process.env)) {
    const K = k.toUpperCase();
    const prefixed = PASS_PREFIX.some((p) => K.startsWith(p)) && !/TOKEN|SECRET|KEY|PASS|CREDENTIAL|AUTH/.test(K);
    if (PASS.has(K) || prefixed || extra.has(K) || (live && K.startsWith(own))) env[k] = v;
  }
  return env;
}

function log(entry) {
  const file = unquote(process.env.CRAFT_MCP_LOG || "");
  if (!file) return;
  if (!localAbs(file)) return warn(`CRAFT_MCP_LOG ignored: ${file} is not an absolute path on a local drive`);
  try {
    // only a regular file: /dev/stdout, a pipe or a device would put the line into the MCP stream or block
    if (existsSync(file) && !statSync(file).isFile()) return warn(`CRAFT_MCP_LOG ignored: ${file} is not a regular file`);
    appendFileSync(file, JSON.stringify({ when: new Date().toISOString(), launcher: VERSION, ...entry }) + "\n");
  } catch {}
}

function main() {
  const [app, ...rest] = process.argv.slice(2);
  if (app === "--version") {
    process.stderr.write(`craft-mcp ${VERSION}\n`);
    return;
  }
  if (app === "--parse-reg") {
    // test hook: parse `reg export` text from stdin
    let text = "";
    process.stdin.on("data", (d) => (text += d)).on("end", () => process.stdout.write(JSON.stringify(parseRegExport(text)) + "\n"));
    return;
  }
  if (app === "--where") {
    for (const a of Object.keys(APPS)) {
      const list = found(a, false, true);
      if (!list.length) process.stderr.write(`${a.padEnd(12)} NOT FOUND\n`);
      list.forEach((c, i) => {
        const v = c.bad ? null : cliVersion(c.cli, childEnv(a, []), tmpdir());
        process.stderr.write(`${(i ? "" : a).padEnd(12)} ${i ? "  also" : "  uses"} ${c.cli}  [${c.rule}]  ${v ? v.join(".") : "?"}\n`);
      });
    }
    return;
  }
  if (!app || !APPS[app]) {
    process.stderr.write(`craft-mcp: usage: craft-mcp <${Object.keys(APPS).join("|")}> [args...] | --where\n`);
    process.exit(2);
  }
  const hit = found(app)[0];
  if (!hit) {
    fail(
      `${exe(app)} not found. Install ${APPS[app].name} from https://getartcraft.com/apps/${app} (on macOS also the separate ` +
        `${app}-cli zip), put ${exe(app)} on PATH, or set ${app.toUpperCase()}_CLI to its full path. Then run /mcp and Reconnect.`,
    );
  }
  protectedExtra = [path.dirname(hit.cli), path.dirname(fileURLToPath(import.meta.url))];
  const w = writeRoot(app);
  const { args, version } = withRoots(app, rest, w, hit.cli, childEnv(app, rest));
  const env = childEnv(app, args);
  const plan = { app, cli: hit.cli, rule: hit.rule, version, args, cwd: w, env: Object.keys(env).sort() };
  log(plan);
  if (process.env.CRAFT_MCP_DRY_RUN) {
    process.stdout.write(JSON.stringify(plan) + "\n");
    return;
  }
  let child;
  try {
    child = spawn(hit.cli, args, { stdio: "inherit", windowsHide: true, cwd: w, env });
  } catch (e) {
    fail(`failed to start ${hit.cli}: ${e.message}`); // e.g. a damaged or wrong-platform exe throws here, not via "error"
  }
  child.on("error", (e) => fail(`failed to start ${hit.cli}: ${e.message}`));
  child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
  for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.on(sig, () => {
      if (!child.killed) child.kill(sig);
    });
  }
}

// Always run: this file is only ever executed, never imported (an import.meta/argv comparison breaks
// when the plugin directory is reached through a symlink or junction).
main();
