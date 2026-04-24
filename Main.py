import threading
import time

import RPi.GPIO as GPIO

from AlgoritmoCrazy import serial_reader, position_calculator
from Network import NetworkWorker, QueueHeartbeat, StopNetworkWorker, outboundQueue
from ProximityAndAccess import SetGPIO, Triggered, sensorInfo


def RegisterGPIOCallbacks():
    for pin in sensorInfo.keys():
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=Triggered, bouncetime=50)


def QueueInitialSensorStates():
    for pin in sensorInfo.keys():
        Triggered(pin)


def HeartbeatLoop(serviceName, intervalSeconds):
    while True:
        QueueHeartbeat(serviceName)
        time.sleep(intervalSeconds)


def StartThread(target, name, args=()):
    thread = threading.Thread(target=target, name=name, args=args, daemon=True)
    thread.start()
    return thread


def Main():
    print("Program started")

    networkThread = StartThread(NetworkWorker, "network-worker", args=(3,))

    StartThread(HeartbeatLoop, "heartbeat-proximity", args=("proximity", 60))
    StartThread(HeartbeatLoop, "heartbeat-sensors", args=("sensors", 60))

    SetGPIO()
    QueueInitialSensorStates()
    RegisterGPIOCallbacks()

    StartThread(serial_reader, "serial-reader")
    StartThread(position_calculator, "position-calculator")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        StopNetworkWorker()
        outboundQueue.join()
        networkThread.join()
        GPIO.cleanup()


if __name__ == "__main__":
    Main()
