@echo off
setlocal
cd /d "C:\Users\migue\OneDrive\Escritorio\MIGUEL\SIDE PROJECTS\GAS SCRAPING"
if not exist "data\reports" mkdir "data\reports"
python "scripts\refresh_catalog.py" --source auto --write-report "data\reports\catalog_refresh_report.json" >> "data\reports\catalog_refresh.log" 2>&1
endlocal
