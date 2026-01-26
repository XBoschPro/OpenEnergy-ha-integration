"""OpenEnergy integration.

Current scope:
- Device Authorization Grant (Keycloak)
- Exchange Keycloak access token -> OpenEnergy opaque token (server-side)
- Options menu (status, reconnect, rotate token, disconnect, advanced info)

Later:
- Supervisor add-on bootstrap
- Patch configuration.yaml
- FRP provisioning
"""

# from __future__ import annotations
import logging
from typing import Any
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_PORTAL_URL,
    DATA_OE_TOKEN,
    DATA_HA_UUID,
    DATA_FRP_DEVICE_SECRET,
)
from .frp_bridge import apply_frpc_config_to_addon, FrpBridgeError
from .portal_api import PortalClient, PortalConfig
from .config_patch import patch_configuration_yaml, ConfigPatchError
from .supervisor_api import SupervisorClient, SupervisorApiError

_LOGGER = logging.getLogger(__name__)

DEFAULT_ADDON_NAME_CONTAINS = "OpenEnergy FRP Client"
DEFAULT_LOCAL_IP = "127.0.0.1"
DEFAULT_LOCAL_PORT = 8123


async def _restart_core_later(hass: HomeAssistant) -> None:
    """Restart HA Core via Supervisor.

    This coroutine may be cancelled during shutdown/restart; cancellation is expected.
    """
    try:
        sup = SupervisorClient(hass)
        await sup.async_restart_core()
    except asyncio.CancelledError:
        # Expected when the restart cancels in-flight tasks.
        return
    except SupervisorApiError as err:
        _LOGGER.error("Cannot restart core automatically (Supervisor unavailable): %s", err)
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("Unexpected error while restarting core: %s", err)


def _schedule_core_restart(hass: HomeAssistant, delay_s: float = 60.0) -> None:
    """Schedule a core restart in a thread-safe way.

    This is safe even if called from an executor thread.
    """
    # Restart only once per HA run.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("restart_scheduled"):
        return
    domain_data["restart_scheduled"] = True
    
    def _cancel_on_stop(_event) -> None:
        task = domain_data.pop("restart_task", None)
        if task and not task.done():
            task.cancel()

    def _schedule_on_loop() -> None:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _cancel_on_stop)
        def _cb() -> None:
            # Thread-safe: HA will run the coroutine on its event loop.
            hass.add_job(_restart_core_later(hass))

        hass.loop.call_later(delay_s, _cb)

    # Ensures scheduling happens on the loop thread.
    hass.loop.call_soon_threadsafe(_schedule_on_loop)


async def _maybe_patch_configuration_yaml(hass: HomeAssistant) -> None:
    """Patch configuration.yaml to enable X-Forwarded-For and trusted proxies for OpenEnergy."""
    try:
        changed = await hass.async_add_executor_job(patch_configuration_yaml, hass)
    except ConfigPatchError as err:
        _LOGGER.error("configuration.yaml patch failed: %s", err)
        return
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("Unexpected error while patching configuration.yaml: %s", err)
        return

    if not changed:
        _LOGGER.info("configuration.yaml already patched (no changes).")
        return

    if changed:
        _LOGGER.warning("configuration.yaml patched; scheduling Home Assistant core restart.")
        _schedule_core_restart(hass, delay_s=3.0)
    



async def _maybe_push_frpc_to_addon(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Push FRPC options into the Supervisor add-on if we have enough data.

    This is the ONLY path that updates the add-on options (server_addr, tunnel_domain, etc.).
    """
    data = entry.data or {}
    opts = entry.options or {}

    portal_url = data.get(CONF_PORTAL_URL)
    device_token = data.get(DATA_OE_TOKEN)
    ha_uuid = data.get(DATA_HA_UUID)
    device_secret = data.get(DATA_FRP_DEVICE_SECRET)

    # If these are missing, we cannot configure the add-on.
    if not portal_url or not device_token or not ha_uuid:
        _LOGGER.info(
            "Skipping add-on configuration: missing portal_url/device_token/ha_uuid "
            "(portal_url=%s, has_token=%s, ha_uuid=%s)",
            bool(portal_url),
            bool(device_token),
            bool(ha_uuid),
        )
        return

    # device_secret is returned only once (first enroll). If missing, you can't build frpc.toml safely.
    if not device_secret:
        _LOGGER.error(
            "Cannot configure add-on: FRP device_secret is missing in config entry data. "
            "You likely enrolled without receiving it, or you need a fresh enroll/rotation."
        )
        return

    addon_name_contains = str(opts.get("addon_name_contains", DEFAULT_ADDON_NAME_CONTAINS))
    local_ip = str(opts.get("local_ip", DEFAULT_LOCAL_IP))
    local_port = int(opts.get("local_port", DEFAULT_LOCAL_PORT))

    portal = PortalClient(hass, PortalConfig(portal_url=str(portal_url)))

    try:
        result = await apply_frpc_config_to_addon(
            hass,
            portal=portal,
            addon_name_contains=addon_name_contains,
            device_token=str(device_token),
            stored_device_secret=str(device_secret),
            local_ip=local_ip,
            local_port=local_port,
        )
        _LOGGER.info("Configured add-on '%s' with tunnel '%s'", result["addon_slug"], result["tunnel_domain"])
    except (SupervisorApiError, FrpBridgeError) as err:
        _LOGGER.error("Failed to apply FRPC config to add-on: %s", err)
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("Unexpected error while configuring add-on: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenEnergy from a config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    # Patch configuration.yaml on first setup.
    await _maybe_patch_configuration_yaml(hass)

    # Push config into add-on on startup/reload.
    await _maybe_push_frpc_to_addon(hass, entry)

    # Forward platforms (sensor/button)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Re-apply if options change (local_ip/local_port/addon match).
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    await _maybe_push_frpc_to_addon(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload OpenEnergy config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok

