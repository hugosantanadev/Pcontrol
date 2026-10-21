@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PControl - configurar

echo.
echo  ==============================
echo   PControl - configuracao
echo  ==============================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Criando o ambiente Python...
  python -m venv .venv || (echo Instale o Python 3.11+ em python.org e rode de novo. & pause & exit /b 1)
) else (
  echo [1/5] Ambiente Python ok.
)

echo [2/5] Instalando dependencias...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Falhou ao instalar. & pause & exit /b 1)
if not exist "dist\PControl.apk" (
  echo       Baixando o app Android da pagina de Releases...
  powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; New-Item -ItemType Directory -Force dist | Out-Null; try { Invoke-WebRequest 'https://github.com/USUARIO/PControl/releases/latest/download/PControl.apk' -OutFile 'dist\PControl.apk' -UseBasicParsing } catch { Write-Host '      Nao consegui baixar o APK. Pegue em github.com/USUARIO/PControl/releases' }"
)

echo [3/5] Senha de acesso
".venv\Scripts\python.exe" server.py --senha || (pause & exit /b 1)

echo [4/5] Abrir junto com o Windows
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\startup.ps1"

echo [5/5] Liberando no Firewall (o Windows vai pedir permissao de administrador)...
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0tools\firewall.ps1\"'"

echo.
echo Iniciando o PControl...
call "%~dp0parar.bat" >nul 2>&1
start "" ".venv\Scripts\pythonw.exe" "%~dp0server.py"
timeout /t 3 >nul
start "" "http://localhost:8765/conectar"
echo.
echo Pronto! Escaneie o QR code que abriu no navegador com o celular.
echo.
pause
