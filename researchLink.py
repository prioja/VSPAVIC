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

Researcher machine (send treadmill speed to tablet — tablet app must be running first):

  python3 -m researchLink --send-config --tablet <TABLET_IP> --tablet-port 6000

  Or send speed then listen for auction events in one command:

  python3 -m researchLink --listen --tablet <TABLET_IP> --treadmill-speed 1.0

  Prompts for speed/stiffness when --send-config is used without --treadmill-speed.
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
                lines.append(f"  Total Time (min): {float(totalSeconds) / 60.0:.2f}")
            except Exception:
                lines.append(f"  totalTimeMinutes: {totalSeconds}")
        if totalRounds is not None and totalRounds != "":
            lines.append(f"  totalRounds: {totalRounds}")
        cfg = payload.get("config")
        if isinstance(cfg, dict):
            rm = cfg.get("roboModel")
            if isinstance(rm, dict) and rm:
                summ = (rm.get("summary") or "").strip()
                if summ:
                    lines.append(f"  Robo model (session): {summ}")
                else:
                    lines.append(
                        f"  Robo model (session): {rm.get('name', '')}  k={rm.get('k')}  b={rm.get('b')}  n={rm.get('count')}"
                    )
        if "treadmillSpeedSetting" in payload:
            lines.append(f"  treadmillSpeedSetting: {payload.get('treadmillSpeedSetting', '')}")
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
        lines = [f"[{ts}] {title}"]
        bids = payload.get("robotBidsLocked")
        if isinstance(bids, list):
            try:
                bidsTxt = ", ".join(f"{float(x):.2f}" for x in bids)
            except Exception:
                bidsTxt = ", ".join(str(x) for x in bids)
            lines.append(f"  Robot bids: [{bidsTxt}]")
        rm = payload.get("roboModel")
        if isinstance(rm, dict) and rm:
            summ = (rm.get("summary") or "").strip()
            if summ:
                lines.append(f"  Robo model: {summ}")
            else:
                lines.append(
                    f"  Robo model: {rm.get('name', '')}  k={rm.get('k')}  b={rm.get('b')}  n={rm.get('count')}"
                )
        return "\n".join(lines)

    msgTxt = payload.get("message")
    if msgTxt:
        return f"[{ts}] {head}\n  {msgTxt}"
    return f"[{ts}] {head}"


def sendResearcherConfig(
    tabletHost,
    tabletPort=6000,
    treadmillSpeed="",
    preferredStiffness="",
):
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


def runSendConfig(tablet, tablet_port=6000, treadmill_speed=None, condition="", preferred_stiffness=None):
    """Push treadmill speed (and optional VS stiffness) to the tablet config listener."""
    if not (tablet or "").strip():
        raise SystemExit("--tablet is required to send treadmill config.")

    speed = (treadmill_speed or "").strip()
    if not speed:
        speed = input("Treadmill Speed (m/s): ").strip()

    cond = (condition or "").strip().upper()
    if not cond and preferred_stiffness is None:
        cond = input("Trial Condition (TH/PF/VS) [optional]: ").strip().upper()

    stiff = preferred_stiffness
    if stiff is None:
        stiff = ""
        if cond.startswith("VS"):
            stiff = input("Preferred Stiffness (N/mm): ").strip()
    else:
        stiff = str(stiff).strip()

    sendResearcherConfig(
        tablet.strip(),
        int(tablet_port),
        treadmillSpeed=speed,
        preferredStiffness=stiff,
    )
    print(
        f"researchLink: sent researcher_config to {tablet.strip()}:{int(tablet_port)} "
        f"(treadmill speed={speed!r})."
    )


def listenLoop(port, raw=False, showIp=False):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", int(port)))
    srv.listen(5)
    print(f"researchLink: listening on 0.0.0.0:{port} (Ctrl+C to stop)")
    print(
        "researchLink: tablet events appear here when the app sets "
        "VSPA_MONITOR_HOST to this machine."
    )
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
        help="Prompt and send treadmill / stiffness (VS) to tablet.",
    )
    p.add_argument("--tablet", type=str, default="", help="Tablet IP for config send (port 6000).")
    p.add_argument("--tablet-port", type=int, default=6000, help="Tablet config port (default 6000).")
    p.add_argument(
        "--treadmill-speed",
        type=str,
        default="",
        help="Treadmill speed in m/s (with --send-config or --listen --tablet).",
    )
    p.add_argument(
        "--preferred-stiffness",
        type=str,
        default=None,
        help="Preferred stiffness N/mm for VS trials (optional).",
    )
    p.add_argument(
        "--condition",
        type=str,
        default="",
        help="Trial condition TH/PF/VS; if VS and stiffness omitted, prompts.",
    )
    args = p.parse_args()

    should_send = bool(args.send_config) or bool((args.treadmill_speed or "").strip())
    if args.listen and args.tablet and not should_send:
        print(
            "researchLink: tip — add --treadmill-speed 1.0 or --send-config to push "
            "speed to the tablet before listening."
        )

    if should_send:
        runSendConfig(
            args.tablet,
            tablet_port=args.tablet_port,
            treadmill_speed=args.treadmill_speed or None,
            condition=args.condition,
            preferred_stiffness=args.preferred_stiffness,
        )

    if args.listen:
        listenLoop(args.port, raw=args.raw, showIp=args.show_ip)
        return

    if args.send_config or should_send:
        if not args.tablet and should_send:
            raise SystemExit("--tablet is required when sending treadmill config.")
        return

    print("Nothing to do. Use --listen and/or --send-config (with --tablet).")


if __name__ == "__main__":
    main()
