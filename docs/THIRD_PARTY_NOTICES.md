# Componentes y servicios de terceros

Este inventario es factual y preliminar. No sustituye asesoramiento jurídico ni afirma cumplimiento completo. La licencia principal de FuelOpt no se ha elegido.

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
| OpenRouteService | Servicio | Geocodificación y rutas opcionales | Condiciones del servicio/API | No | [openrouteservice](https://openrouteservice.org/) | El usuario aporta su clave; revisar onboarding, cuotas y privacidad. |
| OpenStreetMap Standard Tile Layer | Servicio/datos | Teselas desde `tile.openstreetmap.org` y atribución | ODbL para datos; política de teselas separada | No | [Copyright OSM](https://www.openstreetmap.org/copyright), [Tile usage policy](https://operations.osmfoundation.org/policies/tiles/) | Revisar carga, cache, atribución y política de uso antes de publicar (FR-038). |
| MINETUR | Fuente de datos | Precios de carburantes | Condiciones y procedencia pendientes de revisión | No | [Geoportal de gasolineras](https://geoportalgasolineras.es/) | No se afirma una licencia de reutilización; resolver FR-045. |
| Ballenoil | Fuente complementaria | Precios/catálogo cuando aplica | Condiciones pendientes de revisión | No | [Ballenoil](https://www.ballenoil.es/) | Revisar procedencia, frecuencia y permiso antes de release. |
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

El icono de FuelOpt fue proporcionado y aprobado por el responsable del proyecto el 12 de julio de 2026. La fuente rasterizada aprobada, su SHA-256 y el proceso de derivación constan en `assets/README.md`. No se incorporaron iconos externos ni recursos gráficos de terceros para generar PNG e ICO.

La procedencia jurídica de la imagen no ha sido verificada de manera independiente. Esta nota registra el origen declarado y no constituye una conclusión legal. Una futura fuente vectorial profesional permanece como decisión pendiente (FR-037).

## Licencia de FuelOpt

No existe un archivo `LICENSE` aprobado. Por tanto, este repositorio no concede por ahora una licencia de código abierto sobre el código propio. Elegirla, documentar titulares y comprobar compatibilidad con terceros es un **BLOCKER DE RELEASE** (FR-002).
