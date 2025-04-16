import time
import random

def read_sensor():
    # Simulate a temperature sensor reading
    return random.uniform(20.0, 30.0)

def control_device(temp):
    if temp > 25.0:
        print("Temperature is high. Turning ON the fan.")
    else:
        print("Temperature is low. Turning OFF the fan.")

if __name__ == "__main__":
    while True:
        sensor_value = read_sensor()
        print(f"Sensor value: {sensor_value:.2f}°C")
        control_device(sensor_value)
        time.sleep(5)
