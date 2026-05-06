"""
Optional "researcher monitor" link.

On the researcher laptop, run a simple TCP listener, e.g.:

  python -m researchLink --listen --port 5999

Or with netcat:

  nc -lk 5999

On the tablet, set env vars before launching the app:

  export VSPA_MONITOR_HOST=141.212.x.x
  export VSPA_MONITOR_PORT=5999

Short aliases are also accepted:

  export HOST=141.212.x.x
  export PORT=5999
"""

import argparse
import json
import os
import socket
import threading
import time
from datetime import datetime


def sendMonitorEvent(event, payload=None, host=None, port=None):
    host = host or os.environ.get("VSPA_MONITOR_HOST", "").strip() or os.environ.get("HOST", "").strip()
    if not host:
        return False
    try:
        port = int(port or os.environ.get("VSPA_MONITOR_PORT", "").strip() or os.environ.get("PORT", "5999").strip())
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


def _fmt_ts(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return "??:??:??"


def _pretty_line(msg):
    ts = _fmt_ts(msg.get("ts"))
    ev = msg.get("event", "event")
    payload = msg.get("payload") or {}

    label = payload.get("label")
    if label:
        head = label
    else:
        head = ev.replace("_", " ").upper()

    # Keep it minimal + readable in a terminal.
    if ev == "bid_submitted":
        bid = payload.get("bid")
        try:
            bid_txt = f"${float(bid):.2f}"
        except Exception:
            bid_txt = str(bid)
        return f"[{ts}] BID: {bid_txt}"

    if ev in ("help_pressed", "auction_paused", "auction_resumed"):
        return f"[{ts}] {head}"

    if ev == "session_started":
        subj = payload.get("subjectId", "")
        cond = payload.get("trialCond", "")
        trial = payload.get("trialNum", "")
        totalRounds = payload.get("totalRounds", "")
        totalSeconds = payload.get("totalAuctionSeconds", "")
        extra = ""
        try:
            if totalSeconds != "" and totalSeconds is not None:
                extra += f" | {float(totalSeconds):.0f}s"
        except Exception:
            pass
        if totalRounds != "" and totalRounds is not None:
            extra += f" | rounds={totalRounds}"
        return f"[{ts}] SESSION STARTED: {subj} | {cond} | {trial}{extra}"

    if ev == "round_started":
        bids = payload.get("robotBidsLocked")
        if isinstance(bids, list):
            try:
                bids_txt = ", ".join(f"{float(x):.2f}" for x in bids)
            except Exception:
                bids_txt = ", ".join(str(x) for x in bids)
            return f"[{ts}] ROUND STARTED (robots): [{bids_txt}]"
        return f"[{ts}] ROUND STARTED"

    # Fallback: show label/message if provided, else event name only.
    msg_txt = payload.get("message")
    if msg_txt:
        return f"[{ts}] {head}: {msg_txt}"
    return f"[{ts}] {head}"


def sendResearcherConfig(tabletHost, tabletPort=6000, treadmillSpeed="", preferredStiffness=""):
    payload = {
        "treadmillSpeedSetting": treadmillSpeed,
        "preferredStiffnessNPerMm": preferredStiffness,
    }
    msg = {"ts": time.time(), "event": "researcher_config", "payload": payload}
    line = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
    s = socket.create_connection((tabletHost, int(tabletPort)), timeout=3.0)
    try:
        s.sendall(line)
    finally:
        s.close()


def startConfigListener(onPayload, port=6000, host="0.0.0.0"):
    """
    Tablet-side listener so the researcher machine can send session settings (e.g. treadmill
    speed and preferred stiffness) at launch.
    """
    def _run():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, int(port)))
        srv.listen(5)
        print(f"researchLink: config listener on {host}:{port}")
        while True:
            conn, _addr = srv.accept()
            try:
                data = conn.recv(4096)
                if not data:
                    continue
                text = data.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    if msg.get("event") != "researcher_config":
                        continue
                    payload = msg.get("payload") or {}
                    try:
                        onPayload(payload)
                    except Exception as e:
                        print("researchLink: config apply failed:", e)
            finally:
                conn.close()

    threading.Thread(target=_run, daemon=True).start()


def listenLoop(port, raw=False, show_ip=False):
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
                    text = data.decode("utf-8", errors="replace")
                    for line in text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if raw:
                            prefix = f"{addr} " if show_ip else ""
                            print(prefix + line)
                            continue
                        try:
                            msg = json.loads(line)
                        except Exception:
                            prefix = f"{addr} " if show_ip else ""
                            print(prefix + line)
                            continue
                        prefix = f"{addr} " if show_ip else ""
                        print(prefix + _pretty_line(msg))
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
    p.add_argument("--raw", action="store_true", help="Print raw JSON lines (no pretty formatting).")
    p.add_argument("--show-ip", action="store_true", help="Prefix lines with (ip, port).")
    p.add_argument("--send-config", action="store_true", help="Prompt and send treadmill/stiffness to tablet.")
    p.add_argument("--tablet", type=str, default="", help="Tablet IP/hostname for --send-config.")
    p.add_argument("--tablet-port", type=int, default=6000, help="Tablet port for --send-config (default 6000).")
    p.add_argument(
        "--condition",
        type=str,
        default="",
        help="Optional condition code (VS/PF/TH). If VS, will prompt for Preferred Stiffness.",
    )
    args = p.parse_args()
    if args.listen:
        listenLoop(args.port, raw=args.raw, show_ip=args.show_ip)
    elif args.send_config:
        if not args.tablet:
            raise SystemExit("--tablet is required with --send-config")
        treadmillSpeed = input("Treadmill Speed: ").strip()
        cond = (args.condition or input("Condition (VS/PF/TH) [optional]: ").strip()).upper()
        preferredStiffness = ""
        if cond.startswith("VS"):
            preferredStiffness = input("Preferred Stiffness (N/mm): ").strip()
        sendResearcherConfig(
            args.tablet,
            args.tablet_port,
            treadmillSpeed=treadmillSpeed,
            preferredStiffness=preferredStiffness,
        )
        print("Sent researcher_config.")
    else:
        print("Nothing to do. Use --listen, or import sendMonitorEvent() from your app.")


if __name__ == "__main__":
    main()
