@echo off
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
  .venv\Scripts\python -m pip install --require-hashes -r requirements-lock.txt
)
start "" .venv\Scripts\pythonw builder\gambit_builder.py
