"""Constants for the Evohaus Home integration."""

DOMAIN = "evohaus_parking"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_NAME = "Evohaus Parking"

# API URLs
API_LOGIN = "signinForm.php?mode=ok"
API_RESIDENCE = "/php/ownConsumption.php"
API_METER_DATA = "/php/newMeterTable.php"
API_TRAFFIC = "/php/getTrafficLightStatus.php"
API_CHART = "php/getMeterDataWithParam.php"

# Update intervals
THROTTLE_INTERVAL_SECONDS = 100
SCAN_INTERVAL_MINUTES = 15