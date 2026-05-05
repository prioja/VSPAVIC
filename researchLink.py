"""
Optional "researcher monitor" link.

On the researcher laptop, run a simple TCP listener, e.g.:

  python -m researchLink --listen --port 5999

Or with netcat:

  nc -lk 5999

On the tablet, set env vars before launching the app:

  export VSPA_MONITOR_HOST=141.212.x.x
  export VSPA_MONITOR_PORT=5999
"""

import argparse
import json
import os
import socket
import threading
import time


def sendMonitorEvent(event, payload=None, host=None, port=None):
    host = host or os.environ.get("VSPA_MONITOR_HOST", "").strip()
    if not host:
        return False
    try:
        port = int(port or os.environ.get("VSPA_MONITOR_PORT", "5999"))
    except ValueError:
        port = 5999

    msg = {"ts": time.time(), "event": event, "payload": payload or {}}
    line = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")

    def _send():
        try:
            s = socket.create_connection((host, port), timeout=1.0)
            try:
                s.sendall(line)
            finally:
                s.close()
        except Exception as e:
            print("researchLink: send failed:", e)

    threading.Thread(target=_send, daemon=True).start()
    return True


def listenLoop(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", int(port)))
    srv.listen(5)
    print(f"researchLink: listening on 0.0.0.0:{port} (Ctrl+C to stop)")
    try:
        while True:
            conn, addr = srv.accept()
            try:
                data = conn.recv(4096)
                if data:
                    print(addr, data.decode("utf-8", errors="replace").strip())
            finally:
                conn.close()
    except KeyboardInterrupt:
        print("\nresearchLink: stopped.")
    finally:
        srv.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--listen", action="store_true")
    p.add_argument("--port", type=int, default=5999)
    args = p.parse_args()
    if args.listen:
        listenLoop(args.port)
    else:
        print("Nothing to do. Use --listen, or import sendMonitorEvent() from your app.")


if __name__ == "__main__":
    main()
