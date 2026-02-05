# Author: Kamil Kobak
# License: GPL-3.0
import os
import json
import time
import subprocess
import socket
from datetime import datetime

# --- CONFIGURATION ---
REFRESH_INTERVAL = 5  # Refresh interval in seconds
CHECK_SERVICES = ["docker", "libvirtd", "smbd"]  # Services to monitor
DATA_FILE_PATH = "/opt/kkdash/www/data.json"  # Absolute path to save the data.json file
# ---------------------

def get_cpu_info():
    try:
        # Get CPU usage using a different method
        cmd = "grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage}'"
        usage_val = subprocess.check_output(cmd, shell=True).decode().strip()
        usage = f"{float(usage_val):.1f}%" if usage_val else "0.0%"
        
        # Get CPU model and core count
        model = subprocess.check_output("grep -m 1 'model name' /proc/cpuinfo | cut -d: -f2", shell=True).decode().strip()
        cores = subprocess.check_output("nproc", shell=True).decode().strip()
        
        return {
            "usage": usage,
            "model": model,
            "cores": cores
        }
    except Exception as e:
        return {"usage": "N/A", "model": str(e), "cores": "N/A"}

def get_mount_info():
    try:
        # Get list of mounted filesystems (filtering for real disks and excluding overlay)
        cmd = "df -h --output=source,size,used,avail,pcent,target -x tmpfs -x devtmpfs -x overlay | tail -n +2"
        output = subprocess.check_output(cmd, shell=True).decode().splitlines()
        mounts = []
        for line in output:
            parts = line.split()
            if len(parts) >= 6:
                mounts.append({
                    "source": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "avail": parts[3],
                    "percent": parts[4],
                    "target": parts[5]
                })
        return mounts
    except Exception:
        return []

def get_logged_users():
    try:
        cmd = "who | awk '{print $1}' | sort | uniq | tr '\\n' ' '"
        users = subprocess.check_output(cmd, shell=True).decode().strip().split()
        return users
    except Exception:
        return []

def get_service_status():
    status_map = {}
    for svc in CHECK_SERVICES:
        try:
            cmd = f"systemctl is-active {svc}"
            status = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode().strip()
            status_map[svc] = status
        except subprocess.CalledProcessError as e:
            status_map[svc] = e.output.decode().strip() if e.output else "inactive"
        except Exception:
            status_map[svc] = "unknown"
    return status_map

def get_docker_containers():
    try:
        # Check if docker is installed
        if subprocess.call("command -v docker > /dev/null", shell=True) != 0:
            return None
            
        # Get container name, image, and status
        cmd = "docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}'"
        output = subprocess.check_output(cmd, shell=True).decode().splitlines()
        containers = []
        for line in output:
            parts = line.split('|')
            if len(parts) == 3:
                containers.append({
                    "name": parts[0],
                    "image": parts[1],
                    "status": parts[2]
                })
        return containers
    except Exception:
        return []

def get_memory_info():
    try:
        # Use /proc/meminfo for more reliable parsing
        meminfo = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    meminfo[parts[0].strip()] = parts[1].strip()
        
        total_kb = int(meminfo['MemTotal'].split()[0])
        avail_kb = int(meminfo.get('MemAvailable', '0').split()[0])
        
        total_mb = total_kb // 1024
        used_mb = (total_kb - avail_kb) // 1024
        percent = (used_mb / total_mb) * 100
        
        return {
            "total": f"{total_mb} MB",
            "used": f"{used_mb} MB",
            "percent": f"{percent:.1f}%"
        }
    except Exception:
        return {"total": "N/A", "used": "N/A", "percent": "0%"}

def get_disk_info():
    try:
        cmd = "df -h / | tail -1"
        parts = subprocess.check_output(cmd, shell=True).decode().split()
        return {
            "total": parts[1],
            "used": parts[2],
            "free": parts[3],
            "percent": parts[4]
        }
    except Exception:
        return {"total": "N/A", "used": "N/A", "free": "N/A", "percent": "0%"}

def get_system_info():
    try:
        return {
            "hostname": socket.gethostname(),
            "uptime": subprocess.check_output("uptime -p", shell=True).decode().strip(),
            "kernel": subprocess.check_output("uname -r", shell=True).decode().strip(),
            "os": subprocess.check_output("cat /etc/os-release | grep PRETTY_NAME | cut -d'=' -f2 | tr -d '\"'", shell=True).decode().strip(),
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception:
        return {"hostname": "N/A", "uptime": "N/A", "kernel": "N/A", "os": "N/A", "last_update": "N/A"}

def main():
    print("KKDash Monitor started...")
    while True:
        try:
            data = {
                "cpu": get_cpu_info(),
                "memory": get_memory_info(),
                "disk": get_disk_info(),
                "mounts": get_mount_info(),
                "users": get_logged_users(),
                "services": get_service_status(),
                "docker_containers": get_docker_containers(),
                "system": get_system_info()
            }
            
            # Save with absolute path to ensure service writes to correct location
            # When running as service in /opt/kkdash, this writes to /opt/kkdash/data.json
            # Save to configured path
            with open(DATA_FILE_PATH, 'w') as f:
                json.dump(data, f, indent=4)
                
            
            time.sleep(REFRESH_INTERVAL)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            break
        except Exception as e:
            print(f"Error in monitor loop: {e}")
            time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    main()
