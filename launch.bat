@echo off
chcp 65001 >nul
cls

echo.
echo ==========================================
echo    VARIAC CONTROL SYSTEM
echo ==========================================
echo.

set SCRIPT_DIR=%~dp0
set CONFIG=%SCRIPT_DIR%config.ini

if not exist "%CONFIG%" (
  echo [ERROR] config.ini not found in:
  echo %SCRIPT_DIR%
  echo.
  pause
  exit /b 1
)

for /f "tokens=1,* delims==" %%a in ('findstr /i "app_dir" "%CONFIG%"') do set APP_DIR=%%b
set PORT=5001

set APP_DIR=%APP_DIR: =%
set PORT=%PORT: =%
if "%PORT%"=="" set PORT=5001

echo [1/4] Checking configuration...
echo OK - config.ini found
echo.

if not exist "%APP_DIR%" (
  echo [ERROR] Folder not found:
  echo %APP_DIR%
  echo Check app_dir in config.ini
  echo.
  pause
  exit /b 1
)

if not exist "%APP_DIR%\app.py" (
  echo [ERROR] app.py not found in:
  echo %APP_DIR%
  echo.
  pause
  exit /b 1
)

echo [2/4] Checking project folder...
echo OK - %APP_DIR%
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found
  echo Install Python from python.org
  echo Make sure to check "Add Python to PATH"
  echo.
  pause
  exit /b 1
)

for /f "tokens=*" %%v in ('python --version') do echo [3/4] Checking Python... OK - %%v
echo.

python -c "import flask, flask_socketio, serial" >nul 2>&1
if errorlevel 1 (
  echo [4/4] Installing missing packages...
  pip install flask flask-socketio pyserial
  echo.
) else (
  echo [4/4] All dependencies OK
  echo.
)

if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs"
if not exist "%APP_DIR%\CalexConfig\data" mkdir "%APP_DIR%\CalexConfig\data"

echo ==========================================
echo Starting server on port %PORT%...
echo Open http://localhost:%PORT%
echo ==========================================
echo.
echo Press CTRL+C to stop the server
echo.

cd /d "%APP_DIR%"

start /b cmd /c "timeout /t 4 >nul && start http://localhost:%PORT%"

python app.py

pause
