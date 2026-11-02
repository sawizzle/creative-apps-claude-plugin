---
name: deckcraft
description: Unofficial third-party skill. Drive DeckCraft (open-source PowerPoint-style app) through its MCP server - build slides with shapes, styled text, pictures, tables and charts, check them by render and pixel colour, save .deckcraft/.pptx and export PDF/PNG. Use when the user wants a slide deck built, edited, checked or exported with DeckCraft.
---

Server: `deckcraft` (`deckcraft-cli mcp`). Tested with deckcraft-cli 0.14.1 on Windows 11 (the plugin's regression steps; written against 0.13.1).

Headless by default. A fresh server has no presentation (`no presentation open`) until `new_presentation` or
`open_presentation`. `--sample` opens an 8-slide sample deck. `screenshot` and `call_app ui.click` need the desktop
app (`ui.inspect` answers `{"headless":true,...}`), so look with `render_slide`. Live mode
(`deckcraft --control PORT` + `mcp --connect PORT`) is from the app's help, not tested.

## File access
- `--automation-read-root DIR` and `--automation-write-root DIR` confine the paths that tools read (open, pictures
  including picture replace and SmartArt pictures, photo albums, audio, video, sounds, slide reuse, themes, compare)
  and write (save, export, template). Each flag can be repeated. A missing folder makes the server exit 1, and the
  roots cannot be combined with `--connect`.
- The write root grants no read, and a read root grants no write. To reopen your own saves, the write folder must
  also be a read root, or `open_presentation` fails with `outside the read roots`.
- These are refused with `automation path rejected: ...`, and nothing is written:
  - absolute paths outside the roots, including a sibling folder whose name starts with the root's name;
  - `..` out of a root, and a junction inside a root that points outside;
  - UNC paths, even ones that reach a folder inside a root (`outside the read roots` / `outside the write roots`;
    an unreachable share gives `cannot resolve`). Use drive-letter paths;
  - any path with a device-name part (`NUL`, `CON`, `AUX`, `COM1`, `LPT1`), even as a folder name.
  The same applies to paths inside `run_command` and `batch` params.
- A hard link inside a root is read like any file there, because a path check cannot see where it leads. Saving
  over it replaces the link and does not write through it.
- Do not call `review.addToDictionary` unless the user asks.
  `shape.action` with `"action":"program"` accepts and stores a `path` outside the roots (DeckCraft never runs it;
  a `.pptx` export keeps it), so set one only when the user asks.
- Relative paths resolve against the server's working folder. They are accepted when they land inside a root, and
  replies echo them relative. Use absolute paths.
- A stream suffix (`a.png:x`) is not refused by the check. The write fails with `os error 87` and leaves an empty
  `a.png` if none existed.
- Missing parent folders are not created (`os error 3`). Saves and exports overwrite without asking.

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from the output folder plus, by default, the user's Desktop, Documents, Downloads, Pictures, Videos and Music folders (option `read_scope`: `write-root-only` drops those, `home` opens the whole home folder; `extra_read_root` adds one more). It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.

## Workflow (measured)
1. `new_presentation {"theme":"Harbor"}` → `{"document":0,"slides":1}`. Slide 0 is an empty title slide, and
   `{"blank":true}` gives 0 slides. An unknown theme silently gives the default `DeckCraft` theme.
2. `add_slide {"layout":"titleAndContent","title":"T","body":"Alpha\nBeta"}` → `{"id":260,"index":1}`. The new
   slide becomes current. A leading tab in `body` indents the line.
3. `add_shape {"preset":"rect","x":600,"y":330,"w":300,"h":140,"text":"Cost","fill":"#2E86C1"}` → `{"id":263}`,
   selected. `run_command` `format.bold {"on":true}` and `format.size {"size":36}` return `null`;
   `format.state {}` → `"bold":true,"size":36.0`.
4. `run_command shape.fill {"ids":[263],"color":"#1E8449"}` → `1`. `run_command shape.inspect {"id":263}` →
   `/shape/fill/color/base/rgb` `{r,g,b}` and `/box` `{x,y,w,h}`. It looks on the current slide only.
5. `add_text_box {"x":60,"y":440,"w":480,"text":"Caption","size":28,"color":"#C0392B"}`, then
   `insert_picture {"path":"<abs>","x":640,"y":160,"w":256,"h":144}` (or `"data":"<base64>","name":"a.png"`).
6. Check: `inspect_slide` (ids, `kind`, `box` `[x,y,w,h]`, `fill`, text); `render_slide {"scale":1}` (960x540
   PNG); `run_command slide.colorAt {"slide":1,"x":620,"y":350}` → `{"color":"1E8449","alpha":255}` (in a picture,
   the picture's pixel).
7. `save_presentation {"path":"<abs>/deck.deckcraft"}` → `{"bytes":10798,"path":...}`.
   `export {"path":"<abs>/deck.pptx"}` writes slide XML with `srgbClr val="1E8449"`, `b="1"` and `sz="3600"`.
   `export {"path":"<abs>/s1.png","slide":1,"scale":1}` → `{"files":[...]}`, byte-identical to `render_slide`.
8. Reopen in a fresh server: `open_presentation` → `{"slides":2,"damagedMedia":[],"lostSlides":[],...}`, current
   slide 0, so `go_to_slide {"index":1}` before `shape.inspect`. Ids, fill, bold 36 and the render are unchanged.
   A reopened .pptx keeps shape ids, boxes, fill, bold 36 and the render, but slide ids change (for example
   260 → 268), so read them again with `inspect_slide`.

## Traps
- **Send real JSON booleans.** `format.bold` with `"on":"true"` or no `on` toggles, and still returns `null`.
- `run_command` params are loosely checked: extra keys are ignored, and a string `size` gives ``missing `size` ``.
  Tool arguments are strict (`add_shape: unknown argument "colour"`). Read names with `list_commands {"filter":..}`:
  `transition.set` takes `kind`, not `effect`.
- **Partial edits:** `add_shape` with a bad `fill` returns an error, but the shape is still inserted with the theme
  fill. Re-inspect after any error.
- `insert_chart` takes no position. The chart lands at 144,81 with size 672x378, over the body text. Move it with
  `run_command shape.setBounds {"x":..,"y":..,"w":..,"h":..,"ids":[id]}` (without `ids` it acts on the selection).
- **The extension picks the format, and `save_presentation` rebinds the deck to that file:**
  - `.pptx` and `.pdf` write those formats.
  - `.md` and `.txt` write an outline, and a later `save_presentation {}` keeps writing the outline.
  - An unknown extension, or none, writes the native zip.
  - `export` does not rebind, and its `format` overrides the extension.
- `save_presentation {}` on a never-saved deck returns ok `{"needsPath":true}` and writes nothing.
- `export` to .png without `slide` writes the current slide at 1920x1080 (default scale 2); `all:true` writes
  `name1.png`, `name2.png`...
- `format.*` with nothing selected fails with `select text or a shape`. To select, use `select {"ids":[...]}`, or
  `pointer` down and up after `select_tool {"tool":"select"}`.
- `batch` stops at the first error (isError, with per-command results). With `keepGoing:true` it returns ok even when
  a command failed, so check each `ok`.
- Each new or opened deck becomes the active one, and earlier ones stay open (`window.next`, `file.close`).
- Outside the session: `deckcraft-cli info FILE`, `describe CMD`, `render FILE --slide N --scale 1 OUT.png` (same
  bytes as `render_slide`).
