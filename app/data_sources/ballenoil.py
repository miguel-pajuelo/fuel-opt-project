from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from app.data_sources.minetur import normalize_key


GLOBAL_MATCH_TOKEN_BLOCKLIST = {
    "CASTILLOALTO",
    "ALZIRA",
}

TOKEN_INCLUDE_RE = re.compile(
    r"""
    item
    \s*\[\s*(['"])direcci[oó]n\1\s*\]
    \s*\.\s*includes\s*\(\s*
    (?P<token>
      "(?:\\.|[^"\\])*"
      |
      '(?:\\.|[^'\\])*'
    )
    \s*\)
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


def extract_match_tokens(html: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in TOKEN_INCLUDE_RE.finditer(html):
        literal = match.group("token").strip()
        if len(literal) < 2:
            continue
        quote = literal[0]
        if literal[-1] != quote:
            continue
        value = literal[1:-1]
        value = value.replace("\\'", "'") if quote == "'" else value.replace('\\"', '"')
        value = value.replace("\\\\", "\\").strip()
        value_norm = normalize_key(value)
        if value and value_norm and value_norm not in GLOBAL_MATCH_TOKEN_BLOCKLIST and value not in seen:
            seen.add(value)
            tokens.append(value)
    return tokens


def extract_address(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, AttributeError):
            continue
        if not isinstance(data, dict):
            continue
        postal = data.get("address", {})
        if not isinstance(postal, dict):
            continue
        parts = [postal.get("streetAddress", ""), postal.get("postalCode", ""), postal.get("addressLocality", "")]
        combined = ", ".join(str(part).strip() for part in parts if str(part).strip())
        if combined:
            return combined

    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        content = str(og["content"]).strip()
        if re.search(r"\b\d{5}\b", content):
            return content

    address_tag = soup.find("address")
    if address_tag:
        text = address_tag.get_text(" ", strip=True)
        if text:
            return text
    return None


def parse_station_detail(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "address": extract_address(soup),
        "tokens": extract_match_tokens(html),
    }
