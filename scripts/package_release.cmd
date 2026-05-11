@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PACKAGE_DIR=dist\FuelOptPortable"
set "APP_DIR=%PACKAGE_DIR%\FuelOptApp"
set "ZIP_PATH=dist\FuelOptPortable.zip"

if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%APP_DIR%"

copy /y "FuelOpt.cmd" "%PACKAGE_DIR%\FuelOpt.cmd" >nul
copy /y "fuelopt_launcher.py" "%APP_DIR%\fuelopt_launcher.py" >nul
copy /y "requirements-web.txt" "%APP_DIR%\requirements-web.txt" >nul
copy /y "README_WEB.md" "%APP_DIR%\README_WEB.md" >nul
copy /y ".env.example" "%APP_DIR%\.env.example" >nul

if exist "dist\FuelOptLauncher.exe" (
  copy /y "dist\FuelOptLauncher.exe" "%APP_DIR%\FuelOptLauncher.exe" >nul
)

call :copy_dir app
if errorlevel 1 exit /b 1
call :copy_dir data
if errorlevel 1 exit /b 1
call :copy_dir docs
if errorlevel 1 exit /b 1
call :copy_dir scripts
if errorlevel 1 exit /b 1
call :copy_dir static
if errorlevel 1 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%PACKAGE_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force"

echo.
echo Portable package ready:
echo   %PACKAGE_DIR%
echo   %ZIP_PATH%
echo.
echo Zip layout:
echo   FuelOpt.cmd
echo   FuelOptApp\...
exit /b 0

:copy_dir
robocopy "%~1" "%APP_DIR%\%~1" /E /XD "__pycache__" ".pytest_cache" /XF "*.pyc" "*.sqlite-wal" "*.sqlite-shm" "*.next.sqlite" "*.previous-*.sqlite" "launcher.log" "launcher_server.log" "launcher_refresh.log" "catalog_refresh.log" >nul
if errorlevel 8 (
  echo Failed to copy %~1
  exit /b 1
)
exit /b 0
