---
name: effectcraft
description: Unofficial third-party skill. Drive EffectCraft (open-source After Effects-style app) through its MCP server - comps, solid/shape/text/footage layers, effects, keyframes, expressions, frame checks, H.264 renders, .ecproj save and reopen. Use when the user wants motion graphics, titles or VFX comps built or rendered in EffectCraft.
---

Server: `effectcraft` (`effectcraft-cli mcp`). Tested with effectcraft-cli 0.20.0 on Windows 11 (the plugin's regression steps; written against 0.19.0).

Every edit is an engine command: `command_run {"id","params"}` (alias `execute_command {"command","params"}`).
`command_list {"filter":"layer.new","compact":true}` and `describe_command {"command":"comp.new"}` show ids and
params (742 commands, 308 effects in 0.19.0); unknown param keys are rejected. Times are seconds. A layer is its id,
`"#n"` (from the top) or its name. Unknown CLI options are rejected (exit 2).

## Tested workflow
1. `open_project {"new":true}` (or `{"path":"/abs/x.ecproj"}`, or `{"demo":true}`).
2. `command_run {"id":"comp.new","params":{"name":"Main","width":640,"height":360,"frameRate":24,"duration":2,"background":"#000000"}}` → `{"comp":1}`
3. Layers. Each returns `{"layer":id}`, and new layers go on top:
   - `layer.newSolid {"color":"#1e90ff","name":"BG"}`
   - `layer.newShape {"kind":"rect","size":[160,160],"fill":"#ff0000","position":[160,180],"name":"Box"}`
   - `layer.newText {"text":"Title","size":48,"fill":"#ffffff","position":[320,330],"name":"Title"}`
   - `file.import {"paths":["/abs/card.png"],"addToComp":true}` returns item ids, not the layer id. Read the layer
     from `get_comp`, where it is named after the file.
4. Edit:
   - `add_effect {"layer":id,"effect":"Fill","values":{"color":"#00ff00"}}` → `path` `effects/#1` + each param path
   - `add_keyframe {"layer":id,"path":"transform/position","keys":[{"time":0,"value":[160,180]},{"time":1.5,"value":[480,180]}],"interpolation":"linear"}`
   - `set_property {"layer":id,"path":"transform/scale","value":[50,50,100]}` or `{..., "expression":"time*45"}`
   - `get_property {"layer","path","time"}` (comp time); `get_layer {"layer","flat":true}` lists every path.
5. Look: `render_preview {"time":0,"max_side":640}` (inline PNG), or
   `render_frame {"time":1,"max_side":0,"path":"/abs/f.png","inline":false}`. Open the image.
6. Render: `command_run renderQueue.add {"comp":"Main","format":"h264","output":"/abs/out.mp4"}`, then
   `renderQueue.render {"wait":true}` → `"failed":0`. Check with ffprobe. Only h264 was tested; the app also lists
   hevc, av1, prores, uncompressed, webm, png, jpeg, tiff, exr, tga, gif, wav and aiff.
7. `save_project {"path":"/abs/out.ecproj"}`. Reopened in a new process, the layers, effect, keys, expression and
   text all came back.

## Batches and undo
- `batch {"steps":[{"command","params"}]}` is ONE undo step, and later steps can use `"$1.layer"`.
- `command_batch {"steps":[{"id","params"}]}` gives one undo step per command. If a step fails it returns
  isError true, and the JSON body lists the results.
- `undo {"steps":1}`, `history`. Layer ids are reused after an undo, so re-read them.

## Traps (measured)
- After you set an expression, `value` still holds the value from before the expression. Read `evaluated`.
  A broken expression returns isError false plus `expressionError`.
- Keyframe `time` is layer time. On an offset layer, pass `"timeBase":"comp"`. Keys report `compTime` and
  `layerTime`, and warn when they fall outside the layer's range.
- Scale `[50,50]` stores z = 0. Pass all three values.
- `file.import` returns isError false and lists per-file failures in `errors[]`.
- `run_script` errors return isError false plus `{"ok":false,"error":{message,line,column}}`.
- `effect.apply` documents `layers` (an array) but also accepts `layer`; with neither, it applies to the selected
  layer (the newest one). `add_effect` takes `layer`.
- Parent folders are not created (os error 3).
- H.264 is 4:2:0, so flat colours can shift by 1-3 levels.

## File access
Measured with `--automation-read-root IN --automation-write-root OUT`. Paths are checked against the roots.
- Paths you pass must be absolute and inside a root. Any `..` is refused, even when the path stays inside the root.
  A relative path is refused with "give an absolute path".
- The write root is also readable, so you can reopen and import your own outputs without an extra read root.
  Commands cannot write into a read root.
- A junction is followed, and refused if it leads out of the roots. A UNC path to a share that does not exist is
  refused ("can't be resolved"); real shares were not tested. `file:stream` writes fail.
- Both flags can be repeated. The root folders must exist, or the server exits at startup.
- Confined, scripting is off: `run_script`, `script_ui`, `script.run`, `file.runScript`, `file.executeFile`,
  `file.installScript`, `file.installScriptUIPanel`, `file.uninstallScript` and the startup, shutdown and scheduled
  script commands are refused, and `prefs.set scripting.*` cannot change that. Expressions have no `File`, `$`,
  `system`, `require` or `fetch`.
- Paths in commands are checked too: `file.saveAs` / `saveCopy`, `renderQueue.add` outputs, exports, imports
  (including `file.importProject`), the folder you give Collect Files, and settings that hold folders.
- Footage stored in a project outside the roots is treated as missing from 0.20.0: the project opens, `footage.missing`
  lists it, it renders as nothing, `file.importProject` reports it in `missingMedia` and `file.collectFiles` skips it
  (0.19.0 loaded and rendered it).
- While confined, do not use `file.watchFolder`, the Media Browser commands (`mediaBrowser.*`) or
  `renderQueue.setOutput`: import with `file.import` and set outputs with `renderQueue.add`.
  Some of these commands reach outside the roots (being reported privately to the developers; details withheld until fixed).
- `OUT/CON` and `OUT/NUL.png` are written as ordinary files. Deleting a file named CON needs a `\\?\` path, so avoid
  such names.
- With `--autosave`, the server creates its auto-save folder in the user profile, outside the roots, even when
  confined.
- Unconfined (no root flags), scripts can read only files in the project's folder and cannot write any file until
  `prefs.set {"key":"scripting.allowScriptsWriteFiles","value":true}`; after that a script read and wrote files
  elsewhere. `system.callSystem` is refused either way.

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from the output folder plus, by default, the user's Desktop, Documents, Downloads, Pictures, Videos and Music folders (option `read_scope`: `write-root-only` drops those, `home` opens the whole home folder; `extra_read_root` adds one more). It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.

Rendering: headless renders on the CPU; with `--gpu` (root flags too) `get_project` reports `renderer.active` "gpu"
and frames render correctly. Live mode (from the app's docs, not tested): `--bridge PORT` drives a window started with
`effectcraft --control PORT`. The server accepted `--bridge` with the root flags; whether the roots then confine the
live app was not tested.
