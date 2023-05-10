"""ZWeather component."""
import datetime
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional

import aiohttp
import pytz
from typing_extensions import Self

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from homeassistant.loader import async_get_integration
from homeassistant.helpers import entity_registry as er


DOMAIN = "zweather"
log = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config):
    """Setup integration."""

    log.info("Zweather has started.")
    coordinator = ZWeatherDataCoordinator(hass)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coordinator

    # sun_integration = await async_get_integration(hass, "sun")
    # entity_registry = er.async_get(hass)
    # log.info("*********" + str(entity_registry.entities))
    # sun_entity = entity_registry.async_get("sensor.sun_next_setting")
    # sun_entity.
    # next_sunset = sun_entity.attributes.get("next_setting")

    # log.error(f"**** next sunset: " + next_sunset)

    return True


class ZWeatherData:
    """Represents the weather data and also acts as data fetcher.
    That is, it contains the logic to fetch weather from the API.
    """

    """Weather codes are defined here: https://open-meteo.com/en/docs/dwd-api#latitude=45.69&longitude=21.24&hourly=temperature_2m,weathercode
    and HA condition strings are defined here: https://www.home-assistant.io/integrations/weather/
    """
    # TODO: 0 -> map to 'sunny' during daylight and clear-night during night
    # TODO: same for code 1
    wmo_code_to_condition_map = {
        0: "sunny",
        1: "sunny",
        2: "partlycloudy",
        3: "cloudy",
        45: "fog",
        48: "fog",
        51: "rainy",
        53: "rainy",
        55: "rainy",
        56: "snowy-rainy",
        57: "snowy-rainy",
        61: "rainy",
        63: "rainy",
        65: "pouring",
        66: "snowy-rainy",
        67: "snowy-rainy",
        71: "snow",
        73: "snow",
        75: "snow",
        77: "snow",
        80: "rainy",
        81: "rainy",
        82: "rainy",
        85: "snow",
        86: "snow",
        95: "lightning-rainy",
        96: "lightning-rainy",
        99: "lightning-rainy",
    }

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the weather entity data."""
        self.hass = hass
        self._weather_data = {}
        self.current_weather_data: dict = {}
        self.daily_forecast: list[dict] = []
        self.hourly_forecast: list[dict] = []
        self._coordinates: dict[str, str] | None = None
        # Timezone: GMT + 0
        # Datetime format: ISO 8601
        # Temperature: Celsius
        # Precipitation: mm
        # Using two different urls for daily and hourly. Techinically one would have been enough which contains both
        # daily and hourly data, but I have used GMT to time in hourly data and appending MSK time instead of GMT would also change
        # processing logic for hourly.
        # Daily is more important to contain the right timezone because it might indiacate different lower temperatures during the night
        # With hourly the side effect of using GMT instead of the right timezone is that we have data for 3 hours in the past which
        # is not really an issue.
        self._rest_endpoint = "https://api.open-meteo.com/v1/dwd-icon?latitude=45.69&longitude=21.24&hourly=temperature_2m,relativehumidity_2m,rain,showers,snowfall,cloudcover_low,windspeed_10m,winddirection_10m,surface_pressure,weathercode"
        self._rest_endpoint_daily = "https://api.open-meteo.com/v1/dwd-icon?latitude=45.69&longitude=21.24&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=Europe%2FMoscow"

    def _get_current_datetime_iso(self):
        """Retrieve the current datetime in ISO 8601 format."""
        current_time = datetime.now(pytz.utc)
        current_time_iso = current_time.isoformat()
        return current_time_iso

    def _get_index_for_time(
        self, data: Dict[str, Any], ref_datetime, is_hourly=True
    ) -> Optional[int]:
        """Given a time series with separate lists for time and the rest of the attributes,
        finds the index in that list which corresponds to the given time.

        Raises:
            Exception if no data json is provided
            Exception if no reference datetime is provided

        """
        if data is None:
            raise Exception("No data json is provided")
        if ref_datetime is None:
            raise Exception("No reference datetime is provided")

        field_name = "hourly"
        slice_index = 13
        if is_hourly is False:
            field_name = "daily"
            slice_index = 10

        time_list = data[field_name]["time"]
        current_day_hour = ref_datetime[0:slice_index]
        matching_index = None
        for i, time_str in enumerate(time_list):
            if current_day_hour in time_str:
                matching_index = i
                break
        return matching_index

    def _add_timezone_information_to_datetime(
        self, datetime_iso_str: str, timezone: pytz.BaseTzInfo = pytz.utc
    ):
        """Given a datetime as a string, it will add timezone information to the date and return as string.

        If no timezone object is provided, it will use UTC.
        """
        iso_date = datetime.fromisoformat(datetime_iso_str)
        datetime_with_tz_str = str(timezone.localize(iso_date).isoformat())
        return datetime_with_tz_str

    def _get_daily_weather_for_datetime(
        self, data: Dict[str, Any], ref_datetime
    ) -> Optional[Dict[str, Any]]:
        """Returns a dictionary with daily weather data for the specified datetime."""
        # Get matching index for the time entry. Returning None if no match in data.
        matching_index = self._get_index_for_time(data, ref_datetime, is_hourly=False)
        if matching_index is None:
            return None

        log.info(f"Retrieve weather for time: {str(ref_datetime)}")
        log.info(f"Matching index: {str(matching_index)}")

        time_list = data["daily"]["time"]
        weathercode_list = data["daily"]["weathercode"]
        temp_max_list = data["daily"]["temperature_2m_max"]
        temp_min_list = data["daily"]["temperature_2m_min"]
        precip_sum_list = data["daily"]["precipitation_sum"]

        condition_dict = {}
        datetime_original = time_list[matching_index]
        condition_dict["datetime"] = self._add_timezone_information_to_datetime(
            datetime_original
        )

        condition_dict["weathercode"] = weathercode_list[matching_index]
        condition_dict["temperature"] = temp_max_list[matching_index]
        condition_dict["templow"] = temp_min_list[matching_index]
        condition_dict["precipitation"] = precip_sum_list[matching_index]
        condition_dict["condition"] = ZWeatherData.wmo_code_to_condition_map[
            weathercode_list[matching_index]
        ]

        return condition_dict

    def _get_weather_for_datetime(
        self, data: Dict[str, Any], ref_datetime
    ) -> Optional[Dict[str, Any]]:
        """Returns a dictionary with weather data for the specified datetime."""

        # Get matching index for the time entry. Returning None if no match in data.
        matching_index = self._get_index_for_time(data, ref_datetime, is_hourly=True)
        if matching_index is None:
            return None

        log.info(f"Retrieve weather for time: {str(ref_datetime)}")

        time_list = data["hourly"]["time"]
        temperature_list = data["hourly"]["temperature_2m"]
        rain_list = data["hourly"]["rain"]
        showers_list = data["hourly"]["showers"]
        snowfall_list = data["hourly"]["snowfall"]
        humidity_list = data["hourly"]["relativehumidity_2m"]
        pressure_list = data["hourly"]["surface_pressure"]
        wind_speed_list = data["hourly"]["windspeed_10m"]
        wind_bearing_list = data["hourly"]["winddirection_10m"]
        cloudcover_list = data["hourly"]["cloudcover_low"]
        weathercode_list = data["hourly"]["weathercode"]

        condition_dict = {}
        datetime_original = time_list[matching_index]
        condition_dict["datetime"] = self._add_timezone_information_to_datetime(
            datetime_original
        )

        condition_dict["temperature"] = temperature_list[matching_index]
        condition_dict["humidity"] = humidity_list[matching_index]
        condition_dict["pressure"] = pressure_list[matching_index]
        condition_dict["wind_bearing"] = wind_bearing_list[matching_index]
        condition_dict["wind_speed"] = wind_speed_list[matching_index]
        condition_dict["rain"] = rain_list[matching_index]
        condition_dict["snowfall"] = snowfall_list[matching_index]
        condition_dict["showers"] = showers_list[matching_index]
        condition_dict["precipitation"] = (
            rain_list[matching_index]
            + snowfall_list[matching_index]
            + showers_list[matching_index]
        )
        condition_dict["cloudcover"] = cloudcover_list[matching_index]
        condition_dict["condition"] = ZWeatherData.wmo_code_to_condition_map[
            weathercode_list[matching_index]
        ]

        return condition_dict

    def _get_hourly_forecast(
        self, data: Dict[str, Any], current_datetime_str: str, next_hours_count: int
    ) -> list[dict]:
        """Retrieves the hourly forecast starting with the current_datetime.
        Will retrieve for the next 'next_hours_count' number of hours.
        """
        current_datetime = datetime.fromisoformat(current_datetime_str)
        result: list[dict] = []
        for _i in range(next_hours_count):
            current_datetime += timedelta(hours=1)
            datetime_str = current_datetime.isoformat()
            cond_dict = self._get_weather_for_datetime(data, datetime_str)
            result.append(cond_dict)
        return result

    def _get_daily_forecast(
        self, data: Dict[str, Any], current_datetime_str: str
    ) -> list[dict]:
        """Retrieve daily forecast for the next 7 days."""
        current_datetime = datetime.fromisoformat(current_datetime_str)
        result: list[dict] = []
        for i in range(6):
            current_datetime += timedelta(days=1)
            datetime_str = current_datetime.isoformat()
            cond_dict = self._get_daily_weather_for_datetime(data, datetime_str)
            result.append(cond_dict)
        return result

    def _refresh_weather_data_hourly(self, data: Dict[str, Any]) -> None:
        current_datetime = self._get_current_datetime_iso()
        log.info(f"Current datetime from systen: {current_datetime}")
        log.info("Retrieve current conditions weather data")
        self.current_weather_data = self._get_weather_for_datetime(
            data, current_datetime
        )
        forecast_for_x_hours = 24
        log.info(
            f"Retrieving hourly forecast for the next {forecast_for_x_hours} hours"
        )
        self.hourly_forecast = self._get_hourly_forecast(
            data, current_datetime, next_hours_count=forecast_for_x_hours
        )

        log.info(str(self.current_weather_data))
        log.info(str(self.hourly_forecast))

    def _refresh_weather_data_daily(self, data: Dict[str, Any]) -> None:
        current_datetime = self._get_current_datetime_iso()
        log.info(f"Current datetime from systen: {current_datetime}")

        log.info(f"Retrieving daily forecast for the next days")
        self.daily_forecast = self._get_daily_forecast(data, current_datetime)

    def _refresh_current_conditions(self, data_current_conditions):
        pass

    async def fetch_data(self) -> Self:
        """Fetch data from the rest api endpoint."""
        log.info("Fetching hourly data from rest api")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._rest_endpoint) as response:
                    # response = await self.hass.async_add_executor_job(
                    #     requests.get, self._rest_endpoint
                    # )
                    if response.status == 200:
                        log.info("Successfully called weather rest api endpoint")
                        data = await response.json()
                        self._refresh_weather_data_hourly(data)
                    else:
                        log.error(
                            "Some error occurreed while calling rest api endpoint"
                        )
                        log.error("Status code is: " + str(response.status))
        except Exception as e:
            log.error("Error fetching data", e)

        log.info("Fetching daily data from rest api")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._rest_endpoint_daily) as response:
                    # response = await self.hass.async_add_executor_job(
                    #     requests.get, self._rest_endpoint
                    # )
                    if response.status == 200:
                        log.info(
                            "Successfully called weather rest api endpoint - daily"
                        )
                        data = await response.json()
                        self._refresh_weather_data_daily(data)
                    else:
                        log.error(
                            "Some error occurreed while calling rest api endpoint"
                        )
                        log.error("Status code is: " + str(response.status))
        except Exception as e:
            log.error("Error fetching data", e)

        return self


class ZWeatherDataCoordinator(DataUpdateCoordinator["ZWeatherData"]):
    """Define a data coordinator."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.weather = ZWeatherData(hass)
        super().__init__(
            hass,
            log,
            name="ZWeather",
            update_interval=timedelta(minutes=30),
        )

    async def _async_update_data(self) -> ZWeatherData:
        log.info("Called update data from coordinator")
        return await self.weather.fetch_data()
