import os
import shutil
import subprocess
import sys
import ctypes
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
import threading
import time





LOGFILE = os.path.join(os.environ["USERPROFILE"], "Desktop", f"Optimizacion_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_cmd(command, timeout=None):
    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        start_time = time.time()
        output, error = "", ""
        while True:
            if process.poll() is not None:
                output, error = process.communicate()
                break
            if timeout and (time.time() - start_time > timeout):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
                return ("", "[TIMEOUT] El comando excedió el tiempo límite y fue cancelado.")
            time.sleep(0.1)
        return (output.strip(), error.strip())
    except Exception as e:
        return ("", f"[EXCEPCIÓN] {str(e)}")

def add_log(msg):
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} {msg}\n")

# ----------- Diagnóstico RAM y Disco -----------
def diagnostico_ram(callback):
    info = []
    recomendacion = ""
    try:
        cmd = 'wmic memorychip get banklabel,capacity,manufacturer,partnumber,speed'
        out, err = run_cmd(cmd)
        ram_modulos = []
        for line in out.splitlines()[1:]:
            if line.strip():
                parts = [p.strip() for p in line.split() if p.strip()]
                # Algunos fabricantes pueden dejar columnas vacías, entonces chequeamos
                if len(parts) < 5: continue
                bank, cap, mfg, part, speed = parts[:5]
                gb = int(cap) // (1024 ** 3) if cap.isdigit() else 0
                ram_modulos.append((bank, gb, mfg, part, speed))
        slots = len(ram_modulos)
        total_ram = sum([mod[1] for mod in ram_modulos])
        max_slots = 2  # Puedes ajustarlo para tu hardware
        if slots < max_slots:
            recomendacion = f"💡 Hay slots de RAM libres. Recomendado ampliar a {max(8,total_ram*2)}GB para mejor desempeño."
        else:
            if total_ram < 8:
                recomendacion = f"💡 Ampliar RAM a 8GB mínimo. Actualmente: {total_ram}GB ({slots} módulos instalados)."
            else:
                recomendacion = f"RAM instalada óptima: {total_ram}GB ({slots} módulos)."
        info.append("Módulos RAM detectados:")
        for m in ram_modulos:
            info.append(f"- Slot: {m[0]}, Tamaño: {m[1]} GB, Marca: {m[2]}, Modelo: {m[3]}, Velocidad: {m[4]}")
        info.append(recomendacion)
    except Exception as e:
        info.append(f"[ERROR] Diagnóstico RAM: {e}")
    add_log("\n".join(info))
    callback("\n".join(info))

def diagnostico_almacenamiento(callback):
    info = []
    recomendacion = ""
    try:
        out, err = run_cmd('wmic diskdrive get model,mediaType,size')
        is_hdd = False
        for line in out.splitlines()[1:]:
            if line.strip():
                parts = [p.strip() for p in line.split() if p.strip()]
                if len(parts) < 3: continue
                model, tipo, size = parts[:3]
                gb = int(size) // (1024 ** 3) if size.isdigit() else 0
                info.append(f"- Modelo: {model}, Tipo: {tipo}, Tamaño: {gb} GB")
                if "HDD" in tipo or "Hard" in tipo or "Fixed" in tipo:
                    is_hdd = True
        if is_hdd:
            recomendacion = "💡 El equipo tiene HDD. Migrar a SSD es altamente recomendable para mejorar velocidad."
        else:
            recomendacion = "✔ El equipo ya cuenta con SSD."
        info.append(recomendacion)
    except Exception as e:
        info.append(f"[ERROR] Diagnóstico Almacenamiento: {e}")
    add_log("\n".join(info))
    callback("\n".join(info))

# ----------- Funciones de mantenimiento ----------
def limpiar_temporales(callback):
    temp_paths = [
        os.environ.get("TEMP"),
        os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Temp"),
        os.path.join(os.environ["SystemRoot"], "Temp"),
        os.path.join(os.environ["SystemRoot"], "SoftwareDistribution", "Download"),
        os.path.join(os.environ["SystemRoot"], "System32", "config", "systemprofile", "AppData", "Local", "Microsoft", "Windows", "INetCache"),
        os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Microsoft", "Windows", "INetCache"),
        os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Lenovo"),
        "C:\\ProgramData\\Lenovo"
    ]
    for path in temp_paths:
        if path and os.path.exists(path):
            callback(f"Limpieza: {path}")
            try:
                for filename in os.listdir(path):
                    file_path = os.path.join(path, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path, ignore_errors=True)
                add_log(f"Limpieza completada en {path}")
            except Exception as e:
                add_log(f"[ERROR] Limpieza en {path}: {e}")

def configurar_servicios(callback):
    servicios = {
        "wuauserv": "auto",
        "TrustedInstaller": "demand",
        "BITS": "demand",
        "DiagTrack": "disabled",
        "Pcaudiovisualservice": "disabled",
        "XboxGipSvc": "disabled",
        "XboxNetApiSvc": "disabled",
        "WwanSvc": "disabled",
        "MapsBroker": "disabled",
        "OneSyncSvc": "disabled"
    }
    for s, modo in servicios.items():
        callback(f"Configurando servicio: {s} → {modo}")
        out, err = run_cmd(f"sc config {s} start= {modo}")
        if modo == "disabled":
            run_cmd(f"sc stop {s}")
        if err:
            add_log(f"[WARNING] Servicio {s}: {err}")

def deshabilitar_tareas(callback):
    tareas = [
        "Microsoft\\Windows\\Customer Experience Improvement Program\\Consolidator",
        "Microsoft\\Windows\\Application Experience\\ProgramDataUpdater"
    ]
    for tarea in tareas:
        callback(f"Deshabilitando tarea: {tarea}")
        out, err = run_cmd(f'schtasks /Change /TN "{tarea}" /Disable')
        if err and "no existe" not in err:
            add_log(f"[ERROR] {tarea}: {err}")

def diagnostico_hardware(callback):
    diagnostico_ram(callback)
    diagnostico_almacenamiento(callback)

def diagnostico_disco(callback):
    cmd_media_type = 'wmic diskdrive get MediaType'
    result = subprocess.run(cmd_media_type, shell=True, capture_output=True, text=True)
    if "Fixed hard disk" in result.stdout or "HDD" in result.stdout:
        callback("Desfragmentando HDD...")
        out, err = run_cmd('defrag C: /O /U /V', timeout=300)
        add_log(out + "\n" + err)
    else:
        callback("No es HDD. Saltando desfragmentación.")

def run_cmd_with_skip(app, command, callback, timeout=300):
    # Ejecuta el comando, permite terminar el proceso externo si presionas Saltar.
    app._current_subprocess = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    start_time = time.time()
    output, error = "", ""
    asked = False
    while True:
        if app.skip_current:
            app._current_subprocess.terminate()
            try:
                app._current_subprocess.wait(timeout=5)
            except Exception:
                app._current_subprocess.kill()
            callback(f"[AVISO] Paso saltado por el usuario.")
            add_log(f"[AVISO] Paso saltado por el usuario.")
            app.skip_current = False
            break
        if app._current_subprocess.poll() is not None:
            output, error = app._current_subprocess.communicate()
            add_log(output + "\n" + error)
            break
        if time.time() - start_time > timeout and not asked:
            resp = messagebox.askyesno("Proceso lento", f"Este paso lleva más de {timeout // 60} minutos.\n¿Quieres saltar este paso?")
            asked = True
            if resp:
                app.skip_current = True
        time.sleep(0.3)
    app._current_subprocess = None

def reparar_sistema(app, callback):
    for nombre, cmd in [
        ("SFC", 'sfc /scannow'),
        ("DISM", 'DISM /Online /Cleanup-Image /RestoreHealth'),
        ("CHKDSK", 'echo S | chkdsk C: /f /r')
    ]:
        callback(f"Ejecutando {nombre}...")
        app.skip_current = False
        t = threading.Thread(target=run_cmd_with_skip, args=(app, cmd, callback))
        t.start()
        while t.is_alive():
            app.update()
            time.sleep(0.2)
        # El log ya está registrado en run_cmd_with_skip

def ajuste_paginacion(callback):
    try:
        output = subprocess.check_output('wmic computersystem get TotalPhysicalMemory', shell=True, text=True)
        # El valor puede estar vacío si falla el comando, maneja con try/except
        try:
            ram_gb = int([x for x in output.split('\n')[1:] if x.strip()][0]) / (1024 ** 3)
        except:
            ram_gb = 0
        if ram_gb < 8:
            callback("Ajustando archivo de paginación a 8GB por RAM baja...")
            run_cmd('wmic computersystem where name="%computername%" set AutomaticManagedPagefile=False')
            run_cmd('wmic pagefileset where name="C:\\\\pagefile.sys" set InitialSize=8192,MaximumSize=8192')
            add_log("Paginación fija 8GB aplicada.")
    except Exception as e:
        add_log(f"[ERROR] Ajustando paginación: {e}")

def renovar_ip_dns(callback):
    callback("Renovando IP y limpiando DNS...")
    run_cmd('ipconfig /renew')
    run_cmd('ipconfig /flushdns')

def limpiar_papelera(callback):
    callback("Vaciando papelera...")
    run_cmd('PowerShell.exe -Command "Clear-RecycleBin -Confirm:$false"')

def advertencias(callback):
    add_log("⚠️ Si tienes OwnCloud, OneDrive u otras apps que se inician con Windows y no usas, deshabilítalas (Administrador de tareas > Inicio o shell:startup).")

# --------------------- Interfaz gráfica ----------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mantenimiento lógico Windows (Diagnóstico y optimización)")
        self.geometry("760x480")
        self.resizable(True, True)
        self.cancelled = False
        self.skip_current = False
        self._current_subprocess = None
        self.current_step = 0
        self.pasos = [
            ("Limpieza de archivos temporales", limpiar_temporales),
            ("Vaciar papelera", limpiar_papelera),
            ("Diagnóstico de hardware y recomendaciones", diagnostico_hardware),
            ("Configuración de servicios", configurar_servicios),
            ("Deshabilitar tareas programadas", deshabilitar_tareas),
            ("Diagnóstico y optimización de disco", diagnostico_disco),
            ("Reparación de sistema", lambda cb: reparar_sistema(self, cb)),
            ("Ajuste de paginación", ajuste_paginacion),
            ("Renovación IP/DNS", renovar_ip_dns),
            ("Advertencias finales", advertencias)
        ]
        self.start_screen()

    def start_screen(self):
        for widget in self.winfo_children():
            widget.destroy()
        f = tk.Frame(self, bg="#f6faff")
        f.place(relx=0.5, rely=0.5, anchor="center")
        btn = tk.Button(f, text="Iniciar mantenimiento", font=("Segoe UI", 18, "bold"), bg="#3182ce", fg="white",
                        width=22, height=2, command=self.go_to_progress)
        btn.pack(pady=40)

    def go_to_progress(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.geometry("900x550")
        btn_log = tk.Button(self, text="Ver log", command=self.show_log, font=("Segoe UI", 10, "bold"), bg="#e2e8f0")
        btn_log.place(x=10, y=10)
        btn_download = tk.Button(self, text="Descargar log", command=self.download_log, font=("Segoe UI", 10, "bold"), bg="#e2e8f0")
        btn_download.place(x=95, y=10)
        self.btn_skip = tk.Button(self, text="Saltar paso", command=self.skip_step, font=("Segoe UI", 10, "bold"), bg="#f6a800")
        self.btn_skip.place(x=200, y=10)
        self.btn_close = tk.Button(self, text="Cerrar programa", command=self.safe_close, font=("Segoe UI", 10, "bold"), bg="#f65c60")
        self.btn_close.place(x=315, y=10)
        self.label_status = tk.Label(self, text="Listo para iniciar...", font=("Segoe UI", 14, "bold"), anchor="w")
        self.label_status.place(x=430, y=10)
        self.progress = tk.Label(self, text="Esperando...", font=("Consolas", 11), anchor="w", bg="white", relief="solid", bd=1, width=115)
        self.progress.place(x=30, y=70, height=35)
        self.simple_log = scrolledtext.ScrolledText(self, width=130, height=19, font=("Consolas", 10))
        self.simple_log.place(x=30, y=120, relwidth=0.93, relheight=0.67)
        threading.Thread(target=self.run_maintenance, daemon=True).start()

    def show_log(self):
        win = tk.Toplevel(self)
        win.title("Log detallado de mantenimiento")
        win.geometry("950x550")
        txt = scrolledtext.ScrolledText(win, width=120, height=32, font=("Consolas", 10))
        txt.pack(fill="both", expand=True)
        if os.path.exists(LOGFILE):
            with open(LOGFILE, encoding="utf-8") as f:
                txt.insert("1.0", f.read())
        else:
            txt.insert("1.0", "Log aún no generado.")

    def download_log(self):
        if not os.path.exists(LOGFILE):
            messagebox.showerror("Error", "El log aún no está disponible.")
            return
        savepath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Archivo de texto", "*.txt")], title="Guardar log como")
        if savepath:
            shutil.copy(LOGFILE, savepath)
            messagebox.showinfo("Listo", f"Log guardado en:\n{savepath}")

    def skip_step(self):
        self.skip_current = True
        if self._current_subprocess:
            try:
                self._current_subprocess.terminate()
            except Exception:
                pass

    def safe_close(self):
        if messagebox.askokcancel("Salir", "¿Deseas cerrar el programa de manera segura?"):
            self.cancelled = True
            self.destroy()

    def run_maintenance(self):
        total = len(self.pasos)
        def callback(msg):
            self.progress["text"] = msg
            self.simple_log.insert(tk.END, msg + "\n")
            self.simple_log.see(tk.END)
            self.label_status["text"] = f"En proceso: {msg}"

        if not is_admin():
            messagebox.showinfo("Permiso requerido", "Se requiere ejecutar como administrador. El programa se reiniciará como admin.")
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            self.destroy()
            return

        inicio = datetime.now()
        self.label_status["text"] = "Mantenimiento iniciado..."
        for idx, (nombre, func) in enumerate(self.pasos, 1):
            if self.cancelled:
                callback("Proceso cancelado por el usuario.")
                break
            self.skip_current = False
            callback(f"{nombre}...")
            t = threading.Thread(target=func, args=(lambda x: callback(x) if not self.skip_current and not self.cancelled else None,))
            t.start()
            while t.is_alive():
                self.update()
                time.sleep(0.2)
            self.progress["text"] = f"{nombre} ✔"
        fin = datetime.now()
        mins = (fin - inicio).total_seconds() / 60
        callback(f"Proceso completado. Duración: {mins:.2f} min.\nRevisa el log completo para detalles y sugerencias.")
        self.label_status["text"] = "¡Mantenimiento terminado!"

if __name__ == "__main__":
    App().mainloop()
