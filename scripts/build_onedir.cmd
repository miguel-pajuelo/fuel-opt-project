@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

rem Release builds always use the windowed bootloader, regardless of inherited
rem environment. For a diagnostic console build, invoke PyInstaller manually
rem with FUELOPT_DIAGNOSTIC_CONSOLE=1 and separate dist/work paths.
set "FUELOPT_DIAGNOSTIC_CONSOLE=0"

if not defined FUELOPT_VERSION for /f "delims=" %%V in ('python scripts\generate_version_info.py --resolve-default') do set "FUELOPT_VERSION=%%V"
python scripts\generate_version_info.py --version "%FUELOPT_VERSION%" --output build\metadata\FuelOpt.version.txt
if errorlevel 1 exit /b 1

python scripts\check_build_environment.py
if errorlevel 1 exit /b 1

python -m PyInstaller --clean --noconfirm --workpath build\pyinstaller FuelOpt.spec
if errorlevel 1 exit /b 1

python tests\bundle_check.py --bundle dist\FuelOpt
if errorlevel 1 exit /b 1

python tests\version_info_check.py --exe dist\FuelOpt\FuelOpt.exe --expected-version "%FUELOPT_VERSION%"
if errorlevel 1 exit /b 1

echo.
echo FuelOpt onedir build complete: dist\FuelOpt\FuelOpt.exe
echo The legacy onefile build remains available through scripts\build_launcher.cmd.
endlocal
