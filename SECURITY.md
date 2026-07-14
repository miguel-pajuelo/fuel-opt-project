# Política de seguridad

## Versiones soportadas

FuelOpt está en pre-release y todavía no existen versiones públicas soportadas. Esta política y la matriz de soporte se revisarán antes de aprobar la primera publicación.

## Informar de una vulnerabilidad

No publiques claves, credenciales, tokens, datos personales ni detalles explotables en GitHub Issues. Si el repositorio ofrece el canal privado de seguridad de GitHub, utilízalo. Si no aparece un canal privado, abre únicamente un Issue sin información sensible para solicitar instrucciones antes de compartir la evidencia.

GitHub Issues se reserva para ideas y errores no sensibles. FuelOpt ya no incluye un formulario de correo ni solicita una dirección de correo dentro de la aplicación. No se inventa ni se ofrece aquí una dirección privada que no exista.

Incluye, cuando pueda compartirse con seguridad:

- versión o commit afectado;
- componente y escenario;
- pasos mínimos de reproducción saneados;
- impacto observado y esperado;
- versión de Windows y tipo de instalación;
- mitigaciones conocidas.

No se promete un SLA. La respuesta depende de la disponibilidad del mantenedor y del alcance reproducible del informe.

## Controles vigentes

- El servidor local se enlaza de forma predeterminada a `127.0.0.1`; no se publica en la red.
- CORS y la documentación OpenAPI están desactivados por defecto y solo se habilitan mediante configuración explícita de desarrollo.
- Los secretos deben permanecer fuera del repositorio. La clave ORS se guarda preferentemente en Windows Credential Manager; una variable de entorno local queda disponible para desarrollo y migración.
- Los errores procedentes de ORS y de la red se convierten en mensajes públicos estables. Los logs normales no incluyen claves, URLs preparadas, parámetros `api_key`, cabeceras `Authorization` ni texto crudo de esas excepciones.
- `tests/security_check.py` es obligatorio dentro de `scripts/release_check.cmd`; un fallo detiene el gate de release.

## Limitaciones conocidas

La interfaz no aplica todavía una Content Security Policy estricta. Los ejecutables e instaladores actuales tampoco están firmados digitalmente. Estas limitaciones, junto con la revisión final de dependencias y artefactos, permanecen abiertas en el [backlog de revisión](docs/FINAL_REVIEW_BACKLOG.md).
