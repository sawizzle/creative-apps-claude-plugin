---
name: soundcraft
description: Unofficial third-party skill. Drive SoundCraft (open-source Pro Tools-style app) through its MCP server - generate or import audio onto tracks, set volume, pan, mute, automation and markers, bounce WAV/AIFF/FLAC with peak and LUFS, save and reopen .scraft sessions. Use when the user wants a multitrack mix built, measured or bounced.
---

# SoundCraft via MCP

Server: `soundcraft` (`soundcraft-cli mcp`). Tested with soundcraft-cli 0.16.0 on Windows 11 (the plugin's regression steps; written against 0.15.0).

- Headless engine. `new_session {"template":"demo"}` loads a 9-track demo (5 audio, 2 instrument, the aux `Verb` and `Master 1`) with 4 markers.
- **No headless picture.** `screenshot`, `ui_*`, `menu_invoke`, `click`, `drag` and `key` fail with "needs the desktop app". To preview, bounce and read `peak_db`/`lufs`.
- Live app (from the app's docs, not tested): `soundcraft --control 0` prints a port, then `mcp --connect PORT`. With nothing listening, calls fail with "connection timed out". `--connect` with a root flag exits 2.

## File access

In this plugin the server is locked to folders. It writes only to the output folder (plugin option `write_root`, default `~/CreativeApps`) and reads from the output folder plus, by default, the user's Desktop, Documents, Downloads, Pictures, Videos and Music folders (option `read_scope`: `write-root-only` drops those, `home` opens the whole home folder; `extra_read_root` adds one more). It starts in the output folder. Use absolute paths. The `creative-apps-setup` skill has the details.
- `--automation-read-root DIR` covers open, import and preset loads. `--automation-write-root DIR` covers save, bounce and exports. Both repeat. A missing root folder stops the server (exit 1).
- **With no root flag nothing is confined** (stderr then lacks the `files confined:` line). With any root flag, a kind left out is refused with "automation filesystem access is not granted: write authority is absent" (or read).
- **The write root is not readable.** To reopen a session or re-import a bounce, its folder must also be a read root.
- "automation path rejected" refuses paths outside the roots, a `..` that leaves a root, and junctions pointing out. A UNC path to a missing share fails with "cannot resolve" (a reachable share was not tested). Device names (`NUL.wav`, `CON`) are refused.
- **Relative paths resolve against the server's working directory**, then are checked against the roots like any other path: a relative read is refused when the working folder is not a read root. Replies echo them unresolved. A leading `/` is the current drive's root, so use `C:/...` paths.
- **Never put `:` in a path** except right after the drive letter.
- **Hard links:** `track.save_preset`, and `export_session_text` with `replace:true`, write through a hard link in place, so don't make hard links in the write root.

## Workflow (tested)
1. `new_session {"name":"Mix","template":"blank","sample_rate":48000}`.
2. `execute {"command":"track.new","params":{"name":"Tone","format":"mono"}}` → `{"tracks":[1]}`.
3. `execute audiosuite.process {"process":"signal_generator","tracks":[1],"start":0,"end":{"seconds":2},"params":{"waveform":0,"freq":1000,"level":-12}}` → `{"clips":[3],"processed":1}`.
   - `waveform` 0-5 is Sine, Square, Saw, Triangle, White Noise, Pink Noise. `level` is in dB (default -20).
4. `import_audio {"path":"C:/abs/clip.mp4"}` → `{"imported":[{track, clip, source, frames, channels}]}`. The new track is named after the file stem.
5. Mix with `execute`; replies confirm the call, not the state.
   - `mix.volume {"tracks":[1],"db":-6}`, `mix.pan {"tracks":[1],"pan":-1}`, `mix.mute {"tracks":[5],"value":true}`
   - `markers.add {"name":"Hit","at":{"seconds":1}}` → `{"id":7,"number":1}`
   - Times can be samples, `{"seconds":x}`, `"0:01.500"` or `"bars_beats:2|1|000"`.
6. Read back with `execute track.inspect {"track":1}` (clips in samples, `mute`, `pan`, `volume_db`) and `inspect_session {"detail":"summary"}` (markers, sources, `dirty`).
7. `bounce_mix {"path":"C:/abs/mix.wav","start":{"seconds":0},"end":{"seconds":2},"bit_depth":"24"}` → `{bytes, path, seconds, peak_db, true_peak_db, lufs}`.
   - Steps 3 and 5 give -18.0 dBFS and -21.0 LUFS.
   - `"format":"flac","bit_depth":"16"` writes a 16-bit FLAC.
8. `save_session {"path":"C:/abs/mix.scraft","replace":true}` → `{audio_files_written, path}`: JSON plus `Audio Files/` (32-bit float WAVs). Nothing is on disk before the first save. Identical audio already there is reused (counted 0); different audio with the same name gets `_01`.
9. In a fresh process, `open_session {"path":...}` → `{"missing":[],"name":"mix","tracks":2}`. Volume, pan, mute and markers survive, and a bounce after reopening nulls against the first (sample-identical).
10. `execute file.export_session_text {"path":"C:/abs/info.txt","replace":true}` lists tracks, clips, mutes and markers, but not volume or pan. Shell: `soundcraft-cli info <.scraft or audio file>`.

## Traps
- **Pan law:** mono at centre is -3 dB per side; hard-panned, 0 dB on its side.
- **Misspelled optional keys are ignored:** `bitdepth` wrote 24-bit, and `lvl` or `"level":"loud"` gave -20 dB. Missing required keys fail (`mix.volume` needs `db`, or `delta_db` for a relative change, and a bounce needs `path`).
- **Bounce:**
  - The default is 24-bit and `"32f"` writes float. `.aiff` and `.flac` write 24-bit. mp3 is refused.
  - `format` overrides the extension: `x.wav` with `"format":"aiff"` writes AIFF.
  - With no `start`/`end` it bounces the whole session. `normalize:true` peaks at -0.1 dBFS.
  - Dither leaves 1 LSB (-138 dBFS) on a silent side. `"dither":false` gives zeros and is accepted, although the schema does not list it.
  - Bounces overwrite silently. A missing folder fails (os error 3).
- **Save:** `save_session {}` fails until a path is set. Overwriting another file (or an `export_session_text` file) needs `replace:true`; the session's own path does not. Old content goes to `Backups/<stem> backup N.scraft`. Missing folders are created, and the session takes the file stem as its name. `track.save_preset` overwrites an existing file without `replace`.
- **AAC/M4A/MP4 imports land 1024 samples (21 ms) late** compared with ffmpeg. Convert to WAV first when sync matters.
- **Master:** `track.new {"kind":"master","name":"Master"}` is named `Master 1`, so use the returned id. Master `mix.volume` works; master `mix.trim` returns ok but does nothing. Track trim works but is not in `track.inspect`.
- **Automation:** `automation.write_range {"track":"A","param":"volume","start":0,"end":{"seconds":1},"value":-20}` replaces the fader level: -18 dBFS at -6 dB became -32. `automation.clear {"track":"A","param":"volume"}` restores it.
- **`batch {"calls":[...]}`** stops at the first error (isError, with a per-call `ok`), and earlier calls stay applied. `keep_going:true` runs the rest, but the reply is still an error if any call failed.
- **Discovery:** `list_commands` lists 482 commands (`{"filter":"mix"}` narrows it). `execute engine.plugins` lists 30 plugins.
