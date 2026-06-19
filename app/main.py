#!/usr/bin/env python3
"""
main.py — The Show starts here
CAINE: terminal AI with memory and training data collection

Commands:
  /good      — marks the last reply as a good training example
  /export    — exports the data to training_data.jsonl in the current folder
  /train     — shows how many examples have been collected
"""

import sys
import os

# ── Suppresses ALSA before any audio import ───────────────────────────────────
if sys.platform == "linux":
    import ctypes
    try:
        _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        _asound.snd_lib_error_set_handler(ctypes.CFUNCTYPE(None)(lambda *_: None))
    except Exception:
        pass

# ── Project imports ───────────────────────────────────────────────────────────
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.memory import Memory
from core.ai      import CaineAI
from audio.tts    import TTS

from rich.console import Console
from rich.panel   import Panel
from rich.live    import Live
from rich.text    import Text

console = Console()


class CaineApp:
    def __init__(self):
        self.memory = Memory()
        self.tts    = TTS()
        self.ai = CaineAI(self.memory)
        self.tts_enabled = self.tts.available
        self.running     = True

    def _welcome(self):
        name      = self.memory.data.get("name")
        sessions  = self.memory.data.get("num_sessions", 0)
        facts     = len(self.memory.data.get("facts", []))
        training  = self.ai.training_count()
        performer = f"[bold magenta]{name}[/bold magenta]" if name else "new performer"
        info = (
            f"Welcome to the show, {performer}!\n"
            f"Session [bold]#{sessions + 1}[/bold]  •  {facts} facts in memory  •  "
            f"[yellow]{training} training examples[/yellow]\n"
            f"Model: [bold cyan]{self.ai.model}[/bold cyan]  │  "
            f"TTS: {'[green]✓[/green] ' + self.tts.method if self.tts_enabled else '[red]✗[/red]'}\n\n"
            "[dim]/mute  /memory  /models  /model <n>\n"
            "/good  /train  /export  /forget  /clear  /quit[/dim]"
        )
        console.print(Panel(
            info,
            title="[bold yellow]🎭  THE AMAZING DIGITAL CIRCUS[/bold yellow]",
            border_style="yellow",
        ))
        console.print()

    def _handle_command(self, raw: str):
        parts = raw.strip().split(maxsplit=1)
        cmd   = parts[0].lower()

        if cmd in ("/quit", "/exit", "/q"):
            console.print("\n[dim]Saving the show's memory...[/dim]")
            self.ai.save_session()
            console.print("[bold yellow]The show... for now... ends. 👋[/bold yellow]")
            self.running = False

        elif cmd == "/good":
            # ── Marks the last reply as a good training example ──
            if self.ai.mark_good():
                total = self.ai.training_count()
                console.print(f"[green]✓ Saved! Total examples: {total}[/green]")
                console.print("[dim]Once you have ~100 examples, run /export[/dim]")
            else:
                console.print("[yellow]No reply to save yet.[/yellow]")

        elif cmd == "/train":
            total = self.ai.training_count()
            console.print(f"[cyan]Training examples collected: [bold]{total}[/bold][/cyan]")
            if total < 50:
                console.print(f"[dim]Recommended: at least 100. {max(0, 100-total)} to go.[/dim]")
            elif total < 100:
                console.print("[dim]Good progress! Keep using /good on the replies you like.[/dim]")
            else:
                console.print("[green]You have enough data for fine-tuning! Use /export.[/green]")

        elif cmd == "/export":
            path = self.ai.export_training()
            console.print(f"[green]✓ File exported:[/green] [bold]{path}[/bold]")
            console.print("[dim]Upload this file to Google Colab with Unsloth to train.[/dim]")

        elif cmd == "/mute":
            self.tts_enabled = not self.tts_enabled
            if self.tts_enabled and not self.tts.available:
                console.print("[red]TTS not available on this system.[/red]")
                self.tts_enabled = False
            else:
                state = f"[green]on ({self.tts.method})[/green]" if self.tts_enabled else "[red]off[/red]"
                console.print(f"[cyan]TTS {state}[/cyan]")

        elif cmd == "/memory":
            console.print(Panel(
                self.memory.show(),
                title="[bold green]🧠 Memory[/bold green]",
                border_style="green",
            ))

        elif cmd == "/forget":
            self.memory.clear()
            console.print("[dim]Memory cleared. New performer![/dim]")

        elif cmd == "/clear":
            self.ai.history = []
            console.print("[dim]Session history cleared.[/dim]")

        elif cmd == "/models":
            models  = self.ai.list_models()
            current = self.ai.model.split(":")[0]
            lines = [f"  {'→' if m.split(':')[0] == current else ' '} {m}" for m in models]
            console.print(Panel(
                "\n".join(lines) if lines else "No models.",
                title="[bold]Installed models[/bold]",
                border_style="cyan",
            ))

        elif cmd == "/model":
            if len(parts) < 2:
                console.print(f"[yellow]Current model: {self.ai.model}[/yellow]  Usage: /model <name>")
            else:
                self.ai.set_model(parts[1].strip())
                console.print(f"[cyan]Model: '{self.ai.model}'. History cleared.[/cyan]")

        else:
            console.print(f"[yellow]Unknown command:[/yellow] {cmd}")
            console.print("[dim]/mute /memory /models /model /good /train /export /forget /clear /quit[/dim]")

    def _stream_reply(self, user_input: str) -> str:
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
            raise
        console.print()
        return "".join(collected)

    def run(self):
        self._welcome()

        while self.running:
            try:
                console.print("[bold cyan]You »[/bold cyan] ", end="")
                user_input = input().strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    console.print()
                    continue

                reply = self._stream_reply(user_input)

                # Hint after each reply
                console.print("[dim]  (if you liked this reply, type /good)[/dim]")

                if self.tts_enabled:
                    self.tts.speak(reply)

            except KeyboardInterrupt:
                console.print("\n\n[dim]Saving memory...[/dim]")
                self.ai.save_session()
                console.print("[bold yellow]\nThe show... for now... ends. 👋[/bold yellow]")
                break


if __name__ == "__main__":
    try:
        CaineApp().run()
    except RuntimeError as e:
        console.print(f"\n[bold red]❌  {e}[/bold red]\n")
        sys.exit(1)
