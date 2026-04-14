import sys
import os
import subprocess
import webbrowser
import platform
import threading
import re
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from ai import CaineAI
from memory import Memory
from tts import TTS
from stt import STT

class MessageBubble(QFrame):
    def __init__(self, sender, text, is_caine=True):
        super().__init__()
        layout = QVBoxLayout(self)
        name_lbl = QLabel(sender.upper())
        name_lbl.setStyleSheet(f"color: {'#e8c44a' if is_caine else '#7b4fd4'}; font-weight: bold; font-size: 10px; background: transparent;")
        msg_lbl = QLabel(text)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("color: #f0ead6; font-size: 14px; background: transparent; border: none;")
        layout.addWidget(name_lbl)
        layout.addWidget(msg_lbl)
        bg = "#121225" if is_caine else "#1a1a30"
        self.setStyleSheet(f"QFrame {{ background-color: {bg}; border-radius: 12px; padding: 12px; margin: 5px; border: 1px solid rgba(255,255,255,0.05); }}")

class CaineGUI(QMainWindow):
    response_received = pyqtSignal(str)
    status_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.memory = Memory()
        self.ai = CaineAI(self.memory)
        self.tts = TTS()
        self.stt = STT(on_state=self.update_status_bar)
        
        self.setWindowTitle("CAINE — Digital Circus OS")
        self.resize(1000, 800)
        self.init_ui()
        self.apply_styles()
        
        self.response_received.connect(self.add_caine_message)
        self.status_updated.connect(self.update_status_bar)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setObjectName("sidebar")
        s_layout = QVBoxLayout(sidebar)
        avatar = QLabel("🎭")
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_layout.addWidget(avatar)
        self.status_lbl = QLabel("● PRONTO")
        self.status_lbl.setObjectName("status-pill")
        s_layout.addWidget(self.status_lbl)
        s_layout.addStretch()
        layout.addWidget(sidebar)

        # Chat
        chat_area = QWidget()
        chat_area.setObjectName("chat-area")
        r_layout = QVBoxLayout(chat_area)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().setStyleSheet("background-color: #080810;")
        self.container = QWidget()
        self.chat_layout = QVBoxLayout(self.container)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.container)
        r_layout.addWidget(self.scroll)

        # Input
        input_box = QFrame()
        i_layout = QHBoxLayout(input_box)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Pede para abrir o terminal ou listar pastas...")
        self.input_field.returnPressed.connect(self.send_message)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(45, 45)
        i_layout.addWidget(self.input_field)
        i_layout.addWidget(self.mic_btn)
        r_layout.addWidget(input_box)
        layout.addWidget(chat_area)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, #chat-area, #chat-inner, QScrollArea { background-color: #080810; border: none; }
            #sidebar { background-color: #0d0d1a; border-right: 1px solid #1a1a2e; }
            #avatar { font-size: 60px; margin: 30px; }
            #status-pill { color: #2dd4c8; background: rgba(45, 212, 200, 0.1); border-radius: 10px; padding: 5px; margin: 10px 40px; text-align: center; }
            QLineEdit { background: #151525; border: 1px solid #2a2a40; color: white; padding: 12px; border-radius: 8px; }
            QPushButton { background: #7b4fd4; border-radius: 22px; color: white; border: none; }
        """)

    def execute_action(self, text):
        match = re.search(r'ACTION:(\{.*?\})', text)
        if not match: return
        
        try:
            data = json.loads(match.group(1))
            cmd_type = data.get("cmd")
            home = str(Path.home())
            downloads = str(Path.home() / "Transferências") # Linux PT
            if not os.path.exists(downloads):
                downloads = str(Path.home() / "Downloads") # Fallback

            final_cmd = ""
            
            # Lógica de tradução de comandos "inventados" para reais
            if cmd_type == "terminal_home":
                final_cmd = f"x-terminal-emulator --working-directory='{home}'" if platform.system() != "Windows" else f"start cmd /K cd {home}"
            
            elif cmd_type == "terminal_downloads":
                final_cmd = f"x-terminal-emulator --working-directory='{downloads}'" if platform.system() != "Windows" else f"start cmd /K cd {downloads}"
            
            elif cmd_type == "list_home":
                if platform.system() != "Windows":
                    final_cmd = f"x-terminal-emulator -e 'bash -c \"ls -la {home}; exec bash\"'"
                else:
                    final_cmd = f"start cmd /K dir {home}"
            
            # Se não for uma keyword, tenta executar o comando bruto
            else:
                final_cmd = data.get("cmd", "")

            if final_cmd:
                subprocess.Popen(final_cmd, shell=True)
                
        except Exception as e:
            print(f"Erro na ação: {e}")

    def process_ai(self, text):
        try:
            reply = self.ai.chat(text)
            self.execute_action(reply)
            clean_reply = re.sub(r'ACTION:\{.*?\}', '', reply).strip()
            self.response_received.emit(clean_reply)
            if self.tts.available: self.tts.speak(clean_reply)
        except Exception as e:
            self.response_received.emit(f"Erro: {e}")

    def send_message(self):
        text = self.input_field.text().strip()
        if not text: return
        if text.startswith("/"):
            self.handle_commands(text)
        else:
            self.add_user_message(text)
            threading.Thread(target=self.process_ai, args=(text,), daemon=True).start()
        self.input_field.clear()

    def handle_commands(self, text):
        if "/memoria" in text: self.add_caine_message(self.memory.show())
        if "/apagar" in text: self.memory.clear(); self.add_caine_message("Memória apagada!")
        if "/sair" in text: self.ai.save_session(); self.close()

    def add_user_message(self, t):
        self.chat_layout.insertWidget(self.chat_layout.count()-1, MessageBubble("Tu", t, False))
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def add_caine_message(self, t):
        self.chat_layout.insertWidget(self.chat_layout.count()-1, MessageBubble("Caine", t, True))
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def update_status_bar(self, s): self.status_lbl.setText(s.upper())
    def start_voice_input(self):
        def _v():
            self.status_updated.emit("A ESCUTAR...")
            t = self.stt.listen()
            if t: self.process_ai(t)
            self.status_updated.emit("PRONTO")
        threading.Thread(target=_v, daemon=True).start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CaineGUI()
    win.show()
    sys.exit(app.exec())