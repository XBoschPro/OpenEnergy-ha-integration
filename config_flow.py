"""Config flow for OpenEnergy using Keycloak Device Authorization Grant.

Flow overview:
1) User enters issuer/client_id/portal_url (and optional health url).
2) Integration requests device_code + user_code from Keycloak.
3) Integration displays a code + verification URL.
4) User authenticates on Keycloak website and enters the code.
5) User clicks "Continue" in HA; we poll token endpoint once per click.
6) On token success, we fetch userinfo (sub/email).
7) We call OpenEnergy enroll endpoint to obtain credentials.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import instance_id

from .addon import configure_frpc_addon
from .api import enroll_ha, get_health, rotate_opaque_token, rotate_frp_secret
from .const import (
    CONF_CLIENT_ID,
    CONF_HEALTH_URL,
    CONF_ISSUER_URL,
    CONF_PORTAL_URL,
    DATA_KC_USER,
    DATA_OE_TOKEN,
    DATA_SERVER_UUID,
    DATA_FRP_SECRET,
    DATA_FRP_SERVER_ADDR,
    DATA_FRP_SERVER_PORT,
    DATA_FRP_TLS_ENABLE,
    DATA_TUNNEL_DOMAIN,
    DATA_PROVISIONING_STATE,
    DEFAULT_CLIENT_ID,
    DEFAULT_HEALTH_URL,
    DEFAULT_ISSUER_URL,
    DEFAULT_PORTAL_URL,
    DOMAIN,
    SCOPE_BASE,
)
from .device_auth import DeviceCodeResponse, fetch_userinfo, poll_token_once, request_device_code

_LOGGER = logging.getLogger(__name__)


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ISSUER_URL, default=DEFAULT_ISSUER_URL): str,
        vol.Required(CONF_CLIENT_ID, default=DEFAULT_CLIENT_ID): str,
        vol.Required(CONF_PORTAL_URL, default=DEFAULT_PORTAL_URL): str,
        vol.Required(CONF_HEALTH_URL, default=DEFAULT_HEALTH_URL): str,
    }
)


class OpenEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenEnergy."""

    VERSION = 1
    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize flow state."""
        self._issuer_url: str | None = None
        self._client_id: str | None = None
        self._portal_url: str | None = None
        self._health_url: str | None = None

        self._device: DeviceCodeResponse | None = None
        self._last_token_error: str | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return the logger used by this config flow."""
        return _LOGGER

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Initial step where server endpoints are configured."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        self._issuer_url = user_input[CONF_ISSUER_URL].rstrip("/")
        self._client_id = user_input[CONF_CLIENT_ID]
        self._portal_url = user_input[CONF_PORTAL_URL].rstrip("/")
        self._health_url = user_input[CONF_HEALTH_URL].rstrip("/")

        # Unique ID based on portal + issuer to allow multiple setups if really needed,
        # but usually one per HA instance.
        await self.async_set_unique_id(f"openenergy::{self._portal_url}")
        self._abort_if_unique_id_configured()

        # Request device code now and proceed to device step.
        try:
            self._device = await request_device_code(
                hass=self.hass,
                issuer_url=self._issuer_url,
                client_id=self._client_id,
                scope=SCOPE_BASE,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Device authorization request failed: %s", err)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_SCHEMA,
                errors={"base": "device_auth_failed"},
            )
        self._last_token_error = None
        return await self.async_step_device()

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Display user_code and verification URI, then poll token endpoint on submit."""
        if self._device is None or self._issuer_url is None or self._client_id is None:
            return self.async_abort(reason="missing_device_state")

        placeholders = {
            "user_code": self._device.user_code,
            "verification_uri": self._device.verification_uri,
            "verification_uri_complete": self._device.verification_uri_complete or "",
            "last_error": self._last_token_error or "",
        }

        if user_input is None:
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema({}),
                description_placeholders=placeholders,
            )

        # Poll once per click.
        token_result = await poll_token_once(
            hass=self.hass,
            issuer_url=self._issuer_url,
            client_id=self._client_id,
            device_code=self._device.device_code,
        )

        if isinstance(token_result, str):
            # Not ready yet or some transient error.
            self._last_token_error = token_result
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema({}),
                description_placeholders=placeholders | {"last_error": token_result},
            )

        # Success: fetch userinfo + enroll.
        access_token = token_result.access_token
        kc_user = await fetch_userinfo(self.hass, self._issuer_url, access_token)

        # Get stable ID for this HA instance
        device_uid = await instance_id.async_get(self.hass)
        label = self.hass.config.location_name

        enroll_result = await enroll_ha(
            hass=self.hass,
            portal_url=self._portal_url,
            kc_access_token=access_token,
            label=label,
            device_uid=device_uid,
        )

        entry_data: dict[str, Any] = {
            CONF_ISSUER_URL: self._issuer_url,
            CONF_CLIENT_ID: self._client_id,
            CONF_PORTAL_URL: self._portal_url,
            CONF_HEALTH_URL: self._health_url,
            DATA_KC_USER: kc_user,
        }

        if enroll_result:
            entry_data[DATA_OE_TOKEN] = enroll_result["device_token"]
            entry_data[DATA_SERVER_UUID] = enroll_result["ha_uuid"]
            entry_data[DATA_TUNNEL_DOMAIN] = enroll_result["tunnel_domain"]
            
            # frpc dict contains server details and device_secret ONLY on enroll
            frpc_config = enroll_result.get("frpc", {})
            entry_data[DATA_FRP_SERVER_ADDR] = frpc_config.get("server_addr", "")
            entry_data[DATA_FRP_SERVER_PORT] = frpc_config.get("server_port", 7000)
            entry_data[DATA_FRP_TLS_ENABLE] = frpc_config.get("tls_enable", True)

            secret = frpc_config.get("device_secret")
            if not secret and enroll_result.get("ha_uuid"):
                # Auto-Repair: We re-enrolled but server kept old secret (not returned).
                # We must rotate it now to regain control because we have a valid KC token.
                _LOGGER.warning("Device secret missing from enroll (re-install detected). Rotating FRP secret...")
                try:
                    new_secret = await rotate_frp_secret(
                        self.hass, 
                        self._portal_url, 
                        access_token, 
                        enroll_result["ha_uuid"]
                    )
                    if new_secret:
                        secret = new_secret
                        _LOGGER.info("FRP secret successfully rotated and recovered.")
                except Exception as err:
                    _LOGGER.error("Failed to auto-rotate FRP secret: %s", err)

            if secret:
                entry_data[DATA_FRP_SECRET] = secret
                
                # Configure Add-on immediately
                await configure_frpc_addon(
                    hass=self.hass,
                    server_addr=entry_data[DATA_FRP_SERVER_ADDR],
                    server_port=entry_data[DATA_FRP_SERVER_PORT],
                    tls_enable=entry_data[DATA_FRP_TLS_ENABLE],
                    ha_uuid=enroll_result["ha_uuid"],
                    device_secret=secret,
                    tunnel_domain=enroll_result["tunnel_domain"],
                )
            
            entry_data[DATA_PROVISIONING_STATE] = "ok"
        else:
            entry_data[DATA_PROVISIONING_STATE] = "exchange_failed"

        return self.async_create_entry(title="OpenEnergy", data=entry_data)

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Reauth uses the same device flow path."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_entry_not_found")

        self._issuer_url = entry.data[CONF_ISSUER_URL]
        self._client_id = entry.data[CONF_CLIENT_ID]
        self._portal_url = entry.data[CONF_PORTAL_URL]
        self._health_url = entry.data.get(CONF_HEALTH_URL, DEFAULT_HEALTH_URL)

        # Always request a new device code for reauth.
        self._device = await request_device_code(
            hass=self.hass,
            issuer_url=self._issuer_url,
            client_id=self._client_id,
            scope=SCOPE_BASE,
        )
        self._last_token_error = None
        return await self.async_step_device()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return OpenEnergyOptionsFlow(config_entry)


class OpenEnergyOptionsFlow(config_entries.OptionsFlow):
    """Options flow acting as a simple menu."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Main menu."""
        # TODO: Add 'rotate_frp' option if needed, for now we stick to basic rotation
        return self.async_show_menu(
            step_id="init",
            menu_options=["status", "server_status", "reconnect", "rotate", "disconnect", "advanced"],
            sort=True,
        )

    async def async_step_status(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Display token/user status."""
        data = self.config_entry.data
        kc_user = data.get(DATA_KC_USER, {}) or {}
        has_token = DATA_OE_TOKEN in data
        prov = data.get(DATA_PROVISIONING_STATE, "not_connected")
        tunnel = data.get(DATA_TUNNEL_DOMAIN, "N/A")

        return self.async_show_form(
            step_id="status",
            data_schema=vol.Schema({}),
            description_placeholders={
                "connected": "yes" if has_token else "no",
                "provisioning": str(prov),
                "sub": str(kc_user.get("sub", "")),
                "email": str(kc_user.get("email", "")),
                "tunnel": str(tunnel),
            },
        )

    async def async_step_server_status(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Check public health endpoint."""
        health_url = self.config_entry.data.get(CONF_HEALTH_URL, DEFAULT_HEALTH_URL)
        ok, details = await get_health(self.hass, health_url)
        return self.async_show_form(
            step_id="server_status",
            data_schema=vol.Schema({}),
            description_placeholders={
                "url": health_url,
                "ok": "yes" if ok else "no",
                "details": details,
            },
        )

    async def async_step_reconnect(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Trigger device flow again (reauth/provision)."""
        self.config_entry.async_start_reauth(self.hass)
        return self.async_abort(reason="reauth_started")

    async def async_step_rotate(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Rotate the OpenEnergy token via server API (requires reauth first usually).
        
        Note: The current rotate_opaque_token implementation requires a KC token.
        But we don't store KC tokens. So this action will likely fail if we don't prompt for reauth.
        For now, we just redirect to reauth if we want to be safe, 
        OR we assume the user just did a reauth flow.
        """
        # Since we don't keep KC tokens, we cannot just "rotate" silently. 
        # We must ask the user to re-authenticate to get a fresh KC token to authorize rotation.
        return await self.async_step_reconnect()

    async def async_step_disconnect(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Remove stored tokens and user identity."""
        data = dict(self.config_entry.data)
        data.pop(DATA_OE_TOKEN, None)
        data.pop(DATA_KC_USER, None)
        data.pop(DATA_SERVER_UUID, None)
        data.pop(DATA_FRP_SECRET, None)
        data.pop(DATA_TUNNEL_DOMAIN, None)
        data[DATA_PROVISIONING_STATE] = "not_connected"
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        return self.async_abort(reason="disconnected")

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Display server-related configuration (read-only)."""
        data = self.config_entry.data
        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema({}),
            description_placeholders={
                "issuer": str(data.get(CONF_ISSUER_URL, "")),
                "client_id": str(data.get(CONF_CLIENT_ID, "")),
                "portal": str(data.get(CONF_PORTAL_URL, "")),
                "health": str(data.get(CONF_HEALTH_URL, "")),
                "server_uuid": str(data.get(DATA_SERVER_UUID, "")),
            },
        )