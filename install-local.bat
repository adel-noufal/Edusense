@echo off
cd /d "%~dp0backend"
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
cd /d "%~dp0frontend"
npm install
