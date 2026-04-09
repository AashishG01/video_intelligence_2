import time
import psutil
import subprocess
import redis
import csv
import os

# Connect to Redis
print("⏳ Connecting to Redis...")
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
except Exception as e:
    print(f"❌ Redis Connection Failed: {e}")
    exit(1)

def get_gpu_metrics():
    """Uses nvidia-smi to get GPU utilization and VRAM usage."""
    try:
        result = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits']
        )
        # Output format: "47, 10339, 49140"
        stats = result.decode('utf-8').strip().split(', ')
        return int(stats[0]), int(stats[1]), int(stats[2])
    except Exception as e:
        return 0, 0, 0

csv_filename = 'benchmark_hardware_report.csv'
print(f"✅ Monitor Active. Recording data to {csv_filename}...")
print("🛑 Press Ctrl+C to stop monitoring when your test finishes.\n")
print("-" * 100)
print(f"{'TIME':<8} | {'CPU %':<7} | {'RAM (GB)':<10} | {'GPU %':<7} | {'VRAM (GB)':<10} | {'RAW Q':<7} | {'READY Q':<7}")
print("-" * 100)

with open(csv_filename, 'w', newline='') as f:
    writer = csv.writer(f)
    # Write CSV Header
    writer.writerow(['Time_Seconds', 'CPU_Percent', 'RAM_GB', 'GPU_Util_Percent', 'VRAM_Used_GB', 'Raw_Frames_Queue', 'Face_Ready_Queue'])

    start_time = time.time()
    
    try:
        while True:
            elapsed = time.time() - start_time
            
            # System Metrics
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().used / (1024**3) # Convert to GB
            
            # GPU Metrics
            gpu_util, vram_used, vram_total = get_gpu_metrics()
            vram_used_gb = vram_used / 1024 # Convert MB to GB
            
            # Redis Queue Metrics
            raw_q = r.llen("bench_raw_frames")
            ready_q = r.llen("bench_face_ready")
            
            # Save to CSV
            writer.writerow([round(elapsed, 1), cpu, round(ram, 2), gpu_util, round(vram_used_gb, 2), raw_q, ready_q])
            
            # Print to Terminal
            print(f"{elapsed:>6.1f}s | {cpu:>6.1f}% | {ram:>7.2f} GB | {gpu_util:>5}% | {vram_used_gb:>7.2f} GB | {raw_q:>5} | {ready_q:>5}")
            
            time.sleep(1) # Record snapshot every 1 second
            
    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print(f"🏁 Monitoring Stopped. Data successfully saved to '{csv_filename}'.")
        print("💡 Pro Tip: Open this CSV in Excel/Google Sheets to plot your performance graphs!")
        print("=" * 50)