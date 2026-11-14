"""DataUpdateCoordinator for Evohaus."""
from datetime import timedelta
import async_timeout
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import aiohttp
from bs4 import BeautifulSoup
import json
from urllib.parse import urlsplit
from cachetools import TTLCache

from .const import (
    API_BASE_URL,
    API_LOGIN,
    API_LOGIN_PAGE,
    API_METER_DATA,
    API_TRAFFIC,
    DOMAIN,
    LOGIN_SUCCESS_PATH,
    THROTTLE_INTERVAL_SECONDS,
    SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

class EvohausDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Evohaus data."""

    @staticmethod
    def _clean_json_payload(text):
        """Normalize invalid unicode whitespace that can break JSON decoding."""
        cleaned = text.translate(
            str.maketrans(
                {
                    "\ufeff": "",  # UTF-8 BOM
                    "\u00a0": " ",  # non-breaking space
                    "\u202f": " ",  # narrow non-breaking space
                    "\u2007": " ",  # figure space
                    "\u2060": "",  # word joiner
                }
            )
        )
        return cleaned.strip()

    def __init__(self, hass, username, password):
        """Initialize."""
        self._username = username
        self._password = password
        self.cache = TTLCache(maxsize=1, ttl=THROTTLE_INTERVAL_SECONDS)
        self.hass = hass
        self.residenceId = username.split("_")[0]
        self._session = aiohttp.ClientSession()

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )

    async def _async_update_data(self):
        try:
            async with async_timeout.timeout(10):
                await self.async_login()
                return {"traffic": await self.fetch_traffic_data(), "meter": await self.fetch_meter_data()}

        except Exception as error:
            raise UpdateFailed(f"Error fetching data: {error}")

    async def async_login(self):
        """Log in using the session cookie and CSRF token from the login form."""
        async with self._session.get(API_BASE_URL + API_LOGIN_PAGE) as response:
            response.raise_for_status()
            login_page = BeautifulSoup(await response.text(), "html.parser")
            if response.url.path.rstrip("/") == LOGIN_SUCCESS_PATH:
                if self._is_authenticated_page(login_page):
                    return
                raise HomeAssistantError("Evohaus login failed: start page is not authenticated")

        token_input = login_page.select_one('input[name="csrf_token"]')
        token = token_input.get("value") if token_input else None
        if not isinstance(token, str) or not token:
            raise HomeAssistantError("Evohaus login page did not contain a CSRF token")

        payload = {
            "user": self._username,
            "passwort": self._password,
            "csrf_token": token,
        }
        async with self._session.post(API_BASE_URL + API_LOGIN, data=payload) as response:
            response.raise_for_status()
            if "Ihre Anmeldedaten waren nicht korrekt" in await response.text():
                raise HomeAssistantError("Evohaus login failed: credentials were rejected")

        async with self._session.get(API_BASE_URL + LOGIN_SUCCESS_PATH) as response:
            response.raise_for_status()
            start_page = BeautifulSoup(await response.text(), "html.parser")
            if response.url.path.rstrip("/") != LOGIN_SUCCESS_PATH or not self._is_authenticated_page(start_page):
                raise HomeAssistantError("Evohaus login failed: start page is not authenticated")

    @staticmethod
    def _is_authenticated_page(page):
        """Check the start page for the logout link shown to logged-in users."""
        for link in page.select("a[href]"):
            href = link.get("href")
            if isinstance(href, str) and urlsplit(href).path.rstrip("/") == "/abmelden":
                return True
        return False

    async def async_shutdown(self):
        """Close the private HTTP session."""
        await self._session.close()

    async def fetch_traffic_data(self):
        url = API_BASE_URL + API_TRAFFIC
        async with self._session.get(url) as response:
            text = await response.text()
            try:
                return json.loads(self._clean_json_payload(text))
            except json.JSONDecodeError:
                _LOGGER.warning("getTrafficLightStatus returned non-JSON response, skipping: %.100s", text)
                return {}

    async def fetch_meter_data(self):
        """Fetch the meter data."""
        url = API_BASE_URL + API_METER_DATA
        now = dt_util.now()
        today = now.strftime("%Y-%m-%d")
        payload = {"dateParam": today}
        async with self._session.post(url, data=payload) as response:
            return BeautifulSoup(await response.text(), "html.parser")
