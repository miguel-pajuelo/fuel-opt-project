# Desarrollo

El runtime usa `requirements-web.txt`. Las herramientas de empaquetado e identidad visual son dependencias exclusivas de build fijadas en `requirements-build.txt`; Pillow no se necesita durante la ejecución de FuelOpt.

## Identidad visual

La fuente aprobada está preservada en `assets/source/fuelopt-icon-approved.png`. Para regenerar los derivados:

```bat
python -m pip install -r requirements-build.txt
python scripts\generate_brand_assets.py --contact-sheet build\brand-assets-contact-sheet.png
python tests\brand_assets_check.py
```

El generador rechaza cualquier archivo cuyo formato, dimensiones o SHA-256 no coincidan con la fuente aprobada. No sobrescribe la fuente, no traza vectores y no descarga recursos externos. La hoja de contacto es evidencia temporal ignorada por Git.

Antes de entregar cambios de packaging:

```bat
python -m pytest
scripts\release_check.cmd
git diff --check
```
