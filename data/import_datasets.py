"""
import_datasets.py — Imports 3 Hugging Face datasets for CAINE
Filters relevant examples (Python, PyQt, Ollama, AI) and converts them to JSONL

Usage:
    pip install datasets
    python import_datasets.py
"""

import json
from pathlib import Path
from datasets import load_dataset

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = Path.home() / ".caine"
OUTPUT   = DATA_DIR / "training_data.jsonl"
DATA_DIR.mkdir(exist_ok=True)

SYSTEM = (
    "You are CAINE — ringmaster of The Amazing Digital Circus and a programming genius. "
    "Specialties: Python, PyQt6, Ollama API, TTS, AI agent architecture. "
    "You always reply in the same language the user wrote in. When you write code: complete, functional, commented."
)

# Keywords used to filter relevant examples
KEYWORDS = [
    "python", "pyqt", "ollama", "threading", "json", "api",
    "class", "function", "async", "stream", "model", "ai",
    "machine learning", "neural", "prompt", "llm", "chatbot",
    "gui", "interface", "socket", "http", "request", "subprocess",
]

def is_relevant(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in KEYWORDS)

def save_example(f, user: str, assistant: str):
    if not user.strip() or not assistant.strip():
        return 0
    example = {
        "messages": [
            {"role": "system",    "content": SYSTEM},
            {"role": "user",      "content": user.strip()},
            {"role": "assistant", "content": assistant.strip()},
        ]
    }
    f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return 1


# ══════════════════════════════════════════════════════════════════════════════
print("\n🎭 CAINE — Dataset importer")
print("=" * 50)

total = 0

with OUTPUT.open("a", encoding="utf-8") as f:

    # ── 1. CodeAlpaca-20k ─────────────────────────────────────────────────────
    print("\n[1/3] Loading CodeAlpaca-20k...")
    try:
        ds1 = load_dataset("sahil2801/CodeAlpaca-20k", split="train")
        count1 = 0
        for row in ds1:
            instruction = row.get("instruction", "")
            output      = row.get("output", "")
            inp         = row.get("input", "")
            # Appends input to the instruction if it exists
            user = f"{instruction}\n{inp}".strip() if inp else instruction
            if is_relevant(user) or is_relevant(output):
                count1 += save_example(f, user, output)
        print(f"   ✓ {count1} examples imported")
        total += count1
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # ── 2. OpenHermes-2.5 ─────────────────────────────────────────────────────
    print("\n[2/3] Loading OpenHermes-2.5...")
    try:
        ds2 = load_dataset("teknium/OpenHermes-2.5", split="train")
        count2 = 0
        for row in ds2:
            convs = row.get("conversations", [])
            if len(convs) < 2:
                continue
            # Format: list of {"from": "human"/"gpt", "value": "..."}
            user      = next((c["value"] for c in convs if c.get("from") == "human"), "")
            assistant = next((c["value"] for c in convs if c.get("from") == "gpt"),   "")
            if is_relevant(user) or is_relevant(assistant):
                count2 += save_example(f, user, assistant)
            # Caps at 5000 examples (the dataset is huge)
            if count2 >= 5000:
                break
        print(f"   ✓ {count2} examples imported")
        total += count2
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # ── 3. evol-codealpaca ────────────────────────────────────────────────────
    print("\n[3/3] Loading evol-codealpaca-v1...")
    try:
        ds3 = load_dataset("theblackcat102/evol-codealpaca-v1", split="train")
        count3 = 0
        for row in ds3:
            user      = row.get("instruction", "")
            assistant = row.get("output", "")
            if is_relevant(user) or is_relevant(assistant):
                count3 += save_example(f, user, assistant)
        print(f"   ✓ {count3} examples imported")
        total += count3
    except Exception as e:
        print(f"   ✗ Error: {e}")


# ── Final result ──────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
print(f"✓ Total: {total} examples saved to:")
print(f"  {OUTPUT}")
print()
if total >= 100:
    print("🟢 You have enough data for fine-tuning!")
    print("   Run /export in CAINE to get the file.")
else:
    print(f"🟡 Recommended: 100+ examples. You have {total}.")
print()
