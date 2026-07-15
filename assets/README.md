# Recursos de identidad visual de FuelOpt

`source/fuelopt-icon-approved.png` es la fuente raster aprobada para la identidad visual de FuelOpt. Los derivados se generan de forma reproducible y no deben editarse manualmente.

- SHA-256: `0EF1C3988F4711352F4ABDF4A2EC1B3081E80A02F75FAE28A3B545A88DC82A16`.
- Dimensiones: 1254 × 1254 píxeles.
- Formato: PNG RGB de 24 bits.
- Autoría y dirección: Miguel Pajuelo Gómez, con asistencia de ChatGPT durante el proceso creativo.

## Derivados

- `fuelopt-icon-1024.png`: PNG RGBA preparado para escalado.
- `fuelopt.ico`: icono de Windows con tamaños entre 16 y 256 píxeles.
- `../static/favicon.ico` y `../static/icons/fuelopt-*.png`: recursos web derivados.

La transformación elimina únicamente el fondo exterior conectado al lienzo, añade transparencia y genera los tamaños necesarios. El archivo fuente no se sobrescribe.

## Regeneración

```bat
python -m pip install -r requirements-build.txt
python scripts\generate_brand_assets.py --contact-sheet build\brand-assets-contact-sheet.png
python tests\brand_assets_check.py
```

La hoja de contacto se escribe en `build/`, no se rastrea ni se incluye en el bundle. El generador valida formato, dimensiones y SHA-256 antes de crear derivados.
