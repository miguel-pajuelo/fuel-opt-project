from .runtime import *
# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def fetch_html(
    session: requests.Session,
    url: str,
    retries: int = 3,
    backoff: float = 2.0,
) -> str:
    """GET con reintentos y backoff exponencial ante errores transitorios."""
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=TIMEOUT_HTTP)
            r.raise_for_status()
            return r.text
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            if attempt == retries or (exc.response is not None and status < 500):
                raise
            logger.warning("HTTP %s en %s, reintento %d/%d", status, url, attempt, retries)
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            logger.warning("Error de red en %s: %s, reintento %d/%d", url, exc, attempt, retries)
        time.sleep(backoff ** attempt)
    # Nunca llega aquí, pero satisface el tipo checker
    raise RuntimeError("fetch_html: no debería llegar aquí")


# ---------------------------------------------------------------------------
# Parsing del índice de estaciones
# ---------------------------------------------------------------------------

def parse_station_index(html: str, base_url: str) -> List[Station]:
    soup = BeautifulSoup(html, "html.parser")
    stations: List[Station] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/gasolineras-ballenoil/" not in href:
            continue
        full = urljoin(base_url, href)
        name = a.get_text(strip=True)
        if not name:
            continue
        stations.append(Station(name=name, url=full))

    # Dedup por URL preservando el primero encontrado
    uniq: Dict[str, Station] = {}
    for s in stations:
        uniq.setdefault(s.url, s)
    return list(uniq.values())


# ---------------------------------------------------------------------------
# Parsing de la ficha de estación
# ---------------------------------------------------------------------------

def parse_station_detail(html: str) -> Dict[str, Any]:
    """
    Extrae dirección y tokens de emparejamiento de la ficha HTML.

    Correcciones respecto al original:
    - La regex de token ahora sigue el patron real:
      item["dirección"].includes("...") y variantes con comillas simples.
    - Se extraen TODOS los tokens, no solo el primero.
    - Se añade fallback para la dirección og:description o <address>.
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- dirección ---
    address = _extract_address(soup, html)

    # --- Tokens de emparejamiento ---
    tokens = _extract_match_tokens(html)

    return {"address": address, "tokens": tokens}


def _extract_address(soup: BeautifulSoup, html: str) -> Optional[str]:
    """Intenta extraer la dirección por múltiples estrategias."""

    # 1) JSON-LD (schema.org GasStation / LocalBusiness) — más fiable
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                postal = data.get("address", {})
                if isinstance(postal, dict):
                    parts = [
                        postal.get("streetAddress", ""),
                        postal.get("postalCode", ""),
                        postal.get("addressLocality", ""),
                    ]
                    combined = ", ".join(p for p in parts if p)
                    if combined:
                        return combined
        except (json.JSONDecodeError, AttributeError):
            pass

    # 2) Metaetiqueta og:description (suele contener "Calle X, CP - Localidad")
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        content = og["content"].strip()
        if re.search(r"\b\d{5}\b", content):
            return content

    # 3) Elemento <address>
    addr_tag = soup.find("address")
    if addr_tag:
        text = addr_tag.get_text(" ", strip=True)
        if text:
            return text

    # 4) Línea de texto con CP de 5 dígitos y palabra clave de calle
    for ln in (l.strip() for l in soup.get_text("\n").splitlines() if l.strip()):
        if re.search(r"\b\d{5}\b", ln) and any(k in ln for k in STREET_KEYWORDS):
            return ln

    return None


def _extract_match_tokens(html: str) -> List[str]:
    """Extrae todos los tokens de includes("...") o includes('...')."""
    tokens: List[str] = []
    seen: set[str] = set()

    for match in TOKEN_INCLUDE_RE.finditer(html):
        literal = match.group("token").strip()
        if len(literal) < 2:
            continue

        quote = literal[0]
        if literal[-1] != quote:
            continue

        value = literal[1:-1]
        if quote == "'":
            value = value.replace("\\'", "'")
        else:
            value = value.replace('\\"', '"')
        value = value.replace("\\\\", "\\").strip()

        value_norm = _norm(value)
        if (
            value
            and value_norm
            and value_norm not in GLOBAL_MATCH_TOKEN_BLOCKLIST
            and value not in seen
        ):
            seen.add(value)
            tokens.append(value)

    return tokens


__all__ = [name for name in globals() if not name.startswith('__')]

