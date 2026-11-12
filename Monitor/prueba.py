
import serial
import time

# Ajusta el puerto si es necesario
puerto = 'COM5'
baudrate = 115200

try:
    arduino = serial.Serial(puerto, baudrate, timeout=2)
    print(f"Conectado a {puerto}")
    time.sleep(1)  # Esperar a que el ESP32 se inicialice
    
    print("Esperando datos...")
    for i in range(20):  # Leer 20 líneas
        linea = arduino.readline().decode('utf-8', errors='ignore').strip()
        print(f"Línea {i+1}: '{linea}'")
        time.sleep(0.1)
    
    arduino.close()
    print("Desconectado")
    
except Exception as e:
    print(f"Error: {e}")