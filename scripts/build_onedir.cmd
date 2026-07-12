@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

rem Release builds always use the windowed bootloader, regardless of inherited
rem environment. For a diagnostic console build, invoke PyInstaller manually
rem with FUELOPT_DIAGNOSTIC_CONSOLE=1 and separate dist/work paths.
set "FUELOPT_DIAGNOSTIC_CONSOLE=0"

python scripts\check_build_environment.py
if errorlevel 1 exit /b 1

python -m PyInstaller --clean --noconfirm FuelOpt.spec
if errorlevel 1 exit /b 1

python tests\bundle_check.py --bundle dist\FuelOpt
if errorlevel 1 exit /b 1

echo.
echo FuelOpt onedir build complete: dist\FuelOpt\FuelOpt.exe
echo The legacy onefile build remains available through scripts\build_launcher.cmd.
endlocal
