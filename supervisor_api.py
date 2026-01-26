"""
Supervisor API helper for:
- locating the OpenEnergy FRP Client add-on
- updating add-on options
- restarting the add-on
- restarting HA core (after patching configuration.yaml)

This works only on supervised/OS installs where SUPERVISOR_TOKEN is present.
"""

import os
from typing import Any, Dict, Optional

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class SupervisorApiError(Exception):
    """Raised for Supervisor API errors."""


class SupervisorClient:
    """Minimal Supervisor API client."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize supervisor client."""
        self._hass = hass
        self._session = async_get_clientsession(hass)
        self._token = os.getenv("SUPERVISOR_TOKEN") or ""
        self._base = "http://supervisor"

        if not self._token:
            raise SupervisorApiError("SUPERVISOR_TOKEN missing (not supervised/OS?)")

    def _headers(self) -> Dict[str, str]:
        """Return auth headers for Supervisor API."""
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 20,
    ) -> Dict[str, Any]:
        """Perform a Supervisor API request and return parsed JSON.

        Raises:
            SupervisorApiError: on non-2xx responses or transport errors.
        """
        url = f"{self._base}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                json=json_data,
                timeout=timeout,
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise SupervisorApiError(f"{method} {path} failed: HTTP {resp.status} - {text[:400]}")
                # Some endpoints return JSON, some return empty body.
                try:
                    return await resp.json()
                except Exception:
                    return {}
        except ClientError as err:
            raise SupervisorApiError(f"{method} {path} failed: {err}") from err

    async def async_get_addons(self) -> Dict[str, Any]:
        """List installed add-ons."""
        return await self._request_json("GET", "/addons")

    async def async_find_addon_slug(self, *, name_contains: str) -> str:
        """Find add-on slug by fuzzy name match."""
        data = await self.async_get_addons()
        addons = (data.get("data") or {}).get("addons") or []
        needle = name_contains.lower()

        for addon in addons:
            name = (addon.get("name") or "").lower()
            slug = addon.get("slug") or ""
            if needle in name and slug:
                return slug

        raise SupervisorApiError(f"Add-on not found (name_contains={name_contains})")

    async def async_set_addon_options(self, slug: str, options: Dict[str, Any]) -> None:
        """Set add-on options."""
        await self._request_json("POST", f"/addons/{slug}/options", json_data={"options": options})

    async def async_restart_addon(self, slug: str) -> None:
        """Restart an add-on."""
        await self._request_json("POST", f"/addons/{slug}/restart", json_data={})

    async def async_get_addon_info(self, slug: str) -> Dict[str, Any]:
        """Get add-on info (status)."""
        return await self._request_json("GET", f"/addons/{slug}/info")

    async def async_restart_core(self) -> None:
        """Restart Home Assistant Core."""
        # No JSON body required.
        await self._request_json("POST", "/core/restart", json_data=None, timeout=30)
