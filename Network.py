import time
import json
import queue
from datetime import datetime, timezone
from urllib import request

remoteUrl = "https://server-api.calmgrass-d765df7a.westus2.azurecontainerapps.io/api/"

eventQueue = queue.Queue()
locationQueue = queue.Queue()

def GetIsoUtcNow():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def SendToRemote(payload):
    if payload == 'heartbeatProximity':
        body = {
            "service_name": "proximity",
            "universalTimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        }
        data = json.dumps(body).encode("utf-8")
        endpoint = 'proximity/heartbeat'
    elif payload == 'heartbeatSensors':
        body = {
            "service_name": "sensors",
            "universalTimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        }
        data = json.dumps(body).encode("utf-8")
        endpoint = 'sensors/heartbeat'
    else:
        data = json.dumps(payload).encode("utf-8")

        if payload.get("sensorType") in ["door", "window"]:
            endpoint = 'sensors'
        else:
            endpoint = 'proximity'

    req = request.Request(
        url=remoteUrl + endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        response = request.urlopen(req, timeout=5)

        if response.status == 200:
            print("Success (200)")
        else:
            print(f"Unexpected status: {response.status}")

    except error.HTTPError as e:
        print(f"HTTP Error: {e.code}")

    except error.URLError as e:
        print(f"Connection Error: {e.reason}")

# Worker thread (only place where network happens)
def Worker(numberOfAttempts=3, waitTime=0, heartbeatType=''):
    sleepTime = 0
    
    while True:
        startTime = time.time()
        
        if(waitTime!=0):
            pass
            time.sleep(sleepTime)
            eventQueue.put(heartbeatType)

        payload = eventQueue.get()

        try:
            if payload is None:
                break

            for attempt in range(numberOfAttempts):
                try:
                    SendToRemote(payload)
                    break
                except Exception as e:
                    print(f"Remote send failed (attempt {attempt + 1}/{numberOfAttempts}): {e}")
                    if attempt == (numberOfAttempts - 1):
                        print(f"Giving up on payload after {numberOfAttempts} attempts")
                    else:
                        time.sleep(1)
        finally:
            eventQueue.task_done()

        elapsedTime = time.time() - startTime
        sleepTime = max(0, waitTime - elapsedTime)


def SendLocationToRemote(payload):
    data = json.dumps(payload).encode("utf-8")
    endpoint = 'location'

    req = request.Request(
        url=remoteUrl + endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        response = request.urlopen(req, timeout=5)
        if response.status == 200:
            print("Location Success (200)")
        else:
            print(f"Location Unexpected status: {response.status}")
    except Exception as e:
        if hasattr(e, "read"):
            print(f"Location API rechazo (422): {e.read().decode()[:200]}")
        else:
            print(f"Location send error: {e}")

def LocationWorker(numberOfAttempts=3):
    while True:
        payload = locationQueue.get()
        try:
            if payload is None:
                break
            for attempt in range(numberOfAttempts):
                try:
                    SendLocationToRemote(payload)
                    break
                except Exception as e:
                    print(f"Location send failed (attempt {attempt + 1}/{numberOfAttempts}): {e}")
                    if attempt < numberOfAttempts - 1:
                        time.sleep(1)
        finally:
            locationQueue.task_done()
