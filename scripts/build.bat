@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

title Forja de Impressoras - Build

echo ==========================================
echo  Forja de Impressoras - Build Script
echo ==========================================
echo.

:: ---------------------------------------------------------------------
::  Verifica o Python
:: ---------------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado no PATH.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------
::  1) dependencias
:: ---------------------------------------------------------------------
echo [1/6] Instalando/Atualizando dependencias...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo ERRO: falha ao instalar as dependencias do requirements.txt.
    pause
    exit /b 1
)
python -m pip install --quiet --disable-pip-version-check pyinstaller
if errorlevel 1 (
    echo ERRO: falha ao instalar o PyInstaller.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------
::  1b) pre-flight: app em execucao + exe antigo travam a regravacao
:: ---------------------------------------------------------------------
set "BLOQUEADO=0"
tasklist /FI "IMAGENAME eq ForjaDeImpressoras.exe" 2>nul | findstr /I "ForjaDeImpressoras.exe" >nul
if not errorlevel 1 (
    if exist "dist\windows\ForjaDeImpressoras.exe" (
        echo       processo antigo detectado — testando se o .exe esta travado...
        powershell -NoProfile -Command "try { $s=[IO.File]::Open('dist\windows\ForjaDeImpressoras.exe','Open','Write'); $s.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
        if errorlevel 1 set "BLOQUEADO=1"
    )
)
if "%BLOQUEADO%"=="1" (
    echo.
    echo  [BLOQUEADO] A Forja de Impressoras esta em execucao.
    echo  O Windows nao permite regravar o .exe enquanto ele roda.
    echo.
    echo  Faca UMA das opcoes e rode o build de novo:
    echo    1^) Feche a janela do app; ou
    echo    2^) Gerenciador de Tarefas ^> finalizar "ForjaDeImpressoras.exe"; ou
    echo    3^) Reinicie o computador.
    echo.
    pause
    exit /b 2
)

:: ---------------------------------------------------------------------
::  2) versao (fonte unica: arquivo VERSION)
:: ---------------------------------------------------------------------
set /p APP_VERSION=<"VERSION"
if "!APP_VERSION!"=="" (
    echo ERRO: Arquivo VERSION ausente ou vazio. A versao e lida exclusivamente de VERSION.
    pause
    exit /b 1
)
echo       versao: !APP_VERSION!

:: ---------------------------------------------------------------------
::  3) limpeza
:: ---------------------------------------------------------------------
echo [2/6] Limpando builds e caches...
if exist "dist" rd /s /q "dist"
if exist "build" rd /s /q "build"
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
if exist "logs" rd /s /q "logs"

:: ---------------------------------------------------------------------
::  4) icone + spec
:: ---------------------------------------------------------------------
echo [3/6] Gerando icone e spec...
python "%CD%\scripts\gen_icon.py"
if errorlevel 1 (
    echo AVISO: falha ao gerar o icone. O build segue sem icone custom.
)
python "%CD%\scripts\gen_spec.py"
if errorlevel 1 (
    echo ERRO: Falha ao gerar spec.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------
::  5) PyInstaller
:: ---------------------------------------------------------------------
set TARGET=ForjaDeImpressoras

echo.
echo === Compilando %TARGET% ===
python -m PyInstaller --distpath "dist\windows" --workpath "build\windows\%TARGET%" --clean --noconfirm "build\windows\%TARGET%.spec"
if errorlevel 1 (
    echo ERRO: PyInstaller falhou ao compilar %TARGET%.
    pause
    exit /b 1
)

echo [4/6] Preparando pasta de publicacao...
if not exist "dist\windows" mkdir "dist\windows"

:: atalho de execucao no proprio .exe
(
  echo @echo off
  echo title Forja de Impressoras
  echo echo Iniciando a Forja de Impressoras...
  echo start "" "%%~dp0%TARGET%.exe"
) > "dist\windows\Iniciar Forja de Impressoras.bat"

:: -------------------------------------------------------------------------
::  6) Inno Setup
:: -------------------------------------------------------------------------
echo [5/6] Compilando instalador Inno Setup...

set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH goto :sem_inno

"%ISCC_PATH%" "/DAppVersion=!APP_VERSION!" "setup\windows\ForjaDeImpressorasSetup.iss"
if errorlevel 1 goto :falha_inno
echo OK - dist\windows\ForjaDeImpressorasSetup.exe  versao !APP_VERSION!
goto :fim_inno

:sem_inno
echo AVISO: Inno Setup 6 nao encontrado.
echo        Instale com: winget install --id JRSoftware.InnoSetup -e -s winget
goto :fim_inno

:falha_inno
echo AVISO: Falha ao compilar o instalador.

:fim_inno

echo [6/6] Concluido.
echo.
echo  Tudo em: dist\windows\
echo  - %TARGET%.exe              (executavel)
echo  - %TARGET%Setup.exe        (instalador)
echo.
pause
exit /b 0
