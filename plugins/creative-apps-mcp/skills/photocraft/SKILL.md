---
name: photocraft
description: Unofficial third-party skill. Drive PhotoCraft (open-source Photoshop-style app) through its MCP server - create or open images, edit with engine commands (shapes, text, filters, adjustments, smart objects), preview, save .pcraft and export PSD/PNG/JPEG/TIFF/WebP. Use when the user wants to edit, composite or convert raster images with PhotoCraft.
---

# PhotoCraft via MCP

Server: `photocraft` (`photocraft-cli mcp`). Tested with photocraft-cli 0.19.0 on Windows 11 (the plugin's regression steps; written against 0.18.0).
Headless unless started in bridge mode (see Live mode).

## File access
- Nothing is readable or writable without roots. `--automation-read-root DIR` grants reading only,
  `--automation-write-root DIR` grants writing only. Each flag may be given **once** (a second one stops the
  server, exit 2) and the folder must exist (exit 1).
- **The write root does not grant reading.** To reopen your own saves and exports, the read root must contain
  the write root.
- Paths: absolute inside a root, or relative with `/`. Relative reads resolve against the read root and
  relative writes against the write root, never the working directory. So `doc_save {}` on a document opened
  by a relative path writes relative to the **write** root: when the roots differ it fails (NotFound) or
  writes a second file there, reports success and leaves the opened file unchanged. Open by absolute path, or
  pass `path`.
- Refused: paths outside the roots (also UNC, `\\?\`, `\\.\`), any `..` segment (even one that stays inside),
  a `.` segment in a relative path (in an absolute path it is accepted and dropped), `\` in a relative path,
  `:` streams, device names (`CON`, `NUL.png`, `COM1.png`, `CONIN$`), and junctions under either root, even
  ones pointing back inside it.
- Engine commands with their own file paths (`file.saveACopy`, `file.openAs`, `file.placeEmbedded`, batch,
  presets, `.icc`/`.cube` files, plug-ins) are disabled under MCP: use the `doc_*` tools. Built-in profile ids
  still work (`edit.convertToProfile {"profile":"srgb"}`).
- `doc_import_data_sets` imports any comma-separated text file under the read root (any extension) and
  `variables.list` returns its cells: keep secrets out of the read root.
- `PHOTOCRAFT_CONTROL_PORT` in the environment switches to bridge mode, and the root flags then stop the server
  (exit 2). The token variables alone do not.

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`, or PhotoCraft's write folder from plugin 0.2.0 if set) and reads from exactly one folder: by default the output folder; if the user set `extra_read_root` (or PhotoCraft's read folder from plugin 0.2.0), only that folder, so it cannot reopen anything in the output folder (its own saves included) unless the output folder is inside it
(the user can put `write_root` inside `extra_read_root` to keep that); with `read_scope` set to `home`, the whole home folder. With the default, copy a file from elsewhere into the output folder first with your own file tools, so the user sees and approves the copy. It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.

## Workflow
1. `doc_new {"width":640,"height":400,"background":"#ffffff","name":"x"}` -> `{"document":0}`, or
   `doc_open {"path":...}` -> `{index,name,width,height,layers,warnings}`.
2. `command_list {"filter":"blur"}` gives ids and params docs. Always filter: the full list is over 100 KB.
3. `command_run {"id":...,"params":{...}}`, for example:
   - `shape.create {"kind":"rect","rect":[x,y,w,h],"fill":"#ff0000","name":"Box"}` -> `{layer,bounds,...}`
   - `type.create {"x":60,"y":300,"text":"Hello","size":36,"color":"#0000ff"}` (y = baseline) -> `{layer,bounds}`
   - `filter.blur.gaussianBlur {"radius":4}` acts on the active layer; on a smart object it becomes a smart filter.
   - `layer.setProps {"layer":id,"opacity":0.5}` returns `null`: read it back.
   - `doc_place {"path":...,"scale":25,"center":[480,120]}` places a smart object.
4. `doc_inspect`: layers top to bottom (`id`, `kind`, `bounds`, `opacity`, `text`, `smartFilters`),
   `history`, `revision`. `type.info {"layer":id}` gives text and runs.
5. `doc_render_preview {"max_side":1024}` returns a PNG. Look at it before you export or report.
6. `doc_save {"path":".../x.pcraft"}` (lossless; keeps layer ids, smart filters and notes). `doc_export` with
   `.png`, `.psd`, `.tif`, `.webp`, `.exr`, or `.jpg`. `"quality":1..100` sets JPEG quality and makes WebP
   lossy (without it WebP is lossless). Flat formats warn "N layer(s) flattened".
7. `doc_save {}` writes back only a `.pcraft`/PSD/PSB/OpenRaster file that sits inside the write root; anything
   else needs `path`.

## Traps (measured on 0.18.0)
- **Bounds:** `shape.create` and `doc_inspect` use `[x,y,w,h]`; `type.create` and `doc_place` return `[x0,y0,x1,y1]`.
- **Colours:** use `"#rrggbb"`. `edit.fill` paints **black** for `"red"` or `"#f00"` with no error. Arrays are
  0..1, so `[128,128,128]` is white (`edit.fill`, `tools.setColors`, shape `fill`).
- **Validation:** filters reject bad types, unknown keys, `null` and out-of-range values. Adjustments reject bad
  types but accept `null` and clamp numbers, and a misspelled key (also in `layer.setProps`) is a no-op. Each of
  these still adds a history step.
- **Layers:** `layer` takes an id or a whole layer name, case-insensitive (`"box"` finds `Box`, `"Bo"` finds
  nothing); `"3"` is a name. `select.findLayers` is a case-insensitive substring (`Layer 1` also selects
  `Layer 10`). Ids survive `.pcraft` save and reopen; PSD renumbers them. A `.pcraft` keeps its saved name, so a
  renamed copy reopens under the old name: key on `path`.
- **command_batch** returns `isError:false` when a step fails: check `completed`, `failed`, `results[].ok`. It
  stops at the first failure unless `"stop_on_error":false`, and is not atomic.
- **History:** `revision` rises on every edit, undo and redo. `doc_inspect` has no `dirty`; `session_list` does.
- **Jobs:** `"wait":false` -> `{job,pending:true}`. Other edits to that document are refused while it runs, but
  `doc_export` writes the pre-job pixels with no warning: poll `jobs_list` to `done` first. `jobs_cancel` without
  `job` cancels every job.
- **Writing:** `doc_export` does not create folders (NotFound) and overwrites silently. `doc_export_layers {"dir":"sub"}`
  creates the folder, refuses the root itself and existing files.
- **Preview:** `max_side` up to 2048; documents over 67,108,864 px are refused. Linear and Adobe RGB documents
  preview as raw values; run `edit.convertToProfile {"profile":"srgb"}` first.
- **Closing:** `doc_close`, `file.close` and `file.closeAll` discard unsaved changes silently. `doc_open` of an
  open file opens a second copy.
- **Notes** have only a positional index; `notes.add` dirties the document. They survive `.pcraft` and PSD.

## Live mode (from the app's docs, not tested on 0.18.0)
`ui_*` and `control_call` need bridge mode: run `photocraft --control <port> --control-token-file F`, then
`photocraft-cli mcp --bridge 127.0.0.1:<port> --control-token-file F`, with the roots set in the app (root flags
with `--bridge` stop the server: measured). Bridge previews are window screenshots. Never close or save the
user's documents.

## Without MCP
Tested: `photocraft-cli convert in.pcraft out.psd`, `info FILE --compact`, `commands --json`. These take no root
flags and reach any file you can, so use them only on paths the user named.
