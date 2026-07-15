# Security policy

## Versiones soportadas

La versión más reciente publicada de la serie 0.1.x recibe correcciones de seguridad. Al publicarse una revisión, las anteriores dejan de mantenerse. La versión vigente está disponible en [Latest release](https://github.com/miguel-pajuelo/fuel-opt-project/releases/latest).

## Reportar una vulnerabilidad

No publiques claves, credenciales, datos personales, trazas sensibles ni instrucciones explotables en GitHub Issues. Usa el canal privado de seguridad de GitHub cuando esté disponible en el repositorio. Si no aparece un canal privado adecuado, limita el reporte público a indicar que existe un posible problema de seguridad, sin incluir detalles sensibles.

GitHub Issues se reserva para ideas, errores funcionales y problemas no sensibles. FuelOpt no utiliza formularios SMTP ni solicita correo electrónico dentro de la aplicación.

## Principios de seguridad

- El servidor escucha en `127.0.0.1` de forma predeterminada.
- La escucha en `0.0.0.0` requiere habilitar explícitamente el acceso LAN; no es el modo predeterminado.
- CORS permanece cerrado salvo que se configure una allowlist explícita. OpenAPI, Swagger y ReDoc están desactivados por defecto.
- Las cabeceras vigentes incluyen `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` y una `Permissions-Policy` limitada.
- Los headers reenviados solo se usan cuando se habilita conscientemente la confianza en proxy. No confíes en headers de proxies no autorizados.
- Los logs normales anonimizan la IP del cliente. El modo diagnóstico puede registrar más información técnica y debe activarse solo en un entorno controlado.
- Los secretos se mantienen fuera del repositorio.
- La clave ORS se guarda preferentemente en Windows Credential Manager; las variables de entorno se reservan para desarrollo local.
- Los errores procedentes de ORS se convierten en mensajes públicos estables y no exponen URLs preparadas, cabeceras o texto crudo de excepciones.
- `tests/security_check.py` forma parte obligatoria del release gate.
- Los bundles se revisan para excluir secretos, configuración privada, rutas personales y datos mutables.

## Limitaciones conocidas

La interfaz no aplica todavía una Content Security Policy estricta. Los ejecutables y el instalador no están firmados digitalmente, por lo que Windows puede mostrar advertencias de reputación. Estas limitaciones no sustituyen la verificación del origen y los checksums de cada descarga.
