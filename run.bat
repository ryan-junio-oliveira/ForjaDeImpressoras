@echo off
REM Forja de Impressoras - abre a janela desktop como Administrador
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel%==0 goto :run
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" 2>nul
exit /b
:run
python main.py --mode desktop
pause
