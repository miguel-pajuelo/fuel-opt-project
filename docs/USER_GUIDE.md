# Guía de usuario

## Preparar una consulta

1. Selecciona origen y destino.
2. Indica si el viaje es solo de ida o de ida y vuelta.
3. Elige el combustible.
4. Introduce litros o presupuesto, según el modo seleccionado.
5. Indica el consumo medio del vehículo.
6. Limita, si quieres, las marcas consideradas.
7. Selecciona el objetivo de optimización disponible en la interfaz.

FuelOpt compara estaciones candidatas y muestra una recomendación y alternativas. El **ahorro estimado** compara el coste calculado con una referencia; no es dinero garantizado. El **coste del desvío** estima el combustible consumido en la distancia adicional. Peajes, tráfico, tiempo, errores de ubicación y cambios posteriores de precio pueden alterar el resultado.

## Rutas y distancias

Con una clave ORS configurada, FuelOpt intenta geocodificar y obtener rutas por carretera. Si ORS falta o falla, puede usar Haversine: una distancia geométrica que no conoce carreteras, sentidos, barreras ni tráfico. Una ruta mostrada nunca implica precisión absoluta.

## Precios y frescura

Los precios proceden de fuentes externas y pueden ser antiguos, incompletos o degradados. La interfaz indica la frescura disponible. FuelOpt no garantiza precio, disponibilidad ni actualización en tiempo real; confirma la información antes de desplazarte.

El catálogo puede actualizarse al abrir, manualmente o mediante una tarea periódica. Consulta [CONFIGURATION.md](CONFIGURATION.md).

## Funcionamiento offline

La última base válida permite consultas limitadas sin conexión. El mapa puede quedar incompleto porque Leaflet está incluido localmente, pero las teselas se solicitan a un proveedor externo. ORS y los refrescos también requieren red.

## Privacidad, logs y soporte

La consulta se procesa en el servidor local, aunque ORS, las teselas y las fuentes de precios reciben las solicitudes necesarias y pueden ver la IP. FuelOpt no incorpora telemetría propia. Los logs técnicos se guardan bajo `%LOCALAPPDATA%\FuelOpt\logs` y pueden incluir errores o rutas técnicas, pero no deberían incluir la clave ORS.

El formulario de feedback depende de una configuración SMTP que puede no estar disponible en instalaciones públicas. Para problemas consulta [TROUBLESHOOTING.md](TROUBLESHOOTING.md) y [SECURITY.md](../SECURITY.md).
