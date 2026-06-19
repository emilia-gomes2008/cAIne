"""
tts.py — CAINE's speech synthesis
Supports espeak-ng (Linux), say (macOS), pyttsx3 (Windows)
"""

import re
import subprocess
import threading
import platform


class TTS:
    def __init__(self):
        self.os     = platform.system()
        self.method = self._detect()

    def _detect(self) -> str:
        if self.os == "Darwin":
            return "macos"
        elif self.os == "Linux":
            for cmd in ("espeak-ng", "espeak"):
                if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
                    return cmd
            return "none"
        elif self.os == "Windows":
            try:
                import pyttsx3  # noqa
                return "pyttsx3"
            except ImportError:
                return "none"
        return "none"

    @property
    def available(self) -> bool:
        return self.method != "none"

    def speak(self, text: str):
        if not self.available:
            return
        clean = re.sub(r"[*_`#>\[\]()♪♫]", "", text)
        clean = re.sub(r"\n+", ". ", clean).strip()
        threading.Thread(target=self._do, args=(clean,), daemon=True).start()

    def _do(self, text: str):
        try:
            if self.method == "macos":
                # Uses the system's default voice, which follows the OS language.
                subprocess.run(["say", text], capture_output=True)
            elif self.method == "espeak-ng":
                subprocess.run(
                    ["espeak-ng", "-s", "160", text],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            elif self.method == "espeak":
                subprocess.run(
                    ["espeak", text],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            elif self.method == "pyttsx3":
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
        except Exception:
            pass
