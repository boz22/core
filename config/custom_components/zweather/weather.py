"""Platform for weather integration."""
from __future__ import annotations

import logging

from homeassistant.components.weather import Forecast, WeatherEntity
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZWeatherDataCoordinator

log = logging.getLogger(__name__)

DOMAIN = "zweather"


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the weather platform."""

    log.info("Adding ZWeather entity into Weather domain")
    coordinator: ZWeatherDataCoordinator = hass.data[DOMAIN]["coordinator"]
    add_entities([ZWeather(coordinator)])
    add_entities([ZWeather(coordinator, is_hourly=False)])


class ZWeather(CoordinatorEntity[ZWeatherDataCoordinator], WeatherEntity):
    """Z Weather entity."""

    _attr_attribution = "ZWeather"
    # _attr_name = "ZWeather"
    _attr_has_entity_name = True
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR

    def __init__(
        self, coordinator: ZWeatherDataCoordinator, is_hourly: bool = True
    ) -> None:
        """Initialize ZWeather entity."""
        super().__init__(coordinator)
        self._is_hourly = is_hourly
        log.info("__init()__ called on Zweather entity")

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        if self._is_hourly is True:
            return "zweather_hourly"
        return "zweather_daily"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        if self._is_hourly is True:
            return "Z-Weather Hourly"
        return "Z-Weather Daily"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return True

    @property
    def condition(self) -> str | None:
        """Return the current condition.
        List of conditions in HA is defined here: https://www.home-assistant.io/integrations/weather/.
        """
        return self.coordinator.data.current_weather_data.get("condition")

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        return self.coordinator.data.current_weather_data.get("temperature")

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        return self.coordinator.data.current_weather_data.get("pressure")

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        return self.coordinator.data.current_weather_data.get("humidity")

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        return self.coordinator.data.current_weather_data.get("wind_speed")

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind direction."""
        return self.coordinator.data.current_weather_data.get("wind_bearing")

    @property
    def forecast(self) -> list[Forecast] | None:
        """Return the forecast array."""
        result = self.coordinator.data.hourly_forecast
        if self._is_hourly is False:
            # Return daily data
            result = self.coordinator.data.daily_forecast
            log.info("Returning daily forecast")
        else:
            log.info("Returning hourly forecast")
        return result

    @property
    def device_info(self) -> DeviceInfo:
        """Device info."""
        return DeviceInfo(
            default_name="Forecast",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={("zweather")},  # type: ignore[arg-type]
            manufacturer="boz22",
            model="Forecast",
            configuration_url="https://zegheanu.ro",
        )
