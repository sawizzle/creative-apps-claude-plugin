---
name: pdfcraft
description: Unofficial third-party skill. Drive PdfCraft (open-source Acrobat-style app) through its MCP server - create PDFs, add text and images, rotate pages, redact, set metadata, render pages and export to Word or PNG. Use when the user wants to build, edit, inspect, redact or convert a PDF with PdfCraft.
---

Server: `pdfcraft` (`pdfcraft-cli mcp --compact`). Tested with pdfcraft-cli 0.17.0 on Windows 11 (the plugin's regression steps; written against 0.16.1).

- `--compact` lists 17 tools (15 core tools plus `tool_search` / `tool_call`); the full set is 182. Tools that are not
  listed (`doc_create`, `page_*` other than `page_render`, `redact_*`, `content_*`, exports) still run: through
  `tool_call {"name","arguments"}` or by calling the name directly. `tool_search {"name":"page_add_text"}` returns a
  tool's input schema.
- Headless only: `mcp` has no live-window flag.

## Tested workflow
1. `tool_call {"name":"doc_create","arguments":{"from":"blank","pages":2}}` makes an unsaved US Letter (612x792 pt)
   document. `from` can also be `"images"` with `paths`, or `"text"` with `text`. It returns `{doc, pages, dirty, path, ...}`.
   `doc_open {"path":...}` opens a file. Pass `doc` to every later call. Ids keep counting up within a session.
2. Edit. Coordinates are points from the top-left of the displayed page.
   - `page_add_text {"doc":1,"page":1,"text":"Title","at":[72,72],"size":36,"bold":true,"color":"#FF0000","width":450}`
   - `page_add_image {"doc":1,"page":1,"path":".../in.png","rect":[72,300,552,570]}`
   - `page_rotate {"doc":1,"pages":[2],"degrees":90}`
   - `doc_set_info {"doc":1,"key":"Title","value":"..."}`
   - `redact_mark {"doc":1,"find":"ALPHA-7731"}`, then `redact_apply {"doc":1}`
   - `edit_undo {"doc":1}` returns `{undone}`.
3. Check the result:
   - `render_preview {"doc":1,"page":1,"max_side":792}` or `page_render {"doc":1,"page":1,"dpi":72}` returns a PNG.
     At 72 dpi, 1 px = 1 pt. Look at it.
   - `text_extract {"doc":1}` returns `{pages:[{page,text}]}`. `text_find {"doc":1,"query":"..."}` returns `{count, matches}`.
   - `doc_info` lists the title, page sizes and rotations, annotations and fonts (a bold title shows as `Helvetica-Bold`).
4. `doc_save {"doc":1,"path":".../out.pdf"}` does a full, atomic rewrite. Saving again in place (no `path`) is an incremental
   update (`"incremental": true`), except right after `redact_apply`: that save is a full rewrite (`"incremental": false`),
   so no older revision in the file keeps the redacted text.
5. Exports. Each one includes unsaved edits.
   - `doc_export_office {"doc":1,"path":".../out.docx"}` writes .docx, .pptx, .html, .rtf or .md, chosen by extension.
     The .docx keeps the text, bold, colour, image and title. .html and .pptx carry the image; .rtf and .md carry none.
   - `doc_export_images {"doc":1,"folder":"...","format":"png","dpi":72,"pages":[1]}` writes `<name>_page_1.png`.
6. Reopen the saved file in a fresh server. Text, the image, the rotation and the title survive. Added text and images
   are still listed by `content_list` and stay editable with `content_update {"doc":1,"page":1,"index":1,"color":"#00A000"}`;
   the change survives an in-place save.

## Traps (measured)
- `doc_save` always writes a PDF, whatever the extension. A `.docx` path gives you a PDF named .docx, so use the
  export tools for other formats.
- Saves and exports overwrite existing files without a warning.
- `page_add_text` needs `at` or `rect`. It only accepts Western European (WinAnsi) characters; Chinese is refused.
- `tool_call` rejects unknown arguments. `command_run` drops them with only a `warnings` entry and runs anyway.
- `redact_mark` alone only draws a thin red outline: the text is still in the file. `redact_apply` removes it, leaving a
  newline in the extracted text. The added text box that held the redacted text is flattened and drops out of
  `content_list`; other added text and images stay listed and editable. `pdfcraft-cli audit` reports marks that were
  never applied (exit 1).
- `doc_close` refuses a document with unsaved changes unless you pass `discard_changes: true`.
- `render_preview` can leave out `doc` only when exactly one document is open.

## File access
- `--automation-read-root DIR` and `--automation-write-root DIR` may each be given once. A second one, a missing folder
  or an unknown option stops the server at startup (exit 1).
- **The write root grants no reading.** With the read root on the inputs only, the server cannot reopen its own
  output ("outside the read root"), so make the read root a folder that contains the write root. A root that is left out
  grants nothing. `--root DIR` is applied on top of the automation roots (both must allow a path), so it cannot add
  access.
- Relative paths resolve against the server's working directory and are then confined.
- Refused:
  - absolute paths outside the roots and `..` that climbs out (`..` that stays inside is fine);
  - junctions that point outside, for reading and writing, also when reached through an 8.3 short name, a trailing
    dot or space, or another letter case;
  - UNC paths (`\\host\share`, `//host/share`, `\\?\UNC\...`), even when they point inside a root, and `\\?\` / `\\.\`
    paths outside the roots (`\\?\GLOBALROOT\...` included; a `\\?\` path inside a root works);
  - device names (`NUL.png`, `CON`, `com1.pdf`, `AUX`).
  The same checks apply inside `tool_call`, `command_run`, every `command_batch` step and the export, attach, combine,
  batch, split, extract, insert-file and add-image tools.
- `file.pdf:stream` fails with OS error 87 but leaves an empty `.file.pdf` (dot-named, not hidden) in the folder.
- Saving or exporting (.docx, .html, text, PNG) over a hard-linked name replaces the link, and the outside file is
  unchanged. A hard link that already exists inside the read root can be read.
- Missing subfolders inside the write root are created on save or export.
- `js_run` runs document JavaScript. `this.saveAs` and `app.openDoc` are not available. Don't run scripts from
  untrusted PDFs.

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from exactly one folder: by default the output folder; if the user set `extra_read_root`, only that folder, so it cannot reopen anything in the output folder (its own saves included) unless the output folder is inside it
(the user can put `write_root` inside `extra_read_root` to keep that); with `read_scope` set to `home`, the whole home folder. With the default, copy a file from elsewhere into the output folder first with your own file tools, so the user sees and approves the copy. It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.
