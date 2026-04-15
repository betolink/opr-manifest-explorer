import subprocess
import time
import sys
import signal
import os

# Start panel serve
cmd = [
    sys.executable,
    "-m",
    "panel",
    "serve",
    "explorer.py",
    "--port",
    "0",
    "--autoreload",
    "off",
]
proc = subprocess.Popen(
    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)

try:
    # Wait for startup message or timeout
    for _ in range(30):
        line = proc.stdout.readline()
        if not line:
            break
        print(line, end="")
        if "Starting Bokeh server" in line or "Server started" in line:
            print("Server started successfully")
            break
        if "error" in line.lower():
            print("Error detected")
            break
    else:
        print("Timeout waiting for server start")
finally:
    # Kill the process
    proc.terminate()
    proc.wait(timeout=5)
    print("Test completed")
