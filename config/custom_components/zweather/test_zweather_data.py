import datetime
import json
from unittest.mock import MagicMock

import pytest

from . import ZWeatherData


@pytest.fixture(name="zweather_data")
def _zweather_data():
    return ZWeatherData(None)


@pytest.fixture(name="hourly_json")
def _hourly_json():
    with open("test_hourly.json", encoding="utf-8") as file:
        content = file.read()
        data = json.loads(content)
    return data


def test_data_fetch(zweather_data, hourly_json):
    mock_current_time = datetime.datetime(2023, 4, 21, 2, 24, 00).isoformat()
    zweather_data._get_current_datetime_iso = MagicMock(return_value=mock_current_time)
    zweather_data._refresh_weather_data(hourly_json)
    current_data = zweather_data.current_weather_data
    assert current_data["datetime"] == "2023-04-21T02:00:00+00:00"
    assert current_data["temperature"] == 7.8
    assert current_data["humidity"] == 89
    assert current_data["rain"] == 0.00


def test_hourly_forecast(zweather_data, hourly_json):
    mock_current_time = datetime.datetime(2023, 4, 21, 2, 24, 00).isoformat()
    zweather_data._get_current_datetime_iso = MagicMock(return_value=mock_current_time)
    zweather_data._refresh_weather_data(hourly_json)
    hourly_data = zweather_data.hourly_forecast

    assert hourly_data[2]["temperature"] == 7.3
    assert hourly_data[2]["wind_bearing"] == 345
    assert len(hourly_data) == 24
    print(hourly_data)
