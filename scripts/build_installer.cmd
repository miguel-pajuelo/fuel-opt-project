@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

if not defined FUELOPT_VERSION set "FUELOPT_VERSION=0.1.0"

python tests\bundle_check.py --bundle dist\FuelOpt
if errorlevel 1 exit /b 1

python tests\installer_check.py
if errorlevel 1 exit /b 1

set "ISCC_EXE="
for %%I in (
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if not defined ISCC_EXE if exist "%%~I" set "ISCC_EXE=%%~I"

if not defined ISCC_EXE for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC_EXE set "ISCC_EXE=%%~fI"

if not defined ISCC_EXE (
  echo Inno Setup 6 compiler not found. Install JRSoftware.InnoSetup and retry.
  exit /b 2
)

"%ISCC_EXE%" /DAppVersion="%FUELOPT_VERSION%" installer\FuelOpt.iss
if errorlevel 1 exit /b 1

if not exist "dist\installer\FuelOpt-Setup-%FUELOPT_VERSION%.exe" (
  echo Installer output was not created.
  exit /b 1
)

echo.
echo FuelOpt installer complete: dist\installer\FuelOpt-Setup-%FUELOPT_VERSION%.exe
endlocal
