# Arquitectura

FuelOpt combina un launcher Windows, una API FastAPI local, una interfaz web estática y recursos de catálogo. PyInstaller crea un bundle onedir y el script Inno Setup lo empaqueta como instalador por usuario.

## Flujo de identidad visual

`assets/source/fuelopt-icon-approved.png` es una entrada inmutable. `scripts/generate_brand_assets.py` valida su identidad y genera un PNG sRGB con alfa. A partir de ese PNG se producen el ICO multirresolución y los tamaños web.

`FuelOpt.spec` consume únicamente `assets/fuelopt.ico` como icono del ejecutable. No añade la fuente ni la hoja de contacto al bundle. `installer/FuelOpt.iss` consume el mismo ICO para el instalador; accesos directos y metadatos de desinstalación reutilizan `FuelOpt.exe`. Las páginas estáticas consumen únicamente derivados bajo `static/`.

No existe un SVG maestro. La futura vectorización profesional es una decisión separada y no debe inferirse de los PNG o ICO actuales.
