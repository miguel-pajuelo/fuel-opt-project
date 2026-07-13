# Contributing

FuelOpt todavía está en pre-release. Mantén cada cambio limitado, revisable y vinculado a un problema verificable.

## Entorno y rama

Usa Python 3.12 (CI: 3.12.10), un entorno virtual y una rama propia. Instala `requirements-web.txt`; añade `requirements-build.txt` solo para empaquetado. Los mensajes de commit deben ser breves, imperativos y describir una sola unidad lógica.

## Reglas de seguridad y datos

- No confirmes `.env`, claves reales, tokens ni credenciales SMTP.
- No introduzcas rutas absolutas o nombres de usuario personales.
- No confirmes bases activas, WAL, SHM, locks, logs, caches, `build/` ni `dist/`.
- No modifiques accidentalmente la semilla `data/db/gas_stations.sqlite` ni el snapshot `data/cache/minetur_snapshot.json`.
- Si un cambio intencional modifica semilla o snapshot, explica procedencia, validación, hashes y reproducibilidad.
- Conserva la copia mediante SQLite y la publicación atómica; no sustituyas estos mecanismos por copias binarias de bases abiertas.
- No amplíes el alcance retirando fallbacks, migraciones o compatibilidad sin una auditoría específica.

## Pull requests

Describe objetivo, riesgos, archivos, pruebas y cualquier validación manual pendiente. No declares como probado en Windows real algo que solo se inspeccionó estáticamente o en CI.

Comprobaciones mínimas:

```bat
python -m pytest
git diff --check
```

Para cambios de runtime, packaging, instalador o publicación ejecuta también:

```bat
scripts\release_check.cmd
```

Revisa `git status --short`, confirma que los hashes de datos rastreados no cambiaron y que no quedan procesos, locks o artefactos de prueba. Consulta [DEVELOPMENT.md](docs/DEVELOPMENT.md).
