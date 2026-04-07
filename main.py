#!/usr/bin/env python3
"""
main.py — O Espetáculo começa aqui
Caine: IA terminal com voz, memória e músicas
Otimizado:
  - Streaming de tokens em modo texto E modo voz
  - TTS arranca em paralelo com o streaming (não espera pelo fim)
  - Feedback de estado do microfone (a calibrar / a escutar / a processar)
  - Indicador de backend STT ativo (Whisper / Google)
"""

import sys
import os
import threading

# ── Suprime ALSA antes de qualquer import de áudio ───────────────────────────
if sys.platform == "linux":
    import ctypes
    try:
        _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        _asound.snd_lib_error_set_handler(ctypes.CFUNCTYPE(None)(lambda *_: None))
    except Exception:
        pass

# ── Imports do projeto ────────────────────────────────────────────────────────
from pathlib import Path
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from memory import Memory
from ai     import CaineAI
from tts    import TTS
from stt    import STT

from rich.console import Console
from rich.panel   import Panel
from rich.live    import Live
from rich.text    import Text

console = Console()

# ── Ícones de estado do microfone ─────────────────────────────────────────────
_MIC_STATES = {
    "listening"   : ("[bold green]🎤[/bold green]", "A escutar..."),
    "processing"  : ("[bold yellow]⚙[/bold yellow]",  "A processar..."),
    "calibrating" : ("[bold cyan]📡[/bold cyan]",    "A calibrar mic..."),
}

def _mic_label(state: str) -> str:
    if state.startswith("error:"):
        msg = state[6:] or "erro"
        return f"[bold red]✗[/bold red] [dim]{msg}[/dim]"
    icon, label = _MIC_STATES.get(state, ("🎤", state))
    return f"{icon} [dim]{label}[/dim]"


# ══════════════════════════════════════════════════════════════════════════════
#  APLICAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

class CaineApp:
    def __init__(self):
        self.memory = Memory()
        self.tts    = TTS()

        # STT com callback de estado — atualiza variável para o loop de UI
        self._mic_state = "listening"
        self.stt = STT(on_state=self._on_mic_state)

        self.ai = CaineAI(self.memory)

        self.voice_mode  = False
        self.tts_enabled = self.tts.available
        self.running     = True

    def _on_mic_state(self, state: str):
        self._mic_state = state

    # ── Boas-vindas ───────────────────────────────────────────────────────────
    def _welcome(self):
        nome    = self.memory.data.get("nome")
        sessoes = self.memory.data.get("num_sessoes", 0)
        factos  = len(self.memory.data.get("factos", []))

        performer = f"[bold magenta]{nome}[/bold magenta]" if nome else "novo performer"

        # Aguarda detecção de Whisper (máx 2s) para mostrar backend correto
        self.stt._whisper_ready.wait(timeout=2.0)
        stt_backend = self.stt.backend

        info = (
            f"Bem-vindo ao espetáculo, {performer}!\n"
            f"Sessão [bold]#{sessoes + 1}[/bold]  •  {factos} factos na memória\n"
            f"Modelo: [bold cyan]{self.ai.model}[/bold cyan]  │  "
            f"TTS: {'[green]✓[/green] ' + self.tts.method if self.tts_enabled else '[red]✗[/red]'}  │  "
            f"STT: {'[green]' + stt_backend + '[/green]' if self.stt.available else '[red]✗[/red]'}\n\n"
            "[dim]/voz  /mudo  /memoria  /modelos  "
            "/modelo <n>  /apagar  /limpar  /sair[/dim]"
        )
        console.print(Panel(
            info,
            title="[bold yellow]🎭  THE AMAZING DIGITAL CIRCUS[/bold yellow]",
            border_style="yellow",
        ))
        console.print()

    # ── Comandos ──────────────────────────────────────────────────────────────
    def _handle_command(self, raw: str):
        parts = raw.strip().split(maxsplit=1)
        cmd   = parts[0].lower()

        if cmd in ("/sair", "/exit", "/quit", "/q"):
            console.print("\n[dim]A guardar memória do espetáculo...[/dim]")
            self.ai.save_session()
            console.print("[bold yellow]O show... por agora... termina. 👋[/bold yellow]")
            self.running = False

        elif cmd == "/voz":
            if self.stt.available:
                self.voice_mode = not self.voice_mode
                estado = "[green]ativado 🎤[/green]" if self.voice_mode else "[red]desativado[/red]"
                console.print(f"[cyan]Modo voz {estado}[/cyan]")
                if self.voice_mode:
                    console.print(f"[dim]Backend STT: {self.stt.backend}[/dim]")
            else:
                console.print("[red]Microfone não disponível.[/red]")

        elif cmd == "/mudo":
            self.tts_enabled = not self.tts_enabled
            if self.tts_enabled and not self.tts.available:
                console.print("[red]TTS não disponível neste sistema.[/red]")
                self.tts_enabled = False
            else:
                estado = f"[green]ativado ({self.tts.method})[/green]" if self.tts_enabled else "[red]desligado[/red]"
                console.print(f"[cyan]TTS {estado}[/cyan]")

        elif cmd == "/memoria":
            console.print(Panel(
                self.memory.show(),
                title="[bold green]🧠 Memória[/bold green]",
                border_style="green",
            ))

        elif cmd == "/apagar":
            self.memory.clear()
            console.print("[dim]Memória apagada. Novo performer![/dim]")

        elif cmd == "/limpar":
            self.ai.history = []
            console.print("[dim]Histórico da sessão limpo.[/dim]")

        elif cmd == "/modelos":
            models = self.ai.list_models()
            atual  = self.ai.model.split(":")[0]
            linhas = [f"  {'→' if m.split(':')[0] == atual else ' '} {m}" for m in models]
            console.print(Panel(
                "\n".join(linhas) if linhas else "Nenhum modelo.",
                title="[bold]Modelos instalados[/bold]",
                border_style="cyan",
            ))

        elif cmd == "/modelo":
            if len(parts) < 2:
                console.print(f"[yellow]Modelo atual: {self.ai.model}[/yellow]  Uso: /modelo <nome>")
            else:
                self.ai.set_model(parts[1].strip())
                console.print(f"[cyan]Modelo: '{self.ai.model}'. Histórico limpo.[/cyan]")

        else:
            console.print(f"[yellow]Comando desconhecido:[/yellow] {cmd}")
            console.print("[dim]/voz /mudo /memoria /modelos /modelo /apagar /limpar /sair[/dim]")

    # ── Streaming com TTS paralelo ────────────────────────────────────────────
    def _stream_reply(self, user_input: str) -> str:
        """Faz streaming dos tokens para o terminal e devolve a resposta completa."""
        console.print()
        console.print("[bold magenta]CAINE »[/bold magenta]")

        collected = []

        try:
            with Live(
                Panel("", border_style="magenta", padding=(0, 1)),
                console=console,
                refresh_per_second=15,
            ) as live:
                for token in self.ai.chat_stream(user_input):
                    collected.append(token)
                    live.update(Panel(
                        Text("".join(collected)),
                        border_style="magenta",
                        padding=(0, 1),
                    ))
        except KeyboardInterrupt:
            raise  # propaga para o run() guardar a sessão

        console.print()
        return "".join(collected)

    # ── Input por voz com feedback visual ─────────────────────────────────────
    def _listen_with_feedback(self) -> str | None:
        """
        Escuta o microfone mostrando estado em tempo real:
          📡 A calibrar mic...  →  🎤 A escutar...  →  ⚙ A processar...
        """
        result_holder = [None]
        done = threading.Event()

        def _do_listen():
            result_holder[0] = self.stt.listen()
            done.set()

        threading.Thread(target=_do_listen, daemon=True).start()

        with Live(console=console, refresh_per_second=8) as live:
            while not done.is_set():
                live.update(Text.from_markup(
                    f"[bold cyan]Tu 🎤 »[/bold cyan]  {_mic_label(self._mic_state)}"
                ))
                done.wait(timeout=0.12)
            live.update(Text(""))

        text = result_holder[0]
        if text:
            console.print(f"[bold cyan]Tu 🎤 »[/bold cyan] [dim]{text}[/dim]")
        return text

    # ── Loop principal ────────────────────────────────────────────────────────
    def run(self):
        self._welcome()

        while self.running:
            try:
                # ── Input ──
                if self.voice_mode:
                    user_input = self._listen_with_feedback()
                    if not user_input:
                        continue
                else:
                    console.print("[bold cyan]Tu »[/bold cyan] ", end="")
                    user_input = input().strip()

                if not user_input:
                    continue

                # ── Comandos ──
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    console.print()
                    continue

                # ── Resposta com streaming em ambos os modos ──
                # Streaming puro; TTS só arranca depois do texto completo
                reply = self._stream_reply(user_input)

                if self.tts_enabled:
                    self.tts.speak(reply)

            except KeyboardInterrupt:
                console.print("\n\n[dim]A guardar memória...[/dim]")
                self.ai.save_session()
                console.print("[bold yellow]\nO show... por agora... termina. 👋[/bold yellow]")
                break


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        CaineApp().run()
    except RuntimeError as e:
        console.print(f"\n[bold red]❌  {e}[/bold red]\n")
        sys.exit(1)