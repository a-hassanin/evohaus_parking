"""The Evohaus component."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import EvohausDataUpdateCoordinator

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Evohaus component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Evohaus from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    username = entry.data.get("username")
    password = entry.data.get("password")

    coordinator = EvohausDataUpdateCoordinator(hass, username, password)

    try:
        await coordinator.async_login()
        await coordinator.async_refresh()

        if not coordinator.last_update_success:
            raise ConfigEntryNotReady
    except Exception as e:
        raise ConfigEntryNotReady from e

    # Store the coordinator so platforms can access it
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok