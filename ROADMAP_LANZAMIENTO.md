# FuelOpt — Roadmap de lanzamiento público

**Última actualización:** 2026-05-13  
**Estado actual del producto:** funcional localmente, ~65 % listo para producción pública.  
**Objetivo de este documento:** que cualquier persona que conozca el proyecto pueda continuar el trabajo sin perder contexto, sabiendo exactamente qué hay que hacer, por qué y en qué orden.

---

## 0. Estrategia: MVP público → escala futura → monetización

**Objetivo de la Fase 0-3:** Lanzar un MVP público funcional y estable en infraestructura económica (Oracle Cloud Free Tier + ORS Free Tier) que permita validar con usuarios reales sin quemar presupuesto.

**Limitaciones aceptadas del MVP:**
- ORS limitado a 2.000 req/día (free tier): suficiente para ~500 optimizaciones/día, razonable para lanzamiento.
- Oracle Free: 4 OCPUs ARM + 24 GB RAM + 20 GB almacenamiento. Capacidad estimada: 20-50 usuarios concurrentes.
- Sin caché de resultados ORS, sin Redis, sin CDN de contenidos.

**Visión paralela — Escalar ORS sin refactorizar:**
El código debe estar preparado para escalar ORS pagando cuando sea necesario. Está documentado:
- **1.2** (CORS configurable): habilita separar frontend y API en dominios distintos, necesario para distribuir carga.
- **2.3** (Logging + Analytics): permite detectar cuándo se alcanza el límite de ORS (429 Too Many Requests) y tomar decisiones informadas sobre upgrade.
- **3.1** (Cache-Control): reduce carga innecesaria en endpoints estáticos, estirando los recursos gratuitos.
- **Código futuro recomendado** (no bloqueante ahora): caché de matrices ORS en memoria (`@functools.lru_cache`) o Redis. Ver Sección 6.

**Visión paralela — Monetización con tip jar:**
Una vez el MVP esté en producción, estable, con al menos 100-200 usuarios mensuales activos, se implementará:
1. Botón "Invítame a un café" (Ko-fi o Buy Me a Coffee) en el footer.
2. Mensaje contextual: "Si FuelOpt te ha ahorrado €X este mes, considera apoyar el proyecto".
3. Tarjeta de afiliado (Rastreator, Acierto) para seguros de coche si el usuario busca productos relacionados.

La monetización NO es bloqueante para el lanzamiento, pero SÍ debe estar planificada. El código debe permitir añadir estos elementos sin refactorización. Ver **Fase 4 (futuro)** en esta sección.

---

## 1. Qué es FuelOpt y en qué punto está

FuelOpt es una aplicación web que ayuda a conductores españoles a encontrar la gasolinera más económica teniendo en cuenta no solo el precio del combustible, sino el desvío de la ruta y el consumo del vehículo. El coste efectivo que calcula incluye precio × litros + combustible gastado en el desvío.

### Stack técnico actual

| Componente | Tecnología |
|---|---|
| Backend | FastAPI 0.136 + Uvicorn, Python 3.12 |
| Base de datos | SQLite (`data/db/gas_stations.sqlite`), ~12.000 gasolineras y ~37.000 precios |
| Frontend | HTML/CSS/JS estático, Leaflet 1.9.4 |
| Geocodificación y rutas | OpenRouteService API (`ORS_API_KEY` en `.env`) |
| Datos de precios | MINETUR (API pública del Ministerio de Energía de España) |
| Fallback de rutas | Cálculo Haversine propio (sin dependencia externa) |
| Refresco de datos | Tarea programada de Windows: `FuelOpt Catalog Refresh`, cada 4 horas |

### Lo que funciona hoy

- Optimización completa en modos litros y presupuesto.
- Búsqueda por corredor (origen → destino) y radial (solo origen, regreso al punto de partida).
- Filtro por marca de gasolinera.
- Tres modos de optimización: máximo ahorro / equilibrado / mínimo desvío.
- Geocodificación con autocomplete (depende de ORS).
- Fallback automático a Haversine si ORS falla durante la optimización.
- Geolocalización del usuario en el mapa con círculo de precisión.
- Refresco automático del catálogo de precios cada 4 horas (tarea programada Windows).
- Tests de pipeline, frontend estático, adaptadores y política de refresco: todos en verde.

### Lo que falta para lanzar al público

La lógica de negocio está sólida. Lo que falta es el andamiaje de infraestructura, seguridad y legal que hace que la app sea segura y operable en un servidor público. Se desglosa en las secciones siguientes.

---

## 2. Contexto sobre el refresco de datos

**Importante para quien continúe el trabajo:** el refresco del catálogo de precios ya está automatizado mediante una tarea programada de Windows llamada `"FuelOpt Catalog Refresh"` que se ejecuta cada 4 horas en el PC de desarrollo. No hay que implementar ningún cron en el código.

La tarea ejecuta `scripts/refresh_catalog.py --source auto`, que:
1. Descarga datos en vivo de MINETUR.
2. Si MINETUR falla (TLS, red, rate limit), cae automáticamente al snapshot local.
3. Valida la base candidata (mínimo 8.000 estaciones y 20.000 precios).
4. Solo publica la nueva base si pasa la validación, reemplazando la activa de forma atómica.
5. Escribe un reporte en `data/reports/catalog_refresh_report.json`.

**Al migrar a un servidor de producción** (VPS, Hetzner, etc.) esta tarea deberá recrearse en el servidor como un cron de Linux o un systemd timer. No requiere cambios de código, solo configuración del servidor. El comando equivalente sería:

```bash
# /etc/cron.d/fuelopt o systemd timer
0 */4 * * * /path/to/venv/bin/python /opt/fuelopt/scripts/refresh_catalog.py --source auto
```

---

## 3. Fases del roadmap

### Fase 0 — Fundamentos de seguridad y legal *(bloqueante: no distribuir la URL sin esto)*

Tiempo estimado: 6-8 horas de desarrollo.

---

#### 0.1 Rate limiting en la API

**Por qué es crítico:** ahora mismo cualquier bot puede hacer miles de peticiones a `/optimize` en cuestión de minutos, agotando el cupo diario de OpenRouteService (2.000 peticiones/día en el tier gratuito) y potencialmente saturando el servidor. Un único usuario malintencionado puede tumbar el servicio para todos.

**Qué hay que hacer:**

Añadir `slowapi` a las dependencias (es compatible con FastAPI/Starlette, no introduce librerías pesadas):

```
# Añadir a requirements-web.txt
slowapi==0.1.9
```

En `app/api/main.py`, registrar el limitador:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Y decorar los endpoints de mayor coste:

```python
@app.post("/optimize")
@limiter.limit("20/minute")
async def optimize(request: Request, payload: OptimizeRequest):
    ...

@app.get("/geocode")
@limiter.limit("40/minute")
async def geocode(request: Request, ...):
    ...

@app.post("/catalog/refresh")
@limiter.limit("2/minute")
async def refresh_catalog(request: Request):
    ...
```

Los valores `20/minute` y `40/minute` son un punto de partida razonable. Ajustar tras el primer mes con datos reales de uso.

**Archivos a modificar:** `app/api/main.py`, `requirements-web.txt`

---

#### 0.2 Validación de variables de entorno al arrancar

**Por qué importa:** actualmente, si `ORS_API_KEY` está vacía o el fichero `.env` no existe, el servidor arranca sin errores pero falla silenciosamente en la primera llamada de geocodificación. En producción esto significa que el servidor parece "sano" (el endpoint `/health` responde 200) pero la funcionalidad principal está rota.

**Qué hay que hacer:**

En `app/api/main.py`, añadir un evento de startup:

```python
from app.config import load_settings

@app.on_event("startup")
def validate_config():
    cfg = load_settings()
    if not cfg.ors_api_key:
        import logging
        logging.warning(
            "ORS_API_KEY no está configurada. "
            "Geocodificación y rutas reales no estarán disponibles."
        )
    db_path = cfg.db_path
    if not db_path.exists():
        raise RuntimeError(
            f"Base de datos no encontrada en {db_path}. "
            "Ejecuta scripts/refresh_catalog.py antes de arrancar."
        )
```

Nota: se usa `warning` en lugar de excepción para `ORS_API_KEY` porque la app puede funcionar en modo Haversine sin ella. El fallo de arranque solo aplica a la base de datos, que es estrictamente necesaria.

**Archivos a modificar:** `app/api/main.py`

---

#### 0.3 Política de privacidad y cumplimiento GDPR

**Por qué es crítico:** la app recibe coordenadas de origen y destino de los usuarios y las reenvía a OpenRouteService (un servicio de terceros ubicado en Alemania). Bajo el RGPD esto cuenta como transferencia de datos personales a un encargado del tratamiento. Sin una política de privacidad que lo declare hay responsabilidad legal.

La app no guarda logs de búsquedas ni coordenadas en base de datos, lo cual es positivo. Pero hay que comunicarlo.

**Qué hay que hacer:**

1. Crear `static/privacy.html` con el contenido mínimo legal:
   - Quién es el responsable del tratamiento (nombre/empresa o nombre del desarrollador).
   - Qué datos se procesan (coordenadas de origen/destino, introducidas voluntariamente por el usuario).
   - Con qué finalidad (calcular la ruta óptima de repostaje).
   - Qué terceros reciben datos: OpenRouteService GmbH (geocodificación y rutas), OpenStreetMap Foundation (tiles del mapa), unpkg.com/jsDelivr (scripts de Leaflet).
   - Que no se almacenan búsquedas ni se crean perfiles de usuario.
   - Datos de contacto para ejercer derechos RGPD.

2. Añadir enlace en el footer de `static/index.html`:

```html
<footer class="legal-footer">
  <a href="/static/privacy.html">Política de privacidad</a>
</footer>
```

3. Añadir una ruta en `app/api/main.py` si se prefiere servir desde la raíz en lugar de `/static/privacy.html`:

```python
@app.get("/privacidad", response_class=HTMLResponse)
def privacy():
    return (STATIC_DIR / "privacy.html").read_text(encoding="utf-8")
```

**Nota sobre cookies:** la app actualmente no usa cookies propias ni `localStorage` para datos sensibles. Los tiles de OpenStreetMap y Leaflet cargado desde CDN pueden establecer cookies de terceros. Si se decide añadir analytics (ver Fase 3), habrá que añadir banner de consentimiento en ese momento. Por ahora no es necesario.

**Archivos a crear/modificar:** `static/privacy.html`, `static/index.html`, opcionalmente `app/api/main.py`

---

#### 0.4 Error tracking en producción (Sentry)

**Por qué importa:** sin este punto eres ciego en producción. Si `/optimize` falla para un subconjunto de usuarios (coordenadas fuera de rango, combinación de parámetros no probada, bug de regresión), no lo sabrás hasta que alguien se queje.

**Qué hay que hacer:**

Añadir `sentry-sdk` a las dependencias:

```
# requirements-web.txt
sentry-sdk[fastapi]==2.x.x
```

En `app/api/main.py`:

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

sentry_dsn = os.getenv("SENTRY_DSN", "")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=0.1,  # 10% de requests para performance tracking
        send_default_pii=False,  # no enviar IPs ni headers con datos personales
    )
```

Añadir `SENTRY_DSN` a `.env.example`:

```
SENTRY_DSN=           # DSN del proyecto en sentry.io (dejar vacío para deshabilitar)
```

Sentry tiene tier gratuito (5.000 errores/mes) que es más que suficiente para el lanzamiento. Si `SENTRY_DSN` está vacío, el bloque se salta sin efectos secundarios.

**Archivos a modificar:** `app/api/main.py`, `requirements-web.txt`, `.env.example`

---

### Fase 1 — Deploy reproducible

Tiempo estimado: 5-6 horas.

---

#### 1.1 Dockerfile

**Por qué importa:** sin Docker, desplegar en un servidor nuevo implica instalar manualmente Python, crear virtualenv, gestionar versiones, configurar paths. Es frágil y no reproducible. Con Docker, el despliegue es `docker compose up -d`.

**Qué hay que hacer:**

Crear `Dockerfile` en la raíz:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copiar código fuente
COPY app/ ./app/
COPY static/ ./static/
COPY scripts/ ./scripts/
COPY main.py .

# Crear directorios de datos (se montarán como volumen)
RUN mkdir -p data/db data/cache data/reports

# Usuario sin privilegios
RUN useradd -m fuelopt
USER fuelopt

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Crear `.dockerignore`:

```
.env
data/
__pycache__/
*.pyc
.git/
dist/
build/
tests/
*.log
```

Crear `docker-compose.yml` para desarrollo y producción:

```yaml
services:
  web:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data        # datos persistentes fuera del contenedor
      - ./.env:/app/.env:ro     # secretos montados como solo lectura
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Nota crítica sobre los datos:** el directorio `data/` se monta como volumen externo al contenedor. Esto es intencional: la base SQLite y los snapshots deben persistir entre reinicios y actualizaciones del contenedor. El script de refresco del catálogo debe ejecutarse contra el volumen, no dentro del contenedor efímero.

**Archivos a crear:** `Dockerfile`, `.dockerignore`, `docker-compose.yml`

---

#### 1.2 CORS configurable por variable de entorno

**Por qué importa:** hoy frontend y API están en el mismo servidor (misma URL). Si en el futuro se separan (por ejemplo, frontend en Vercel o Cloudflare Pages, API en Hetzner), las peticiones del frontend serán bloqueadas por el navegador por política CORS. Añadirlo ahora cuesta 10 minutos y evita un problema de debugging oscuro más adelante.

**Qué hay que hacer:**

En `app/config.py`, añadir:

```python
cors_origins: list[str] = field(
    default_factory=lambda: [o.strip() for o in
        os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
)
```

En `app/api/main.py`:

```python
from starlette.middleware.cors import CORSMiddleware

cfg = load_settings()
if cfg.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
```

En `.env.example`:

```
CORS_ORIGINS=          # Lista separada por comas. Ej: https://fuelopt.es,https://www.fuelopt.es
```

Si `CORS_ORIGINS` está vacío (caso por defecto, mismo dominio), el middleware no se añade y no hay overhead.

**Archivos a modificar:** `app/config.py`, `app/api/main.py`, `.env.example`

---

#### 1.3 CI/CD con GitHub Actions

**Por qué importa:** los tests existen y están bien escritos, pero no corren automáticamente. Cualquier cambio que rompa el pipeline de optimización, los checks del frontend o los adaptadores pasará desapercibido hasta que alguien lo descubra en producción.

**Qué hay que hacer:**

Crear `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Instalar dependencias
        run: pip install -r requirements-web.txt

      - name: Crear datos mínimos de test
        run: |
          mkdir -p data/db data/cache data/reports
          # Los tests crean su propia SQLite temporal; solo necesitamos el directorio

      - name: Tests de sanidad
        run: python tests/sanity_check.py

      - name: Tests de adaptadores
        run: python tests/test_adapters.py

      - name: Tests de frontend estático
        run: python tests/frontend_static_check.py

      - name: Tests del pipeline web
        run: python tests/web_pipeline_check.py

      - name: Compilar módulos Python
        run: python -m compileall app -q
```

**Nota:** el test `web_pipeline_check.py` crea su propia SQLite en memoria o temporal, no necesita la base de producción.

**Archivos a crear:** `.github/workflows/ci.yml`

---

### Fase 2 — Operaciones y observabilidad

Tiempo estimado: 4-5 horas.

---

#### 2.1 Logging estructurado de requests

**Por qué importa:** los logs de Uvicorn por defecto solo muestran método, path y código HTTP. No hay registro de tiempo de respuesta, IP, ni qué payload causó un error. En producción esto hace inviable diagnosticar problemas.

**Qué hay que hacer:**

En `app/api/main.py`, añadir un middleware de logging:

```python
import logging
import time
import uuid

logger = logging.getLogger("fuelopt.api")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "ip": request.client.host if request.client else "unknown",
        },
    )
    return response
```

Configurar el formato JSON en `main.py` al arrancar:

```python
import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        data.update(getattr(record, "__dict__", {}))
        return json.dumps(data, ensure_ascii=False, default=str)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(handlers=[handler], level=logging.INFO)
```

**Archivos a modificar:** `app/api/main.py`, `main.py`

---

#### 2.2 Alerting si el refresco del catálogo falla

**Por qué importa:** si el refresco falla repetidamente (MINETUR cambia su API, el servidor de producción pierde conectividad), los precios se quedarán desactualizados. Sin alertas no sabrás hasta que un usuario se queje de datos incorrectos.

**Qué hay que hacer:**

Modificar `scripts/refresh_catalog.py` para que al finalizar con `refresh_status != "ok"` envíe una notificación. La forma más simple es un webhook (funciona con Telegram, Slack, Discord, ntfy.sh):

```python
import os
import requests

def _notify_failure(status: str, reason: str) -> None:
    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "")
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={
            "text": f"[FuelOpt] Refresco de catálogo: {status}. Motivo: {reason}"
        }, timeout=10)
    except Exception:
        pass  # el alerting no debe bloquear ni crashear el proceso principal
```

Añadir a `.env.example`:

```
ALERT_WEBHOOK_URL=     # URL de webhook para alertas de refresco fallido (Telegram, Slack, ntfy.sh...)
```

Para Telegram, la URL tiene la forma `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>`.  
Para ntfy.sh (solución self-hosted gratuita): `https://ntfy.sh/mi-canal-fuelopt`.

**Archivos a modificar:** `scripts/refresh_catalog.py`, `.env.example`

---

#### 2.3 SEO básico y robots.txt

**Por qué importa:** ahora `static/index.html` solo tiene `<title>FuelOpt</title>` y ninguna meta tag. Si alguien comparte el enlace en WhatsApp no habrá preview. Si alguien busca en Google "optimizador gasolineras España" no encontrará la app.

**Qué hay que hacer:**

En `static/index.html`, añadir en `<head>`:

```html
<title>FuelOpt — Encuentra la gasolinera más barata en tu ruta</title>
<meta name="description" content="Calcula qué gasolinera te sale más barata teniendo en cuenta el precio del combustible y el desvío de tu ruta. Gratis, sin registro.">
<meta property="og:title" content="FuelOpt — Optimizador de repostaje">
<meta property="og:description" content="Encuentra la gasolinera más económica en tu ruta por España. Compara precio real incluyendo el coste del desvío.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://fuelopt.es">
<meta name="theme-color" content="#171411">
```

Crear `static/robots.txt`:

```
User-agent: *
Allow: /
Sitemap: https://fuelopt.es/sitemap.xml
```

Añadir endpoint en `app/api/main.py`:

```python
from starlette.responses import PlainTextResponse

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return (STATIC_DIR / "robots.txt").read_text()
```

**Nota sobre el SPA:** la app es una Single Page Application. Google y otros motores modernos ejecutan JavaScript al crawlear, por lo que el contenido dinámico (lista de gasolineras) es indexable. Sin embargo, para SEO solo importa el contenido inicial de la página, que es el formulario de búsqueda y el mapa, no los resultados.

**Archivos a modificar/crear:** `static/index.html`, `static/robots.txt`, `app/api/main.py`

---

#### 2.4 Migrar el refresco automático al servidor de producción

**Cuándo:** en el momento de hacer el primer despliegue en servidor.

**Qué hay que hacer:** la tarea programada de Windows `"FuelOpt Catalog Refresh"` que corre en el PC de desarrollo deberá recrearse en el servidor Linux. El equivalente es un systemd timer o una entrada en crontab.

Opción recomendada (systemd timer en Ubuntu/Debian):

Crear `/etc/systemd/system/fuelopt-refresh.service`:

```ini
[Unit]
Description=FuelOpt catalog refresh
After=network.target

[Service]
Type=oneshot
User=fuelopt
WorkingDirectory=/opt/fuelopt
ExecStart=/opt/fuelopt/venv/bin/python scripts/refresh_catalog.py --source auto
StandardOutput=journal
StandardError=journal
```

Crear `/etc/systemd/system/fuelopt-refresh.timer`:

```ini
[Unit]
Description=FuelOpt catalog refresh every 4 hours

[Timer]
OnBootSec=10min
OnUnitActiveSec=4h
Persistent=true

[Install]
WantedBy=timers.target
```

Activar:

```bash
systemctl daemon-reload
systemctl enable --now fuelopt-refresh.timer
```

Verificar:

```bash
systemctl list-timers fuelopt-refresh.timer
journalctl -u fuelopt-refresh.service -n 50
```

Este paso no requiere cambios de código. Solo configuración del servidor.

---

### Fase 3 — Validación con usuarios reales *(primera semana tras lanzamiento)*

Estas tareas no son bloqueantes para lanzar, pero sí importantes para entender si la app funciona bien para usuarios reales y tomar decisiones informadas.

---

#### 3.1 Analytics de uso (Plausible)

**Por qué Plausible y no Google Analytics:** Plausible es GDPR-compliant de serie, no usa cookies, no necesita banner de consentimiento y es de código abierto. El script de tracking pesa 1 KB frente a los 45 KB de GA4.

**Qué hay que hacer:**

1. Crear cuenta en [plausible.io](https://plausible.io) (o auto-alojar).
2. Añadir en `<head>` de `static/index.html`:

```html
<script defer data-domain="fuelopt.es" src="https://plausible.io/js/script.js"></script>
```

3. Registrar eventos personalizados en `static/app.js` para medir las acciones clave:

```javascript
// Cuántas búsquedas se completan
function trackOptimization(resultCount) {
    if (window.plausible) {
        plausible('Optimización calculada', { props: { resultados: resultCount } });
    }
}
```

Los eventos importantes a rastrear son: "Optimización calculada", "Geolocalización usada", "Marca filtrada", "Modo presupuesto activado".

**Archivos a modificar:** `static/index.html`, `static/app.js`

---

#### 3.2 Mensaje de bienvenida para usuarios nuevos

**El problema actual:** cuando un usuario llega por primera vez ve el mapa vacío, dos campos "Sin seleccionar" y nada más. No hay ninguna instrucción sobre qué hacer. La tasa de abandono de primer contacto puede ser alta.

**Qué hay que hacer:**

Añadir en `static/index.html` un mensaje de primer uso dentro de `.map-top`:

```html
<div id="onboarding_hint" class="onboarding-hint">
  Busca tu punto de salida o pulsa en el mapa para empezar
</div>
```

En `static/app.js`, ocultar el mensaje en cuanto el usuario establece el primer punto:

```javascript
function hideOnboardingHint() {
    const hint = $('onboarding_hint');
    if (hint) hint.style.display = 'none';
}
// Llamar a hideOnboardingHint() dentro de setPoint()
```

**Archivos a modificar:** `static/index.html`, `static/app.js`, `static/styles.css`

---

#### 3.3 Caché HTTP en endpoints estáticos

**Por qué importa:** `/brands` y `/fuels` devuelven datos que cambian como máximo una vez cada 4 horas (con el refresco del catálogo). Sin cabeceras de caché, cada carga de página hace una petición nueva a estos endpoints.

**Qué hay que hacer:**

En `app/api/main.py`, añadir `Cache-Control` a los endpoints que no cambian frecuentemente:

```python
from starlette.responses import JSONResponse

@app.get("/brands")
def brands():
    data = get_brand_counts(...)
    response = JSONResponse(content=data)
    response.headers["Cache-Control"] = "public, max-age=3600"  # 1 hora
    return response

@app.get("/fuels")
def fuels():
    data = [...]
    response = JSONResponse(content=data)
    response.headers["Cache-Control"] = "public, max-age=86400"  # 24 horas
    return response
```

**Archivos a modificar:** `app/api/main.py`

---

#### 3.4 Load test básico

**Por qué importa:** antes de enviar el enlace a mucha gente, hay que saber cuántos usuarios concurrentes puede manejar el servidor. SQLite con WAL debería aguantar bien lecturas concurrentes, pero el cuello de botella podría estar en las llamadas a ORS (limitadas a 40 req/min en el tier gratuito) o en el tiempo de CPU del optimizador.

**Cómo hacerlo:**

Con `hey` (herramienta de carga HTTP, un solo binario):

```bash
# Instalar
go install github.com/rakyll/hey@latest

# Test básico: 200 peticiones con 10 concurrentes
hey -n 200 -c 10 -m POST \
  -H "Content-Type: application/json" \
  -d '{"origin_lat":40.4168,"origin_lon":-3.7038,"destination_lat":40.4168,"destination_lon":-3.7038,"fuel_type":"gasoleo_a","input_mode":"liters","liters":30,"consumption_l_100km":5.5,"use_ors":false,"result_limit":5}' \
  http://localhost:8000/optimize
```

El parámetro `use_ors: false` garantiza que el test no consume cupo de ORS. Los resultados mostrarán latencia p50/p95/p99 y tasa de errores.

Un servidor básico (Hetzner CX22, 2 vCPU, 4 GB RAM) debería responder 20-50 req/s sin ORS. Con ORS el cuello de botella es el rate limit del proveedor externo.

---

## 4. Resumen de archivos a crear/modificar por fase

### Fase 0

| Archivo | Acción | Tarea |
|---|---|---|
| `requirements-web.txt` | Modificar | Añadir `slowapi` y `sentry-sdk[fastapi]` |
| `app/api/main.py` | Modificar | Rate limiting, startup validation, Sentry init, CORS |
| `app/config.py` | Modificar | Campo `cors_origins` |
| `static/privacy.html` | Crear | Política de privacidad |
| `static/index.html` | Modificar | Enlace a privacidad |
| `.env.example` | Modificar | Añadir `SENTRY_DSN`, `CORS_ORIGINS` |

### Fase 1

| Archivo | Acción | Tarea |
|---|---|---|
| `Dockerfile` | Crear | Contenedor de producción |
| `.dockerignore` | Crear | Excluir `.env`, `data/`, `dist/` |
| `docker-compose.yml` | Crear | Orquestación con volumen de datos |
| `.github/workflows/ci.yml` | Crear | CI automático en cada push |

### Fase 2

| Archivo | Acción | Tarea |
|---|---|---|
| `app/api/main.py` | Modificar | Logging estructurado, robots.txt, cache headers |
| `main.py` | Modificar | Configurar formato JSON de logs |
| `scripts/refresh_catalog.py` | Modificar | Alertas de fallo por webhook |
| `static/robots.txt` | Crear | SEO |
| `static/index.html` | Modificar | Meta tags, og:tags |
| `.env.example` | Modificar | Añadir `ALERT_WEBHOOK_URL` |

### Fase 3

| Archivo | Acción | Tarea |
|---|---|---|
| `static/index.html` | Modificar | Plausible analytics, onboarding hint |
| `static/app.js` | Modificar | Eventos Plausible, ocultar hint al usar |
| `static/styles.css` | Modificar | Estilos del onboarding hint |
| `app/api/main.py` | Modificar | Cache-Control en `/brands` y `/fuels` |

### Fase 4 (inicia semana 3-4 post-lanzamiento)

| Archivo | Acción | Tarea |
|---|---|---|
| `static/index.html` | Modificar | Ko-fi button en footer |
| `static/app.js` | Modificar | Mensaje "Te has ahorrado €X" tras resultado |
| `static/styles.css` | Modificar | Estilos Ko-fi button y mensaje de ahorro |

---

### Fase 4 — Monetización con tip jar *(inicia en semana 3-4 tras lanzamiento, tras validar tráfico y estabilidad)*

**Por qué esperar y no hacerlo desde el día 1:**
- El producto debe demostrar valor real a usuarios antes de pedir dinero.
- Necesitas datos (Analytics) para medir si merece la pena.
- Concentrarse en funcionalidad y confiabilidad es más importante que ingresos en el MVP.

**Qué hay que hacer:**

#### 4.1 Ko-fi button en el footer

En `static/index.html`, añadir al final antes de `</body>`:

```html
<div id="support-footer" class="support-footer" style="display: none;">
  <a href="https://ko-fi.com/migelpajuelo" target="_blank" class="ko-fi-button">
    ☕ Apoya el proyecto
  </a>
</div>
<script>
  // Mostrar el botón solo después de 2 segundos de carga (para no distraer)
  setTimeout(() => {
    const btn = document.getElementById('support-footer');
    if (btn) btn.style.display = 'block';
  }, 2000);
</script>
```

En `static/styles.css`:

```css
.support-footer {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 1000;
  background: var(--gold);
  padding: 12px 16px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.ko-fi-button {
  color: white;
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
}

.ko-fi-button:hover {
  text-decoration: underline;
}
```

Crear cuenta en [ko-fi.com](https://ko-fi.com) y usar tu URL en el href.

#### 4.2 Mensaje contextual: "Te has ahorrado €X"

Cuando `/optimize` devuelve resultados con ahorro positivo, añadir un mensaje en `static/app.js`:

```javascript
function renderResult(data, index, scrollToTop) {
    // ... código existente ...
    
    const saving = selected.net_savings_eur || 0;
    if (saving > 0.50) {  // solo mostrar si el ahorro es significativo
        const supportMsg = document.createElement('div');
        supportMsg.className = 'savings-message';
        supportMsg.innerHTML = `
            <strong>¡Te has ahorrado €${saving.toFixed(2)}!</strong>
            Si FuelOpt te resulta útil, considera 
            <a href="https://ko-fi.com/migelpajuelo" target="_blank">apoyar el proyecto</a>.
        `;
        $('result').insertAdjacentElement('afterbegin', supportMsg);
    }
}
```

En `static/styles.css`:

```css
.savings-message {
  background: linear-gradient(135deg, #285848 0%, #2f5f4f 100%);
  color: var(--paper);
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
  border-left: 4px solid var(--gold);
}

.savings-message a {
  color: var(--gold);
  text-decoration: underline;
}
```

#### 4.3 Afiliado a comparador de seguros (opcional, más trabajo)

Una vez valides que hay usuarios activos, integrar un enlace de afiliado a Rastreator o Acierto.com. Estos permiten insertar un widget o link contextual. Solo hazlo si Plausible muestra que los usuarios completan optimizaciones (no abandonen antes).

Ejemplo: después de mostrar el resultado, un pequeño banner: *"Además de ahorrar en gasolina, ¿quieres aseguranza de coche barata? Compara aquí →"*

**Archivos a crear/modificar:**
- `static/index.html`: button Ko-fi
- `static/styles.css`: estilos del button y mensaje
- `static/app.js`: lógica de mostrar mensaje según ahorro

**Checklist antes de activar Fase 4:**
- [ ] Plausible muestra tráfico diario estable (≥50 usuarios/día)
- [ ] `/optimize` se ejecuta sin errores >95% del tiempo
- [ ] Datos de ORS frescos (no más de 4 horas de antigüedad)
- [ ] Al menos 3-5 usuarios reportan ahorro >€1 en sus búsquedas
- [ ] Ko-fi account creada y verificada

---

## 5. Checklist de lanzamiento

Antes de compartir la URL públicamente, verificar:

- [ ] **0.1** Rate limiting activo (probar con curl en bucle que devuelve 429 al exceder límite)
- [ ] **0.2** Startup check: arrancar el servidor sin `.env` y verificar que el log advierte claramente
- [ ] **0.3** Política de privacidad accesible en `/privacidad` o `/static/privacy.html`
- [ ] **0.4** Sentry configurado y recibiendo un error de prueba (`sentry_sdk.capture_message("test")`)
- [ ] **1.1** `docker compose up` funciona en un servidor limpio (sin el entorno de desarrollo)
- [ ] **1.3** GitHub Actions en verde en el último commit de `main`
- [ ] **1.2** CORS configurado si frontend y API van a estar en dominios distintos
- [ ] **2.4** Refresco automático del catálogo configurado en el servidor de producción (systemd timer o cron)
- [ ] `.env` real **no** está en el repositorio (verificar con `git log --all --full-history -- .env`)
- [ ] La clave `ORS_API_KEY` tiene restricciones de dominio en el panel de OpenRouteService (evitar uso no autorizado si la clave se filtra)
- [ ] El servidor escucha en `0.0.0.0:80` detrás de un reverse proxy (nginx o Caddy), no directamente expuesto en el puerto de Uvicorn
- [ ] El endpoint `/catalog/refresh` está protegido (solo accesible desde la propia máquina o con token)

---

## 6. Notas de arquitectura para el futuro

Estas no son tareas inmediatas pero son decisiones de diseño a tener en cuenta si la app crece:

**Caché de resultados ORS (CRÍTICO para escalar):** Este es el punto de mayor retorno para escalar sin aumentar coste de ORS. Si muchos usuarios buscan las mismas rutas frecuentes (Madrid - Valencia, Barcelona - Madrid, etc.), las matrices ORS se pueden cachear en memoria con `@functools.lru_cache(maxsize=500)` con TTL de 1-2 horas. 

Implementación estimada: 20-30 líneas en `app/optimizer/ranking.py`, dentro de `ORSRouteProvider._matrix()`. Un caché bien dimensionado puede reducir peticiones ORS 60-70% en producción (usuarios hacen búsquedas muy similares: mismo origen, mismo destino, solo varían combustible o marcas).

Con el ORS free tier (2.000 req/día), sin caché: ~500 optimizaciones. Con caché: ~1.500-2.000. Esto estira el MVP varios meses antes de necesitar pagar ORS.

**Cuándo implementar:** Post-lanzamiento (semana 2-3), cuando Analytics muestre qué rutas se repiten más. Prioridad: ALTA si el tráfico crece rápido.

**Leaflet desde CDN vs. local:** actualmente Leaflet se carga desde `unpkg.com`. Si el CDN cae, el mapa no carga. Para una app de producción robusta conviene copiar `leaflet.css` y `leaflet.js` a `static/vendor/` y servir desde el propio servidor. Cambio de 10 minutos que elimina una dependencia externa crítica.

**SQLite vs. PostgreSQL:** para el volumen actual (12.000 estaciones, 37.000 precios, consultas de lectura) SQLite con WAL es más que suficiente y elimina la necesidad de gestionar un servidor de base de datos. Solo tendría sentido migrar si se añaden escrituras concurrentes (cuentas de usuario, historial de búsquedas) o si el volumen de datos crece varios órdenes de magnitud.

**Endpoint `/catalog/refresh` en producción:** ahora mismo cualquiera que conozca la URL puede disparar un refresco. Antes del lanzamiento hay que protegerlo con un token simple (`Authorization: Bearer <TOKEN>`) o restringirlo a localhost para que solo el cron del servidor pueda llamarlo.
