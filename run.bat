@echo off
setlocal enabledelayedexpansion
REM =====================================================================
REM  Instalador de Impressoras — inicializador
REM
REM  uso:
REM    run.bat                 :: janela desktop (unico modo de uso)
REM    run.bat servidor        :: sobe o servidor local (desenvolvimento)
REM    run.bat scan [CIDR]     :: varredura pela linha de comando
REM    run.bat --help          :: ver todas as opcoes do CLI
REM
REM  Politica do app: interface SOMENTE na janela desktop.
REM  Nenhum fluxo abre o navegador do usuario.
REM =====================================================================
cd /d "%~dp0"

set "MODO=%~1"
if "%MODO%"=="" set "MODO=desktop"
if /i "%MODO%"=="--help" set "MODO=help"
if /i "%MODO%"=="-h" set "MODO=help"
if /i "%MODO%"=="browser" set "MODO=desktop"
if /i "%MODO%"=="navegador" set "MODO=desktop"
if /i "%MODO%"=="servidor" set "MODO=servidor"
if /i "%MODO%"=="server" set "MODO=servidor"
if /i "%MODO%"=="scan" set "MODO=scan"

if /i "%MODO%"=="help" goto :ajuda

REM ---------------------------------------------------------------------
REM  1) privilegio de administrador (necessario para instalar)
REM ---------------------------------------------------------------------
net session >nul 2>&1
if not %errorlevel%==0 (
  echo.
  echo  Solicitando elevacao de Administrador...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs" 2>nul
  if errorlevel 1 (
    echo  [ERRO] Elevacao cancelada. Sem Administrador nao e possivel instalar impressoras.
    pause
  )
  exit /b
)

REM ---------------------------------------------------------------------
REM  2) Python
REM ---------------------------------------------------------------------
set "PY="
python --version >nul 2>&1 && set "PY=python"
if "%PY%"=="" (
  py -3 --version >nul 2>&1 && set "PY=py -3"
)
if "%PY%"=="" (
  echo.
  echo  [ERRO] Python 3.10+ nao encontrado.
  echo         Instale em https://www.python.org/downloads/  (marque "Add to PATH")
  echo.
  pause
  exit /b 1
)

REM ---------------------------------------------------------------------
REM  3) modo
REM ---------------------------------------------------------------------
if /i "%MODO%"=="scan" goto :scan

if /i "%MODO%"=="servidor" goto :servidor

REM --- modo desktop (unico modo de uso): exige PySide6 (QtWebEngine) ---
%PY% -c "import PySide6.QtWebEngineWidgets" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [AVISO] PySide6/QtWebEngine ausente.
  echo          Instalando (pode levar alguns minutos)...
  %PY% -m pip install --quiet --disable-pip-version-check PySide6
  if errorlevel 1 (
    echo  [ERRO] Falha ao instalar o PySide6. Sem ele a janela nao abre.
    echo         Reinstale pelo instalador (ForjaDeImpressorasSetup.exe).
    pause
    exit /b 1
  )
)

echo.
echo  ============================================================
echo   Instalador de Impressoras — janela desktop
echo  ============================================================
echo.
%PY% main.py --mode desktop %*
goto :fim

:servidor
echo.
echo  ============================================================
echo   Instalador de Impressoras — servidor local
echo  ============================================================
echo.
%PY% main.py --mode server
goto :fim

:scan
echo.
echo  Varredura pela linha de comando...
echo.
shift
if "%1"=="" (
  %PY% main.py --scan
) else (
  %PY% main.py --scan %1
)
goto :fim

:ajuda
echo.
echo  Instalador de Impressoras
echo  ------------------------------------------------------------
echo   run.bat                 janela desktop (modo de uso)
echo   run.bat servidor        sobe o servidor local (desenvolvimento)
echo   run.bat scan [CIDR]     varredura pela linha de comando
echo.
echo  Opcoes do CLI (python main.py --help):
echo   --mode desktop^|server
echo   --port N                 porta do servidor local (padrao 8765)
echo   --scan [CIDR]            varre a rede
echo   --test-ip IP             testa um host
echo   --install IP --driver N  instala por linha de comando
echo   --remove-all             remove impressoras + portas orfas
echo.
pause
exit /b 0

:fim
echo.
pause
