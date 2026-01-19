"""Keycloak Device Authorization Grant helpers.

This module derives endpoints from the realm issuer URL and implements:
- Device authorization request
- Token polling
- UserInfo retrieval

All operations are async and use Home Assistant's shared aiohttp session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client


@dataclass(frozen=True, slots=True)
class OidcEndpoints:
    """OIDC endpoints derived from issuer."""
    device_authorization_url: str
    token_url: str
    userinfo_url: str


@dataclass(frozen=True, slots=True)
class DeviceCodeResponse:
    """Device authorization response (RFC 8628)."""
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_in: int
    interval: int


@dataclass(frozen=True, slots=True)
class TokenSuccess:
    """Token endpoint success response subset."""
    access_token: str
    token_type: str
    expires_in: int


def derive_endpoints_from_issuer(issuer_url: str) -> OidcEndpoints:
    """Derive Keycloak OIDC endpoints from issuer URL.

    Keycloak realm issuer example:
      https://auth1.openenergy.be/realms/portalOpenenergy

    Derived:
      /protocol/openid-connect/auth/device
      /protocol/openid-connect/token
      /protocol/openid-connect/userinfo
    """
    base = issuer_url.rstrip("/")
    return OidcEndpoints(
        device_authorization_url=f"{base}/protocol/openid-connect/auth/device",
        token_url=f"{base}/protocol/openid-connect/token",
        userinfo_url=f"{base}/protocol/openid-connect/userinfo",
    )


async def request_device_code(
    hass: HomeAssistant,
    issuer_url: str,
    client_id: str,
    scope: str,
) -> DeviceCodeResponse:
    """Request a device_code/user_code from Keycloak.

    Raises:
        RuntimeError: When Keycloak returns an error response (no device_code).
    """
    ep = derive_endpoints_from_issuer(issuer_url)
    session = aiohttp_client.async_get_clientsession(hass)

    payload = {
        "client_id": client_id,
        "scope": scope,
    }

    async with session.post(ep.device_authorization_url, data=payload, timeout=20) as resp:
        status = resp.status
        text = await resp.text()

    # Try JSON decode, but keep raw text if not JSON.
    data: dict[str, Any] = {}
    try:
        import json  # local import to keep module light
        data = json.loads(text) if text else {}
    except Exception:  # noqa: BLE001
        data = {}

    # Keycloak error responses typically include "error" / "error_description"
    if status >= 400 or "device_code" not in data:
        err = str(data.get("error", "unknown_error"))
        desc = str(data.get("error_description", text[:300]))
        raise RuntimeError(f"Keycloak device authorization failed (HTTP {status}): {err} - {desc}")

    return DeviceCodeResponse(
        device_code=str(data["device_code"]),
        user_code=str(data["user_code"]),
        verification_uri=str(data["verification_uri"]),
        verification_uri_complete=data.get("verification_uri_complete"),
        expires_in=int(data.get("expires_in", 600)),
        interval=int(data.get("interval", 5)),
    )



async def poll_token_once(
    hass: HomeAssistant,
    issuer_url: str,
    client_id: str,
    device_code: str,
) -> TokenSuccess | str:
    """Poll token endpoint once.

    Returns:
      - TokenSuccess on success
      - error string on non-success (e.g., 'authorization_pending', 'slow_down', 'expired_token')
    """
    ep = derive_endpoints_from_issuer(issuer_url)
    session = aiohttp_client.async_get_clientsession(hass)

    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id,
        "device_code": device_code,
    }

    async with session.post(ep.token_url, data=payload, timeout=20) as resp:
        data = await resp.json()

    # Success response contains access_token/token_type/expires_in.
    if "access_token" in data:
        return TokenSuccess(
            access_token=str(data["access_token"]),
            token_type=str(data.get("token_type", "Bearer")),
            expires_in=int(data.get("expires_in", 300)),
        )

    # Error response: {"error": "...", "error_description": "..."}
    return str(data.get("error", "unknown_error"))


async def fetch_userinfo(
    hass: HomeAssistant,
    issuer_url: str,
    access_token: str,
) -> dict[str, Any]:
    """Fetch userinfo from Keycloak and return a stable subset."""
    ep = derive_endpoints_from_issuer(issuer_url)
    session = aiohttp_client.async_get_clientsession(hass)

    headers = {"Authorization": f"Bearer {access_token}"}

    async with session.get(ep.userinfo_url, headers=headers, timeout=20) as resp:
        data = await resp.json()

    # Keep default claims only.
    return {
        "sub": data.get("sub"),
        "email": data.get("email"),
        "preferred_username": data.get("preferred_username"),
        "name": data.get("name"),
    }
