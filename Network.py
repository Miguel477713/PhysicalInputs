import time
import json
import queue
from datetime import datetime, timezone
from urllib import request

remoteUrl = "https://server-api.calmgrass-d765df7a.westus2.azurecontainerapps.io/api/sensors"

eventQueue = queue.Queue()

def GetIsoUtcNow():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def SendToRemote(payload):
    data = json.dumps(payload).encode("utf-8")

    req = request.Request(
        remoteUrl,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        response = request.urlopen(req, timeout=5)

        if response.status == 200:
            print("✅ Success (200)")
        else:
            print(f"⚠️ Unexpected status: {response.status}")

    except error.HTTPError as e:
        print(f"❌ HTTP Error: {e.code}")

    except error.URLError as e:
        print(f"❌ Connection Error: {e.reason}")

# Worker thread (only place where network happens)
def Worker(numberOfAttempts=3):
    while True:
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
