"""OAuth2 helper utilities for OpenEnergy (Keycloak OIDC)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN


@dataclass(frozen=True, slots=True)
class KeycloakOidcEndpoints:
    """OIDC endpoints derived from a Keycloak realm issuer URL."""
    authorize_url: str
    token_url: str
    userinfo_url: str


def build_keycloak_endpoints(issuer_url: str) -> KeycloakOidcEndpoints:
    """Build standard Keycloak OIDC endpoints from a realm issuer URL."""
    base = issuer_url.rstrip("/")
    return KeycloakOidcEndpoints(
        authorize_url=f"{base}/protocol/openid-connect/auth",
        token_url=f"{base}/protocol/openid-connect/token",
        userinfo_url=f"{base}/protocol/openid-connect/userinfo",
    )


def build_oauth2_implementation(
    hass: HomeAssistant,
    issuer_url: str,
    client_id: str,
) -> config_entry_oauth2_flow.AbstractOAuth2Implementation:
    """Create a local OAuth2 implementation (Authorization Code + PKCE) for Keycloak.

    Key details:
    - Keycloak client is PUBLIC, so client_secret is empty.
    - PKCE (S256) must be enabled/required in Keycloak.
    - Home Assistant versions differ on the LocalOAuth2ImplementationWithPkce signature.
      This implementation uses only widely supported parameters.
    """
    ep = build_keycloak_endpoints(issuer_url)

    # NOTE: Do NOT pass auth_domain here; some HA versions don't support it.
    return config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce(
        hass=hass,
        domain=DOMAIN,
        client_id=client_id,
        authorize_url=ep.authorize_url,
        token_url=ep.token_url,
        client_secret="",
        code_verifier_length=128,
    )

