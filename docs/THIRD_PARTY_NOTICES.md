# Componentes y servicios de terceros

Este inventario es factual y preliminar. No sustituye asesoramiento jurídico ni afirma cumplimiento completo. El código propio de FuelOpt se distribuye bajo Apache License 2.0, Copyright 2026 Miguel Pajuelo Gómez.

## A. Componentes distribuidos en el bundle

| Componente | Versión | Uso | Licencia declarada | Distribuido | Fuente oficial | Obligación o incertidumbre |
|---|---:|---|---|---|---|---|
| Python | 3.12.10 | Runtime embebido | PSF License | Sí | [Python license](https://docs.python.org/3/license.html) | Conservar avisos aplicables; confirmar archivos incluidos por PyInstaller. |
| FastAPI | 0.136.0 | API local | MIT | Sí | [FastAPI](https://github.com/fastapi/fastapi) | Conservar aviso/licencia. |
| Starlette | 1.0.1 | ASGI | BSD-3-Clause | Sí | [Starlette](https://github.com/Kludex/starlette) | Conservar copyright y condiciones. |
| Pydantic | 2.13.2 | Validación | MIT | Sí | [Pydantic](https://github.com/pydantic/pydantic) | Incluye `pydantic-core`; revisar transitivas. |
| Uvicorn | 0.44.0 | Servidor local | BSD-3-Clause | Sí | [Uvicorn](https://github.com/Kludex/uvicorn) | Conservar copyright y condiciones. |
| Requests | 2.33.0 | HTTP saliente | Apache-2.0 | Sí | [Requests](https://github.com/psf/requests) | Incluir licencia y avisos aplicables. |
| Beautiful Soup | 4.14.3 | Parseo de fuentes | MIT | Sí | [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) | Confirmar archivo de licencia distribuido. |
| SlowAPI | 0.1.9 | Rate limiting | MIT | Sí | [SlowAPI](https://github.com/laurentS/slowapi) | Revisar también `limits` y dependencias. |
| certifi | 2026.6.17 en build validado | Certificados CA | MPL-2.0 | Sí | [certifi](https://github.com/certifi/python-certifi) | Mantener el bundle de CA y licencia MPL. |
| Leaflet | 1.9.4 | Mapa en navegador | BSD-2-Clause | Sí, local | [Leaflet](https://leafletjs.com/) | Ya se distribuye `static/vendor/leaflet/LICENSE`; mantener atribución. |

Las dependencias transitivas, módulos congelados y metadatos de licencia del bundle requieren un inventario final reproducible (FR-003 y FR-043).

## B. Servicios externos utilizados en ejecución

| Servicio | Versión | Uso | Licencia/condiciones | Distribuido | Fuente oficial | Obligación o incertidumbre |
|---|---|---|---|---|---|---|
| OpenRouteService | Servicio | Geocodificación y rutas opcionales | Condiciones del servicio/API; resultados CC BY 4.0 | No | [openrouteservice](https://openrouteservice.org/terms-of-service/) | La aplicación muestra la atribución requerida; el usuario aporta su clave. |
| OpenStreetMap Standard Tile Layer | Servicio/datos | Teselas desde `tile.openstreetmap.org` y atribución | ODbL para datos; política de teselas separada | No | [Copyright OSM](https://www.openstreetmap.org/copyright), [Tile usage policy](https://operations.osmfoundation.org/policies/tiles/) | La URL oficial y la atribución visible se configuran en Leaflet; revisar carga real antes de publicar (FR-038). |
| MINETUR | Fuente y datos redistribuidos | Snapshot y semilla SQLite del catálogo oficial de estaciones | Condiciones generales de reutilización de datos abiertos | Sí, snapshot y SQLite transformada | [Geoportal de gasolineras](https://geoportalgasolineras.es/), [condiciones de reutilización](https://sede.serviciosmin.gob.es/es-ES/Paginas/aviso.aspx#Reutilizacion) | Citar fuente y fecha, conservar integridad y no desnaturalizar; consultar `DATA_SOURCES_AND_ATTRIBUTION.md`. |
| Google Maps | Servicio abierto por el usuario | Mostrar origen, estación y destino al pulsar **Abrir en Maps** | Condiciones del servicio | No | [Google Maps](https://www.google.com/maps) | No recibe puntos automáticamente; revisar sus condiciones y privacidad antes de usar el enlace. |
| GitHub Issues | Servicio abierto por el usuario | Ideas y errores no sensibles mediante **Mándanos tu idea** | Condiciones de GitHub | No | [GitHub Terms](https://docs.github.com/site-policy/github-terms/github-terms-of-service) | FuelOpt no adjunta datos de la búsqueda; el usuario decide qué publica. No usar para secretos o vulnerabilidades. |

Los proveedores externos pueden recibir la IP y los parámetros necesarios. Leaflet local no convierte las teselas en un recurso offline.

## C. Herramientas de desarrollo y compilación

| Herramienta | Versión | Uso | Licencia/política | Distribuida como runtime | Fuente oficial | Obligación o incertidumbre |
|---|---:|---|---|---|---|---|
| PyInstaller | 6.19.0 | Bundle `onedir` | GPL-2.0-or-later con excepción para aplicaciones congeladas | No como herramienta | [PyInstaller license](https://pyinstaller.org/en/stable/license.html) | Revisar aplicación exacta de la excepción y licencias de binarios incluidos. |
| Inno Setup | 6.7.3 en CI | Instalador Windows | Licencia propia | No como runtime | [Inno Setup](https://jrsoftware.org/isinfo.php) | Revisar política aplicable y uso comercial antes de publicar (FR-004). |
| GitHub Actions | `windows-latest` y acciones fijadas por SHA | CI y artefactos | Condiciones de GitHub y licencias de cada acción | No | [GitHub Actions](https://docs.github.com/actions) | Mantener permisos mínimos y revisar cambios de imágenes del runner. |

## Identidad visual de FuelOpt

El icono propio de FuelOpt fue creado y aprobado por Miguel Pajuelo Gómez con asistencia de ChatGPT durante el proceso creativo. La fuente rasterizada aprobada, su SHA-256 y el proceso de derivación constan en `assets/README.md`.

## Licencia de FuelOpt

El código propio de FuelOpt se distribuye bajo Apache License 2.0. El archivo `LICENSE` contiene los términos íntegros y `NOTICE` identifica al titular. La revisión completa de dependencias transitivas y la revisión jurídica profesional siguen pendientes (FR-003 y FR-043).
