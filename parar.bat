@echo off
rem Para o PControl que estiver rodando em segundo plano.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | Where-Object { $_.CommandLine -like '*%~dp0server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('PControl parado (PID ' + $_.ProcessId + ').') }"
