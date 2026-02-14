#!/bin/bash

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}   主机端口流量监控 一键安装脚本   ${NC}"
echo -e "${GREEN}======================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Error: 请使用 root 权限运行此脚本 (sudo bash install.sh)${NC}"
  exit 1
fi

# 1. Install Dependencies
echo -e "\n[1/5] 正在安装系统依赖..."
if command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y python3 python3-pip git
elif command -v yum &> /dev/null; then
    yum install -y python3 python3-pip git
elif command -v apk &> /dev/null; then
    apk add python3 py3-pip git
else
    echo -e "${RED}未检测到支持的包管理器 (apt/yum/apk)，请手动安装 python3 和 git${NC}"
fi

# 2. Clone/Update Repository
INSTALL_DIR="/opt/traffic-monitor"
echo -e "\n[2/5] 正在下载/更新代码..."
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    git pull
else
    git clone https://github.com/llulun/port-traffic-monitor.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create data directory
mkdir -p data

# 3. Install Python Requirements
echo -e "\n[3/5] 正在安装 Python 依赖..."
# Try standard pip, fallback to --break-system-packages for newer OS
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

# 4. Configure Systemd Service
echo -e "\n[4/5] 配置后台服务..."
PYTHON_PATH=$(which python3)

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

# 5. Start Service
echo -e "\n[5/5] 启动服务..."
systemctl daemon-reload
systemctl enable traffic-monitor
systemctl restart traffic-monitor

# Final Output
IP=$(hostname -I | awk '{print $1}')
echo -e "\n${GREEN}======================================${NC}"
echo -e "${GREEN}🎉 安装成功！${NC}"
echo -e "🏠 访问地址: http://$IP:8899"
echo -e "📂 安装目录: $INSTALL_DIR"
echo -e "⚙️ 服务状态: systemctl status traffic-monitor"
echo -e "${GREEN}======================================${NC}"
