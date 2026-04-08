from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from firebase_admin import db

from src.config import get_timezone, init_firebase, init_supabase
from src.models import SensorData

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware"
FIRMWARE_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Sensor Logger API")
app.mount("/firmware", StaticFiles(directory=str(FIRMWARE_DIR)), name="firmware")


def _parse_version(version: str | None) -> list[int]:
    if not version:
        return []

    parts: list[int] = []
    for part in str(version).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return parts


def compare_versions(current_version: str | None, target_version: str | None) -> int:
    current_parts = _parse_version(current_version)
    target_parts = _parse_version(target_version)
    max_len = max(len(current_parts), len(target_parts), 1)

    current_parts.extend([0] * (max_len - len(current_parts)))
    target_parts.extend([0] * (max_len - len(target_parts)))

    for current_part, target_part in zip(current_parts, target_parts):
        if current_part != target_part:
            return 1 if current_part > target_part else -1
    return 0


def clear_ota_metadata(device_id: str) -> None:
    db.reference(f"stations/{device_id}/ota").set({"enabled": False})


def build_ota_response(ota_config: dict[str, Any] | None, firmware_version: str | None) -> dict[str, Any]:
    ota_config = ota_config or {}
    enabled = bool(ota_config.get("enabled"))
    target_version = ota_config.get("target_version")
    url = ota_config.get("url")
    sha256 = ota_config.get("sha256")
    size_bytes = ota_config.get("size_bytes")

    has_artifact = bool(target_version and url)
    is_newer = True if not firmware_version else compare_versions(firmware_version, target_version) < 0
    available = enabled and has_artifact and is_newer

    return {
        "available": available,
        "target_version": target_version if available else None,
        "url": url if available else None,
        "sha256": sha256 if available else None,
        "size_bytes": size_bytes if available else None,
    }


@app.on_event("startup")
async def startup_event():
    init_firebase()
    app.state.supabase = init_supabase()


@app.get("/")
async def home():
    return {"message": "Sensor logger is running"}


@app.post("/api/sensor-data")
async def receive_sensor_data(sensor_data: SensorData):
    try:
        print("Received data:", sensor_data)
        tz = get_timezone()
        timestamp = datetime.now(tz).isoformat()

        if hasattr(sensor_data, "model_dump"):
            data_dict = sensor_data.model_dump(exclude_none=True)
        else:
            data_dict = sensor_data.dict(exclude_none=True)
        data_dict["timestamp"] = timestamp

        ref = db.reference(f"stations/{sensor_data.device_id}")
        ref.update(data_dict)

        ota_ref = db.reference(f"stations/{sensor_data.device_id}/ota")
        ota_config = ota_ref.get() or {}
        target_version = ota_config.get("target_version")
        if (
            sensor_data.firmware_version
            and target_version
            and compare_versions(sensor_data.firmware_version, target_version) >= 0
        ):
            clear_ota_metadata(sensor_data.device_id)

        try:
            if hasattr(app.state, "supabase") and app.state.supabase:
                app.state.supabase.table("sensor_data").insert(data_dict).execute()
        except Exception as e_sup:
            print(f"Supabase error: {e_sup}")

        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/{device_id}/ota")
async def get_device_ota(device_id: str, firmware_version: str | None = None):
    try:
        ota_config = db.reference(f"stations/{device_id}/ota").get() or {}
        return build_ota_response(ota_config, firmware_version)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sensor-data/debug")
async def debug_sensor_data(request: Request):
    try:
        data = await request.json()
        print("Raw received JSON:", data)
        return {"received": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/wake/{device_id}")
async def wake_device(device_id: str):
    try:
        ref = db.reference(f"stations/{device_id}")
        device = ref.get()

        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")

        tz = get_timezone()
        wake_ref = db.reference(f"wake_requests/{device_id}")
        wake_ref.set({
            "timestamp": datetime.now(tz).isoformat(),
            "status": "pending"
        })

        return {"status": "success", "message": f"Wake request sent to {device_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))