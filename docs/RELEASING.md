# Publicación

## 0.1.2 — 2026-07-19

La versión estable actualiza la identidad visual, incorpora el vídeo de la guía rápida y mejora su diseño responsive.

## Preparación

1. Trabaja desde una rama limpia basada en `main`.
2. Actualiza la versión común y `CHANGELOG.md`.
3. Ejecuta `scripts\release_check.cmd`.
4. Construye y audita bundle e instalador limpios.
5. Ejecuta `workflow_dispatch` con la versión prevista y confirma que el job de publicación queda omitido.
6. Revisa el diff, los artifacts y cualquier validación manual aplicable.

## Validaciones manuales antes de publicar

- **Interfaz responsive:** para `0.1.2` se corrigió el overflow horizontal de la cabecera y se comprobó la interfaz a 320 px, con zoom al 200 % y en escritorio. No se observó scroll horizontal involuntario y mapa, controles y filtros permanecieron utilizables.
- **Credenciales históricas de ORS:** confirma por un canal privado que cualquier credencial histórica de OpenRouteService ha sido revocada o rotada. No registres su valor ni lo copies en Issues, documentación, logs, commits o chats. Para `0.1.2`, la persona responsable confirmó la revocación o rotación antes de publicar, sin registrar ningún valor de credencial.

## Publicación por tag

El workflow solo publica tags con formato `vMAJOR.MINOR.PATCH`. El tag debe apuntar al commit revisado y `LICENSE` debe superar el guard técnico.

El job de publicación:

1. descarga los tres assets producidos por el mismo run;
2. resuelve el tag remoto y lo compara con `GITHUB_SHA`;
3. consulta siempre el repositorio mediante `--repo "$env:GITHUB_REPOSITORY"`;
4. si no existe una release, la crea como draft con instalador, ZIP y `SHA256SUMS.txt`;
5. compara nombres, tamaños y digests SHA-256 remotos con el payload auditado;
6. publica el draft únicamente después de esa verificación.

No se utiliza `gh release upload --clobber`. Si una release publicada ya existe y coincide exactamente, el run termina sin modificarla. Si existe con assets ausentes, adicionales o diferentes, el job falla y requiere revisión manual. Un draft anterior solo se reanuda cuando tag, commit y assets coinciden.

## Verificación posterior

- Confirma el SHA del tag y el estado de la release.
- Descarga los tres assets desde GitHub.
- Verifica `SHA256SUMS.txt`.
- Ejecuta los checks de VERSIONINFO, bundle, inventario legal e instalador.
- Confirma que no se publicaron secretos, rutas personales o datos mutables.

## Rollback

No sustituyas assets de un tag publicado. Si una release es defectuosa, detén su distribución y documenta la incidencia. Corrige el código en un nuevo commit y publica una versión posterior con un tag nuevo. Un draft no publicado puede revisarse o retirarse manualmente antes de crear otro intento.
