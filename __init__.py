"""OpenEnergy integration.

This integration will orchestrate:
- OAuth login to OpenEnergy/Keycloak (later)
- Supervisor add-on bootstrap (repo/add/install/options/start)
- Patching Home Assistant configuration.yaml for reverse proxy trust
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, LOGGER, FRPC_ADDON_SLUG
from .coordinator import OpenEnergyDataUpdateCoordinator
from .patcher import patch_configuration
from homeassistant.components import hassio

OPENENERGY_ADDON_REPO = "https://github.com/XBoschPro/openenergy-ha-addons"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenEnergy from a config entry."""
    coordinator = OpenEnergyDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    if hassio.is_hassio(hass):
        await async_bootstrap_frpc_addon(hass, coordinator.data)

    if patch_configuration(hass):
        LOGGER.warning("configuration.yaml patched, please restart Home Assistant")
        hass.components.persistent_notification.async_create(
            "OpenEnergy integration requires a restart of Home Assistant to apply changes to `configuration.yaml`.",
            title="Restart required",
            notification_id="openenergy_restart_required",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_bootstrap_frpc_addon(hass, frp_config):
    """Bootstrap the openenergy_frpc add-on."""
    supervisor_info = await hassio.async_get_supervisor_info(hass)
    if OPENENERGY_ADDON_REPO not in [
        repo["url"] for repo in supervisor_info["addons_repositories"]
    ]:
        LOGGER.info("Adding OpenEnergy add-on repository")
        await hassio.async_add_addon_repository(hass, OPENENERGY_ADDON_REPO)

    if not await hassio.async_is_addon_installed(hass, FRPC_ADDON_SLUG):
        LOGGER.info(f"Installing {FRPC_ADDON_SLUG} add-on")
        await hassio.async_install_addon(hass, FRPC_ADDON_SLUG)
    
    await async_update_frpc_addon_config(hass, frp_config)

async def async_update_frpc_addon_config(hass, frp_config):
    """Update and start the openenergy_frpc add-on."""
    if not frp_config:
        LOGGER.error("FRP config not available, cannot configure add-on")
        return

    try:
        addon_info = await hassio.async_get_addon_info(hass, FRPC_ADDON_SLUG)
    except hassio.HassioAPIError:
        LOGGER.error(f"Could not get {FRPC_ADDON_SLUG} add-on info. Is the add-on installed?")
        return

    addon_options = addon_info.get("options", {})
    new_options = {
        "server_addr": frp_config.get("server_addr"),
        "server_port": frp_config.get("server_port"),
        "tunnels": [
            {
                "name": frp_config.get("tunnel_name"),
                "type": "http",
                "local_port": 8123,
                "custom_domains": [frp_config.get("tunnel_name")],
            }
        ],
        "token": frp_config.get("frp_token"),
    }

    if addon_options != new_options:
        LOGGER.info("Updating frpc addon configuration")
        await hassio.async_set_addon_options(hass, FRPC_ADDON_SLUG, new_options)
        
    if addon_info.get("state") != "started":
        LOGGER.info("Starting frpc addon")
        await hassio.async_start_addon(hass, FRPC_ADDON_SLUG)



async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload OpenEnergy config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok

