@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

python -m py_compile app\api\main.py app\api\ui.py app\bootstrap.py app\catalog\refresh_service.py app\config.py app\paths.py app\user_config.py app\windows_credentials.py app\windows_scheduler.py app\windows_shutdown.py app\legacy_migration.py app\models.py app\optimizer\ranking.py app\storage\database.py app\storage\publish.py app\storage\validation.py app\data_sources\brand_catalog.py app\routing\ors.py fuelopt_launcher.py scripts\check_build_environment.py scripts\check_release_license.py scripts\generate_brand_assets.py scripts\generate_runtime_legal_inventory.py scripts\generate_version_info.py scripts\refresh_catalog.py scripts\rebuild_station_catalog.py scripts\renormalize_catalog_brands.py tests\web_pipeline_check.py tests\test_adapters.py tests\test_release_legal.py tests\legal_inventory_check.py tests\frontend_static_check.py tests\security_check.py tests\brand_assets_check.py tests\documentation_hygiene_check.py tests\refresh_policy_check.py tests\desktop_config_check.py tests\bootstrap_check.py tests\refresh_scheduler_check.py tests\windows_shutdown_check.py tests\bundle_check.py tests\bundle_smoke_check.py tests\installer_check.py tests\release_workflow_check.py tests\version_info_check.py
if errorlevel 1 exit /b 1

python -m pytest -q
if errorlevel 1 exit /b 1

python tests\version_info_check.py --source-only
if errorlevel 1 exit /b 1

python tests\legal_inventory_check.py
if errorlevel 1 exit /b 1

python tests\brand_assets_check.py
if errorlevel 1 exit /b 1

python tests\documentation_hygiene_check.py
if errorlevel 1 exit /b 1

python tests\web_pipeline_check.py
if errorlevel 1 exit /b 1

python tests\frontend_static_check.py
if errorlevel 1 exit /b 1

python tests\security_check.py
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
