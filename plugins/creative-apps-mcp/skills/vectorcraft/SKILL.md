---
name: vectorcraft
description: Unofficial third-party skill. Drive VectorCraft (open-source Illustrator-style app) through its MCP server - draw shapes, paths and type, recolour, transform, add effects and pathfinder, then render and export SVG, PDF, PNG, AI, EPS or DXF. Use when the user wants vector art, icons, logos or posters made or edited in VectorCraft.
---
Server: `vectorcraft` (`vectorcraft-cli mcp --headless`). Tested with vectorcraft-cli 0.20.0 on Windows 11 (the plugin's regression steps; written against 0.19.0).

A headless server starts in a few hundredths of a second, so use a fresh process per job or reopen. Always give
a mode: a bare `vectorcraft-cli mcp` drives whatever listens on 127.0.0.1:7979 without checking which app it
is. The root flags imply `--headless`. `prompts/list` offers poster, icon-set, recolor, trace-and-style and
export-set workflows.

## File access
- Reads are held to `--automation-read-root` folders, writes to `--automation-write-root` folders; both flags
  repeat. The write root grants no read: to reopen your own saves, that folder must also be a read root.
- Refused (`automation path rejected`): paths outside the roots, `..` out of a root, a junction in a root that
  points out, UNC paths (even `\\localhost\C$\…` back into a root), device names (`NUL.png`, `CON`) and, from
  0.20.0, alternate data streams (`a.png:x.png`, "alternate data streams are not allowed"), also
  inside `run_command`, `command_run`, `command_batch`, `command.batch`, `invoke_menu`, `screenshot`, `file.list`.
- Not refused: relative paths (resolved against the server's working folder; `..` is resolved first, so
  `sub/../x.png` is fine and only a `..` that leaves the root is refused), and reading through a hard link in a
  root to a file outside. (0.19.0 wrote `a.png:x.png` as a hidden stream; 0.20.0 refuses it.)
- Exports never create folders (os error 3). A missing root folder stops the server at start.
  `run_command file.list {"path":DIR}` lists what you may open. Use absolute paths.

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from the output folder plus, by default, the user's Desktop, Documents, Downloads, Pictures, Videos and Music folders (option `read_scope`: `write-root-only` drops those, `home` opens the whole home folder; `extra_read_root` adds one more). It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.

## Workflow
1. `inspect_document {"depth":0}`: one 612×792 pt document is open. `run_command file.new
   {"name":"Poster","width":800,"height":600}` adds one and makes it active.
2. Draw; each returns `{id}`:
   - `draw_shape {"shape":"rectangle","x":50,"y":50,"width":300,"height":200,"radius":16,"fill":"#ff6633","stroke":"none","name":"Card"}`.
     ellipse: x, y, width, height; polygon: cx, cy, radius, sides; star: cx, cy, radius1, radius2, points;
     line: x1, y1, x2, y2.
   - `draw_path {"points":[[0,0],[100,0],[50,80]],"closed":true}` or `{"d":"M0 0 L100 0 L50 80 Z"}`.
   - `add_text {"text":"Hi","x":70,"y":120,"size":32,"color":"#ffffff"}` (y is the first baseline).
3. Edit: `set_paint {"ids":[N],"fill":"#22aa44"}`, `transform {"ids":[N],"dy":300}` (also rotate, scale %),
   `run_command text.setText {"id":T,"text":"New"}`, `apply_effect {"ids":[N],"effect":"stylize.dropShadow",
   "params":{"x":5,"y":5,"blur":3}}`, `pathfinder {"operation":"unite","ids":[A,B]}` (returns the new id),
   `run_command edit.clear {"ids":[N]}`.
4. Read back: `run_command document.node {"id":N,"summary":true}` (bounds, fill hex, kind, name) and
   `run_command document.find {"text":"New"}` (or name, kind).
5. Look: `render_preview {}` returns the artboard as PNG at 1 px per pt, long side capped at 1024 px
   (`max_side` sets the cap). Open it first.
6. `save_file {"path":"/abs/art.vectorcraft"}`; `export {"path":"/abs/art.png","scale":2}`. The extension or
   `format` picks svg, pdf, ai, eps, dxf, png, jpg, webp, tiff, psd and more; no `path` returns `dataBase64`.
7. Reopen in a fresh process with `open_file {"path":…}`. It becomes the active document, which later exports
   use. Ids survive a .vectorcraft reopen, and a PDF or AI one while the native copy is embedded (default).
8. `command_batch {"atomic":true,"label":"Two","steps":[{"id":"draw_shape","params":{…}},{"id":"object.move",
   "params":{"ids":["$0.id"],"dx":10,"dy":0}}]}` returns `{completed, failed, results, created}` and stops with
   isError at the first failure. `atomic` only makes it one undo step named by `label`: steps done before a
   failure stay (one `undo` removes them). `run_command command.batch {"commands":[…]}` rolls back if one fails.

## Traps (measured): a reply of ok is not proof
- Params are checked unevenly: `object.move` rejects unknown keys and `object.rotate` a string angle, but
  `paint.setFill` and `document.export` ignore unknown keys. `object.move {}` and `transform {"dx":"10"}` reply
  ok and move nothing. Read the object back.
- Colours: `[r,g,b]` is 0..1; `[255,128,0]` is clamped to `#ffff00` while the reply echoes it. `#rrggbbaa`
  drops the alpha: pass `opacity` (0-100) to `draw_shape` or `run_command object.setProps {"id":N,"opacity":50}`
  (`set_paint` has no `opacity`); it reads back as `opacityPct`.
- New-art paint drifts: a paint given to `draw_shape` or `set_paint` becomes the default for later shapes, and
  `add_text` without `color` takes the fill. Only in a fresh document do unpainted shapes get a white fill and a
  1 pt black stroke.
- A negative `strokeWidth` is stored as 0 but echoed. A star with `points:2` is accepted.
- `text.editRange` needs `start` and `end` (bytes): `{id, insert}` alone replaces all the text.
- A missing font still succeeds and renders in Source Sans 3; `run_command text.missingFonts` lists it.
- Undoing a creation reuses its id; deleted ids are not reused. An SVG reopen renumbers ids and turns live
  shapes into `Path`.
- Live effects don't show in `inspect_document` or the summary: use `run_command effect.list {"ids":[N]}`.
- Saves and exports overwrite silently. `export` with no extension, or a trailing dot (`x.svg.` lands as
  `x.svg`), writes PNG bytes; `save_file` writes the native format there.
- Empty areas export transparent (a pixel check reads 0,0,0) though `render_preview` shows them white: draw a
  background if you need one.
- Headless `file.close` on a modified document closes it without asking; once none is open, document tools
  fail until `file.new` or `open_file`. Headless `save_file {}` on a never-saved document is an error.
- PDF and AI exports embed the native document by default; pass `"options":{"preserveEditing":false}` for a
  plain PDF. `save_file` to .svg warns about losses, `export` doesn't.
- `vectorcraft-cli info FILE` prints object counts by kind and fonts: a quick independent check of a save.

## Live app (from the app's docs, not tested)
Start `vectorcraft --control <port>` with its own root flags and connect with `--connect 127.0.0.1:<port>`
(root flags plus `--connect` are refused). `ui_*`, `inspect_ui`, `type_text`, `open_panel` and `answer_dialog`
need the window. `save_file` without a path on an untitled document opens a dialog and replies `pending`.
