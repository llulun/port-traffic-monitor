# 🌐 主机端口流量监控面板 (Port Traffic Monitor)

一个轻量级、功能强大的 Web 监控面板，用于实时监控主机指定端口的流量、连接数和进程状态。专为 SS/SSR 节点、Web 服务器或数据库端口监控设计。

![Screenshot](https://via.placeholder.com/800x400?text=Traffic+Monitor+Preview)

## ✨ 主要功能

- **📊 实时流量监控**：毫秒级响应的上传/下载速度显示。
- **📈 24小时趋势图**：每分钟聚合数据，清晰展示全天流量波动。
- **📅 历史数据统计**：自动记录每日流量消耗（支持保留最近7天）。
- **🔍 进程与连接**：显示占用端口的进程名称 (PID) 及活跃 TCP 连接数。
- **💻 系统资源**：实时显示服务器 CPU 和内存使用率。
- **📝 事件日志**：记录端口添加/删除、进程启停等关键系统事件。
- **📂 数据导出**：支持一键导出 CSV 格式的历史流量数据。
- **⚙️ 动态管理**：无需重启，在网页端即可添加、删除或切换监控端口。

---

## 🚀 极速部署 (One-Click Deploy)

**复制下面的完整命令块**，直接在服务器终端粘贴运行：

```bash
docker run -d \
  --name traffic-monitor \
  --network host \
  --restart always \
  -v $(pwd)/traffic-data:/app/data \
  ghcr.io/llulun/port-traffic-monitor:latest
```

> **说明**：
> *   `--network host`：让容器共享宿主机网络，从而能监控宿主机端口流量。
> *   `-v $(pwd)/traffic-data:/app/data`：将数据文件挂载到当前目录下的 `traffic-data` 文件夹，防止数据丢失。

> **🔴 无法拉取镜像 (Permission Denied)?**
> 默认情况下 GitHub Packages 可能是私有的。请前往 GitHub 仓库页面 -> 右侧 "Packages" -> 点击包名 -> "Package settings" -> "Change visibility" -> 设置为 **Public**。

---

## 💻 本地开发

### 方式一：直接运行 (Python)

1.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

2.  **启动服务**
    ```bash
    python app.py
    ```

3.  **访问面板**
    打开浏览器访问 `http://服务器IP:8899`

---

### 方式二：Docker 部署 (推荐)

我们提供了 `docker-compose` 配置，支持一键部署。由于需要监控宿主机网络，必须使用 `network_mode: host`。

1.  **构建并启动**
    ```bash
    docker-compose up -d
    ```

2.  **查看日志**
    ```bash
    docker-compose logs -f
    ```

3.  **停止服务**
    ```bash
    docker-compose down
    ```

**注意**：
*   容器必须以 `privileged` 或 `pid: host` 模式运行才能获取宿主机的进程信息（本配置已默认包含）。
*   数据文件 `traffic_stats.json` 和 `config.json` 会挂载到当前目录，确保数据持久化。

---

## 🛠️ 配置说明

*   **默认端口**：`8899` (Web 面板端口)
*   **初始监控端口**：`7788` (首次启动默认监控的业务端口，可在页面修改)
*   **数据文件**：
    *   `config.json`: 存储监控的端口列表。
    *   `traffic_stats.json`: 存储所有的流量统计数据。

## 📸 界面预览

*   **多端口切换**：顶部下拉菜单快速切换不同端口视图。
*   **深色模式**：支持一键切换日间/夜间模式。
*   **数据重置**：支持单独清空某个端口的历史数据。

---

## ⚠️ 常见问题

**Q: 为什么显示的进程名是 "unknown"?**
A: 可能是因为权限不足。请确保以 root 用户运行脚本，或在 Docker 中开启了 `pid: host`。

**Q: 在线时长不准确？**
A: 在线时长仅在**检测到有流量传输**（上传或下载 > 0）时才会增加，纯挂机（无流量）不计入时长。

---

**License**: MIT
