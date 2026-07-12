@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

python -m py_compile app\api\main.py app\api\ui.py app\bootstrap.py app\catalog\refresh_service.py app\config.py app\paths.py app\user_config.py app\windows_credentials.py app\windows_scheduler.py app\windows_shutdown.py app\legacy_migration.py app\models.py app\optimizer\ranking.py app\storage\database.py app\storage\publish.py app\storage\validation.py app\data_sources\brand_catalog.py fuelopt_launcher.py scripts\check_build_environment.py scripts\refresh_catalog.py scripts\rebuild_station_catalog.py scripts\renormalize_catalog_brands.py tests\web_pipeline_check.py tests\test_adapters.py tests\frontend_static_check.py tests\refresh_policy_check.py tests\desktop_config_check.py tests\bootstrap_check.py tests\refresh_scheduler_check.py tests\windows_shutdown_check.py tests\bundle_check.py tests\installer_check.py tests\release_workflow_check.py
if errorlevel 1 exit /b 1

python tests\web_pipeline_check.py
if errorlevel 1 exit /b 1

python tests\test_adapters.py
if errorlevel 1 exit /b 1

python tests\frontend_static_check.py
if errorlevel 1 exit /b 1

python tests\refresh_policy_check.py
if errorlevel 1 exit /b 1

python tests\desktop_config_check.py
if errorlevel 1 exit /b 1

python tests\bootstrap_check.py
if errorlevel 1 exit /b 1

python tests\refresh_scheduler_check.py
if errorlevel 1 exit /b 1

python tests\windows_shutdown_check.py
if errorlevel 1 exit /b 1

python tests\sanity_check.py
if errorlevel 1 exit /b 1

python tests\secrets_check.py
if errorlevel 1 exit /b 1

python tests\db_artifact_check.py
if errorlevel 1 exit /b 1

python tests\installer_check.py
if errorlevel 1 exit /b 1

python tests\release_workflow_check.py
if errorlevel 1 exit /b 1

echo.
echo Release checks passed.
endlocal
