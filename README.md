# FuelOpt

FuelOpt es una aplicación local que compara estaciones de servicio y estima el coste económico de repostar teniendo en cuenta el precio, la cantidad de combustible y el desvío. Está orientada a España y presenta los resultados en una interfaz web servida únicamente desde el equipo del usuario.

> **Estado: pre-release.** La plataforma objetivo es Windows 10/11 x64. El bundle y el instalador se compilan y auditan en GitHub Actions `windows-latest`, pero la instalación limpia en una máquina virtual sin Python sigue pendiente. Las versiones instalables se publicarán en GitHub Releases cuando la primera versión sea aprobada.

## Funciones principales

- Optimización por coste efectivo, ahorro estimado o aprovechamiento del presupuesto.
- Tres objetivos explícitos: más ahorro, menor desvío y equilibrio entre ambos criterios.
- Viaje de ida o ida y vuelta, entrada por litros o presupuesto y filtro de marcas.
- Estimación del coste del desvío y presentación de alternativas.
- Rutas de OpenRouteService (ORS) cuando el usuario configura una clave.
- Aproximación geográfica Haversine cuando ORS no está disponible; no equivale a una ruta por carretera.
- Base semilla incluida y uso offline con los últimos datos válidos disponibles.
- Refresco manual, al abrir o programado cada 1, 2, 4, 8, 12 o 24 horas.
- Datos mutables separados de los recursos instalados.

FuelOpt se abre en el navegador mediante una dirección local `http://127.0.0.1:<puerto>`. El launcher utiliza los puertos 8001–8010 y verifica la identidad del servidor antes de reutilizar una instancia. No se publica un servidor en Internet.

Los objetivos no se reducen al precio por litro: consideran el desplazamiento y ordenan todas las alternativas válidas antes de aplicar el límite de resultados. Consulta el detalle en la [guía de usuario](docs/USER_GUIDE.md#objetivos-de-optimizacion).

## Datos, red y privacidad

La aplicación se instala por usuario en `%LOCALAPPDATA%\Programs\FuelOpt` y conserva configuración, base activa, caché y logs en `%LOCALAPPDATA%\FuelOpt`. La base semilla instalada es de solo lectura y se copia o reconstruye en el primer arranque sin sustituir una base activa válida.

Sin conexión se puede consultar el último catálogo disponible, pero no se pueden obtener precios nuevos, teselas de mapa ni rutas ORS. Sin clave ORS, FuelOpt conserva una funcionalidad limitada basada en aproximaciones geométricas. No incluye telemetría propia. Los proveedores externos pueden recibir la dirección IP al realizar solicitudes; consulta [Privacidad y configuración](docs/CONFIGURATION.md#privacidad-y-servicios-externos).

## Instalación para usuarios

El instalador previsto es per-user, no requiere Python, Git ni privilegios de administrador. Todavía no está firmado y la validación manual en una VM limpia es un blocker de la primera release. Consulta la [guía de instalación](docs/INSTALLATION.md).

## Desarrollo

Repositorio: <https://github.com/miguel-pajuelo/fuel-opt-project>

```bat
git clone https://github.com/miguel-pajuelo/fuel-opt-project.git
cd fuel-opt-project
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-web.txt
```

El entorno de CI está fijado a Python 3.12.10. Para ejecutar la aplicación en desarrollo:

```bat
python fuelopt_launcher.py
```

Tests y checks principales:

```bat
python -m pytest
scripts\release_check.cmd
git diff --check
```

Builds de Windows:

```bat
scripts\build_onedir.cmd
scripts\build_installer.cmd
```

Consulta [Desarrollo](docs/DEVELOPMENT.md), [Arquitectura](docs/ARCHITECTURE.md) y [Publicación](docs/RELEASING.md).

## Documentación

- [Índice de documentación](docs/README.md)
- [Instalación y desinstalación](docs/INSTALLATION.md)
- [Guía de usuario](docs/USER_GUIDE.md)
- [Configuración, ORS y CLI](docs/CONFIGURATION.md)
- [Solución de problemas](docs/TROUBLESHOOTING.md)
- [Seguridad](SECURITY.md) y [contribución](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Avisos de terceros](docs/THIRD_PARTY_NOTICES.md)
- [Backlog previo a release](docs/FINAL_REVIEW_BACKLOG.md)
- [Reconciliación de la PR #2](docs/PR2_RECONCILIATION.md)

## Licencia

La licencia principal aún no ha sido elegida. Hasta que exista un archivo `LICENSE` aprobado, el código no se ofrece bajo una licencia de código abierto y la publicación pública es un blocker. Los componentes de terceros conservan sus propias licencias; consulta [THIRD_PARTY_NOTICES](docs/THIRD_PARTY_NOTICES.md).
