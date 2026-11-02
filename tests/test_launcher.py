"""Unit tests for plugins/creative-apps-mcp/scripts/craft-mcp.mjs.

    python tests/test_launcher.py          (needs Node 18+ on PATH; no app has to be installed)

Each test builds a fake home, install folders and PATH in a temp dir and points the launcher's environment at them
(ProgramFiles, LOCALAPPDATA, USERPROFILE/HOME, PATH...). Most tests read the JSON the launcher prints with
CRAFT_MCP_DRY_RUN=1 (the CLI it chose and why, the arguments, the working folder, the environment variable names it
passes). The RealMode tests run the launcher for real against a fake CLI: a copy of the Node binary named <app>-cli,
which runs the script "mcp" from the folder it starts in and reports the working folder, arguments and environment it got.
Written and run on Windows; the POSIX branches are exercised only where noted.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = os.path.join(ROOT, "plugins", "creative-apps-mcp")
LAUNCHER = os.path.join(PLUGIN, "scripts", "craft-mcp.mjs")
NODE = shutil.which("node")
WIN = sys.platform == "win32"
EXE = ".exe" if WIN else ""
ROOTS = ["photocraft", "vectorcraft", "pdfcraft", "effectcraft", "designcraft", "figcraft", "wordcraft", "deckcraft", "soundcraft"]
SINGLE = ["photocraft", "pdfcraft", "wordcraft"]
NAMES = {"photocraft": "PhotoCraft", "vectorcraft": "VectorCraft", "filmcraft": "FilmCraft", "lightcraft": "LightCraft",
         "pdfcraft": "PdfCraft", "effectcraft": "EffectCraft", "designcraft": "DesignCraft", "figcraft": "FigCraft",
         "wordcraft": "WordCraft", "deckcraft": "DeckCraft", "gridcraft": "GridCraft", "cadcraft": "CADCraft",
         "soundcraft": "SoundCraft"}
SECRETS = {"ANTHROPIC_API_KEY": "x", "GITHUB_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "x", "FILMCRAFT_CONTROL_TOKEN": "x",
           "PHOTOCRAFT_CONTROL_PORT": "7878", "PHOTOCRAFT_CONTROL_TOKEN_FILE": "x", "WORDCRAFT_CONTROL_KEY": "x",
           "CLAUDE_CODE_OAUTH_TOKEN": "x", "MY_PASSWORD": "x", "CRAFT_OPT_READ_SCOPE": "content-folders"}


def stub(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"#!/bin/sh\necho stub\n")
    if not WIN:
        os.chmod(path, 0o755)
    return path


def same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def junction(link, target):
    os.makedirs(target, exist_ok=True)
    if WIN:
        import _winapi
        _winapi.CreateJunction(target, link)
    else:
        os.symlink(target, link)


class Fake:
    """A throwaway machine: home, Program Files, LocalAppData, an empty PATH folder."""

    def __init__(self):
        self.base = tempfile.mkdtemp(prefix="craftmcp_")
        self.home = os.path.join(self.base, "home")
        self.pf = os.path.join(self.base, "pf")
        self.x86 = os.path.join(self.base, "pf86")
        self.local = os.path.join(self.home, "AppData", "Local")
        self.roaming = os.path.join(self.home, "AppData", "Roaming")
        self.path = os.path.join(self.base, "pathdir")
        for d in (self.home, self.pf, self.x86, self.local, self.roaming, self.path):
            os.makedirs(d, exist_ok=True)
        self.default_w = os.path.join(self.home, "CreativeApps")

    def env(self, **extra):
        e = {"PATH": self.path, "USERPROFILE": self.home, "HOME": self.home, "ProgramFiles": self.pf, "ProgramW6432": self.pf,
             "ProgramFiles(x86)": self.x86, "LOCALAPPDATA": self.local, "APPDATA": self.roaming, "ProgramData": os.path.join(self.base, "pd"),
             "CRAFT_MCP_DRY_RUN": "1", "CRAFT_MCP_NO_REGISTRY": "1", "CRAFT_MCP_TEST_VERSION": "999.0.0"}
        for k in ("SystemRoot", "windir", "TEMP", "TMP", "SYSTEMDRIVE"):
            if os.environ.get(k):
                e[k] = os.environ[k]
        for k, v in extra.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = v
        return e

    def run(self, app, *args, cwd=None, **env):
        r = subprocess.run([NODE, LAUNCHER, app, "mcp", *args], capture_output=True, text=True, env=self.env(**env), timeout=60,
                           cwd=cwd or self.base)
        out = None
        if r.returncode == 0 and r.stdout.strip() and env.get("CRAFT_MCP_DRY_RUN", "1"):
            out = json.loads(r.stdout)
        return r.returncode, out, r.stderr

    def cleanup(self):
        shutil.rmtree(self.base, ignore_errors=True)


def flags(args, name):
    return [args[i + 1] for i, a in enumerate(args) if a == name]


class Resolution(unittest.TestCase):
    def setUp(self):
        self.f = Fake()

    def tearDown(self):
        self.f.cleanup()

    def layouts(self, app):
        n, b = NAMES[app], f"{app}-cli{EXE}"
        f = self.f
        if WIN:
            return [
                ("PATH", os.path.join(f.path, b)),
                ("Program Files\\ArtCraft", os.path.join(f.pf, "ArtCraft", n, b)),
                ("LocalAppData\\Programs\\ArtCraft", os.path.join(f.local, "Programs", "ArtCraft", n, b)),
                ("Program Files (x86)\\ArtCraft", os.path.join(f.x86, "ArtCraft", n, b)),
                ("Craft Launcher apps", os.path.join(f.local, "ArtCraft Launcher", "apps", app, b)),
                ("Program Files (older installer)", os.path.join(f.pf, n, b)),
                ("Program Files (x86) (older installer)", os.path.join(f.x86, n, b)),
                ("LocalAppData\\Programs (older installer)", os.path.join(f.local, "Programs", n, b)),
            ]
        user_bin = os.path.join(f.home, ".local", "bin")
        if sys.platform == "darwin":  # the macOS CLI is a separate zip; the Craft Launcher does not install it
            return [("PATH", os.path.join(f.path, b)), (user_bin, os.path.join(user_bin, b)),
                    (os.path.join(f.home, "bin"), os.path.join(f.home, "bin", b))]
        return [("PATH", os.path.join(f.path, b)), (user_bin, os.path.join(user_bin, b)),
                ("Craft Launcher apps", os.path.join(f.home, ".var", "app", "ai.storyteller.artcraft-launcher", "data",
                                                     "artcraft-launcher", "apps", app, "bin", b))]

    def test_each_location_alone(self):
        for app in NAMES:
            for rule, p in self.layouts(app):
                stub(p)
                code, out, err = self.f.run(app)
                self.assertEqual(code, 0, f"{app} {rule}: {err}")
                self.assertTrue(same(out["cli"], p), f"{app} {rule}")
                self.assertEqual(out["rule"], rule)
                os.remove(p)

    def test_precedence_of_every_adjacent_pair(self):
        lay = self.layouts("filmcraft")
        for (r1, p1), (r2, p2) in zip(lay, lay[1:]):
            stub(p1), stub(p2)
            code, out, err = self.f.run("filmcraft")
            self.assertEqual(out["rule"], r1, f"{r1} should win over {r2}")
            os.remove(p1), os.remove(p2)

    def test_env_override_wins_and_bad_override_fails(self):
        stub(os.path.join(self.f.pf, "ArtCraft", "FilmCraft", f"filmcraft-cli{EXE}"))
        custom = stub(os.path.join(self.f.base, "custom", f"filmcraft-cli{EXE}"))
        code, out, _ = self.f.run("filmcraft", FILMCRAFT_CLI=custom)
        self.assertTrue(same(out["cli"], custom))
        code, out, err = self.f.run("filmcraft", FILMCRAFT_CLI=os.path.join(self.f.base, "nope.exe"))
        self.assertEqual(code, 1)
        self.assertIn("is not an executable file", err)
        stub(os.path.join(self.f.base, "bin", f"filmcraft-cli{EXE}"))
        code, out, err = self.f.run("filmcraft", FILMCRAFT_CLI=os.path.join("bin", f"filmcraft-cli{EXE}"))
        self.assertEqual(code, 1, "a relative <APP>_CLI must be refused")
        self.assertIn("absolute path", err)

    def test_not_found_message(self):
        code, out, err = self.f.run("cadcraft")
        self.assertEqual(code, 1)
        self.assertIn("cadcraft-cli", err)
        self.assertIn("CADCRAFT_CLI", err)

    @unittest.skipUnless(WIN, "Windows path forms")
    def test_relative_unc_and_drive_relative_path_entries_are_ignored(self):
        stub(os.path.join(self.f.base, "rel", f"gridcraft-cli{EXE}"))  # would match if 'rel' were resolved against the cwd
        drive = os.path.splitdrive(self.f.base)[0]
        stub(os.path.join(drive + "\\", "craftmcp_drel_" + os.path.basename(self.f.base), f"gridcraft-cli{EXE}"))
        try:
            entries = ["rel", "\\\\127.0.0.1\\share", "\\craftmcp_drel_" + os.path.basename(self.f.base)]
            code, out, err = self.f.run("gridcraft", cwd=self.f.base, PATH=os.pathsep.join(entries))
            self.assertEqual(code, 1, out)
            code, out, err = self.f.run("gridcraft", cwd=self.f.base, PATH=os.path.join(self.f.base, "rel"))
            self.assertEqual(code, 0, "the same folder as an absolute entry is found")
        finally:
            shutil.rmtree(os.path.join(drive + "\\", "craftmcp_drel_" + os.path.basename(self.f.base)), ignore_errors=True)

    @unittest.skipUnless(WIN, "Windows registry")
    def test_real_registry_installdir_is_read_and_comes_before_older_folders(self):
        reg = subprocess.run(["reg", "query", "HKLM\\Software\\PhotoCraft", "/v", "InstallDir"], capture_output=True, text=True)
        if reg.returncode != 0:
            self.skipTest("no PhotoCraft InstallDir in HKLM on this machine")
        value = re.search(r"InstallDir\s+REG_\w+\s+(.+)", reg.stdout).group(1).strip()
        if not os.path.isfile(os.path.join(value, "photocraft-cli.exe")):
            self.skipTest("the registered PhotoCraft folder has no CLI")
        old = stub(os.path.join(self.f.pf, "PhotoCraft", "photocraft-cli.exe"))
        code, out, err = self.f.run("photocraft", CRAFT_MCP_NO_REGISTRY=None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out["rule"], "registry HKLM")
        self.assertTrue(same(out["cli"], os.path.join(value, "photocraft-cli.exe")))
        self.assertTrue(os.path.exists(old))
        new = stub(os.path.join(self.f.pf, "ArtCraft", "PhotoCraft", "photocraft-cli.exe"))
        code, out, err = self.f.run("photocraft", CRAFT_MCP_NO_REGISTRY=None)
        self.assertTrue(same(out["cli"], new), "an ArtCraft install folder comes before the registry")


class Arguments(unittest.TestCase):
    def setUp(self):
        self.f = Fake()
        for app, n in NAMES.items():
            stub(os.path.join(self.f.pf, "ArtCraft", n, f"{app}-cli{EXE}") if WIN else os.path.join(self.f.path, f"{app}-cli{EXE}"))

    def tearDown(self):
        self.f.cleanup()

    def test_root_flags_only_for_apps_that_take_them(self):
        for app in NAMES:
            code, out, err = self.f.run(app)
            self.assertEqual(code, 0, f"{app}: {err}")
            has = any(a.startswith("--automation-") for a in out["args"])
            self.assertEqual(has, app in ROOTS, f"{app}: {out['args']}")

    def test_default_write_root_is_the_cwd_and_a_dry_run_creates_nothing(self):
        for app in NAMES:
            code, out, err = self.f.run(app)
            self.assertFalse(os.path.exists(self.f.default_w), "a dry run must not create the write root")
            self.assertTrue(same(out["cwd"], self.f.default_w), app)
            if app in ROOTS:
                w = flags(out["args"], "--automation-write-root")
                self.assertEqual(len(w), 1)
                self.assertTrue(same(w[0], self.f.default_w))

    def test_read_roots_content_folders(self):
        for d in ("Pictures", "Documents"):
            os.makedirs(os.path.join(self.f.home, d))
        code, out, _ = self.f.run("figcraft")
        reads = sorted(os.path.normcase(os.path.realpath(r)) for r in flags(out["args"], "--automation-read-root"))
        want = sorted(os.path.normcase(os.path.realpath(os.path.join(self.f.home, d))) for d in ("CreativeApps", "Documents", "Pictures"))
        self.assertEqual(reads, want)  # missing Desktop/Downloads/Videos/Music are left out
        for single in SINGLE:
            code, out, _ = self.f.run(single)
            reads = flags(out["args"], "--automation-read-root")
            self.assertEqual(len(reads), 1, single)
            self.assertTrue(same(reads[0], self.f.default_w), single)

    def test_read_scope_variants_and_extra(self):
        extra = os.path.join(self.f.base, "projects")
        os.makedirs(extra)
        code, out, _ = self.f.run("vectorcraft", CRAFT_OPT_READ_SCOPE="write-root-only", CRAFT_OPT_EXTRA_READ_ROOT=extra)
        self.assertEqual(len(flags(out["args"], "--automation-read-root")), 2)
        code, out, err = self.f.run("wordcraft", CRAFT_OPT_EXTRA_READ_ROOT=extra)
        self.assertTrue(same(flags(out["args"], "--automation-read-root")[0], extra))
        self.assertIn("cannot reopen files in the output folder", err)
        code, out, _ = self.f.run("pdfcraft", CRAFT_OPT_READ_SCOPE="home")
        self.assertTrue(same(flags(out["args"], "--automation-read-root")[0], self.f.home))
        code, _, err = self.f.run("pdfcraft", CRAFT_OPT_READ_SCOPE="everything")
        self.assertEqual(code, 1)
        self.assertIn("read_scope", err)

    def test_extra_read_root_checks(self):
        code, _, err = self.f.run("figcraft", CRAFT_OPT_EXTRA_READ_ROOT=os.path.join(self.f.base, "typo"))
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)
        os.makedirs(os.path.join(self.f.home, ".ssh"))
        for bad, why in ((os.path.join(self.f.home, ".ssh"), "is inside"), (self.f.home, "read_scope"),
                         (os.path.splitdrive(self.f.base)[0] + os.sep if WIN else "/", "read_scope")):
            code, _, err = self.f.run("photocraft", CRAFT_OPT_EXTRA_READ_ROOT=bad)
            self.assertEqual(code, 1, bad)
            self.assertIn(why, err, bad)

    def test_legacy_photocraft_read_root_checks(self):
        os.makedirs(os.path.join(self.f.home, ".ssh"))
        code, _, err = self.f.run("photocraft", CRAFT_OPT_PHOTOCRAFT_READ_ROOT=os.path.join(self.f.home, ".ssh"))
        self.assertEqual(code, 1)
        code, _, err = self.f.run("photocraft", CRAFT_OPT_PHOTOCRAFT_READ_ROOT=os.path.join("rel", "dir"))
        self.assertEqual(code, 1)
        for wide in (self.f.home, os.path.splitdrive(self.f.base)[0] + os.sep if WIN else "/"):
            code, out, err = self.f.run("photocraft", CRAFT_OPT_PHOTOCRAFT_READ_ROOT=wide)
            self.assertEqual(code, 1, f"a 0.2.0 read folder of {wide} is too wide")
            self.assertIn("read_scope", err)
        ok = os.path.join(self.f.base, "art")
        os.makedirs(ok)
        code, out, err = self.f.run("photocraft", CRAFT_OPT_PHOTOCRAFT_READ_ROOT=ok)
        self.assertEqual(code, 0, err)

    def test_unset_plugin_options_mean_defaults(self):
        for v in ("", "${user_config.write_root}"):
            code, out, err = self.f.run("deckcraft", CRAFT_OPT_WRITE_ROOT=v, CRAFT_OPT_READ_SCOPE="${user_config.read_scope}")
            self.assertEqual(code, 0, err)
            self.assertTrue(same(out["cwd"], self.f.default_w))

    def test_write_root_with_spaces_and_trailing_separator(self):
        w = os.path.join(self.f.base, "my outputs") + os.sep
        code, out, err = self.f.run("soundcraft", CRAFT_OPT_WRITE_ROOT=w)
        self.assertEqual(code, 0, err)
        self.assertTrue(same(out["cwd"], w.rstrip(os.sep)))
        self.assertTrue(same(flags(out["args"], "--automation-write-root")[0], w.rstrip(os.sep)))

    def test_refused_write_roots_are_not_created(self):
        bad = [os.path.join(self.f.home, ".ssh", "x"), os.path.join(self.f.home, ".claude", "skills", "x"),
               os.path.join(self.f.local, "x"), os.path.join(self.f.roaming, "Microsoft", "Windows", "Start Menu", "x")]
        for w in bad:
            code, out, err = self.f.run("effectcraft", CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, f"{w} should be refused: {out}")
            self.assertIn("write root", err)
            self.assertFalse(os.path.exists(w), f"{w} was created before it was refused")
        for w in (self.f.home, os.path.dirname(self.f.home)):
            code, _, err = self.f.run("effectcraft", CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, w)

    def test_drive_root_unc_and_relative_write_roots(self):
        cases = [("outputs", "absolute path")]
        if WIN:
            cases += [("Z:\\", "drive root"), ("\\\\127.0.0.1\\share\\out", "absolute path"), ("\\nodrive\\out", "absolute path")]
        else:
            cases += [("/", "drive root")]
        for w, why in cases:
            code, _, err = self.f.run("designcraft", CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, w)
            self.assertIn(why, err, w)

    def test_write_root_through_a_junction_into_a_protected_folder(self):
        os.makedirs(os.path.join(self.f.home, ".ssh"))
        link = os.path.join(self.f.base, "innocent")
        junction(link, os.path.join(self.f.home, ".ssh"))
        for w in (link, os.path.join(link, "deeper", "x")):
            code, _, err = self.f.run("vectorcraft", CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, w)
            self.assertIn("overlaps", err)
        self.assertFalse(os.path.exists(os.path.join(self.f.home, ".ssh", "deeper")))

    def test_a_folder_that_merely_contains_a_dot_ssh_folder_is_fine(self):
        os.makedirs(os.path.join(self.f.base, "parent", ".ssh"))
        code, _, err = self.f.run("effectcraft", CRAFT_OPT_WRITE_ROOT=os.path.join(self.f.base, "parent"))
        self.assertEqual(code, 0, err)

    def test_home_inside_a_protected_folder_does_not_block_home(self):
        # like /var/home/<user> on Fedora Silverblue: LocalAppData (protected) here contains the home folder
        code, out, err = self.f.run("figcraft", LOCALAPPDATA=self.f.base)
        self.assertEqual(code, 0, err)
        self.assertTrue(same(out["cwd"], self.f.default_w))

    def test_claude_config_dir_is_protected(self):
        cfg = os.path.join(self.f.base, "claudecfg")
        os.makedirs(cfg)
        for w in (cfg, os.path.join(cfg, "hooks")):
            code, _, err = self.f.run("figcraft", CLAUDE_CONFIG_DIR=cfg, CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, w)

    def test_write_root_holding_code_projects_is_refused(self):
        for rel in (".git", os.path.join("repo", ".claude"), os.path.join("GitHub", "repo", ".git"), os.path.join("a", "CLAUDE.md")):
            w = os.path.join(self.f.base, "w_" + str(abs(hash(rel))))
            target = os.path.join(w, rel)
            if rel.endswith(".md"):
                os.makedirs(os.path.dirname(target))
                open(target, "w").close()
            else:
                os.makedirs(target)
            code, _, err = self.f.run("figcraft", CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, rel)
            self.assertIn("code project", err)
        w = os.path.join(self.f.base, "deep")
        os.makedirs(os.path.join(w, "a", "b", "c", ".git"))
        code, _, err = self.f.run("figcraft", CRAFT_OPT_WRITE_ROOT=w)
        self.assertEqual(code, 0, "three levels down is not scanned")

    def test_bridge_flag_means_no_roots_and_passes_own_control_vars(self):
        code, out, _ = self.f.run("photocraft", "--bridge", "127.0.0.1:7878", PHOTOCRAFT_CONTROL_TOKEN="a" * 64)
        self.assertFalse(any(a.startswith("--automation-") for a in out["args"]))
        self.assertIn("PHOTOCRAFT_CONTROL_TOKEN", out["env"])
        code, out, _ = self.f.run("filmcraft", "--bridge", "127.0.0.1:9886", FILMCRAFT_CONTROL_TOKEN="b" * 64, GRIDCRAFT_CONTROL_TOKEN="c" * 64)
        self.assertIn("FILMCRAFT_CONTROL_TOKEN", out["env"])
        self.assertNotIn("GRIDCRAFT_CONTROL_TOKEN", out["env"])

    def test_user_given_roots_are_not_doubled(self):
        d = self.f.base.replace("\\", "/")
        code, out, _ = self.f.run("designcraft", "--automation-read-root", d, "--automation-write-root", d)
        self.assertEqual(len(flags(out["args"], "--automation-write-root")), 1)
        self.assertEqual(len(flags(out["args"], "--automation-read-root")), 1)

    def test_environment_is_scrubbed_in_the_report(self):
        for app in NAMES:
            code, out, err = self.f.run(app, WGPU_BACKEND="dx12", WORDCRAFT_REGION="en-US", HTTPS_PROXY="http://proxy:8080", **SECRETS)
            self.assertEqual(code, 0, err)
            upper = {k.upper() for k in out["env"]}
            for s in SECRETS:
                self.assertNotIn(s, upper, f"{app} leaked {s}")
            for keep in ("PATH", "WGPU_BACKEND", "HTTPS_PROXY"):
                self.assertIn(keep, upper)
        code, out, _ = self.f.run("cadcraft", CRAFT_MCP_PASS_ENV="MY_SETTING", MY_SETTING="1")
        self.assertIn("MY_SETTING", out["env"])

    def test_dotdot_named_folders_inside_protected_folders_are_refused(self):
        for w in (os.path.join(self.f.home, ".claude", "..hooks"), os.path.join(self.f.roaming, "..Microsoft")):
            code, _, err = self.f.run("figcraft", CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, w)
            self.assertFalse(os.path.exists(w))

    def test_folder_of_the_cli_is_protected(self):
        cli = stub(os.path.join(self.f.base, "portable", "figcraft", f"figcraft-cli{EXE}"))
        code, _, err = self.f.run("figcraft", FIGCRAFT_CLI=cli, CRAFT_OPT_WRITE_ROOT=os.path.join(self.f.base, "portable", "figcraft", "out"))
        self.assertEqual(code, 1)
        self.assertIn("overlaps", err)
        code, out, err = self.f.run("figcraft", FIGCRAFT_CLI=cli, CRAFT_OPT_EXTRA_READ_ROOT=os.path.join(self.f.base, "portable"))
        self.assertEqual(code, 0, f"reading a folder that holds the CLI is fine: {err}")

    @unittest.skipUnless(WIN, "junctions")
    def test_home_reached_through_a_junction(self):
        alias = os.path.join(tempfile.gettempdir(), "craftmcp_alias_" + os.path.basename(self.f.base))
        junction(alias, self.f.base)
        try:
            home = os.path.join(alias, "home")
            w = os.path.join(home, ".ssh", "x")
            code, _, err = self.f.run("figcraft", USERPROFILE=home, HOME=home, CRAFT_OPT_WRITE_ROOT=w)
            self.assertEqual(code, 1, err)
            self.assertFalse(os.path.exists(os.path.join(self.f.home, ".ssh", "x")), "created before it was refused")
        finally:
            os.rmdir(alias)

    def write_reg(self, data):
        path_ = os.path.join(self.f.base, "reg.json")
        with open(path_, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path_

    @unittest.skipUnless(WIN, "Windows registry")
    def test_registry_hkcu_before_hklm(self):
        for app in NAMES:  # drop the default stubs so only the registry can match
            p = os.path.join(self.f.pf, "ArtCraft", NAMES[app], f"{app}-cli{EXE}")
            if os.path.exists(p):
                os.remove(p)
        user = stub(os.path.join(self.f.base, "user install", "photocraft-cli.exe"))
        machine = stub(os.path.join(self.f.base, "machine install", "photocraft-cli.exe"))
        both = {"HKCU\\Software\\PhotoCraft": {"InstallDir": os.path.dirname(user) + "\\"},
                "HKLM\\Software\\PhotoCraft": {"InstallDir": os.path.dirname(machine) + "\\"}}
        code, out, err = self.f.run("photocraft", CRAFT_MCP_TEST_REG=self.write_reg(both))
        self.assertEqual(code, 0, err)
        self.assertEqual(out["rule"], "registry HKCU")
        self.assertTrue(same(out["cli"], user))
        only = {"HKLM\\Software\\PhotoCraft": {"InstallDir": os.path.dirname(machine)}}
        code, out, err = self.f.run("photocraft", CRAFT_MCP_TEST_REG=self.write_reg(only))
        self.assertEqual(out["rule"], "registry HKLM")
        rel = {"HKCU\\Software\\PhotoCraft": {"InstallDir": "relative\\dir"}}
        code, out, err = self.f.run("photocraft", CRAFT_MCP_TEST_REG=self.write_reg(rel))
        self.assertEqual(code, 1, "a relative InstallDir is ignored")

    @unittest.skipUnless(WIN, "Windows known folders")
    def test_content_folders_from_the_registry_are_filtered(self):
        good = os.path.join(self.f.base, "redirected docs")
        os.makedirs(good)
        os.makedirs(os.path.join(self.f.home, ".ssh", "inside"))
        key = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders"
        vals = {"Personal": good, "Desktop": self.f.home, "My Pictures": os.path.splitdrive(self.f.base)[0] + "\\",
                "My Music": os.path.join(self.f.home, ".ssh", "inside"), "My Video": os.path.dirname(self.f.home)}
        code, out, err = self.f.run("figcraft", CRAFT_MCP_TEST_REG=self.write_reg({key: vals}))
        self.assertEqual(code, 0, err)
        reads = flags(out["args"], "--automation-read-root")
        self.assertTrue(any(same(r, good) for r in reads), reads)
        for bad in (self.f.home, vals["My Pictures"], vals["My Music"], vals["My Video"]):
            self.assertFalse(any(same(r, bad) for r in reads), f"{bad} must not be a read root: {reads}")

    def test_token_like_prefixed_variables_are_not_passed(self):
        code, out, _ = self.f.run("figcraft", VK_ACCESS_TOKEN="x", MESA_API_KEY="x", VK_ICD_FILENAMES="x", XDG_RUNTIME_DIR="x")
        self.assertNotIn("VK_ACCESS_TOKEN", out["env"])
        self.assertNotIn("MESA_API_KEY", out["env"])
        self.assertIn("VK_ICD_FILENAMES", out["env"])

    def test_legacy_photocraft_options_are_honoured(self):
        r = os.path.join(self.f.base, "pc_read")
        w = os.path.join(self.f.base, "pc_write")
        os.makedirs(r)
        code, out, err = self.f.run("photocraft", CRAFT_OPT_PHOTOCRAFT_READ_ROOT=r, CRAFT_OPT_PHOTOCRAFT_WRITE_ROOT=w)
        self.assertEqual(code, 0, err)
        self.assertTrue(same(flags(out["args"], "--automation-read-root")[0], r))
        self.assertTrue(same(flags(out["args"], "--automation-write-root")[0], w))
        code, out, _ = self.f.run("vectorcraft", CRAFT_OPT_PHOTOCRAFT_WRITE_ROOT=w)
        self.assertTrue(same(out["cwd"], self.f.default_w))

    def test_versions_too_old_for_folder_flags_are_refused(self):
        for app, old in (("photocraft", "0.1.9"), ("vectorcraft", "0.8.0"), ("pdfcraft", "0.5.0"), ("effectcraft", "0.7.0"),
                         ("designcraft", "0.8.9"), ("figcraft", "0.6.0"), ("wordcraft", "0.6.0"), ("deckcraft", "0.7.0"),
                         ("soundcraft", "0.6.9")):
            code, out, err = self.f.run(app, CRAFT_MCP_TEST_VERSION=f"{app}-cli {old}")
            self.assertEqual(code, 1, f"{app} {old} should be refused: {out}")
            self.assertIn("cannot be locked to folders", err)
            self.assertIn(f"https://getartcraft.com/apps/{app}", err)
            self.assertIn("--where", err)
        code, out, err = self.f.run("photocraft", CRAFT_MCP_TEST_VERSION="photocraft-cli 0.6.0 (abc, 2026-10-10)")
        self.assertEqual(code, 0, err)
        code, out, err = self.f.run("filmcraft", CRAFT_MCP_TEST_VERSION="filmcraft-cli 0.5.0")
        self.assertEqual(code, 0, err)  # an app without folder flags is never refused for its version

    def test_unreadable_version_fails_closed(self):
        code, out, err = self.f.run("vectorcraft", CRAFT_MCP_TEST_VERSION=None)  # the stub prints no version
        self.assertEqual(code, 1, out)
        self.assertIn("could not read the version", err)
        code, out, err = self.f.run("gridcraft", CRAFT_MCP_TEST_VERSION=None)
        self.assertEqual(code, 0, "apps without folder flags do not need a version")

    def test_versions_too_old_for_several_read_roots_get_one(self):
        os.makedirs(os.path.join(self.f.home, "Pictures"))
        for app, older, newer in (("vectorcraft", "0.14.0", "0.19.0"), ("designcraft", "0.12.0", "0.15.2"),
                                  ("deckcraft", "0.13.0", "0.13.1"), ("soundcraft", "0.13.0", "0.15.0")):
            code, out, err = self.f.run(app, CRAFT_MCP_TEST_VERSION=older)
            self.assertEqual(code, 0, err)
            self.assertEqual(len(flags(out["args"], "--automation-read-root")), 1, f"{app} {older}")
            code, out, err = self.f.run(app, CRAFT_MCP_TEST_VERSION=newer)
            self.assertEqual(len(flags(out["args"], "--automation-read-root")), 2, f"{app} {newer}")

    def test_log_file(self):
        logf = os.path.join(self.f.base, "launch.log")
        code, out, _ = self.f.run("deckcraft", CRAFT_MCP_LOG=logf)
        with open(logf, encoding="utf-8") as f:
            entry = json.loads(f.read().splitlines()[-1])
        self.assertEqual(entry["args"], out["args"])
        self.assertEqual(entry["app"], "deckcraft")

    def test_log_file_records_a_refusal(self):
        logf = os.path.join(self.f.base, "refused.log")
        code, out, err = self.f.run("effectcraft", CRAFT_MCP_LOG=logf, CRAFT_OPT_WRITE_ROOT=self.f.home)
        self.assertEqual(code, 1, out)
        with open(logf, encoding="utf-8") as f:
            entry = json.loads(f.read().splitlines()[-1])
        self.assertEqual(entry["app"], "effectcraft")
        self.assertIn("write root", entry["refused"])
        self.assertIn(entry["refused"], err)

    def test_log_path_in_quotes_is_used(self):
        logf = os.path.join(self.f.base, "quoted.log")
        code, out, err = self.f.run("deckcraft", CRAFT_MCP_LOG=f'"{logf}"')
        self.assertEqual(code, 0, err)
        with open(logf, encoding="utf-8") as f:
            self.assertEqual(json.loads(f.read().splitlines()[-1])["app"], "deckcraft")

    def test_log_path_that_is_not_a_regular_file_is_ignored(self):
        targets = [self.f.base] + ([] if WIN else ["/dev/stdout"])  # a folder; on POSIX also the MCP stream itself
        for target in targets:
            code, out, err = self.f.run("deckcraft", CRAFT_MCP_LOG=target)  # run() parses stdout as the one plan line
            self.assertEqual(code, 0, f"{target}: {err}")
            self.assertEqual(out["app"], "deckcraft")
            self.assertIn("not a regular file", err, target)


REPORTER = r"""
const out = { cwd: process.cwd(), argv: process.argv.slice(2), env: Object.keys(process.env) };
process.stdout.write(JSON.stringify(out) + "\n");
process.exit(7);
"""


class RealMode(unittest.TestCase):
    """The launcher started for real, with a copy of Node as the app's CLI (it runs the script 'mcp' in the write root)."""

    def setUp(self):
        self.f = Fake()
        os.makedirs(self.f.default_w, exist_ok=True)
        with open(os.path.join(self.f.default_w, "mcp"), "w", encoding="utf-8") as fh:
            fh.write(REPORTER)

    def tearDown(self):
        self.f.cleanup()

    def test_a_cli_that_cannot_be_executed_fails_cleanly(self):
        bad = os.path.join(self.f.base, "badcli", f"gridcraft-cli{EXE}")
        os.makedirs(os.path.dirname(bad))
        with open(bad, "wb") as fh:
            fh.write(b"\x00\x01 not a program")
        if not WIN:
            os.chmod(bad, 0o755)
        code, _, err = self.f.run("gridcraft", CRAFT_MCP_DRY_RUN="", GRIDCRAFT_CLI=bad)
        self.assertEqual(code, 1, err)
        self.assertIn("craft-mcp: failed to start", err)

    def run_real(self, app, *args, **env):
        cli = os.path.join(self.f.base, "fakecli", f"{app}-cli{EXE}")
        if not os.path.exists(cli):
            os.makedirs(os.path.dirname(cli), exist_ok=True)
            shutil.copy2(NODE, cli)
        e = self.f.env(CRAFT_MCP_DRY_RUN=None, CRAFT_MCP_TEST_VERSION=None, **{f"{app.upper()}_CLI": cli}, **env)
        return subprocess.run([NODE, LAUNCHER, app, "mcp", *args], capture_output=True, text=True, env=e, timeout=60,
                              cwd=self.f.base, stdin=subprocess.DEVNULL)

    def test_child_gets_scrubbed_env_write_root_cwd_and_args_and_stdout_is_clean(self):
        for app in ("filmcraft", "figcraft", "wordcraft"):
            r = self.run_real(app, HTTPS_PROXY="http://proxy:8080", **SECRETS)
            self.assertEqual(r.returncode, 7, f"{app}: exit code not passed through: {r.stderr}")
            lines = r.stdout.splitlines()
            self.assertEqual(len(lines), 1, f"{app}: stdout must carry only the child's output: {r.stdout!r}")
            got = json.loads(lines[0])
            self.assertTrue(same(got["cwd"], self.f.default_w), app)
            upper = {k.upper() for k in got["env"]}
            for s in SECRETS:
                self.assertNotIn(s, upper, f"{app} child got {s}")
            self.assertIn("HTTPS_PROXY", upper)
            has_roots = any(a.startswith("--automation-") for a in got["argv"])
            self.assertEqual(has_roots, app in ROOTS, got["argv"])

    def test_a_real_run_creates_the_write_root(self):
        w = os.path.join(self.f.base, "fresh outputs", "sub")
        r = self.run_real("gridcraft", CRAFT_OPT_WRITE_ROOT=w)
        self.assertTrue(os.path.isdir(w), r.stderr)

    def test_real_version_path_reads_the_cli_version(self):
        r = self.run_real("vectorcraft")
        self.assertEqual(r.returncode, 7, r.stderr)  # Node prints v<major>.<minor>.<patch>, which is new enough

    def test_where_lists_rule_and_version(self):
        stub(os.path.join(self.f.pf, "ArtCraft", "FilmCraft", f"filmcraft-cli{EXE}"))
        cli = os.path.join(self.f.base, "fakecli", f"gridcraft-cli{EXE}")
        os.makedirs(os.path.dirname(cli), exist_ok=True)
        shutil.copy2(NODE, cli)
        e = self.f.env(CRAFT_MCP_DRY_RUN=None, GRIDCRAFT_CLI=cli)
        r = subprocess.run([NODE, LAUNCHER, "--where"], capture_output=True, text=True, env=e, timeout=60)
        self.assertIn("Program Files\\ArtCraft" if WIN else "PATH", r.stderr)
        self.assertRegex(r.stderr, r"gridcraft\s+uses .*GRIDCRAFT_CLI\]\s+\d+\.\d+\.\d+")
        self.assertRegex(r.stderr, r"cadcraft\s+NOT FOUND")
        self.assertEqual(r.stdout, "")


class Registry(unittest.TestCase):
    def parse(self, text, **env):
        e = dict(os.environ, **env)
        r = subprocess.run([NODE, LAUNCHER, "--parse-reg"], input=text.encode("utf-8"), capture_output=True, env=e, timeout=30)
        return json.loads(r.stdout.decode("utf-8"))

    def test_export_fixtures(self):
        head = "\ufeffWindows Registry Editor Version 5.00\r\n\r\n[HKEY_LOCAL_MACHINE\\Software\\PhotoCraft]\r\n"
        self.assertEqual(self.parse(head + '"InstallDir"="C:\\\\Program Files\\\\PhotoCraft\\\\"\r\n')["InstallDir"], "C:\\Program Files\\PhotoCraft\\")
        self.assertEqual(self.parse(head + '"InstallDir"="C:\\\\Users\\\\Jos\u00e9\\\\Apps\\\\PhotoCraft"\r\n')["InstallDir"], "C:\\Users\\Jos\u00e9\\Apps\\PhotoCraft")
        hexval = ",".join(f"{b:02x}" for b in "%LOCALAPPDATA%\\Programs".encode("utf-16le")) + ",00,00"
        # reg export wraps long hex values after a comma, ending the line with a backslash
        got = self.parse(head + '"Downloads"=hex(2):' + hexval[:63] + "\\\r\n  " + hexval[63:] + "\r\n", LOCALAPPDATA="C:\\Users\\u\\AppData\\Local")
        self.assertEqual(got["Downloads"], "C:\\Users\\u\\AppData\\Local\\Programs")
        self.assertEqual(self.parse(head + '"Other"="x"\r\n\r\n[HKEY_LOCAL_MACHINE\\Software\\PhotoCraft\\Sub]\r\n"InstallDir"="C:\\\\wrong"\r\n'), {"Other": "x"})
        self.assertEqual(self.parse(""), {})


class Consistency(unittest.TestCase):
    def test_names_and_versions_agree(self):
        with open(LAUNCHER, encoding="utf-8") as f:
            src = f.read()
        apps = re.findall(r"^  (\w+): \{ name: \"", src, re.M)
        version = re.search(r'const VERSION = "([^"]+)"', src).group(1)
        with open(os.path.join(PLUGIN, ".mcp.json"), encoding="utf-8") as f:
            servers = json.load(f)["mcpServers"]
        with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(sorted(apps), sorted(NAMES))
        self.assertEqual(sorted(servers), sorted(NAMES))
        self.assertEqual(version, manifest["version"])
        skills = sorted(d for d in os.listdir(os.path.join(PLUGIN, "skills")) if d != "creative-apps-setup")
        self.assertEqual(skills, sorted(NAMES))
        steps = sorted(f[:-5] for f in os.listdir(os.path.join(HERE, "steps")) if f.endswith(".json"))
        self.assertEqual(steps, sorted(NAMES))
        with open(os.path.join(HERE, "versions.json"), encoding="utf-8") as f:
            pinned = json.load(f)
        self.assertEqual(sorted(pinned), sorted(NAMES))
        for app, s in servers.items():
            self.assertEqual(s["args"][:3], ["${CLAUDE_PLUGIN_ROOT}/scripts/craft-mcp.mjs", app, "mcp"])
            self.assertEqual(s["env"]["CRAFT_OPT_WRITE_ROOT"], "${user_config.write_root}")
            for k, v in s["env"].items():
                opt = v[len("${user_config."):-1]
                self.assertIn(opt, manifest["userConfig"], f"{app} env {k} names an unknown option")
            with open(os.path.join(PLUGIN, "skills", app, "SKILL.md"), encoding="utf-8") as f:
                skill = f.read()
            self.assertIn(f"Tested with {app}-cli {pinned[app]}", skill, f"{app} skill version differs from tests/versions.json")
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        for app, n in NAMES.items():
            self.assertIn(f"[{n}](https://github.com/storytold/{app})", readme)


if __name__ == "__main__":
    if not NODE:
        sys.exit("node not found on PATH")
    unittest.main(verbosity=1)
