# Guía de usuario

## Empezar

1. Abre FuelOpt desde el menú Inicio o el acceso directo.
2. Busca una localidad o haz doble clic en el mapa para indicar la salida.
3. Si el viaje no termina en el mismo lugar, desactiva **Regreso al origen** e indica el destino.
4. Selecciona combustible, litros o presupuesto, consumo y marcas.
5. Elige un objetivo y pulsa **Calcular mejor repostaje**.

La primera apertura muestra una ayuda breve. Puede abrirse de nuevo desde **Ayuda rápida**.

## Objetivos de optimización

### Más ahorro (`economic`)

Prioriza el resultado económico neto estimado. Considera el precio y el coste del desplazamiento; no equivale simplemente a elegir el menor precio por litro.

### Menor desvío (`minimal_detour`)

En un trayecto prioriza la menor distancia adicional. En una búsqueda local prioriza la estación más cercana. La economía se utiliza para desempatar.

### Equilibrado (`balanced`)

Combina por igual la posición económica y la posición por desvío. No suma directamente euros y kilómetros y su puntuación interna no se muestra.

FuelOpt ordena todo el universo válido y aplica el límite de resultados al final. La mejor opción aparece primero y las alternativas conservan el orden calculado.

## Rutas y estimaciones

Con una clave OpenRouteService, FuelOpt puede geocodificar direcciones y calcular distancias por carretera. La interfaz identifica ORS como OpenRouteService.

Si ORS no está disponible, el cálculo puede continuar con Haversine, una aproximación geográfica local. La interfaz la presenta como estimación, no como ruta real.

## Catálogo y precios

Las estaciones y precios proceden del catálogo oficial de MINETUR. FuelOpt trabaja sobre una copia SQLite local y muestra la información de frescura disponible.

Los precios pueden cambiar y la disponibilidad no está garantizada. Confirma la información antes de desplazarte.

## Uso sin conexión

La última base válida permite realizar consultas limitadas sin red. No se podrán descargar precios nuevos, teselas del mapa ni rutas ORS. Leaflet se incluye localmente, pero las teselas de OpenStreetMap requieren conexión.

## Privacidad y soporte

Las búsquedas se procesan en el servidor local. ORS recibe los puntos necesarios cuando se usa; OpenStreetMap recibe las peticiones de teselas. Google Maps solo recibe origen, destino y estación cuando el usuario pulsa **Abrir en Maps**.

**Mándanos tu idea** abre GitHub Issues. El usuario decide qué información publica y no debe incluir secretos ni datos sensibles. Consulta [Privacidad](../static/privacy.html) y [Seguridad](../SECURITY.md).
