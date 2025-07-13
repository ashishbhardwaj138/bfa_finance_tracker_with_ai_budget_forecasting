import os
import time
import socket
import psutil
import logging
import configparser
import subprocess
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# ------------------ Load Config ------------------
config = configparser.ConfigParser()
config.read("config.ini")

def get_cfg(section, key, fallback=None, type_cast=str):
    try:
        value = config.get(section, key, fallback=str(fallback))
        return type_cast(value)
    except Exception:
        return fallback

# SYSTEM
project_dir      = get_cfg("SYSTEM", "project_dir")
script_name      = get_cfg("SYSTEM", "script_name")
venv_activate    = get_cfg("SYSTEM", "venv_activate")
log_file         = get_cfg("SYSTEM", "log_file")

# SCHEDULE
hour             = get_cfg("SCHEDULE", "hour", 9, int)
minute           = get_cfg("SCHEDULE", "minute", 0, int)

# CONDITIONS
min_ram_free     = get_cfg("CONDITIONS", "min_ram_percent_free", 10, int)
max_idle_minutes = get_cfg("CONDITIONS", "max_idle_minutes", 5, int)
loop_interval    = get_cfg("CONDITIONS", "check_interval_seconds", 600, int)

# ------------------ Setup Logging ------------------
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(filename=log_file, level=logging.INFO)

# ------------------ Utility Functions ------------------
def is_internet_connected():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

def is_ram_free(threshold):
    mem = psutil.virtual_memory()
    return mem.available * 100 / mem.total > threshold

def is_laptop_active():
    try:
        if os.name == 'nt':
            from ctypes import windll
            return windll.user32.GetForegroundWindow() != 0
        else:
            idle_time = int(os.popen("xprintidle").read()) // 1000  # seconds
            return idle_time < (max_idle_minutes * 60)
    except:
        return True  # Assume active

# ------------------ Ingestion Job ------------------
def run_job():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logging.info(f"[{now}] Checking job conditions...")

    if not is_internet_connected():
        logging.info("🛑 Skipped: No internet connection.")
        return
    if not is_ram_free(min_ram_free):
        logging.info(f"🛑 Skipped: Less than {min_ram_free}% free RAM.")
        return
    if not is_laptop_active():
        logging.info(f"🛑 Skipped: Laptop is idle > {max_idle_minutes} min or locked.")
        return

    logging.info("✅ All conditions met. Running ingestion job...")

    try:
        cmd = f"source {venv_activate} && cd {project_dir} && python {script_name}"
        subprocess.call(["/bin/bash", "-c", cmd])
        logging.info("✅ Job executed successfully.")
    except Exception as e:
        logging.error(f"❌ Job failed: {str(e)}")

# ------------------ Scheduler Setup ------------------
scheduler = BackgroundScheduler()
scheduler.add_job(run_job, 'cron', hour=hour, minute=minute)
scheduler.start()

print("Smart scheduler started in background...")

try:
    while True:
        time.sleep(loop_interval)
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()
    print("Smart scheduler stopped.")

