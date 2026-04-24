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

# --- IDENTIFICADORES DE NODOS ---
# Nota: Las variables de calibración teórica ("A", "n", "weight") se han eliminado.
# El nuevo modelo WKNN ya no las necesita porque el espacio ahora se rige por mapas reales (FINGERPRINTS).
NODOS_IDS = [1, 2, 3, 4, 5]

# --- ESTRUCTURAS DE DATOS ---
data_store = {i: {"rssi": None, "t": 0} for i in NODOS_IDS}
# Ventana grande (20) para amortiguar bien los picos de RF/Body Shadowing
buffers_rssi = {i: deque(maxlen=20) for i in NODOS_IDS}
lock = threading.Lock()

# --- CLASE FILTRO DE KALMAN 2D ---
class KalmanIndoor:
    def __init__(self):
        self.x = np.array([5, 3, 0, 0]) # Estado inicial: x, y, vx, vy
        self.P = np.eye(4) * 5.0
        self.F = np.array([[1, 0, 0.25, 0], [0, 1, 0, 0.25], [0, 0, 1, 0], [0, 0, 0, 1]])
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        # R (Desconfianza de medición) en 6.0: Filtro MUY fuerte, ignora parpadeos
        self.R = np.eye(2) * 6.0  
        self.Q = np.eye(4) * 0.05

    def update(self, z):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        if z is not None:
            S = self.H @ self.P @ self.H.T + self.R
            K = self.P @ self.H.T @ np.linalg.inv(S)
            self.x = self.x + K @ (z - self.H @ self.x)
            self.P = (np.eye(4) - K @ self.H) @ self.P
        return self.x[0], self.x[1]

# --- FUNCIONES MATEMÁTICAS WKNN ---
# Estos son los promedios extraídos de tus datos Fase 2 (Huellas Magnéticas)
FINGERPRINTS = {
    "Seccion 1": {"pos": np.array([1.5, 1.5]), "rssi": {1: -72, 2: -73, 3: -76, 4: -52, 5: -71}},
    "Seccion 2": {"pos": np.array([4.5, 1.5]), "rssi": {1: -69, 2: -74, 3: -71, 4: -61, 5: -64}},
    "Seccion 3": {"pos": np.array([8.5, 1.5]), "rssi": {1: -73, 2: -70, 3: -65, 4: -73, 5: -61}},
    "Seccion 4": {"pos": np.array([5.0, 4.5]), "rssi": {1: -69, 2: -69, 3: -70, 4: -68, 5: -65}} 
}

def wknn_position(current_rssi):
    if len(current_rssi) < 3: return None, "Desconocida"
    
    distances = []
    # Comparar la lectura actual contra cada una de nuestras "huellas"
    for zone, data in FINGERPRINTS.items():
        dist_sq = 0
        for nid, fp_rssi in data["rssi"].items():
            # Penalización fuerte general para nodos perdidos por colisión RF
            curr_rssi = current_rssi.get(nid, -95) 

            # ----- AJUSTE DE GABINETES (Sección 2 vs Sección 4) -----
            # Si estamos evaluando el Nodo 5 en la Sección 2, le quitamos peso a su diferencia.
            # Como los gabinetes bloquean el Nodo 5 ahí, su lectura será mala y variable, 
            # así que le decimos a la matemática "perdónale el error al Nodo 5 si estás en la Sección 2".
            weight = 1.0
            if zone == "Seccion 2" and nid == 5:
                # Subimos un poco el peso (de 0.3 a 0.6) porque con 0.3 la Seccion 2 era tan
                # tolerante que a veces "robaba" las lecturas cuando estabas en la Seccion 4.
                weight = 0.6 
            
            dist_sq += weight * (curr_rssi - fp_rssi)**2
        
        dist = np.sqrt(dist_sq)
        distances.append((dist, zone, data["pos"]))
        
    distances.sort(key=lambda x: x[0])
    
    # Interpolar entre las 2 zonas más parecidas a la lectura actual (K=2)
    peso_total = 0
    x_est, y_est = 0.0, 0.0
    
    for k in range(2):
        d, z, pos = distances[k]
        peso = 1.0 / (d + 0.001) # Evitar división por cero
        x_est += pos[0] * peso
        y_est += pos[1] * peso
        peso_total += peso
        
    pos_final = np.array([x_est / peso_total, y_est / peso_total])
    zona_mas_cercana = distances[0][1] # La de menor distancia
    
    return pos_final, zona_mas_cercana

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
                            # Seguimos usando el percentil 75 para descartar bloqueos de cuerpo abruptos
                            data_store[node_id]["rssi"] = np.percentile(buffers_rssi[node_id], 75)
                            data_store[node_id]["t"] = time.time()
                except: continue
        except:
            print("Reconectando serial...")
        finally:
            if ser: ser.close()
        time.sleep(RECONNECT_DELAY_S)

def position_calculator():
    kf = KalmanIndoor()
    print("Iniciando cálculo WKNN + Kalman...")
    while True:
        time.sleep(0.25)
        current_rssi = {}
        with lock:
            now = time.time()
            for nid, info in data_store.items():
                if info["rssi"] is not None and (now - info["t"]) < 1.2:
                    current_rssi[nid] = info["rssi"]

        raw_pos_data, zona = wknn_position(current_rssi)
        
        if raw_pos_data is not None:
            x_filt, y_filt = kf.update(raw_pos_data)
            print(f"[{zona}] Coord Hibrida: ({round(x_filt, 1)}m, {round(y_filt, 1)}m) | Nodos: {len(current_rssi)}")
        else:
            kf.update(None)

