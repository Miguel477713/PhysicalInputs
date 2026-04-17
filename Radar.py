import serial
import json
import threading
import time

# --- CONFIGURACIÓN ---
PORT_CANDIDATES = ["/dev/serial0", "/dev/ttyAMA0"]
BAUD = 115200          # Debe coincidir con el ESP32 Maestro
RECONNECT_DELAY_S = 2

# Diccionario global para guardar el último RSSI de cada nodo
# Formato: { nodo_id: { "rssi": valor, "timestamp": tiempo } }
data_store = {
    1: {"rssi": None, "t": 0},
    2: {"rssi": None, "t": 0},
    3: {"rssi": None, "t": 0},
    4: {"rssi": None, "t": 0}
}

lock = threading.Lock()

def serial_reader():
    """Hilo encargado de leer el puerto serie constantemente"""
    while True:
        ser = None
        connected = False

        for port in PORT_CANDIDATES:
            try:
                ser = serial.Serial(port, BAUD, timeout=1)
                print(f"Conectado a {port} a {BAUD} baudios")
                connected = True
                break
            except Exception as e:
                print(f"No se pudo abrir {port}: {e}")

        if not connected:
            print(f"Reintentando en {RECONNECT_DELAY_S}s...")
            time.sleep(RECONNECT_DELAY_S)
            continue

        try:
            while True:
                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode('utf-8', errors='replace').strip()
                if not line:
                    continue

                try:
                    packet = json.loads(line)
                    node_id = packet['n']
                    rssi = packet['r']

                    print(f"Trama recibida: {line}")
                    print(f"Nodo={node_id}, RSSI={rssi}")

                    with lock:
                        if node_id in data_store:
                            data_store[node_id]["rssi"] = rssi
                            data_store[node_id]["t"] = time.time()
                except (json.JSONDecodeError, KeyError, TypeError):
                    print(f"Trama ignorada: {line}")
        except Exception as e:
            print(f"Error en Serial: {e}")
            print(f"Intentando reconectar en {RECONNECT_DELAY_S}s...")
        finally:
            if ser is not None and ser.is_open:
                ser.close()

        time.sleep(RECONNECT_DELAY_S)

def position_calculator():
    """Hilo encargado de calcular la posición cada 250ms"""
    while True:
        time.sleep(0.25) # Frecuencia de actualización de 4Hz
        
        with lock:
            # Extraer los RSSI actuales
            # Si un dato tiene más de 1 segundo de antigüedad, lo consideramos "perdido"
            current_time = time.time()
            nodes_rssi = {}
            for node, info in data_store.items():
                if current_time - info["t"] < 1.0: 
                    nodes_rssi[node] = info["rssi"]
                else:
                    nodes_rssi[node] = None

        # Solo calculamos si tenemos al menos 3 nodos con señal
        valid_nodes = {k: v for k, v in nodes_rssi.items() if v is not None}
        
        if len(valid_nodes) >= 3:
            print(f"Calculando posición con: {valid_nodes}")
            # Aquí llamarías a tu función de trilateración(valid_nodes)
        else:
            print("Esperando más señales de nodos...")