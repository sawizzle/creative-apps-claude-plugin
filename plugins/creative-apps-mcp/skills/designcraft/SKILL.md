---
name: designcraft
description: Unofficial third-party skill. Drive DesignCraft (open-source InDesign-style app) through its MCP server - lay out pages with text frames, shapes, swatches and placed images, render pages, save .designcraft and export PDF/X-4, PNG/JPEG, IDML, HTML, EPUB or PPTX. Use when the user wants a flyer, poster, brochure or page layout made with DesignCraft.
---

# DesignCraft via MCP

Server: `designcraft` (`designcraft-cli mcp`). Tested with designcraft-cli 0.16.0 on Windows 11 (the plugin's regression steps; written against 0.15.2).

The server runs a headless engine with no window. Coordinates are points in spread space with y pointing down. A single-page spread's page starts at (0,0), and a Letter page is 612x792.

## File access
- Every path that a call reads or writes is checked against the roots. This includes paths inside `execute`, `batch` and `script.run` params. `--automation-read-root` and `--automation-write-root` can each be given more than once.
- **The write root does not grant reading.** To reopen your own saves or place your own exports, the write folder must also be a read root. With a write root only, every read fails with "read authority is absent".
- Root folders must exist, or the server exits at start. The root flags cannot be combined with `--connect`.
- These are refused: absolute paths outside the roots (including a sibling `<root>_x` folder), `..` that leaves a root, a junction inside a root that points outside, UNC paths (even ones that point into a root), and device names (`NUL.png`, `CON`, `AUX.png`). An image link inside a document that points outside the roots is not followed: `links.list` shows `missing` and the embedded copy is drawn.
- Relative paths resolve against the server's working folder and are then checked. The reply repeats the path as you gave it, so use absolute paths with forward slashes. Exports do not create missing folders (`file.package` creates its own `dir`).
- A stream suffix such as `a.png:x` fails with OS error 87 but leaves an empty `.a.png` behind.

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from the output folder plus, by default, the user's Desktop, Documents, Downloads, Pictures, Videos and Music folders (option `read_scope`: `write-root-only` drops those, `home` opens the whole home folder; `extra_read_root` adds one more). It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.

## Workflow
1. `new_document {"width":612,"height":792}` returns `{index}`. It also takes `preset` ("A4"), `pages`, `margins`, `columns`, `gutter`, `facingPages`, `bleed` and `intent`. `{"sample":true}` opens the sample magazine.
2. `execute {"command":"frame.create","params":{"rect":[54,54,558,200],"content":"text","text":"Headline"}}` returns `{id, story}`. `rect` is `[x0,y0,x1,y1]`. For a shape, pass `"shape":"rectangle"` (or `"ellipse"`/`"polygon"`) with `"content":"unassigned"` or `"graphic"`.
3. `set_story_text {"frame":8,"text":"Line one\nLine two"}` replaces the whole text (`\n` starts a new paragraph). The new text takes the formatting of the story's first character and paragraph, so mixed formatting is flattened: format after setting the text. It returns paragraphs, lines and overset (`null` when the text fits). `get_story {"frame":8}` reads the text.
4. To format characters, run `execute selection.set {"ids":[8]}` then `execute type.char {"attrs":{"size":36}}` (the flat `{"size":36}` also works). Read the result back with `execute type.selectionAttrs {}` (`chars.size`, `chars.fontFamily`). The default is Source Serif 4 Regular 12 pt.
5. For colour, run `execute swatch.create {"name":"Brand","color":{"c":0,"m":100,"y":100,"k":0}}`, then `execute object.fill {"swatch":"Brand","ids":[10]}`. It returns `{changed}`.
6. `place_image {"path":"<abs>/img.png","x":54,"y":540,"width":256}` returns `{asset, id}`, and the height follows the aspect ratio. Pass `"frame":id` to fill an existing graphic frame. PNG and JPEG were tested.
7. Check the layout:
   - `inspect_document` lists spreads[].items (id, kind, bounds, fill), stories (overset), swatches and the selection.
   - `render_page {"page":0,"scale":1,"path":"<abs>/p.png"}` returns a PNG at 72 ppi. Look at it.
8. Export:
   - `export_png {"path":"<abs>/p1.png","page":0}` uses scale 2 by default. A `.jpg` path writes a JPEG.
   - `execute file.exportPdf {"path":"<abs>/o.pdf","standard":"x4"}` returns `{pages, warnings}`. `designcraft-cli validate-pdf o.pdf` checks PDF/X-4.
   - `file.exportIdml`, `file.exportHtml`, `file.exportEpub`, `file.exportPptx` and `file.exportText` were also tested.
9. `save_document {"path":"<abs>/out.designcraft"}` writes a zip with document.json and the embedded images. `open_document` reopens it, and item ids stay the same.

## Commands
- `list_commands {"filter":"swatch"}` returns `{commands:[{id,label,params,enabled}],count}`. Always pass a filter: all 545 commands come to more than 100 KB. `designcraft-cli describe <id>` prints one command.
- `batch {"commands":[...]}` runs commands in order and stops at the first error. Earlier steps stay applied. `"$0.id"` passes a value from step 0's result.
- The resources `designcraft://document` and `designcraft://commands` hold the same data.
- An unknown command id is an error. Under `app.`, `view.` or `window.` the error says it "is a UI command; it needs the desktop app", the same text that real UI-only commands get. Check the spelling before starting the app.

## Traps
- Many commands return `null` on success. Verify with `inspect_document`, `type.selectionAttrs` or `render_page`.
- Unknown object ids do not cause errors. `object.fill {"ids":[999]}` returns `{"changed":1}` and changes nothing. `selection.set` with an unknown id returns null and empties the selection. Use the ids that the calls return.
- `type.char` at a caret leaves the existing text unchanged and applies only to text typed next with `type_text`. A caret is where `frame.create` with text leaves you. Select the frame, or a range with `text.select {story, anchor, focus}` (UTF-8 byte offsets), first. With nothing selected, `type.char` errors. Unknown attributes are rejected, and the error lists the valid ones.
- PDF/X-4 with an RGB swatch (`"#ff0000"`) exports with a warning and fails `validate-pdf`. Use CMYK swatches. Renders are colour-managed, so C0 M100 Y100 K0 draws as about rgb(227,4,18).
- `file.exportText` fails with only a `frame` param. Run `selection.set` on the frame first.
- PPTX export splits words into separate runs. Pass `"lineBreaks":"reflow"` to keep the text whole.
- Saved `.designcraft` and IDML files record each placed image's full source path. Before sharing, run `execute file.package {"dir":"<abs>/pkg"}`: it writes the document, an IDML and a `Links/` folder, and the packaged links are relative.
- Live app, from the app's help and not tested here: start `designcraft --control <port>`, then run `designcraft-cli mcp --connect <port>` for the window tools (`screenshot`, `click`, `menu_list`, `ui_*`, `dialog_*`). A running app is not confined by the root flags. The GUI's graphics backend can be forced with the `WGPU_BACKEND` environment variable.
