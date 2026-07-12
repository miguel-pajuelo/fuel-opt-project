# Publicar una versión de FuelOpt para Windows

El workflow `Windows release` crea una GitHub Release únicamente al publicar un tag con formato estricto `vMAJOR.MINOR.PATCH`, por ejemplo `v0.1.0`.

También admite ejecución manual mediante `workflow_dispatch`. Las ejecuciones manuales son siempre dry-run: construyen y conservan artefactos del workflow, pero el job con permiso `contents: write` queda omitido y no puede crear una GitHub Release.

## Antes de crear el tag

1. Trabaja desde un commit limpio que haya pasado `scripts\release_check.cmd`.
2. Confirma que la versión todavía no existe como tag o GitHub Release.
3. Confirma que los datos semilla y el snapshot rastreados son los aprobados para esa versión.
4. Crea y publica el tag sobre el commit exacto que se quiere distribuir:

   ```powershell
   git tag -a v0.1.0 -m "FuelOpt 0.1.0"
   git push origin v0.1.0
   ```

Los tags como `v0.1`, `v0.1.0-beta` o cualquier valor que no sea `vX.Y.Z` hacen fallar el workflow antes del build.

## Qué ejecuta el workflow

- Instala Python 3.12.10, disponible para `windows-latest`, y las dependencias fijadas.
- Ejecuta todos los release checks.
- limpia `build\` y `dist\`;
- genera el bundle PyInstaller onedir;
- descarga Inno Setup 6.7.3, verificando SHA-256 y firma de Pyrsys B.V.;
- compila el instalador con la versión derivada del tag;
- genera el ZIP del bundle y `SHA256SUMS.txt`;
- conserva los tres archivos como artefacto del workflow;
- crea la GitHub Release o reemplaza sus archivos si se reintenta el mismo tag.

La Release contiene:

- `FuelOpt-Setup-X.Y.Z.exe`;
- `FuelOpt-X.Y.Z-windows-x64.zip`;
- `SHA256SUMS.txt`.

## Límites actuales

Los binarios permanecen sin firma digital hasta configurar un certificado de code signing. No añadas certificados, contraseñas, claves ORS ni otros secretos directamente al workflow o al repositorio.
