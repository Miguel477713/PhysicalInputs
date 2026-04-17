import RPi.GPIO as GPIO
import time
import json
import threading
import queue
from Network import *

GPIO.setmode(GPIO.BCM)

PINS = [6, 13, 19, 26]

SENSOR_NAMES = {
    PINS[0]: "door",
    PINS[1]: "window",
    PINS[2]: "proximity1",
    PINS[3]: "proximity2"
}

sensorInfo = {
    6:  {"sensorType": "door", "sensorId": 1},
    13: {"sensorType": "window", "sensorId": 2},
    19: {"sensorType": "proximity", "sensorId": 3},
    26: {"sensorType": "proximity", "sensorId": 4}
}

def BuildSensorPayload(pin, state):
    info = sensorInfo[pin]
    timestamp = GetIsoUtcNow()

    return {
        "sensorType": info["sensorType"],
        "sensorId": info["sensorId"],
        "state": bool(state),
        "stateMeaning": GetStateMeaning(info["sensorType"], bool(state)),
        "universalTimeStamp": timestamp,
        "sourceTimeStamp": timestamp
    }


def GetStateMeaning(sensorType, state):
    if sensorType == "door" or sensorType == "window":
        return "open" if state else "closed"
    if sensorType == "proximity":
        return "coming" if state else "clear"
    return "active" if state else "inactive"


def Triggered(channel):
    state = GPIO.input(channel)

    if state == 1:
        print(f"{SENSOR_NAMES[channel]}: Relay opened")
    else:
        print(f"{SENSOR_NAMES[channel]}: Relay closed")

    payload = BuildSensorPayload(channel, state)

    # NON-BLOCKING: just enqueue
    eventQueue.put(payload)

# Setup GPIO
def SetGPIO():
    for pin in PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)