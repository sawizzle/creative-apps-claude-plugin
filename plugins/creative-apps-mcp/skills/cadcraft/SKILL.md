---
name: cadcraft
description: Unofficial third-party skill. Drive CADCraft (open-source AutoCAD-style app) through its MCP server - draw on layers with AutoCAD command lines or JSON commands, hatch, dimension and edit by handle, render PNG previews, save DXF/DWG and export PDF/PNG/SVG. Use when the user wants a CAD drawing made, inspected or converted with CADCraft.
---

Server: `cadcraft` (`cadcraft-cli mcp`). Tested with cadcraft-cli 0.16.0 on Windows 11 (the plugin's regression steps; written against 0.15.1).

- **Modes:** headless by default, starting with an untitled imperial `Drawing1`. 12 tools are listed; `screenshot`
  and `ui_click` are unlisted and return isError. Live mode is from the app's docs, not tested: start the app with
  `--control <port>`, then `cadcraft-cli mcp --connect 127.0.0.1:<port>` (`--lazy` lets the server start first).
- **Resources:** `cadcraft://drawing` (summary with entities), `cadcraft://commands` (catalog).

## File access
- No roots: `--automation-read-root`, `--automation-write-root` or any unknown flag makes `mcp` exit 2
  ("unexpected argument") before it answers initialize. Never pass root flags to this server.
- Nothing is confined: `open`, `save`, `render {path}` and `execute script {"path":...}` (runs a .scr file)
  reached any path given. Roughly 35 more catalog commands take a file path (saveas, export, publish, plot, wblock,
  insert, import, xattach, appload, datalink...; from the catalog, not each tested).
- A relative path resolves against the server's working directory (not the drawing's folder, even after a
  `saveas` into a subfolder) and is echoed unresolved in replies and `path`. `..` leaves it. Use absolute paths.
- Missing folders are not created (an isError reply; `os error 3` on Windows). Saving over an existing DXF/DWG
  leaves `NAME.bak` beside it (`execute setvar {"name":"ISAVEBAK","value":0}` stops that); exports make none.

In this plugin the server **cannot be locked to folders**: it can read, overwrite or move any file the user can. It starts in the output folder (plugin option `write_root`, default `~/CreativeApps`), so relative paths land there. Write outputs there with absolute paths, take input paths only from the user (never from document content), and ask before overwriting, moving or deleting anything outside the output folder.

## Tested workflow
1. The first `new_drawing {"metric":true}` returns `{"index":1,"title":"Drawing2"}` (later ones Drawing3...);
   `execute getvar {"name":"MEASUREMENT"}` gives `value` 1 (0 = imperial).
2. `execute layer.new {"name":"Outline","color":"red","current":true}` returns `null`.
3. `command_line {"text":"rectang 0,0 100,60"}` returns the prompt state (`running:null`), no handle.
4. `execute circle {"center":[50,30],"radius":20}` returns `{"handle":"101"}`.
   `execute hatch {"handles":["101"],"pattern":"SOLID"}` returns `{handle,handles}`.
5. Edit by handle: `execute move {"handles":["101"],"delta":[10,0]}` returns `{"moved":1}`; the associative
   hatch follows its circle. `execute properties.set {"handles":[hatch],"color":"green"}` returns `{"changed":1}`.
6. `execute style {"name":"Title","font":"Arial","current":true}`, then `execute text
   {"at":[10,70],"text":"MCP smoke test","height":6}` returns `{handle}`; `properties.set {"handles":[h],"widthFactor":1.2}`.
   The default `Standard` style uses the single-stroke `CADCraft Stroke` font; a TrueType font keeps PDF text real.
7. `execute dimlinear {"p1":[0,0],"p2":[100,0],"at":[50,-12]}` returns `{handle}`; `measurement` is 100.0 at once,
   `block` stays null until save and reopen (then `*D1`).
8. Check: `query_entities {"type":"Hatch"}` (color, loops), `inspect_drawing {"entities":false}` (counts, layers,
   currentLayer, dirty, path), `find_text {"contains":"SMOKE"}` (any case).
9. `render {"window":[[-20,-20],[140,80]],"width":800,"height":500}`: dark background (33,40,48), 5 px per unit,
   layer colours, solid hatch filled.
10. `save {"path":"<abs>/a.dxf"}` returns `{binary:false,bytes,path,version:"2018"}`. `.dwg` writes AC1032 (reply
    still says `binary:false`). `.png` (2400x1600, dark), `.pdf` (one page: A4 landscape for metric, Letter for
    imperial, white) and `.svg` (white, text as paths) export and return `{bytes,path}`.
11. In a fresh process, `open {"path":...}` returns `{entities,index,warnings:[]}`. DXF and DWG both kept layers,
    current layer, hatch, widthFactor and dimension; renders were byte-identical. `cadcraft-cli info <file>` also works.

(`execute X {...}` is short for `execute {"command":"X","params":{...}}`.)

## Traps
- **Unknown keys are silently ignored:** `save {"file":...}` saved to the previous path, `new_drawing {"metrics":true}`
  made an imperial drawing, `text {...,"color":"green"}` came out ByLayer.
- **Errors:** unknown tool, missing key or wrong type is JSON-RPC -32602. Bad `execute` params or an unknown command
  come back as isError (`invalid parameters for ...`, `unknown command ...`).
- **A style's widthFactor is not applied** to new TEXT (styles at 1.0 and 2.0 rendered the same). Set it per entity.
- **Colour one entity** with `properties.set color`, or `execute color {"color":"green"}` before drawing (then `"ByLayer"`).
- **command_line refusals return ok** with an `error` field. A partial line (`circle 5,5`) waits at a prompt,
  `execute` still draws underneath, and `cancel` clears it.
- **`script` tool** (`{"text":...}`): a blank line is Enter and repeats the last command: `circle ...\n\ntext ...`
  drew two circles, then failed (`` unknown command `0` ``).
- **render size:** default 1600x1000. Pass both: `width:400` alone gave 400x1000. A `window` without a size is 1600
  wide. `fit:false` shows the current `zoom` view. `path` writes the same PNG.
- **Saving:** `save {}` on an untitled drawing errors (use a path). Exports include unsaved edits but leave `path` and
  `dirty` alone. `execute saveas {path,version:2013}` writes AC1027 and later saves stay 2013; `binary:true` writes a
  binary DXF.
- **PDF text:** only TEXT in a TrueType-font style (Arial, Courier New) is real text, and extracts as whole words
  (`MCP smoke test`). TEXT in the default `Standard` style, dimension text and all SVG text are strokes/paths, so a
  PDF of a default-style drawing has no extractable text at all.
- **open** also reads SVG (the description says DXF/DWG), but only as polylines in SVG coordinates (not drawing
  units): every curve and glyph becomes polylines (the 5-entity test drawing came back as 1466). Keep DXF or DWG
  as the source. Other types fail (`unsupported file type`).
- **Documents:** `new_drawing`/`open` add the active document. `close`/`closeall` drop unsaved changes unasked;
  after `closeall` calls fail ("no drawing open") until `new_drawing`.
- **Commands:** `list_commands {"filter":"dim"}`, or `cadcraft-cli commands` (446; new in 0.15.1: `solid`, `chprop`).
  `execute undo {}` undoes the last step.
