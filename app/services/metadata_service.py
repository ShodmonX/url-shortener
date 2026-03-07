import asyncio
import io
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
import qrcode
from bs4 import BeautifulSoup
from qrcode.image.svg import SvgPathImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Link


class UnsafeMetadataTargetError(ValueError):
    pass


def _assert_safe_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeMetadataTargetError("metadata fetch supports only http and https URLs")
    if not parsed.hostname:
        raise UnsafeMetadataTargetError("metadata fetch target must include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeMetadataTargetError("metadata fetch target must not include userinfo")


async def _resolve_public_ip_addresses(hostname: str, port: int | None) -> set[str]:
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not literal_ip.is_global:
            raise UnsafeMetadataTargetError("metadata fetch target resolves to a private or reserved IP")
        return {hostname}

    loop = asyncio.get_running_loop()
    try:
        address_infos = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeMetadataTargetError("metadata fetch target hostname could not be resolved") from exc

    ip_addresses = {address_info[4][0] for address_info in address_infos}
    if not ip_addresses:
        raise UnsafeMetadataTargetError("metadata fetch target hostname did not resolve to any IP addresses")

    for ip_address_raw in ip_addresses:
        if not ipaddress.ip_address(ip_address_raw).is_global:
            raise UnsafeMetadataTargetError("metadata fetch target resolves to a private or reserved IP")

    return ip_addresses


async def _assert_safe_request_target(url: str) -> None:
    _assert_safe_url(url)
    parsed = urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    await _resolve_public_ip_addresses(parsed.hostname or "", port)


async def fetch_url_metadata(url: str) -> dict[str, str] | None:
    headers = {"User-Agent": settings.metadata_user_agent}
    current_url = url

    async with httpx.AsyncClient(
        timeout=settings.metadata_fetch_timeout_seconds,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for _ in range(settings.metadata_max_redirects + 1):
            await _assert_safe_request_target(current_url)

            async with client.stream("GET", current_url, headers=headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise httpx.HTTPStatusError(
                            "redirect response missing location header",
                            request=response.request,
                            response=response,
                        )
                    current_url = urljoin(str(response.url), location)
                    continue

                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return None

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    remaining = settings.metadata_max_html_bytes - len(body)
                    if remaining <= 0:
                        break
                    body.extend(chunk[:remaining])
                    if len(body) >= settings.metadata_max_html_bytes:
                        break

                html = body.decode(response.encoding or "utf-8", errors="ignore")
                break
        else:
            raise UnsafeMetadataTargetError("metadata fetch exceeded redirect limit")

    soup = BeautifulSoup(html, "html.parser")

    def meta_content(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return None

    title = meta_content("og:title", "twitter:title")
    if title is None and soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = meta_content("og:description", "description", "twitter:description")
    image = meta_content("og:image", "twitter:image")
    site_name = meta_content("og:site_name")

    if image:
        image = urljoin(current_url, image)

    metadata = {
        "title": title or "",
        "description": description or "",
        "image": image or "",
        "site_name": site_name or "",
        "canonical_url": current_url,
    }
    return {key: value for key, value in metadata.items() if value}


def generate_qr_svg(short_url: str) -> str:
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(short_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


class MetadataEnrichmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def enrich_link(self, short_code: str, public_base_url: str) -> None:
        link = await self.db.scalar(select(Link).where(Link.short_code == short_code))
        if link is None:
            return

        short_url = f"{public_base_url.rstrip('/')}/{link.short_code}"
        link.qr_svg = generate_qr_svg(short_url)

        try:
            metadata = await fetch_url_metadata(link.long_url)
            link.preview_metadata = metadata
            link.metadata_status = "ready" if metadata else "empty"
        except UnsafeMetadataTargetError:
            link.preview_metadata = None
            link.metadata_status = "blocked"
        except Exception:
            link.preview_metadata = None
            link.metadata_status = "failed"

        await self.db.commit()
