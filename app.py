import psutil
import time
import json
import os
import threading
import csv
import io
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response, send_from_directory

# Configuration
DEFAULT_PORT = 7788
DATA_FILE = "traffic_stats.json"
CONFIG_FILE = "config.json"
UPDATE_INTERVAL = 1

app = Flask(__name__)

@app.route('/favicon.ico')
def favicon():
    return "", 204

class TrafficMonitor:
    def __init__(self):
        self.config = self.load_config()
        self.ports = set(self.config.get("ports", [DEFAULT_PORT]))
        self.data = self.load_data()
        
        # Runtime states
        self.current_stats = {
            port: {"up": 0, "down": 0, "pids": [], "process_names": [], "connections": 0} 
            for port in self.ports
        }
        self.lock = threading.Lock()
        
        # Traffic Series (24h history with 1-minute resolution)
        # Format: {"7788": [{"time": "HH:MM", "up": X, "down": Y}, ...]}
        if "traffic_series" not in self.data:
            self.data["traffic_series"] = {}
        elif isinstance(self.data["traffic_series"], list): # Migration: convert old list format to dict
            old_series = self.data["traffic_series"]
            self.data["traffic_series"] = {str(DEFAULT_PORT): old_series}
            
        # Ensure series dict exists for all ports
        for port in self.ports:
            if str(port) not in self.data["traffic_series"]:
                self.data["traffic_series"][str(port)] = []

        # Temporary bucket for minute aggregation
        self.minute_buckets = {}
        self.reset_buckets()
        
        # In-memory Event Log (Keep last 50 events)
        self.event_log = []
        self.log_event("系统", "监控服务已启动")

    def log_event(self, source, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.event_log.insert(0, {"time": timestamp, "source": source, "message": message})
        if len(self.event_log) > 50:
            self.event_log.pop()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"ports": [DEFAULT_PORT]}

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump({"ports": list(self.ports)}, f, indent=4)
        except:
            pass

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading data: {e}")
        
        return {
            "daily_stats": {},     # { "2023-10-01": { "7788": { "upload": 0... } } }
            "process_states": {},  # { "pid_createtime": { "read": X, "write": Y } }
            "total_stats": {},     # { "7788": { "upload": 0, "download": 0, "online": 0 } }
            "traffic_series": {}
        }

    def save_data(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception:
            pass

    def add_port(self, port):
        with self.lock:
            port = int(port)
            if port not in self.ports:
                self.ports.add(port)
                self.current_stats[port] = {"up": 0, "down": 0, "pids": [], "process_names": [], "connections": 0}
                if str(port) not in self.data["traffic_series"]:
                    self.data["traffic_series"][str(port)] = []
                self.save_config()
                self.log_event("系统", f"添加监控端口 {port}")
                return True
        return False

    def remove_port(self, port):
        with self.lock:
            port = int(port)
            if port in self.ports and len(self.ports) > 1: # Prevent removing last port
                self.ports.remove(port)
                if port in self.current_stats:
                    del self.current_stats[port]
                self.save_config()
                self.log_event("系统", f"移除监控端口 {port}")
                return True
        return False

    def reset_buckets(self):
        current_min = datetime.now().minute
        for port in self.ports:
            if str(port) not in self.minute_buckets:
                self.minute_buckets[str(port)] = {
                    "up": 0, "down": 0, "count": 0, "last_minute": current_min
                }

    def get_port_pids_and_conns(self):
        port_info = {port: {"pids": set(), "conns": 0} for port in self.ports}
        try:
            connections = psutil.net_connections(kind='inet')
            for conn in connections:
                if conn.laddr.port in self.ports:
                    # Count ESTABLISHED connections
                    if conn.status == psutil.CONN_ESTABLISHED:
                         port_info[conn.laddr.port]["conns"] += 1
                         
                    if conn.pid:
                        port_info[conn.laddr.port]["pids"].add(conn.pid)
        except Exception:
            pass
        
        # Convert set to list
        return {
            k: {"pids": list(v["pids"]), "conns": v["conns"]} 
            for k, v in port_info.items()
        }

    def update_loop(self):
        while True:
            self.update()
            time.sleep(UPDATE_INTERVAL)

    def update(self):
        port_info_map = self.get_port_pids_and_conns()
        
        with self.lock:
            today = datetime.now().strftime("%Y-%m-%d")
            current_minute = datetime.now().minute
            
            # Initialize daily stats structure
            if today not in self.data["daily_stats"]:
                self.data["daily_stats"][today] = {}
            
            # Initialize total stats structure
            if "total_stats" not in self.data:
                self.data["total_stats"] = {}

            active_keys = set()
            
            for port in self.ports:
                str_port = str(port)
                info = port_info_map.get(port, {"pids": [], "conns": 0})
                pids = info["pids"]
                
                # Detect state changes for logging
                prev_pids = self.current_stats[port]["pids"]
                if not prev_pids and pids:
                    self.log_event(f"Port {port}", "检测到活动进程")
                elif prev_pids and not pids:
                    self.log_event(f"Port {port}", "进程已停止/断开")

                self.current_stats[port]["pids"] = pids
                self.current_stats[port]["connections"] = info["conns"]
                self.current_stats[port]["process_names"] = [] # will fill below
                
                # Init stats for this port if missing
                if str_port not in self.data["daily_stats"][today]:
                    self.data["daily_stats"][today][str_port] = {
                        "upload": 0, "download": 0, "online_seconds": 0
                    }
                if str_port not in self.data["total_stats"]:
                    self.data["total_stats"][str_port] = {
                        "upload": 0, "download": 0, "online_seconds": 0
                    }
                if str_port not in self.minute_buckets: # Handle newly added ports
                    self.minute_buckets[str_port] = {
                        "up": 0, "down": 0, "count": 0, "last_minute": current_minute
                    }

                daily = self.data["daily_stats"][today][str_port]
                total = self.data["total_stats"][str_port]

                port_delta_up = 0
                port_delta_down = 0

                for pid in pids:
                    try:
                        p = psutil.Process(pid)
                        # Collect process name
                        try:
                            proc_name = p.name()
                            if proc_name not in self.current_stats[port]["process_names"]:
                                self.current_stats[port]["process_names"].append(proc_name)
                        except:
                            pass
                        
                        key = f"{pid}_{int(p.create_time())}"
                        active_keys.add(key)
                        
                        io = p.io_counters()
                        curr_read = io.read_bytes
                        curr_write = io.write_bytes
                        
                        last_state = self.data["process_states"].get(key, {"read": 0, "write": 0})
                        
                        if key not in self.data["process_states"]:
                            delta_read = 0
                            delta_write = 0
                        else:
                            delta_read = curr_read - last_state["read"]
                            delta_write = curr_write - last_state["write"]
                        
                        if delta_read < 0: delta_read = 0
                        if delta_write < 0: delta_write = 0
                        
                        port_delta_up += delta_write
                        port_delta_down += delta_read
                        
                        self.data["process_states"][key] = {
                            "read": curr_read,
                            "write": curr_write
                        }
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                if port_delta_up > 0 or port_delta_down > 0:
                    daily["online_seconds"] += UPDATE_INTERVAL
                    total["online_seconds"] += UPDATE_INTERVAL

                # Update accumulated stats
                daily["upload"] += port_delta_up
                daily["download"] += port_delta_down
                total["upload"] += port_delta_up
                total["download"] += port_delta_down
                
                # Update current speed
                self.current_stats[port]["up"] = port_delta_up / UPDATE_INTERVAL
                self.current_stats[port]["down"] = port_delta_down / UPDATE_INTERVAL
                
                # --- Minute Aggregation for 24h Trend ---
                bucket = self.minute_buckets[str_port]
                bucket["up"] += self.current_stats[port]["up"]
                bucket["down"] += self.current_stats[port]["down"]
                bucket["count"] += 1
                
                if current_minute != bucket["last_minute"]:
                    if bucket["count"] > 0:
                        avg_up = bucket["up"] / bucket["count"]
                        avg_down = bucket["down"] / bucket["count"]
                        timestamp = datetime.now().strftime("%H:%M")
                        
                        if str_port not in self.data["traffic_series"]:
                             self.data["traffic_series"][str_port] = []
                             
                        self.data["traffic_series"][str_port].append({
                            "time": timestamp,
                            "up": avg_up,
                            "down": avg_down,
                            "full_time": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                        
                        # Keep last 1440 points
                        if len(self.data["traffic_series"][str_port]) > 1440:
                            self.data["traffic_series"][str_port] = self.data["traffic_series"][str_port][-1440:]
                    
                    # Reset bucket
                    self.minute_buckets[str_port] = {
                        "up": 0, "down": 0, "count": 0, "last_minute": current_minute
                    }

            # Clean up old process states
            keys_to_remove = [k for k in self.data["process_states"] if k not in active_keys]
            for k in keys_to_remove:
                del self.data["process_states"][k]
            
            self.save_data()

    def get_system_stats(self):
        """Get global system resource usage"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent
        }

    def reset_port_data(self, port):
        with self.lock:
            port = int(port)
            str_port = str(port)
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Reset daily
            if today in self.data["daily_stats"] and str_port in self.data["daily_stats"][today]:
                self.data["daily_stats"][today][str_port] = {
                    "upload": 0, "download": 0, "online_seconds": 0
                }
            
            # Reset total
            if "total_stats" in self.data and str_port in self.data["total_stats"]:
                self.data["total_stats"][str_port] = {
                    "upload": 0, "download": 0, "online_seconds": 0
                }
                
            # Reset series
            if str_port in self.data["traffic_series"]:
                self.data["traffic_series"][str_port] = []
            
            self.save_data()
            self.log_event(f"Port {port}", "数据已重置")
            return True

    def get_port_stats(self, port):
        with self.lock:
            port = int(port)
            str_port = str(port)
            today = datetime.now().strftime("%Y-%m-%d")
            
            daily = {"upload": 0, "download": 0, "online_seconds": 0}
            if today in self.data["daily_stats"] and str_port in self.data["daily_stats"][today]:
                daily = self.data["daily_stats"][today][str_port]
                
            total = {"upload": 0, "download": 0, "online_seconds": 0}
            if "total_stats" in self.data and str_port in self.data["total_stats"]:
                total = self.data["total_stats"][str_port]
            
            curr = self.current_stats.get(port, {"up": 0, "down": 0, "pids": [], "process_names": [], "connections": 0})
            
            return {
                "port": port,
                "active_pids": curr["pids"],
                "process_names": curr["process_names"],
                "connections": curr["connections"],
                "current_speed_up": curr["up"],
                "current_speed_down": curr["down"],
                "total_upload": total["upload"],
                "total_download": total["download"],
                "total_online_seconds": total["online_seconds"],
                "today_upload": daily["upload"],
                "today_download": daily["download"],
                "today_online_seconds": daily["online_seconds"]
            }

    def get_all_ports_summary(self):
        with self.lock:
            return list(self.ports)
            
    def get_logs(self):
        return self.event_log

# Initialize Monitor
monitor = TrafficMonitor()

# Start background thread
thread = threading.Thread(target=monitor.update_loop, daemon=True)
thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/ports')
def get_ports():
    return jsonify(monitor.get_all_ports_summary())

@app.route('/api/ports', methods=['POST'])
def add_port():
    data = request.json
    if 'port' in data:
        try:
            port = int(data['port'])
            if 1 <= port <= 65535:
                if monitor.add_port(port):
                    return jsonify({"success": True, "message": f"Port {port} added"})
                else:
                    return jsonify({"success": False, "message": "Port already exists"})
            else:
                return jsonify({"success": False, "message": "Invalid port number"})
        except ValueError:
            return jsonify({"success": False, "message": "Port must be a number"})
    return jsonify({"success": False, "message": "Missing port parameter"}), 400

@app.route('/api/ports/<int:port>', methods=['DELETE'])
def delete_port(port):
    if monitor.remove_port(port):
        return jsonify({"success": True, "message": f"Port {port} removed"})
    else:
        return jsonify({"success": False, "message": "Could not remove port (maybe it's the last one?)"}), 400

@app.route('/api/system')
def system_stats():
    return jsonify(monitor.get_system_stats())

@app.route('/api/logs')
def get_logs():
    return jsonify(monitor.get_logs())

@app.route('/api/export/<int:port>')
def export_history(port):
    str_port = str(port)
    data = monitor.data.get("daily_stats", {})
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Upload (Bytes)', 'Download (Bytes)', 'Online Seconds'])
    
    # Sort dates descending
    dates = sorted(data.keys(), reverse=True)
    
    for date in dates:
        if str_port in data[date]:
            day_data = data[date][str_port]
            writer.writerow([
                date, 
                day_data['upload'], 
                day_data['download'], 
                day_data['online_seconds']
            ])
            
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=traffic_history_port_{port}.csv"}
    )

@app.route('/api/stats/<int:port>', methods=['DELETE'])
def reset_stats(port):
    if monitor.reset_port_data(port):
        return jsonify({"success": True, "message": f"Stats for port {port} reset"})
    return jsonify({"success": False, "message": "Failed to reset"}), 400

@app.route('/api/stats/<int:port>')
def stats(port):
    return jsonify(monitor.get_port_stats(port))

@app.route('/api/series/<int:port>')
def series(port):
    return jsonify(monitor.data.get("traffic_series", {}).get(str(port), []))

@app.route('/api/history/<int:port>')
def history(port):
    # Extract history for specific port from daily_stats
    # Structure: daily_stats = { "date": { "port": { ... } } }
    # Output needed: { "date": { "upload": X, "download": Y } }
    history_data = {}
    str_port = str(port)
    for date, ports_data in monitor.data.get("daily_stats", {}).items():
        if str_port in ports_data:
            history_data[date] = ports_data[str_port]
    return jsonify(history_data)

if __name__ == '__main__':
    print("Starting Web Monitor on http://0.0.0.0:8899")
    app.run(host='0.0.0.0', port=8899, debug=False)
