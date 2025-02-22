"""DataUpdateCoordinator for Evohaus."""
from datetime import timedelta
import async_timeout
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from bs4 import BeautifulSoup
import json
from cachetools import TTLCache

from .const import DOMAIN, THROTTLE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

class EvohausDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Evohaus data."""

    def __init__(self, hass, username, password):
        """Initialize."""
        self._username = username
        self._password = password
        self._residenceId = username.split("_")[0]
        self._cookie = None
        self._domain = "https://ems003.enocoo.com:48889/"
        self.cache = TTLCache(maxsize=1, ttl=THROTTLE_INTERVAL_SECONDS)
        self.hass = hass

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=THROTTLE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            async with async_timeout.timeout(10):
                await self.async_login()
                await self.fetch_traffic_data()
                return await self.fetch_meter_data()
        except Exception as error:
            raise UpdateFailed(f"Error fetching data: {error}")

    async def async_login(self):
        """Login to Evohaus and store session cookies."""
        try:
            payload = {"user": self._username, "passwort": self._password}
            url = self._domain + "signinForm.php?mode=ok"
            session = async_get_clientsession(self.hass)
            async with session.get(url) as response:
                self._cookie = {"PHPSESSID": response.cookies.get("PHPSESSID")}
            async with session.post(url, data=payload, cookies=self._cookie):
                pass
            if self._cookie is None:
                raise Exception("Cannot login to Evohaus")
        except Exception as error:
            raise Exception(f"Error logging in: {error}")

    async def fetch_traffic_data(self):
        url = self._domain + "/php/getTrafficLightStatus.php"
        session = async_get_clientsession(self.hass)
        async with session.get(url, cookies=self._cookie) as response:
            return json.loads(await response.text())

    async def fetch_meter_data(self):
        """Fetch the meter data."""
        url = self._domain + "/php/newMeterTable.php"
        now = dt_util.now()  # current date and time
        today = now.strftime("%Y-%m-%d")
        payload = {"dateParam": today}
        session = async_get_clientsession(self.hass)
        async with session.post(url, data=payload, cookies=self._cookie) as response:
            return BeautifulSoup(await response.text(), "html.parser")

    async def fetch_chart_data(self, dataType):
        """Parse data."""
        now = dt_util.now()  # current date and time
        today = now.strftime("%Y-%m-%d")
        url = (
                self._domain
                + "php/getMeterDataWithParam.php?from="
                + today
                + "&intVal=Tag&mClass="
                + dataType
                + "&AreaId="
                + self._residenceId
        )
        session = async_get_clientsession(self.hass)
        async with session.get(url, cookies=self._cookie) as response:
            return json.loads(await response.text())
