# 🎭 CAINE — The Amazing Digital Circus AI

IA terminal com personalidade do Caine, voz, memória persistente e músicas.

## Estrutura

```
caine/
├── main.py        ← entrada principal (corre isto)
├── ai.py          ← cérebro: chat com Ollama + extração de memória
├── memory.py      ← memória persistente em ~/.caine/memoria.json
├── tts.py         ← síntese de voz (espeak-ng / say / pyttsx3)
├── stt.py         ← reconhecimento de voz (sem spam ALSA)
└── requirements.txt
```

## Instalação

```bash
# 1. Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &          # noutro terminal
ollama pull llama3.2    # 2GB

# 2. Dependências de áudio (Linux)
sudo apt install espeak-ng portaudio19-dev python3-pyaudio

# 3. Pacotes Python
pip install -r requirements.txt

# 4. Arrancar
python main.py
```

## Comandos

| Comando | Ação |
|---|---|
| `/voz` | Liga/desliga microfone |
| `/mudo` | Liga/desliga TTS |
| `/memoria` | Mostra o que o Caine sabe sobre ti |
| `/apagar` | Apaga a memória |
| `/modelos` | Lista modelos Ollama instalados |
| `/modelo llama3.3` | Troca de modelo |
| `/limpar` | Limpa histórico da sessão |
| `/sair` | Guarda e sai |
"
