"""Config flow for OpenEnergy using Keycloak Device Authorization Grant.

Flow overview:
1) User enters issuer/client_id/portal_url (and optional health url).
2) Integration requests device_code + user_code from Keycloak.
3) Integration displays a code + verification URL.
4) User authenticates on Keycloak website and enters the code.
5) User clicks "Continue" in HA; we poll token endpoint once per click.
6) On token success, we fetch userinfo (sub/email).
7) We call OpenEnergy exchange endpoint to obtain an opaque device token.
   - If exchange is not ready yet, we still create an entry but mark it not connected.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import instance_id

from .api import get_health
from .const import (
    CONF_CLIENT_ID,
    CONF_HEALTH_URL,
    CONF_ISSUER_URL,
    CONF_PORTAL_URL,
    DATA_KC_USER,
    DATA_OE_TOKEN,
    DATA_PROVISIONING_STATE,
    DEFAULT_CLIENT_ID,
    DEFAULT_HEALTH_URL,
    DEFAULT_ISSUER_URL,
    DEFAULT_PORTAL_URL,
    DOMAIN,
    SCOPE_BASE,
    DATA_HA_UUID,
    DATA_FRP_DEVICE_SECRET,
)
from .device_auth import DeviceCodeResponse, fetch_userinfo, poll_token_once, request_device_code
from .portal_api import PortalClient, PortalConfig, PortalAuthError


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

        await self.async_set_unique_id(f"openenergy::{self._portal_url}::{self._issuer_url}::{self._client_id}")
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

        # Success: fetch userinfo + exchange token.
        access_token = token_result.access_token
        kc_user = await fetch_userinfo(self.hass, self._issuer_url, access_token)


        # Build portal client
        portal = PortalClient(self.hass, PortalConfig(portal_url=self._portal_url))

        # Stable HA installation identifier
        device_uid = await instance_id.async_get(self.hass)

        # Human label shown in DB / portal
        label = self.hass.config.location_name or "Home Assistant"

        # If this is a reauth, you can reuse existing ha_uuid (optional)
        existing_entry = None
        if "entry_id" in self.context:
            existing_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        existing_ha_uuid = existing_entry.data.get(DATA_HA_UUID) if existing_entry else None

        try:
            enroll = await portal.async_enroll(
                kc_access_token=access_token,
                ha_uuid=existing_ha_uuid,
                device_uid=device_uid,
                device_mac=None,
                label=label,
            )
        except PortalAuthError as err:
            _LOGGER.error("Portal enroll rejected: %s", err)
            self._last_token_error = "portal_enroll_rejected"
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema({}),
                description_placeholders=placeholders | {"last_error": "portal_enroll_rejected"},
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Portal enroll failed: %s", err)
            self._last_token_error = "portal_enroll_failed"
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema({}),
                description_placeholders=placeholders | {"last_error": "portal_enroll_failed"},
            )

        device_token = enroll.get("device_token")
        ha_uuid_server = enroll.get("ha_uuid")
        frp_secret = (enroll.get("frpc") or {}).get("device_secret")

        entry_data: dict[str, Any] = {
            CONF_ISSUER_URL: self._issuer_url,
            CONF_CLIENT_ID: self._client_id,
            CONF_PORTAL_URL: self._portal_url,
            CONF_HEALTH_URL: self._health_url,
            DATA_KC_USER: kc_user,
        }

        if isinstance(device_token, str) and device_token:
            entry_data[DATA_OE_TOKEN] = device_token
            entry_data[DATA_PROVISIONING_STATE] = "ok"
            if isinstance(ha_uuid_server, str) and ha_uuid_server:
                entry_data[DATA_HA_UUID] = ha_uuid_server
            if isinstance(frp_secret, str) and frp_secret:
                entry_data[DATA_FRP_DEVICE_SECRET] = frp_secret
        else:
            entry_data[DATA_PROVISIONING_STATE] = "exchange_failed"  # keep your existing label for now

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

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry


    async def async_step_init(self, user_input=None):
        """Manage the OpenEnergy options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Minimal example schema - adapt to your current options
        current = dict(self._config_entry.options)

        schema = vol.Schema(
            {
                vol.Optional("addon_name_contains", default=current.get("addon_name_contains", "OpenEnergy FRP Client")): str,
                vol.Optional("local_ip", default=current.get("local_ip", "127.0.0.1")): str,
                vol.Optional("local_port", default=int(current.get("local_port", 8123))): int,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    # async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    #     """Main menu."""
    #     return self.async_show_menu(
    #         step_id="init",
    #         menu_options=["status", "server_status", "reconnect", "rotate", "disconnect", "advanced"],
    #         sort=True,
    #     )

    async def async_step_status(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Display token/user status."""
        data = self.config_entry.data
        kc_user = data.get(DATA_KC_USER, {}) or {}
        has_token = DATA_OE_TOKEN in data
        prov = data.get(DATA_PROVISIONING_STATE, "not_connected")

        return self.async_show_form(
            step_id="status",
            data_schema=vol.Schema({}),
            description_placeholders={
                "connected": "yes" if has_token else "no",
                "provisioning": str(prov),
                "sub": str(kc_user.get("sub", "")),
                "email": str(kc_user.get("email", "")),
                "username": str(kc_user.get("preferred_username", "")),
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

    # async def async_step_rotate(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    #     """Rotate the OpenEnergy token via server API."""
    #     data = dict(self.config_entry.data)
    #     portal_url = data.get(CONF_PORTAL_URL, DEFAULT_PORTAL_URL)
    #     oe_token = data.get(DATA_OE_TOKEN)

    #     if not oe_token:
    #         return self.async_show_form(
    #             step_id="rotate",
    #             data_schema=vol.Schema({}),
    #             errors={"base": "no_token"},
    #         )

    #     new_token = await rotate_token(self.hass, portal_url, oe_token)
    #     if not new_token:
    #         return self.async_show_form(
    #             step_id="rotate",
    #             data_schema=vol.Schema({}),
    #             errors={"base": "rotate_failed"},
    #         )

    #     data[DATA_OE_TOKEN] = new_token
    #     data[DATA_PROVISIONING_STATE] = "ok"
    #     self.hass.config_entries.async_update_entry(self.config_entry, data=data)
    #     await self.hass.config_entries.async_reload(self.config_entry.entry_id)
    #     return self.async_abort(reason="rotated")

    async def async_step_disconnect(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Remove stored tokens and user identity."""
        data = dict(self.config_entry.data)
        data.pop(DATA_OE_TOKEN, None)
        data.pop(DATA_KC_USER, None)
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
            },
        )

