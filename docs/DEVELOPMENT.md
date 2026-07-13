# Desarrollo

## Entorno

CI utiliza Python 3.12.10. Crea un entorno virtual e instala dependencias exactas:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-web.txt
python -m pip install -r requirements-build.txt
```

No confirmes `.env`, claves reales o rutas personales. Pillow es una herramienta exclusiva del pipeline gráfico y no una dependencia runtime.

## Estructura

- `app/`: API, bootstrap, catálogo, rutas, persistencia e integración Windows.
- `static/`: frontend, derivados gráficos y Leaflet local.
- `assets/`: fuente aprobada y derivados de marca; no contiene un SVG maestro.
- `data/`: semilla y snapshot rastreados; no es el directorio mutable instalado.
- `fuelopt_launcher.py`: entry point de desarrollo y ejecutable congelado.
- `installer/`: Inno Setup.
- `scripts/`: mantenimiento, builds y release checks.
- `tests/`: checks funcionales, estáticos y de empaquetado.

## Ejecución y pruebas

```bat
python fuelopt_launcher.py
python -m pytest
scripts\release_check.cmd
git diff --check
```

El endpoint `POST /catalog/refresh` y `FUELOPT_ADMIN_TOKEN` permanecen por compatibilidad; el Scheduler usa el pipeline directo.

## Política SQLite

La semilla rastreada debe estar cerrada, validada, checkpointed y sin WAL útil. Solo el bootstrap la abre como `immutable=1`. Bases activas, legacy, migradas o backups se leen normalmente mediante `sqlite3.Connection.backup()` para incluir transacciones confirmadas en WAL. Las actualizaciones se construyen en una candidata, se validan y se publican atómicamente; una activa válida no se reemplaza por la semilla.

No confirmes bases activas, sidecars, locks ni datos de usuario. Un cambio intencional en semilla o snapshot debe incluir procedencia, reconstrucción, validación y hashes.

## Identidad visual

La fuente aprobada es `assets/source/fuelopt-icon-approved.png`, SHA-256 `0EF1C3988F4711352F4ABDF4A2EC1B3081E80A02F75FAE28A3B545A88DC82A16`. El generador valida formato, dimensiones e identidad antes de producir PNG, ICO multirresolución y recursos web. No descarga recursos, no sobrescribe la fuente y no vectoriza: no existe SVG maestro.

```bat
python scripts\generate_brand_assets.py --contact-sheet build\brand-assets-contact-sheet.png
python tests\brand_assets_check.py
```

## Builds y release

```bat
scripts\build_onedir.cmd
scripts\build_installer.cmd
```

El bundle es PyInstaller `onedir`. Los recursos se localizan desde el runtime congelado, no desde `cwd`. `build/` y `dist/` son regenerables. No incluyas `.env`, tests, logs, caches, datos mutables ni `.git`.

`FUELOPT_VERSION` es el parámetro común del build. En CI se deriva del tag o del input dry-run; localmente los scripts resuelven el valor predeterminado validado. `generate_version_info.py` genera de forma determinista el recurso PE en `build/metadata/`, y `version_info_check.py` exige que versión textual, versión numérica e iconos coincidan. El bundle distribuye la fuente rastreada `docs/THIRD_PARTY_NOTICES.md` como `_internal/licenses/THIRD_PARTY_NOTICES.md`.

El workflow de Windows ejecuta checks, construye bundle e instalador, y genera ZIP y SHA-256. `workflow_dispatch` es dry-run y puede compilar sin licencia; un tag solo puede alcanzar el job de publicación cuando el guard valida un `LICENSE` regular, no vacío y sin placeholders. Consulta [RELEASING.md](RELEASING.md).
