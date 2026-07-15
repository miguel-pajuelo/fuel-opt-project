# Instalación y actualización

FuelOpt está dirigido a Windows 10/11 x64 y se instala por usuario, sin necesitar Python, Git ni privilegios de administrador.

## Descargar

1. Abre [Latest release](https://github.com/miguel-pajuelo/fuel-opt-project/releases/latest).
2. Descarga el instalador `FuelOpt-Setup-<versión>.exe` o el ZIP portable.
3. Descarga también `SHA256SUMS.txt` y verifica el archivo antes de ejecutarlo.

En PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\FuelOpt-Setup-<versión>.exe
Get-Content .\SHA256SUMS.txt
```

El hash calculado debe coincidir exactamente con la línea correspondiente.

## Instalar

El instalador utiliza `%LOCALAPPDATA%\Programs\FuelOpt` y crea accesos directos según las opciones elegidas. La configuración, base activa, cache y logs se guardan fuera del directorio del programa, en `%LOCALAPPDATA%\FuelOpt`.

Durante la instalación se puede elegir actualización cada 1, 2, 4, 8, 12 o 24 horas, al abrir FuelOpt o solo manual. Para instalaciones nuevas, el valor recomendado y preseleccionado es cada 24 horas.

El primer arranque copia o reconstruye la base activa desde la semilla MINETUR incluida. Una base válida existente no se sustituye con la semilla.

## Advertencia de Microsoft Defender SmartScreen

Windows puede mostrar una advertencia de Microsoft Defender SmartScreen al abrir FuelOpt. SmartScreen evalúa la reputación de los archivos descargados y sus firmas digitales, por lo que una aplicación nueva, con pocas descargas o sin firma puede generar una advertencia. Esa advertencia, por sí sola, no equivale a una detección de malware.

Descarga FuelOpt únicamente desde la GitHub Release oficial y verifica el instalador o el ZIP con `SHA256SUMS.txt`. Si el origen es correcto y el SHA-256 coincide, en el aviso estándar puede seleccionarse **Más información** y después **Ejecutar de todas formas**, cuando esa opción esté disponible.

No continúes si el archivo procede de otra fuente, el checksum no coincide o Windows muestra una detección concreta de malware. No desactives Microsoft Defender para ejecutar FuelOpt.

Más información: [Microsoft Defender SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/).

## Instalación silenciosa

```bat
FuelOpt-Setup-<versión>.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /REFRESH=24h
```

`/REFRESH` admite `1h`, `2h`, `4h`, `8h`, `12h`, `24h`, `on_open` y `manual`. Un valor no admitido cancela la instalación.

## Actualizar

Ejecuta el instalador nuevo sobre la instalación existente. El AppId y el directorio se mantienen. La frecuencia seleccionada anteriormente se recupera del instalador y solo cambia si el usuario elige otro valor o pasa `/REFRESH` explícitamente.

FuelOpt cierra cooperativamente sus procesos antes de sustituir el runtime. La configuración, clave ORS, base activa, cache y logs permanecen en el perfil del usuario.

## Desinstalar

La desinstalación elimina el programa y su tarea programada. Los datos personales se conservan por defecto. La opción visible **Eliminar también mis datos, configuración y precios almacenados** o `/REMOVEDATA=1` permite borrar `%LOCALAPPDATA%\FuelOpt` con consentimiento explícito.

El instalador y el desinstalador nunca deben modificar tareas de nombre similar que no pertenezcan inequívocamente a FuelOpt.
