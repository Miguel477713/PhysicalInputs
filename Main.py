from AlgoritmoCrazy import serial_reader, position_calculator
from ProximityAndAccess import * 

def Main():
    print("Program started")

    # Start NET worker threads
    workerThread = threading.Thread(target=Worker, daemon=True, args=(3, 0))
    locWorkerThread = threading.Thread(target=LocationWorker, daemon=True, args=(3,))
    locWorkerThread.start()
    workerThread.start()

    #timedWorkerThread1 = threading.Thread(target=TimedWorker, daemon=True, args=(3, 60, 'heartbeatProximity'))
    #timedWorkerThread1.start()

    #timedWorkerThread2 = threading.Thread(target=TimedWorker, daemon=True, args=(3, 60, 'heartbeatSensors'))
    #timedWorkerThread2.start()
    
    #sensors------------------------------------------------------------
    SetGPIO()

    # Initial states
    for pin, info in sensorInfo.items():
        Triggered(pin)

    # Event detection
    for pin, info in sensorInfo.items():
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=Triggered, bouncetime=50)


    #radar------------------------------------------------------------
    # Hilo 1: Lector
    t1 = threading.Thread(target=serial_reader, daemon=True)
    t1.start()
    
    # Hilo 2: Calculador (Loop Principal)
    t2 = threading.Thread(target=position_calculator, daemon=True)
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        eventQueue.put(None)  # signal worker to stop
        eventQueue.join() #wait until no queue empty
        workerThread.join() #blocks until all queued tasks are marked done
        GPIO.cleanup()

if __name__ == "__main__":
    Main()
