#!/usr/bin/env python3
import json
import sys
import subprocess
import time
import threading

def read_stderr(proc):
    """Read and print stderr in a separate thread."""
    for line in proc.stderr:
        print("Server:", line.strip(), file=sys.stderr)

def send_request(proc, request):
    """Send a JSON-RPC request to the server process."""
    request_str = json.dumps(request) + "\n"
    print("Sending:", request_str.strip(), file=sys.stderr)
    proc.stdin.write(request_str)
    proc.stdin.flush()
    
    # Read until we get a complete JSON response
    response = ""
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        response += line
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            continue

def main():
    # Start the server process
    proc = subprocess.Popen(
        ["python", "main.py", "--transport", "stdio", "--debug"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    # Start a thread to read stderr
    stderr_thread = threading.Thread(target=read_stderr, args=(proc,), daemon=True)
    stderr_thread.start()

    try:
        # Wait a bit for the server to start
        time.sleep(1)

        # Initialize the connection
        print("\nInitializing connection...", file=sys.stderr)
        init_response = send_request(proc, {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1",
                "capabilities": {},
                "clientInfo": {"name": "test_client", "version": "1.0"}
            },
            "id": 1
        })
        print("Initialization response:", json.dumps(init_response, indent=2))

        # List available tools
        print("\nListing tools...", file=sys.stderr)
        tools_response = send_request(proc, {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 2
        })
        print("Tools response:", json.dumps(tools_response, indent=2))

        # Call list_tasks
        print("\nCalling list_tasks...", file=sys.stderr)
        tasks_response = send_request(proc, {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "list_tasks",
                "arguments": {}
            },
            "id": 3
        })
        print("Tasks response:", json.dumps(tasks_response, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        # Clean up
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main() 