# Instalación y desinstalación

El ejecutable y el instalador todavía no están firmados. Windows SmartScreen puede mostrar una advertencia; la firma y la experiencia SmartScreen deben resolverse o aceptarse expresamente antes de publicar.

## Instalación prevista

El instalador trabaja por usuario, con privilegios mínimos:

- programa: `%LOCALAPPDATA%\Programs\FuelOpt`;
- datos: `%LOCALAPPDATA%\FuelOpt`;
- sin necesidad de Python, Git ni permisos administrativos;
- acceso directo en Inicio y acceso de escritorio opcional;
- frecuencia predeterminada: 4 horas.

Durante la instalación se puede elegir 1h, 2h, 4h, 8h, 12h, 24h, al abrir o solo manual. La primera apertura crea el directorio del usuario y copia o reconstruye la base activa desde los recursos instalados. Una base activa válida no se sobrescribe con la semilla.

Instalación silenciosa prevista:

```bat
FuelOpt-Setup-0.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /REFRESH=4h
```

Solo se admiten los ocho valores documentados. La matriz silenciosa completa sigue pendiente de VM.

## Apertura y uso offline

FuelOpt inicia un servidor local y abre el navegador. Sin red puede usar la última base válida; no podrá descargar precios, rutas ORS ni teselas de mapa. Consulta [TROUBLESHOOTING.md](TROUBLESHOOTING.md) si el bootstrap falla.

## Actualización

Una actualización reutiliza el AppId estable y el mismo directorio. Debe cerrar cooperativamente launcher y servidor antes de sustituir `_internal`. Configuración, clave ORS, frecuencia, base activa, cache y logs viven fuera de la instalación y deben conservarse. Este flujo tiene checks automatizados, pero la actualización real entre dos instaladores permanece pendiente.

## Desinstalación

La desinstalación detiene FuelOpt, elimina la tarea programada y los accesos directos, y retira los archivos del programa. Los datos se conservan por defecto. La opción “Eliminar también mis datos, configuración y precios almacenados” permite borrar `%LOCALAPPDATA%\FuelOpt` explícitamente.

En modo silencioso, borrar datos requiere:

```bat
unins000.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /REMOVEDATA=1
```

Sin `/REMOVEDATA=1` deben conservarse. Ambos comportamientos necesitan validación final en VM.

## Identidad visual

El icono aprobado está integrado en ejecutable, instalador y accesos directos. Su validación técnica se conserva en los checks de marca. La procedencia jurídica permanece en revisión; consulta FR-001 y FR-037 en el [backlog](FINAL_REVIEW_BACKLOG.md).
