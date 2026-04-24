import json
import queue
import threading
import time
from datetime import datetime, timezone
from urllib import request, error

remoteUrl = "https://server-api.calmgrass-d765df7a.westus2.azurecontainerapps.io/api/"

# Three outbound queues. They are all thread-safe because Python queue.Queue
# already handles locking internally.
gpioQueue = queue.Queue()
heartbeatQueue = queue.Queue()
radarQueue = queue.Queue()

stopRequested = threading.Event()
queueRotationIndex = 0


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


def QueueGpioOutbound(endpoint, payload):
    gpioQueue.put(BuildQueueItem(endpoint, payload))


def QueueHeartbeatOutbound(endpoint, payload):
    heartbeatQueue.put(BuildQueueItem(endpoint, payload))


def QueueRadarOutbound(endpoint, payload):
    radarQueue.put(BuildQueueItem(endpoint, payload))


def QueueSensorPayload(payload):
    if payload.get("sensorType") in ["door", "window"]:
        QueueGpioOutbound("sensors", payload)
    else:
        QueueGpioOutbound("proximity", payload)


def QueueLocationPayload(payload):
    QueueRadarOutbound("location", payload)


def QueueHeartbeat(serviceName):
    QueueHeartbeatOutbound(f"{serviceName}/heartbeat", BuildHeartbeatPayload(serviceName))


def StopNetworkWorker():
    stopRequested.set()


def OutboundQueuesAreEmpty():
    return gpioQueue.empty() and heartbeatQueue.empty() and radarQueue.empty()


def JoinOutboundQueues():
    gpioQueue.join()
    heartbeatQueue.join()
    radarQueue.join()


def GetNextQueueItem(timeoutSeconds=0.25):
    """
    Fair round-robin selection across the three queues.

    This avoids the old single-FIFO problem where many radar messages could sit
    in front of a GPIO message. It also avoids strict priority: GPIO does not
    always jump ahead forever; each non-empty queue gets turns.
    """
    global queueRotationIndex

    queues = [
        ("gpio", gpioQueue),
        ("heartbeat", heartbeatQueue),
        ("radar", radarQueue),
    ]

    # First: try all queues without blocking (fair round-robin)
    for offset in range(len(queues)):
        index = (queueRotationIndex + offset) % len(queues)
        queueName, selectedQueue = queues[index]
        try:
            queueItem = selectedQueue.get_nowait()
            queueRotationIndex = (index + 1) % len(queues)
            return queueName, selectedQueue, queueItem
        except queue.Empty:
            pass

    # Second: nothing available, then sleep briefly
    time.sleep(timeoutSeconds)
    return None, None, None


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
        if stopRequested.is_set() and OutboundQueuesAreEmpty():
            break

        queueName, selectedQueue, queueItem = GetNextQueueItem()

        if queueItem is None:
            continue

        try:
            endpoint = queueItem["endpoint"]
            payload = queueItem["payload"]

            print(f"Sending {queueName} item to {endpoint}")

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
            selectedQueue.task_done()
