"""Frozen environment: the doctor's web lookup (Exa search restricted to trusted medical references)."""

from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import urlparse

EXA_URL = "https://api.exa.ai/search"
TIMEOUT_S = 20
ALLOWED_DOMAINS = [
    "ncbi.nlm.nih.gov", "statpearls.com", "merckmanuals.com", "medlineplus.gov", "mayoclinic.org", "nice.org.uk",
    "who.int", "cochranelibrary.com", "aafp.org", "emedicine.medscape.com", "cdc.gov", "nhs.uk",
]


def allowed_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def exa_search(query: str, n: int = 5) -> list[dict]:
    """Blocking; returns [{title, url, text}]. Errors come back as one "lookup failed" result."""
    body = {
        "query": query,
        "numResults": n,
        "type": "auto",
        "includeDomains": ALLOWED_DOMAINS,
        "contents": {"highlights": {"maxCharacters": 600, "numSentences": 4}},
    }
    req = urllib.request.Request(
        EXA_URL,
        data=json.dumps(body).encode(),
        headers={"x-api-key": os.environ["EXA_API_KEY"], "content-type": "application/json", "user-agent": "rsi-doc"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            results = json.load(resp).get("results") or []
    except (OSError, ValueError) as e:  # URLError/HTTPError/timeouts are OSErrors; bad JSON is a ValueError
        return [{"title": "lookup failed", "url": "", "text": str(e)}]
    return [
        {"title": r.get("title") or "", "url": r.get("url") or "", "text": " ".join(r.get("highlights") or [])}
        for r in results
    ]
