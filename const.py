"""Constants for the OpenEnergy integration."""

DOMAIN = "openenergy"
PLATFORMS: list[str] = []

CONF_ISSUER_URL = "issuer_url"
CONF_CLIENT_ID = "client_id"
CONF_PORTAL_URL = "portal_url"
CONF_TOKEN_STORAGE = "token_storage"

DEFAULT_ISSUER_URL = "https://auth1.openenergy.be/realms/portalOpenenergy"
DEFAULT_CLIENT_ID = "openenergy-ha"
DEFAULT_PORTAL_URL = "https://portal.openenergy.be"

# Public health endpoint (no auth)
DEFAULT_HEALTH_URL = "https://portal.openenergy.be/api/health"

# OAuth scopes
SCOPE_BASE = "openid profile email"
SCOPE_OFFLINE = "offline_access"

# Token storage modes
TOKEN_STORAGE_EXCHANGE = "exchange"         # Recommended: exchange KC token for OpenEnergy token
TOKEN_STORAGE_KC_ACCESS = "kc_access_only"  # Strict: keep KC access only (reauth more often)
TOKEN_STORAGE_KC_REFRESH = "kc_refresh"     # Convenience: keep KC refresh (requires offline_access)

DATA_OAUTH_IMPL = "auth_implementation"
DATA_OAUTH_TOKEN = "token"          # Keycloak OAuth2 token dict as provided by HA
DATA_KC_USER = "kc_user"            # dict with sub/email/username (from userinfo)
DATA_OE_TOKEN = "openenergy_token"  # opaque OpenEnergy token from exchange
