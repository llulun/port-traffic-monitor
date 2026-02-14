#!/bin/bash

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}   主机端口流量监控 一键安装脚本 v1.7   ${NC}"
echo -e "${GREEN}======================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Error: 请使用 root 权限运行此脚本 (例如: bash install.sh)${NC}"
  exit 1
fi

# Detect OS/Package Manager
IS_OPENWRT=0
if [ -f /etc/openwrt_release ] || command -v opkg &> /dev/null; then
    IS_OPENWRT=1
fi

# 1. Install Dependencies
echo -e "\n[1/5] 正在安装系统依赖..."
if [ $IS_OPENWRT -eq 1 ]; then
    echo "检测到 OpenWrt 系统..."
    opkg update
    # Install python3-flask and python3-psutil from repo to save space and avoid compilation
    # git-http is often huge or problematic on routers, so we rely on curl
    opkg install python3 python3-pip curl python3-psutil python3-flask
    
    # Try to open firewall port 8899
    echo "Configuring firewall..."
    if command -v uci &> /dev/null; then
        uci set firewall.traffic_monitor=rule
        uci set firewall.traffic_monitor.name='Allow-Traffic-Monitor'
        uci set firewall.traffic_monitor.src='wan'
        uci set firewall.traffic_monitor.proto='tcp'
        uci set firewall.traffic_monitor.dest_port='8899'
        uci set firewall.traffic_monitor.target='ACCEPT'
        uci commit firewall
        /etc/init.d/firewall reload 2>/dev/null || true
    else
        # Fallback to iptables
        iptables -I INPUT -p tcp --dport 8899 -j ACCEPT 2>/dev/null || true
    fi
elif command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y python3 python3-pip curl
elif command -v yum &> /dev/null; then
    yum install -y python3 python3-pip curl
elif command -v apk &> /dev/null; then
    apk add python3 py3-pip curl
else
    echo -e "${RED}未检测到支持的包管理器 (opkg/apt/yum/apk)，请手动安装 python3, pip 和 curl${NC}"
fi

# 2. Download Files (No Git Required)
INSTALL_DIR="/opt/traffic-monitor"
echo -e "\n[2/5] 正在下载代码..."

# Create dir if not exists
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/static"
mkdir -p "$INSTALL_DIR/templates"
mkdir -p "$INSTALL_DIR/data"
cd "$INSTALL_DIR"

# Download files individually using curl (more robust on routers than git)
BASE_URL="https://raw.githubusercontent.com/llulun/port-traffic-monitor/main"

echo "Downloading app.py..."
curl -s -O "$BASE_URL/app.py"
echo "Downloading requirements.txt..."
curl -s -O "$BASE_URL/requirements.txt"
echo "Downloading templates/index.html..."
curl -s -o "templates/index.html" "$BASE_URL/templates/index.html"

# Verify download
if [ ! -f "app.py" ] || [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: 文件下载失败！请检查网络连接或 GitHub 访问情况。${NC}"
    exit 1
fi

# 3. Install Python Requirements
echo -e "\n[3/5] 正在安装 Python 依赖..."

if [ $IS_OPENWRT -eq 1 ]; then
    # OpenWrt specific:
    # 1. psutil is already installed via opkg (python3-psutil)
    # 2. Flask might be installed via opkg (python3-flask), but if not, we try pip
    # 3. Rich is NOT installed (optional, saves space)
    
    echo "OpenWrt detected: Checking if Flask is installed..."
    if python3 -c "import flask" 2>/dev/null; then
        echo "Flask already installed (via opkg), skipping pip install."
    else
        echo "Flask not found, installing via pip (minimal mode)..."
        # Try to clean cache first to free up space
        rm -rf ~/.cache/pip
        pip3 install flask --no-cache-dir --break-system-packages
    fi
else
    # Standard installation
    pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt
fi

# 4. Configure Service
echo -e "\n[4/5] 配置后台服务..."
PYTHON_PATH=$(which python3)

if [ $IS_OPENWRT -eq 1 ]; then
    # OpenWrt (Procd) Configuration
    cat > /etc/init.d/traffic-monitor <<EOF
#!/bin/sh /etc/rc.common

START=99
STOP=10

USE_PROCD=1
PROG=$PYTHON_PATH
ARGS="$INSTALL_DIR/app.py"

start_service() {
    procd_open_instance
    procd_set_param command \$PROG \$ARGS
    procd_set_param respawn
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_set_param user root
    procd_set_param workdir "$INSTALL_DIR"
    procd_close_instance
}
EOF
    chmod +x /etc/init.d/traffic-monitor
else
    # Systemd Configuration
    cat > /etc/systemd/system/traffic-monitor.service <<EOF
[Unit]
Description=Port Traffic Monitor Web Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_PATH app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
fi

# 5. Start Service
echo -e "\n[5/5] 启动服务..."
if [ $IS_OPENWRT -eq 1 ]; then
    /etc/init.d/traffic-monitor enable
    /etc/init.d/traffic-monitor restart
else
    systemctl daemon-reload
    systemctl enable traffic-monitor
    systemctl restart traffic-monitor
fi

# Final Output
if command -v hostname &> /dev/null && hostname -I &> /dev/null; then
    IP=$(hostname -I | awk '{print $1}')
else
    # Fallback for OpenWrt or minimal systems
    IP="<服务器IP>"
fi

echo -e "\n${GREEN}======================================${NC}"
echo -e "${GREEN}🎉 安装成功！${NC}"
echo -e "🏠 访问地址: http://$IP:8899"
echo -e "📂 安装目录: $INSTALL_DIR"
if [ $IS_OPENWRT -eq 1 ]; then
    echo -e "⚙️ 服务管理: /etc/init.d/traffic-monitor {start|stop|restart}"
else
    echo -e "⚙️ 服务管理: systemctl status traffic-monitor"
fi
echo -e "${GREEN}======================================${NC}"
