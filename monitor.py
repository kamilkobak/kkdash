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

# Global state for CPU calculation
prev_cpu_times = None

def get_cpu_info():
    global prev_cpu_times
    try:
        # Read /proc/stat
        with open('/proc/stat', 'r') as f:
            line = f.readline()
        
        if not line.startswith('cpu '):
            return {"usage": "N/A", "model": "Error reading /proc/stat", "cores": "N/A"}
        
        # Parse CPU times: user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
        parts = [float(x) for x in line.split()[1:]]
        idle_time = parts[3] + parts[4]  # idle + iowait
        non_idle_time = parts[0] + parts[1] + parts[2] + parts[5] + parts[6] + parts[7]
        total_time = idle_time + non_idle_time
        
        usage = "0.0%"
        if prev_cpu_times is not None:
            prev_total, prev_idle = prev_cpu_times
            total_delta = total_time - prev_total
            idle_delta = idle_time - prev_idle
            
            if total_delta > 0:
                usage_pct = (total_delta - idle_delta) / total_delta * 100
                usage = f"{max(0, min(100, usage_pct)):.1f}%"
        
        prev_cpu_times = (total_time, idle_time)
        
        # Get CPU model and core count
        model = subprocess.check_output("grep -m 1 'model name' /proc/cpuinfo | cut -d: -f1,2 --complement", shell=True).decode().strip()
        if not model: # Some ARM systems use 'Processor' instead of 'model name'
             model = subprocess.check_output("grep -m 1 'Processor' /proc/cpuinfo | cut -d: -f2", shell=True).decode().strip()
             
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

def get_ufw_stats():
    try:
        # Check if UFW is installed and active
        try:
            status_output = subprocess.check_output("ufw status", shell=True).decode().strip()
            is_active = "Status: active" in status_output
        except Exception:
            is_active = False

        if not is_active:
            return {"active": False, "top_blocked": [], "ports": {}}

        # Get lines containing [UFW BLOCK] from dmesg
        cmd = "dmesg | grep '\[UFW BLOCK\]' | tail -n 1000"
        try:
            output = subprocess.check_output(cmd, shell=True).decode().splitlines()
        except subprocess.CalledProcessError:
            # grep returns 1 if no matches found
            output = []
        
        blocks = []
        port_counts = {}
        pair_counts = {}
        
        for line in output:
            import re
            src_match = re.search(r'SRC=([^\s]+)', line)
            dpt_match = re.search(r'DPT=([^\s]+)', line)
            
            if src_match and dpt_match:
                src = src_match.group(1)
                dpt = dpt_match.group(1)
                
                # Count pairs for the table
                pair = f"{src}|{dpt}"
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
                
                # Count ports for the chart
                port_counts[dpt] = port_counts.get(dpt, 0) + 1
        
        # Sort and get top 10 pairs
        top_pairs_raw = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_blocked = []
        for p_str, count in top_pairs_raw:
            ip, port = p_str.split('|')
            top_blocked.append({"ip": ip, "port": port, "count": count})
        
        # Sort and get top ports (for better visualization)
        top_ports = dict(sorted(port_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        
        return {
            "active": True,
            "top_blocked": top_blocked,
            "ports": top_ports
        }
    except Exception as e:
        return {"active": False, "top_blocked": [], "ports": {}}

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
                "system": get_system_info(),
                "ufw": get_ufw_stats()
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
