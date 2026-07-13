# Reconciliación de la PR #2

Este documento registra la revisión de **#2 — Integrate recovered FuelOpt improvements**. La PR parte de `work/preserve-local-merged-20260711-210900`, con head `b5dcbbb42692fc2d3e1b36f8a48a110beb5297f0`.

No se fusiona completa porque contiene arquitectura anterior e implementaciones incompatibles con la aplicación local Windows, el refresco directo, el launcher frozen y la distribución vigente. La funcionalidad válida se reimplementó selectivamente sobre la rama final.

## A. Recuperado

| Área | Decisión |
|---|---|
| Contrato de optimización | Recuperados `economic`, `minimal_detour` y `balanced`. |
| Ranking | Orden determinista, balanced 50/50 y aplicación final de `result_limit`. |
| Interfaz | Selector accesible, presentación del modo y `why_selected` específico. |
| Transparencia | Identificación visible de OpenRouteService y de la estimación Haversine. |
| Validación | Tests relevantes portados y adaptados a la arquitectura vigente. |

## B. Ya existía de forma equivalente

| Área | Implementación vigente |
|---|---|
| Consulta | `result_limit` y regreso al origen en el frontend. |
| Datos | `refresh_service`, protección del refresco y bootstrap. |
| Windows | Scheduler, launcher frozen y cierre cooperativo Win32. |
| Catálogo | Gestión vigente de marcas independientes. |

## C. Pospuesto a 0.2.0

- `remaining_fuel_liters`, autonomía, margen de seguridad y warnings de estaciones inalcanzables.
- Skeleton de marcas, selección top-10, tooltips adicionales y niveles de precisión.
- Sufijos visuales adicionales que no sean necesarios para explicar el criterio actual.

Estas propuestas requieren una decisión de producto y pruebas propias; no forman parte de 0.1.0.

## D. Descartado

- Railway, hosting web anterior, GoatCounter y `fuelopt.es`.
- Leaflet mediante CDN/unpkg y el frontend antiguo completo.
- Refresco antiguo mediante subprocess y worker anterior del launcher.
- Ocultación de Haversine y documentación cloud obsoleta.

La PR #2 debe cerrarse como **superseded** únicamente después de que la nueva PR final incluya la reconciliación, pase todos sus checks y documente expresamente estas decisiones.
