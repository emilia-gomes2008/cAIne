"""
trainer.py — Recolha de dados para fine-tuning do Caine
Guarda conversas boas em formato JSONL (compatível com Unsloth/OpenAI)

Uso:
  from trainer import Trainer
  t = Trainer()
  t.save_example(user="como faço X?", assistant="Fazes assim: ...")
  t.export()  # gera training_data.jsonl
"""

import json
from pathlib import Path
from datetime import datetime

DATA_DIR      = Path.home() / ".caine"
TRAINING_FILE = DATA_DIR / "training_data.jsonl"

SYSTEM_PROMPT = (
    "És o CAINE — mestre de cerimónias do The Amazing Digital Circus e génio de programação. "
    "Especializações: Python, PyQt6, Ollama API, STT/TTS, arquitetura de agentes IA. "
    "Respondes em Português Europeu. Quando escreves código: completo, funcional, comentado."
)


class Trainer:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)

    def save_example(self, user: str, assistant: str):
        """Guarda um par pergunta/resposta no ficheiro JSONL."""
        example = {
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": user},
                {"role": "assistant", "content": assistant},
            ]
        }
        with TRAINING_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    def save_session(self, history: list[dict]):
        """
        Guarda toda a sessão como exemplos multi-turn.
        history = lista de {"role": ..., "content": ...}
        """
        if len(history) < 2:
            return
        example = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history
        }
        with TRAINING_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    def count(self) -> int:
        """Devolve o número de exemplos guardados."""
        if not TRAINING_FILE.exists():
            return 0
        return sum(1 for _ in TRAINING_FILE.open(encoding="utf-8"))

    def export(self, dest: Path | None = None) -> Path:
        """
        Copia o ficheiro JSONL para o destino indicado (ou pasta atual).
        Pronto para carregar no Google Colab / Unsloth.
        """
        dest = dest or Path.cwd() / "training_data.jsonl"
        if TRAINING_FILE.exists():
            dest.write_bytes(TRAINING_FILE.read_bytes())
            print(f"✓ Exportado: {dest}  ({self.count()} exemplos)")
        else:
            print("Sem dados para exportar.")
        return dest

    def clear(self):
        if TRAINING_FILE.exists():
            TRAINING_FILE.unlink()
            print("Dados de treino apagados.")