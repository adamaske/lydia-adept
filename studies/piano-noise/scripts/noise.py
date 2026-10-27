"""Looped background-noise playback (multi-talker babble) for the NP blocks.

No third-party dependencies:
  Windows      winsound.PlaySound(..., SND_ASYNC | SND_LOOP)   -> file must be PCM WAV
  Linux/macOS  paplay / aplay / afplay restarted in a loop by a background thread

Level calibration is done with the OS/amplifier volume and an SPL meter at the
listening position (target ~65 dB SPL for the babble); use `--noise-test`
in run_session.py to play the file for a while.
"""
import os
import shutil
import subprocess
import sys
import threading
import wave


class NoisePlayer:
    def __init__(self, path):
        self.path = path
        self.enabled = path is not None
        self._thread = None
        self._stop = threading.Event()
        self._proc = None
        if self.enabled:
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            with wave.open(path, "rb") as w:  # validates that it is a PCM WAV
                self.duration_s = w.getnframes() / w.getframerate()
            self._player = None
            if sys.platform != "win32":
                for cand in (["paplay"], ["aplay", "-q"], ["afplay"]):
                    if shutil.which(cand[0]):
                        self._player = cand
                        break
                if self._player is None:
                    raise RuntimeError("no command-line audio player found (paplay/aplay/afplay)")

    # ------------------------------------------------------------------ #
    def start(self):
        if not self.enabled:
            return
        self.stop()
        self._stop.clear()
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(self.path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
        else:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        if not self.enabled:
            return
        self._stop.set()
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        else:
            p = self._proc
            if p is not None and p.poll() is None:
                p.terminate()
            if self._thread is not None:
                self._thread.join(timeout=1.0)
                self._thread = None

    def _loop(self):
        while not self._stop.is_set():
            self._proc = subprocess.Popen(self._player + [self.path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._proc.wait()


if __name__ == "__main__":
    import time
    p = NoisePlayer(sys.argv[1])
    print(f"playing {sys.argv[1]} ({p.duration_s:.1f} s file) for 5 s")
    p.start(); time.sleep(5); p.stop()
