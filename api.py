"""OpenEnergy server API client.
- health check (public)
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client


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


# async def exchange_token(
#     hass: HomeAssistant,
#     portal_url: str,
#     kc_access_token: str,
#     ha_uuid: str,
#     ha_name: str,
#     ha_version: str,
# ) -> str | None:
#     """Exchange Keycloak access token for an OpenEnergy opaque token.

#     Expected server endpoint (to implement later):
#       POST {portal_url}/api/ha/auth/exchange
#       Authorization: Bearer <kc_access_token>
#       JSON body: {ha_uuid, ha_name, ha_version}
#       Response JSON: {"openenergy_token": "<opaque>"}
#     """
#     session = aiohttp_client.async_get_clientsession(hass)
#     url = f"{portal_url.rstrip('/')}/api/ha/auth/exchange"
#     headers = {"Authorization": f"Bearer {kc_access_token}"}
#     payload: dict[str, Any] = {
#         "ha_uuid": ha_uuid,
#         "ha_name": ha_name,
#         "ha_version": ha_version,
#     }

#     try:
#         async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
#             if resp.status >= 400:
#                 return None
#             data = await resp.json()
#     except Exception:  # noqa: BLE001
#         return None

#     token = data.get("openenergy_token") or data.get("token")
#     return token if isinstance(token, str) and token else None


# async def rotate_token(hass: HomeAssistant, portal_url: str, oe_token: str) -> str | None:
#     """Rotate OpenEnergy token server-side.

#     Expected server endpoint (to implement later):
#       POST {portal_url}/api/ha/auth/rotate
#       Authorization: Bearer <oe_token>
#       Response JSON: {"openenergy_token": "<new opaque>"}
#     """
#     session = aiohttp_client.async_get_clientsession(hass)
#     url = f"{portal_url.rstrip('/')}/api/ha/auth/rotate"
#     headers = {"Authorization": f"Bearer {oe_token}"}

#     try:
#         async with session.post(url, headers=headers, timeout=20) as resp:
#             if resp.status >= 400:
#                 return None
#             data = await resp.json()
#     except Exception:  # noqa: BLE001
#         return None

#     token = data.get("openenergy_token") or data.get("token")
#     return token if isinstance(token, str) and token else None
