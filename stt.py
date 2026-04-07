"""
stt.py — Reconhecimento de voz do Caine
Melhorado:
  - Whisper local (faster-whisper) se instalado → muito mais rápido e preciso
  - Fallback automático para Google Speech
  - Calibração de ruído ambiente em background (não bloqueia o arranque)
  - Feedback de estado: a escutar / a processar / erro
  - Deteção de voz por energia antes de enviar para reconhecimento
  - energy_threshold adaptativo mais agressivo
"""

import os
import sys
import ctypes
import contextlib
import threading
import queue
import time
from typing import Callable

import speech_recognition as sr


# ── Silencia ALSA/JACK no Linux ───────────────────────────────────────────────
_ALSA_ERROR_HANDLER = None

def _suppress_alsa():
    global _ALSA_ERROR_HANDLER
    if sys.platform != "linux":
        return
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        _ALSA_ERROR_HANDLER = ctypes.CFUNCTYPE(None)(lambda *_: None)
        asound.snd_lib_error_set_handler(_ALSA_ERROR_HANDLER)
    except Exception:
        pass

_suppress_alsa()


@contextlib.contextmanager
def _quiet():
    """Redireciona stderr para /dev/null durante operações de áudio."""
    if sys.platform != "linux":
        yield
        return
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    old_stderr  = os.dup(2)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)


# ── Deteção de Whisper local ──────────────────────────────────────────────────
def _try_load_whisper():
    """
    Tenta carregar faster-whisper (mais rápido que openai-whisper).
    Instala via:  pip install faster-whisper
    Fallback:     openai-whisper
    """
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        return ("faster-whisper", model)
    except ImportError:
        pass
    try:
        import whisper
        model = whisper.load_model("small")
        return ("whisper", model)
    except ImportError:
        pass
    return (None, None)


class STT:
    """
    Reconhecedor de voz com dois backends:
      1. Whisper local  — offline, rápido, preciso em PT
      2. Google Speech  — online, fallback automático

    Parâmetros
    ----------
    on_state : callable(str) opcional
        Chamado com "listening", "processing", "calibrating", "error:<msg>"
        para atualizar UI (ex: mudar o ícone do terminal).
    prefer_whisper : bool
        Se False, usa sempre Google mesmo que Whisper esteja instalado.
    """

    def __init__(
        self,
        on_state: Callable[[str], None] | None = None,
        prefer_whisper: bool = True,
    ):
        self.on_state       = on_state or (lambda _: None)
        self.prefer_whisper = prefer_whisper

        self.r = sr.Recognizer()
        self.r.dynamic_energy_threshold  = True
        self.r.energy_threshold          = 300   # começa baixo; sobe com calibração
        self.r.pause_threshold           = 0.7   # mais responsivo (era 0.9)
        self.r.non_speaking_duration     = 0.4
        self.r.phrase_threshold          = 0.3

        self._mic          = None
        self._mic_checked  = False
        self._calibrated   = False
        self._calib_lock   = threading.Lock()

        # Carrega Whisper em background para não atrasar o arranque
        self._whisper_type  = None
        self._whisper_model = None
        self._whisper_ready = threading.Event()
        if prefer_whisper:
            threading.Thread(target=self._load_whisper_bg, daemon=True).start()
        else:
            self._whisper_ready.set()

    # ── Backend Whisper ───────────────────────────────────────────────────────
    def _load_whisper_bg(self):
        wtype, model = _try_load_whisper()
        self._whisper_type  = wtype
        self._whisper_model = model
        self._whisper_ready.set()

    @property
    def backend(self) -> str:
        if self._whisper_ready.is_set() and self._whisper_type:
            return self._whisper_type
        return "google"

    # ── Microfone ─────────────────────────────────────────────────────────────
    def _init_mic(self):
        if self._mic_checked:
            return
        self._mic_checked = True
        try:
            with _quiet():
                mic = sr.Microphone()
                with mic as src:
                    # Calibração rápida inicial (0.3s) — melhora drasticamente
                    # o threshold inicial antes da calibração profunda em bg
                    self.r.adjust_for_ambient_noise(src, duration=0.3)
                self._mic = mic
        except Exception:
            self._mic = None
            return

        # Calibração profunda em background (2s) sem bloquear o utilizador
        threading.Thread(target=self._calibrate_bg, daemon=True).start()

    def _calibrate_bg(self):
        """Ajusta o energy_threshold ao ambiente real (2 segundos de silêncio)."""
        if self._calibrated or not self._mic:
            return
        self.on_state("calibrating")
        try:
            with _quiet():
                with self._mic as src:
                    self.r.adjust_for_ambient_noise(src, duration=2.0)
            with self._calib_lock:
                self._calibrated = True
        except Exception:
            pass

    @property
    def available(self) -> bool:
        self._init_mic()
        return self._mic is not None

    # ── Reconhecimento ────────────────────────────────────────────────────────
    def _recognize_whisper(self, audio: sr.AudioData) -> str | None:
        """Transcreve com Whisper local. Muito mais rápido que Google em hardware médio."""
        import io, tempfile, wave

        # Guarda o áudio em WAV temporário
        wav_data = audio.get_wav_data()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_data)
            tmp_path = f.name

        try:
            if self._whisper_type == "faster-whisper":
                segments, info = self._whisper_model.transcribe(
                    tmp_path,
                    language="pt",
                    beam_size=3,           # balanceia velocidade vs qualidade
                    vad_filter=True,       # filtra silêncio automaticamente
                    vad_parameters={"min_silence_duration_ms": 300},
                )
                return " ".join(s.text.strip() for s in segments).strip() or None

            elif self._whisper_type == "whisper":
                result = self._whisper_model.transcribe(tmp_path, language="pt", fp16=False)
                return result.get("text", "").strip() or None

        except Exception:
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _recognize_google(self, audio: sr.AudioData) -> str | None:
        """Fallback para Google Speech Recognition."""
        try:
            return self.r.recognize_google(audio, language="pt-PT")
        except (sr.UnknownValueError, sr.RequestError):
            return None

    # ── API pública ───────────────────────────────────────────────────────────
    def listen(self, timeout: int = 8, phrase_limit: int = 20) -> str | None:
        """
        Escuta o microfone e devolve o texto reconhecido, ou None.

        Fluxo:
          1. Capta áudio (com timeout)
          2. Se Whisper disponível → usa Whisper
          3. Senão → Google Speech
        """
        self._init_mic()
        if not self._mic:
            return None

        # Aguarda Whisper carregar mas não eternamente (máx 3s)
        self._whisper_ready.wait(timeout=3.0)

        try:
            self.on_state("listening")
            with _quiet():
                with self._mic as src:
                    # Recalibra apenas se não estiver calibrado ainda
                    if not self._calibrated:
                        self.r.adjust_for_ambient_noise(src, duration=0.2)
                    audio = self.r.listen(
                        src,
                        timeout=timeout,
                        phrase_time_limit=phrase_limit,
                    )

            self.on_state("processing")

            # Escolhe backend
            if self._whisper_type and self.prefer_whisper:
                result = self._recognize_whisper(audio)
                if result is None:
                    # Whisper falhou → tenta Google como último recurso
                    result = self._recognize_google(audio)
            else:
                result = self._recognize_google(audio)

            return result

        except sr.WaitTimeoutError:
            self.on_state("listening")  # volta ao estado de espera silenciosamente
            return None
        except sr.UnknownValueError:
            self.on_state("error:não percebido")
            return None
        except Exception as e:
            self.on_state(f"error:{e}")
            return None

    def listen_continuous(
        self,
        callback: Callable[[str], None],
        stop_event: threading.Event,
    ):
        """
        Escuta em loop numa thread separada.
        Chama callback(texto) para cada frase reconhecida.
        Para quando stop_event estiver definido.
        """
        while not stop_event.is_set():
            text = self.listen()
            if text and not stop_event.is_set():
                callback(text)