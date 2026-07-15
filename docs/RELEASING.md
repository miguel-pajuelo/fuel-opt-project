# Publicar una versión de FuelOpt para Windows

El workflow `Windows release` crea una GitHub Release únicamente al publicar un tag con formato estricto `vMAJOR.MINOR.PATCH`, por ejemplo `v0.1.0`. `workflow_dispatch` es siempre dry-run: puede construir artefactos sin `LICENSE`, informa que la publicación está bloqueada y omite el job con permiso `contents: write`.

## Antes del tag

1. Parte de un commit limpio y ejecuta `scripts\release_check.cmd`.
2. Confirma que versión, instalador, metadatos, CHANGELOG y nombres de artefactos coinciden.
3. Confirma semilla y snapshot aprobados mediante hashes.
4. Resuelve todos los blockers de [FINAL_REVIEW_BACKLOG.md](FINAL_REVIEW_BACKLOG.md), incluida una licencia principal.
5. Ejecuta `workflow_dispatch`, descarga instalador, ZIP y `SHA256SUMS.txt`, y verifica contenido y hashes.
6. Confirma que la firma está aplicada o que su ausencia tiene una aceptación de riesgo explícita.
7. Solo entonces crea el tag sobre el commit exacto:

   ```bat
   git tag -a v0.1.0 -m "FuelOpt 0.1.0"
   git push origin v0.1.0
   ```

Tags incompletos o con sufijos no admitidos deben fallar antes del build.

El guard de publicación exige que `LICENSE` exista como archivo regular, tenga contenido y no contenga `TODO`, `CHOOSE LICENSE`, `LICENSE PENDING` ni `TBD`. En un tag, un fallo del guard detiene el job antes de instalar dependencias; el job de publicación exige además la salida positiva del guard. El dry-run no elude el blocker: solo permite validar técnicamente los artefactos mientras la licencia principal sigue pendiente.

## Pipeline

- instala Python 3.12.10 y dependencias fijadas;
- ejecuta release checks;
- limpia `build\` y `dist\`;
- genera PyInstaller `onedir`;
- deriva un único `FUELOPT_VERSION` y valida el `VERSIONINFO` de `FuelOpt.exe`;
- incorpora `THIRD_PARTY_NOTICES.md` en `_internal/licenses/`;
- obtiene Inno Setup 6.7.3 verificando hash y firma del proveedor;
- compila el instalador con la versión derivada del tag;
- genera `FuelOpt-X.Y.Z-windows-x64.zip` y `SHA256SUMS.txt`;
- conserva instalador, ZIP y hashes como artefactos;
- publica solo para tag y reemplaza assets del mismo nombre en un reintento.

## Verificación posterior

Descarga los assets desde GitHub, recalcula SHA-256, verifica firma y metadatos y audita que no existan secretos, rutas personales, tests o datos mutables. Confirma una sola Release y un solo conjunto coherente de assets. La idempotencia real de una Release permanece pendiente hasta la primera publicación controlada.

## Rollback y retirada

Un fallo previo al job de publicación no debe crear Release. Si una Release publicada es defectuosa, retírala o conviértela en borrador, documenta el motivo y verifica separadamente Release y tag. No reutilices una versión para contenido diferente: publica la corrección con un número nuevo. Conserva hashes y logs saneados para trazabilidad.

## Límites actuales

No hay licencia principal, firma digital ni validación completa en VM. No añadas certificados, contraseñas, claves ORS ni otros secretos al workflow. El guard técnico impide publicar sin `LICENSE`; su dry-run debe validarse remotamente antes de cerrar Patch 8B, pero esa evidencia no resuelve la elección de licencia ni los demás blockers humanos.
