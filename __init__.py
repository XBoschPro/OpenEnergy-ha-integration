"""OpenEnergy integration.

Current scope:
- Device Authorization Grant (Keycloak)
- Exchange Keycloak access token -> OpenEnergy opaque token (server-side)
- Options menu (status, reconnect, rotate token, disconnect, advanced info)
- Observability sensors (connectivity, latency)
- Supervisor add-on orchestration

Later:
- Patch configuration.yaml
- FRP provisioning
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN, 
    PLATFORMS, 
    DATA_FRP_SECRET, 
    DATA_SERVER_UUID, 
    DATA_TUNNEL_DOMAIN,
    DATA_FRP_SERVER_ADDR,
    DATA_FRP_SERVER_PORT,
    DATA_FRP_TLS_ENABLE
)
from .coordinator import OpenEnergyCoordinator
from .helpers import verify_http_config, check_addon_installed
from .addon import configure_frpc_addon
from .config_patch import patch_configuration_yaml

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenEnergy from a config entry."""
    # Patch configuration.yaml for trusted_proxies
    try:
        if await hass.async_add_executor_job(patch_configuration_yaml, hass):
            _LOGGER.info("configuration.yaml was patched for trusted_proxies.")
            from homeassistant.components import persistent_notification
            persistent_notification.async_create(
                hass,
                "L'intégration OpenEnergy a mis à jour votre fichier configuration.yaml pour autoriser l'accès distant.\n\n**Vous devez redémarrer Home Assistant** pour que ces changements soient pris en compte.",
                title="Configuration mise à jour",
                notification_id="openenergy_patch_restart"
            )
    except Exception as err:
        _LOGGER.error("Failed to patch configuration.yaml: %s", err)

    coordinator = OpenEnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "title": entry.title,
        "data": dict(entry.data),
        "options": dict(entry.options),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Run health checks / UX helpers
    _LOGGER.info("Scheduling health checks for OpenEnergy integration.")
    hass.async_create_task(check_addon_installed(hass))
    
    # Ensure Add-on is configured (Sync on startup)
    data = entry.data
    
    # DEBUG: Log keys to see what is missing
    _LOGGER.error("DEBUG_INIT_DATA_KEYS: %s", list(data.keys()))

    if DATA_FRP_SECRET in data and DATA_SERVER_UUID in data:
        _LOGGER.info("Syncing OpenEnergy FRPC Add-on configuration...")
        hass.async_create_task(
            configure_frpc_addon(
                hass,
                server_addr=data.get(DATA_FRP_SERVER_ADDR, ""),
                server_port=data.get(DATA_FRP_SERVER_PORT, 7000),
                tls_enable=data.get(DATA_FRP_TLS_ENABLE, True),
                ha_uuid=data[DATA_SERVER_UUID],
                device_secret=data[DATA_FRP_SECRET],
                tunnel_domain=data.get(DATA_TUNNEL_DOMAIN, "")
            )
        )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload OpenEnergy config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
