import serial
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# --- CONFIGURACIÓN ---
PUERTO = 'COM5'
BAUDIOS = 115200

class ControladorBombaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Control Manual de Bombas - ESP32")
        self.root.geometry("700x650")
        self.root.configure(bg="#121212")
        self.root.resizable(False, False)
        
        # Variables de estado
        self.distancia_var = tk.StringVar(value="Esperando conexión...")
        self.nivel_var = tk.StringVar(value="--%")
        self.nivel_actual = 0.0
        
        # Estado de botones
        self.boton_llenar_activo = False
        self.boton_vaciar_activo = False
        
        # Conexión Serial segura
        self.ser = None
        self.estado_conexion = False
        self._conectar_serial()

        if not self.estado_conexion:
            return

        # Iniciar hilo de lectura
        self.hilo_lectura = threading.Thread(target=self.leer_datos_loop, daemon=True)
        self.hilo_lectura.start()

        self.crear_interfaz()

    def _conectar_serial(self):
        """Conecta al puerto con pausa para reinicio del ESP32"""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(PUERTO, BAUDIOS, timeout=1)
            time.sleep(2)  # Esperar reinicio del ESP32
            self.ser.reset_input_buffer()  # Limpiar basura inicial
            self.estado_conexion = True
            print(f"✅ Conectado a {PUERTO}")
        except Exception as e:
            self.estado_conexion = False
            self.ser = None
            print(f"❌ Error de conexión: {e}")
            self.root.after(100, lambda: messagebox.showerror(
                "Error de Conexión", 
                f"No se pudo abrir {PUERTO}\n{e}\n\nAsegúrate de:\n1. Cerrar Monitor Serie de Arduino IDE\n2. Verificar cable USB"
            ))

    def crear_interfaz(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#121212")
        style.configure("TLabel", background="#121212", foreground="#ffffff", font=("Segoe UI", 11))
        style.configure("TLabelframe", background="#121212", foreground="#ffffff")
        style.configure("TLabelframe.Label", background="#121212", foreground="#ff4d4d", font=("Segoe UI", 12, "bold"))
        style.configure("Red.TButton", background="#8b0000", foreground="white", font=("Segoe UI", 11, "bold"))
        style.map("Red.TButton", background=[("active", "#a50000")])
        style.configure("Green.TButton", background="#2e7d32", foreground="white", font=("Segoe UI", 11, "bold"))
        style.map("Green.TButton", background=[("active", "#388e3c")])
        style.configure("Gray.TButton", background="#424242", foreground="white", font=("Segoe UI", 11, "bold"))
        style.map("Gray.TButton", background=[("active", "#616161")])

        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === SECCIÓN 1: SIMULACIÓN DEL TANQUE + LEDs ===
        tank_frame = ttk.LabelFrame(main_frame, text="MONITOREO EN TIEMPO REAL", padding=15)
        tank_frame.pack(fill=tk.X, pady=(0, 15))

        self.canvas = tk.Canvas(tank_frame, width=120, height=200, bg="#1e1e1e", highlightthickness=2, highlightbackground="#333")
        self.canvas.pack(side=tk.LEFT, padx=(0, 20))
        
        self.canvas.create_rectangle(10, 10, 110, 190, outline="#555", width=2, fill="#0a0a0a")
        self.water_rect = self.canvas.create_rectangle(12, 188, 108, 188, fill="#1a6dff", outline="")
        for y in [40, 80, 120, 160]:
            self.canvas.create_line(10, y, 110, y, dash=(2, 4), fill="#333")

        status_panel = ttk.Frame(tank_frame)
        status_panel.pack(side=tk.LEFT, fill=tk.Y, expand=True)

        self.led_status = tk.Canvas(status_panel, width=30, height=30, bg="#121212", highlightthickness=0)
        self.led_status.pack(pady=5)
        self.led_status.create_oval(5, 5, 25, 25, fill="#333333", outline="#555")
        ttk.Label(status_panel, text="ESTADO", font=("Segoe UI", 9, "bold")).pack()

        ttk.Label(status_panel, textvariable=self.distancia_var, font=("Consolas", 14), foreground="#aaaaaa").pack(pady=8)
        ttk.Label(status_panel, textvariable=self.nivel_var, font=("Segoe UI", 28, "bold"), foreground="#ff4d4d").pack()

        # === SECCIÓN 2: BOTONES DE ACCIÓN EXPLÍCITA ===
        action_frame = ttk.LabelFrame(main_frame, text="CONTROL MANUAL", padding=15)
        action_frame.pack(fill=tk.X, pady=(0, 15))

        btn_llenar = ttk.Button(action_frame, text="▶ EMPEZAR A LLENAR", style="Green.TButton", 
                                command=self.empezar_llenar)
        btn_llenar.pack(fill=tk.X, pady=5)

        btn_vaciar = ttk.Button(action_frame, text="▼ EMPEZAR A VACIAR", style="Red.TButton", 
                                command=self.empezar_vaciar)
        btn_vaciar.pack(fill=tk.X, pady=5)

        btn_stop = ttk.Button(action_frame, text=" DETENER TODO", style="Gray.TButton", 
                              command=self.detener_todo)
        btn_stop.pack(fill=tk.X, pady=5)

        # Indicadores LED de estado de bombas
        led_frame = ttk.Frame(action_frame)
        led_frame.pack(fill=tk.X, pady=(10,0))
        
        self.led_llenar = tk.Canvas(led_frame, width=24, height=24, bg="#121212", highlightthickness=0)
        self.led_llenar.pack(side=tk.LEFT, padx=(0, 10))
        self.led_llenar.create_oval(4, 4, 20, 20, fill="#333333", outline="#555")
        ttk.Label(led_frame, text="Bomba Llenado", background="#121212", foreground="#ffffff").pack(side=tk.LEFT)

        self.led_vaciar = tk.Canvas(led_frame, width=24, height=24, bg="#121212", highlightthickness=0)
        self.led_vaciar.pack(side=tk.LEFT, padx=(20, 10))
        self.led_vaciar.create_oval(4, 4, 20, 20, fill="#333333", outline="#555")
        ttk.Label(led_frame, text="Bomba Vaciado", background="#121212", foreground="#ffffff").pack(side=tk.LEFT)

    # --- LÓGICA DE BOTONES ---
    def empezar_llenar(self):
        self.boton_vaciar_activo = False
        self.boton_llenar_activo = True
        self.enviar("EMPEZAR_LLENAR")
        self.actualizar_leds_bombas()

    def empezar_vaciar(self):
        self.boton_llenar_activo = False
        self.boton_vaciar_activo = True
        self.enviar("EMPEZAR_VACIAR")
        self.actualizar_leds_bombas()

    def detener_todo(self):
        self.boton_llenar_activo = False
        self.boton_vaciar_activo = False
        self.enviar("DETENER_TODO")
        self.actualizar_leds_bombas()

    def actualizar_leds_bombas(self):
        color_llenar = "#33cc33" if self.boton_llenar_activo else "#333333"
        self.led_llenar.delete("all")
        self.led_llenar.create_oval(4, 4, 20, 20, fill=color_llenar, outline="#555")

        color_vaciar = "#33cc33" if self.boton_vaciar_activo else "#333333"
        self.led_vaciar.delete("all")
        self.led_vaciar.create_oval(4, 4, 20, 20, fill=color_vaciar, outline="#555")

    # --- COMUNICACIÓN SERIAL SEGURA ---
    def enviar(self, comando):
        if not self.estado_conexion or not self.ser:
            return
        try:
            self.ser.write((comando + '\n').encode())
        except Exception as e:
            print(f"Error al enviar: {e}")
            self.estado_conexion = False

    def leer_datos_loop(self):
        while True:
            try:
                if not self.estado_conexion or not self.ser:
                    time.sleep(1)
                    continue
                    
                if self.ser.in_waiting > 0:
                    linea = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if linea.startswith("DATA:"):
                        partes = linea.replace("DATA:", "").split(",")
                        if len(partes) == 2:
                            self.root.after(0, lambda d=partes[0], n=partes[1]: self.actualizar_todo(d, n))
            except serial.SerialException as e:
                print(f"️ Error serial: {e}")
                self.estado_conexion = False
                self.root.after(0, lambda: messagebox.showwarning(
                    "Conexión Perdida", "Se desconectó el ESP32."
                ))
            except Exception as e:
                print(f"⚠️ Error inesperado: {e}")
            
            time.sleep(0.05)

    # --- ACTUALIZACIÓN DE INTERFAZ ---
    def actualizar_todo(self, distancia, nivel_str):
        try:
            nivel = float(nivel_str)
            if nivel < 0:
                self.distancia_var.set("Sensor: Sin señal")
                self.nivel_var.set("--%")
                return
        except:
            nivel = 0
            
        self.nivel_actual = max(0, min(80, nivel))
        self.distancia_var.set(f"Distancia: {distancia} cm")
        self.nivel_var.set(f"{nivel:.1f}%")
        
        self.actualizar_tanque_visual()
        self.actualizar_led_estado(nivel)

    def actualizar_tanque_visual(self):
        y_bottom = 188
        altura_agua = (self.nivel_actual / 80.0) * 176
        y_top = y_bottom - altura_agua
        
        if self.nivel_actual <= 20:
            color = "#ff3333"
        elif self.nivel_actual >= 85:
            color = "#ffaa00"
        else:
            color = "#1a6dff"
            
        self.canvas.coords(self.water_rect, 12, y_top, 108, y_bottom)
        self.canvas.itemconfig(self.water_rect, fill=color)

    def actualizar_led_estado(self, nivel):
        if nivel <= 20:
            color_status = "#ff3333"
        elif nivel >= 85:
            color_status = "#ffaa00"
        else:
            color_status = "#33cc33"
        self.led_status.delete("all")
        self.led_status.create_oval(5, 5, 25, 25, fill=color_status, outline="#555")


if __name__ == "__main__":
    root = tk.Tk()
    app = ControladorBombaApp(root)
    root.mainloop()
