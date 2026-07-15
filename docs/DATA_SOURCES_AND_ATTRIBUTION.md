# Fuentes de datos y atribución

## Fuente oficial

La semilla de FuelOpt procede del catálogo oficial de estaciones de servicio publicado por el **Ministerio de Industria y Turismo (MINETUR)** a través del [Geoportal de gasolineras](https://geoportalgasolineras.es/). La copia incluida fue obtenida el `2026-06-04T22:27:28+0200`.

Las [condiciones oficiales de reutilización](https://sede.serviciosmin.gob.es/es-ES/Paginas/aviso.aspx#Reutilizacion) exigen citar la fuente y la fecha de actualización, preservar la integridad del contenido y sus metadatos y no desnaturalizar el sentido de la información.

Los precios pueden cambiar después de la fecha indicada. FuelOpt no garantiza que una estación conserve el precio o la disponibilidad mostrados.

## Transformación local

FuelOpt conserva el snapshot recibido y transforma sus registros a una estructura SQLite local para poder validar, consultar y ordenar el catálogo de manera eficiente. La transformación normaliza nombres de campos, tipos numéricos, coordenadas, combustibles y rótulos; no pretende cambiar el significado de los datos oficiales. La base conserva metadata de fuente, fechas y versión del dataset.

Los hashes, la fecha de obtención, la versión del esquema y los archivos concretos de la semilla están registrados en [`data/SEED_PROVENANCE.json`](../data/SEED_PROVENANCE.json). Esa metadata permite comprobar que el snapshot y la SQLite incluidos corresponden a la misma entrega aprobada.

## Arranque y refresco

El primer arranque copia la semilla instalada al perfil del usuario sin esperar una descarga. Después, el refresco puede consultar MINETUR según la configuración vigente, preparar y validar una base candidata y sustituir la base activa de forma atómica. Si la consulta o validación falla, FuelOpt conserva la última base válida.

MINETUR es la única fuente productiva del catálogo en FuelOpt 0.1.0. La semilla y los refrescos utilizan ese catálogo oficial, y FuelOpt procesa las estaciones con criterios neutrales respecto a su marca.
