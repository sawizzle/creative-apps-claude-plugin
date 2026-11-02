---
name: filmcraft
description: Unofficial third-party skill. Drive FilmCraft (open-source Premiere Pro-style app) through its MCP server - import media, cut sequences, apply effects and graphics, render frames, save .fcproj projects and export H.264/ProRes/WAV or FCPXML/EDL/OTIO/FCP7 XML/AAF. Use when the user wants to edit, inspect or export video in FilmCraft.
---

Server: `filmcraft` (`filmcraft-cli mcp`). Tested with filmcraft-cli 0.16.0 on Windows 11 (the plugin's regression steps; written against 0.15.0).

Runs headless (no window, no token). Every edit is an engine command: `command_list {"filter":"razor"}` (or
`filmcraft-cli describe <id>`) shows its params, `command_run {"id":..,"params":{..}}` runs one, `command_batch
{"steps":[{"id":..,"params":{..}}]}` runs several. Time is in ticks (254016000000 per second); most commands also
take `seconds`, `frame` or `timecode` (not `render_frame` or `file.exportFrame`: see 5 and 7).

## Workflow (0.15.0; the plugin's regression steps run every call below and check its result)
1. `media_import {"paths":["C:/abs/clip.mp4"]}` → `{"errors":[],"items":[1]}`. A missing file is an isError.
2. `command_run file.newSequenceFromClip {"items":[1]}` → `{"sequence":4,"clips":[6,7]}` (video, linked audio).
   Take ids from replies; never hard-code them. A 1280x720 still gives one clip and a 1280x720 29.97 fps,
   150-frame sequence.
3. Edit:
   - `timeline.razor {"seconds":1.0}` → `{"cuts":2}` (video and linked audio). It returns no ids: read the new
     clip from `sequence_inspect` (`video[0].items[1].clip`).
   - `effects.apply {"clips":[id],"effect":"invert"}` → `{"applied":[{"clip":id,"effect":"invert","index":3}]}` (from 0.16.0 every video clip lists the built-in `motion`, `opacity` and `time_remap` first, so applied effects start at index 3; 0.15.0 started at 0).
     Effects start at their defaults (Gaussian Blur blurriness 0 changes nothing), so then
     `effects.setParam {"clip":id,"effect":"gaussian_blur","param":"blurriness","value":40}`. `effect` is the id;
     the label (`"Gaussian Blur"`) gives "no such effect on clip".
   - `graphics.newRectangle {"position":[320,180],"size":[200,100],"time":0,"seconds":2}` → `{"clip":12,"layer":0}`
     on a new video track. `time` is the start, `seconds` the duration; the default fill is red (#D93340). Colour it
     with `graphics.set {"clip":12,"layer":0,"props":{"fill_color":"#ff8000"}}` (returns `null`).
   - `markers.add {"seconds":1.25,"name":"Note"}` → `{"marker":id}`.
4. Read back: `sequence_inspect` (`startFrame`/`endFrame`, effects per clip, markers, `in`/`out`),
   `graphics.list {"clip":id}` (kind, position, bounds; no colours: check fills by pixel), `history.list`
   (`undo`/`redo` step names). `ok` is not proof.
5. Look: `render_frame {"seconds":1.5}` returns a PNG of the program output. It takes only `seconds` and
   `max_side` (`frame` or `time` is a protocol error). The default `max_side` is 960, so a 640x360 sequence
   renders at 640x360 but a 1280x720 one at 960x540; `max_side:0` gives full size. `render_preview` gives the
   same image. Open the image.
6. Save: `command_run file.saveAs {"path":"C:/abs/edit.fcproj"}` (JSON text). Reopen: `file.open {"path":..}` →
   `{"missingMedia":0,..}`. `file.saveCopy {"path":..}` writes a copy and leaves `path`, `dirty` and `revision`
   unchanged.
7. Export: `file.exportMedia {"path":"C:/abs/out.mp4","format":"h264","wait":true}` → `result.frames` and
   `result.path` (H.264 plus AAC 48 kHz stereo). Range:
   - With no range keys it exports **In/Out when they are marked** (`markers.markIn`/`markOut`; `sequence_inspect`
     `in`/`out`), out-inclusive: In 0.5 s, Out 1.0 s gave 13 of 48 frames. Pass `"range":"entire"` for the whole
     sequence, and compare `result.frames` with `sequence_inspect.durationFrames`.
   - Sub-range: `"startSeconds":1.0,"endSeconds":2.0` (end exclusive: 24 frames at 24 fps; `endSeconds` alone
     errors).
   - `"format":"wav"` writes PCM 48 kHz stereo; for audio formats `result.frames` counts samples (96000 for 2 s).
   - One still: `file.exportFrame {"path":..,"format":"png","time":ticks}` → PNG at sequence size. It takes only
     `time` in ticks: `seconds` or `frame` are ignored and it exports time 0 (check the reply's `time`). It is RGBA:
     areas the picture does not cover (such as blurred edges) are transparent, while `render_frame` is opaque.
8. Interchange: `file.exportFcpxml`, `file.exportFcp7Xml`, `file.exportOtio`, `file.exportAaf`, `file.exportEdl`,
   each `{"path":..}`, all **lossy** (below). Re-import with `file.import {"paths":[..]}` →
   `{"sequences":[id],"documents":[{"format":"FCPXML","offlineMedia":[],..}]}`; the imported sequence becomes the
   active one.

## Traps (measured on 0.15.0)
- Misspelled or wrong-typed optional params are ignored: `timeline.razor {"secs":1.5}` and `{"seconds":"1.5"}` both
  return ok with `{"cuts":0}`, and still add a "Razor" undo step and bump `revision`. Check counts in replies.
  Required params do error.
- Interchange is lossy. Read the reply's `report` array after every interchange export. Graphic clips are left out
  of FCPXML, become media-less clip items in FCP7 XML, come back offline from OTIO and become a gap in AAF. EDL keeps
  only one video track and no effects. Markers survive FCPXML.
- Importing an AAF writes `<aaf-name> Media/<clip>.wav` next to the AAF (the export writes only the .aaf).
- Effect names resolve per clip type: `"Invert"` on an audio clip applies the audio Invert (`invert_a`).
- Headless has no selection. Without ids, `effects.apply` fails with "select clips first": pass `clips`/`clip`/`items`.
  An unknown clip id reads "`Invert` does not apply to the selected clips".
- Ids freed by undo are reused by the next edit (an undone marker's id goes to the next marker). Re-read ids after
  any undo.
- On a 29.97 fps sequence `seconds` is not frame-exact: `markers.add {"seconds":0.5}` keeps 0.5 s, while
  `playhead.set {"seconds":0.5}` snaps to frame 14. Use `frame` for frame-exact work.
- `markers.clearCurrent` removes **every** marker on the playhead frame (there is no delete by id), and adds an
  undo step even when nothing is removed.
- `timeline.place {"item":1,"track":"new","seconds":1}` puts the linked audio on A1 and overwrites the clip there.
  Add `"audioTrack":"new"`.
- `command_batch` stops at the first failure with isError `{"completed":n,"failed":1,..}`; the completed steps stay
  applied (n undos restore). With `"stop_on_error":false` it runs every step and still returns isError.
- `project_inspect.revision` moves on edit, undo and redo, not on playhead moves.
- `file.open` discards unsaved changes without asking: check `project_inspect.dirty` first.
- `wait:false`, then ending the session: no file is written. Use `wait:true` or poll `jobs.list`.
- A wrong extension gets the container's appended (`x.mov` as h264 → `x.mov.mp4`).
- Exports and saves overwrite silently.
- `sequence_inspect` costs about 2.5 KB per clip.

## File access
- `filmcraft-cli mcp` has no sandbox flags. `--automation-read-root`, `--automation-write-root` or any unknown
  option makes it exit 2 (`unknown mcp option`) before answering initialize. Never pass root flags to it.
- It reads and writes any path the user can: absolute, `..`, through junctions, `\\?\` and UNC paths.
- Relative paths resolve against the server's working directory. A relative import is stored as typed in the
  .fcproj and re-resolved against the project's folder on reopen (`missingMedia` goes up), so import with absolute
  paths.
- `file.exportMedia` creates missing folders; saves and interchange exports fail (os error 3).
- On Windows never put `:` in a file name. `file.exportMedia` then writes a hidden NTFS stream (a 0-byte visible
  file) and returns ok; saves and other exports fail (os error 87) and leave a 0-byte `.<name>` file.
- `clip.updateMetadata {"items":[id]}` writes `<media-stem>.xmp` next to the source media: run it only on copies.
- `filmcraft-cli --project p.fcproj mcp` opens a project at start; a path after `mcp` is ignored.

In this plugin the server **cannot be locked to folders**: it can read, overwrite or move any file the user can. It starts in the output folder (plugin option `write_root`, default `~/CreativeApps`), so relative paths land there. Write outputs there with absolute paths, take input paths only from the user (never from document content), and ask before overwriting, moving or deleting anything outside the output folder.

## Live app (bridge)
- `filmcraft-cli mcp --bridge 127.0.0.1:<port>` drives the app started with `filmcraft --control <port>`; both
  sides need the same 64-hex-character `FILMCRAFT_CONTROL_TOKEN`. Only `ui_*` tools need the live app.
- Measured on 0.15.0 without the app: a non-loopback `--bridge` exits 2; with nothing listening each call fails
  after about 2 s with `bridge: cannot connect`; headless `ui_*` tools return isError. Headless, `file.save`,
  `saveAs`, `saveCopy`, `open` and `import` without a path return an invalid-parameters error.
- From the 0.5.0 live session, not re-checked on 0.15.0:
  - Over the bridge those path-less `file.*` calls open a native dialog that freezes every control connection;
    always pass a path.
  - Re-read `project_inspect.revision` right before writing beside a person; stop if it moved.
  - Bridge `render_frame` returns a Program-monitor screenshot with UI chrome and can move the user's playhead.
    For clean frames, `file.saveCopy` and render the copy headless.
  - `app: timeout` (60 s) does not mean the command failed: re-read `history.list` before retrying.
  - Prefix agent markers (for example `AGENT: `), keep them off frames that hold a person's markers
    (`markers.clearCurrent` would take both), and never use `markers.clearAll`.
