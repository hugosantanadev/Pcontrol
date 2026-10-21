@echo off
chcp 65001 >nul
rem Roda o PControl com a janela aberta (bom para ver erros). Feche a janela para parar.
cd /d "%~dp0"
call "%~dp0parar.bat" >nul 2>&1
".venv\Scripts\python.exe" "%~dp0server.py"
pause
