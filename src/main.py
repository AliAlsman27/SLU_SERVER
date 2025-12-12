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
        
        # Add timestamp to each reading, matching ESP32 schema
        updated_data = []
        for reading in sensor_data.data:
            # Convert to dict if it's a Pydantic model
            if hasattr(reading, "dict"):
                reading = reading.dict()
            # Only keep expected keys and add timestamp
            filtered = {
                "sensor": reading.get("sensor"),
                "value": reading.get("value"),
                "unit": reading.get("unit"),
                "timestamp": timestamp
            }
            updated_data.append(filtered)

        # Save to Firebase with status
        ref = db.reference(f'stations/{sensor_data.device_id}')
        ref.set({
            'device_id': sensor_data.device_id,
            'status': sensor_data.status,  # Add status to Firebase
            'data': updated_data,
            'timestamp': timestamp
        })

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
