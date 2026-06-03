# Auditoria tecnica y funcional del proyecto FuelOpt

Fecha de revision: 2026-05-04
Raiz analizada: `C:\Users\migue\OneDrive\Escritorio\MIGUEL\SIDE PROJECTS\GAS SCRAPING`

## 1. Resumen ejecutivo

El proyecto es una aplicacion local de optimizacion de repostaje llamada FuelOpt. Su objetivo es ayudar a una persona usuaria a comparar gasolineras en Espana en funcion del tipo de combustible, litros o presupuesto, origen, destino, consumo medio del vehiculo, marcas seleccionadas y coste del desvio.

La aplicacion esta construida principalmente en Python con FastAPI como backend, una interfaz web estatica servida por el propio backend, una base de datos SQLite local y scripts de refresco de catalogo. El sistema puede funcionar como aplicacion web local, como API, como paquete portable para Windows y mantiene compatibilidad con una CLI antigua centrada en Ballenoil.

El valor funcional principal es calcular una recomendacion de repostaje que no se limita al precio por litro. El sistema estima el coste efectivo considerando:

- Precio del combustible.
- Cantidad a repostar o presupuesto en euros.
- Distancia adicional hasta la gasolinera.
- Consumo medio del vehiculo.
- Modo de optimizacion: economico, equilibrado o minimo desvio.
- Filtro opcional por marcas.
- Ruta local con regreso al origen o ruta origen-destino.

Estado actual observado:

- Implementado: API FastAPI, frontend web con mapa Leaflet, optimizador, SQLite local, carga desde MINETUR/snapshots/caches, refresco seguro con base candidata, endpoints de estado, filtros de marca y tests de pipeline.
- Parcialmente implementado o condicionado: rutas reales y geocodificacion dependen de `ORS_API_KEY`; si ORS falla, el frontend intenta fallback a estimacion Haversine para `/optimize`, pero el pintado de ruta por `/route/stopover` requiere ORS.
- Simulado/cacheado: la aplicacion sirve datos desde `data/db/gas_stations.sqlite` y caches locales. La base activa indica estado `degraded` porque el ultimo refresco uso snapshot local tras fallo TLS contra MINETUR.
- Riesgo critico: existe una clave real de OpenRouteService en `.env`. Debe rotarse y excluirse de cualquier entrega, repositorio o paquete no controlado.

## 2. Descripcion funcional del sistema

### Capacidades disponibles para el usuario

La interfaz principal esta en `static/index.html`, `static/app.js` y `static/styles.css`, servida por `app/api/main.py` en `GET /`.

Desde la UI el usuario puede:

- Buscar un punto de salida en el mapa mediante `/geocode`.
- Seleccionar origen haciendo doble clic en el mapa.
- Mantener "Regreso al origen" activo para una busqueda local o desactivarlo para definir una llegada distinta.
- Elegir tipo de combustible desde `/fuels`.
- Elegir objetivo de optimizacion: `economic`, `balanced` o `minimal_detour`.
- Introducir cantidad en litros o presupuesto en euros.
- Introducir consumo medio en L/100 km.
- Filtrar marcas mediante checkboxes cargados desde `/brands`.
- Ejecutar el calculo con `POST /optimize`.
- Ver la mejor gasolinera recomendada, precio, coste efectivo, ahorro neto o litros aproximados segun modo, desvio extra y ranking de alternativas.
- Seleccionar alternativas del ranking.
- Forzar refresco del catalogo con `POST /catalog/refresh`.
- Consultar implicitamente el estado de actualizacion del catalogo con `/catalog/status`.

### Flujos principales

Flujo local con regreso al origen:

1. El usuario selecciona origen.
2. `static/app.js` copia origen como destino si `return_to_origin` esta activo.
3. El usuario selecciona combustible, litros o euros, consumo y marcas.
4. El frontend envia coordenadas iguales de origen y destino a `POST /optimize`.
5. `app/optimizer/ranking.py` detecta que origen y destino son practicamente el mismo punto mediante `_same_place`.
6. Se usa busqueda radial local (`local_radius`) con radio preferente por defecto de 50 km.
7. Se ordenan candidatos por coste efectivo o litros netos.
8. La UI muestra el resultado y, si ORS esta disponible, dibuja ruta origen-gasolinera-destino.

Flujo origen-destino:

1. El usuario desactiva regreso al origen.
2. Selecciona salida y llegada.
3. El frontend envia ambas coordenadas a `POST /optimize`.
4. Si `use_ors=true`, `app/routing/ors.py` intenta obtener geometria real de ruta para filtrar por corredor.
5. Si ORS falla en la optimizacion, `static/app.js` reintenta `/optimize` con `use_ors=false`.
6. Sin ORS, el backend usa estimacion Haversine con factor de desvio.
7. El optimizador usa corredor de ruta o linea recta, calcula desvio y coste efectivo.

Flujo por litros:

- El usuario introduce litros.
- `static/app.js` envia `input_mode='liters'`, `liters=<valor>`.
- `app/optimizer/ranking.py` calcula coste de compra como `liters * price_eur_l`.
- La ordenacion principal usa `effective_total_cost_eur + detour_penalty`.

Flujo por presupuesto:

- El usuario cambia el selector a euros.
- `static/app.js` envia `input_mode='budget'`, `budget_amount_eur=<valor>` y `liters=1` solo para satisfacer validacion del modelo.
- `app/optimizer/ranking.py` calcula litros brutos como `budget / price_eur_l`.
- Resta litros gastados en el desvio.
- Ordena maximizando litros netos.

## 3. Arquitectura general

### Tecnologias usadas

- Python 3, segun bytecode observado para 3.12 y 3.13 en `__pycache__`.
- FastAPI `0.136.0`, Starlette `1.0.0`, Pydantic `2.13.2`, Uvicorn `0.44.0`: `requirements-web.txt`.
- Requests `2.32.5`: llamadas HTTP a MINETUR y OpenRouteService.
- BeautifulSoup `4.14.3`: parsing de HTML de detalle Ballenoil.
- SQLite: persistencia local en `data/db/gas_stations.sqlite`.
- Leaflet `1.9.4` desde CDN `unpkg.com`: mapa de la UI.
- OpenStreetMap tiles: capa visual del mapa.
- OpenRouteService: geocodificacion, reverse geocoding, matrices y rutas reales.
- PyInstaller: empaquetado del launcher Windows, configurado en `FuelOptLauncher.spec` y scripts `.cmd`.

### Estructura de carpetas

- `app/`: codigo principal Python.
- `app/api/`: FastAPI, endpoints y carga del frontend.
- `app/data_sources/`: conectores y normalizacion de fuentes de datos.
- `app/optimizer/`: logica de optimizacion y ranking.
- `app/routing/`: integracion con OpenRouteService y proveedor de rutas.
- `app/storage/`: SQLite, validacion y publicacion segura de base de datos.
- `app/legacy_cli/`: CLI heredada y scraping historico.
- `static/`: frontend web estatico.
- `scripts/`: tareas de reconstruccion, refresco, normalizacion y release.
- `data/cache/`: snapshots y caches JSON/TXT.
- `data/db/`: base SQLite activa.
- `data/reports/`: logs y reportes de refresco/launcher.
- `docs/`: documentacion operativa y catalogo de rotulos.
- `tests/`: checks manuales/ejecutables del pipeline, frontend, adaptadores y refresco.
- `build/` y `dist/`: artefactos generados por PyInstaller y paquete portable.

### Diagrama textual

```text
Usuario
  |
  v
static/index.html + static/app.js + Leaflet
  |
  | HTTP local
  v
app/api/main.py - FastAPI
  |
  +--> app/routing/ors.py - ORS geocoding/routing si hay clave
  |
  +--> app/optimizer/ranking.py - calculo de candidatos y ranking
  |       |
  |       v
  |   app/storage/database.py - lectura de estaciones y precios
  |
  +--> scripts/refresh_catalog.py - refresco bajo demanda
          |
          v
      app/data_sources/minetur.py + caches locales
          |
          v
      data/db/gas_stations.sqlite
```

## 4. Modulos principales del codigo

### `main.py`

Responsabilidad:

- Punto de entrada compatible.
- Reexporta nombres de la CLI antigua desde `app/legacy_cli/*`.
- Arranca la API web por defecto mediante Uvicorn.
- Permite `python main.py --legacy-cli` para la CLI heredada.

Entradas:

- Argumentos CLI: `--legacy-cli`, `--host`, `--port`, `--reload`.

Salidas:

- Servidor web en Uvicorn o ejecucion de CLI.

Dependencias:

- `app.api.main:app`.
- `app.legacy_cli.*`.

### `fuelopt_launcher.py`

Responsabilidad:

- Launcher local/portable para Windows.
- Detecta raiz del proyecto.
- Arranca servidor en segundo plano si `/health` no responde.
- Abre navegador.
- Lanza refresco en segundo plano si el catalogo tiene mas de 4 horas o no es valido.
- Gestiona logs en `data/reports/launcher.log`, `launcher_server.log` y `launcher_refresh.log`.

Funciones relevantes:

- `project_root()`: localiza raiz en modo fuente o PyInstaller.
- `catalog_refresh_due()`: decide si refrescar por antiguedad o catalogo vacio.
- `start_server()`: arranca proceso servidor.
- `start_refresh_worker()`: arranca refresco.
- `run_server()`: ejecuta Uvicorn.

Riesgos:

- Por defecto escucha en `0.0.0.0:8001`, lo que expone la app a la LAN si el firewall lo permite.
- No hay autenticacion.

### `app/config.py`

Responsabilidad:

- Define rutas base y configuracion.
- Carga `.env` manualmente sin dependencia externa.
- Centraliza parametros de optimizacion y rutas de datos.

Datos leidos:

- `ORS_API_KEY`.
- `GAS_DB_PATH`.
- `MINETUR_SNAPSHOT_PATH`.
- `BALLENOIL_RESULT_PATH`.
- `BALLENOIL_PRICES_PATH`.
- `CONSUMPTION_L_100KM`.
- `MAX_ROUTE_CANDIDATES`.
- `PREFILTER_RADIUS_KM`.
- `LOCAL_SEARCH_RADIUS_KM`.
- `CORRIDOR_RADIUS_KM`.
- `MAX_SEARCH_EXTENT_KM`.
- `OPTIMIZATION_MODE`.
- `ROUTE_DETOUR_FACTOR`.
- `SAME_PLACE_THRESHOLD_KM`.
- `MAX_BRANDS_PER_REQUEST`.

Riesgo:

- `.env` contiene una clave real de ORS. El archivo `.env.example` indica correctamente que `.env` no debe committearse, pero la clave esta presente en el entorno revisado.

### `app/models.py`

Responsabilidad:

- Define entidades de dominio como dataclasses.

Entidades:

- `Station`: gasolinera, marca, direccion, municipio, provincia, coordenadas, fuente, raw original y metadatos de marca.
- `Price`: precio por estacion y combustible.
- `Coordinates`: latitud/longitud.
- `OptimizationInput`: parametros normalizados para optimizacion.
- `CandidateResult`: resultado calculado para una estacion candidata.

Mapa de combustibles:

- `FUEL_FIELDS` mapea claves internas a campos MINETUR:
  - `gasoleo_a`: `Precio Gasoleo A`.
  - `gasoleo_b`: `Precio Gasoleo B`.
  - `gasoleo_prem`: `Precio Gasoleo Premium`.
  - `gasolina_95`: `Precio Gasolina 95 E5`.
  - `gasolina_98`: `Precio Gasolina 98 E5`.
  - `gasolina_98e10`: `Precio Gasolina 98 E10`.

### `app/api/main.py`

Responsabilidad:

- Backend HTTP principal.
- Sirve frontend y endpoints de consulta, geocodificacion, refresco y optimizacion.

Endpoints confirmados:

- `GET /`: UI HTML desde `app/api/ui.py`.
- `GET /health`: comprueba tablas SQLite.
- `GET /fuels`: lista combustibles soportados.
- `GET /brands`: marcas canonicas con conteo de estaciones.
- `GET /brands/raw`: conteo de rotulos originales.
- `GET /catalog/status`: metadata de catalogo.
- `POST /catalog/refresh`: refresco sincrono protegido por lock de proceso.
- `GET /prices/status`: resumen de precios por combustible.
- `GET /stations`: listado paginado de estaciones.
- `GET /geocode`: busqueda ORS.
- `GET /reverse-geocode`: reverse geocoding ORS.
- `POST /route/stopover`: geometria ORS para origen-gasolinera-destino.
- `POST /optimize`: calculo principal.

Validaciones relevantes:

- `fuel_type` debe existir en `FUEL_FIELDS`.
- `input_mode` solo acepta `liters` o `budget`.
- En modo budget, `budget_amount_eur` es obligatorio.
- Latitud/longitud se validan con rangos Pydantic.
- Se limita `result_limit` a 100 y `max_candidates` a 250.
- Se limita numero de marcas segun `MAX_BRANDS_PER_REQUEST`, por defecto 10.
- Alias deprecated `preferred_search_radius_km` y `preferred_corridor_km` siguen aceptados, pero se rechazan si contradicen los campos nuevos.

Dependencias:

- `app.optimizer.ranking.optimize_from_db_with_context`.
- `app.routing.ors.ORSRouteProvider`.
- `app.storage.database`.
- `app.data_sources.brand_catalog`.

### `app/api/ui.py`

Responsabilidad:

- Cargar `static/index.html`.
- Mantener el frontend fuera de cadenas Python embebidas.

### `static/index.html`

Responsabilidad:

- Estructura de la aplicacion web.
- Carga Leaflet desde CDN y assets locales.
- Define controles de salida/llegada, combustible, objetivo, litros/euros, consumo y marcas.

Datos que introduce el usuario:

- Origen y destino.
- Cantidad en litros o presupuesto.
- Consumo medio.
- Tipo de combustible.
- Modo de optimizacion.
- Marcas seleccionadas.

### `static/app.js`

Responsabilidad:

- Estado y comportamiento de la UI.
- Integracion con mapa Leaflet.
- Geocodificacion, reverse geocoding y seleccion por doble clic.
- Construccion de payloads para `/optimize`.
- Fallback de ORS a Haversine para optimizacion.
- Render de resultados y ranking.
- Refresco de catalogo y polling de estado.

Funciones relevantes:

- `parsePositiveDecimal()`: valida inputs positivos.
- `selectedBrands()`, `allBrandsSelected()`, `renderBrands()`: gestion de marcas.
- `setInputMode()`: alterna litros/euros.
- `requestOptimization()`: llama `/optimize`; si ORS falla y `use_ors=true`, reintenta con `use_ors=false`.
- `renderResult()`: muestra mejor resultado y alternativas.
- `refreshSelectedRoute()`: llama `/route/stopover` para pintar ruta real con ORS.

Limitaciones observadas:

- La UI fija `max_search_extent_km=150`, `local_search_radius_km=50`, `corridor_radius_km=10`, `max_candidates=75` y `result_limit=10`; no expone esos parametros al usuario.
- La UI carga solo las primeras 24 marcas en `renderBrands(brands.slice(0, 24))`.
- El pintado de ruta seleccionada depende de ORS; no se ha encontrado fallback visual a linea Haversine para `/route/stopover`.
- Hay textos con problemas de codificacion en los archivos HTML/CSS/JS, por ejemplo caracteres como `Ãš` o `DesvÃo`.

### `static/styles.css`

Responsabilidad:

- Layout responsive de sidebar, mapa, resultados, ranking y controles.

Observaciones:

- No contiene logica de negocio.
- Usa una paleta visual definida con variables CSS.

### `app/optimizer/ranking.py`

Responsabilidad:

- Nucleo de negocio.
- Selecciona candidatos, estima rutas/desvios, calcula costes/litros netos y ordena resultados.

Funciones principales:

- `haversine_km()`: distancia geodesica.
- `HaversineEstimateProvider`: proveedor de distancias aproximadas con factor de desvio.
- `_same_place()`: decide si origen y destino son equivalentes.
- `_radial_candidates()`: candidatos para busqueda local.
- `_corridor_candidates()`: candidatos alrededor de corredor de ruta.
- `_economically_expand_pool()`: expansion economica fuera del area preferida.
- `prefilter_candidates_with_trace()`: prefiltrado con trazabilidad.
- `optimize_candidates()`: calculo completo por candidato.
- `_annotate_results()`: calcula referencia, ahorro y explicacion.
- `optimize_from_db_with_context()`: orquesta lectura de DB, prefiltrado y ranking.

Entradas:

- `OptimizationInput`.
- Estaciones y precios desde SQLite.
- Proveedor de ruta ORS o Haversine.

Salidas:

- Lista de `CandidateResult`.
- Contexto de busqueda: politica, tamano de universo, pool, expansion economica, forma de busqueda y numero de resultados.

### `app/routing/ors.py`

Responsabilidad:

- Integracion con OpenRouteService.

Funciones:

- `geocode_candidates()`: geocodificacion de direcciones en Espana.
- `geocode_address()`: primer resultado como coordenadas.
- `reverse_geocode_coordinates()`: coordenadas a etiqueta.
- `ORSRouteProvider._matrix()`: matriz de distancias por carretera.
- `ORSRouteProvider.route_geometry()`: geometria GeoJSON de ruta.

Riesgos:

- Requiere `ORS_API_KEY`.
- Usa API externa y puede fallar por red, cuota, clave invalida o limites del proveedor.
- El backend maneja errores con HTTP 400/502/504 segun caso.

### `app/storage/database.py`

Responsabilidad:

- Crear y migrar esquema SQLite.
- Insertar catalogo completo.
- Consultar estaciones, marcas, precios, estado y salud.

Tablas:

- `stations`: gasolineras y metadatos de marca/direccion/coordenadas.
- `prices`: precios por estacion y tipo de combustible.
- `catalog_metadata`: claves de estado, version, fuente y degradacion.

Funciones relevantes:

- `init_db()`: crea tablas e indices.
- `replace_catalog()`: reemplaza estaciones, precios y metadata.
- `list_stations()`: listado paginado.
- `canonical_brand_counts()`: conteos para UI.
- `get_candidates_with_price()`: candidatos con precio por combustible.
- `get_candidates_with_price_in_bbox()`: candidatos dentro de bounding box.
- `catalog_status()`: resumen de catalogo.
- `price_status()`: resumen por combustible.

Datos observados en la SQLite activa:

- `stations`: 12.187 registros.
- `prices`: 37.298 registros.
- `source`: `MINETUR_SNAPSHOT`.
- `source_reference_date`: `2026-04-23T23:09:05+0200`.
- `built_at`: `2026-04-26T12:25:27.131572+00:00`.
- `refresh_status`: `degraded`.
- `degraded_reasons`: fallo TLS al intentar descargar MINETUR en vivo.
- Precios con `updated_at` nulo en la consulta directa, aunque metadata mantiene fecha de referencia del snapshot.

### `app/storage/validation.py`

Responsabilidad:

- Validar una base candidata antes de publicarla.

Reglas por defecto:

- Minimo 8.000 estaciones.
- Minimo 20.000 precios.
- Advertencia si ratio de marca desconocida supera 50%.
- Requiere precios para `gasoleo_a` y `gasolina_95`.

### `app/storage/publish.py`

Responsabilidad:

- Publicacion segura de SQLite candidata.
- Gestion de WAL/SHM.
- Backup atomico de base activa.
- Limpieza de backups antiguos.

Importancia:

- Evita exponer a usuarios una DB parcialmente escrita durante refrescos.

### `app/data_sources/minetur.py`

Responsabilidad:

- Fuente oficial MINETUR.
- Descarga, parsing, normalizacion y construccion de catalogo.
- Carga de snapshots y caches.

Funciones relevantes:

- `fetch_minetur_items()`: descarga `ListaEESSPrecio` con cabeceras de navegador.
- `to_float_es()`: convierte numeros espanoles con coma decimal.
- `extract_ideess()`: obtiene identificador oficial.
- `station_from_minetur_item()`: convierte item MINETUR a `Station`.
- `prices_from_minetur_item()`: extrae precios segun `FUEL_FIELDS`.
- `build_catalog_from_minetur()`: genera estaciones y precios.
- `load_prices_cache_as_catalog()`: fallback degradado desde cache de precios.
- `quality_report()`: metricas de calidad.

Tratamiento de datos invalidos:

- Estaciones sin `IDEESS`, latitud o longitud se descartan.
- Precios no parseables se omiten.
- Rotulos no reconocidos reciben confianza 0.5 o `UNKNOWN` si no hay marca.

### `app/data_sources/brand_catalog.py`

Responsabilidad:

- Catalogo de marcas y aliases.
- Normalizacion de rotulos MINETUR a marcas canonicas.
- Lista de marcas para la UI.

Ejemplos:

- `REPSOL`, `CAMPSA`, `CAMPSA EXPRESS`, `PETRONOR` se agrupan como `REPSOL`.
- `CEPSA`, `MOEVE`, `CEPSA-MOEVE`, `MOEVE-CEPSA`, `DISA` se agrupan como `CEPSA`.
- Rotulos sin marca como `SIN ROTULO`, `LIBRE`, `NO TIENE` se convierten a `UNKNOWN`.

Trazabilidad externa:

- `docs/rotulos_catalog.txt` documenta conteos y decisiones de agrupacion.

### `app/data_sources/adapters.py`

Responsabilidad:

- Patron de adaptadores por marca.
- `MineturFilterAdapter` filtra items MINETUR por rotulos exactos.
- `BrandRegistry` registra adaptadores y permite procesar todas o algunas marcas.

### `app/data_sources/adapters_scraping.py`

Responsabilidad:

- Adaptador de scraping Ballenoil heredado.
- Usa `app.legacy_cli.scraper.scrape_ballenoil_diesel()`.

Estado:

- Existe, pero el flujo principal web actual no scrapea en cada uso. La documentacion `README_WEB.md` indica que el path de UI no debe scrapear y debe servirse desde catalogo/cache.

### `app/data_sources/ballenoil.py`

Responsabilidad:

- Parser de paginas de detalle Ballenoil.
- Extrae direccion y tokens de matching desde HTML.

Uso confirmado:

- Cubierto por `tests/sanity_check.py` y `tests/web_pipeline_check.py`.

### `scripts/rebuild_station_catalog.py`

Responsabilidad:

- Reconstruir `data/db/gas_stations.sqlite` desde fuente seleccionada.

Fuentes:

- `auto`: intenta MINETUR vivo y cae a snapshot/cache.
- `minetur`: exige MINETUR vivo.
- `snapshot`: usa `data/cache/minetur_snapshot.json`.
- `prices-cache`: usa `data/cache/ballenoil_precios.json`.
- `ballenoil-cache`: usa `data/cache/ballenoil_espana_combustible.txt`.

Salida:

- SQLite activa o ruta indicada por `--db`.
- Reporte JSON opcional.

### `scripts/refresh_catalog.py`

Responsabilidad:

- Pipeline seguro de refresco.

Flujo:

1. Crea lock en `data/reports/catalog_refresh.lock`.
2. Genera `gas_stations.next.sqlite`.
3. Descarga o carga fuente.
4. Escribe DB candidata.
5. Valida con `validate_catalog_db()`.
6. Publica sustituyendo la DB activa solo si valida.
7. Publica snapshot candidato.
8. Limpia candidatos y backups segun retencion.
9. Escribe `catalog_refresh_report.json`.

### `scripts/renormalize_catalog_brands.py`

Responsabilidad:

- Reaplicar normalizacion de marcas a una SQLite existente.
- Actualiza campos de marca y metadata de cobertura.

### `scripts/*.cmd`, `FuelOpt.cmd`, `FuelOptLauncher.spec`

Responsabilidad:

- Construccion y empaquetado Windows.
- `scripts/build_launcher.cmd`: build PyInstaller.
- `scripts/package_release.cmd`: zip portable.
- `scripts/release_check.cmd`: validaciones de release.
- `FuelOpt.cmd`: entrada para usuarios no tecnicos.

### `app/legacy_cli/*`

Responsabilidad:

- Codigo heredado de CLI y scraping Ballenoil.
- `main.py --legacy-cli` conserva compatibilidad.

Estado:

- No parece ser el flujo principal actual.
- Algunos archivos contienen BOM inicial, detectado al intentar parsearlos con `ast.parse` leyendo como UTF-8 puro. No se ha validado impacto funcional en ejecucion normal.

## 5. Modelo de datos y fuentes de informacion

### Entidades principales

`Station` en `app/models.py`:

- `station_id`: identificador unico. Para MINETUR corresponde a `IDEESS`; para Ballenoil cache/scraper puede ser `ballenoil:<url>`.
- `brand`, `brand_canonical`, `brand_group`: marca normalizada.
- `brand_label_raw`: rotulo original.
- `brand_confidence`: 1.0 si coincide con catalogo, 0.5 si no reconocido pero no vacio, 0.0 para `UNKNOWN`.
- `name`, `address`, `postal_code`, `municipality`, `province`.
- `lat`, `lon`.
- `source`.
- `active`.
- `last_seen_at`.
- `raw`: payload original, no expuesto en `public_dict()`.

`Price`:

- `station_id`.
- `fuel_type`.
- `price_eur_l`.
- `updated_at`.
- `source`.

`OptimizationInput`:

- Origen/destino.
- Combustible.
- Modo de entrada: litros o presupuesto.
- Litros, presupuesto, consumo.
- Radios y limites de busqueda.
- Modo de optimizacion.
- Factor de desvio.

`CandidateResult`:

- Estacion.
- Precio.
- Distancias estimadas o reales.
- Desvio.
- Litros gastados en ruta.
- Coste de compra.
- Coste de viaje adicional.
- Coste efectivo.
- Ahorro frente a referencia.
- Litros netos en modo presupuesto.
- Motivo textual de seleccion.

### Fuentes de datos

Fuente oficial principal:

- MINETUR: `https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/`.
- Codigo: `app/data_sources/minetur.py`.
- Snapshot local: `data/cache/minetur_snapshot.json`.

Fuente de rutas/geocodificacion:

- OpenRouteService.
- Codigo: `app/routing/ors.py`.
- Clave: `ORS_API_KEY` en `.env`.

Fuente de mapa:

- Leaflet desde `https://unpkg.com`.
- Tiles OpenStreetMap desde `https://{s}.tile.openstreetmap.org`.

Caches locales:

- `data/cache/minetur_snapshot.json`: snapshot MINETUR.
- `data/cache/ballenoil_mapping.json`: mapping Ballenoil.
- `data/cache/ballenoil_precios.json`: cache de precios.
- `data/cache/ballenoil_espana_combustible.txt`: cache antigua Ballenoil.

Persistencia:

- `data/db/gas_stations.sqlite`: SQLite activa.
- `catalog_metadata`: estado de construccion, fuente, version y degradacion.

Datos introducidos por usuario:

- Coordenadas via busqueda o doble clic.
- Modo regreso al origen.
- Tipo de combustible.
- Litros o euros.
- Consumo medio.
- Marcas.
- Objetivo de optimizacion.

Datos calculados:

- Distancias por Haversine u ORS.
- Desvio extra.
- Litros gastados por desvio.
- Coste de viaje adicional.
- Coste efectivo.
- Litros netos.
- Ahorro neto frente a referencia.
- Ranking y motivo de seleccion.

## 6. Logica de negocio

### Seleccion de combustible

La seleccion se basa en `FUEL_FIELDS` de `app/models.py`. El endpoint `/fuels` expone las claves y etiquetas. El optimizador rechaza cualquier `fuel_type` no incluido.

### Litros frente a presupuesto

Modo litros:

```text
fuel_purchase_cost_eur = liters * price_eur_l
gross_refuel_liters = liters
```

Modo presupuesto:

```text
gross_refuel_liters = budget_amount_eur / price_eur_l
fuel_purchase_cost_eur = budget_amount_eur
```

Codigo:

- `_candidate_gross_liters()` en `app/optimizer/ranking.py`.
- `_candidate_purchase_cost()` en `app/optimizer/ranking.py`.

### Coste de desplazamiento

El sistema calcula el combustible gastado solo por el desvio adicional:

```text
route_via_station_km = origin_to_station_km + station_to_destination_km
extra_detour_km = max(0, route_via_station_km - direct_route_km)
liters_spent_on_route = extra_detour_km / 100 * consumption_l_100km
travel_cost_eur = liters_spent_on_route * reference_price
```

Codigo:

- `optimize_candidates()` en `app/optimizer/ranking.py`.

La referencia de precio usada para coste por km es la mediana de precios candidatos:

```text
reference_price = median(candidate_prices)
cost_per_km = consumption_l_100km / 100 * reference_price
```

Codigo:

- `_reference_price()`.
- `_cost_per_km()`.

### Coste efectivo

En modo litros:

```text
effective_total_cost_eur = fuel_purchase_cost_eur + extra_travel_cost_eur
optimization_score_eur = effective_total_cost_eur + detour_penalty_eur
```

En modo presupuesto:

```text
net_liters = gross_refuel_liters - liters_spent_on_route
optimization_score = -net_liters + detour_penalty_liters
```

Se descartan candidatos con `price <= 0` o `net_liters <= 0`.

### Modos de optimizacion

Definidos en `MODE_DETOUR_PENALTY_EUR_KM` de `app/optimizer/ranking.py`:

- `economic`: penalizacion 0.0 EUR/km.
- `balanced`: penalizacion 0.08 EUR/km.
- `minimal_detour`: penalizacion 0.25 EUR/km.

El modo afecta el score, no cambia directamente los precios.

### Busqueda local o por corredor

Si origen y destino estan a menos de `same_place_threshold_km`, por defecto 1 km:

- Se usa busqueda radial desde origen.
- Radio preferente por defecto: 50 km.

Si origen y destino difieren:

- Se usa corredor de ruta.
- Radio de corredor por defecto: 10 km.
- Con ORS, el corredor sigue geometria real.
- Sin ORS, se genera una linea recta con `_line_geometry()`.

Codigo:

- `_same_place()`.
- `_radial_candidates()`.
- `_corridor_candidates()`.
- `_distance_to_geometry_km()`.

### Expansion economica

El area preferente no es siempre limite duro si `economic_expansion_enabled=true`.

La funcion `_economically_expand_pool()`:

- Evalua umbrales crecientes hasta `max_search_extent_km`.
- Calcula score aproximado por precio y distancia.
- Continua expandiendo mientras una estacion barata externa pueda mejorar el coste.
- Para si el coste optimista del siguiente tramo ya no puede superar el mejor score observado, con margen `ECONOMIC_EPSILON_EUR = 0.10`.

### Seleccion del pool

`_select_profiled_pool()` mezcla tres perfiles:

- Candidatos mas cercanos.
- Candidatos mas baratos.
- Candidatos con mejor score aproximado.

El objetivo es no perder opciones baratas por filtrar solo por distancia.

### Referencia y ahorro

`_annotate_results()` toma como referencia la alternativa con menor desvio y menor coste efectivo:

```text
reference = min(results, key=(extra_detour_km, effective_total_cost_eur))
net_savings_vs_reference_eur = reference_cost - candidate_effective_total_cost
```

En modo presupuesto se usa `net_liters_vs_reference` en lugar de ahorro monetario.

### Filtros por marca

El backend acepta:

- `brand`: string legacy.
- `brands`: lista.

`app/api/main.py` normaliza a mayusculas, elimina duplicados y limita el numero. `app/storage/database.py` filtra por `brand_canonical`.

La UI:

- Carga marcas desde `/brands`.
- Muestra hasta 24.
- Si todas estan seleccionadas, omite `brands` en el payload para significar "todas".
- Bloquea seleccionar mas de 10 si no estan todas.

## 7. Flujo de datos

### Flujo de refresco de catalogo

1. `scripts/refresh_catalog.py` recibe fuente y parametros.
2. Intenta adquirir lock en `data/reports/catalog_refresh.lock`.
3. `scripts/rebuild_station_catalog.py::load_catalog()` descarga MINETUR o carga snapshot/cache.
4. `app/data_sources/minetur.py` convierte items en `Station` y `Price`.
5. `app/storage/database.py::replace_catalog()` escribe `gas_stations.next.sqlite`.
6. `app/storage/validation.py::validate_catalog_db()` valida conteos minimos y combustibles requeridos.
7. `app/storage/publish.py::publish_sqlite_candidate()` sustituye la DB activa.
8. Se escribe reporte en `data/reports/catalog_refresh_report.json`.

Si MINETUR falla:

- `--source auto` cae a snapshot si existe.
- Si usa cache de precios, metadata puede degradarse por marca/direccion desconocidas.
- El estado `degraded` queda reflejado en `catalog_metadata`.

### Flujo de optimizacion desde UI

1. Usuario elige origen/destino en `static/app.js`.
2. El frontend valida cantidad y consumo con `parsePositiveDecimal()`.
3. Crea payload con coordenadas, combustible, modo, cantidad, consumo, radios fijos y marcas si aplica.
4. Llama `POST /optimize`.
5. `app/api/main.py` valida con Pydantic y reglas adicionales.
6. Si `use_ors=true`, instancia `ORSRouteProvider`; si no, `HaversineEstimateProvider`.
7. `optimize_from_db_with_context()` obtiene geometria si procede.
8. Se prefiltran candidatos desde SQLite por bounding box y combustible.
9. Se calcula score por candidato.
10. Se ordena y anota el ranking.
11. FastAPI devuelve `best`, `items`, `search` y warnings.
12. `static/app.js::renderResult()` pinta resultado, alternativa y marcador.
13. `static/app.js::refreshSelectedRoute()` intenta pintar ruta real con `/route/stopover`.

### Flujo de geocodificacion

1. Usuario escribe texto en busqueda de mapa.
2. `static/app.js` llama `/geocode?q=...&size=10`.
3. `app/api/main.py` delega en `geocode_candidates()`.
4. ORS devuelve candidatos.
5. La UI muestra sugerencias y guarda lat/lon seleccionadas.

Si falta `ORS_API_KEY`, el backend devuelve error 400 y la UI no puede resolver busquedas por texto.

## 8. Manejo de errores y casos limite

### Controlados

- DB inaccesible en `/health`: HTTP 503.
- Falta `ORS_API_KEY` para geocodificacion: HTTP 400.
- Fallo ORS de geocodificacion/rutas: HTTP 502 o 504 segun endpoint.
- `fuel_type` no soportado: HTTP 400.
- `input_mode` invalido: HTTP 400.
- Modo presupuesto sin `budget_amount_eur`: HTTP 422.
- Lat/lon fuera de rango: validacion Pydantic.
- Demasiadas marcas: HTTP 400.
- Alias de radio contradictorios: HTTP 400.
- Refresco concurrente: HTTP 429 o `refresh_status=skipped`.
- Refresco que no valida: HTTP 422 desde `/catalog/refresh`.
- Candidatos sin precio o precio no positivo: omitidos.
- Candidatos cuyo desvio consume todo el combustible/presupuesto neto: omitidos.
- Estaciones MINETUR sin ID/coordenadas: descartadas.
- Precios no parseables: omitidos.

### Parcialmente controlados

- Si ORS falla en `/optimize`, la UI reintenta con Haversine. Esta logica esta en `static/app.js::requestOptimization()`.
- Si ORS falla en `/route/stopover`, la UI muestra error y no pinta ruta real. No se ha encontrado fallback visual equivalente.
- Si no hay candidatos con la politica actual, la API devuelve `best=null` y la UI muestra "Sin resultado".
- Si una fuente esta degradada, se registra en metadata, pero la UI solo muestra fecha de refresco y no expone claramente los motivos de degradacion.

### No encontrados o insuficientemente cubiertos

- No se ha encontrado autenticacion ni control de acceso.
- No se ha encontrado rate limiting propio.
- No se ha encontrado cifrado de `.env`, SQLite ni logs.
- No se ha encontrado politica formal de retencion de logs, salvo rotacion del launcher.
- No se ha encontrado gestion de cuotas ORS ni cache de geocodificacion.
- No se ha encontrado verificacion automatica de freshness de precios en `/optimize` que bloquee datos antiguos.
- No se ha encontrado cobertura de tests end-to-end con navegador real.

## 9. Seguridad y privacidad

### Datos sensibles potenciales

El sistema no maneja cuentas de usuario, pagos ni autenticacion. Sin embargo, puede manejar informacion sensible o semisensible:

- Ubicaciones introducidas por el usuario: origen y destino.
- Preferencias de combustible, marcas, consumo y presupuesto.
- Clave ORS.
- Logs de servidor que pueden contener rutas o errores.
- Base local con datos publicos de gasolineras y precios.

### Riesgos identificados

Clave real en `.env`:

- Se ha encontrado `ORS_API_KEY` con valor real en `.env`.
- Riesgo: exposicion accidental en repositorio, zip portable, logs, backups o capturas.
- Accion prioritaria: rotar clave y sustituir `.env` por `.env.example` en cualquier entrega.

Exposicion LAN:

- `fuelopt_launcher.py` usa host por defecto `0.0.0.0` y puerto `8001`.
- Riesgo: cualquier dispositivo de la LAN podria acceder si firewall lo permite.
- No hay autenticacion.

API externa:

- ORS recibe direcciones/coordenadas buscadas.
- Debe comunicarse como transferencia a tercero.
- No se ha encontrado consentimiento, aviso de privacidad ni minimizacion especifica.

Logs:

- `data/reports/*.log` almacena errores y actividad del launcher/servidor.
- No se ha encontrado evidencia de que se registre la clave ORS completa, pero si hay errores de proveedores y rutas de archivos.
- Recomendable revisar logs antes de compartir paquetes.

Frontend:

- `static/app.js` incluye `escapeHtml()` y tests verifican uso para fragmentos dinamicos de HTML.
- Riesgo residual: todo render dinamico futuro debe mantener escape.

CORS/autenticacion:

- No se ha encontrado configuracion CORS explicita.
- No se ha encontrado autenticacion de endpoints como `/catalog/refresh`.
- En uso local puede ser aceptable, pero no para despliegue abierto.

### Recomendaciones de seguridad

1. Rotar inmediatamente la clave ORS expuesta en `.env`.
2. No distribuir `.env` en `dist/` salvo a destinatarios controlados.
3. Cambiar host por defecto a `127.0.0.1` o exigir opt-in explicito para LAN.
4. Proteger `/catalog/refresh` si se expone fuera del equipo local.
5. Anadir aviso de privacidad para uso de ORS y OpenStreetMap.
6. Sanitizar y revisar `data/reports/*` antes de auditorias externas o distribucion.
7. Anadir comprobacion automatica que falle release si `.env` contiene claves reales.

## 10. Dependencias externas

### Librerias principales

Definidas en `requirements-web.txt`:

- `fastapi==0.136.0`.
- `starlette==1.0.0`.
- `pydantic==2.13.2`.
- `uvicorn[standard]==0.44.0`.
- `requests==2.32.5`.
- `beautifulsoup4==4.14.3`.

### Servicios externos

MINETUR:

- Fuente de estaciones y precios.
- Riesgo: cambios de formato, caidas, TLS, rate limiting o indisponibilidad.
- Mitigacion: snapshots y caches locales.
- Estado actual: DB activa indica fallo TLS reciente y uso de snapshot.

OpenRouteService:

- Geocodificacion, matrices y geometria de rutas.
- Riesgo: cuota, clave, indisponibilidad, latencia.
- Mitigacion parcial: fallback Haversine en optimizacion si ORS falla.
- Sin fallback completo para dibujo de ruta real.

OpenStreetMap tiles:

- Mapa visual.
- Riesgo: uso sujeto a politicas de tiles publicos, disponibilidad y conectividad.

unpkg.com:

- CDN para Leaflet CSS/JS.
- Riesgo: si no hay conexion o CDN falla, el mapa no cargara.
- Para produccion/portable robusto conviene empaquetar Leaflet localmente.

PyInstaller:

- Genera `dist/FuelOptLauncher.exe` y portable zip.
- Riesgo: incluir `.env`, caches o logs por error.

## 11. Testing y validacion

### Tests existentes

Los tests no usan pytest como runner principal en todos los casos; son scripts Python ejecutables directamente.

Ejecutados durante esta revision:

- `python tests\sanity_check.py`: OK.
- `python tests\test_adapters.py`: OK.
- `python tests\refresh_policy_check.py`: OK.
- `python tests\frontend_static_check.py`: OK.
- `python tests\web_pipeline_check.py`: OK.

Cobertura funcional observada:

- Parsing de Ballenoil y conversion numerica.
- Adaptadores MINETUR por marca.
- Canonicalizacion de marcas.
- Escritura y consulta SQLite.
- Optimizer en modo litros y presupuesto.
- Filtro por marca.
- Busqueda por corredor vs radio local.
- Expansion economica.
- Alias deprecated y conflictos.
- Errores sin ORS key.
- Endpoint de ruta stopover con provider simulado.
- Seguridad basica de frontend contra HTML no escapado.
- Politica de refresco y publicacion segura de snapshot/SQLite.

### Tests ausentes o recomendados

- Tests con FastAPI `TestClient` para todos los endpoints HTTP reales.
- Tests E2E de navegador para flujo completo UI.
- Tests con ORS mockeado a nivel HTTP para geocoding, matrix y directions.
- Tests de catalogo con datos reales reducidos de MINETUR.
- Tests de freshness y degradacion visibles en UI.
- Tests de empaquetado portable que verifiquen ausencia de `.env` real.
- Tests de seguridad para no exponer secretos en logs o bundles.
- Tests de rendimiento con 12.000 estaciones y multiples marcas.

### Pruebas manuales recomendadas

1. Arrancar backend:

```powershell
python main.py --host 127.0.0.1 --port 8000
```

2. Ver salud:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

3. Ver catalogo:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/catalog/status
```

4. Probar optimizacion local sin ORS:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/optimize `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "origin_lat": 40.4168,
    "origin_lon": -3.7038,
    "destination_lat": 40.4168,
    "destination_lon": -3.7038,
    "fuel_type": "gasoleo_a",
    "input_mode": "liters",
    "liters": 30,
    "consumption_l_100km": 5.5,
    "use_ors": false,
    "result_limit": 5
  }'
```

5. Probar presupuesto:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/optimize `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "origin_lat": 40.4168,
    "origin_lon": -3.7038,
    "destination_lat": 40.4168,
    "destination_lon": -3.7038,
    "fuel_type": "gasoleo_a",
    "input_mode": "budget",
    "budget_amount_eur": 40,
    "consumption_l_100km": 5.5,
    "use_ors": false,
    "result_limit": 5
  }'
```

6. Probar filtro de marca:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/optimize `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "origin_lat": 40.4168,
    "origin_lon": -3.7038,
    "destination_lat": 40.4168,
    "destination_lon": -3.7038,
    "fuel_type": "gasoleo_a",
    "liters": 30,
    "brands": ["REPSOL"],
    "use_ors": false
  }'
```

7. Probar UI:

- Abrir `http://127.0.0.1:8000`.
- Buscar "Puerta del Sol, Madrid" si ORS esta configurado.
- Elegir litros y gasoleo A.
- Ejecutar calculo.
- Cambiar a euros.
- Probar filtro por marca.
- Probar ruta con destino distinto.
- Observar si se pinta ruta real o si aparece error ORS.

## 12. Estado actual y roadmap tecnico

### Implementado

- Backend FastAPI.
- Frontend web estatico con Leaflet.
- Base SQLite local.
- Modelo de estaciones, precios y resultados.
- Catalogo desde MINETUR/snapshot/cache.
- Normalizacion amplia de marcas.
- Filtro por marca.
- Modos litros y presupuesto.
- Modos economico/equilibrado/minimo desvio.
- Busqueda local y por corredor.
- Expansion economica de candidatos.
- Fallback Haversine para optimizacion.
- Refresco seguro con DB candidata.
- Launcher Windows y empaquetado portable.
- Tests de pipeline, adaptadores, refresco y frontend estatico.

### Parcialmente implementado

- ORS: implementado, pero dependiente de clave, cuota y red.
- Geocodificacion UI: funcional solo con ORS.
- Pintado de ruta: funcional solo si `/route/stopover` con ORS responde.
- Freshness: existe metadata y refresco, pero no bloqueo automatico de optimizacion con datos antiguos.
- Exposicion de degradacion: backend la reporta, UI no la comunica claramente al usuario final.

### Mockeado o simulado

- Tests usan providers fijos y bases SQLite temporales.
- Fallback Haversine es estimacion, no ruta real.
- Caches locales sustituyen a fuentes vivas cuando fallan.
- `prices-cache` puede generar estaciones `UNKNOWN` sin direccion/marca completa.

### Pendiente o recomendable antes de produccion

1. Gestion de secretos:
   - Rotar ORS key.
   - Eliminar `.env` real de entregables.
   - Anadir check de release anti-secretos.

2. Seguridad de exposicion:
   - Cambiar host por defecto a localhost.
   - Anadir autenticacion si se usa en red.
   - Proteger endpoints de mantenimiento.

3. Calidad de datos:
   - Mostrar estado degradado y fecha real de precios en UI.
   - Definir politica de caducidad maxima de precios.
   - Validar por combustible seleccionado si hay cobertura suficiente.

4. Robustez frontend:
   - Empaquetar Leaflet localmente.
   - Corregir mojibake/encoding en textos.
   - Anadir fallback visual de ruta si ORS falla.
   - Exponer o justificar radios fijos.

5. Testing:
   - Anadir E2E con navegador.
   - Anadir tests HTTP con TestClient.
   - Anadir mocks HTTP de ORS/MINETUR.
   - Anadir test de paquete portable.

6. Operacion:
   - Documentar instalacion de tarea programada real.
   - Revisar politica de logs.
   - Monitorizar fallos de refresh y antiguedad de catalogo.

## 13. Conclusion para auditoria

El proyecto presenta una arquitectura local razonablemente clara: frontend estatico, API FastAPI, almacenamiento SQLite, fuentes externas normalizadas y un modulo de optimizacion separado. La logica de negocio esta concentrada principalmente en `app/optimizer/ranking.py`, lo que facilita su revision. La persistencia y el refresco estan bien separados en `app/storage/*` y `scripts/*`, con una estrategia prudente de DB candidata antes de publicar.

Fortalezas principales:

- Separacion clara entre API, datos, routing, optimizacion y almacenamiento.
- Modelo de datos explicito en `app/models.py`.
- Refresco seguro con validacion antes de publicar.
- Fallback local para optimizacion cuando ORS falla.
- Tests ejecutables que cubren casos relevantes de negocio.
- Metadata de catalogo que permite detectar degradacion.

Riesgos principales:

- Clave ORS real presente en `.env`.
- Sin autenticacion ni control de acceso.
- Exposicion por defecto en `0.0.0.0` desde el launcher.
- Dependencia fuerte de servicios externos para geocodificacion/ruta/mapa.
- Base actual marcada como `degraded` por fallo de descarga MINETUR.
- UI no comunica claramente degradacion del catalogo ni antiguedad de datos.
- Algunos textos muestran problemas de codificacion.
- No hay evidencia de tests E2E de navegador ni de validacion de paquete portable sin secretos.

Informacion que deberia verificarse manualmente:

- Si la tarea programada `FuelOpt Catalog Refresh` existe realmente en la maquina destino.
- Si `dist/FuelOptPortable.zip` contiene `.env` real o logs sensibles.
- Si la clave ORS sigue activa y si tiene restricciones de dominio/IP/cuota.
- Si los terminos de uso de ORS, OpenStreetMap tiles y MINETUR permiten el uso previsto.
- Si la fecha de referencia de precios se muestra correctamente al usuario final.
- Si el usuario entiende que los calculos sin ORS son aproximaciones.

Proximos pasos recomendados:

1. Rotar y retirar la clave ORS de `.env`.
2. Corregir exposicion LAN por defecto o documentarla como opcion explicita.
3. Mostrar en UI `refresh_status`, `degraded_reasons` y fecha de precios.
4. Anadir fallback visual de ruta sin ORS.
5. Corregir codificacion de textos.
6. Anadir tests E2E y checks de release anti-secretos.

## Resumen final

### Archivos principales revisados

- `README_WEB.md`
- `.env`
- `.env.example`
- `requirements-web.txt`
- `main.py`
- `fuelopt_launcher.py`
- `app/config.py`
- `app/models.py`
- `app/api/main.py`
- `app/api/ui.py`
- `app/optimizer/ranking.py`
- `app/routing/ors.py`
- `app/storage/database.py`
- `app/storage/validation.py`
- `app/storage/publish.py`
- `app/data_sources/minetur.py`
- `app/data_sources/brand_catalog.py`
- `app/data_sources/adapters.py`
- `app/data_sources/adapters_scraping.py`
- `app/data_sources/ballenoil.py`
- `scripts/rebuild_station_catalog.py`
- `scripts/refresh_catalog.py`
- `scripts/renormalize_catalog_brands.py`
- `static/index.html`
- `static/app.js`
- `static/styles.css`
- `docs/rotulos_catalog.txt`
- `docs/TASK_REFRESH_COMMANDS.md`
- `tests/*.py`
- `data/db/gas_stations.sqlite`
- `data/reports/catalog_refresh_report.json`

### Funcionalidades confirmadas

- UI web local con mapa.
- Seleccion de origen y destino.
- Regreso al origen.
- Seleccion de combustible.
- Entrada por litros o presupuesto.
- Consumo medio configurable.
- Filtro por marcas.
- Optimizacion por coste efectivo o litros netos.
- Comparacion de gasolineras.
- Ranking de alternativas.
- Estimacion de desvio y coste de ruta.
- Geocodificacion y rutas ORS si hay clave.
- Fallback Haversine en optimizacion.
- Catalogo SQLite local.
- Refresco seguro del catalogo.
- Tests basicos y de pipeline pasando.

### Funcionalidades dudosas o mockeadas

- Datos en vivo MINETUR: ultimo estado observado usa snapshot por fallo TLS.
- Ruta visual sin ORS: no se ha encontrado fallback.
- Tarea programada Windows: documentada, pendiente de verificar en entorno destino.
- CLI heredada: existe, pero no parece flujo principal.
- Tests ORS reales: no se han encontrado; se usan providers simulados.

### Riesgos principales

- Secreto ORS expuesto en `.env`.
- App sin autenticacion.
- Launcher expone en LAN por defecto.
- Dependencia externa de ORS, MINETUR, OpenStreetMap y unpkg.
- Datos actuales marcados como degradados.
- UI no comunica suficientemente frescura/degradacion.
- Posibles problemas de codificacion en textos.

### Recomendaciones prioritarias

1. Rotar `ORS_API_KEY` y eliminar secretos de entregables.
2. Restringir host por defecto a `127.0.0.1` o proteger acceso LAN.
3. Mostrar estado del catalogo y antiguedad de precios en la UI.
4. Anadir tests E2E y de integracion HTTP.
5. Empaquetar dependencias frontend criticas localmente.
6. Establecer politica de freshness, logs y release.
