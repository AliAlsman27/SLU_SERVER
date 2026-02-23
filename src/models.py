from typing import List, Optional, Union
from pydantic import BaseModel
from datetime import datetime

class GPSData(BaseModel):
    lat: float
    lon: float

class SensorData(BaseModel):
    device_id: str
    status: str
    basket_size: str
    matrix_sensor_1: List[int]
    level_sensor_1: float
    matrix_sensor_2: List[int]
    level_sensor_2: float
    matrix_total: List[int]
    total_level: float
    gps: Optional[GPSData] = None
    battery: int
    vbat_mv: Optional[int] = None
    reset_reason: Optional[int] = None
    wakeup_count: Optional[int] = None
    slave_used: Optional[bool] = None

