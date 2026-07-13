# Recursos de identidad visual de FuelOpt

La imagen `source/fuelopt-icon-approved.png` fue proporcionada y aprobada por el responsable del proyecto el 12 de julio de 2026. Es la fuente visual oficial de FuelOpt 0.1.0.

- SHA-256: `0EF1C3988F4711352F4ABDF4A2EC1B3081E80A02F75FAE28A3B545A88DC82A16`.
- Dimensiones originales: 1254 × 1254 píxeles.
- Formato original: PNG RGB de 24 bits, sin canal alfa.
- Procedencia: material proporcionado y aprobado por el responsable del proyecto.
- Verificación jurídica: la procedencia jurídica no se ha verificado de manera independiente.

La fuente no debe sustituirse, editarse ni regenerarse sin nueva aprobación. No se ha creado un maestro SVG: el material aprobado es rasterizado. Una futura fuente vectorial profesional continúa como decisión pendiente.

## Derivados

- `fuelopt-icon-1024.png`: PNG RGBA cuadrado, con perfil sRGB y fondo negro exterior eliminado mediante selección conectada desde los bordes.
- `fuelopt.ico`: ICO real de 32 bits con entradas 16, 20, 24, 32, 40, 48, 64, 128 y 256 píxeles.
- `../static/favicon.ico` y `../static/icons/fuelopt-*.png`: recursos web derivados del PNG preparado.

La transformación conserva la composición, colores y degradados aprobados. Solo elimina el negro exterior conectado al lienzo, añade transparencia y aplica reducción Lanczos para los tamaños derivados. El archivo fuente nunca es sobrescrito.

## Regeneración reproducible

Herramientas fijadas en `requirements-build.txt`: Python, Pillow 12.0.0 y PyInstaller 6.19.0.

```bat
python -m pip install -r requirements-build.txt
python scripts\generate_brand_assets.py --contact-sheet build\brand-assets-contact-sheet.png
python tests\brand_assets_check.py
```

La hoja de contacto se escribe en `build/`, no se rastrea y no se incluye en el bundle. El generador valida formato, dimensiones y SHA-256 antes de producir ningún derivado.

## Requisitos

- FR-001 exige conservar esta fuente, generar e integrar todos los derivados, verificar los builds reales y revisar visualmente los tamaños pequeños.
- FR-037 registra aprobación, hash, fecha, ausencia de recursos gráficos externos y la limitación sobre procedencia jurídica y futura vectorización profesional.
