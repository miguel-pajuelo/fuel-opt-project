# Arquitectura

FuelOpt es una aplicación local Windows: un ejecutable inicia Uvicorn/FastAPI en loopback y abre un frontend HTML/CSS/JavaScript. Leaflet se distribuye localmente; teselas y servicios de rutas siguen siendo externos.

```text
Usuario
  -> FuelOpt.exe
     -> launcher y lock de instancia
        -> recursos instalados (solo lectura)
        -> bootstrap de datos del usuario
        -> Uvicorn / FastAPI en 127.0.0.1:8001-8010
           -> frontend local
           -> base SQLite activa del usuario
           -> routing ORS o aproximación Haversine
           -> refresh_service
              -> fuentes externas
              -> base candidata
              -> validación
              -> sustitución atómica
```

## Recursos y datos

`%LOCALAPPDATA%\Programs\FuelOpt` contiene ejecutable, `_internal`, frontend, semilla y snapshot. La lógica no debe escribir allí. `%LOCALAPPDATA%\FuelOpt` contiene `config.json`, `data/db`, `data/cache` y `logs`.

En primer arranque, el bootstrap conserva una base activa válida; si falta, copia la semilla con backup SQLite y fuente inmutable o reconstruye desde snapshot. Un refresco fallido conserva la activa y, cuando corresponde, una copia `previous` recuperable.

## Refresco y Scheduler

`refresh_service` ejecuta el pipeline sin HTTP. Windows Task Scheduler invoca `FuelOpt.exe --refresh-direct --silent` para el usuario actual. `config.json` es la fuente de verdad de la política y los locks evitan refrescos simultáneos.

## Launcher e instancia

El entry point ejecuta `multiprocessing.freeze_support()` temprano. En frozen, procesos independientes usan `sys.executable`. Uvicorn emplea una instancia ASGI, un worker, `asyncio`, `h11`, lifespan activo y sin reload. El launcher verifica `/health` e identidad `FuelOpt`, usa 8001–8010 y mantiene un runtime record. El cierre cooperativo Win32 permite actualizar `_internal` sin terminar procesos ajenos.

## Identidad visual

`assets/source/fuelopt-icon-approved.png` es una entrada inmutable validada por SHA-256. A partir de ella se generan PNG sRGB/RGBA, ICO 16–256 y derivados web. No existe SVG maestro ni se afirma vectorización. `FuelOpt.spec` consume el ICO para el ejecutable e Inno Setup lo reutiliza para instalador y accesos. La trazabilidad técnica está validada; la procedencia jurídica permanece en curso.

## Packaging, seguridad y servicios

PyInstaller produce `onedir`; Inno Setup instala por usuario con AppId estable y datos externos. GitHub Actions fija Python, ejecuta release checks y genera instalador, ZIP y checksums.

La clave ORS vive en Credential Manager y los logs aplican redacción. El endpoint administrativo legacy sigue protegido por `FUELOPT_ADMIN_TOKEN`. Servicios externos: ORS, fuentes de precios y teselas OpenStreetMap. No existe hosting público ni analítica propia vigente.
