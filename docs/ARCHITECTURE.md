# Arquitectura

## Aplicación local

FuelOpt combina un launcher Windows, una API FastAPI local y un frontend estático. El launcher selecciona un puerto entre 8001 y 8010, inicia Uvicorn en `127.0.0.1`, comprueba `/health` y abre el navegador. La exposición a la LAN requiere una opción explícita.

## Datos y bootstrap

Los recursos instalados son inmutables. La configuración, base activa, cache y logs viven en `%LOCALAPPDATA%\FuelOpt`.

El primer arranque conserva una base activa válida; si falta, copia la semilla MINETUR o la reconstruye desde su snapshot. Los refrescos escriben y validan una SQLite candidata antes de sustituir atómicamente la base activa. Un fallo conserva la última base válida.

MINETUR es la fuente productiva del catálogo. Las estaciones se procesan de forma neutral respecto a su marca.

## Optimización

El API valida la entrada y obtiene candidatos desde SQLite. El ranking admite `economic`, `minimal_detour` y `balanced`, ordena todo el universo válido de forma determinista y aplica `result_limit` al final.

OpenRouteService aporta geocodificación y distancias por carretera cuando existe una clave. Haversine ofrece una aproximación local cuando ORS no está disponible. La interfaz identifica qué fuente de ruta se utilizó.

## Procesos y actualización

En modo frozen, los procesos auxiliares utilizan el mismo ejecutable. El launcher mantiene un runtime record, comprueba la identidad del servidor y usa cierre cooperativo para permitir actualizaciones sin terminar procesos ajenos.

La tarea `FuelOpt Catalog Refresh` ejecuta el refresco directo. La frecuencia se guarda en `config.json` y en los datos previos del instalador para conservarla durante actualizaciones.

## Build y publicación

PyInstaller genera un bundle onedir y Inno Setup crea el instalador por usuario. La versión común alimenta VERSIONINFO, instalador y nombres de artifacts.

GitHub Actions fija dependencias, ejecuta release checks y genera instalador, ZIP y checksums. Un dry-run conserva los artifacts de Actions y no publica. Un tag válido crea primero una GitHub Release draft, verifica tag, commit, nombres, tamaños y SHA-256, y solo entonces la publica.
