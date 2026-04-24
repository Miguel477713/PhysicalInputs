import json
import queue
import time
from datetime import datetime, timezone
from urllib import request, error

remoteUrl = "https://server-api.calmgrass-d765df7a.westus2.azurecontainerapps.io/api/"

# One queue for every outbound network message: sensors, proximity, location, heartbeat.
outboundQueue = queue.Queue()


def GetIsoUtcNow():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def BuildHeartbeatPayload(serviceName):
    return {
        "service_name": serviceName,
        "universalTimeStamp": GetIsoUtcNow()
    }


def BuildQueueItem(endpoint, payload):
    return {
        "endpoint": endpoint,
        "payload": payload
    }


def QueueOutbound(endpoint, payload):
    outboundQueue.put(BuildQueueItem(endpoint, payload))


def QueueSensorPayload(payload):
    if payload.get("sensorType") in ["door", "window"]:
        QueueOutbound("sensors", payload)
    else:
        QueueOutbound("proximity", payload)


def QueueLocationPayload(payload):
    QueueOutbound("location", payload)


def QueueHeartbeat(serviceName):
    QueueOutbound(f"{serviceName}/heartbeat", BuildHeartbeatPayload(serviceName))


def StopNetworkWorker():
    outboundQueue.put(None)


def SendToRemote(endpoint, payload):
    data = json.dumps(payload).encode("utf-8")

    req = request.Request(
        url=remoteUrl + endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        response = request.urlopen(req, timeout=5)

        if response.status == 200:
            print(f"{endpoint} Success (200)")
        else:
            print(f"{endpoint} Unexpected status: {response.status}")

    except error.HTTPError as e:
        responseBody = ""
        try:
            responseBody = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        print(f"{endpoint} HTTP Error: {e.code} {responseBody}")
        raise

    except error.URLError as e:
        print(f"{endpoint} Connection Error: {e.reason}")
        raise


# Worker thread: the only place where network requests happen.
def NetworkWorker(numberOfAttempts=3):
    while True:
        queueItem = outboundQueue.get()

        try:
            if queueItem is None:
                break

            endpoint = queueItem["endpoint"]
            payload = queueItem["payload"]

            for attempt in range(numberOfAttempts):
                try:
                    SendToRemote(endpoint, payload)
                    break
                except Exception as e:
                    print(f"Remote send failed (attempt {attempt + 1}/{numberOfAttempts}): {e}")
                    if attempt == numberOfAttempts - 1:
                        print(f"Giving up on payload after {numberOfAttempts} attempts")
                    else:
                        time.sleep(1)
        finally:
            outboundQueue.task_done()
