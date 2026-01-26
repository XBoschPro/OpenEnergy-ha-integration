"""
Portal API client (async) used by the Home Assistant integration.

All calls are made with aiohttp and must be non-blocking.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from aiohttp import ClientResponseError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

@dataclass(frozen=True)
class PortalConfig:
    """Portal endpoints configuration."""
    portal_url: str  # e.g. https://portal.openenergy.be


class PortalApiError(Exception):
    """Raised when the portal API returns an unexpected error."""


class PortalAuthError(PortalApiError):
    """Raised when portal API indicates authentication failure."""


class PortalClient:
    """Async client for OpenEnergy portal API."""

    def __init__(self, hass: HomeAssistant, cfg: PortalConfig) -> None:
        """Initialize API client with a Home Assistant session."""
        self._hass = hass
        self._cfg = cfg
        self._session = async_get_clientsession(hass)

    def _url(self, path: str) -> str:
        """Build absolute URL for the portal API."""
        return f"{self._cfg.portal_url.rstrip('/')}{path}"

    async def async_health(self) -> Dict[str, Any]:
        """Fetch portal health status."""
        url = self._url("/api/health")
        async with self._session.get(url, timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def async_enroll(
        self,
        kc_access_token: str,
        *,
        ha_uuid: Optional[str],
        device_uid: str,
        device_mac: Optional[str],
        label: Optional[str],
    ) -> Dict[str, Any]:
        """Enroll/re-attach a Home Assistant on the portal (KC auth)."""
        url = self._url("/api/ha/enroll")
        payload: Dict[str, Any] = {
            "device_uid": device_uid,
            "device_mac": device_mac,
            "label": label,
        }
        if ha_uuid:
            payload["ha_uuid"] = ha_uuid

        headers = {"Authorization": f"Bearer {kc_access_token}"}

        async with self._session.post(url, json=payload, headers=headers, timeout=20) as resp:
            if resp.status in (401, 403):
                raise PortalAuthError(f"Enroll rejected (HTTP {resp.status})")
            resp.raise_for_status()
            return await resp.json()

    async def async_get_frpc(self, device_token: str) -> Dict[str, Any]:
        """Get FRPC config from portal using opaque device token."""
        url = self._url("/api/ha/frpc")
        headers = {"Authorization": f"Bearer {device_token}"}
        async with self._session.get(url, headers=headers, timeout=20) as resp:
            if resp.status in (401, 403):
                data = await resp.json()
                raise PortalAuthError(data.get("error", "auth_failed"))
            resp.raise_for_status()
            return await resp.json()

    async def async_rotate_device_token(self, kc_access_token: str, ha_uuid: str) -> Dict[str, Any]:
        """Rotate opaque device token (KC auth)."""
        url = self._url("/api/ha/token/rotate")
        headers = {"Authorization": f"Bearer {kc_access_token}"}
        async with self._session.post(url, json={"ha_uuid": ha_uuid}, headers=headers, timeout=20) as resp:
            if resp.status in (401, 403):
                raise PortalAuthError(f"Rotate rejected (HTTP {resp.status})")
            resp.raise_for_status()
            return await resp.json()
