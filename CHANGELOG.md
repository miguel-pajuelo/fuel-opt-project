# Changelog

## [0.1.2] - 2026-07-19

### Added

- Nueva identidad visual y nuevo logo de FuelOpt en la aplicación, favicon, ejecutable e instalador.
- Vídeo explicativo integrado en la guía rápida y distribuido dentro del paquete de Windows.

### Changed

- El tutorial adopta un diseño más amplio, legible y responsive, con reproducción automática silenciada y en bucle.
- Se mejoran la jerarquía visual, el contraste, la navegación por teclado y el comportamiento del modal en pantallas pequeñas.

## [0.1.1] - 2026-07-15

### Changed

- La frecuencia predeterminada de actualización pasa de 4 a 24 horas para instalaciones nuevas; las preferencias existentes se conservan.
- La documentación pública se simplifica y se alinea con el funcionamiento publicado.
- La guía de instalación explica las advertencias de Microsoft Defender SmartScreen y la verificación mediante SHA-256.

### Fixed

- La publicación automática identifica explícitamente el repositorio, crea primero una release draft y verifica sus assets antes de publicarla.
- Los reintentos no reemplazan assets de una release publicada: una coincidencia exacta es un no-op y cualquier diferencia requiere revisión manual.

## [0.1.0] - 2026-07-15

### Added

- Aplicación local para Windows 10/11 x64 con launcher, servidor FastAPI local y frontend web.
- Optimización por ahorro, menor desvío o equilibrio, con entrada por litros o presupuesto.
- Catálogo MINETUR local en SQLite, actualización atómica y tarea programada configurable.
- Rutas ORS opcionales y estimación Haversine identificada cuando ORS no está disponible.
- Instalador por usuario, ZIP portable, VERSIONINFO, iconos y checksums SHA-256.
- Inventario reproducible de componentes runtime, LICENSE, NOTICE y textos legales de terceros.
- Checks de seguridad, secretos, documentación, bundle, instalador y smoke test en GitHub Actions.

### Known limitations

- Los ejecutables y el instalador no están firmados digitalmente.
- Los precios, rutas y disponibilidad de estaciones pueden cambiar; los resultados son orientativos.
- Algunas funciones requieren conexión y ORS necesita una clave aportada por el usuario.
