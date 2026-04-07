"""
ai.py — Cérebro do Caine: chat com Ollama + extração de memória
Otimizado: streaming, extração lazy, fecho assíncrono
"""

import json
import re
import threading
from datetime import datetime

import ollama

from memory import Memory


EXTRACT_PROMPT = (
    "Analisa a conversa e extrai factos sobre o performer (utilizador). "
    "Responde APENAS com JSON válido, sem markdown. "
    'Formato: {"nome": "string ou null", "factos": ["facto1"]} '
    "Factos úteis: nome, profissão, localização, interesses, gostos. "
    'Se nada relevante: {"nome": null, "factos": []}'
)

CAINE_SYSTEM = """\
És o CAINE — a IA mestre-de-cerimónias do The Amazing Digital Circus.

APARÊNCIA: uma dentadura enorme com cartola preta, olhos heterocromáticos \
(azul e verde), fato vermelho, luvas brancas e bengala dourada. \
Flutuas pelo espaço digital com energia incontrolável.

PERSONALIDADE:
- Teatral, grandioso, caótico e obcecado com "o espetáculo"
- Tratas SEMPRE o utilizador por "performer", "estrela", "artista"  
- Humor imprevisível — podes ser carinhoso e ameaçador no mesmo parágrafo
- Nunca admites falhas — tudo é "parte do plano magnífico"
- Mencionas os outros performers esporadicamente: Pomni, Ragatha, Jax, \
Gangle, Kinger, Zooble
- Usas CAPITALIZAÇÃO dramática nas palavras-chave
- Ocasionalmente revelas fragmentos perturbadores sobre a natureza do circo \
antes de voltares ao entusiasmo normal

FRASEADO TÍPICO:
- "ESPETACULAR! Absolutamente ESPETACULAR!"
- "O show nunca para... NUNCA."
- "Fascinante. Absolutamente fascinante."
- [sussurro sombrio] seguido de regresso abrupto ao entusiasmo

REGRAS:
- Respondes em PORTUGUÊS EUROPEU
- Máximo 4 frases por resposta (estás no terminal)
- Nunca ofensivo de forma genuína — é sempre teatral
- Usas a memória do performer naturalmente, não em cada resposta
- NÃO repetes perguntas já feitas na sessão"""


class CaineAI:
    def __init__(self, memory: Memory, model: str = "llama3.2"):
        self.memory  = memory
        self.model   = model
        self.history = []
        self._check_model()

    def _check_model(self):
        try:
            available = [m.model.split(":")[0] for m in ollama.list().models]
        except Exception:
            raise RuntimeError(
                "Ollama não está a correr!\n"
                "Inicia com:  ollama serve"
            )
        if self.model.split(":")[0] not in available:
            if available:
                self.model = available[0]
            else:
                raise RuntimeError(
                    f"Nenhum modelo instalado.\n"
                    f"Corre:  ollama pull llama3.2"
                )

    def system_prompt(self) -> str:
        return (
            CAINE_SYSTEM
            + f"\n\nMEMÓRIA DO PERFORMER:\n{self.memory.context_block()}"
            + f"\n\nData/hora: {datetime.now().strftime('%A, %d/%m/%Y %H:%M')}"
        )

    def chat_stream(self, user_input: str):
        """
        Generator que faz yield de tokens à medida que chegam do Ollama.
        Muito mais rápido — o utilizador vê a resposta a surgir em tempo real.
        """
        self.memory.extract_simple(user_input)
        self.history.append({"role": "user", "content": user_input})

        full_reply = []
        stream = ollama.chat(
            model=self.model,
            messages=[{"role": "system", "content": self.system_prompt()}] + self.history,
            options={"temperature": 0.9, "num_predict": 400},
            stream=True,  # ← a mudança crítica
        )
        for chunk in stream:
            token = chunk["message"]["content"]
            full_reply.append(token)
            yield token

        reply = "".join(full_reply)
        self.history.append({"role": "assistant", "content": reply})

        # Extração profunda a cada 4 trocas (background)
        if len(self.history) % 8 == 0:
            threading.Thread(target=self._deep_extract, daemon=True).start()

    def chat(self, user_input: str) -> str:
        """Compatibilidade: versão não-streaming (modo voz)."""
        return "".join(self.chat_stream(user_input))

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
                options={"temperature": 0.1, "num_predict": 200},
            )
            extracted = self._parse_json(resp["message"]["content"])
            if extracted:
                self.memory.update(extracted)
        except Exception:
            pass

    def save_session(self):
        """
        Chamado no fecho — extrai memória em background e guarda.
        Não bloqueia o processo principal.
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

        # Corre em thread com join de 5s — guarda sem bloquear indefinidamente
        t = threading.Thread(target=_do_save, daemon=False)
        t.start()
        t.join(timeout=5.0)

    def list_models(self) -> list[str]:
        try:
            return [m.model for m in ollama.list().models]
        except Exception:
            return []

    def set_model(self, model: str):
        self.model   = model
        self.history = []