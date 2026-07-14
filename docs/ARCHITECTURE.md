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

`%LOCALAPPDATA%\Programs\FuelOpt` contiene ejecutable, `_internal`, frontend, semilla MINETUR, snapshot y metadata de procedencia. La lógica no debe escribir allí. `%LOCALAPPDATA%\FuelOpt` contiene `config.json`, `data/db`, `data/cache` y `logs`.

En primer arranque, el bootstrap conserva una base activa válida; si falta, copia la semilla MINETUR con backup SQLite y fuente inmutable o reconstruye desde su snapshot. El flujo productivo de 0.1.0 usa únicamente MINETUR y su snapshot como fuentes. Todas las estaciones se procesan con criterios neutrales respecto a su marca a partir del catálogo oficial. Un refresco fallido conserva la activa y, cuando corresponde, una copia `previous` recuperable.

## Optimización y presentación

El contrato público admite `economic`, `minimal_detour` y `balanced`. La pipeline construye el universo válido, calcula sus métricas, aplica una ordenación determinista y limita la respuesta únicamente después del ranking.

`economic` conserva la clave económica neta; `minimal_detour` usa el desvío adicional en trayectos o la distancia a la estación en búsquedas locales, con la economía como desempate. `balanced` combina al 50 % los rangos normalizados económico y de desvío, tratando empates semánticos con competition ranking. La puntuación y los rangos son internos: la API solo conserva `why_selected` como explicación pública.

OpenRouteService y la aproximación Haversine no cambian el contrato de modos. El frontend identifica cuál se utilizó y presenta Haversine como estimación. La versión 0.1.0 no implementa autonomía ni `remaining_fuel_liters`.

## Refresco y Scheduler

`refresh_service` ejecuta el pipeline sin HTTP. Windows Task Scheduler invoca `FuelOpt.exe --refresh-direct --silent` para el usuario actual. `config.json` es la fuente de verdad de la política y los locks evitan refrescos simultáneos.

## Launcher e instancia

El entry point ejecuta `multiprocessing.freeze_support()` temprano. En frozen, procesos independientes usan `sys.executable`. Uvicorn emplea una instancia ASGI, un worker, `asyncio`, `h11`, lifespan activo y sin reload. El launcher verifica `/health` e identidad `FuelOpt`, usa 8001–8010 y mantiene un runtime record. El cierre cooperativo Win32 permite actualizar `_internal` sin terminar procesos ajenos.

## Identidad visual

`assets/source/fuelopt-icon-approved.png` es una entrada inmutable validada por SHA-256. A partir de ella se generan PNG sRGB/RGBA, ICO 16–256 y derivados web. No existe SVG maestro ni se afirma vectorización. `FuelOpt.spec` consume el ICO para el ejecutable e Inno Setup lo reutiliza para instalador y accesos. La trazabilidad técnica está validada; la procedencia jurídica permanece en curso.

## Packaging, seguridad y servicios

PyInstaller produce `onedir`; Inno Setup instala por usuario con AppId estable y datos externos. La versión derivada por el workflow o los scripts alimenta tanto el `VERSIONINFO` de `FuelOpt.exe` como los metadatos del instalador y los nombres de artefactos. El bundle incorpora los avisos rastreados en `_internal/licenses/`, sin documentación interna de auditoría.

GitHub Actions fija Python, ejecuta release checks y genera instalador, ZIP y checksums. El build permite dry-runs sin licencia para obtener evidencia técnica, pero la ruta de tag falla antes de compilar y el job con `contents: write` exige una aprobación positiva del guard de `LICENSE`.

La clave ORS vive preferentemente en Credential Manager y los logs aplican redacción. Las fronteras ORS convierten errores externos en mensajes públicos estables y registran solo operación, clase general y estado remoto seguro; no propagan URL, query, cabeceras ni texto arbitrario del proveedor. `tests/security_check.py` se ejecuta obligatoriamente dentro del release gate.

El endpoint administrativo legacy sigue protegido por `FUELOPT_ADMIN_TOKEN`. Servicios externos: ORS, fuentes de precios y teselas OpenStreetMap; Google Maps y GitHub se abren solo por una acción explícita del usuario. No existe hosting público, formulario de correo ni analítica propia vigente.
