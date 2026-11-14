"""Constants for the Evohaus Home integration."""

DOMAIN = "evohaus_parking"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# API URLs
API_BASE_URL = "https://ems003.enocoo.com:48889"
API_LOGIN_PAGE = "/anmelden"
API_LOGIN = "/anmelden?mode=ok"
LOGIN_SUCCESS_PATH = "/start"
API_METER_DATA = "/api/zaehlertabelle"
API_TRAFFIC = "/api/ampel"

# Update intervals
THROTTLE_INTERVAL_SECONDS = 100
SCAN_INTERVAL_MINUTES = 15