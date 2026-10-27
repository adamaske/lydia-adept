"""1 kHz audio cue, no third-party dependencies.

Windows: winsound.Beep. Linux/macOS: a generated WAV played with the first
available command-line player (paplay, aplay, afplay). Playback runs in a
background thread so marker timing is not delayed.
"""
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave

FREQ_HZ = 1000
DURATION_MS = 200
_wav_path = None


def _make_wav(freq=FREQ_HZ, ms=DURATION_MS, rate=44100, amp=0.5):
    global _wav_path
    if _wav_path and os.path.exists(_wav_path):
        return _wav_path
    n = int(rate * ms / 1000)
    fade = int(rate * 0.005)  # 5 ms ramp to avoid clicks
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        v = int(32767 * amp * env * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack("<h", v)
    fd, path = tempfile.mkstemp(prefix="piano_beep_", suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    _wav_path = path
    return path


def _play(freq, ms):
    try:
        if sys.platform == "win32":
            import winsound
            winsound.Beep(freq, ms)
            return
        path = _make_wav(freq, ms)
        for player in (["paplay"], ["aplay", "-q"], ["afplay"]):
            if shutil.which(player[0]):
                subprocess.run(player + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        print("\a", end="", flush=True)  # terminal bell as last resort
    except Exception as e:  # never let audio break the session
        print(f"  (beep failed: {e})")


def beep(freq: int = FREQ_HZ, ms: int = DURATION_MS, times: int = 1, gap_ms: int = 120):
    def run():
        for i in range(times):
            _play(freq, ms)
            if i < times - 1 and sys.platform == "win32":
                import time
                time.sleep(gap_ms / 1000)
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    import time
    beep(); time.sleep(0.6); beep(times=2); time.sleep(1)
