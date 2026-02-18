import firebase_admin
from firebase_admin import credentials, db
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib import cm
import json
import os
from pathlib import Path

# --- Configuration ---
DATABASE_URL = "https://slu-project-3bc4e-default-rtdb.firebaseio.com/"
DEFAULT_DEVICE_ID = "ESP32_001"

# Basket Dimensions (mm) - from your sketch
BASKET_TOP_WIDTH = 2170      # Top width
BASKET_BOTTOM_WIDTH = 1324   # Bottom width (c)
BASKET_LEFT_HEIGHT = 1270    # Left side height
BASKET_RIGHT_HEIGHT = 1490   # Right side height
BASKET_DEPTH = 1000          # Assumed depth (adjust as needed)

# Scaling factor to make visualization manageable
SCALE = 0.001  # Convert mm to meters for display


def init_firebase():
    """Initialize Firebase connection"""
    if not firebase_admin._apps:
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


class Basket3DVisualizer:
    def __init__(self, device_id):
        self.device_id = device_id
        self.matrix_total = np.zeros((8, 8))
        self.total_level = 0.0
        self.timestamp = "Never"
        self.battery = 0
        
        # Basket dimensions (scaled)
        self.top_w = BASKET_TOP_WIDTH * SCALE
        self.bottom_w = BASKET_BOTTOM_WIDTH * SCALE
        self.left_h = BASKET_LEFT_HEIGHT * SCALE
        self.right_h = BASKET_RIGHT_HEIGHT * SCALE
        self.depth = BASKET_DEPTH * SCALE
        
        # Maximum bar height (based on basket height)
        self.max_bar_height = max(self.left_h, self.right_h) * 0.9
        
        self.setup_plot()
        
    def setup_plot(self):
        """Setup the 3D plot"""
        self.fig = plt.figure(figsize=(14, 10))
        self.ax = self.fig.add_subplot(111, projection='3d')
        self.fig.suptitle(f'3D Basket Visualization: {self.device_id}', fontsize=16, fontweight='bold')
        
    def fetch_data(self):
        """Fetch latest data from Firebase"""
        try:
            ref = db.reference(f'stations/{self.device_id}')
            data = ref.get()
            
            if data:
                def process_matrix(matrix_list):
                    if not matrix_list:
                        return None
                    arr = np.array(matrix_list)
                    size = int(np.sqrt(len(arr)))
                    if size * size == len(arr):
                        return arr.reshape(size, size)
                    return None
                
                mt = process_matrix(data.get('matrix_total'))
                if mt is not None:
                    self.matrix_total = mt
                
                self.total_level = data.get('total_level', 0.0)
                self.timestamp = data.get('timestamp', 'N/A')
                self.battery = data.get('battery', 0)
                return True
        except Exception as e:
            print(f"Error fetching data: {e}")
        return False
    
    def get_basket_vertices(self):
        """
        Calculate the 8 vertices of the trapezoidal basket.
        The basket has:
        - Wider top (top_w)
        - Narrower bottom (bottom_w)
        - Left side height (left_h)
        - Right side height (right_h)
        
        Coordinate system: X=width, Y=depth, Z=height (vertical)
        """
        # Calculate offsets for the trapezoidal shape
        top_half = self.top_w / 2
        bottom_half = self.bottom_w / 2
        d_half = self.depth / 2
        
        # Vertices: [x, y, z] where Z is height (vertical)
        # Bottom vertices (z=0, on the ground)
        v0 = [-bottom_half, -d_half, 0]           # back-left bottom
        v1 = [bottom_half, -d_half, 0]            # back-right bottom
        v2 = [bottom_half, d_half, 0]             # front-right bottom
        v3 = [-bottom_half, d_half, 0]            # front-left bottom
        
        # Top vertices (heights vary along Z axis)
        # Left side uses left_h, right side uses right_h
        v4 = [-top_half, -d_half, self.left_h]    # back-left top
        v5 = [top_half, -d_half, self.right_h]    # back-right top
        v6 = [top_half, d_half, self.right_h]     # front-right top
        v7 = [-top_half, d_half, self.left_h]     # front-left top
        
        return np.array([v0, v1, v2, v3, v4, v5, v6, v7])
    
    def draw_basket(self):
        """Draw the basket wireframe"""
        vertices = self.get_basket_vertices()
        
        # Define the 6 faces of the basket
        faces = [
            [vertices[0], vertices[1], vertices[2], vertices[3]],  # Bottom
            [vertices[4], vertices[5], vertices[6], vertices[7]],  # Top (open)
            [vertices[0], vertices[1], vertices[5], vertices[4]],  # Back
            [vertices[2], vertices[3], vertices[7], vertices[6]],  # Front
            [vertices[0], vertices[3], vertices[7], vertices[4]],  # Left
            [vertices[1], vertices[2], vertices[6], vertices[5]],  # Right
        ]
        
        # Draw basket edges (wireframe style)
        edges = [
            # Bottom edges
            (0, 1), (1, 2), (2, 3), (3, 0),
            # Top edges
            (4, 5), (5, 6), (6, 7), (7, 4),
            # Vertical edges
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        
        for e in edges:
            xs = [vertices[e[0]][0], vertices[e[1]][0]]
            ys = [vertices[e[0]][1], vertices[e[1]][1]]
            zs = [vertices[e[0]][2], vertices[e[1]][2]]
            self.ax.plot(xs, ys, zs, color='#8B4513', linewidth=3)  # Brown basket color
        
        # Optional: Add semi-transparent bottom
        bottom_face = Poly3DCollection([faces[0]], alpha=0.2, facecolor='#D2691E', edgecolor='#8B4513')
        self.ax.add_collection3d(bottom_face)
    
    def get_bar_position(self, row, col, grid_size=8):
        """
        Calculate the position of a bar within the trapezoidal basket.
        Maps grid position to actual basket coordinates.
        Coordinate system: X=width, Y=depth, Z=height (vertical)
        """
        # Normalize position (0 to 1)
        x_norm = (col + 0.5) / grid_size  # 0.5 to center in cell
        y_norm = (row + 0.5) / grid_size
        
        # Calculate max height at this position (interpolate between left and right)
        height_at_pos = self.left_h + x_norm * (self.right_h - self.left_h)
        
        # Calculate width at different heights (bottom is narrower)
        # Place bars at the bottom of the basket (z=0)
        bar_base_z = 0
        
        # At the bottom, use bottom width
        half_width = self.bottom_w / 2
        half_depth = self.depth / 2
        
        # Map to actual coordinates (X=width, Y=depth, Z=height)
        x = -half_width + x_norm * self.bottom_w
        y = -half_depth + y_norm * self.depth
        
        return x, y, bar_base_z, height_at_pos
    
    def draw_surface(self):
        """Draw a perfectly smooth 3D surface using cubic interpolation"""
        from scipy import ndimage
        
        # Upscale factor for smoothness (8x8 -> 64x64)
        zoom_factor = 8
        original_size = self.matrix_total.shape[0]
        new_size = original_size * zoom_factor
        
        # Use cubic spline interpolation (order=3) to upscale the matrix
        # This creates smooth curves between points while preserving peaks better than simple smoothing
        smoothed_matrix = ndimage.zoom(self.matrix_total, zoom_factor, order=3)
        # Ensure values stay in 0-100 range after interpolation
        smoothed_matrix = np.clip(smoothed_matrix, 0, 100)
        
        # Create coordinate grids for the high-resolution surface
        half_width = self.bottom_w / 2
        half_depth = self.depth / 2
        
        # High resolution X and Y
        x_high = np.linspace(-half_width, half_width, new_size)
        y_high = np.linspace(-half_depth, half_depth, new_size)
        X_high, Y_high = np.meshgrid(x_high, y_high)
        
        # Calculate Z heights for the high-res surface
        Z_high = (smoothed_matrix / 100.0) * self.max_bar_height
        Z_high = np.maximum(Z_high, 0.005) # Min height
        
        # Draw the smooth surface
        # Using the standard cmap parameter for automatic color mapping on upscaled data
        surf = self.ax.plot_surface(X_high, Y_high, Z_high, 
                                     cmap='jet',
                                     vmin=0, vmax=max(10, self.matrix_total.max()),
                                     linewidth=0,
                                     antialiased=True,
                                     alpha=0.8,
                                     shade=True)
        
        # Draw vertical walls (sides) using the high-res data for a perfect fit
        self.draw_surface_sides(X_high, Y_high, Z_high, plt.colormaps['jet'], plt.Normalize(0, 100))
        
        # Add labels based on the original data so labels don't move
        self.add_surface_labels()
    
    def draw_surface_sides(self, X, Y, Z, cmap, norm):
        """Draw the side walls connecting the surface to the ground (high-res)"""
        rows, cols = Z.shape
        
        # We'll collect all polygons and add them at once for better performance
        polys = []
        
        # Front edge (y is min)
        for c in range(cols - 1):
            verts = [[(X[0, c], Y[0, c], 0), (X[0, c+1], Y[0, c+1], 0), 
                      (X[0, c+1], Y[0, c+1], Z[0, c+1]), (X[0, c], Y[0, c], Z[0, c])]]
            color = cmap(norm( (Z[0, c] + Z[0, c+1]) / 2 / self.max_bar_height * 100 ))
            polys.append(Poly3DCollection(verts, facecolor=color, alpha=0.8, linewidth=0))
            
        # Back edge (y is max)
        for c in range(cols - 1):
            verts = [[(X[-1, c], Y[-1, c], 0), (X[-1, c+1], Y[-1, c+1], 0), 
                      (X[-1, c+1], Y[-1, c+1], Z[-1, c+1]), (X[-1, c], Y[-1, c], Z[-1, c])]]
            color = cmap(norm( (Z[-1, c] + Z[-1, c+1]) / 2 / self.max_bar_height * 100 ))
            polys.append(Poly3DCollection(verts, facecolor=color, alpha=0.8, linewidth=0))
            
        # Left edge (x is min)
        for r in range(rows - 1):
            verts = [[(X[r, 0], Y[r, 0], 0), (X[r+1, 0], Y[r+1, 0], 0), 
                      (X[r+1, 0], Y[r+1, 0], Z[r+1, 0]), (X[r, 0], Y[r, 0], Z[r, 0])]]
            color = cmap(norm( (Z[r, 0] + Z[r+1, 0]) / 2 / self.max_bar_height * 100 ))
            polys.append(Poly3DCollection(verts, facecolor=color, alpha=0.8, linewidth=0))
            
        # Right edge (x is max)
        for r in range(rows - 1):
            verts = [[(X[r, -1], Y[r, -1], 0), (X[r+1, -1], Y[r+1, -1], 0), 
                      (X[r+1, -1], Y[r+1, -1], Z[r+1, -1]), (X[r, -1], Y[r, -1], Z[r, -1])]]
            color = cmap(norm( (Z[r, -1] + Z[r+1, -1]) / 2 / self.max_bar_height * 100 ))
            polys.append(Poly3DCollection(verts, facecolor=color, alpha=0.8, linewidth=0))

        for p in polys:
            self.ax.add_collection3d(p)
    
    def add_surface_labels(self):
        """Add percentage labels for all cells with significant values"""
        grid_size = self.matrix_total.shape[0]
        half_width = self.bottom_w / 2
        half_depth = self.depth / 2
        
        # Show labels for ALL cells with value > 15%
        for row in range(grid_size):
            for col in range(grid_size):
                percentage = self.matrix_total[row, col]
                
                if percentage > 15:  # Only show labels for significant values
                    x = -half_width + (col + 0.5) / grid_size * self.bottom_w
                    y = -half_depth + (row + 0.5) / grid_size * self.depth
                    z = (percentage / 100.0) * self.max_bar_height + 0.03
                    
                    # Different styling for high values
                    if percentage >= 80:
                        fontsize = 10
                        bgcolor = 'red'
                        textcolor = 'white'
                    elif percentage >= 50:
                        fontsize = 9
                        bgcolor = 'orange'
                        textcolor = 'black'
                    else:
                        fontsize = 8
                        bgcolor = 'white'
                        textcolor = 'black'
                    
                    self.ax.text(x, y, z, f'{int(percentage)}%', 
                                ha='center', va='bottom', fontsize=fontsize, fontweight='bold',
                                color=textcolor,
                                bbox=dict(boxstyle='round,pad=0.2', facecolor=bgcolor, alpha=0.8))
    
    def update(self, frame):
        """Update the visualization"""
        self.ax.clear()
        
        if self.fetch_data():
            # Draw the basket frame
            self.draw_basket()
            
            # Draw the smooth surface
            self.draw_surface()
            
            # Set labels and title (X=width, Y=depth, Z=height)
            self.ax.set_xlabel('Width (m)', fontsize=10)
            self.ax.set_ylabel('Depth (m)', fontsize=10)
            self.ax.set_zlabel('Height (m)', fontsize=10)
            
            # Set axis limits
            max_dim = max(self.top_w, self.depth, max(self.left_h, self.right_h))
            self.ax.set_xlim([-max_dim * 0.7, max_dim * 0.7])
            self.ax.set_ylim([-max_dim * 0.7, max_dim * 0.7])
            self.ax.set_zlim([0, max_dim * 1.2])  # Height starts from ground
            
            # Add info text
            info_text = f"Total Level: {self.total_level:.1f}% | Battery: {self.battery}% | Updated: {self.timestamp}"
            self.ax.text2D(0.5, 0.02, info_text, transform=self.ax.transAxes, 
                          ha='center', fontsize=10, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            # Add color bar reference
            self.add_colorbar_legend()
            
            # Set viewing angle (looking down at basket from above-front)
            self.ax.view_init(elev=30, azim=-60)
            
    def add_colorbar_legend(self):
        """Add a simple legend showing color mapping"""
        # Create legend for color scale (no emoji to avoid font issues)
        legend_text = "Color Scale: [BLUE] 0% ============ 100% [RED]"
        self.ax.text2D(0.5, 0.97, legend_text, transform=self.ax.transAxes, 
                      ha='center', fontsize=10, fontweight='bold')
    
    def run(self):
        """Run the animation"""
        ani = FuncAnimation(self.fig, self.update, interval=2000, cache_frame_data=False)
        plt.tight_layout()
        plt.show()


def demo_mode():
    """Run with demo data (no Firebase required)"""
    print("Running in DEMO mode with random data...")
    
    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_subplot(111, projection='3d')
    fig.suptitle('3D Basket Visualization (DEMO MODE)', fontsize=16, fontweight='bold')
    
    viz = Basket3DVisualizer("DEMO")
    
    def update(frame):
        ax.clear()
        
        # Generate random demo data
        viz.matrix_total = np.random.uniform(0, 100, (8, 8))
        viz.total_level = np.mean(viz.matrix_total)
        viz.timestamp = "DEMO"
        viz.battery = 4200
        
        viz.ax = ax
        viz.draw_basket()
        viz.draw_surface()
        
        # Set labels (X=width, Y=depth, Z=height)
        max_dim = max(viz.top_w, viz.depth, max(viz.left_h, viz.right_h))
        ax.set_xlabel('Width (m)', fontsize=10)
        ax.set_ylabel('Depth (m)', fontsize=10)
        ax.set_zlabel('Height (m)', fontsize=10)
        ax.set_xlim([-max_dim * 0.7, max_dim * 0.7])
        ax.set_ylim([-max_dim * 0.7, max_dim * 0.7])
        ax.set_zlim([0, max_dim * 1.2])  # Height from ground up
        
        info_text = f"Total Level: {viz.total_level:.1f}% | Battery: {viz.battery}mV"
        ax.text2D(0.5, 0.02, info_text, transform=ax.transAxes, 
                  ha='center', fontsize=10, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        ax.view_init(elev=30, azim=-60 + frame * 2)  # Rotate view in demo
    
    ani = FuncAnimation(fig, update, interval=2000, cache_frame_data=False)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    print("=" * 50)
    print("  3D BASKET VISUALIZATION")
    print("=" * 50)
    print("\nBasket Dimensions (from image):")
    print(f"  Top Width: {BASKET_TOP_WIDTH}mm")
    print(f"  Bottom Width: {BASKET_BOTTOM_WIDTH}mm")
    print(f"  Left Height: {BASKET_LEFT_HEIGHT}mm")
    print(f"  Right Height: {BASKET_RIGHT_HEIGHT}mm")
    print(f"  Depth: {BASKET_DEPTH}mm (estimated)")
    print()
    
    mode = input("Select mode:\n  1. Live Firebase data\n  2. Demo mode (random data)\nChoice [1/2]: ").strip()
    
    if mode == "2":
        demo_mode()
    else:
        if init_firebase():
            device_id = input(f"Enter Device ID [default: {DEFAULT_DEVICE_ID}]: ") or DEFAULT_DEVICE_ID
            viz = Basket3DVisualizer(device_id)
            viz.run()
