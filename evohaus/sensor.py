import logging
import homeassistant

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import STATE_UNKNOWN

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    STATE_CLASS_TOTAL,
)

from homeassistant.const import (
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_PASSWORD,
    CONF_USERNAME,
    CURRENCY_EURO,
    CURRENCY_CENT,
    UnitOfEnergy,
    UnitOfVolume,
)
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass

from homeassistant.exceptions import PlatformNotReady
from homeassistant.util import Throttle
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)
import requests
import json

from datetime import timedelta
from bs4 import BeautifulSoup
import re
from cachetools import TTLCache

THROTTLE_INTERVAL_SECONDS = 100

SCAN_INTERVAL = timedelta(minutes=15)
THROTTLE_INTERVAL = timedelta(seconds=THROTTLE_INTERVAL_SECONDS)

DEFAULT_NAME = "evohaus_parking"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL): cv.time_period,
    }
)
ELECTRIC_METER = {
    "name": "electricity_meter_parking",
    "icon": "mdi:meter-electric-outline",
    "unit": UnitOfEnergy.KILO_WATT_HOUR,
    "description": "Verbrauch Strom",
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": STATE_CLASS_TOTAL_INCREASING,
}
ELECTRIC_CONSUMPTION = {
    "name": "electricity_consumption_parking",
    "icon": "mdi:solar-power",
    "unit": UnitOfEnergy.KILO_WATT_HOUR,
    "query": "Stromverbrauch",
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": STATE_CLASS_TOTAL,
}
TOTAL_ELECTRIC_CONSUMPTION = {
    "name": "total_electricity_consumption_parking",
    "icon": "mdi:solar-power",
    "unit": UnitOfEnergy.KILO_WATT_HOUR,
    "query": "Stromverbrauch",
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": STATE_CLASS_TOTAL_INCREASING,
}

def setup_platform(hass, config, add_devices, discovery_info=None):
    user = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    name = config.get(CONF_NAME)

    _LOGGER.info("Initializing Evohaus Parking...)")

    devices = []
    try:
        evohaus = Evohaus(user, password, hass)
        devices.append(ElectricConsumptionSensor(evohaus))
        devices.append(ElectricTotalConsumptionSensor(evohaus))
        devices.append(ElectricityMeterSensor(evohaus))

    except HomeAssistantError:
        _LOGGER.exception("Fail to setup Evohaus Parking.")
        raise PlatformNotReady

    add_devices(devices)


class Evohaus:
    def __init__(self, user, password, hass):
        self._cookie = None
        self._meter_data = None
        self._user = user
        self._password = password
        self._domain = "https://ems003.enocoo.com:48889/"
        self.__login()
        self.residenceId = self._get_residence()
        self._data_source = None
        self.cache = TTLCache(maxsize=1, ttl=THROTTLE_INTERVAL_SECONDS)
        self.hass = hass

    def __login(self):
        _LOGGER.debug("Start login....")
        payload = {"user": self._user, "passwort": self._password}
        url = self._domain + "signinForm.php?mode=ok"
        with requests.Session() as s:
            r = s.get(url)
            self._cookie = {"PHPSESSID": r.cookies["PHPSESSID"]}
            s.post(url, data=payload, cookies=self._cookie)
        if self._cookie is None:
            _LOGGER.error("Cannot login")
        else:
            _LOGGER.debug("Login successful")

    def _get_residence(self):
        url = self._domain + "/php/ownConsumption.php"
        with requests.Session() as s:
            r = s.get(url, cookies=self._cookie)

        content = BeautifulSoup(r.content, "html.parser")
        scripts = content.find_all('script')
        chosenResidence = None

        # iterate over each script tag
        for script in scripts:
            if script.string:  # if the script tag has something
                # check if chosenResidence is in this script tag
                match = re.search(r'var chosenResidenceId = "(.*?)";', script.string)
                if match:
                    # if found, extract the value and stop searching further
                    chosenResidence = match.group(1)
                    break;
                    
        if chosenResidence is None:
            _LOGGER.error('Residence can not be found')
        
        return chosenResidence

    def sync_meter_data(self):
        if "meter_data" not in self.cache:
            url = self._domain + "/php/newMeterTable.php"
            now = homeassistant.util.dt.now()  # current date and time
            today = now.strftime("%Y-%m-%d")
            payload = {"dateParam": today}

            with requests.Session() as s:
                r = s.post(url, data=payload, cookies=self._cookie)
                if len(r.content) == 0:
                    self.__login()
                    r = s.post(url, data=payload, cookies=self._cookie)
                self.cache["meter_data"] = BeautifulSoup(r.content, "html.parser")
            if self._cookie is None:
                _LOGGER.error("Cannot fetch meter data")
            else:
                _LOGGER.debug(self._meter_data)
        self._meter_data = self.cache["meter_data"]

    def fetch_meter_data(self, meterType):
        rows = self._meter_data.find_all("tr")
        row = {"state": 0, "meter_no": ""}

        for raw_row in rows:
            _LOGGER.debug("row content: " + str(raw_row))
            cols = raw_row.find_all("td")
            if not cols:
                continue

            unit = cols[0].contents[0]
            description = cols[1].contents[0].replace(" " + unit, "")
            if description.startswith(meterType):
                row["state"] = float(
                    cols[4].contents[0].replace(".", "").replace(",", ".")
                )
                row["meter_no"] = cols[2].contents[0]
                return row
            else:
                continue

        return row

    def fetch_chart_data(self, dataType):
        """Parse data."""
        now = homeassistant.util.dt.now()  # current date and time
        today = now.strftime("%Y-%m-%d")
        url = (
                self._domain
                + "php/getMeterDataWithParam.php?from="
                + today
                + "&intVal=Tag&mClass="
                + dataType
                + "&AreaId="
                + self.residenceId
        )
        data = None
        with requests.Session() as s:
            r = s.get(url, cookies=self._cookie)
            data = json.loads(r.content)
        if data is None or len(data[0]) == 0:
            _LOGGER.error("Cannot fetch data: " + url)
        else:
            _LOGGER.debug(data)
        return data


class EvoSensor(SensorEntity):
    def __init__(self, evohaus, config):
        self._updateTime = "unknown"
        self._state = STATE_UNKNOWN
        self._evohaus = evohaus
        self._config = config
        self._total = 0
        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._config["name"]

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._config["icon"]

    @property
    def native_value(self):
        """Return the state of the device."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._config["unit"]

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the last update."""
        attrs = {"updateTime": self._updateTime}
        return attrs

    @Throttle(THROTTLE_INTERVAL)
    def update(self):
        """Get the latest data and updates the states."""
        self._evohaus.sync_meter_data()
        self.parse_data()

    @property
    def native_unit_of_measurement(self) -> str:
        """Return percentage."""
        return self._config["unit"]

    @property
    def state_class(self):
        return self._config["state_class"]

    @property
    def device_class(self):
        """Device class of this entity."""
        return self._config["device_class"]


class MeterSensor(EvoSensor):
    def __init__(self, evohaus, config):
        super().__init__(evohaus, config)

    @property
    def state_class(self):
        return self._config["state_class"]
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes of the last update."""
        attrs = super().extra_state_attributes
        attrs["meter_no"] = self._meter_no
        return attrs

    def parse_data(self):
        meter_data = self._evohaus.fetch_meter_data(self._config["description"])
        new_state = meter_data["state"]
        try:
            if float(new_state) >= float(self._state):
                self._state = new_state
        except ValueError:  # if history state does not exists
            self._state = new_state
        self._meter_no = meter_data["meter_no"]
        self._updateTime = homeassistant.util.dt.now().strftime("%H:%M")

class ElectricityMeterSensor(MeterSensor):
    def __init__(self, evohaus):
        super().__init__(evohaus, ELECTRIC_METER)

class ElectricTotalConsumptionSensor(EvoSensor):
    def __init__(self, evohaus):
        super().__init__(evohaus, TOTAL_ELECTRIC_CONSUMPTION)
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes of the last update."""
        attrs = super().extra_state_attributes
        attrs["total_cost_today"] = self._total_cost
        return attrs

    def parse_data(self):
        electric_data = self._evohaus.fetch_chart_data(self._config["query"])
        self._state = 0
        self._total_cost = 0
        
        for i in range(len(electric_data[1])):
            if i % 4 == 0:
                minute = "00"
            else:
                minute = str(int(i % 4 * 15))
            
            if electric_data[0][i] != None:
                self._state += electric_data[0][i]
                self._total_cost += electric_data[0][i] * electric_data[2][i]
                self._updateTime = str(electric_data[1][i]) + ":" + minute
        
class ElectricConsumptionSensor(EvoSensor):
    def __init__(self, evohaus):
        super().__init__(evohaus, ELECTRIC_CONSUMPTION)
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes of the last update."""
        attrs = super().extra_state_attributes
        return attrs

    def parse_data(self):
        electric_data = self._evohaus.fetch_chart_data(self._config["query"])
        self._state = 0
        
        for i in range(len(electric_data[1])):
            if i % 4 == 0:
                minute = "00"
            else:
                minute = str(int(i % 4 * 15))
            
            self._state = 0
            
            if electric_data[0][i] != None and i % 4 == 0 and i > 0:
                self._state = electric_data[0][i-1] + electric_data[0][i-2] + electric_data[0][i-3] + electric_data[0][i-4]
                self._updateTime = str(electric_data[1][i]) + ":" + minute
