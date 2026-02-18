import firebase_admin
from firebase_admin import credentials, db
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation
import json
import os
from pathlib import Path

# --- Configuration ---
DATABASE_URL = "https://slu-project-3bc4e-default-rtdb.firebaseio.com/"
# Change this to your actual device ID
DEFAULT_DEVICE_ID = "ESP32_001" 

def init_firebase():
    """Initialize Firebase connection"""
    if not firebase_admin._apps:
        # Try different paths for credentials
        possible_cred_paths = [
            Path(__file__).parent.parent / 'firebase-credentials.json',
            Path(__file__).parent / 'firebase-credentials.json',
            Path.home() / 'Downloads' / 'firebase-credentials.json',
            Path('firebase-credentials.json')
        ]
        
        cred_path = None
        for p in possible_cred_paths:
            if p.exists():
                cred_path = p
                break
        
        if not cred_path:
            # Check environment variable
            cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
            if cred_json:
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
            else:
                print("Error: firebase-credentials.json not found.")
                print("Please place it in the project root or set FIREBASE_CREDENTIALS_JSON.")
                return False
        else:
            print(f"Using credentials from: {cred_path}")
            cred = credentials.Certificate(str(cred_path))
            
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
    return True

class FirebaseHeatmapVisualizer:
    def __init__(self, device_id):
        self.device_id = device_id
        self.sensor1_data = np.zeros((8, 8))
        self.sensor2_data = np.zeros((8, 8))
        self.matrix_total = np.zeros((8, 8))
        self.levels = {"s1": 0.0, "s2": 0.0, "total": 0.0}
        self.timestamp = "Never"
        self.battery = 0
        
        self.setup_plot()
        
    def setup_plot(self):
        self.fig, (self.ax1, self.ax2, self.ax3) = plt.subplots(1, 3, figsize=(18, 6))
        self.fig.suptitle(f'Firebase Real-time Matrices: {self.device_id}', fontsize=16)
        
        # Color limits for heatmaps (adjust based on your sensor range)
        self.vmin, self.vmax = 0, 2000 
        
    def fetch_data(self):
        """Fetch latest data from Firebase"""
        try:
            ref = db.reference(f'stations/{self.device_id}')
            data = ref.get()
            
            if data:
                # Update attributes
                def process_matrix(matrix_list):
                    if not matrix_list: return None
                    arr = np.array(matrix_list)
                    size = int(np.sqrt(len(arr)))
                    if size * size == len(arr):
                        return arr.reshape(size, size)
                    return None

                m1 = process_matrix(data.get('matrix_sensor_1'))
                if m1 is not None: self.sensor1_data = m1
                
                m2 = process_matrix(data.get('matrix_sensor_2'))
                if m2 is not None: self.sensor2_data = m2
                
                mt = process_matrix(data.get('matrix_total'))
                if mt is not None: self.matrix_total = mt
                
                self.levels["s1"] = data.get('level_sensor_1', 0.0)
                self.levels["s2"] = data.get('level_sensor_2', 0.0)
                self.levels["total"] = data.get('total_level', 0.0)
                self.timestamp = data.get('timestamp', 'N/A')
                self.battery = data.get('battery', 0)
                return True
        except Exception as e:
            print(f"Error fetching data: {e}")
        return False

    def draw_heatmap(self, ax, data, title, level, vmin=None, vmax=None, cmap='jet_r'):
        ax.clear()
        # Rotate data if needed (adjust based on physical mounting)
        # Using rot90(data, 2) for 180 degrees as in your serial script
        data_rotated = np.rot90(data, 2)
        rows, cols = data_rotated.shape
        
        # Use default instance values if not provided
        v_min = vmin if vmin is not None else self.vmin
        v_max = vmax if vmax is not None else self.vmax
        
        im = ax.imshow(data_rotated, cmap=cmap, vmin=v_min, vmax=v_max, 
                      interpolation='nearest', aspect='auto')
        
        # Annotate with values
        for i in range(rows):
            for j in range(cols):
                val = data_rotated[i, j]
                # Determine text color based on background intensity
                # For jet_r: 0 (red) is dark, 2000 (blue) is light? No, jet is blue(0)->red(max).
                # Simple logic for text contrast
                norm_val = (val - v_min) / (v_max - v_min) if v_max > v_min else 0
                text_color = "white" if (cmap.endswith('_r') and norm_val < 0.5) or (not cmap.endswith('_r') and norm_val > 0.5) else "black"
                
                ax.text(j, i, f'{int(val)}', ha="center", va="center", 
                        color=text_color, 
                        fontsize=10 if rows <= 4 else 8)
        
        ax.set_title(f"{title}\nLevel: {level:.1f}%")
        ax.axis('off')

    def update(self, frame):
        if self.fetch_data():
            # Individual sensors: 0-2000mm, jet_r (red for close/full)
            self.draw_heatmap(self.ax1, self.sensor1_data, "Sensor 1 (Distances)", self.levels["s1"], 
                             vmin=0, vmax=2000, cmap='jet_r')
            self.draw_heatmap(self.ax2, self.sensor2_data, "Sensor 2 (Distances)", self.levels["s2"], 
                             vmin=0, vmax=2000, cmap='jet_r')
            
            # Total matrix: 0-100%, jet (red for 100%/full)
            self.draw_heatmap(self.ax3, self.matrix_total, "Total Matrix (Percentage)", self.levels["total"], 
                             vmin=0, vmax=100, cmap='jet')
            
            self.fig.canvas.manager.set_window_title(f"Last Update: {self.timestamp} | Battery: {self.battery}mV")
        
    def run(self):
        ani = FuncAnimation(self.fig, self.update, interval=1000, cache_frame_data=False)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.show()

if __name__ == "__main__":
    if init_firebase():
        # You can prompt for device ID or use the default
        device_id = input(f"Enter Device ID [default: {DEFAULT_DEVICE_ID}]: ") or DEFAULT_DEVICE_ID
        viz = FirebaseHeatmapVisualizer(device_id)
        viz.run()
