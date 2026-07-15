# FuelOpt

FuelOpt es una aplicación local para Windows que compara estaciones de servicio en España y estima dónde conviene repostar teniendo en cuenta el precio, la cantidad de combustible y el desplazamiento.

La aplicación se abre en el navegador desde el propio equipo, en `127.0.0.1`. No publica un servidor en Internet ni envía las búsquedas a un servidor central de FuelOpt.

## Funciones principales

- Entrada por litros o presupuesto.
- Modos **Más ahorro**, **Menor desvío** y **Equilibrado**.
- Viajes de ida o ida y vuelta y filtro de marcas.
- Comparación de la mejor opción y alternativas ordenadas.
- Rutas de OpenRouteService cuando el usuario configura una clave.
- Estimación geográfica Haversine cuando no hay ruta ORS disponible.
- Catálogo local basado en datos oficiales de MINETUR.
- Actualización manual, al abrir o programada entre 1 y 24 horas.
- Conservación de configuración y datos en `%LOCALAPPDATA%\FuelOpt`.

Los cálculos son orientativos. Los precios pueden cambiar y una estimación Haversine no equivale a una ruta real por carretera.

## Descargar e instalar

La versión pública más reciente se encuentra en [Latest release](https://github.com/miguel-pajuelo/fuel-opt-project/releases/latest). Descarga únicamente el instalador o ZIP publicado en ese repositorio.

Los artefactos actuales no están firmados digitalmente, por lo que Microsoft Defender SmartScreen puede mostrar una advertencia de reputación. Antes de continuar, comprueba el origen y verifica el SHA-256 con `SHA256SUMS.txt`; consulta la [guía de instalación](docs/INSTALLATION.md#advertencia-de-microsoft-defender-smartscreen).

## Uso y privacidad

La base activa, la configuración y los logs se almacenan localmente. Algunas funciones necesitan conexión: actualización de precios, teselas de OpenStreetMap y rutas o geocodificación ORS. FuelOpt no incorpora telemetría propia.

Consulta la [guía de usuario](docs/USER_GUIDE.md), la [configuración](docs/CONFIGURATION.md) y la [página de privacidad](static/privacy.html).

## Desarrollo

```bat
git clone https://github.com/miguel-pajuelo/fuel-opt-project.git
cd fuel-opt-project
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-runtime.lock -r requirements-test.txt
python fuelopt_launcher.py
```

Checks principales:

```bat
python -m pytest
scripts\release_check.cmd
git diff --check
```

Consulta [Desarrollo](docs/DEVELOPMENT.md), [Arquitectura](docs/ARCHITECTURE.md) y [Publicación](docs/RELEASING.md).

## Documentación

- [Índice de documentación](docs/README.md)
- [Instalación y desinstalación](docs/INSTALLATION.md)
- [Guía de usuario](docs/USER_GUIDE.md)
- [Cómo funciona FuelOpt](static/como-funciona.html)
- [Configuración](docs/CONFIGURATION.md)
- [Solución de problemas](docs/TROUBLESHOOTING.md)
- [Seguridad](SECURITY.md)
- [Fuentes de datos y atribución](docs/DATA_SOURCES_AND_ATTRIBUTION.md)
- [Avisos de terceros](docs/THIRD_PARTY_NOTICES.md)
- [Historial de cambios](CHANGELOG.md)

## Licencia

FuelOpt se distribuye bajo [Apache License 2.0](LICENSE), Copyright 2026 Miguel Pajuelo Gómez. Los componentes de terceros conservan sus propias licencias.
