@echo off
setlocal
cd /d "%~dp0\.."
python -m PyInstaller ^
  --clean ^
  --onefile ^
  --noconsole ^
  --noupx ^
  --name FuelOptLauncher ^
  --exclude-module matplotlib ^
  --exclude-module PySide6 ^
  --exclude-module tkinter ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module scipy ^
  --exclude-module IPython ^
  --exclude-module jupyter ^
  --exclude-module zmq ^
  fuelopt_launcher.py
if errorlevel 1 exit /b 1
echo.
echo Launcher build complete: dist\FuelOptLauncher.exe
echo Run scripts\package_release.cmd to create the clean portable zip.
endlocal
