@echo off
rem Compila o APK e copia para dist\PControl.apk (o PC serve ele em http://SEU-IP:8765/app.apk).
setlocal
cd /d "%~dp0"
if exist "C:\Program Files\Android\Android Studio\jbr\bin\java.exe" set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
call "%~dp0gradlew.bat" assembleRelease --console=plain
if errorlevel 1 (
  echo.
  echo Falhou ao compilar o APK.
  exit /b 1
)
if not exist "..\dist" mkdir "..\dist"
copy /y "app\build\outputs\apk\release\app-release.apk" "..\dist\PControl.apk" >nul
echo.
echo APK pronto: %~dp0..\dist\PControl.apk
