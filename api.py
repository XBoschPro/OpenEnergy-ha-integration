"""OpenEnergy server API client.

Aligned with OpenEnergy Server v1 (Flask).
"""

from __future__ import annotations

from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.network import get_url

from .const import (
    ENDPOINT_ENROLL,
    ENDPOINT_ROTATE_TOKEN,
    ENDPOINT_ROTATE_FRP,
    ENDPOINT_GET_FRPC,
)


class EnrollResult(TypedDict):
    """Result from enrollment."""
    ha_uuid: str
    slug: str
    tunnel_domain: str
    device_token: str
    frpc: dict[str, Any]  # contains device_secret only on initial enroll/rotate


async def get_health(hass: HomeAssistant, health_url: str) -> tuple[bool, str]:
    """Query public health endpoint."""
    session = aiohttp_client.async_get_clientsession(hass)
    try:
        async with session.get(health_url, timeout=10) as resp:
            text = await resp.text()
            ok = 200 <= resp.status < 300
            return ok, f"HTTP {resp.status} - {text[:200]}"
    except Exception as err:  # noqa: BLE001
        return False, f"error: {err}"


async def enroll_ha(
    hass: HomeAssistant,
    portal_url: str,
    kc_access_token: str,
    label: str | None = None,
    device_uid: str | None = None,
) -> EnrollResult | None:
    """Enroll this Home Assistant instance with the portal.

    Maps to POST /api/ha/enroll
    """
    session = aiohttp_client.async_get_clientsession(hass)
    url = f"{portal_url.rstrip('/')}{ENDPOINT_ENROLL}"
    headers = {"Authorization": f"Bearer {kc_access_token}"}
    
    # We do NOT send internal_url because it often resolves to a local IP (e.g. 127.0.0.1)
    # which causes the server to generate invalid slugs (e.g. 127.0.0.1.ha.domain.com).
    # We let the server fallback to UUID-based slug.
    payload: dict[str, Any] = {
        "label": label or hass.config.location_name or "Home Assistant",
        "device_uid": device_uid,
        # "ha_uuid": ... we don't send it initially
    }

    try:
        async with session.post(url, json=payload, headers=headers, timeout=30) as resp:
            if resp.status >= 400:
                return None
            data = await resp.json()
    except Exception:  # noqa: BLE001
        return None

    if not data.get("ok"):
        return None

    return {
        "ha_uuid": data["ha_uuid"],
        "slug": data["slug"],
        "tunnel_domain": data["tunnel_domain"],
        "device_token": data["device_token"],
        "frpc": data["frpc"],
    }


async def rotate_opaque_token(
    hass: HomeAssistant,
    portal_url: str,
    kc_access_token: str,
    server_ha_uuid: str,
) -> str | None:
    """Rotate the opaque device token.

    Maps to POST /api/ha/token/rotate
    Requires Keycloak token (re-auth).
    """
    session = aiohttp_client.async_get_clientsession(hass)
    url = f"{portal_url.rstrip('/')}{ENDPOINT_ROTATE_TOKEN}"
    headers = {"Authorization": f"Bearer {kc_access_token}"}
    payload = {"ha_uuid": server_ha_uuid}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
            if resp.status >= 400:
                return None
            data = await resp.json()
    except Exception:  # noqa: BLE001
        return None

    if not data.get("ok"):
        return None

    return data.get("device_token")


async def rotate_frp_secret(
    hass: HomeAssistant,
    portal_url: str,
    kc_access_token: str,
    server_ha_uuid: str,
) -> str | None:
    """Rotate the FRP device secret.

    Maps to POST /api/ha/frp/rotate
    Requires Keycloak token (re-auth).
    Returns the NEW device_secret (plaintext).
    """
    session = aiohttp_client.async_get_clientsession(hass)
    url = f"{portal_url.rstrip('/')}{ENDPOINT_ROTATE_FRP}"
    headers = {"Authorization": f"Bearer {kc_access_token}"}
    payload = {"ha_uuid": server_ha_uuid}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
            if resp.status >= 400:
                return None
            data = await resp.json()
    except Exception:  # noqa: BLE001
        return None

    if not data.get("ok"):
        return None

    return data.get("device_secret")


async def get_frpc_config(
    hass: HomeAssistant,
    portal_url: str,
    device_token: str,
) -> dict[str, Any] | None:
    """Fetch current FRPC configuration using the opaque token.

    Maps to GET /api/ha/frpc
    Does NOT return the device_secret.
    """
    session = aiohttp_client.async_get_clientsession(hass)
    url = f"{portal_url.rstrip('/')}{ENDPOINT_GET_FRPC}"
    headers = {"Authorization": f"Bearer {device_token}"}

    try:
        async with session.get(url, headers=headers, timeout=20) as resp:
            if resp.status >= 400:
                return None
            data = await resp.json()
    except Exception:  # noqa: BLE001
        return None

    if not data.get("ok"):
        return None

    return data.get("frpc")