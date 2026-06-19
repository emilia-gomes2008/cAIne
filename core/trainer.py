"""
trainer.py — Training data collection for CAINE's fine-tuning
Stores good conversations in JSONL format (compatible with Unsloth/OpenAI)

Usage:
  from core.trainer import Trainer
  t = Trainer()
  t.save_example(user="how do I do X?", assistant="Here's how: ...")
  t.export()  # generates training_data.jsonl
"""

import json
from pathlib import Path
from datetime import datetime

DATA_DIR      = Path.home() / ".caine"
TRAINING_FILE = DATA_DIR / "training_data.jsonl"

SYSTEM_PROMPT = (
    "You are CAINE — ringmaster of The Amazing Digital Circus and a programming genius. "
    "Specialties: Python, PyQt6, Ollama API, TTS, AI agent architecture. "
    "You always reply in the same language the user wrote in. When you write code: complete, functional, commented."
)


class Trainer:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)

    def save_example(self, user: str, assistant: str):
        """Saves a question/answer pair to the JSONL file."""
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
        Saves the whole session as a multi-turn example.
        history = list of {"role": ..., "content": ...}
        """
        if len(history) < 2:
            return
        example = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history
        }
        with TRAINING_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    def count(self) -> int:
        """Returns the number of stored examples."""
        if not TRAINING_FILE.exists():
            return 0
        return sum(1 for _ in TRAINING_FILE.open(encoding="utf-8"))

    def export(self, dest: Path | None = None) -> Path:
        """
        Copies the JSONL file to the given destination (or the current folder).
        Ready to upload to Google Colab / Unsloth.
        """
        dest = dest or Path.cwd() / "training_data.jsonl"
        if TRAINING_FILE.exists():
            dest.write_bytes(TRAINING_FILE.read_bytes())
            print(f"✓ Exported: {dest}  ({self.count()} examples)")
        else:
            print("No data to export.")
        return dest

    def clear(self):
        if TRAINING_FILE.exists():
            TRAINING_FILE.unlink()
            print("Training data cleared.")
