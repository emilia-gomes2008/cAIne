import sys
import os
import subprocess
import webbrowser
import platform
import threading
import re
import json
import html
from pathlib import Path

if getattr(sys, "frozen", False):
    # Running as a PyInstaller binary: source files live in a temp bundle dir
    # (onefile) or next to the executable (onedir), not under app/.. like in dev.
    _ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_ROOT))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame, QMessageBox,
    QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QFont

from core.ai import CaineAI, action_seems_intentional, extract_action
from core.memory import Memory
from audio.tts import TTS

ASSETS_DIR  = _ROOT / "assets"
AVATAR_PATH = ASSETS_DIR / "caine_avatar.png"

# Palette inspired by The Amazing Digital Circus
TADC_BLUE   = "#1f6fe8"
TADC_BLUE_D = "#123a8a"
TADC_RED    = "#e8312f"
TADC_RED_D  = "#9c1816"
TADC_YELLOW = "#ffd23f"
TADC_CREAM  = "#fff7e8"


def circular_pixmap(path: Path, size: int) -> QPixmap:
    """Crops the image into a circle, for use as a round avatar."""
    source = QPixmap(str(path))
    if source.isNull():
        return source
    source = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
    rounded = QPixmap(size, size)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path_circle = QPainterPath()
    path_circle.addEllipse(0, 0, size, size)
    painter.setClipPath(path_circle)
    x = (source.width() - size) // 2
    y = (source.height() - size) // 2
    painter.drawPixmap(-x, -y, source)
    painter.end()
    return rounded


def render_markdown_lite(text: str) -> str:
    """Turns ```lang\\ncode\\n``` fences into styled boxes (and `inline code`
    into a pill), so code shows up readable instead of literal backticks."""
    parts = re.split(r"```(?:\w+)?\n?(.*?)```", text, flags=re.DOTALL)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            code = html.escape(part.rstrip("\n"))
            out.append(
                '<pre style="background:#0c1f3f; color:#d8e8ff; padding:8px 10px; '
                'border-radius:8px; border:1px solid #ffd23f; '
                "font-family:Consolas,'Courier New',monospace; font-size:12px; "
                f'white-space:pre-wrap; margin:6px 0;">{code}</pre>'
            )
        else:
            escaped = html.escape(part)
            escaped = re.sub(
                r"`([^`]+)`",
                r'<code style="background:#0c1f3f; color:#ffd23f; padding:1px 5px; '
                r'border-radius:4px;">\1</code>',
                escaped,
            )
            out.append(escaped.replace("\n", "<br>"))
    return "".join(out)


class MessageBubble(QFrame):
    def __init__(self, sender, text, is_caine=True):
        super().__init__()
        layout = QVBoxLayout(self)
        name_lbl = QLabel(sender.upper())
        name_lbl.setStyleSheet(f"color: {TADC_YELLOW if is_caine else TADC_BLUE_D}; font-weight: bold; font-size: 10px; background: transparent; letter-spacing: 1px; border: none;")
        self.msg_lbl = QLabel()
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.msg_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_color = TADC_CREAM if is_caine else "#0c2f6b"
        self.msg_lbl.setStyleSheet(f"color: {text_color}; font-size: 14px; background: transparent; border: none;")
        self.set_text(text)
        layout.addWidget(name_lbl)
        layout.addWidget(self.msg_lbl)
        if is_caine:
            bg, border = TADC_RED_D, TADC_YELLOW
        else:
            bg, border = TADC_CREAM, TADC_BLUE
        self.setStyleSheet(
            f"background-color: {bg}; border-radius: 16px; padding: 12px; "
            f"margin: 6px; border: 2px solid {border};"
        )

    def set_text(self, text: str):
        self.msg_lbl.setText(render_markdown_lite(text))

class CaineGUI(QMainWindow):
    response_received = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    stream_started = pyqtSignal()
    stream_token = pyqtSignal(str)
    stream_finished = pyqtSignal()
    confirm_request = pyqtSignal(dict, object)
    warm_up_done = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.memory = Memory()
        self.ai = CaineAI(self.memory, confirm=self._confirm_action)
        self.confirm_request.connect(self._show_confirm_dialog)
        self.tts = TTS()
        self.tts_enabled = self.tts.available
        self._stream_bubble = None
        self._stream_text = ""
        self._last_user_input = ""

        self.setWindowTitle("cAIne")
        self.resize(1000, 800)
        self.init_ui()
        self.apply_styles()

        self.response_received.connect(self.add_caine_message)
        self.status_updated.connect(self.update_status_bar)
        self.stream_started.connect(self._start_stream_bubble)
        self.stream_token.connect(self._append_stream_token)
        self.stream_finished.connect(self._finish_stream)
        self.warm_up_done.connect(self._on_warm_up_done)
        threading.Thread(target=self._wait_for_warm_up, daemon=True).start()

    def _wait_for_warm_up(self):
        self.ai.ready.wait()
        self.warm_up_done.emit()

    def _on_warm_up_done(self):
        self.content_stack.setCurrentIndex(1)
        self.input_field.setEnabled(True)
        self.input_field.setPlaceholderText("Talk to CAINE, performer...")
        self.input_field.setFocus()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar — the circus stage
        sidebar = QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setObjectName("sidebar")
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(20, 30, 20, 20)

        avatar_lbl = QLabel()
        avatar_lbl.setObjectName("avatar")
        pix = circular_pixmap(AVATAR_PATH, 160)
        if not pix.isNull():
            avatar_lbl.setPixmap(pix)
        else:
            avatar_lbl.setText("🎭")
        avatar_lbl.setFixedSize(168, 168)
        avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_layout.addWidget(avatar_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel("CAINE")
        title_lbl.setObjectName("title")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Ringmaster\nof the Digital Circus")
        subtitle_lbl.setObjectName("subtitle")
        subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_layout.addWidget(subtitle_lbl)

        zigzag = QFrame()
        zigzag.setObjectName("zigzag")
        zigzag.setFixedHeight(10)
        s_layout.addWidget(zigzag)

        self.status_lbl = QLabel(f"● {self.ai.model}")
        self.status_lbl.setObjectName("status-pill")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_layout.addWidget(self.status_lbl)

        self.profile_btn = QPushButton("👤 Profile")
        self.profile_btn.setObjectName("profile-btn")
        self.profile_btn.clicked.connect(self.show_profile)
        s_layout.addWidget(self.profile_btn)

        self.tts_btn = QPushButton()
        self.tts_btn.setObjectName("profile-btn")
        self.tts_btn.clicked.connect(self.toggle_tts)
        self._refresh_tts_btn()
        s_layout.addWidget(self.tts_btn)

        s_layout.addStretch()
        layout.addWidget(sidebar)

        # Chat — the circus ring
        chat_area = QWidget()
        chat_area.setObjectName("chat-area")
        r_layout = QVBoxLayout(chat_area)
        r_layout.setContentsMargins(20, 20, 20, 20)

        top_zigzag = QFrame()
        top_zigzag.setObjectName("zigzag")
        top_zigzag.setFixedHeight(8)
        r_layout.addWidget(top_zigzag)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("scroll")
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container.setObjectName("chat-inner")
        self.chat_layout = QVBoxLayout(self.container)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.container)

        loading_widget = QWidget()
        loading_widget.setObjectName("loading-screen")
        loading_layout = QVBoxLayout(loading_widget)
        loading_lbl = QLabel("🎪 CAINE is warming up for the show...")
        loading_lbl.setObjectName("loading-label")
        loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addStretch()
        loading_layout.addWidget(loading_lbl)
        loading_layout.addStretch()

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(loading_widget)  # index 0: loading
        self.content_stack.addWidget(self.scroll)      # index 1: chat
        r_layout.addWidget(self.content_stack)

        # Input
        input_box = QFrame()
        input_box.setObjectName("input-box")
        i_layout = QHBoxLayout(input_box)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("CAINE is warming up...")
        self.input_field.setEnabled(False)
        self.input_field.returnPressed.connect(self.send_message)
        i_layout.addWidget(self.input_field)
        r_layout.addWidget(input_box)
        layout.addWidget(chat_area)

    def apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {TADC_BLUE_D}; }}
            #chat-area {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {TADC_BLUE}, stop:1 {TADC_BLUE_D});
            }}
            #scroll, #chat-inner {{ background: transparent; border: none; }}
            #sidebar {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {TADC_RED}, stop:1 {TADC_RED_D});
                border-right: 4px solid {TADC_YELLOW};
            }}
            #avatar {{
                font-size: 60px;
                border: 5px solid {TADC_YELLOW};
                border-radius: 84px;
                background-color: {TADC_CREAM};
            }}
            #title {{
                color: {TADC_CREAM};
                font-size: 26px;
                font-weight: 900;
                letter-spacing: 4px;
                margin-top: 14px;
            }}
            #subtitle {{
                color: {TADC_YELLOW};
                font-size: 11px;
                font-style: italic;
                margin-bottom: 10px;
            }}
            #zigzag {{
                background: repeating-linear-gradient(135deg,
                    {TADC_YELLOW} 0px, {TADC_YELLOW} 8px,
                    transparent 8px, transparent 16px);
                border-radius: 4px;
                margin: 6px 0;
            }}
            #status-pill {{
                color: {TADC_BLUE_D};
                background: {TADC_YELLOW};
                border-radius: 10px;
                padding: 6px;
                margin: 10px 20px;
                font-weight: bold;
                text-align: center;
            }}
            #loading-label {{
                color: {TADC_CREAM};
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
            }}
            #input-box {{ background: transparent; margin-top: 10px; }}
            QLineEdit {{
                background: {TADC_CREAM};
                border: 3px solid {TADC_YELLOW};
                color: {TADC_BLUE_D};
                padding: 12px;
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton#profile-btn {{
                background: {TADC_YELLOW};
                color: {TADC_BLUE_D};
                border-radius: 10px;
                border: none;
                padding: 8px;
                margin: 4px 20px;
                font-weight: bold;
            }}
            QPushButton#profile-btn:hover {{ background: {TADC_CREAM}; }}
            QPushButton#profile-btn:disabled {{ background: rgba(255, 210, 63, 0.5); color: {TADC_BLUE_D}; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; }}
            QScrollBar::handle:vertical {{ background: {TADC_YELLOW}; border-radius: 5px; }}
        """)

    def show_profile(self):
        """Reads CAINE's stored opinion straight from memory.json — instant, no model call."""
        text = self.ai.generate_profile()
        box = QMessageBox(self)
        box.setWindowTitle("CAINE's view of you")
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def toggle_tts(self):
        self.tts_enabled = not self.tts_enabled
        self._refresh_tts_btn()

    def _refresh_tts_btn(self):
        if not self.tts.available:
            self.tts_btn.setText("🔇 No TTS available")
            self.tts_btn.setEnabled(False)
        else:
            self.tts_btn.setText("🔊 Speech: On" if self.tts_enabled else "🔇 Speech: Off")

    def _confirm_action(self, action: dict) -> bool:
        """Called by CaineAI (on a background thread) before writing/changing files."""
        result = {}
        event = threading.Event()
        self.confirm_request.emit(action, (result, event))
        event.wait()
        return result.get("ok", False)

    def _show_confirm_dialog(self, action, holder):
        result, event = holder
        atype = action.get("type")
        path  = action.get("path", "")
        reply = QMessageBox.question(
            self, "Confirm CAINE action",
            f"CAINE wants to run '{atype}' on '{path}'.\nAllow it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        result["ok"] = reply == QMessageBox.StandardButton.Yes
        event.set()

    def _open_terminal(self, cwd: str):
        """Opens a terminal at cwd using argument lists — no shell string nesting needed."""
        if platform.system() != "Windows":
            subprocess.Popen(["x-terminal-emulator", "--working-directory", cwd])
        else:
            subprocess.Popen(f'start cmd /K cd {cwd}', shell=True)

    def _run_in_terminal(self, command: str):
        """Runs a raw command in a new terminal. Passed as argv, not a shell string,
        so the command never needs to be quote-escaped by the model or by us."""
        if platform.system() != "Windows":
            subprocess.Popen(["x-terminal-emulator", "-e", "bash", "-c", f"{command}; exec bash"])
        else:
            subprocess.Popen(f'start cmd /K {command}', shell=True)

    def execute_action(self, text):
        action = extract_action(text)
        if not action or action.get("type") not in ("shell", "url"):
            return
        if not action_seems_intentional(self._last_user_input):
            return  # likely hallucination: the request had nothing to do with system actions

        if action.get("type") == "url":
            url = action.get("url", "")
            reply = QMessageBox.question(
                self, "Confirm CAINE action",
                f"CAINE wants to open a website:\n{url}\nAllow it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes and url:
                webbrowser.open(url)
            return

        try:
            cmd_type = action.get("cmd", "")
            reply = QMessageBox.question(
                self, "Confirm CAINE action",
                f"CAINE wants to run a system command:\n{cmd_type}\nAllow it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            home = str(Path.home())
            downloads = str(Path.home() / "Downloads")
            if not os.path.exists(downloads):
                downloads = str(Path.home() / "Transferências")  # localized fallback

            # Translates "invented" command keywords into real commands
            if cmd_type == "terminal_home":
                self._open_terminal(home)
            elif cmd_type == "terminal_downloads":
                self._open_terminal(downloads)
            elif cmd_type == "list_home":
                self._run_in_terminal(f"ls -la '{home}'")
            elif cmd_type:
                # Anything else is treated as a raw command/alias the performer asked for.
                self._run_in_terminal(cmd_type)

        except Exception as e:
            print(f"Action error: {e}")

    def process_ai(self, text):
        self._last_user_input = text
        try:
            self.stream_started.emit()
            for token in self.ai.chat_stream(text):
                self.stream_token.emit(token)
            self.stream_finished.emit()
        except Exception as e:
            self.response_received.emit(f"Error: {e}")

    def _start_stream_bubble(self):
        at_bottom = self._is_at_bottom()
        self._stream_text = ""
        self._stream_bubble = MessageBubble("Caine", "", True)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, self._stream_bubble)
        if at_bottom:
            QTimer.singleShot(50, self._scroll_bottom)

    def _append_stream_token(self, token):
        # Only follow the stream down if the performer was already at the bottom —
        # otherwise scrolling up to re-read something keeps getting yanked back down.
        at_bottom = self._is_at_bottom()
        self._stream_text += token
        self._stream_bubble.set_text(self._stream_text)
        if at_bottom:
            QTimer.singleShot(0, self._scroll_bottom)

    def _finish_stream(self):
        full = self._stream_text
        self.execute_action(full)
        clean_reply = re.sub(r'ACTION:\{.*?\}', '', full, flags=re.DOTALL).strip()
        # Some models cut the ACTION JSON short and never close the braces — extract_action()
        # already refuses to run a malformed action, but the regex above can't strip it
        # since there's no closing "}" to match. Hide the broken tail instead of showing raw JSON.
        if "ACTION:" in clean_reply:
            clean_reply = clean_reply.split("ACTION:")[0].strip()
        # Some (especially weaker) models reply with the ACTION tag and nothing else —
        # once it's stripped, only the technical [✓/✗ ...] note is left, which can look
        # like the reply vanished. Make sure there's always something readable above it.
        if clean_reply.startswith("[") and clean_reply.endswith("]"):
            clean_reply = f"Done!\n\n{clean_reply}"
        self._stream_bubble.set_text(clean_reply)
        if self.tts_enabled and self.tts.available:
            self.tts.speak(clean_reply)

    def _scroll_bottom(self):
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _is_at_bottom(self) -> bool:
        bar = self.scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 60

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
        if "/memory" in text: self.add_caine_message(self.memory.show())
        if "/forget" in text: self.memory.clear(); self.add_caine_message("Memory cleared!")
        if "/quit" in text: self.ai.save_session(); self.close()

    def add_user_message(self, t):
        self.chat_layout.insertWidget(self.chat_layout.count()-1, MessageBubble("You", t, False))
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def add_caine_message(self, t):
        at_bottom = self._is_at_bottom()
        self.chat_layout.insertWidget(self.chat_layout.count()-1, MessageBubble("Caine", t, True))
        if at_bottom:
            QTimer.singleShot(50, self._scroll_bottom)

    def update_status_bar(self, s):
        self.status_lbl.setText(s if s.startswith("●") else s.upper())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CaineGUI()
    win.show()
    sys.exit(app.exec())
