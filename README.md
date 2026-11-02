# Unofficial third-party plugin for Claude Code: open-source creative apps

This is a third-party Claude Code plugin for the open-source apps listed at [getartcraft.com/apps](https://getartcraft.com/apps).
It connects Claude to the MCP server each app already ships, and adds one skill per app. Each skill
records the setup, workflows tested against real output, and the pitfalls hit along the way.

> **Unofficial third-party plugin.** Not made, sponsored, endorsed, certified or supported by the ArtCraft
> Team, who make the apps it connects to; ArtCraft is their trademark. The app names identify the software
> this plugin connects to and belong to their owners. No ArtCraft logos, artwork or app code are included.
> Report plugin problems here; report a bug to an app's own repository only if you can reproduce it with
> that app's CLI without this plugin.

| App | Comparable to | MCP server | Folder lock | Tested with |
|---|---|---|---|---|
| [PhotoCraft](https://github.com/storytold/photocraft) | Photoshop | `photocraft-cli mcp` | yes | 0.19.0 |
| [VectorCraft](https://github.com/storytold/vectorcraft) | Illustrator | `vectorcraft-cli mcp --headless` | yes | 0.20.0 |
| [FilmCraft](https://github.com/storytold/filmcraft) | Premiere Pro | `filmcraft-cli mcp` | **no** | 0.16.0 |
| [LightCraft](https://github.com/storytold/lightcraft) | Lightroom | `lightcraft-cli mcp --compact` | **no** | 0.17.0 |
| [PdfCraft](https://github.com/storytold/pdfcraft) | Acrobat | `pdfcraft-cli mcp --compact` | yes | 0.17.0 |
| [EffectCraft](https://github.com/storytold/effectcraft) | After Effects | `effectcraft-cli mcp` | yes | 0.20.0 |
| [DesignCraft](https://github.com/storytold/designcraft) | InDesign | `designcraft-cli mcp` | yes | 0.16.0 |
| [FigCraft](https://github.com/storytold/figcraft) | Figma | `figcraft-cli mcp` | yes | 0.14.0 |
| [WordCraft](https://github.com/storytold/wordcraft) | Word | `wordcraft-cli mcp` | yes | 0.14.0 |
| [DeckCraft](https://github.com/storytold/deckcraft) | PowerPoint | `deckcraft-cli mcp` | yes | 0.14.1 |
| [GridCraft](https://github.com/storytold/gridcraft) | Excel | `gridcraft-cli mcp` | **no** | 0.15.0 |
| [CADCraft](https://github.com/storytold/cadcraft) | AutoCAD | `cadcraft-cli mcp` | **no** | 0.16.0 |
| [SoundCraft](https://github.com/storytold/soundcraft) | Pro Tools | `soundcraft-cli mcp` | yes | 0.16.0 |

The apps ship new releases about once a week. "Tested with" is the release each skill and the test suite were
last run against (2026-11-01). Newer releases have mostly added tools and options, but behaviour sometimes changes;
each app's own `command_list` / `list_commands` tool is the source of truth.

**Tested on Windows 11 only.** The macOS and Linux CLI locations come from the apps' packaging and the Craft
Launcher's source, but nobody has tested them. Reports are welcome.

## Install

Upgrading from 0.2.0 or 0.1.x? Read [Upgrading](#upgrading) first.

**You need:**
- [Claude Code](https://code.claude.com) (tested with 2.1.286).
- **Node.js 18+ on `PATH`.** Each server starts through a small launcher that finds the app's CLI. If
  Node is missing, every server fails to connect; see [Without Node](#without-node).
- The apps you want, from [getartcraft.com/apps](https://getartcraft.com/apps) or the Craft Launcher. Apps you
  have not installed show as failed servers; see [Apps you have not installed](#apps-you-have-not-installed).

```
/plugin marketplace add sawizzle/creative-apps-claude-plugin
/plugin install creative-apps-mcp@sawizzle-plugins
```

Or from a shell:

```bash
claude plugin marketplace add sawizzle/creative-apps-claude-plugin
claude plugin install creative-apps-mcp@sawizzle-plugins
```

Restart Claude Code. The servers appear as `plugin:creative-apps-mcp:<app>`.

### Where the launcher looks for each CLI
1. **`<APP>_CLI`**, e.g. `PHOTOCRAFT_CLI=/path/to/photocraft-cli` (an absolute path). If this is set to a path that
   doesn't exist, the launcher fails with an error rather than looking elsewhere. Use it for custom install
   folders, portable zips, tarballs, Flatpak and AppImage.
2. **Absolute local entries on your `PATH`.** Relative entries and network (UNC) paths are ignored.
3. **The install folders:**
   - **Windows, installers from 2026-10-27 on and the Craft Launcher:** `%ProgramFiles%\ArtCraft\<App>\`
     (all users, and every Craft Launcher 0.10 install) or `%LOCALAPPDATA%\Programs\ArtCraft\<App>\` (the
     installer's per-user default), then `%ProgramFiles(x86)%\ArtCraft\<App>\` and the Craft Launcher's portable
     folder `%LOCALAPPDATA%\ArtCraft Launcher\apps\<app>\` (from the launcher's source).
     The installers do **not** add the CLI to PATH.
   - **Windows, a folder you picked in the installer:** the `InstallDir` the installer writes to
     `HKCU`/`HKLM\Software\<App>` (per-user first), read when none of the folders above matched.
   - **Windows, installers before 2026-10-27:** `%ProgramFiles%\<App>\`, `%ProgramFiles(x86)%\<App>\` and
     `%LOCALAPPDATA%\Programs\<App>\`.
   - **macOS:** the CLI is a separate download, `<app>-cli-<version>-macos-universal.zip`. It is not inside the
     `.app`, and the Craft Launcher does not install it. Put it in `/usr/local/bin`, `/opt/homebrew/bin`,
     `~/.local/bin` or `~/bin`, or set `<APP>_CLI`.
   - **Linux:** the deb and rpm packages install to `/usr/bin`; `/usr/local/bin`, `~/.local/bin` and the Craft Launcher's
     `~/.var/app/ai.storyteller.artcraft-launcher/data/artcraft-launcher/apps/<app>/bin/` (from its source) are searched
     too. AppImage and Flatpak apps keep the CLI inside the package: set `<APP>_CLI` or install the deb/rpm.

To see what the launcher finds (every match, with its version; the first one is used), run this from a clone of
this repo:

```bash
node plugins/creative-apps-mcp/scripts/craft-mcp.mjs --where
```

### Folders the apps may use
Nine of the apps can be locked to folders, and this plugin locks them by default. Four apps cannot be locked
(see [Security](#security)).

| Option | Default | What it does |
|---|---|---|
| `write_root` | `~/CreativeApps` (created when needed) | The one folder the locked apps may write to. **Every** app, locked or not, starts in it, so in most apps a relative path lands there. |
| `read_scope` | `content-folders` | What the locked apps may read: `content-folders` = the output folder plus your Desktop, Documents, Downloads, Pictures, Videos and Music folders (wherever Windows keeps them); `write-root-only`; or `home` (your whole home folder). |
| `extra_read_root` | empty | One more folder the locked apps may read. It must exist, and it may not be a drive root or contain your settings folders (use `read_scope` `home` for that). |

**PhotoCraft, PdfCraft and WordCraft read exactly one folder.** By default that is the output folder: copy an input
into it first. If you set `extra_read_root`, they read only that folder, so they cannot reopen their own saves
unless the output folder is inside it: to keep that, put `write_root` inside it (for example `extra_read_root` ~/Art
and `write_root` ~/Art/out). With `read_scope` `home`, they read your whole home folder.

The launcher refuses an output folder that is your home folder, a drive root, overlaps `~/.claude`, `~/.ssh`,
AppData, Program Files or the Windows folder, or holds a `.git`, `.claude` or `CLAUDE.md` within two levels: keep it
an outputs-only folder, never a code project or a folder you run Claude Code in. It also refuses to start a lockable
app whose version is too old to take the folder flags, and says which version is needed.

To change the folders, use `/plugin` → creative-apps-mcp → configure, or:

```bash
echo '{"write_root":"/path/to/outputs","read_scope":"content-folders","extra_read_root":"/path/to/sources"}' \
  | claude plugin configure creative-apps-mcp@sawizzle-plugins --values-stdin
```

### Apps you have not installed
Their servers show as failed in `/mcp`; nothing runs for them. To hide one, disable that server in `/mcp`. After
you install or update an app, open `/mcp` and choose **Reconnect** on its server: Claude Code may not retry a failed
plugin server on its own for a while. To see which folders and CLI the launcher used, set `CRAFT_MCP_LOG` to a file
path before starting Claude Code; each server start, or each refused start with its reason, appends one line.

If servers fail that should start, the launcher's reason is on stderr, which `/mcp` does not show: the CLI was not
found; the app is too old to be locked to folders; its version could not be read; `extra_read_root` (or PhotoCraft's
0.2.0 read folder) is missing or too wide, which stops all nine locked apps; or the output folder is refused, which
stops all 13. `CRAFT_MCP_DRY_RUN=1 node plugins/creative-apps-mcp/scripts/craft-mcp.mjs <app> mcp` in a clone prints
what it would start, or the reason it refuses.

### Without Node
Register the apps you want directly. For example, on Windows:

```bash
claude mcp add --scope user filmcraft -- "C:\Users\<you>\AppData\Local\Programs\ArtCraft\FilmCraft\filmcraft-cli.exe" mcp
```

(the installer's per-user folder, written out in full: Claude Code does not expand `%LOCALAPPDATA%`;
`C:\Program Files\ArtCraft\FilmCraft\` for an all-users or Craft Launcher install). Registered this way, the app gets
Claude Code's full environment and none of the launcher's folder checks.
Add `--automation-read-root <folder> --automation-write-root <folder>` for the apps that take them. The skills
still apply: install the plugin for the skills and disable its servers, or copy the `skills/` folders into
`~/.claude/skills/`.

## Upgrading

### From 0.2.0
Third-party marketplaces do not update automatically:

```bash
claude plugin marketplace update sawizzle-plugins
claude plugin update creative-apps-mcp@sawizzle-plugins
```

Then restart Claude Code (or run `/reload-plugins`). What changes:
- **Six new apps:** FigCraft, WordCraft, DeckCraft, GridCraft, CADCraft and SoundCraft. **GridCraft and CADCraft cannot
  be locked to folders** and are enabled after the update if they are installed; disable them in `/mcp` if you do not
  use them.
- **The launcher finds the new install folders** (`ArtCraft\<App>`) that 0.2.0 missed.
- **Nine apps are now locked to folders** (see [Folders](#folders-the-apps-may-use)). Files go to `~/CreativeApps`
  unless you set `write_root`. PhotoCraft's default output folder moves from `~/PhotoCraft` to `~/CreativeApps`, and
  its default read folder is no longer your whole home folder. If you had set PhotoCraft's folders in 0.2.0, those
  settings still apply to PhotoCraft, with the new checks: a read folder that is missing, a drive root or contains
  settings, or an output folder that holds code projects or Claude settings, now stops PhotoCraft until you change it.
- **Apps too old to be locked are not started** (for example VectorCraft before 0.9.0): update them.
- **EffectCraft scripts are off** while EffectCraft is locked (`run_script` is refused). See the effectcraft skill.
- The launcher moved from `bin/` to `scripts/`, and passes the apps only the environment variables they need.

### From 0.1.x (renamed in 0.2.0)
Versions up to 0.1.2 were published as `artcraft-mcp` from the marketplace `sawizzle-artcraft`. Remove it first;
running both gives you duplicate servers and skills.

```bash
claude plugin marketplace remove sawizzle-artcraft     # also uninstalls the old plugin and clears its saved options
claude plugin marketplace add sawizzle/creative-apps-claude-plugin
claude plugin install creative-apps-mcp@sawizzle-plugins
```

Permission rules and hooks written for `mcp__plugin_artcraft-mcp_*` stop matching; rewrite them for
`mcp__plugin_creative-apps-mcp_*`. Skills are now `/creative-apps-mcp:<app>` and `/creative-apps-mcp:creative-apps-setup`.

## Security

- **The launcher runs the first CLI it finds** (`<APP>_CLI`, PATH, the install folders, the registry); `--where`
  shows which. Anyone who can write to those places as you can already run programs as you.
- **Locked apps** (PhotoCraft, VectorCraft, PdfCraft, EffectCraft, DesignCraft, FigCraft, WordCraft, DeckCraft,
  SoundCraft) refuse paths outside their read folders and output folder, with app-specific gaps: a few EffectCraft,
  SoundCraft and DeckCraft commands can still reach outside them. Those gaps are being reported privately to the developers, and
  their details stay out of this repository until they are fixed; the apps' skills tell Claude what to avoid.
  What each one refuses, and the gaps, were measured; see the table below.
- **FilmCraft, LightCraft, GridCraft and CADCraft cannot be locked.** They can read, overwrite or move any file you
  can, including network paths. While any of them is enabled, the plugin does not protect your files from an agent
  that has been misled. Disable the ones you do not use in `/mcp`. LightCraft's import `mode: move` deletes the
  originals.
- **Document content is data, not instructions.** Text in images, layers, PDFs, slides, cells or timelines can try
  to steer the agent. Read the paths in tool calls before you approve them, and don't "always allow" the open,
  save, export or import tools of the four apps that cannot be locked.
- **Anything the apps can read can end up in the conversation.** Keep keys and credentials out of the read folders;
  think twice before setting `read_scope` to `home`.
- **Exports overwrite existing files without asking.**
- **At startup no server listens on a network port** (measured on all 13, headless, stdio only; the locked FigCraft
  refuses its collaboration-hosting commands; commands of the unlocked apps were not measured). Live mode (`--control`) does open a local port; according to the apps' own docs, on seven of them that port has
  **no authentication** (the `creative-apps-setup` skill lists them; live mode was not tested).
- **Started through the plugin, the apps get only the environment variables they need** (paths, locale, display, GPU selection, and proxy and
  CA settings for their model downloads; a proxy URL can contain credentials), never your tokens or keys.
  `CRAFT_MCP_PASS_ENV=NAME1,NAME2` passes more by name.

**What the folder lock refuses, measured** (Windows 11, the versions in the table at the top, with `read_scope`
`write-root-only` plus one extra read folder; the batteries are `tests/sandbox/<app>.json`; † measured in separate runs
that are not part of the shipped battery):

| App | Read folders | Refused | Gaps found |
|---|---|---|---|
| PhotoCraft | one | outside paths, any `..`, junctions, network paths, device names, `:` streams; engine commands that take their own paths are disabled | none found (hard links not tested) |
| VectorCraft | several | outside paths, `..` that leaves a folder, junctions, network paths (even into a folder), device names, `:` streams (from 0.20.0) | none beyond hard links |
| PdfCraft | one | outside paths, `..` that leaves a folder, junctions, network paths (even into a folder)†, device names | none beyond hard links |
| EffectCraft | several | outside paths, relative paths, any `..`, junctions, scripts (refused while locked) | some, being reported privately to the developers; `NUL.png`/`CON` are written as ordinary files |
| DesignCraft | several | outside paths, `..` that leaves a folder, junctions, network paths (even into a folder)†, device names | none beyond hard links |
| FigCraft | several | outside paths, `..` that leaves a folder, junctions, network paths, device names, `:` streams | none beyond hard links |
| WordCraft | one | outside paths, `..` that leaves a folder, junctions, network paths (even into a folder)†, device names | none beyond hard links |
| DeckCraft | several | outside paths, `..` that leaves a folder, junctions, network paths (even into a folder)†, device names | some, being reported privately to the developers†; a shape's "run program" action and `file:` links can point outside the folders (DeckCraft never runs them; a `.pptx` export keeps them)† |
| SoundCraft | several | outside paths, `..` that leaves a folder, junctions, device names | some, being reported privately to the developers; some commands write through files that are hard links |

**Hard links:** the lock checks paths, so a hard link that someone placed inside an allowed folder can still lead to a
file elsewhere. These gaps are in the apps, not in this plugin; the apps' skills tell Claude how to stay clear of them.

## What the skills cover
- **`creative-apps-setup`:** finding each app's CLI (installer, Craft Launcher, macOS, Linux), the folder options,
  live mode with the ports, flags and tokens for each app, security, and how to report bugs upstream.
- **One skill per app:** a workflow tested end to end (create, edit, render a preview, save and export, reopen the
  saved file in a new process and check it), the important tools, and the traps.

## Test your setup
The tests live in this repo, not in the installed plugin, so clone it first.

```bash
git clone https://github.com/sawizzle/creative-apps-claude-plugin
cd creative-apps-claude-plugin
python3 tests/run_all_tests.py --allow-skip --any-version   # every installed app (on Windows: python)
python3 tests/run_all_tests.py filmcraft --any-version      # one app
python3 tests/test_launcher.py                              # the launcher's own tests; no app needed
```

You need Python 3.9+, Node 18+ and `ffmpeg`/`ffprobe` on PATH. Each app runs a scripted sequence over MCP through the
plugin's launcher and `.mcp.json` (with `read_scope` `write-root-only`, the inputs copied into the output folder, and
fixed fonts and paper size): create, edit, render, save and export, then reopen in a fresh process. Most steps check
the result (colours, sizes, text inside the saved file), not only that the call returned. The locked apps also run a
battery of paths that must be refused; the batteries are Windows-only and are skipped elsewhere (`--no-sandbox` skips
them anywhere). The run is strict: an app version other than `tests/versions.json` fails unless you pass
`--any-version`, and a run in which no app was found fails. Each run goes to `tests/out/<run-id>/`, with a
`contact_sheet.png` that labels every image with its app, version and run.

**Open the contact sheet and the exports.** A passing check doesn't prove the picture is right. If you report a
bug, attach the failing `tests/steps/<app>.json` step and the `<app>_report.json` from the run folder.

## Bugs found while building this
All fixed upstream:
- [storytold/filmcraft#499](https://github.com/storytold/filmcraft/issues/499): `media_import` took a `text` string;
  it now takes `paths`.
- [storytold/photocraft#2176](https://github.com/storytold/photocraft/issues/2176): absolute paths inside the
  automation roots were rejected.
- [storytold/pdfcraft#640](https://github.com/storytold/pdfcraft/issues/640): `pdfcraft-cli mcp` accepted unknown
  options without complaint.
- [storytold/vectorcraft#849](https://github.com/storytold/vectorcraft/issues/849#issuecomment-6091137205): the GUI
  picked the integrated GPU on machines with two GPUs.
- [storytold/designcraft#289](https://github.com/storytold/designcraft/issues/289): character formatting at a caret
  inside existing text was discarded (it now applies to the next text you type).

## License
MIT OR Apache-2.0, at your option. Unless you state otherwise, any contribution you submit is
dual-licensed in the same way, with no additional terms.

<sub>Adobe, Photoshop, Illustrator, Premiere Pro, Lightroom, Acrobat, After Effects and InDesign are trademarks or
registered trademarks of Adobe Inc. Figma is a trademark of Figma, Inc. Microsoft, Word, PowerPoint and Excel are
trademarks of Microsoft Corporation. AutoCAD is a trademark of Autodesk, Inc. Pro Tools is a trademark of Avid
Technology, Inc. They are named here only to describe what each app is comparable to. Windows is a trademark of
Microsoft Corporation, macOS of Apple Inc., Linux of Linus Torvalds, and Node.js of the OpenJS Foundation; other
names belong to their owners. This project is not affiliated with any of them.</sub>
