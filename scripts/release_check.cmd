@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

python -m py_compile app\api\main.py app\api\ui.py app\config.py app\models.py app\optimizer\ranking.py app\storage\database.py app\data_sources\brand_catalog.py fuelopt_launcher.py scripts\refresh_catalog.py scripts\rebuild_station_catalog.py scripts\renormalize_catalog_brands.py tests\web_pipeline_check.py tests\test_adapters.py tests\frontend_static_check.py tests\refresh_policy_check.py
if errorlevel 1 exit /b 1

python tests\web_pipeline_check.py
if errorlevel 1 exit /b 1

python tests\test_adapters.py
if errorlevel 1 exit /b 1

python tests\frontend_static_check.py
if errorlevel 1 exit /b 1

python tests\refresh_policy_check.py
if errorlevel 1 exit /b 1

python tests\sanity_check.py
if errorlevel 1 exit /b 1

python tests\secrets_check.py
if errorlevel 1 exit /b 1

echo.
echo Release checks passed.
endlocal
