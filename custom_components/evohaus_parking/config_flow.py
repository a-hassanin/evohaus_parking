"""Config flow for Evohaus integration."""
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD

class EvohausConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Evohaus."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="Evohaus", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema
        )

    async def async_step_import(self, import_data):
        """Handle import from YAML."""
        return await self.async_step_user(user_input=import_data)