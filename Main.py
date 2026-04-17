from Radar import serial_reader, position_calculator
from ProximityAndAccess import * 

def Main():
    print("Program started")

    # Start NET worker thread
    workerThread = threading.Thread(target=Worker, daemon=True)
    workerThread.start()

    #sensors------------------------------------------------------------
    SetGPIO()

    # Initial states
    for pin in PINS:
        Triggered(pin)

    # Event detection
    for pin in PINS:
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=Triggered, bouncetime=50)


    #radar------------------------------------------------------------
    # # Hilo 1: Lector
    # t1 = threading.Thread(target=serial_reader, daemon=True)
    # t1.start()
    
    # # Hilo 2: Calculador (Loop Principal)
    # t2 = threading.Thread(target=position_calculator, daemon=True)
    # t2.start()

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
