# Desarrollo y builds

## Entorno

FuelOpt usa Python 3.12.10 en CI.

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-runtime.lock -r requirements-test.txt
```

Para generar assets o ejecutables, instala también `requirements-build.txt`.

## Ejecutar desde fuente

```bat
python fuelopt_launcher.py
```

El launcher inicia un servidor local y abre el navegador. La opción LAN es explícita y no debe usarse en redes no confiables.

## Tests

```bat
python -m pytest
python tests\documentation_hygiene_check.py
python tests\security_check.py
scripts\release_check.cmd
git diff --check
```

Los tests que necesitan SQLite utilizan directorios temporales. No escribas bases, logs o snapshots de prueba dentro del repositorio.

## Build de Windows

```bat
scripts\build_onedir.cmd
scripts\build_installer.cmd
```

`FUELOPT_VERSION` es el parámetro común. Si no se indica, los scripts usan la versión predeterminada validada por `generate_version_info.py`. VERSIONINFO, instalador y nombres de artifacts se derivan de ese valor.

El bundle incluye LICENSE, NOTICE, atribuciones, inventario runtime y textos legales. `bundle_check.py`, `legal_inventory_check.py`, `version_info_check.py` e `installer_check.py` validan su contenido.

## Datos

La semilla y el snapshot MINETUR están rastreados deliberadamente. No confirmes una actualización accidental. Cualquier cambio intencional debe conservar procedencia, fechas y hashes en `data/SEED_PROVENANCE.json`.

## Publicación

El workflow de Windows ejecuta checks, construye ZIP e instalador y genera `SHA256SUMS.txt`. `workflow_dispatch` es siempre un dry-run. La publicación solo puede ejecutarse desde un tag válido y se describe en [RELEASING.md](RELEASING.md).
