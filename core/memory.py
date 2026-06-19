"""
memory.py — CAINE's persistent memory
Stores facts about the performer across sessions.
"""

import json
import re
from pathlib import Path
from datetime import datetime

DATA_DIR    = Path.home() / ".caine"
MEMORY_FILE = DATA_DIR / "memory.json"


class Memory:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                data.setdefault("opinion", None)
                data.setdefault("favorite_moment", None)
                return data
            except Exception:
                pass
        return {
            "name": None, "facts": [], "num_sessions": 0, "last_session": None,
            "opinion": None, "favorite_moment": None,
        }

    def save(self):
        MEMORY_FILE.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ── Context injected into the system prompt ──────────────────────────────
    def context_block(self) -> str:
        parts = []
        if self.data.get("name"):
            parts.append(f"Performer's name: {self.data['name']}")
        if self.data.get("facts"):
            parts.append("Known facts about the performer:")
            for f in self.data["facts"][-20:]:
                parts.append(f"  • {f}")
        if self.data.get("last_session"):
            parts.append(f"Last session: {self.data['last_session']}")
        return "\n".join(parts) if parts else "First contact with this performer."

    # ── Updates with extracted data ───────────────────────────────────────────
    def update(self, extracted: dict):
        if extracted.get("name"):
            self.data["name"] = extracted["name"]
        for f in extracted.get("facts", []):
            if f and f not in self.data["facts"]:
                self.data["facts"].append(f)
        # Only overwrite opinion/favorite_moment when the model actually gave a
        # new value — keeps the last known one instead of flickering back to empty.
        if extracted.get("opinion"):
            self.data["opinion"] = extracted["opinion"]
        if extracted.get("favorite_moment"):
            self.data["favorite_moment"] = extracted["favorite_moment"]
        self.data["last_session"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.data["num_sessions"] = self.data.get("num_sessions", 0) + 1
        self.save()

    # ── Simple keyword-based fact extraction ──────────────────────────────────
    def extract_simple(self, text: str):
        """Quick extraction without calling the model."""
        triggers = [
            "my name is", "i'm a", "i am a", "i'm the", "i am the",
            "i like", "i love", "i hate", "i work", "i live in",
            "i have", "years old", "profession", "hobby"
        ]
        t = text.lower()
        if any(kw in t for kw in triggers):
            # Normalize and store
            fact = text.strip().rstrip(".")
            if fact and fact not in self.data["facts"]:
                self.data["facts"].append(fact)
                self.save()

    def update_session(self):
        """Called on close — updates counters even without extraction."""
        self.data["last_session"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.data["num_sessions"] = self.data.get("num_sessions", 0) + 1
        self.save()

    def show(self) -> str:
        d = self.data
        lines = [
            f"Name:     {d.get('name') or '(unknown)'}",
            f"Sessions: {d.get('num_sessions', 0)}",
            f"Last:     {d.get('last_session') or 'N/A'}",
        ]
        facts = d.get("facts", [])
        if facts:
            lines.append(f"\nFacts ({len(facts)}):")
            for f in facts:
                lines.append(f"  • {f}")
        else:
            lines.append("\nNo facts stored.")
        return "\n".join(lines)

    def clear(self):
        self.data = {
            "name": None, "facts": [],
            "num_sessions": self.data.get("num_sessions", 0),
            "last_session": self.data.get("last_session"),
            "opinion": None, "favorite_moment": None,
        }
        self.save()
