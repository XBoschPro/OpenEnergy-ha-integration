"""
Buttons:
- Refresh Bridge: fetch FRPC config (using device_token), push add-on options, restart add-on
- Reconnect: if revoked (or user wants), triggers re-auth path (implemented as config flow reauth)
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import persistent_notification

from .portal_api import PortalClient, PortalConfig
from .frp_bridge import apply_frpc_config_to_addon, FrpBridgeError
from .supervisor_api import SupervisorClient, SupervisorApiError
from .config_patch import patch_configuration_yaml, ConfigPatchError


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up button entities."""
    portal_url = entry.data["portal_url"]
    portal = PortalClient(hass, PortalConfig(portal_url=portal_url))
    addon_name_contains = entry.data.get("addon_name_contains", "OpenEnergy FRP Client")

    async_add_entities(
        [
            OpenEnergyRefreshBridgeButton(hass, entry, portal, addon_name_contains),
            OpenEnergyReconnectButton(hass, entry),
        ]
    )


class OpenEnergyRefreshBridgeButton(ButtonEntity):
    """Button that refreshes FRP bridge config and restarts the add-on."""

    _attr_has_entity_name = True
    _attr_name = "Refresh OpenEnergy Bridge"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, portal: PortalClient, addon_name_contains: str) -> None:
        """Initialize the button."""
        self._hass = hass
        self._entry = entry
        self._portal = portal
        self._addon_name_contains = addon_name_contains
        self._attr_unique_id = f"{entry.entry_id}_refresh_bridge"

    async def async_press(self) -> None:
        """Handle button press."""
        device_token = self._entry.data.get("device_token") or ""
        device_secret = self._entry.data.get("device_secret") or ""
        local_ip = self._entry.data.get("local_ip", "127.0.0.1")
        local_port = int(self._entry.data.get("local_port", 8123))

        if not device_token or not device_secret:
            persistent_notification.async_create(
                self._hass,
                "OpenEnergy: missing device_token or device_secret in config entry. Reconnect via Keycloak.",
                title="OpenEnergy",
            )
            return

        # Apply add-on options and restart FRP client
        try:
            res = await apply_frpc_config_to_addon(
                self._hass,
                portal=self._portal,
                addon_name_contains=self._addon_name_contains,
                device_token=device_token,
                stored_device_secret=device_secret,
                local_ip=local_ip,
                local_port=local_port,
            )
        except FrpBridgeError as e:
            # If portal says revoked -> user must reauth
            msg = str(e)
            persistent_notification.async_create(self._hass, f"OpenEnergy bridge refresh failed: {msg}", title="OpenEnergy")
            return

        # Patch configuration.yaml for trusted proxies (idempotent)
        try:
            changed = patch_configuration_yaml(self._hass)
            if changed:
                # Requires restart to take effect; do it automatically on supervised.
                try:
                    sup = SupervisorClient(self._hass)
                    await sup.async_restart_core()
                except SupervisorApiError:
                    persistent_notification.async_create(
                        self._hass,
                        "OpenEnergy updated configuration.yaml. Please restart Home Assistant to apply proxy settings.",
                        title="OpenEnergy",
                    )
        except ConfigPatchError as e:
            persistent_notification.async_create(self._hass, f"OpenEnergy config patch failed: {e}", title="OpenEnergy")

        persistent_notification.async_create(
            self._hass,
            f"OpenEnergy bridge updated. Tunnel domain: {res.get('tunnel_domain')}",
            title="OpenEnergy",
        )


class OpenEnergyReconnectButton(ButtonEntity):
    """Button that triggers a re-auth instruction for the user."""

    _attr_has_entity_name = True
    _attr_name = "Reconnect OpenEnergy (Keycloak)"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize reconnect button."""
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_reconnect"

    async def async_press(self) -> None:
        """Handle press: instruct user to reconfigure (reauth flow)."""
        persistent_notification.async_create(
            self._hass,
            "OpenEnergy: please reconfigure the integration to re-authenticate via Keycloak (token revoked or rotation requested).",
            title="OpenEnergy",
        )
