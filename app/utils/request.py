from fastapi import Request


def get_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def get_country_code(request: Request) -> str | None:
    return request.headers.get("cf-ipcountry") or request.headers.get("x-country-code")
