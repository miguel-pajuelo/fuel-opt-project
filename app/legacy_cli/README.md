# Legacy CLI package

Este paquete conserva la interfaz de línea de comandos anterior para compatibilidad. `main.py --legacy-cli` delega en estos módulos; la aplicación Windows y la API local utilizan la arquitectura principal de `app/`.

## Módulos

- `runtime.py`: utilidades de terminal, fechas, JSON y parsing.
- `minetur.py`: lectura y normalización de datos oficiales.
- `ballenoil.py` y `scraper.py`: compatibilidad con el pipeline histórico inactivo.
- `routing.py`: integración ORS usada por la CLI.
- `optimizer.py`: cálculo y presentación de resultados legacy.
- `cli.py`: prompts y salida interactiva.

Este paquete no define el flujo productivo de refresco, el launcher Windows ni el ranking de la interfaz actual.
