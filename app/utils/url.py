from urllib.parse import urlsplit, urlunsplit


def normalize_target_url(url: str) -> str:
    cleaned = url.strip()
    parts = urlsplit(cleaned)
    path = parts.path or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
