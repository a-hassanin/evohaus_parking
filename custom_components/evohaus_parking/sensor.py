"""Platform for sensor integration."""
import homeassistant
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers.entity import DeviceInfo

from homeassistant.const import (
    CURRENCY_EURO,
    CURRENCY_CENT,
    UnitOfEnergy,
    UnitOfVolume
)

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

    def __init__(self, coordinator, name, icon, tech_name="", unit=None, device_class=None, state_class=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_tech_name = tech_name
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unit = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

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

class MeterSensor(EvoSensor):
    def __init__(self, coordinator, name, icon, tech_name, unit, device_class):
        super().__init__(coordinator, name, icon, tech_name, unit, device_class, SensorStateClass.TOTAL_INCREASING)

    async def async_update(self):
        """Get the latest data and update the state."""
        await super().async_update()
        meter_data = await self.coordinator.fetch_meter_data()
        meter_data_extracted = self.extract_meter_data(meter_data, self._attr_tech_name)

        self._attr_native_value = meter_data_extracted['state']
        self._attr_extra_state_attributes["meter_no"] = meter_data_extracted['meter_no']

    def extract_meter_data(self, meterData, meterType):
        rows = meterData.find_all("tr")
        row = {"state": 0, "meter_no": ""}

        for raw_row in rows:
            cols = raw_row.find_all("td")
            if not cols:
                continue

            unit = cols[0].contents[0]
            description = cols[1].contents[0].replace(" " + unit, "")
            if description == meterType:
                row["state"] = float(
                    cols[4].contents[0].replace(".", "").replace(",", ".")
                )
                row["meter_no"] = cols[2].contents[0]
                return row
            else:
                continue

        return row

class EnergyMeterSensor(MeterSensor):
    def __init__(self, coordinator, name, icon, tech_name):
        super().__init__(coordinator, name, icon, tech_name, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY)

    async def async_update(self):
        await super().async_update()

class ElectricityPriceSensor(EvoSensor):
    def __init__(self, coordinator):
        super().__init__(coordinator, "Electricity Price", "mdi:currency-eur", "", f"{CURRENCY_CENT}/{UnitOfEnergy.KILO_WATT_HOUR}", SensorDeviceClass.MONETARY)

    async def async_update(self):
        """Get the latest data and update the state."""
        await super().async_update()
        traffic_data = await self.coordinator.fetch_traffic_data()
        self._attr_native_value = round(traffic_data["currentEnergyprice"], 2)
        self._attr_extra_state_attributes["traffic_light"] = traffic_data["color"]

class ElectricityPriceEuroSensor(EvoSensor):
    def __init__(self, coordinator):
        super().__init__(coordinator, "Electricity Price Euro", "mdi:currency-eur", "", f"{CURRENCY_CENT}/{UnitOfEnergy.KILO_WATT_HOUR}", SensorDeviceClass.MONETARY)

    async def async_update(self):
        """Get the latest data and update the state."""
        await super().async_update()
        traffic_data = await self.coordinator.fetch_traffic_data()
        self._attr_native_value = round(traffic_data["currentEnergyprice"]/100, 2)
        self._attr_extra_state_attributes["traffic_light"] = traffic_data["color"]

class ElectricityMeterSensor(EnergyMeterSensor):
    def __init__(self, coordinator):
        super().__init__(coordinator, "Electricity consumption", "mdi:meter-electric-outline", "Verbrauch Strom")
