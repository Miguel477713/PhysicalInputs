import serial
import json
import threading
import time
import numpy as np
from collections import deque

# --- CONFIGURACIÓN DE RED Y HARDWARE ---
PORT_CANDIDATES = ["/dev/serial0", "/dev/ttyAMA0", "/dev/ttyUSB0"]
BAUD = 115200
RECONNECT_DELAY_S = 2

# --- CONFIGURACIÓN DE NODOS (6m x 10m) ---
# n=3.8 para Nodos 3 y 4 debido a los obstáculos fijos detectados en tus logs
CONFIG_NODOS = {
    1: {"pos": np.array([0, 6]),  "A": -48, "n": 3.0, "weight": 1.0},
    2: {"pos": np.array([10, 6]), "A": -42, "n": 2.8, "weight": 1.2},
    3: {"pos": np.array([10, 0]), "A": -53, "n": 3.6, "weight": 0.7},
    4: {"pos": np.array([0, 0]),  "A": -54, "n": 3.8, "weight": 0.6},
    5: {"pos": np.array([5, 0]),  "A": -54, "n": 3.0, "weight": 1.0}
}

# --- ESTRUCTURAS DE DATOS ---
data_store = {i: {"rssi": None, "t": 0} for i in CONFIG_NODOS.keys()}
buffers_rssi = {i: deque(maxlen=5) for i in CONFIG_NODOS.keys()}
lock = threading.Lock()

# --- CLASE FILTRO DE KALMAN 2D ---
class KalmanIndoor:
    def __init__(self):
        self.x = np.array([5, 3, 0, 0]) # Estado inicial: x, y, vx, vy
        self.P = np.eye(4) * 5.0
        self.F = np.array([[1, 0, 0.25, 0], [0, 1, 0, 0.25], [0, 0, 1, 0], [0, 0, 0, 1]])
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        self.R = np.eye(2) * 1.5  # Desconfianza en la medición por ruido
        self.Q = np.eye(4) * 0.05 # Confianza en el modelo de movimiento

    def update(self, z):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        if z is not None:
            S = self.H @ self.P @ self.H.T + self.R
            K = self.P @ self.H.T @ np.linalg.inv(S)
            self.x = self.x + K @ (z - self.H @ self.x)
            self.P = (np.eye(4) - K @ self.H) @ self.P
        return self.x[0], self.x[1]

# --- FUNCIONES MATEMÁTICAS ---
def rssi_to_meters(node_id, rssi):
    c = CONFIG_NODOS[node_id]
    rssi_clamped = max(rssi, -85)
    return 10 ** ((c["A"] - rssi_clamped) / (10 * c["n"]))

def weighted_trilateration(node_distances):
    active_ids = list(node_distances.keys())
    if len(active_ids) < 3: return None
    
    A, b, W = [], [], []
    p_ref = CONFIG_NODOS[active_ids[0]]["pos"]
    d_ref = node_distances[active_ids[0]]

    for i in range(1, len(active_ids)):
        id_i = active_ids[i]
        p_i, weight = CONFIG_NODOS[id_i]["pos"], CONFIG_NODOS[id_i]["weight"]
        d_i = node_distances[id_i]
        
        A.append(2 * (p_i - p_ref))
        b.append(d_ref**2 - d_i**2 + np.sum(p_i**2) - np.sum(p_ref**2))
        W.append(weight)
    
    try:
        Aw, bw = np.diag(W) @ np.array(A), np.diag(W) @ np.array(b)
        pos, _, _, _ = np.linalg.lstsq(Aw, bw, rcond=None)
        return np.clip(pos, [0, 0], [10, 6])
    except: return None

# --- HILOS DE EJECUCIÓN ---
def serial_reader():
    while True:
        ser = None
        for port in PORT_CANDIDATES:
            try:
                ser = serial.Serial(port, BAUD, timeout=1)
                print(f"Conectado a {port}")
                break
            except: continue
        
        if not ser:
            time.sleep(RECONNECT_DELAY_S)
            continue

        try:
            while True:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if not line: continue
                try:
                    packet = json.loads(line)
                    node_id, rssi = packet['n'], packet['r']
                    with lock:
                        if node_id in data_store:
                            buffers_rssi[node_id].append(rssi)
                            data_store[node_id]["rssi"] = np.median(buffers_rssi[node_id])
                            data_store[node_id]["t"] = time.time()
                except: continue
        except:
            print("Reconectando serial...")
        finally:
            if ser: ser.close()
        time.sleep(RECONNECT_DELAY_S)

def position_calculator():
    kf = KalmanIndoor()
    print("Iniciando cálculo de posición...")
    while True:
        time.sleep(0.25)
        current_distances = {}
        with lock:
            now = time.time()
            for nid, info in data_store.items():
                if info["rssi"] is not None and (now - info["t"]) < 1.2:
                    current_distances[nid] = rssi_to_meters(nid, info["rssi"])

        raw_pos = weighted_trilateration(current_distances)
        x_filt, y_filt = kf.update(raw_pos)
        
        # Resultado final con resolución de 1 metro
        print(f"Posición Final: ({round(x_filt)}m, {round(y_filt)}m) | Nodos activos: {len(current_distances)}")

if __name__ == "__main__":
    t1 = threading.Thread(target=serial_reader, daemon=True)
    t1.start()
    position_calculator()