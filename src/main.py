from fastapi import FastAPI, HTTPException, Request
from firebase_admin import db
from datetime import datetime
from models import SensorData
from config import init_firebase, get_timezone

app = FastAPI(title="Sensor Logger API")

@app.on_event("startup")
async def startup_event():
    init_firebase()

@app.get("/")
async def home():
    return {"message": "Sensor logger is running"}

@app.post("/api/sensor-data")
async def receive_sensor_data(sensor_data: SensorData):
    try:
        print("Received data:", sensor_data)
        tz = get_timezone()
        timestamp = datetime.now(tz).isoformat()
        
        # Convert to dict and add timestamp
        # Using .dict() for Pydantic v1 (or v2 compat), which recursively handles nested models like GPSData
        data_dict = sensor_data.dict()
        data_dict['timestamp'] = timestamp
        
        # Save to Firebase with status
        ref = db.reference(f'stations/{sensor_data.device_id}')
        
        # We replace the entire node with the new data structure
        ref.set(data_dict)

        return {"status": "success"}
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
        # Check if device exists in Firebase
        ref = db.reference(f'stations/{device_id}')
        device = ref.get()
        
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
            
        # Log wake request
        tz = get_timezone()
        wake_ref = db.reference(f'wake_requests/{device_id}')
        wake_ref.set({
            'timestamp': datetime.now(tz).isoformat(),
            'status': 'pending'
        })
        
        return {"status": "success", "message": f"Wake request sent to {device_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
