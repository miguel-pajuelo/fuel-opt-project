@echo off
setlocal
set "APP_DIR=%~dp0FuelOptApp"

if not exist "%APP_DIR%\fuelopt_launcher.py" if not exist "%APP_DIR%\FuelOptLauncher.exe" (
  set "APP_DIR=%~dp0"
)

if exist "%APP_DIR%\FuelOptLauncher.exe" (
  start "" "%APP_DIR%\FuelOptLauncher.exe"
) else (
  cd /d "%APP_DIR%"
  python fuelopt_launcher.py
)

endlocal
