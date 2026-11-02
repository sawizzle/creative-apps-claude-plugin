---
name: figcraft
description: Unofficial third-party skill. Drive FigCraft (open-source Figma-style app) through its MCP server - build frames, shapes and styled text, edit and inspect layers, take screenshots, save .figcraft and export PNG, SVG, JPG or PDF. Use when the user wants a UI screen, card or mockup built, checked or exported with FigCraft.
---

# FigCraft via MCP

Server: `figcraft` (`figcraft-cli mcp`). Tested with figcraft-cli 0.14.0 on Windows 11 (the plugin's regression steps; written against 0.13.1).

Headless: an in-process engine with one `Untitled` document and no window. 19 tools; `list_commands {"filter":"align"}`
(plain-text list) and `run_command {"command":id,"params":{}}` reach about 630 engine commands; calls take milliseconds.

## Workflow (measured)
1. `run_command {"command":"file.new","params":{"name":"Smoke"}}` → `{"index":1,"kind":"design"}` (new tab, in front).
2. Build in one undo step; `"as"` names a step and `{"$ref":"card"}` stands for its id:
   `batch {"commands":[{"command":"node.create","as":"card","params":{"type":"frame","name":"Card","width":400,"height":240,"props":{"fill":"#3366FF","cornerRadius":16}}},`
   `{"command":"node.create","params":{"type":"text","text":"Hello","parent":{"$ref":"card"},"x":24,"y":24,"props":{"fontFamily":"Inter","fontStyle":"Bold","fontSize":32,"fill":"#FFFFFF"}}},`
   `{"command":"node.create","params":{"type":"ellipse","parent":{"$ref":"card"},"x":300,"y":140,"width":72,"height":72,"props":{"fill":"#FFD43B"}}}]}`
   → `[{"id":2},{"id":3},{"id":4}]`. Styles go in `props`. x/y are parent-relative (child 10,10 in a frame at 100,50 →
   `absoluteBounds` 110,60). `"onError":"continue"` keeps going past a failed step.
3. Edit: `set_properties {"ids":[2],"props":{"fill":"#2B8A3E"}}`, `{"ids":[3],"props":{"characters":"Edited"}}`,
   `{"ids":[4],"props":{"x":40}}` → `{"ok":true,"nodes":[...]}` with the new values.
4. Verify: `get_node {"id":2,"depth":1,"fields":["name","fills","characters","x"]}` (fills read back as
   `[{"type":"solid","color":"#2B8A3E"}]`). `screenshot {}` → PNG of the page content on its #F5F5F5 background
   (`source:"page"`); `screenshot {"ids":[2]}` → that layer alone (`source:"layers"`).
5. Save: `save_file {"path":"<abs>/card.figcraft"}` → `{bytes, path}` (a zip: document.json + thumbnail.png).
   Export: `export {"format":"png","ids":[2],"path":"<abs>/card.png","scale":2}` → 800x480; `"size":"512w"` instead of
   `scale`; `pdf`, `jpg` (transparent areas come out white; or let the extension decide), `svg` (text outlined
   unless `"svgOutlineText":false`).
6. Reopen: `open_file {"path":...}` → `{document, opened:{index, repairs, summary}}`; `document.pages[0].children`
   lists top-level layers only, so read deeper with `get_node`. After a server restart the reopened ids, fills and text
   matched and `screenshot {}` was byte-identical.
- Outside MCP: `figcraft-cli info <file> --json` and `figcraft-cli render <file> -o x.png` (same pixels as `screenshot {}`).

## File access
- `--automation-read-root DIR` / `--automation-write-root DIR`, both repeatable (two of each worked). Each
  folder must exist, or the server exits 1 before `initialize`. A write root is readable too, so saves reopen without an
  extra read root. A read root with no write root refuses every write ("no folder may be written").
- Paths are resolved (relative ones against the server's working directory, `..`, case, `\\?\`, junctions) and then
  checked, in every tool and inside `run_command`/`batch` params (file.export, file.saveAs, file.open, file.import,
  image.place, file.exportLayers, variable.import/export, plugin.import). Refused with
  "automation path rejected: <path> is outside the folders that may be read" (or "written"): `..` leaving a root, a
  junction pointing out, UNC paths (`\\host\share`, `//host/share`), a bare `CON` or `<dir>/nul`. Device names with a
  folder or an extension (`<dir>/CON`, `NUL.png`, `COM1.png`, `aux.png`, `CONIN$`) and stream suffixes (`a.png:x`,
  `a.png::$DATA`) are refused as "a device or stream name, not a file". `..` that stays inside is fine. The check is
  by path: a hard link inside a root to a file elsewhere could be opened.
- `data.fill {"dir":...}` outside the roots is not an error: the copies are made and each refused file is in `errors`.
- Pass absolute paths: a relative one lands in the server's working directory and is echoed back relative. A missing
  parent folder fails ("os error 3") and is not created.
- `--attach` refuses the root flags (exit 2); an attached app is confined by the roots it was started with (help text,
  not tested).

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from the output folder plus, by default, the user's Desktop, Documents, Downloads, Pictures, Videos and Music folders (option `read_scope`: `write-root-only` drops those, `home` opens the whole home folder; `extra_read_root` adds one more). It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.

## Traps
- Unknown keys are errors: `create_node {"fill":...}` → "unknown argument `fill` (it takes ...)"; `save_file
  {"file":...}` → "unknown argument `file`"; `set_properties` lists the known props.
- `export` without `ids` exports the selection, and new layers become the selection: after a batch a bare export wrote
  only the last layer created. With nothing selected (`select {"ids":[]}`) it exports every top-level layer on
  transparency. Pass `ids`. Without `path` it returns the image (SVG as text).
- `select.byName {"query":"card"}` is a case-insensitive substring match (Card, Card copy and MYCARD).
- `document` (an id from `run_command doc.list`, or the file's path) acts on a background tab without switching.
- `open_file` on a file that is already open returns that tab with its unsaved edits (`dirty:true`) rather than the
  disk copy; `"reload":true` is refused while it is dirty. `file.close` needs `"force":true` on a dirty tab. Saving an
  `Untitled` document renames it after the file.
- Fonts fall back silently: a missing family renders in a sans while the layer keeps its `fontFamily`, with no warning.
  Check `run_command {"command":"text.missingFonts","params":{}}` → `{"families":[{"family":...,"layers":1,"source":null}]}`.
  Installed fonts are used by default (renders vary by machine); `--no-system-fonts` keeps only the 25 families
  bundled with FigCraft (`run_command text.fonts` lists them: Inter, Roboto, Open Sans, Lato, Montserrat, Poppins,
  Merriweather, Playfair Display, Liberation Sans/Serif/Mono and others), so Georgia or Arial then fall back too.
- `type_text {"id":3,"text":"..."}` replaces a layer's text; without `id` it needs an active edit, else "not editing
  text". Headless, `wait_for_changes` returns at once and `window.new` returns ok but opens nothing.
- Live app (help text, not tested): `figcraft --control <port>`, then `figcraft-cli mcp --attach <port>`. With nothing
  listening, `--attach 47999` exits 1 within a second: "can't reach the FigCraft app at 127.0.0.1:47999".
