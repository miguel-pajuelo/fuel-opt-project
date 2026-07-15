# Configuración, ORS y CLI

## Rutas de usuario

```text
%LOCALAPPDATA%\FuelOpt\
  config.json
  data\db\
  data\cache\
  logs\
```

`config.json` contiene opciones no secretas. Si falta o no es válido, la aplicación intenta recuperar valores seguros; el valor de refresco predeterminado es `4h`.

## OpenRouteService

En Windows instalado, la clave se almacena para el usuario actual en Windows Credential Manager como credencial genérica `FuelOpt/ORS_API_KEY`. La implementación usa `CredWriteW`, `CredReadW` y `CredDeleteW` de `Advapi32`; no escribe la clave en `config.json`. La variable `ORS_API_KEY` funciona como fallback para desarrollo y migración, pero no debe incorporarse al bundle ni a logs.

Sin clave, FuelOpt conserva el cálculo aproximado Haversine y no dispone de rutas por carretera fiables.

```bat
FuelOpt.exe --set-ors-key
FuelOpt.exe --clear-ors-key
FuelOpt.exe --show-settings
```

`--set-ors-key` solicita la clave sin incluirla en la línea de comandos. `--show-settings` no revela secretos. Los fallos de ORS se traducen a mensajes públicos estables; los logs normales conservan operación, tipo general de fallo y, cuando es seguro, estado remoto, sin URL preparada, parámetros, cabeceras ni texto crudo del proveedor.

## Frecuencia de refresco

Valores admitidos: `1h`, `2h`, `4h`, `8h`, `12h`, `24h`, `on_open` y `manual`. Las seis primeras crean o sustituyen una tarea por usuario. `on_open` y `manual` eliminan la tarea periódica inequívoca.

```bat
FuelOpt.exe --configure-refresh --interval 4h
FuelOpt.exe --refresh-direct --silent
FuelOpt.exe --remove-refresh-task
```

El refresco directo no depende de FastAPI ni del endpoint HTTP administrativo. Construye una base candidata, la valida y solo entonces publica el resultado.

## Cierre cooperativo

```bat
FuelOpt.exe --shutdown-existing
```

Este comando es público para instalador y mantenimiento. Solicita el cierre de la instancia FuelOpt identificada sin terminar procesos ajenos.

## Comandos internos

`--server-only`, opciones de host/puerto y controles diagnósticos son detalles internos del launcher, no una API estable.

## Códigos de salida y logs

`0` indica operación completada. Un código distinto de cero indica argumentos inválidos, error de credenciales, Scheduler, bootstrap, refresco o cierre; revisa `%LOCALAPPDATA%\FuelOpt\logs`. El modo `--silent` evita interacción, no elimina el registro de errores. Los valores secretos deben redactarse.

## Privacidad y servicios externos

FuelOpt puede contactar con ORS, el catálogo oficial de MINETUR y el servicio estándar de teselas `tile.openstreetmap.org`. MINETUR es la única fuente productiva del catálogo en 0.1.0; la semilla y los refrescos utilizan sus datos oficiales, con tratamiento neutral de todas las marcas. Esos servicios pueden recibir la IP y los parámetros necesarios para su operación. Leaflet está alojado localmente, pero las teselas no son offline. Google Maps recibe los puntos de ruta solo cuando el usuario pulsa **Abrir en Maps**. GitHub recibe información solo cuando el usuario abre **Mándanos tu idea** y decide publicar un Issue.

No hay telemetría propia ni formulario de correo. El navegador utiliza `localStorage` únicamente para `fuelopt:onboarding:v1:dismissed`. Consulta la página de privacidad incluida con la aplicación para el detalle y las limitaciones.
