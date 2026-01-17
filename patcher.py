"""Patcher for configuration.yaml."""
import yaml
from homeassistant.core import HomeAssistant

YAML_CONFIG = """
# Required for OpenEnergy secure remote connection
# Enables reverse proxy support for OpenEnergy FRP
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - "127.0.0.1"
    - "::1"
"""

def patch_configuration(hass: HomeAssistant):
    """Patch configuration.yaml to include http config."""
    config_path = hass.config.path("configuration.yaml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        config = {}

    if not config or "http" not in config:
        with open(config_path, "a") as f:
            f.write(YAML_CONFIG)
        return True

    return False