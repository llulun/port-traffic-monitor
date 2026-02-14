import psutil
import time
import json
import os
import sys
from datetime import datetime
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.console import Console
from rich import box

# Configuration
PORT = 7788
DATA_FILE = "traffic_stats.json"
UPDATE_INTERVAL = 1  # seconds

class TrafficMonitor:
    def __init__(self):
        self.console = Console()
        self.data = self.load_data()
        self.current_speed_up = 0
        self.current_speed_down = 0
        self.active_pids = []
        
    def load_data(self):
        """Load stats from JSON file."""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.console.print(f"[red]Error loading data: {e}[/red]")
        
        return {
            "total_upload": 0,
            "total_download": 0,
            "total_online_seconds": 0,
            "daily_stats": {},
            "process_states": {}  # key: "pid_createtime", value: {read: X, write: Y}
        }

    def save_data(self):
        """Save stats to JSON file."""
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            pass # Avoid crashing on save error

    def get_target_pids(self):
        """Find PIDs listening on the target port."""
        pids = set()
        try:
            # psutil.net_connections requires root/admin on some OS, but usually fine for own processes
            connections = psutil.net_connections(kind='inet')
            for conn in connections:
                if conn.laddr.port == PORT:
                    if conn.pid:
                        pids.add(conn.pid)
        except psutil.AccessDenied:
            pass
        except Exception:
            pass
        return list(pids)

    def update(self):
        """Main update logic."""
        pids = self.get_target_pids()
        self.active_pids = pids
        
        # Current time for daily stats
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.data["daily_stats"]:
            self.data["daily_stats"][today] = {
                "upload": 0,
                "download": 0,
                "online_seconds": 0,
                "first_seen": time.time(),
                "last_seen": time.time()
            }
            
        daily = self.data["daily_stats"][today]
        daily["last_seen"] = time.time()
        
        if pids:
            daily["online_seconds"] += UPDATE_INTERVAL
            self.data["total_online_seconds"] += UPDATE_INTERVAL

        total_delta_up = 0
        total_delta_down = 0
        
        active_keys = set()

        for pid in pids:
            try:
                p = psutil.Process(pid)
                # Unique key for this process instance
                key = f"{pid}_{int(p.create_time())}"
                active_keys.add(key)
                
                # Get IO counters (cumulative)
                io = p.io_counters()
                curr_read = io.read_bytes
                curr_write = io.write_bytes
                
                # Retrieve last state
                last_state = self.data["process_states"].get(key, {"read": 0, "write": 0})
                last_read = last_state["read"]
                last_write = last_state["write"]
                
                # Calculate delta
                # If this is a new process (not in state), delta is full current value?
                # No, if it's new to our tracking, we should start delta from 0 
                # UNLESS we want to catch up on missed traffic (offline monitoring).
                # Logic:
                # If key NOT in process_states: 
                #    It's a "freshly discovered" process.
                #    We don't know if it started just now or long ago.
                #    BUT, if we assume we monitor continuously, any "jump" is traffic.
                #    However, if we just started script and process has 1GB, we shouldn't add 1GB instantly.
                #    We should only count traffic *while monitoring*.
                #    Wait, my previous thought about "catch up" works if we persist state.
                #    If we have state in JSON, we catch up.
                #    If we DON'T have state (new key), we set baseline to current.
                
                if key not in self.data["process_states"]:
                    # Initialize baseline, don't count existing traffic as new delta
                    delta_read = 0
                    delta_write = 0
                else:
                    delta_read = curr_read - last_read
                    delta_write = curr_write - last_write
                
                # Sanity check for negative delta (shouldn't happen with correct keys)
                if delta_read < 0: delta_read = 0
                if delta_write < 0: delta_write = 0
                
                # Update totals
                self.data["total_download"] += delta_read
                self.data["total_upload"] += delta_write
                
                daily["download"] += delta_read
                daily["upload"] += delta_write
                
                total_delta_down += delta_read
                total_delta_up += delta_write
                
                # Update state
                self.data["process_states"][key] = {
                    "read": curr_read,
                    "write": curr_write
                }
                
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                
        # Clean up old process states
        # We only keep keys that are currently active to prevent JSON from growing indefinitely?
        # OR we keep them to allow "catch up" if process restarts?
        # If process restarts, key changes. So old keys are useless unless we want history.
        # But we aggregated history into "total_download" etc.
        # So we can safely remove keys that are not in active_keys.
        # WAIT: If monitoring loop is faster than process restart?
        # No, key contains create_time.
        # So if process is gone, its key is obsolete.
        # We can remove keys not in active_keys.
        
        keys_to_remove = []
        for k in self.data["process_states"]:
            if k not in active_keys:
                keys_to_remove.append(k)
        for k in keys_to_remove:
            del self.data["process_states"][k]

        self.current_speed_down = total_delta_down / UPDATE_INTERVAL
        self.current_speed_up = total_delta_up / UPDATE_INTERVAL
        
        self.save_data()

    def format_bytes(self, size):
        power = 2**10
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return f"{size:.2f} {power_labels.get(n, '')}B"

    def format_time(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"

    def generate_layout(self):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        return layout

    def generate_table(self):
        table = Table(box=box.ROUNDED, expand=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        # Real-time
        table.add_row("Status", "[green]Running[/green]" if self.active_pids else "[red]Waiting for Process...[/red]")
        table.add_row("Monitored Port", str(PORT))
        table.add_row("Active PIDs", ", ".join(map(str, self.active_pids)))
        table.add_section()
        
        # Speed
        table.add_row("Current Upload Speed", f"{self.format_bytes(self.current_speed_up)}/s")
        table.add_row("Current Download Speed", f"{self.format_bytes(self.current_speed_down)}/s")
        table.add_section()
        
        # Today
        today = datetime.now().strftime("%Y-%m-%d")
        daily = self.data["daily_stats"].get(today, {"upload": 0, "download": 0, "online_seconds": 0})
        
        table.add_row("Today Upload", self.format_bytes(daily["upload"]))
        table.add_row("Today Download", self.format_bytes(daily["download"]))
        table.add_row("Today Online Time", self.format_time(daily["online_seconds"]))
        table.add_section()
        
        # Total
        table.add_row("Total Upload", self.format_bytes(self.data["total_upload"]))
        table.add_row("Total Download", self.format_bytes(self.data["total_download"]))
        table.add_row("Total Online Time", self.format_time(self.data["total_online_seconds"]))
        
        return Panel(table, title=f"Traffic Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", border_style="blue")

    def run(self):
        layout = self.generate_layout()
        with Live(layout, refresh_per_second=1, screen=True) as live:
            while True:
                self.update()
                layout["main"].update(self.generate_table())
                time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    # Check permissions
    try:
        psutil.net_connections()
    except psutil.AccessDenied:
        print("Warning: Access Denied. Please run as Administrator.")
        # sys.exit(1) # Try to continue anyway, maybe process ownership is enough
    
    monitor = TrafficMonitor()
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("Stopping monitor...")
