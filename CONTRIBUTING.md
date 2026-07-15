# Contributing

Mantén cada cambio limitado, revisable y vinculado a un problema verificable.

## Entorno

Usa Python 3.12, un entorno virtual y una rama propia:

```bat
python -m pip install -r requirements-runtime.lock -r requirements-test.txt
```

Añade `requirements-build.txt` únicamente para empaquetado. Los commits deben describir una sola unidad lógica.

## Seguridad y datos

- No confirmes `.env`, claves, tokens, credenciales ni rutas personales.
- No rastrees bases activas, WAL, SHM, locks, logs, caches, `build/` o `dist/`.
- No modifiques accidentalmente la semilla o snapshot MINETUR.
- Si una actualización de datos es intencional, documenta fuente, fecha, hashes y reproducibilidad.
- Conserva la publicación atómica de SQLite y la separación entre recursos instalados y datos del usuario.
- No retires fallbacks o compatibilidad sin una revisión específica.

## Pull requests

Describe objetivo, riesgos, archivos y pruebas. Distingue las validaciones automatizadas de las comprobaciones manuales.

```bat
python -m pytest
git diff --check
```

Para cambios de runtime, instalador, packaging o publicación ejecuta también:

```bat
scripts\release_check.cmd
```

Revisa `git status --short` y confirma que los datos rastreados no cambiaron. Consulta [DEVELOPMENT.md](docs/DEVELOPMENT.md).
