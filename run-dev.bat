@echo off
REM Run Aurora OS from the source code (for trying it out).
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
python run.py
