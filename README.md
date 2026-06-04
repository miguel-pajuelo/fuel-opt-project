# FuelOpt

FuelOpt es un optimizador de repostaje para España. Combina precios de gasolineras, rutas por carretera y coste estimado del desvío para recomendar dónde repostar de forma más eficiente.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)](https://sqlite.org)

## Qué problema resuelve

El precio por litro más barato no siempre es la opción más barata en la práctica. Una gasolinera puede requerir un desvío que consume tiempo y combustible. FuelOpt compara estaciones cercanas a la ruta, estima el coste adicional del desvío y calcula el ahorro neto para que la recomendación tenga sentido económico.

## Funcionalidades principales

- Optimización de gasolineras basada en ruta.
- Selección de la opción de repostaje más barata según coste efectivo, no solo precio por litro.
- Cálculo de coste de desvío usando consumo medio, kilómetros extra y precio de referencia.
- Modo de entrada por litros o por euros.
- Filtrado por marcas, con catálogo visual de logos.
- Rutas y geocodificación con OpenRouteService cuando hay clave configurada.
- Fallback por Haversine cuando ORS no está disponible o no devuelve una ruta utilizable.
- Estado de frescura del catálogo para distinguir datos recientes, antiguos o degradados.
- Formulario de feedback para recibir sugerencias de usuarios.

## Cómo funciona la optimización

1. El usuario selecciona origen, destino, combustible, cantidad o presupuesto, consumo medio y marcas permitidas.
2. FuelOpt calcula la ruta principal con ORS o, si falla, usa una aproximación por distancia.
3. El sistema busca estaciones candidatas cercanas a la ruta o al área relevante.
4. Para cada estación compara el precio del combustible con una referencia.
5. Estima los kilómetros extra necesarios para desviarse.
6. Convierte ese desvío en coste de combustible.
7. Ordena las alternativas por ahorro neto o por litros útiles en modo presupuesto.

## Stack

- Python
- FastAPI
- SQLite
- HTML, CSS y JavaScript
- Leaflet
- OpenRouteService
- OpenStreetMap

## Estructura del proyecto

```text
app/
  api/              API FastAPI y endpoints web
  data_sources/     Fuentes de precios, catálogo de marcas y normalización
  optimizer/        Ranking económico y cálculo de alternativas
  routing/          ORS, geocoding y fallback de distancia
  storage/          Persistencia SQLite
data/
  cache/            Snapshot de precios
  db/               Base SQLite local del catálogo
scripts/            Refresco de catálogo, checks y utilidades
static/             Interfaz web, estilos, JS, logos y páginas públicas
tests/              Checks ligeros de frontend, adapters y pipeline
```

## Instalación local

```bash
git clone https://github.com/miguel-pajuelo/fuel-route-optimizer
cd fuel-route-optimizer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-web.txt
copy .env.example .env
```

Edita `.env` y añade solo los valores necesarios para tu entorno local. No subas `.env` al repositorio.

## Variables de entorno

Usa `.env.example` como plantilla. Las variables más relevantes son:

- `ORS_API_KEY`: clave de OpenRouteService para geocoding y rutas reales.
- `FUELOPT_ADMIN_TOKEN`: token requerido para ejecutar refrescos manuales desde `/catalog/refresh`.
- `FUELOPT_ENABLE_API_DOCS`: activa `/docs`, `/redoc` y `/openapi.json` solo si se establece en `true`.
- `GAS_DB_PATH`: ruta de la base SQLite.
- `MINETUR_SNAPSHOT_PATH`: ruta del snapshot de precios.
- `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `FEEDBACK_RECIPIENT`: SMTP opcional para el formulario de feedback.

## Ejecutar la app

```bash
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8001
```

Abre `http://127.0.0.1:8001/`.

## Refrescar el catálogo

El proyecto incluye scripts para actualizar el catálogo desde MINETUR:

```bash
python scripts/refresh_catalog.py --source minetur
```

En Windows también puedes usar:

```bat
scripts\run_refresh_catalog.cmd
```

Si el catálogo aparece como `degraded`, significa que la app no ha conseguido confirmar una descarga fresca completa y puede estar usando un snapshot/cache anterior. Revisa conectividad, respuesta de MINETUR y logs del script antes de publicar resultados.

## Seguridad

- No expongas claves de ORS, tokens de administración ni credenciales SMTP.
- No subas `.env`, credenciales locales, dumps privados, cachés temporales ni entornos virtuales.
- `/catalog/refresh` está protegido por `FUELOPT_ADMIN_TOKEN`.
- La documentación automática de FastAPI queda oculta salvo que `FUELOPT_ENABLE_API_DOCS=true`.
- Ten cuidado al desplegar públicamente: las búsquedas de ruta pueden pasar por ORS y los mapas por proveedores externos de tiles.

## Limitaciones conocidas

- Proyecto en estado prototipo/demo.
- La frescura de datos depende de la disponibilidad de las fuentes externas.
- Algunas estimaciones pueden usar aproximaciones por distancia cuando ORS no responde.
- No está endurecido para producción sin configurar observabilidad, límites, despliegue seguro y gestión robusta de secretos.

## Roadmap

- Despliegue público con HTTPS, variables secretas y refresco programado.
- Monitorización de catálogo y alertas cuando el estado pase a degradado.
- Mejora de scoring para tiempo de desvío, peajes y tráfico.
- Historial de frescura de precios por fuente.
- Tests end-to-end de la experiencia web.

## Licencia

License not specified yet.
