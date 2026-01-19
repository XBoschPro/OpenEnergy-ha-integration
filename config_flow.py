"""Config flow for OpenEnergy integration (Keycloak OAuth2 + Options menu).

This flow supports:
- OAuth2 Authorization Code + PKCE against Keycloak (public client)
- Token storage modes:
  - exchange (recommended): exchange KC access token for OpenEnergy token (revocable/scoped)
  - kc_access_only: store only KC access token (reauth more frequent)
  - kc_refresh: store KC refresh token (requires offline_access, more convenient but higher risk)

It also provides an OptionsFlow acting as a "menu":
- Connection status
- Server status (public health endpoint)
- Reconnect
- Disconnect
"""

from __future__ import annotations

import logging
from typing import Any
import inspect

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_entry_oauth2_flow

from .auth import build_keycloak_endpoints, build_oauth2_implementation
from .const import (
    CONF_CLIENT_ID,
    CONF_ISSUER_URL,
    CONF_PORTAL_URL,
    CONF_TOKEN_STORAGE,
    DATA_KC_USER,
    DATA_OAUTH_IMPL,
    DATA_OAUTH_TOKEN,
    DATA_OE_TOKEN,
    DEFAULT_CLIENT_ID,
    DEFAULT_HEALTH_URL,
    DEFAULT_ISSUER_URL,
    DEFAULT_PORTAL_URL,
    DOMAIN,
    SCOPE_BASE,
    SCOPE_OFFLINE,
    TOKEN_STORAGE_EXCHANGE,
    TOKEN_STORAGE_KC_ACCESS,
    TOKEN_STORAGE_KC_REFRESH,
)

_LOGGER = logging.getLogger(__name__)


def _storage_options() -> dict[str, str]:
    """Return storage mode mapping used in voluptuous selectors."""
    return {
        TOKEN_STORAGE_EXCHANGE: "Recommended: exchange KC token for OpenEnergy token (revocable, scoped)",
        TOKEN_STORAGE_KC_ACCESS: "More secure: store KC access only (reauth more often)",
        TOKEN_STORAGE_KC_REFRESH: "More convenient: store KC refresh token (offline_access; higher risk if HA compromised)",
    }


async def _async_register_oauth_implementation(hass: HomeAssistant, implementation: Any) -> None:
    """Register an OAuth2 implementation (compatible across HA versions)."""
    func = getattr(config_entry_oauth2_flow, "async_register_implementation", None)
    if func is None:
        raise RuntimeError("Home Assistant does not provide async_register_implementation")

    # Some HA versions define it as a regular callback, others as a coroutine.
    if inspect.iscoroutinefunction(func):
        try:
            await func(hass, DOMAIN, implementation)
        except TypeError:
            await func(hass, implementation)
    else:
        try:
            func(hass, DOMAIN, implementation)
        except TypeError:
            func(hass, implementation)



STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ISSUER_URL, default=DEFAULT_ISSUER_URL): str,
        vol.Required(CONF_CLIENT_ID, default=DEFAULT_CLIENT_ID): str,
        vol.Required(CONF_PORTAL_URL, default=DEFAULT_PORTAL_URL): str,
        vol.Required(CONF_TOKEN_STORAGE, default=TOKEN_STORAGE_EXCHANGE): vol.In(_storage_options()),
    }
)


class OpenEnergyConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Handle the OpenEnergy config flow (OAuth2)."""

    VERSION = 1
    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return the logger used by this config flow."""
        return _LOGGER
    
    reauth_entry: config_entries.ConfigEntry | None = None
    _issuer_url: str | None = None
    _client_id: str | None = None
    _portal_url: str | None = None
    _token_storage: str | None = None
    
    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra parameters appended to the authorize URL."""
        scopes = SCOPE_BASE
        if self._token_storage == TOKEN_STORAGE_KC_REFRESH:
            scopes = f"{scopes} {SCOPE_OFFLINE}"
        return {"scope": scopes}





    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle a flow started by a user."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        self._issuer_url = user_input[CONF_ISSUER_URL].rstrip("/")
        self._client_id = user_input[CONF_CLIENT_ID]
        self._portal_url = user_input[CONF_PORTAL_URL].rstrip("/")
        self._token_storage = user_input[CONF_TOKEN_STORAGE]

        # Unique id: one entry per Keycloak realm + client_id
        await self.async_set_unique_id(f"openenergy::{self._issuer_url}::{self._client_id}")
        self._abort_if_unique_id_configured()

        impl = build_oauth2_implementation(self.hass, self._issuer_url, self._client_id)
        await _async_register_oauth_implementation(self.hass, impl)


        # Ensure OIDC scopes are present. Add offline_access only if user selected KC refresh mode.
        scopes = SCOPE_BASE
        if self._token_storage == TOKEN_STORAGE_KC_REFRESH:
            scopes = f"{scopes} {SCOPE_OFFLINE}"

        # AbstractOAuth2FlowHandler supports extra authorize parameters.
        # This ensures Keycloak gets `scope=openid ...`.
        #self.extra_authorize_data = {"scope": scopes}

        return await self.async_step_pick_implementation()

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Start a reauth flow (triggered by options menu or auth failures)."""
        self.reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if self.reauth_entry is None:
            return self.async_abort(reason="reauth_entry_not_found")

        self._issuer_url = self.reauth_entry.data[CONF_ISSUER_URL]
        self._client_id = self.reauth_entry.data[CONF_CLIENT_ID]
        self._portal_url = self.reauth_entry.data[CONF_PORTAL_URL]
        self._token_storage = self.reauth_entry.data.get(CONF_TOKEN_STORAGE, TOKEN_STORAGE_EXCHANGE)

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm dialog shown before redirecting to Keycloak."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))

        impl = build_oauth2_implementation(self.hass, self._issuer_url, self._client_id)
        await _async_register_oauth_implementation(self.hass, impl)


        scopes = SCOPE_BASE
        if self._token_storage == TOKEN_STORAGE_KC_REFRESH:
            scopes = f"{scopes} {SCOPE_OFFLINE}"
        #self.extra_authorize_data = {"scope": scopes}

        return await self.async_step_pick_implementation()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> FlowResult:
        """Create or update the config entry after OAuth completes."""
        issuer_url = self._issuer_url
        client_id = self._client_id
        portal_url = self._portal_url
        token_storage = self._token_storage

        if not issuer_url or not client_id or not portal_url or not token_storage:
            return self.async_abort(reason="missing_setup_parameters")

        oauth_token = data["token"]
        auth_impl = data["auth_implementation"]

        # Fetch userinfo to keep Keycloak identity (sub/email/username).
        kc_user = await _fetch_keycloak_userinfo(self.hass, issuer_url, oauth_token)

        entry_data: dict[str, Any] = {
            CONF_ISSUER_URL: issuer_url,
            CONF_CLIENT_ID: client_id,
            CONF_PORTAL_URL: portal_url,
            CONF_TOKEN_STORAGE: token_storage,
            DATA_OAUTH_IMPL: auth_impl,
            DATA_KC_USER: kc_user,
        }

        # Store KC token depending on mode.
        if token_storage in (TOKEN_STORAGE_KC_ACCESS, TOKEN_STORAGE_KC_REFRESH, TOKEN_STORAGE_EXCHANGE):
            entry_data[DATA_OAUTH_TOKEN] = oauth_token

        # Exchange KC access token for OpenEnergy token if requested.
        if token_storage == TOKEN_STORAGE_EXCHANGE:
            oe_token = await _exchange_for_openenergy_token(self.hass, portal_url, oauth_token)
            if oe_token:
                entry_data[DATA_OE_TOKEN] = oe_token
            else:
                # Keep entry created even if exchange is not ready yet; user can retry later.
                _LOGGER.warning("OpenEnergy token exchange failed (API missing or error).")

        if self.reauth_entry is not None:
            # Always reload after successful reauth.
            return self.async_update_reload_and_abort(self.reauth_entry, data=entry_data)

        return self.async_create_entry(title="OpenEnergy", data=entry_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OpenEnergyOptionsFlow(config_entry)


class OpenEnergyOptionsFlow(config_entries.OptionsFlow):
    """Options flow acting as a small menu for the integration."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show the main menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["status", "server_status", "reconnect", "disconnect"],
            sort=True,
        )

    async def async_step_status(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Display connection status."""
        data = self.config_entry.data
        has_kc = DATA_OAUTH_TOKEN in data
        has_oe = DATA_OE_TOKEN in data
        kc_user = data.get(DATA_KC_USER, {}) or {}

        return self.async_show_form(
            step_id="status",
            data_schema=vol.Schema({}),
            description_placeholders={
                "kc": "yes" if has_kc else "no",
                "oe": "yes" if has_oe else "no",
                "sub": str(kc_user.get("sub", "")),
                "email": str(kc_user.get("email", "")),
            },
        )

    async def async_step_server_status(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Check the portal public health endpoint."""
        ok, details = await _check_health(self.hass, DEFAULT_HEALTH_URL)
        return self.async_show_form(
            step_id="server_status",
            data_schema=vol.Schema({}),
            description_placeholders={
                "ok": "yes" if ok else "no",
                "details": details,
                "url": DEFAULT_HEALTH_URL,
            },
        )

    async def async_step_reconnect(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Trigger a reauthentication flow."""
        self.config_entry.async_start_reauth(self.hass)
        return self.async_abort(reason="reauth_started")

    async def async_step_disconnect(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Clear stored tokens and reload entry."""
        data = dict(self.config_entry.data)
        data.pop(DATA_OAUTH_TOKEN, None)
        data.pop(DATA_OE_TOKEN, None)

        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        return self.async_abort(reason="disconnected")


async def _fetch_keycloak_userinfo(hass: HomeAssistant, issuer_url: str, oauth_token: dict[str, Any]) -> dict[str, Any]:
    """Fetch Keycloak userinfo and return a small stable subset."""
    ep = build_keycloak_endpoints(issuer_url)

    try:
        resp = await config_entry_oauth2_flow.async_oauth2_request(
            hass, oauth_token, "get", ep.userinfo_url
        )
        payload = await resp.json()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Failed to fetch Keycloak userinfo: %s", err)
        return {}

    # Keep default claims only
    return {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        "preferred_username": payload.get("preferred_username"),
        "name": payload.get("name"),
    }


async def _exchange_for_openenergy_token(
    hass: HomeAssistant,
    portal_url: str,
    oauth_token: dict[str, Any],
) -> str | None:
    """Exchange Keycloak access token for an OpenEnergy token.

    Expected endpoint (to implement server-side):
      POST {portal_url}/api/ha/auth/exchange
      Authorization: Bearer <KC access token>
      Response JSON: {"token": "<opaque openenergy token>"}
    """
    access_token = oauth_token.get("access_token")
    if not access_token:
        return None

    url = f"{portal_url}/api/ha/auth/exchange"
    session = aiohttp_client.async_get_clientsession(hass)

    try:
        resp = await session.post(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("OpenEnergy exchange request failed: %s", err)
        return None

    if resp.status >= 400:
        _LOGGER.warning("OpenEnergy exchange failed: HTTP %s", resp.status)
        return None

    try:
        payload = await resp.json()
    except Exception:  # noqa: BLE001
        return None

    token = payload.get("token")
    return token if isinstance(token, str) and token else None


async def _check_health(hass: HomeAssistant, url: str) -> tuple[bool, str]:
    """Check portal health endpoint and return (ok, details)."""
    session = aiohttp_client.async_get_clientsession(hass)

    try:
        resp = await session.get(url, timeout=10)
        text = await resp.text()
        ok = 200 <= resp.status < 300
        details = f"HTTP {resp.status} - {text[:200]}"
        return ok, details
    except Exception as err:  # noqa: BLE001
        return False, f"error: {err}"
