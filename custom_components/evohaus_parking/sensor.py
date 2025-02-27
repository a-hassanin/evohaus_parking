"""Platform for sensor integration."""
import homeassistant
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers.entity import DeviceInfo

from homeassistant.const import (
    CURRENCY_EURO,
    CURRENCY_CENT,
    UnitOfEnergy,
    UnitOfVolume
)

import re
from .const import DOMAIN

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Evohaus sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        ElectricityPriceSensor(coordinator),
        ElectricityPriceEuroSensor(coordinator),
        ElectricityMeterSensor(coordinator),
    ]

    async_add_entities(sensors, True)


class EvoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Evo Sensor."""

    def __init__(self, coordinator, name, icon, unit=None, device_class=None, state_class=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unit = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self.entity_id = f"sensor.{name.lower().replace(' ', '_') + '_' + coordinator.residenceId.lower()}"

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self):
        return self._attr_unit

    @property
    def extra_state_attributes(self):
        self._attr_extra_state_attributes["updateTime"] = homeassistant.util.dt.now().strftime("%H:%M")
        return self._attr_extra_state_attributes

    @property
    def device_class(self):
        """Device class of this entity."""
        return self._attr_device_class

    @property
    def state_class(self):
        return self._attr_state_class

    @property
    def device_info(self):
        """Return device information about this sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, "evohaus_parking")},
            name="Evohaus Parking",
            manufacturer="Evohaus",
        )

    @callback
    def _handle_coordinator_update(self):
        self.async_write_ha_state()

class MeterSensor(EvoSensor):
    def __init__(self, coordinator, name, icon, unit, device_class):
        meter_data_extracted = self._extract_meter_data(name, coordinator.data["meter"])
        super().__init__(coordinator, name + ' ' + meter_data_extracted["parking_no"], icon, unit, device_class, SensorStateClass.TOTAL_INCREASING)

    @callback
    def _handle_coordinator_update(self):
        meter_data_extracted = self._extract_meter_data(self._attr_name, self.coordinator.data["meter"])
        if self._attr_native_value is None or meter_data_extracted["state"] > self._attr_native_value:
            self._attr_native_value = meter_data_extracted["state"]
            self._attr_extra_state_attributes["meter_no"] = meter_data_extracted['meter_no']

        super()._handle_coordinator_update()

    def _extract_parking_number(self, input_string):
        match = re.search(r'TNr\s*(\d+)', input_string)
        if match:
            return match.group(1)
        else:
            return ''
    
    def _extract_meter_data(self, parking_name, meter_data):
        rows = meter_data.find_all("tr")
        row = {"state": 0, "meter_no": ""}

        for raw_row in rows:
            cols = raw_row.find_all("td")
            if not cols:
                continue

            unit = cols[0].contents[0]
            description = cols[1].contents[0].replace(" " + unit, "")
            if "Verbrauch Strom E-Ladestation" in description:
                row["state"] = float(
                    cols[4].contents[0].replace(".", "").replace(",", ".")
                )
                row["meter_no"] = cols[2].contents[0]
                row["parking_no"] = self._extract_parking_number(description)
                return row
            else:
                continue

        return row

class EnergyMeterSensor(MeterSensor):
    def __init__(self, coordinator, name, icon):
        super().__init__(coordinator, name, icon, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY)

class ElectricityPriceSensor(EvoSensor):
    def __init__(self, coordinator):
        super().__init__(coordinator, "Electricity Price", "mdi:currency-eur", f"{CURRENCY_CENT}/{UnitOfEnergy.KILO_WATT_HOUR}", SensorDeviceClass.MONETARY)

    @callback
    def _handle_coordinator_update(self):
        self._attr_native_value = round(self.coordinator.data['traffic']["currentEnergyprice"], 2)
        self._attr_extra_state_attributes["traffic_light"] = self.coordinator.data["traffic"]["color"]
        super()._handle_coordinator_update()

class ElectricityPriceEuroSensor(EvoSensor):
    def __init__(self, coordinator):
        super().__init__(coordinator, "Electricity Price Euro", "mdi:currency-eur", f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}", SensorDeviceClass.MONETARY)

    @callback
    def _handle_coordinator_update(self):
        self._attr_native_value = round(self.coordinator.data['traffic']["currentEnergyprice"] / 100, 2)
        self._attr_extra_state_attributes["traffic_light"] = self.coordinator.data["traffic"]["color"]
        super()._handle_coordinator_update()

class ElectricityMeterSensor(EnergyMeterSensor):
    def __init__(self, coordinator):
        super().__init__(coordinator, "Electricity consumption parking", "mdi:meter-electric-outline")
