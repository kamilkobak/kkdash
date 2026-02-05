#!/bin/bash
# Author: Kamil Kobak
# License: GPL-3.0

ACTION=$1

if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root (sudo)"
  exit 1
fi

install_app() {
    echo "Installing KKDash..."

    # 1. Create directory structure
    mkdir -p /opt/kkdash/bin
    mkdir -p /opt/kkdash/www
    echo "Created /opt/kkdash/bin and /opt/kkdash/www"
    
    # 2. Copy files
    cp monitor.py /opt/kkdash/bin/
    cp index.html style.css /opt/kkdash/www/
    echo "Copied files to /opt/kkdash/bin and /opt/kkdash/www"

    # 3. Configure monitor.py for the service
    # We update the DATA_FILE_PATH to be relative to the WorkingDirectory in the service
    # or just use an absolute path in the config. Let's use WorkingDirectory approach.

    # 4. Check Python3
    if ! command -v python3 &> /dev/null; then
        echo "Python3 could not be found."
        echo "Please install it using: sudo apt install python3"
        exit 1
    fi
    echo "Python3 detected."

    # 5. Create Service
    cat <<EOF > /etc/systemd/system/kkdash.service
[Unit]
Description=KKDash System Monitor Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/kkdash/www
ExecStart=/usr/bin/python3 /opt/kkdash/bin/monitor.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

    echo "Created /etc/systemd/system/kkdash.service"

    # Reload and Start
    systemctl daemon-reload
    systemctl enable kkdash
    systemctl start kkdash
    
    systemctl status kkdash --no-pager

    echo ""
    echo "========================================================"
    echo "To serve the dashboard via Web, run this minimal Docker Nginx:"
    echo "sudo docker run -d --name kkdash-web --restart always -v /opt/kkdash/www:/usr/share/nginx/html:ro -p 8080:80 nginx:alpine"
    echo "Then access: http://localhost:8080"
    echo "========================================================"
}

upgrade_app() {
    echo "Upgrading KKDash files..."

    if [ ! -d "/opt/kkdash" ]; then
        echo "Error: /opt/kkdash does not exist. Please install first."
        exit 1
    fi

    mkdir -p /opt/kkdash/bin
    mkdir -p /opt/kkdash/www

    cp monitor.py /opt/kkdash/bin/
    cp index.html /opt/kkdash/www/
    cp style.css /opt/kkdash/www/
    
    # Cleanup old data.json location
    rm -f /opt/kkdash/data.json
    
    echo "Files updated in /opt/kkdash/bin and /opt/kkdash/www"

    systemctl restart kkdash
    echo "Restarted kkdash service"
    
    systemctl status kkdash --no-pager
}

uninstall_app() {
    echo "Uninstalling KKDash..."

    # 1. Stop and remove service
    if systemctl is-active --quiet kkdash; then
        systemctl stop kkdash
        echo "Stopped kkdash service"
    fi
    
    if systemctl is-enabled --quiet kkdash; then
        systemctl disable kkdash
        echo "Disabled kkdash service"
    fi

    if [ -f "/etc/systemd/system/kkdash.service" ]; then
        rm /etc/systemd/system/kkdash.service
        systemctl daemon-reload
        echo "Removed service file"
    fi

    # 2. Delete directory
    if [ -d "/opt/kkdash" ]; then
        rm -rf /opt/kkdash
        echo "Removed /opt/kkdash"
    fi

    echo "KKDash successfully uninstalled."
}

if [ "$ACTION" == "install" ]; then
    install_app
elif [ "$ACTION" == "upgrade" ]; then
    upgrade_app
elif [ "$ACTION" == "uninstall" ]; then
    uninstall_app
else
    echo "Usage: $0 {install|upgrade|uninstall}"
    exit 1
fi
