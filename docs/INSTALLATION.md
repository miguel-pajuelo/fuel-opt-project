# Instalación de FuelOpt

FuelOpt se distribuye como instalador por usuario para Windows 10/11 x64. El instalador previsto se genera en `dist\installer` y el bundle onedir en `dist\FuelOpt`; ambos son artefactos locales no rastreados.

El icono aprobado se integra en `FuelOpt.exe`, el instalador, Aplicaciones instaladas, el menú Inicio y el acceso directo opcional del escritorio. Los accesos directos apuntan al ejecutable instalado para reutilizar su icono embebido. `UninstallDisplayIcon` también apunta al ejecutable instalado.

La aplicación y el instalador no están firmados. No debe interpretarse un build local satisfactorio como autorización para publicar una release o instalarla en un sistema real.

Comandos de build para un entorno de desarrollo preparado:

```bat
scripts\build_onedir.cmd
scripts\build_installer.cmd
```

La configuración de la tarea real `FuelOpt Catalog Refresh` se realiza únicamente durante un flujo de instalación autorizado; los checks de packaging no deben crearla, eliminarla ni modificarla.
