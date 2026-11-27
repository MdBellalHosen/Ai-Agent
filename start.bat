@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" echo Age setup.bat chalao.
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" main.py
pause
