"""Constants for the OpenEnergy integration."""

DOMAIN = "openenergy"
PLATFORMS: list[str] = ["binary_sensor", "sensor"]

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
DATA_OE_TOKEN = "openenergy_token"       # opaque token issued by OpenEnergy server (device_token)
DATA_SERVER_UUID = "server_ha_uuid"      # UUID assigned by OpenEnergy server
DATA_FRP_SECRET = "frp_device_secret"    # Secret for FRPC (only returned once)
DATA_FRP_SERVER_ADDR = "frp_server_addr"
DATA_FRP_SERVER_PORT = "frp_server_port"
DATA_FRP_TLS_ENABLE = "frp_tls_enable"
DATA_TUNNEL_DOMAIN = "tunnel_domain"     # Full domain (e.g. slug.ha.openenergy.be)
DATA_PROVISIONING_STATE = "provisioning_state"  # 'ok' | 'exchange_failed' | 'not_connected'

# Endpoints
ENDPOINT_HEALTH = "/api/health"
ENDPOINT_ENROLL = "/api/ha/enroll"
ENDPOINT_ROTATE_TOKEN = "/api/ha/token/rotate"
ENDPOINT_ROTATE_FRP = "/api/ha/frp/rotate"
ENDPOINT_GET_FRPC = "/api/ha/frpc"
