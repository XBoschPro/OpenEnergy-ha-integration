"""
FRP bridge logic:
- calls portal API to obtain FRPC parameters
- merges with locally stored device_secret (never re-fetched)
- pushes options into the OpenEnergy FRP Client add-on via Supervisor API
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant

from .portal_api import PortalClient, PortalAuthError
from .supervisor_api import SupervisorClient, SupervisorApiError


@dataclass(frozen=True)
class AddonOptions:
    """OpenEnergy FRP Client add-on options schema."""
    server_addr: str
    server_port: int
    tls_enable: bool
    ha_uuid: str
    device_secret: str
    tunnel_domain: str
    local_ip: str
    local_port: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to the Supervisor add-on options format."""
        return {
            "server_addr": self.server_addr,
            "server_port": self.server_port,
            "tls_enable": self.tls_enable,
            "ha_uuid": self.ha_uuid,
            "device_secret": self.device_secret,
            "tunnel_domain": self.tunnel_domain,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
        }


class FrpBridgeError(Exception):
    """Raised when FRP bridge operations fail."""


async def apply_frpc_config_to_addon(
    hass: HomeAssistant,
    *,
    portal: PortalClient,
    addon_name_contains: str,
    device_token: str,
    stored_device_secret: str,
    local_ip: str,
    local_port: int,
) -> Dict[str, Any]:
    """
    Fetch FRPC config from portal and apply to the FRP Client add-on.

    Returns a dict with useful status information:
      - addon_slug
      - tunnel_domain
    """
    try:
        frpc_payload = await portal.async_get_frpc(device_token)
    except PortalAuthError as e:
        raise FrpBridgeError(f"portal_auth_failed:{e}") from e

    if not frpc_payload.get("ok"):
        raise FrpBridgeError(f"portal_error:{frpc_payload}")

    frpc = (frpc_payload.get("frpc") or {})
    ha_uuid = frpc_payload.get("ha_uuid") or frpc.get("ha_uuid")
    tunnel_domain = frpc_payload.get("tunnel_domain") or frpc.get("tunnel_domain")

    if not ha_uuid or not tunnel_domain:
        raise FrpBridgeError("portal_missing_frpc_fields")

    opts = AddonOptions(
        server_addr=str(frpc["server_addr"]),
        server_port=int(frpc["server_port"]),
        tls_enable=bool(frpc["tls_enable"]),
        ha_uuid=str(ha_uuid),
        device_secret=stored_device_secret,
        tunnel_domain=str(tunnel_domain),
        local_ip=str(local_ip),
        local_port=int(local_port),
    )

    sup = SupervisorClient(hass)
    slug = await sup.async_find_addon_slug(name_contains=addon_name_contains)
    await sup.async_set_addon_options(slug, opts.to_dict())
    await sup.async_restart_addon(slug)

    return {"addon_slug": slug, "tunnel_domain": tunnel_domain}
