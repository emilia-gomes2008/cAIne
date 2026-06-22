@echo off
REM Builds a standalone Windows .exe for the CAINE GUI.
REM Run this ON Windows — PyInstaller does not cross-compile from Linux.
cd /d "%~dp0\.."

pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

pyinstaller --name CAINE --onefile --windowed --noconfirm ^
    --add-data "assets\caine_avatar.png;assets" ^
    app\gui.py
if errorlevel 1 exit /b 1

echo.
echo Done: dist\CAINE.exe
echo Ollama must still be installed and running separately on Windows (or
echo reachable over the network) — this .exe only bundles the Python app.
