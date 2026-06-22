# 🎭 CAINE — The Amazing Digital Circus AI

Terminal and desktop AI with Caine's personality, spoken replies (TTS), persistent memory, and fine-tuning tools.
First message can take a bit, optimization needs some improvement yet.

## Structure

```
cAIne/
├── app/
│   ├── main.py         ← terminal entry point (run this for the CLI)
│   └── gui.py           ← desktop entry point (PyQt6 GUI)
├── core/
│   ├── ai.py             ← brain: chat with Ollama + memory extraction
│   ├── memory.py         ← persistent memory in ~/.caine/memory.json
│   └── trainer.py        ← training data collection (JSONL)
├── audio/
│   └── tts.py             ← speech synthesis (espeak-ng / say / pyttsx3)
├── data/
│   ├── import_datasets.py        ← imports Hugging Face datasets
│   └── prepare_finetune_data.py  ← builds finetune_data.jsonl
├── assets/
│   └── caine_avatar.png   ← GUI avatar
├── model/
│   ├── Modelfile           ← Ollama model definition
│   └── caine_model.gguf    ← fine-tuned weights (not committed, see .gitignore)
└── requirements.txt
```

## Installation

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &          # in another terminal
ollama pull llama3.2     # 2GB

# 2. Audio dependencies (Linux, for spoken replies)
sudo apt install espeak-ng

# 3. Python packages
pip install -r requirements.txt

# 4. Run
python app/main.py     # terminal
python app/gui.py      # desktop GUI
```

## Commands

| Command | Action |
|---|---|
| `/mute` | Toggles TTS |
| `/memory` | Shows what Caine knows about you |
| `/forget` | Clears memory |
| `/models` | Lists installed Ollama models |
| `/model llama3.3` | Switches model |
| `/clear` | Clears the session history |
| `/good` | Marks the last reply as a good training example |
| `/train` | Shows how many training examples have been collected |
| `/export` | Exports the data to training_data.jsonl |
| `/quit` | Saves and exits |

CAINE always replies in whatever language you write to it in — no fixed language is hardcoded into the persona.

## Standalone binary (no Python install needed)

Build a single-file executable of the GUI with PyInstaller. **You must build on each target OS** — PyInstaller does not cross-compile, so a Windows `.exe` has to be built on a Windows machine and a Linux binary on Linux.

```bash
# Linux — produces dist/CAINE
./packaging/build_linux.sh
```

```bat
:: Windows — produces dist\CAINE.exe
packaging\build_windows.bat
```

The binary only bundles the Python app (PyQt6, etc.) — it does **not** include Ollama or the model weights. Ollama still has to be installed and running (locally, or reachable over the network) wherever you run the binary; `ollama pull`/`ollama create caine-dev` happen the same way as in a normal install.