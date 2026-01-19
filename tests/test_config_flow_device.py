"""Unit tests for OpenEnergy config flow (device auth).

These tests mock Keycloak + OpenEnergy endpoints using aioclient_mock.
"""

from __future__ import annotations

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.openenergy.const import (
    CONF_CLIENT_ID,
    CONF_HEALTH_URL,
    CONF_ISSUER_URL,
    CONF_PORTAL_URL,
    DATA_OE_TOKEN,
    DATA_PROVISIONING_STATE,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_flow_device_pending_then_exchange_fails(hass, aioclient_mock):
    """Device flow: pending -> success token -> exchange fails -> entry created with exchange_failed."""
    # Init flow
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    issuer = "https://auth1.openenergy.be/realms/portalOpenenergy"
    device_url = f"{issuer}/protocol/openid-connect/auth/device"
    token_url = f"{issuer}/protocol/openid-connect/token"
    userinfo_url = f"{issuer}/protocol/openid-connect/userinfo"

    # Mock device code response
    aioclient_mock.post(
        device_url,
        json={
            "device_code": "devcode",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://auth/verify",
            "verification_uri_complete": "https://auth/verify?user_code=ABCD-EFGH",
            "expires_in": 600,
            "interval": 5,
        },
    )

    # Submit user step
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ISSUER_URL: issuer,
            CONF_CLIENT_ID: "openenergy-ha",
            CONF_PORTAL_URL: "https://portal.openenergy.be",
            CONF_HEALTH_URL: "https://portal.openenergy.be/api/health",
        },
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "device"

    # Poll 1: pending (token endpoint error)
    aioclient_mock.post(token_url, json={"error": "authorization_pending"})
    result3 = await hass.config_entries.flow.async_configure(result2["flow_id"], {})
    assert result3["type"] == FlowResultType.FORM
    assert result3["step_id"] == "device"

    # Poll 2: token success
    aioclient_mock.post(
        token_url,
        json={"access_token": "kc_access", "token_type": "Bearer", "expires_in": 300},
    )
    # Userinfo
    aioclient_mock.get(
        userinfo_url,
        json={"sub": "kc-sub-123", "email": "u@example.com", "preferred_username": "user"},
    )
    # Exchange fails (simulate 501)
    aioclient_mock.post("https://portal.openenergy.be/api/ha/auth/exchange", status=501, json={"error": "not_ready"})

    result4 = await hass.config_entries.flow.async_configure(result3["flow_id"], {})
    assert result4["type"] == FlowResultType.CREATE_ENTRY
    entry = result4["result"]
    assert entry.domain == DOMAIN
    assert entry.data[DATA_PROVISIONING_STATE] == "exchange_failed"
    assert DATA_OE_TOKEN not in entry.data


@pytest.mark.asyncio
async def test_flow_device_success_exchange_ok(hass, aioclient_mock):
    """Device flow: success -> exchange returns OpenEnergy token -> entry connected."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    issuer = "https://auth1.openenergy.be/realms/portalOpenenergy"
    device_url = f"{issuer}/protocol/openid-connect/auth/device"
    token_url = f"{issuer}/protocol/openid-connect/token"
    userinfo_url = f"{issuer}/protocol/openid-connect/userinfo"

    aioclient_mock.post(
        device_url,
        json={
            "device_code": "devcode",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://auth/verify",
            "verification_uri_complete": None,
            "expires_in": 600,
            "interval": 5,
        },
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ISSUER_URL: issuer,
            CONF_CLIENT_ID: "openenergy-ha",
            CONF_PORTAL_URL: "https://portal.openenergy.be",
            CONF_HEALTH_URL: "https://portal.openenergy.be/api/health",
        },
    )
    assert result2["step_id"] == "device"

    aioclient_mock.post(token_url, json={"access_token": "kc_access", "token_type": "Bearer", "expires_in": 300})
    aioclient_mock.get(userinfo_url, json={"sub": "kc-sub-123"})
    aioclient_mock.post(
        "https://portal.openenergy.be/api/ha/auth/exchange",
        json={"openenergy_token": "oe-token-xyz"},
    )

    result3 = await hass.config_entries.flow.async_configure(result2["flow_id"], {})
    assert result3["type"] == FlowResultType.CREATE_ENTRY
    entry = result3["result"]
    assert entry.data[DATA_PROVISIONING_STATE] == "ok"
    assert entry.data[DATA_OE_TOKEN] == "oe-token-xyz"
