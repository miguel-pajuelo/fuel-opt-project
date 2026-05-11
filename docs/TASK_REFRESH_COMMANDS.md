# FuelOpt Catalog Refresh - comandos utiles

La tarea programada se llama:

```powershell
FuelOpt Catalog Refresh
```

## Ver estado de la tarea

```powershell
Get-ScheduledTask -TaskName "FuelOpt Catalog Refresh"
```

Estado habitual:

- `Ready`: preparada, no esta ejecutando ahora.
- `Running`: esta ejecutando el refresh.
- `Queued`: Windows la tiene en cola.
- `Disabled`: esta desactivada.

## Ver ultima ejecucion y proxima ejecucion

```powershell
Get-ScheduledTaskInfo -TaskName "FuelOpt Catalog Refresh"
```

Campos utiles:

- `LastRunTime`: ultima vez que se ejecuto.
- `NextRunTime`: proxima ejecucion programada.
- `LastTaskResult`: resultado de la ultima ejecucion.
- `NumberOfMissedRuns`: ejecuciones perdidas.

## Arrancar el refresh ahora

```powershell
schtasks /Run /TN "FuelOpt Catalog Refresh"
```

El mensaje `CORRECTO: se ha intentado ejecutar...` significa que Windows acepto la orden de arranque. Para saber si realmente esta corriendo, consulta el estado con:

```powershell
Get-ScheduledTask -TaskName "FuelOpt Catalog Refresh"
```

## Parar el refresh si esta corriendo

```powershell
Stop-ScheduledTask -TaskName "FuelOpt Catalog Refresh"
```

Alternativa con `schtasks`:

```powershell
schtasks /End /TN "FuelOpt Catalog Refresh"
```

## Ver procesos relacionados

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*refresh_catalog.py*" -or $_.CommandLine -like "*run_refresh_catalog.cmd*" } |
  Select-Object ProcessId,Name,CommandLine
```

## Ver ultimo reporte del refresh

```powershell
Get-Content "data\reports\catalog_refresh_report.json" |
  ConvertFrom-Json |
  Select-Object started_at,finished_at,refresh_status,source,validation_ok
```

Valores esperados:

- `refresh_status = ok`: refresco publicado correctamente.
- `refresh_status = failed_validation`: se construyo una DB candidata, pero no paso validacion.
- `refresh_status = failed`: fallo el proceso.
- `refresh_status = skipped`: habia otro refresh activo o un lock reciente.

## Ver logs

```powershell
Get-Content "data\reports\catalog_refresh.log" -Tail 80
```

## Ejecutar el refresh en primer plano, sin tarea programada

```powershell
python scripts\refresh_catalog.py --source auto
```

Esto muestra el resultado directamente en la terminal.

## Estructura de datos generados

```text
data\cache\    snapshots y caches reutilizables
data\db\       SQLite activa y backups recientes
data\reports\  reporte y log del refresco automatico
```

## Desactivar la tarea automatica

```powershell
Disable-ScheduledTask -TaskName "FuelOpt Catalog Refresh"
```

## Reactivar la tarea automatica

```powershell
Enable-ScheduledTask -TaskName "FuelOpt Catalog Refresh"
```

## Eliminar la tarea automatica

```powershell
schtasks /Delete /TN "FuelOpt Catalog Refresh" /F
```
