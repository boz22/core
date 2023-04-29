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

DOMAIN = "zweather"
log = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config):
    """Setup integration."""

    log.info("Zweather has started.")
    coordinator = ZWeatherDataCoordinator(hass)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coordinator

    return True


class ZWeatherData:
    """Represents the weather data and also acts as data fetcher.
    That is, it contains the logic to fetch weather from the API.
    """

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
        self._rest_endpoint = "https://api.open-meteo.com/v1/dwd-icon?latitude=45.69&longitude=21.24&hourly=temperature_2m,relativehumidity_2m,rain,showers,snowfall,cloudcover_low,windspeed_10m,winddirection_10m,surface_pressure"

    def _get_current_datetime_iso(self):
        """Retrieve the current datetime in ISO 8601 format."""
        current_time = datetime.now(pytz.utc)
        current_time_iso = current_time.isoformat()
        return current_time_iso

    def _get_index_for_time(self, data: Dict[str, Any], ref_datetime) -> Optional[int]:
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

        time_list = data["hourly"]["time"]
        current_day_hour = ref_datetime[0:13]
        matching_index = None
        for i, time_str in enumerate(time_list):
            if current_day_hour in time_str:
                matching_index = i
                break
        return matching_index

    def _compute_condition_string(self, data: dict):
        """Computes condition string from the weather data available for a point in time
        List of conditions in HA is defined here: https://www.home-assistant.io/integrations/weather/.
        """
        condition = None
        precipitation = data.get("precipitation")
        cloudcover = data.get("cloudcover")
        if precipitation > 0:
            condition = "rainy"
        else:
            if cloudcover < 10:
                condition = "sunny"
            elif cloudcover > 10 & cloudcover < 50:
                condition = "partlycloudy"
            else:
                condition = "cloudy"

        return condition

    def _get_weather_for_datetime(
        self, data: Dict[str, Any], ref_datetime
    ) -> Optional[Dict[str, Any]]:
        """Returns a dictionary with weather data for the specified datetime."""

        # Get matching index for the time entry. Returning None if no match in data.
        matching_index = self._get_index_for_time(data, ref_datetime)
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

        condition_dict = {}
        # add datetime with timezone information
        datetime_original = time_list[matching_index]
        log.info(f"Original datetime as returned from dataset: {datetime_original}")

        iso_date = datetime.fromisoformat(datetime_original)
        # condition_dict["datetime"] = str(iso_date.astimezone().isoformat())
        condition_dict["datetime"] = str(pytz.utc.localize(iso_date).isoformat())
        log.info(f"datetime after some conversion: {condition_dict['datetime']}")

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
        condition_dict["condition"] = self._compute_condition_string(condition_dict)
        condition_dict["templow"] = 10

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
        self, data: Dict[str, Any], current_datetime_str: str, next_days_count: int
    ) -> list[dict]:
        """Retrieve daily forecast for the next days."""
        current_datetime = datetime.fromisoformat(current_datetime_str)
        result: list[dict] = []
        for _i in range(next_days_count):
            current_datetime += timedelta(days=1)
            datetime_str = current_datetime.isoformat()
            cond_dict = self._get_weather_for_datetime(data, datetime_str)
            cond_dict["templow"] = 10
            result.append(cond_dict)
        return result

    def _refresh_weather_data(self, data: Dict[str, Any]) -> None:
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

        forecast_for_x_days = 6
        log.info(f"Retrieving daily forecast for the next {forecast_for_x_days} days")
        self.daily_forecast = self._get_daily_forecast(
            data, current_datetime, next_days_count=forecast_for_x_days
        )

        log.info(str(self.current_weather_data))
        log.info(str(self.hourly_forecast))

    def _refresh_current_conditions(self, data_current_conditions):
        pass

    async def fetch_data(self) -> Self:
        """Fetch data from the rest api endpoint."""
        log.info("Fetching data from rest api")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._rest_endpoint) as response:
                    # response = await self.hass.async_add_executor_job(
                    #     requests.get, self._rest_endpoint
                    # )
                    if response.status == 200:
                        log.info("Successfully called weather rest api endpoint")
                        data = await response.json()
                        self._refresh_weather_data(data)
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
