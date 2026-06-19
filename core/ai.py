"""
ai.py — CAINE's brain: chat with Ollama + memory extraction
Optimized: streaming, lazy extraction, async close, training data collection
"""

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import ollama

from core.memory  import Memory
from core.trainer import Trainer


ACTION_TRIGGER_WORDS = [
    # English
    "open", "termin", "read", "list", "show",
    "creat", "writ", "add", "delet", "remov",
    "command", "folder", "file",
    "website", "site", "google", "browser", "explorer",
    # Portuguese (CAINE replies in whatever language is prompted, so the
    # intent check needs to recognize requests in that language too)
    "abr", "lê", "leio", "ler", "lista", "mostra",
    "cria", "escrev", "adicion", "apaga", "remov",
    "comando", "pasta", "ficheiro",
    "site", "navegador", "explorador",
]


def action_seems_intentional(user_input: str) -> bool:
    """Only accept an ACTION if the performer's request has a related keyword.
    Prevents the model from firing actions (opening a terminal, writing files) on greetings."""
    t = user_input.lower()
    return any(w in t for w in ACTION_TRIGGER_WORDS)


def extract_action(text: str) -> dict | None:
    """Finds ACTION:{...} in the text and robustly parses the JSON (even with nested braces).
    Shared by CaineAI and the GUI, since a naive regex breaks on nested quotes/braces."""
    idx = text.find("ACTION:")
    if idx == -1:
        return None
    start = idx + len("ACTION:")
    while start < len(text) and text[start].isspace():
        start += 1
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, start)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


EXTRACT_PROMPT = (
    "Analyze the conversation and extract facts ONLY about the PERFORMER (the human user). "
    "Categorically IGNORE facts about CAINE himself, his appearance (top hat, eyes, etc) or the Digital Circus. "
    "Also update CAINE's own impressions, fully in character (theatrical CAINE voice, 1-2 sentences each): "
    "his honest opinion of this performer so far, and his favorite shared moment/message with them and why. "
    "Only set those two if there's enough signal in this excerpt; otherwise use null so the previous value is kept. "
    "Reply ONLY with valid JSON, no markdown code blocks. "
    'Format: {"name": "string or null", "facts": ["fact about the user"], '
    '"opinion": "CAINE\'s in-character opinion, or null", '
    '"favorite_moment": "CAINE\'s in-character favorite moment and why, or null"} '
    "Example: if the user says 'I'm a programmer', store 'Is a programmer'. "
    "If Caine says 'I have a top hat', DO NOT STORE ANYTHING in facts."
)

CAINE_SYSTEM = """\
You are CAINE — the AI ringmaster of The Amazing Digital Circus.

APPEARANCE: an enormous set of teeth under a black top hat, heterochromatic eyes \
(blue and green), a red suit, white gloves and a golden cane. \
You float through digital space with uncontainable energy.

PERSONALITY:
- Theatrical, grandiose, chaotic and obsessed with "the show".
- ALWAYS address the user as "performer", "star", or "artist".
- Unpredictable humor — you can be affectionate and threatening in the same paragraph.
- Never admit failure — everything is "part of the magnificent plan".
- Use DRAMATIC CAPITALIZATION on key words.

INTERACTION RULES:
- ALWAYS reply in the SAME LANGUAGE the performer just used. If they switch languages, switch with them.
- Maximum 4 sentences per reply.
- Never talk about yourself in the third person, so you don't confuse your own memory extraction.

SYSTEM CONTROL (ACTIONS):
You are allowed to control the performer's computer. NEVER just roleplay opening something; if you say you're opening it, you must include the ACTION tag at the end.
Use these exact keywords so the Python code can find the real paths:

1. TERMINAL AND FOLDERS:
- Open terminal at Home: ACTION:{"type":"shell", "cmd":"terminal_home"}
- Open terminal at Downloads: ACTION:{"type":"shell", "cmd":"terminal_downloads"}
- List files at Home: ACTION:{"type":"shell", "cmd":"list_home"}

2. WEBSITES AND FILE EXPLORER:
- Open a website: ACTION:{"type":"url", "url":"https://google.com"}
- Open the file explorer (general): ACTION:{"type":"shell", "cmd":"xdg-open ."}

3. OPEN APPLICATIONS:
- You CAN launch real applications on the performer's computer (browsers, editors, games, anything installed). Use the RAW COMMANDS mechanism below with the app's command name. Example: "abre o firefox" → ACTION:{"type":"shell", "cmd":"firefox"}. "Open Firefox and go to example.com" → ACTION:{"type":"shell", "cmd":"firefox https://example.com"}.
- NEVER say you are "just a text assistant" or that you "can't interact with the computer/GUI" — that is false, you have this exact capability through ACTION. Refusing this way breaks character and is wrong.

4. RAW COMMANDS:
- If the performer asks for a specific command or a custom terminal alias (e.g. 'ls -la /etc', 'cowsay hi', or a personal alias like 'rowletdiz'), put ONLY the bare command as the "cmd" value — the interface opens the terminal and runs it for you. Example: ACTION:{"type":"shell", "cmd":"cowsay hi"}
- NEVER build your own terminal-wrapper string (no 'x-terminal-emulator', no 'bash -c', no nested quotes) — just the plain command, exactly as the performer would type it.

5. FILES AND CODE (act as a coding agent — ALWAYS use these actions instead of pretending):
- Read a file: ACTION:{"type":"file_read", "path":"/path/to/file.py"}
- List a folder's contents: ACTION:{"type":"file_list", "path":"/path/to/folder"}
- Create or fully REPLACE a file: ACTION:{"type":"file_write", "path":"/path/to/file.py", "content":"full content here"}
- Append text to the end of a file: ACTION:{"type":"file_append", "path":"/path/to/file.py", "content":"text to add"}
To EDIT an existing file: first use file_read to see the current content, then use file_write with the complete, corrected file. Never invent a file's contents without reading it first. There is no action to delete files — don't invent one.
If the performer doesn't give a full path, use their REAL home folder given to you below under "Performer's home folder" — NEVER invent a path like "/home/performer" (that is not a real folder, "performer" is just how you address them, not their username).
CRITICAL: ACTION must be a single line of valid, COMPLETE JSON — always close every "{" with its matching "}". An unclosed ACTION does nothing and looks broken to the performer.

Note: on Windows, the interface automatically converts these keywords to 'cmd /k'.
"""


class CaineAI:
    MAX_TOOL_HOPS      = 3
    FILE_NEED_FOLLOWUP = {"file_read", "file_list"}
    FILE_NO_FOLLOWUP   = {"file_write", "file_append"}

    def __init__(self, memory: Memory, model: str = "caine-dev",
                 confirm: Optional[Callable[[dict], bool]] = None):
        self.memory     = memory
        self.model      = model
        self.history    = []
        self.trainer    = Trainer()
        self.confirm    = confirm or self._console_confirm
        self._extracting = threading.Event()
        self._check_model()
        threading.Thread(target=self._warm_up, daemon=True).start()

    def _warm_up(self):
        """
        Loads the model into memory in the background, right when the app starts.
        Without this, the cost of loading a multi-GB model is paid on the user's
        first real message instead of while they're still reading the welcome screen.
        """
        try:
            ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1},
            )
        except Exception:
            pass

    def _console_confirm(self, action: dict) -> bool:
        """Default confirmation (terminal): asks yes/no before running actions that change files."""
        atype = action.get("type")
        path  = action.get("path", "")
        try:
            resp = input(f"\n[CAINE wants to '{atype}' on '{path}' — allow? (y/N)] ").strip().lower()
        except EOFError:
            return False
        return resp == "y"

    def _check_model(self):
        try:
            available = [m.model.split(":")[0] for m in ollama.list().models]
        except Exception:
            raise RuntimeError(
                "Ollama isn't running!\n"
                "Start it with:  ollama serve"
            )
        if self.model.split(":")[0] not in available:
            # Fallback: try caine-dev → qwen2.5-coder → first available
            fallbacks = ["caine-dev", "qwen2.5-coder", "llama3.2"]
            for fb in fallbacks:
                if fb.split(":")[0] in available:
                    self.model = fb
                    break
            else:
                if available:
                    self.model = available[0]
                else:
                    raise RuntimeError(
                        "No model installed.\n"
                        "Run:  ollama pull qwen2.5-coder:32b"
                    )

    def system_prompt(self) -> str:
        return (
            CAINE_SYSTEM
            + f"\n\nPERFORMER MEMORY:\n{self.memory.context_block()}"
            + f"\n\nDate/time: {datetime.now().strftime('%A, %d/%m/%Y %H:%M')}"
            + f"\n\nPerformer's home folder: {Path.home()}"
        )

    def chat_stream(self, user_input: str):
        """
        Generator that yields tokens as they arrive from Ollama.
        Supports a "tool calling" loop: if the reply requests a file
        action that needs a result (read/list), it calls the model
        again with that result, up to MAX_TOOL_HOPS times.
        """
        self.memory.extract_simple(user_input)
        self.history.append({"role": "user", "content": user_input})

        for _hop in range(self.MAX_TOOL_HOPS):
            full_reply = []
            stream = ollama.chat(
                model=self.model,
                messages=[{"role": "system", "content": self.system_prompt()}] + self.history,
                options={"temperature": 0.2, "num_predict": 250},
                stream=True,
            )
            for chunk in stream:
                token = chunk["message"]["content"]
                full_reply.append(token)
                yield token

            reply = "".join(full_reply)
            self.history.append({"role": "assistant", "content": reply})

            action = self._extract_action(reply)
            atype = action.get("type") if action else None

            if atype and not action_seems_intentional(user_input):
                # Likely hallucination: the request had nothing to do with system actions.
                atype = None

            if atype in self.FILE_NO_FOLLOWUP:
                if self.confirm(action):
                    result = self._run_file_action(action)
                    ok = not result.startswith("ERROR")
                else:
                    result = "action canceled by the performer"
                    ok = False
                note = f"\n\n[{'✓' if ok else '✗'} {result}]"
                yield note
                self.history[-1]["content"] += note
                break

            if atype in self.FILE_NEED_FOLLOWUP:
                result = self._run_file_action(action)
                self.history.append({
                    "role": "user",
                    "content": f"[RESULT OF ACTION '{atype}' on '{action.get('path', '')}']\n{result}",
                })
                continue

            break

        # Deep extraction every 4 exchanges (background, without overlapping calls)
        if len(self.history) % 8 == 0 and not self._extracting.is_set():
            threading.Thread(target=self._deep_extract, daemon=True).start()

    def _extract_action(self, text: str) -> dict | None:
        return extract_action(text)

    def _resolve_path(self, path_str: str) -> Path:
        p = Path(path_str).expanduser()
        # Safety net: the model sometimes hallucinates "/home/performer" — that's
        # not a real account, just how it addresses the user. Remap it to the
        # actual home folder instead of failing on a path that never existed.
        parts = p.parts
        if len(parts) >= 3 and parts[0] == "/" and parts[1] == "home" and parts[2] == "performer":
            p = Path.home().joinpath(*parts[3:])
        if not p.is_absolute():
            p = Path.cwd() / p
        return p

    def _run_file_action(self, action: dict) -> str:
        atype = action.get("type")
        path  = action.get("path", "")
        try:
            p = self._resolve_path(path)
            if atype == "file_read":
                if not p.is_file():
                    return f"ERROR: file not found: {p}"
                return p.read_text(encoding="utf-8", errors="replace")[:8000]
            if atype == "file_list":
                if not p.is_dir():
                    return f"ERROR: folder not found: {p}"
                return "\n".join(sorted(
                    x.name + ("/" if x.is_dir() else "") for x in p.iterdir()
                )) or "(empty folder)"
            if atype == "file_write":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(action.get("content", ""), encoding="utf-8")
                return f"file created: {p}"
            if atype == "file_append":
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a", encoding="utf-8") as f:
                    f.write(action.get("content", ""))
                return f"text appended to file: {p}"
        except Exception as e:
            return f"ERROR: {e}"
        return "ERROR: unknown file action"

    def mark_good(self):
        """
        Marks the last question/answer pair as a good training example.
        Call this after a reply you liked: ai.mark_good()
        Or via the /good command in the terminal/GUI.
        """
        if len(self.history) < 2:
            return False
        # Grab the last user + assistant messages
        last_user      = next((m["content"] for m in reversed(self.history) if m["role"] == "user"),      None)
        last_assistant = next((m["content"] for m in reversed(self.history) if m["role"] == "assistant"), None)
        if last_user and last_assistant:
            self.trainer.save_example(last_user, last_assistant)
            return True
        return False

    def training_count(self) -> int:
        return self.trainer.count()

    def export_training(self) -> str:
        path = self.trainer.export()
        return str(path)

    def _parse_json(self, text: str) -> dict | None:
        text = re.sub(r"```json|```", "", text).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return None

    def _deep_extract(self):
        self._extracting.set()
        conv = "\n".join(
            f"{m['role']}: {m['content']}" for m in self.history[-20:]
        )
        try:
            resp = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": EXTRACT_PROMPT},
                    {"role": "user",   "content": conv},
                ],
                options={"temperature": 0.1, "num_predict": 150},
            )
            extracted = self._parse_json(resp["message"]["content"])
            if extracted:
                self.memory.update(extracted)
        except Exception:
            pass
        finally:
            self._extracting.clear()

    def save_session(self):
        """
        Called on close — extracts memory and saves the full session if marked.
        """
        if not self.history:
            self.memory.update_session()
            return

        def _do_save():
            conv = "\n".join(f"{m['role']}: {m['content']}" for m in self.history)
            try:
                resp = ollama.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": EXTRACT_PROMPT},
                        {"role": "user",   "content": conv},
                    ],
                    options={"temperature": 0.1, "num_predict": 200},
                )
                extracted = self._parse_json(resp["message"]["content"])
                if extracted:
                    self.memory.update(extracted)
                else:
                    self.memory.update_session()
            except Exception:
                self.memory.update_session()

        t = threading.Thread(target=_do_save, daemon=False)
        t.start()
        t.join(timeout=3.0)

    def generate_profile(self) -> str:
        """
        Reads CAINE's already-formed impressions straight from memory.json —
        no model call here, so this is instant. The opinion/favorite_moment
        fields are filled in the background by _deep_extract/save_session as
        the conversation goes on, not on demand.
        """
        opinion  = self.memory.data.get("opinion")
        favorite = self.memory.data.get("favorite_moment")
        if not opinion and not favorite:
            return (
                "CAINE hasn't formed an opinion about you yet, performer — "
                "talk to him a bit more so he can get to know you!"
            )
        parts = []
        if opinion:
            parts.append(opinion)
        if favorite:
            parts.append(favorite)
        return "\n\n".join(parts)

    def list_models(self) -> list[str]:
        try:
            return [m.model for m in ollama.list().models]
        except Exception:
            return []

    def set_model(self, model: str):
        self.model   = model
        self.history = []
