# Componentes y servicios de terceros

Este documento es un aviso factual y no sustituye asesoramiento jurídico. El código propio de FuelOpt se distribuye bajo Apache License 2.0, Copyright 2026 Miguel Pajuelo Gómez. Cada componente de terceros conserva sus propios términos.

El ZIP portable y el instalador incluyen el inventario reproducible `_internal/licenses/THIRD_PARTY_COMPONENTS.json`. Los textos legales completos declarados por ese inventario se encuentran en `_internal/licenses/third_party/`; la licencia de Leaflet permanece junto al recurso local en `_internal/static/vendor/leaflet/LICENSE` para evitar una copia duplicada.

## A. Componentes distribuidos en el bundle

El inventario machine-readable es la fuente exacta de nombres, versiones, licencias, URLs oficiales y rutas legales. Se genera sin red desde `requirements-runtime.lock`, la metadata de las wheels instaladas y overrides controlados para el runtime nativo.

| Componente | Versión | Uso | Licencia declarada | Evidencia distribuida |
|---|---:|---|---|---|
| Python | 3.12.10 | Runtime embebido | PSF-2.0 | Licencia oficial íntegra, incluidos sus términos históricos. |
| OpenSSL | 3.0.16 | TLS y criptografía de CPython | Apache-2.0 | Licencia oficial íntegra bajo `licenses/third_party/openssl/`. |
| SQLite | 3.49.1 | Persistencia local | Dominio público (`blessing`) | Aviso y enlace oficial de SQLite. |
| libffi | 3.4.4 | Soporte nativo de `ctypes` | MIT | Licencia oficial íntegra. |
| bzip2 / XZ Utils / zlib | 1.0.8 / 5.2.5 / 1.3.1 | Compresión del runtime Python | Licencias y dedicaciones indicadas en el inventario | Textos oficiales de las versiones usadas por CPython 3.12.10. |
| Microsoft Visual C++ Runtime y Universal CRT | 14.42.34438 / 10.0.26100.1742 | DLL de soporte de CPython | `LicenseRef-Microsoft-Redistributable` | Aviso y enlaces a la lista de redistribución y términos oficiales; requiere revisión jurídica final. |
| PyInstaller bootloader | 6.19.0 | Arranque del ejecutable congelado | GPL-2.0-or-later con Bootloader Exception | `COPYING.txt` oficial. La herramienta PyInstaller no se distribuye. |
| FastAPI, Starlette, Pydantic, Uvicorn, Requests, SlowAPI y transitivas | Versiones exactas en el JSON | Runtime Python de la aplicación | Identificador SPDX por distribución | Textos copiados desde la metadata oficial instalada. |
| certifi | 2026.6.17 | Certificados CA | MPL-2.0 | Licencia íntegra y código fuente exacto en <https://github.com/certifi/python-certifi/tree/2026.06.17>. |
| Requests | 2.33.0 | HTTP saliente | Apache-2.0 | `LICENSE` y `NOTICE` oficiales incluidos. |
| Leaflet | 1.9.4 | Mapa en navegador | BSD-2-Clause | Recurso local y licencia en `static/vendor/leaflet/LICENSE`. |

Beautiful Soup se conserva como dependencia de tests del adaptador histórico inactivo, pero no forma parte del runtime distribuido. `pytest`, `httpx`, Pillow, PyInstaller como herramienta e Inno Setup tampoco se incluyen como dependencias runtime.

## B. Servicios externos utilizados en ejecución

| Servicio | Uso | Distribuido | Fuente oficial | Nota |
|---|---|---|---|---|
| OpenRouteService | Geocodificación y rutas opcionales | No | [Términos de ORS](https://openrouteservice.org/terms-of-service/) | El usuario aporta su clave. |
| OpenStreetMap Standard Tile Layer | Teselas y datos cartográficos | No | [Copyright OSM](https://www.openstreetmap.org/copyright), [política de teselas](https://operations.osmfoundation.org/policies/tiles/) | La atribución visible y la política operativa son obligaciones separadas. |
| MINETUR | Fuente productiva del catálogo y de la semilla transformada | Se redistribuyen snapshot y SQLite transformada | [Geoportal](https://geoportalgasolineras.es/), [reutilización](https://sede.serviciosmin.gob.es/es-ES/Paginas/aviso.aspx#Reutilizacion) | Consultar `DATA_SOURCES_AND_ATTRIBUTION.md`. |
| Google Maps | Enlace abierto voluntariamente por el usuario | No | [Google Maps](https://www.google.com/maps) | Solo recibe los puntos cuando el usuario abre el enlace. |
| GitHub Issues | Ideas y errores no sensibles | No | [GitHub Terms](https://docs.github.com/site-policy/github-terms/github-terms-of-service) | No usar para secretos o vulnerabilidades. |

## C. Herramientas de desarrollo y compilación

| Herramienta | Versión | Uso | Distribuida como herramienta | Fuente oficial |
|---|---:|---|---|---|
| PyInstaller | 6.19.0 | Generación del bundle `onedir` | No; únicamente su bootloader forma parte del ejecutable | [Licencia de PyInstaller](https://pyinstaller.org/en/stable/license.html) |
| Inno Setup | 6.7.3 en CI | Generación del instalador | No | [Licencia oficial](https://jrsoftware.org/files/is6-license.txt) |
| Pillow | 12.0.0 | Generación y comprobación de assets en build | No | [Pillow](https://python-pillow.org/) |
| pytest / httpx | 9.1.1 / 0.28.1 | Tests | No | Metadata oficial instalada en el entorno de test. |
| GitHub Actions | `windows-latest`; acciones fijadas por SHA | CI, builds y artifacts de release | No | [GitHub Actions](https://docs.github.com/actions) |

Inno Setup se usa para producir el instalador y no se incorpora al runtime. Sus condiciones vigentes deben evaluarse para el uso y distribución previstos.

## Licencia de FuelOpt

El archivo `LICENSE` contiene Apache License 2.0 y `NOTICE` identifica al titular. El inventario y los textos empaquetados aportan trazabilidad técnica; no constituyen una conclusión jurídica definitiva sobre la distribución.
