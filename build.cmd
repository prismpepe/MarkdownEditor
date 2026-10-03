@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install -q -r requirements.txt
.venv\Scripts\python -m pytest -q
if errorlevel 1 exit /b 1
.venv\Scripts\python -m PyInstaller --noconfirm --onefile --windowed --name MarkdownEditor --add-data "ui.html;." --add-data "vendor;vendor" --add-data "format.js;." --add-data "find.js;." --add-data "printing.py;." --add-data "print.js;." mdeditor.py
echo.
echo dist\MarkdownEditor.exe
