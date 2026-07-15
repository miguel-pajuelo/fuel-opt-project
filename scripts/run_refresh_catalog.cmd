@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
if not exist "data\reports" mkdir "data\reports"
python "scripts\refresh_catalog.py" --source minetur --write-report "data\reports\catalog_refresh_report.json" >> "data\reports\catalog_refresh.log" 2>&1
endlocal
