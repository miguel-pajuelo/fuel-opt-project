# Configuración

## Rutas locales

FuelOpt separa recursos instalados y datos mutables:

- Programa: `%LOCALAPPDATA%\Programs\FuelOpt`.
- Configuración: `%LOCALAPPDATA%\FuelOpt\config.json`.
- Base activa: `%LOCALAPPDATA%\FuelOpt\db\gas_stations.sqlite`.
- Cache y logs: `%LOCALAPPDATA%\FuelOpt\cache` y `%LOCALAPPDATA%\FuelOpt\logs`.

`config.json` no almacena secretos. Si todavía no existe, la frecuencia predeterminada es `24h`. Un archivo válido existente conserva el valor elegido por el usuario.

## Frecuencia de actualización

Valores admitidos: `1h`, `2h`, `4h`, `8h`, `12h`, `24h`, `on_open` y `manual`.

```bat
FuelOpt.exe --configure-refresh --interval 24h
FuelOpt.exe --show-settings
```

Las seis frecuencias crean o actualizan una tarea por usuario. `on_open` actualiza al iniciar FuelOpt y `manual` elimina la tarea periódica. La tarea ejecuta el refresco directo sin arrancar el servidor web.

## OpenRouteService

ORS es opcional. La clave se guarda preferentemente en Windows Credential Manager:

```bat
FuelOpt.exe --set-ors-key
FuelOpt.exe --clear-ors-key
```

En desarrollo puede utilizarse `ORS_API_KEY` en el entorno local. No confirmes `.env` ni compartas claves en logs, Issues o capturas.

Sin ORS, FuelOpt conserva un funcionamiento limitado mediante estimaciones Haversine. La geocodificación de texto y las rutas reales requieren ORS.

## Opciones de desarrollo

Las variables `FUELOPT_ENABLE_API_DOCS`, `FUELOPT_ALLOW_LAN`, `FUELOPT_TRUST_PROXY_HEADERS` y `FUELOPT_LOG_CLIENT_IP` están desactivadas por defecto. Solo deben activarse en un entorno controlado y comprendiendo su efecto:

- `FUELOPT_ALLOW_LAN` permite escuchar en `0.0.0.0`; sin esa opción, FuelOpt se limita a `127.0.0.1`.
- `FUELOPT_TRUST_PROXY_HEADERS` permite usar la IP reenviada para los límites de peticiones. Déjalo desactivado salvo que FuelOpt esté detrás de un proxy controlado que gestione esos headers; no confíes en valores reenviados por proxies no autorizados.
- `FUELOPT_LOG_CLIENT_IP` permite registrar la IP sin anonimizar para diagnóstico. Los logs normales usan una forma anonimizada; el diagnóstico puede generar más información técnica y debe manejarse con prudencia.
- `FUELOPT_ENABLE_API_DOCS` habilita OpenAPI, Swagger y ReDoc. Permanecen desactivados por defecto.

CORS permanece cerrado salvo que `CORS_ORIGINS` contenga una allowlist explícita. Las respuestas incluyen las cabeceras de seguridad documentadas en [SECURITY.md](../SECURITY.md).

## Privacidad y servicios externos

FuelOpt puede contactar con OpenRouteService, MINETUR y `tile.openstreetmap.org`. Esos servicios pueden recibir la IP y los parámetros necesarios para su operación. Google Maps recibe puntos de ruta solo cuando el usuario abre el enlace. GitHub recibe información únicamente cuando el usuario decide publicar un Issue.

FuelOpt no incorpora telemetría propia ni SMTP. Consulta la [página de privacidad](../static/privacy.html).
