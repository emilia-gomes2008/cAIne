"""
memory.py — Memória persistente do Caine
Guarda factos sobre o performer entre sessões.
"""

import json
import re
from pathlib import Path
from datetime import datetime

DATA_DIR    = Path.home() / ".caine"
MEMORY_FILE = DATA_DIR / "memoria.json"


class Memory:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"nome": None, "factos": [], "num_sessoes": 0, "ultima_sessao": None}

    def save(self):
        MEMORY_FILE.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ── Contexto injetado no system prompt ───────────────────────────────────
    def context_block(self) -> str:
        parts = []
        if self.data.get("nome"):
            parts.append(f"Nome do performer: {self.data['nome']}")
        if self.data.get("factos"):
            parts.append("Factos conhecidos sobre o performer:")
            for f in self.data["factos"][-20:]:
                parts.append(f"  • {f}")
        if self.data.get("ultima_sessao"):
            parts.append(f"Última sessão: {self.data['ultima_sessao']}")
        return "\n".join(parts) if parts else "Primeiro contacto com este performer."

    # ── Atualiza com dados extraídos ─────────────────────────────────────────
    def update(self, extracted: dict):
        if extracted.get("nome"):
            self.data["nome"] = extracted["nome"]
        for f in extracted.get("factos", []):
            if f and f not in self.data["factos"]:
                self.data["factos"].append(f)
        self.data["ultima_sessao"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.data["num_sessoes"]   = self.data.get("num_sessoes", 0) + 1
        self.save()

    # ── Extração simples de factos por palavras-chave ─────────────────────────
    def extract_simple(self, text: str):
        """Extração rápida sem chamar o modelo."""
        triggers = [
            "chamo-me", "o meu nome é", "sou o", "sou a",
            "gosto de", "adoro", "odeio", "trabalho", "vivo em",
            "tenho", "anos", "profissão", "hobby"
        ]
        t = text.lower()
        if any(kw in t for kw in triggers):
            # Normaliza e guarda
            fact = text.strip().rstrip(".")
            if fact and fact not in self.data["factos"]:
                self.data["factos"].append(fact)
                self.save()

    def update_session(self):
        """Chamado no fecho — atualiza contadores mesmo sem extração."""
        self.data["ultima_sessao"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.data["num_sessoes"]   = self.data.get("num_sessoes", 0) + 1
        self.save()

    def show(self) -> str:
        d = self.data
        lines = [
            f"Nome:     {d.get('nome') or '(desconhecido)'}",
            f"Sessões:  {d.get('num_sessoes', 0)}",
            f"Última:   {d.get('ultima_sessao') or 'N/A'}",
        ]
        factos = d.get("factos", [])
        if factos:
            lines.append(f"\nFactos ({len(factos)}):")
            for f in factos:
                lines.append(f"  • {f}")
        else:
            lines.append("\nSem factos guardados.")
        return "\n".join(lines)

    def clear(self):
        self.data = {
            "nome": None, "factos": [],
            "num_sessoes": self.data.get("num_sessoes", 0),
            "ultima_sessao": self.data.get("ultima_sessao"),
        }
        self.save()