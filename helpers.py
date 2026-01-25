"""Helper functions for OpenEnergy integration."""

from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .const import DOMAIN
from .addon import is_hassio, get_addon_info

_LOGGER = logging.getLogger(__name__)

async def verify_http_config(hass: HomeAssistant) -> None:
    """Raise a repair issue advising the user to verify trusted_proxies."""
    _LOGGER.info("Running verify_http_config check.")
    async_create_issue(
        hass,
        DOMAIN,
        "trusted_proxies_configuration",
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="trusted_proxies_configuration",
        learn_more_url="https://www.home-assistant.io/integrations/http/#trusted_proxies",
    )

async def check_addon_installed(hass: HomeAssistant) -> None:
    """Check if the add-on is installed, otherwise raise a repair issue."""
    _LOGGER.info("Running check_addon_installed check.")
    if not is_hassio(hass):
        _LOGGER.info("Not running under Hass.io, skipping addon check.")
        return

    info = await get_addon_info(hass)
    if not info:
        _LOGGER.warning("Add-on not found, creating repair issue.")
        async_create_issue(
            hass,
            DOMAIN,
            "addon_not_installed",
            is_fixable=False,
            severity=IssueSeverity.ERROR,
            translation_key="addon_not_installed",
        )
    else:
        _LOGGER.info("Add-on found: %s", info.get("slug"))
