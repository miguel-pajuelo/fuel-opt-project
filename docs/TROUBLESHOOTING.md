# Solución de problemas

## FuelOpt no abre

Revisa `%LOCALAPPDATA%\FuelOpt\logs`. Confirma que no haya una actualización en curso y prueba una sola apertura. FuelOpt escanea 8001–8010; un servicio ajeno en 8001 no debe ser reutilizado.

## Instancia, puerto o lock

El launcher valida identidad y runtime record antes de reutilizar una instancia. Tras un cierre abrupto puede quedar un lock stale; el código intenta normalizar BOM/espacios y recuperarlo si el proceso ya no existe. No borres un lock mientras exista un proceso FuelOpt. Para cierre cooperativo usa `FuelOpt.exe --shutdown-existing`.

## La base no se crea

El bootstrap debe crear `%LOCALAPPDATA%\FuelOpt\data\db` y copiar la semilla inmutable mediante SQLite. Si la semilla no es válida, intenta reconstruir desde el snapshot. Comprueba espacio, permisos por usuario y logs. No edites `_internal` ni copies una base mientras esté abierta.

## Datos antiguos o refresco fallido

Un fallo conserva la última base válida. Ejecuta `FuelOpt.exe --refresh-direct --silent` y consulta el código de salida y logs. La disponibilidad del catálogo oficial de MINETUR no está garantizada.

## ORS o mapa

Verifica la clave con `--show-settings` sin exponerla. Si ORS falla, se usa una aproximación. Leaflet es local, pero las teselas requieren red y están sujetas al proveedor; un mapa vacío no implica que la base local haya fallado.

## Scheduler

Reconfigura un valor admitido con `--configure-refresh --interval 4h`. No ejecutes ni elimines tareas de nombre similar manualmente. `manual` y `on_open` no mantienen tarea periódica.

## Base corrupta

FuelOpt valida candidatas y conserva una base anterior cuando corresponde. Antes de intervenir, cierra la aplicación y copia fuera de `%LOCALAPPDATA%\FuelOpt` la base activa, `previous` y logs. La recuperación completa ante corrupción aún requiere validación final; no se garantiza que toda corrupción sea recuperable.

## Reinstalación o desinstalación

Reinstalar no debería sobrescribir una base activa válida. Desinstalar conserva los datos por defecto; si quieres eliminarlos, usa la opción explícita o `/REMOVEDATA=1`. Consulta [INSTALLATION.md](INSTALLATION.md).
