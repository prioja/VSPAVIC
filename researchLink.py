"""
Optional "researcher monitor" link.

Researcher machine (receive events):

  python3 -m researchLink --listen --port 5999

Tablet machine (send events): set env vars before launching the app:

  export VSPA_MONITOR_HOST=192.168.x.x
  export VSPA_MONITOR_PORT=5999

Short aliases are also accepted:

  export HOST=192.168.x.x
  export PORT=5999

Researcher machine (send config to tablet):

  python3 -m researchLink --send-config --tablet <TABLET_IP> --tablet-port 6000

  Prompts: treadmill speed, heart-rate baseline, condition; preferred stiffness only if VS*.
"""

import argparse
import json
import os
import socket
import threading
import time
from datetime import datetime

# Shown after total time / total rounds on `session_started` (monitor + JSON payload).
SESSION_START_RESEARCHER_REMINDERS = (
    "Please ensure COSMED mask is fitted.",
    "Please ensure the heartrate monitor is fitted.",
    "Start heartrate program with total time.",
)


def sendMonitorEvent(event, payload=None, host=None, port=None):
    host = host or os.environ.get("VSPA_MONITOR_HOST", "").strip() or os.environ.get("HOST", "").strip()
    if not host:
        return False
    try:
        port = int(
            port
            or os.environ.get("VSPA_MONITOR_PORT", "").strip()
            or os.environ.get("PORT", "5999").strip()
        )
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


def _fmtTs(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return "??:??:??"


def _prettyLine(msg):
    ts = _fmtTs(msg.get("ts"))
    # Do not default missing "event" to the literal "event" — that breaks special-case matching.
    ev = (msg.get("event") or msg.get("Event") or "").strip()
    payload = msg.get("payload") or {}

    label = payload.get("label")
    head = label if label else ev.replace("_", " ").upper()

    # Minimal + readable.
    is_bid = ev == "bid_submitted" or (
        "bid" in payload
        and str(payload.get("label", "")).strip().upper() == "BID SUBMITTED"
    )
    if is_bid:
        bid = payload.get("bid")
        try:
            bidTxt = f"${float(bid):.2f}"
        except Exception:
            bidTxt = str(bid)
        return f"[{ts}] Subject Bid: {bidTxt}"

    if ev in ("help_pressed", "auction_paused", "auction_resumed"):
        return f"[{ts}] {head}"

    if ev == "session_started":
        subj = payload.get("subjectId", "")
        cond = payload.get("trialCond", "")
        trial = payload.get("trialNum", "")

        totalSeconds = payload.get("totalAuctionSeconds", None)
        totalRounds = payload.get("totalRounds", None)

        lines = [
            f"[{ts}] ---------- SESSION STARTED ----------",
            f"  Subject ID: {subj}",
            f"  Condition: {cond}",
            f"  Trial #: {trial}",
        ]
        if totalSeconds is not None and totalSeconds != "":
            try:
                lines.append(f"  totalTimeMinutes: {float(totalSeconds) / 60.0:.2f}")
            except Exception:
                lines.append(f"  totalTimeMinutes: {totalSeconds}")
        if totalRounds is not None and totalRounds != "":
            lines.append(f"  totalRounds: {totalRounds}")
        if "treadmillSpeedSetting" in payload:
            lines.append(f"  treadmillSpeedSetting: {payload.get('treadmillSpeedSetting', '')}")
        if "heartRateBaselineSetting" in payload:
            lines.append(f"  heartRateBaselineSetting: {payload.get('heartRateBaselineSetting', '')}")
        if "preferredStiffnessNPerMm" in payload:
            lines.append(f"  preferredStiffnessNPerMm: {payload.get('preferredStiffnessNPerMm', '')}")
        reminders = payload.get("researcherReminders")
        if not isinstance(reminders, (list, tuple)) or not reminders:
            reminders = SESSION_START_RESEARCHER_REMINDERS
        lines.append("")
        lines.append("  --- Researcher reminders ---")
        for r in reminders:
            lines.append(f"  {r}")
        return "\n".join(lines)

    if ev == "round_started":
        title = "ROUND STARTED"
        try:
            n = int(payload.get("roundNumber"))
            if n >= 1:
                title = f"ROUND {n} STARTED"
        except (TypeError, ValueError):
            lab = (payload.get("label") or "").strip()
            if lab:
                title = lab
        bids = payload.get("robotBidsLocked")
        if isinstance(bids, list):
            try:
                bidsTxt = ", ".join(f"{float(x):.2f}" for x in bids)
            except Exception:
                bidsTxt = ", ".join(str(x) for x in bids)
            return f"[{ts}] {title}\n Robotbids: [{bidsTxt}]"
        return f"[{ts}] {title}"

    if ev == "hr_sensor_connected":
        subj = payload.get("subjectId", "")
        dur = payload.get("recordingDurationSeconds", "")
        anc = payload.get("anchorUnix", "")
        fn = payload.get("hrCsvPath", "")
        lines = [
            f"[{ts}] ---------- HR SENSOR CONNECTED ----------",
            f"  Subject ID: {subj}",
            f"  recordingDurationSeconds: {dur}",
            f"  anchorUnix: {anc}",
            f"  hrCsvPath: {fn}",
            f"  ecgCsvPath: {payload.get('ecgCsvPath', '')}",
            f"  hrSamplesReceived: {payload.get('hrSamplesReceived', '')}",
            f"  ecgEnabled: {payload.get('ecgEnabled', '')}",
        ]
        msg = (payload.get("message") or "").strip()
        if msg:
            lines.append(f"  note: {msg}")
        return "\n".join(lines)

    if ev == "hr_sensor_streaming_pre_auction":
        subj = payload.get("subjectId", "")
        fn = payload.get("hrCsvPath", "")
        n = payload.get("hrSamplesReceived", "")
        lines = [
            f"[{ts}] ---------- POLAR STREAMING (PRE-START) ----------",
            f"  Subject ID: {subj}",
            f"  hrCsvPath: {fn}",
            f"  hrSamplesReceived: {n}",
        ]
        msg = (payload.get("message") or "").strip()
        if msg:
            lines.append(f"  note: {msg}")
        return "\n".join(lines)

    if ev == "hr_auction_anchor_locked":
        subj = payload.get("subjectId", "")
        anc = payload.get("anchorUnix", "")
        dur = payload.get("recordingDurationSeconds", "")
        fn = payload.get("hrCsvPath", "")
        lines = [
            f"[{ts}] ---------- POLAR ANCHOR LOCKED (TABLET START) ----------",
            f"  Subject ID: {subj}",
            f"  anchorUnix: {anc}",
            f"  recordingDurationSeconds: {dur}",
            f"  hrCsvPath: {fn}",
        ]
        msg = (payload.get("message") or "").strip()
        if msg:
            lines.append(f"  note: {msg}")
        return "\n".join(lines)

    msgTxt = payload.get("message")
    if msgTxt:
        return f"[{ts}] {head}\n  {msgTxt}"
    return f"[{ts}] {head}"


def sendResearcherConfig(
    tabletHost,
    tabletPort=6000,
    treadmillSpeed="",
    heartRateBaseline="",
    preferredStiffness="",
):
    payload = {
        "treadmillSpeedSetting": treadmillSpeed,
        "heartRateBaselineSetting": heartRateBaseline,
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
    Tablet-side listener so the researcher machine can send session settings at launch.
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


def listenLoop(port, raw=False, showIp=False):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", int(port)))
    srv.listen(5)
    print(f"researchLink: listening on 0.0.0.0:{port} (Ctrl+C to stop)")
    print(f"researchLink: using script {__file__!r} — restart this process after edits.")
    try:
        while True:
            conn, addr = srv.accept()
            try:
                data = conn.recv(4096)
                if not data:
                    continue
                text = data.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    prefix = f"{addr} " if showIp else ""
                    if raw:
                        print(prefix + line)
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        print(prefix + line)
                        continue
                    print(prefix + _prettyLine(msg))
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
    p.add_argument(
        "--send-config",
        action="store_true",
        help="Prompt and send treadmill / HR baseline / stiffness (VS) to tablet.",
    )
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
        listenLoop(args.port, raw=args.raw, showIp=args.show_ip)
        return

    if args.send_config:
        if not args.tablet:
            raise SystemExit("--tablet is required with --send-config")

        treadmillSpeed = input("treadmillSpeed: ").strip()
        heartRateBaseline = input("heartRateBaseline (e.g. BPM): ").strip()
        cond = (args.condition or input("condition (VS/PF/TH) [optional]: ").strip()).upper()
        preferredStiffness = ""
        if cond.startswith("VS"):
            preferredStiffness = input("preferredStiffnessNPerMm: ").strip()

        sendResearcherConfig(
            args.tablet,
            args.tablet_port,
            treadmillSpeed=treadmillSpeed,
            heartRateBaseline=heartRateBaseline,
            preferredStiffness=preferredStiffness,
        )
        print("Sent researcher_config.")
        return

    print("Nothing to do. Use --listen or --send-config.")


if __name__ == "__main__":
    main()
