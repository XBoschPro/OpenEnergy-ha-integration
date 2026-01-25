"""Manager for the OpenEnergy FRPC Add-on."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification

_LOGGER = logging.getLogger(__name__)

TARGET_SLUG = "local_openenergy_frpc"


def is_hassio(hass: HomeAssistant) -> bool:
    """Return true if Hass.io is loaded."""
    return "hassio" in hass.config.components


async def get_addon_info(hass: HomeAssistant) -> dict[str, Any] | None:
    """Find the installed OpenEnergy FRPC add-on and return its info."""
    if not is_hassio(hass):
        return None

    hassio_api = None
    if hasattr(hass, "components") and hasattr(hass.components, "hassio"):
         hassio_api = hass.components.hassio
    if not hassio_api:
        hassio_api = hass.data.get("hassio")

    if not hassio_api:
        _LOGGER.error("Could not locate Hassio API instance.")
        return None
    
    # We rely on send_command as confirmed by debug logs
    if hasattr(hassio_api, "send_command"):
        try:
            # Check direct slug first
            resp = await hassio_api.send_command(f"/addons/{TARGET_SLUG}/info", method="get")
            if resp and resp.get("result") == "ok":
                return resp.get("data")
        except Exception:
            pass # Fallback to search list

        try:
             # List all addons if direct access fails (e.g. unknown slug variant)
            resp = await hassio_api.send_command("/addons", method="get")
            if resp and resp.get("result") == "ok":
                addons = resp.get("data", {}).get("addons", [])
                for addon in addons:
                    slug = addon.get("slug")
                    if slug == TARGET_SLUG or "openenergy" in addon.get("name", "").lower():
                        # Fetch full info
                        info_resp = await hassio_api.send_command(f"/addons/{slug}/info", method="get")
                        if info_resp and info_resp.get("result") == "ok":
                            return info_resp.get("data")
        except Exception as err:
            _LOGGER.error("Failed to list addons via send_command: %s", err)

    _LOGGER.warning("OpenEnergy FRPC add-on not found. Checked slug: %s", TARGET_SLUG)
    return None


async def configure_frpc_addon(
    hass: HomeAssistant,
    server_addr: str,
    server_port: int,
    tls_enable: bool,
    ha_uuid: str,
    device_secret: str,
    tunnel_domain: str,
) -> bool:
    """Configure and start the OpenEnergy FRPC add-on."""
    if not is_hassio(hass):
        return False

    info = await get_addon_info(hass)
    if not info:
        return False

    slug = info["slug"]
    current_options = info.get("options", {})
    
    # Cast to ensure correct types for API
    try:
        server_port = int(server_port)
    except ValueError:
        server_port = 7000
        
    new_options = {
        "server_addr": str(server_addr),
        "server_port": server_port,
        "tls_enable": bool(tls_enable),
        "ha_uuid": str(ha_uuid),
        "device_secret": str(device_secret),
        "tunnel_domain": str(tunnel_domain),
        "local_ip": str(current_options.get("local_ip", "127.0.0.1")),
        "local_port": int(current_options.get("local_port", 8123)),
    }

    _LOGGER.info("Configuring add-on %s via Supervisor API", slug)
    
    try:
        hassio_api = None
        if hasattr(hass, "components") and hasattr(hass.components, "hassio"):
             hassio_api = hass.components.hassio
        if not hassio_api:
            hassio_api = hass.data.get("hassio")
            
        if not hassio_api or not hasattr(hassio_api, "send_command"):
            _LOGGER.error("Cannot configure add-on: send_command missing")
            return False
            
        # Set options
        resp = await hassio_api.send_command(f"/addons/{slug}/options", method="post", payload={"options": new_options})
        
        if resp.get("result") != "ok":
             _LOGGER.error("Error setting options: %s", resp)
             return False

        # Restart
        action = "restart" if info.get("state") == "started" else "start"
        await hassio_api.send_command(f"/addons/{slug}/{action}", method="post")
        
        # Notify success
        persistent_notification.async_create(
            hass, 
            f"Tunnel OpenEnergy configuré et démarré (Slug: {slug}).",
            title="OpenEnergy Succès"
        )
            
        return True

    except Exception as err:
        _LOGGER.error("Failed to configure/start add-on %s: %s", slug, err)
        return False