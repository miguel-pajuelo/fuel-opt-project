# Changelog

## [0.1.0] - Unreleased

### Added

- Aplicación local para Windows orientada a optimizar el coste de combustible.
- Frontend local con comparación de alternativas, marcas y mapa.
- Tres modos de optimización (`economic`, `minimal_detour` y `balanced`) con ranking determinista y límite de resultados aplicado después de ordenar.
- Selector accesible y explicaciones específicas del criterio utilizado en cada resultado.
- Identificación visible de rutas OpenRouteService y estimaciones Haversine.
- Base semilla y snapshot para primer arranque y recuperación offline.
- Semilla MINETUR con metadata de procedencia, hashes y atribución de reutilización.
- Apache License 2.0 y titularidad de Miguel Pajuelo Gómez.
- Fuente productiva de catálogo limitada a MINETUR; retirados los caches complementarios heredados.
- Atribuciones visibles de OpenStreetMap y OpenRouteService actualizadas.
- Refresco directo, atómico y configurable: 1h, 2h, 4h, 8h, 12h, 24h, al abrir o manual.
- Integración por usuario con Windows Task Scheduler y Credential Manager para ORS.
- Bundle PyInstaller `onedir` e instalador Inno Setup per-user.
- Pipeline de GitHub Actions para checks, bundle, instalador, ZIP y SHA-256.
- Controles para secretos, rutas personales, datos SQLite mutables y recuperación de locks.
- Ayuda rápida accesible en la primera apertura, con persistencia local versionada.

### Security and privacy

- Recursos instalados separados de los datos modificables del usuario.
- Base candidata validada antes de sustituir atómicamente la base activa.
- Sin telemetría propia; los servicios externos utilizados se documentan explícitamente.
- Feedback trasladado a GitHub Issues, sin formulario de correo ni credenciales SMTP.
- Errores ORS y de red sanitizados en respuestas y logs; `security_check.py` es obligatorio en el gate de release.

### Known limitations

- No existe todavía una release pública ni firma digital; la revisión jurídica profesional continúa pendiente.
- Instalación, actualización y desinstalación reales siguen pendientes en una VM Windows limpia.
- Las rutas precisas requieren una clave ORS del usuario; sin ella se usa una aproximación geométrica.
- La frescura de precios depende de las fuentes externas y no se garantiza en tiempo real.
