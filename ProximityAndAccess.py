import RPi.GPIO as GPIO
import time
import json
import threading
import queue
from Network import *

GPIO.setmode(GPIO.BCM)

sensorInfo = {
    6:  {"sensorType": "door", "sensorId": 1},
    13: {"sensorType": "proximity", "sensorId": 1},
    19: {"sensorType": "window", "sensorId": 2},
    26: {"sensorType": "proximity", "sensorId": 2}
}

def BuildSensorPayload(pin, state):
    info = sensorInfo[pin]
    timestamp = GetIsoUtcNow()

    return {
        "sensorType": info["sensorType"],
        "sensorId": info["sensorId"],
        "state": bool(state),
        "stateMeaning": GetStateMeaning(info["sensorType"]),
        "universalTimeStamp": timestamp,
        "sourceTimeStamp": timestamp
    }


def GetStateMeaning(sensorType):
    if sensorType == "door" or sensorType == "window":
        return "open"
    if sensorType == "proximity":
        return "coming"
    return "open"


def Triggered(channel):
    state = GPIO.input(channel)

    if state == 1:
        print(f"{sensorInfo[channel]["sensorType"]}{sensorInfo[channel]["sensorId"]}: Relay opened")
    else:
        print(f"{sensorInfo[channel]["sensorType"]}{sensorInfo[channel]["sensorId"]}: Relay closed")

    payload = BuildSensorPayload(channel, state)

    # NON-BLOCKING: just enqueue
    eventQueue.put(payload)

# Setup GPIO
def SetGPIO():
    for pin, info in sensorInfo.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)