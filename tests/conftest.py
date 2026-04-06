import json
import os
import pytest


@pytest.fixture
def pms():
    from app.services.pms import PMS
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "mock_hotel_data.json")
    return PMS(data_path)


@pytest.fixture
def pms_data():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "mock_hotel_data.json")
    with open(data_path) as f:
        return json.load(f)
