---
name: wordcraft
description: Unofficial third-party skill. Drive WordCraft (open-source Microsoft Word-style app) through its MCP server - write and style .docx documents, tables with formulas, shapes and pictures, render pages, export PDF/ODT/RTF/HTML/Markdown/PNG. Use when the user wants a Word document created, edited, checked or converted with WordCraft.
---

Server: `wordcraft` (`wordcraft-cli mcp`). Tested with wordcraft-cli 0.14.0 on Windows 11 (the plugin's regression steps; written against 0.13.2).

- **Modes:** headless by default (no window, no token). There is no `--headless` flag; unknown flags exit 1.
  Live app, from the app's error text (not tested): `wordcraft --control 7981`, then
  `wordcraft-cli mcp --connect 127.0.0.1:7981`. With no app listening, each call fails after ~1.6 s
  (`... is not reachable ...; will retry on each call`). `--connect` with `--author` or a root flag exits 1.
  Headless, `screenshot`, `ui_inspect`, `click` and `key` error (`needs the desktop app`).
- **Ids:** a session starts with a blank `Document1` (id 1), so `new_document` returns id 2. Opening a file while
  Document1 is untouched replaces it. Document tools take `doc` (an id). `off` in positions counts UTF-8 bytes.
- `--author NAME` sets `lastModifiedBy` in saved files (default `WordCraft User`).

## File access
- `--automation-read-root DIR` / `--automation-write-root DIR` each work **once** (a second one exits 1:
  `given twice`), and the folder must exist and be a folder (else exit 1, `cannot open the automation ... root`).
  A root left out grants none of its access: reads (or writes) then fail with `automation filesystem access is not
  granted: read (write) authority is absent`.
- The write root is not readable and the read root is not writable. **To reopen your own output, the one read root
  must contain the write root** (one folder for both, with the inputs inside it, or a common parent). With read and
  write roots as sibling folders, saving works but `open_document` on the output is refused.
- Refused with `automation path rejected`: paths outside the roots, a `..` that leaves a root (`out/sub/../x.docx` is
  fine), junctions inside a root that point out, UNC paths (also `\\localhost\C$\...` to a file inside a root),
  device names (`NUL.png`, `CON`, `COM1.pdf`, `sub/lpt1.docx`), `a:x.docx`, and the same paths inside
  `execute`/`batch` params (`file.exportPdf`, `file.saveAs`, `insert.textFromFile`, `file.listTemplates {dir}`,
  `styles.copyFrom`, `mailings.finish`, ...).
- Relative paths resolve against the server's working directory, then the roots apply. `\\?\C:\...` (backslashes
  only) and `\\.\C:\...` or `\\.\C:/...` inside a root work; matching ignores case. With no roots, any path works.
- `tools.attachTemplate {path}` records any path without reading it. `INCLUDETEXT`/`INCLUDEPICTURE` fields are never
  evaluated (with or without roots), and externally linked pictures are dropped when a file is opened.

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from exactly one folder: by default the output folder; if the user set `extra_read_root`, only that folder, so it cannot reopen anything in the output folder (its own saves included) unless the output folder is inside it
(the user can put `write_root` inside `extra_read_root` to keep that); with `read_scope` set to `home`, the whole home folder. With the default, copy a file from elsewhere into the output folder first with your own file tools, so the user sees and approves the copy. It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.

## Tested workflow
1. `new_document {"template":"blank"}` → `{id:2,...}`; `execute {"command":"layout.size","params":{"name":"Letter"}}`
   → `pageW` 612, `pageH` 792. Pin the size: MCP documents were Letter under `WORDCRAFT_REGION=en-GB`, while
   `wordcraft-cli run` gave A4.
2. `type_text {"text":"Title\nIntro.","paragraphs":true}`. Without `paragraphs`, `\n` is a line break.
3. `select_text {"text":"Title"}`, then `batch {"commands":[{"command":"para.style","params":{"style":"Heading 1"}},
   {"command":"format.bold","params":{"value":true}},{"command":"format.color","params":{"color":"C00000"}}]}`
   (each item reports `ok`). `format.bold` without `value` toggles.
4. `batch` `caret.docEnd`, `text.newParagraph`, `insert.table {"rows":4,"cols":2}` → `result.table [2]`, caret in
   cell 1. Fill with `text.insert` + `text.tab` (7 tabs for 8 cells; a tab in the last cell adds a row).
5. `execute table.formula {"formula":"=SUM(ABOVE)"}` → `{"result":"42"}`, saved as a real field.
6. `insert.shape {"kind":"rectangle","width":144,"height":72,"fill":"4472C4"}` is inline and **stays selected: run
   `caret.docEnd` before typing or `text.newParagraph`, or the shape is replaced.** `insert.picture
   {"path":..,"width":200}` keeps the aspect ratio (200x112.5 for 16:9) and selects nothing.
7. `get_text`; `render_page {"page":1,"scale":1}` → 612x792 PNG. `render_page` draws spelling squiggles; a saved
   `.png`, `file.exportPng` and `wordcraft-cli render` do not.
8. `save_document {"path":"C:/abs/out.docx"}`, then `.pdf`. After a restart, `open_document` → `alreadyOpen:false,
   words:14`; `execute document.paragraph {"path":[0]}` → style `Heading1`, bold, `Rgb [192,0,0]`; `[2,3,1,0]`
   (`[table,row,cell,block]`) → field `result` `42`; `[3]` → shape 144x72, `fill [68,114,196]`.

## Traps
- **Saving:** the extension picks the format (docx, dotx, pdf, odt, rtf, html, md, tex, txt, json, xml = Word XML
  Flat OPC, png); `.doc` and `.xyz` → `can't save as`. Saving as docx, dotx, odt, rtf, json or xml binds the
  document to that file (a later `save_document {}` writes there); pdf, html, md, tex, txt and png exports keep the
  path. `.png` is page 1 at 2 px/pt; use `execute file.exportPng {"path","page","scale"}` for others. Missing
  folder → `os error 3`; overwrites are silent.
- **Wrong keys pass silently:** `type_text {"txt":..}` types nothing and deletes the selection;
  `save_document {"file":..}` saves in place (untitled: `{"saved":false}`, no error); `insert.shape
  {"colour","w"}` gives a default 108x72 shape, fill `[21,96,130]`.
- **Clear errors:** unknown or missing `command`, unknown style, colour not `RRGGBB`/`auto` (`#C00000` works), bad
  shape `kind` (lists valid ones), `layout.size {"paper":..}` (use `name`), `select_text` empty or not found,
  `render_page {"page":9}` → `no page 9` (`page:0` silently renders page 1).
- `open_document` on an open path (any slash or case) returns `alreadyOpen:true` without reading the disk.
  `file.closeDocument` with unsaved changes errors unless `"force":true`.
- Page fields (NUMPAGES) render ("Pages: 1") but stay empty in `get_text` and the saved file, even after
  `references.updateFields {"all":true}` or `wordcraft-cli convert --update-fields`.
- `list_commands` without `query` returns 163 KB (648 commands); filter, e.g. `{"query":"table"}` → 59.
  Check files from a separate process with `wordcraft-cli text|info|inspect <file>`; `wordcraft-cli render <file>
  <out.png>` draws at 2 px/pt unless you pass `--scale 1`.
