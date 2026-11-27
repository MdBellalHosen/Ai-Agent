@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 goto nopython
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist ".env" copy ".env.example" ".env" >nul
if not defined CI ".venv\Scripts\python.exe" main.py --install
echo.
echo Setup shesh. .env file e API key boshao, save koro, tarpor check.bat chalao.
echo Tarpor Desktop er Mira icon e double click koro, ba bolo "Hey Mira".
if defined CI exit /b 0
notepad .env
pause
exit /b 0

:nopython
echo Python 3.12 pawa jayni. PowerShell e chalao:
echo     winget install --id Python.Python.3.12
if not defined CI pause
exit /b 1

:fail
echo Setup hoyni. Upore error ta dekho.
if not defined CI pause
exit /b 1
