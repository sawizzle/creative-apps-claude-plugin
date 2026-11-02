# Sandbox battery setup for SoundCraft (tests/run_all_tests.py runs it first). Usage: python soundcraft.setup.py <OUT>
# Creates, next to <OUT> and outside both roots:
#   <OUT>_outside/outside.wav   a 0.25 s 1 kHz mono WAV that the server must never read
# and inside <OUT>:
#   <OUT>/jx  a directory junction pointing at <OUT>_outside (_winapi.CreateJunction, no admin needed)
#   <OUT>/inside_seed.wav       a readable file inside the write root
# It is idempotent: it removes the junction, recreates <OUT>_outside from scratch and remakes every file. It also deletes the two
# files the battery's '..' escape checks look for in <OUT>/.. (sbx_dotdot.wav, sbx_rel_escape.wav), so a leak left by
# an earlier broken or unconfined run cannot fail a later good run.
# Safety: it runs only in the test runner's layout (<OUT> is a folder named sandbox_out with a sandbox_in beside it), and it
# deletes <OUT>_outside only when that folder carries the marker file this script writes into it.
import math, os, shutil, struct, sys, wave

MARKER = ".soundcraft_sandbox_fixture"


def tone(path, seconds=0.25, rate=48000, freq=1000.0, dbfs=-12.0):
    amp = 10 ** (dbfs / 20.0)
    n = int(seconds * rate)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)))


def main():
    if sys.platform != "win32":
        sys.exit("Windows-only fixture (junctions)")
    import _winapi
    out = os.path.abspath(sys.argv[1])
    if os.path.basename(out) != "sandbox_out" or not os.path.isdir(os.path.join(os.path.dirname(out), "sandbox_in")):
        sys.exit(f"refusing: {out} is not a test runner's sandbox_out folder (with sandbox_in beside it)")
    os.makedirs(out, exist_ok=True)
    outside = out + "_outside"
    jx = os.path.join(out, "jx")
    if os.path.lexists(jx):
        os.rmdir(jx)  # removes the junction only, never its target
    # start the outside folder from scratch (only a folder this script made, with the marker inside, is removed)
    if os.path.isdir(outside):
        if not os.path.isfile(os.path.join(outside, MARKER)):
            sys.exit(f"refusing: {outside} exists and was not made by this setup")
        shutil.rmtree(outside)
    os.makedirs(outside, exist_ok=True)
    open(os.path.join(outside, MARKER), "w").close()
    tone(os.path.join(outside, "outside.wav"))
    tone(os.path.join(out, "inside_seed.wav"))
    _winapi.CreateJunction(outside, jx)
    if not os.path.isfile(os.path.join(jx, "outside.wav")):
        sys.exit("junction failed")
    for name in ("sbx_dotdot.wav", "sbx_rel_escape.wav"):
        leak = os.path.join(os.path.dirname(out), name)
        if os.path.isfile(leak) and not os.path.islink(leak):
            os.remove(leak)
    print("ok", out, outside, jx)


if __name__ == "__main__":
    main()
