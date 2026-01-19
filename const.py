"""Constants for the OpenEnergy integration."""

DOMAIN = "openenergy"
PLATFORMS: list[str] = []

CONF_ISSUER_URL = "issuer_url"
CONF_CLIENT_ID = "client_id"
CONF_PORTAL_URL = "portal_url"
CONF_HEALTH_URL = "health_url"

DEFAULT_ISSUER_URL = "https://auth1.openenergy.be/realms/portalOpenenergy"
DEFAULT_CLIENT_ID = "openenergy-ha"
DEFAULT_PORTAL_URL = "https://portal.openenergy.be"
DEFAULT_HEALTH_URL = "https://portal.openenergy.be/api/health"

# OIDC scopes requested during Device Authorization.
SCOPE_BASE = "openid profile email"

# Data stored in config entry
DATA_KC_USER = "kc_user"                 # {'sub': ..., 'email': ..., 'preferred_username': ...}
DATA_OE_TOKEN = "openenergy_token"       # opaque token issued by OpenEnergy server
DATA_PROVISIONING_STATE = "provisioning_state"  # 'ok' | 'exchange_failed' | 'not_connected'
