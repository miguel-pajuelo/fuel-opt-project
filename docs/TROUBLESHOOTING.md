# Solución de problemas

## FuelOpt no abre

Comprueba que no haya otra instancia iniciándose y espera unos segundos. El launcher prueba los puertos 8001–8010 y solo reutiliza un servidor cuya respuesta `/health` identifica a FuelOpt.

Los logs se encuentran en `%LOCALAPPDATA%\FuelOpt\logs`. No los publiques sin revisar antes que no contengan información personal.

## No aparecen el mapa o las rutas

Leaflet está incluido, pero las teselas de OpenStreetMap requieren conexión. La búsqueda por dirección y las rutas por carretera necesitan una clave ORS válida.

Sin ORS, el optimizador puede utilizar Haversine. Ese resultado es una estimación y no dibuja una ruta real.

## La tarea de actualización falla

Consulta la configuración:

```bat
FuelOpt.exe --show-settings
FuelOpt.exe --configure-refresh --interval 24h
```

No elimines tareas de nombre parecido manualmente. `manual` y `on_open` no mantienen una tarea periódica.

## Los precios parecen antiguos

FuelOpt conserva la última base válida cuando una descarga o validación falla. Revisa la fecha de frescura mostrada y ejecuta un refresco manual. Los precios externos pueden cambiar incluso después de una actualización correcta.

## La base no puede abrirse

Reinicia FuelOpt para permitir que el bootstrap valide la base activa y use la copia recuperable cuando corresponda. No copies una SQLite abierta ni elimines archivos de `%LOCALAPPDATA%\FuelOpt` sin conservar antes una copia.

## SmartScreen muestra una advertencia

Verifica que el archivo procede de [Latest release](https://github.com/miguel-pajuelo/fuel-opt-project/releases/latest) y que su SHA-256 coincide con `SHA256SUMS.txt`. Sigue las indicaciones de [Instalación](INSTALLATION.md#advertencia-de-microsoft-defender-smartscreen). No desactives Microsoft Defender.
