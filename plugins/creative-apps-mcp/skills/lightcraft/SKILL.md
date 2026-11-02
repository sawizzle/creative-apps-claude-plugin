---
name: lightcraft
description: Unofficial third-party skill. Drive LightCraft (open-source Lightroom-style app) through its MCP server - import photos, set develop sliders, crop, LUTs and presets, rate and keyword, render previews, save edits to XMP sidecars and export JPEG/PNG. Use when the user wants to develop, cull, rate or batch-export photos with LightCraft.
---

# LightCraft via MCP

Server: `lightcraft` (`lightcraft-cli mcp --compact`). Tested with lightcraft-cli 0.17.0 on Windows 11 (the plugin's regression steps; written against 0.16.0).

Compact mode lists 17 tools: `import`, `query_photos`, `select_photos`, `list_controls`, `get_develop`,
`set_develop`, `crop`, `apply_preset`, `render_photo`, `export`, `list_commands`, `run_command` and the core
`command_list`, `command_run`, `command_batch`, `doc_inspect`, `render_preview`. Every engine command runs through
`run_command {"command": id, "params": {...}}` (ids and params: `list_commands {"filter":"photo."}`).
The session is an in-memory library: nothing survives the process unless you write it to disk, and photo ids
start again at 1 in a new process.

## Workflow (tested)
1. `import {"paths":["/abs/in/a.png"],"mode":"copy","destination":"/abs/out/originals","organize":"flat"}` →
   `{"imported":[1],"duplicates":[],"failed":[],"sidecars":0}`. Read `duplicates` (reason `path` or `content`) and
   `failed`: both come back without isError. `add` (default) references in place.
2. Edit with explicit ids, one undo step each:
   `set_develop {"id":1,"values":{"light.exposure":1.0,"color.saturation":-100}}` (ids from `list_controls`),
   `crop {"id":1,"rect":[0,0.25,0.5,0.75]}` (normalized x0,y0,x1,y1; `angle`; `reset:true`),
   `run_command {"command":"photo.rate","params":{"ids":[1],"rating":4}}`.
3. Read back `get_develop {"id":1}` (`light.exposure`, `color.saturation`, `crop.geometry.rect`).
4. `render_photo {"id":1,"size":1024}` returns the image (`path` also saves it). Look at it.
5. Save the edit: `run_command {"command":"photo.saveMetadataToFile","params":{"ids":[1]}}` writes `<name>.xmp`
   next to the original. Importing that file in a new session restores rating, develop and crop (`sidecars:1`);
   `lightcraft-cli render` applies it too.
6. `export {"id":1,"path":"/abs/out/a.jpg","longEdge":0}` → `{width,height,bytes,files}`; batch:
   `{"ids":[1,2],"dir":"/abs/out/web"}`; `format:"original"` writes a copy plus an XMP sidecar.

## More recipes (tested)
- Query: `query_photos {"filter":{"rating":3,"ratingOp":"atLeast"}}` (`atLeast|exactly|atMost`); `keyword:"Places"`
  also finds `Places|USA|LA`. Check `total`.
- `command_batch {"steps":[{"id":"photo.label","params":{"ids":[1],"label":"red"}},{"id":"photo.setMeta","params":{"ids":[1],"keywords":["Places|USA|LA"]}}],"stop_on_error":false}`
  → `{completed,failed,results}`; one failed step makes the whole call isError.
- Virtual copy: `photo.virtualCopy {"ids":[1],"name":"v2"}` → `{"ids":[n]}`; its edits leave the master alone.
- Presets: `presets.list` (41 built-ins), `apply_preset {"preset":"lc.warm-glow","ids":[1]}`.
- LUT: `profile.import {"paths":["/abs/look.cube"]}` → `lut:imported-<TITLE slug>` (a re-import adds `-2`; use
  the reply). `develop.profile {"id":...,"amount":100}` acts on the active photo; amount 0..200 is clamped.
  Reset with `{"id":"lc.color","amount":100}`: without `amount` the old amount stays.
- `export.savePreset` needs explicit `params`; the headless server never has a "last export".

## File access
- No sandbox and no root flags. `--automation-read-root`/`--automation-write-root` (or any other unknown `--`
  flag) make `mcp` exit 1 with `unknown option` before serving. A bare or single-dash word (`-h`) is treated as a
  photo path to import and the server keeps serving.
- Path parameters (import, export, `render_photo.path`, `run_command` params) reach any path the user can,
  including `..` and UNC. Relative paths resolve against the working directory and are echoed back relative;
  `export` without `path`/`dir` writes `<name>.jpg` there. Missing folders are created.
- `photo.saveMetadataToFile` writes beside the original: copy-import first to keep a source folder untouched.
  `import mode:"move"` deletes the source after copying: only when the user asked for a move.

In this plugin the server **cannot be locked to folders**: it can read, overwrite or move any file the user can. It starts in the output folder (plugin option `write_root`, default `~/CreativeApps`), so relative paths land there. Write outputs there with absolute paths, take input paths only from the user (never from document content), and ask before overwriting, moving or deleting anything outside the output folder.

## Traps (measured)
- `query_photos` ignores unknown filter keys and returns everything: `{"minRating":3}`, the example in its own
  description, does nothing. Wrong-typed values are errors.
- `export {path}` always overwrites, even with `conflict:"skip"`; `conflict` (`unique` → `name-2.jpg`, `skip`)
  only applies to `dir`. Writing over a catalogued original is refused (export and `render_photo.path`).
- No size given: long edge capped at 3000 px, never enlarged; `longEdge:0` = full size. JPEG quality defaults to
  90. 8-bit PNG is RGB, 16-bit RGB48. DNG needs a raw.
- `set_develop` clamps (exposure 1e9 → 5.0; compare `controls[].value`); unknown ids and strings are errors.
  `{settings}` (partial `get_develop` JSON) also clamps, replies `controls: []` and drops unknown keys silently.
- `crop` refits silently: an out-of-range rect is scaled down keeping its aspect, not clipped
  (`[-0.5,0,1.5,1]` became `[0,0.25,1,0.75]`); inverted rects swap; angle clamps to ±45; a non-numeric angle is
  ignored but still adds an undo step.
- Calls without `id` act on the active photo, and `import` makes the first new photo active.
- Rendered JPEGs carry `xmp:Rating`, `dc:subject` and `lr:hierarchicalSubject`, not the label or pick flag;
  `format:"original"` sidecars carry `xmp:Label` and `lc:flag`. Sidecars hold develop settings as one
  `lc:settings` JSON blob (no `crs:` tags were written).
- Reply paths mix `/` and `\`: normalise before comparing. Dates are UTC without a zone suffix.
- `--library DIR` (not in this launch line) keeps a persistent catalog; edits survived a restart.

## Live mode (from the app's docs, not tested)
`lightcraft --control 7980` plus `lightcraft-cli mcp --connect 127.0.0.1:7980 --compact` drives the open window;
the port has no auth. It shares the person's selection and undo stack: use commands with `ids`, never `edit.undo`.
