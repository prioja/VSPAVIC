#!/usr/bin/env python3
"""
Polar HR (+ optional ECG) to CSV files matching auction session names.

**Pre-auction streaming (recommended)** — connect and stream HR *before* START, then align
timestamps when the tablet writes ``data/polar_session_anchor.json`` at START::

    python3 heartRate.py --subject 001 --trial-cond "TH Low" --trial-num 1 --wait-for-tablet-start

The tablet writes that anchor file when the participant presses START (``auctionCsv.write_polar_session_anchor``).
``recordingDurationSeconds`` and ``anchorUnix`` in the file set the CSV clock and how long to keep
draining after START (auction total + 5 min buffer from the app).

**Standalone timing** (no tablet anchor)::

    python3 heartRate.py --subject 001 --trial-cond "TH Low" --trial-num 1 --duration-sec 3900

Outputs under ``data/``:

- ``…_HR_polar.csv`` — always written (pre-auction samples get negative ``seconds_since_auction_anchor``).
- ``…_ECG_polar.csv`` — with ``--ecg`` only; ECG starts after the anchor when using ``--wait-for-tablet-start``.

Uses ``VSPA_MONITOR_HOST`` / ``VSPA_MONITOR_PORT`` for monitor events when set.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import sys
import time
from datetime import datetime
from types import SimpleNamespace

from bleak import BleakScanner

from auctionCsv import (
    DATA_DIR,
    POLAR_SESSION_ANCHOR_FILE,
    build_ecg_polar_log_csv_path,
    build_hr_polar_log_csv_path,
)
from PolarH10 import PolarH10

try:
    from researchLink import sendMonitorEvent
except Exception:
    sendMonitorEvent = None


def unix_to_timestamp_12hr_local(t):
    dt = datetime.fromtimestamp(float(t))
    return dt.strftime("%Y-%m-%d %I:%M:%S %p")


def _norm_field(x) -> str:
    return " ".join(str(x or "").split()).strip().lower()


def _anchor_matches_cli(anchor: dict, subject: str, trial_cond: str, trial_num: str) -> bool:
    return (
        _norm_field(anchor.get("subjectId")) == _norm_field(subject)
        and _norm_field(anchor.get("trialCond")) == _norm_field(trial_cond)
        and _norm_field(anchor.get("trialNum")) == _norm_field(trial_num)
    )


def _state_from_cli(subject: str, trial_cond: str, trial_num: str) -> SimpleNamespace:
    return SimpleNamespace(
        subjectId=str(subject or "").strip(),
        trialCond=str(trial_cond or "").strip(),
        trialNum=str(trial_num or "").strip(),
    )


def save_hr_csv(hr_path: str, hr_data: dict, anchor_unix: float, *, partial: bool = False) -> None:
    os.makedirs(os.path.dirname(hr_path) or ".", exist_ok=True)
    times = hr_data.get("times") or []
    values = hr_data.get("values") or []
    n = min(len(times), len(values))
    with open(hr_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "timestamp_local",
                "heart_rate_bpm",
                "seconds_since_auction_anchor",
                "unix_time",
            ]
        )
        for i in range(n):
            tu = float(times[i])
            v = values[i]
            try:
                v_out = int(v)
            except (TypeError, ValueError):
                v_out = v
            w.writerow(
                [
                    unix_to_timestamp_12hr_local(tu),
                    v_out,
                    f"{tu - float(anchor_unix):.6f}",
                    f"{tu:.6f}",
                ]
            )
    tag = " (partial / interrupted)" if partial else ""
    print(f"HR data saved{tag} to {hr_path} ({n} samples)", flush=True)


def save_ecg_csv(
    ecg_path: str,
    ecg_data: dict,
    anchor_unix: float,
    *,
    partial: bool = False,
    allow_empty: bool = False,
) -> None:
    wall = list(ecg_data.get("wall_times") or [])
    vals = list(ecg_data.get("values") or [])
    n = min(len(wall), len(vals))
    os.makedirs(os.path.dirname(ecg_path) or ".", exist_ok=True)
    with open(ecg_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "timestamp_local",
                "ecg_uv",
                "seconds_since_auction_anchor",
                "unix_time",
            ]
        )
        if n == 0:
            if not allow_empty:
                return
            tag = " (no samples)" if not partial else " (partial / interrupted)"
            print(f"ECG file written{tag} (header only): {ecg_path}", flush=True)
            return
        for i in range(n):
            tu = float(wall[i])
            if math.isnan(tu):
                w.writerow(["", int(vals[i]), "", ""])
            else:
                w.writerow(
                    [
                        unix_to_timestamp_12hr_local(tu),
                        int(vals[i]),
                        f"{tu - float(anchor_unix):.6f}",
                        f"{tu:.6f}",
                    ]
                )
    tag = " (partial / interrupted)" if partial else ""
    print(f"ECG data saved{tag} to {ecg_path} ({n} samples)", flush=True)


def drain_polar_hr_ecg(polar_device, hr_data: dict, ecg_data: dict, pos: list[int]) -> None:
    hr_pos, ecg_pos = pos[0], pos[1]
    hr = polar_device.get_hr_data()
    lt = len(hr["times"])
    lv = len(hr["values"])
    nt = min(lt, lv)
    if nt > hr_pos:
        hr_data["times"].extend(hr["times"][hr_pos:nt].tolist())
        hr_data["values"].extend(hr["values"][hr_pos:nt].tolist())
        hr_pos = nt

    ecg = polar_device.get_ecg_data()
    ecg_n = len(ecg["values"])
    if ecg_n > ecg_pos:
        wall = ecg["wall_times"]
        wall_len = len(wall) if hasattr(wall, "__len__") else 0
        if wall_len >= ecg_n:
            ecg_data["wall_times"].extend(list(wall[ecg_pos:ecg_n]))
        else:
            ecg_data["wall_times"].extend([float("nan")] * (ecg_n - ecg_pos))
        ecg_data["values"].extend(ecg["values"][ecg_pos:ecg_n].tolist())
        ecg_pos = ecg_n
    pos[0] = hr_pos
    pos[1] = ecg_pos


async def wait_for_first_hr_samples(polar, hr_data, ecg_data, buf_pos, timeout_sec=25.0) -> int:
    deadline = time.perf_counter() + timeout_sec
    while time.perf_counter() < deadline:
        drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
        n = len(hr_data["times"])
        if n > 0:
            return n
        await asyncio.sleep(0.25)
    drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
    return len(hr_data["times"])


async def wait_for_tablet_anchor_file(
    polar,
    hr_data: dict,
    ecg_data: dict,
    buf_pos: list[int],
    data_dir: str,
    subject: str,
    trial_cond: str,
    trial_num: str,
    timeout_sec: float,
    poll_sec: float = 0.5,
) -> dict:
    """Poll for ``polar_session_anchor.json``; drain HR while waiting. Remove file when matched."""
    path = os.path.join(os.path.abspath(data_dir), POLAR_SESSION_ANCHOR_FILE)
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                await asyncio.sleep(poll_sec)
                continue
            if _anchor_matches_cli(data, subject, trial_cond, trial_num):
                try:
                    os.remove(path)
                except OSError:
                    pass
                return data
            print(
                f"Anchor file at {path!r} does not match this CLI session; waiting for a new START…",
                flush=True,
            )
        await asyncio.sleep(poll_sec)
    raise SystemExit(
        f"Timed out after {timeout_sec:.0f}s waiting for tablet anchor file {path!r}.\n"
        "Press START on the tablet (same subject / condition / trial as this command)."
    )


async def collect_hr_ecg_for_duration(polar_device, hr_data, ecg_data, duration_sec, pos: list[int]):
    start = time.perf_counter()
    while True:
        drain_polar_hr_ecg(polar_device, hr_data, ecg_data, pos)
        elapsed = time.perf_counter() - start
        if elapsed >= duration_sec:
            break
        await asyncio.sleep(min(1.0, duration_sec - elapsed))


async def collect_hr_ecg_until_wall_deadline(
    polar_device, hr_data, ecg_data, pos: list[int], deadline_unix: float
):
    """Drain until ``time.time() >= deadline_unix`` (wall clock aligned with tablet anchor)."""
    while time.time() < deadline_unix:
        drain_polar_hr_ecg(polar_device, hr_data, ecg_data, pos)
        rem = deadline_unix - time.time()
        if rem <= 0:
            break
        await asyncio.sleep(min(1.0, max(0.05, rem)))


def _send(ev: str, payload: dict) -> None:
    if sendMonitorEvent is not None:
        sendMonitorEvent(ev, payload)


async def run_polar_session(
    cfg: dict,
    polar_name_substr: str,
    data_dir: str,
    *,
    enable_ecg: bool = False,
    wait_for_tablet_start: bool = False,
    anchor_wait_seconds: float = 7200.0,
):
    st = _state_from_cli(cfg["subjectId"], cfg["trialCond"], cfg["trialNum"])
    hr_path = build_hr_polar_log_csv_path(st, data_dir=data_dir)
    ecg_path = build_ecg_polar_log_csv_path(st, data_dir=data_dir)

    if wait_for_tablet_start:
        anchor_unix: float | None = None
        duration_sec: float | None = None
        print(
            f"Session: subject={st.subjectId!r} cond={st.trialCond!r} trial={st.trialNum!r}\n"
            f"Mode: connect & stream HR first, then wait for tablet START anchor file.\n"
            f"HR file -> {hr_path}\n"
            f"ECG file -> {ecg_path} (only with --ecg; ECG begins after START anchor)\n",
            flush=True,
        )
    else:
        anchor_unix = (
            float(cfg["anchorUnix"])
            if cfg.get("anchorUnix") is not None and str(cfg.get("anchorUnix")).strip() != ""
            else time.time()
        )
        duration_sec = float(cfg.get("recordingDurationSeconds") or 0.0)
        if duration_sec <= 0:
            raise SystemExit(
                "recordingDurationSeconds must be positive (use --duration-sec or --total-auction-sec)."
            )
        print(
            f"Session: subject={st.subjectId!r} cond={st.trialCond!r} trial={st.trialNum!r}\n"
            f"Recording {duration_sec:.1f}s; anchor_unix={anchor_unix:.3f}\n"
            f"HR file -> {hr_path}\n"
            f"ECG file -> {ecg_path} (only if --ecg)\n",
            flush=True,
        )

    polar = None
    ecg_enabled = False
    interrupted = None
    hr_data: dict = {"times": [], "values": []}
    ecg_data: dict = {"wall_times": [], "values": []}
    buf_pos = [0, 0]

    try:
        devices = await BleakScanner.discover()
        sub = polar_name_substr.lower()
        matched = None
        for device in devices:
            name = device.name or ""
            if sub in name.lower():
                matched = device
                break

        if matched is None:
            print("No Polar device found matching", repr(polar_name_substr), flush=True)
            return

        print(f"Found Polar device: {matched.name} — {matched.address}", flush=True)
        polar = PolarH10(matched)
        await polar.connect()
        await polar.get_device_info()
        await polar.print_device_info()
        await polar.start_hr_stream()
        await asyncio.sleep(0.5)

        n0 = await wait_for_first_hr_samples(polar, hr_data, ecg_data, buf_pos, timeout_sec=25.0)
        if n0 == 0:
            print(
                "No HR samples yet (strap/skin contact, Bluetooth, or wrong device). "
                "Still waiting for tablet START / continuing where applicable.\n",
                flush=True,
            )

        if not wait_for_tablet_start and enable_ecg:
            try:
                await polar.start_ecg_stream()
                ecg_enabled = True
                drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
            except Exception as exc:
                print(f"ECG stream not started ({exc}); HR only.\n", flush=True)

        if wait_for_tablet_start:
            _send(
                "hr_sensor_streaming_pre_auction",
                {
                    "label": "POLAR STREAMING (PRE-START)",
                    "message": "HR stream live; waiting for tablet START to lock auction anchor.",
                    "subjectId": st.subjectId,
                    "trialCond": st.trialCond,
                    "trialNum": st.trialNum,
                    "hrCsvPath": os.path.basename(hr_path),
                    "hrSamplesReceived": n0,
                },
            )
            print(
                f"Waiting for tablet START (file {POLAR_SESSION_ANCHOR_FILE!r} in {data_dir!r})…\n",
                flush=True,
            )
            anchor_payload = await wait_for_tablet_anchor_file(
                polar,
                hr_data,
                ecg_data,
                buf_pos,
                data_dir,
                cfg["subjectId"],
                cfg["trialCond"],
                cfg["trialNum"],
                timeout_sec=anchor_wait_seconds,
            )
            anchor_unix = float(anchor_payload["anchorUnix"])
            duration_sec = float(anchor_payload.get("recordingDurationSeconds") or 0.0)
            if duration_sec <= 0:
                raise SystemExit(
                    "Tablet anchor has recordingDurationSeconds <= 0 (check totalAuctionSeconds in the app)."
                )
            print(
                f"Anchor locked: anchor_unix={anchor_unix:.3f}, recording {duration_sec:.1f}s from anchor.\n",
                flush=True,
            )
            _send(
                "hr_auction_anchor_locked",
                {
                    "label": "POLAR ANCHOR LOCKED",
                    "message": "Tablet START received; Polar CSV timestamps use this anchor.",
                    "subjectId": st.subjectId,
                    "trialCond": st.trialCond,
                    "trialNum": st.trialNum,
                    "anchorUnix": anchor_unix,
                    "recordingDurationSeconds": duration_sec,
                    "hrCsvPath": os.path.basename(hr_path),
                },
            )
            if enable_ecg:
                try:
                    await polar.start_ecg_stream()
                    ecg_enabled = True
                    drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
                except Exception as exc:
                    print(f"ECG stream not started ({exc}); HR only.\n", flush=True)

            deadline = anchor_unix + duration_sec
            now = time.time()
            if now >= deadline:
                print(
                    "Warning: recording window already ended by wall clock at anchor read; saving buffered data.\n",
                    flush=True,
                )
            else:
                print("Recording post-START window… (Ctrl+C to abort)\n", flush=True)
                try:
                    await collect_hr_ecg_until_wall_deadline(
                        polar, hr_data, ecg_data, buf_pos, deadline
                    )
                except BaseException as exc:
                    interrupted = exc
        else:
            _send(
                "hr_sensor_connected",
                {
                    "label": "HR SENSOR CONNECTED",
                    "message": "Polar HR stream running; CSV paths below.",
                    "subjectId": st.subjectId,
                    "trialCond": st.trialCond,
                    "trialNum": st.trialNum,
                    "recordingDurationSeconds": duration_sec,
                    "anchorUnix": anchor_unix,
                    "hrCsvPath": os.path.basename(hr_path),
                    "ecgCsvPath": os.path.basename(ecg_path),
                    "hrSamplesReceived": n0,
                    "ecgEnabled": ecg_enabled,
                },
            )
            print("Recording… (Ctrl+C to abort)\n", flush=True)
            try:
                await collect_hr_ecg_for_duration(polar, hr_data, ecg_data, duration_sec, buf_pos)
            except BaseException as exc:
                interrupted = exc

    except BaseException as exc:
        interrupted = exc
    finally:
        partial = interrupted is not None
        if polar is not None:
            try:
                drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
            except Exception as drain_exc:
                print(f"Polar drain: {drain_exc}", file=sys.stderr, flush=True)
            try:
                if ecg_enabled:
                    await polar.stop_ecg_stream()
                await polar.stop_hr_stream()
                await polar.disconnect()
            except Exception as cleanup_exc:
                print(f"Polar disconnect cleanup: {cleanup_exc}", file=sys.stderr, flush=True)

        try:
            au = anchor_unix
            if au is None and (hr_data.get("times") or []):
                au = time.time()
                print(
                    "Warning: no tablet anchor before exit; using wall time now for seconds_since_auction_anchor.",
                    flush=True,
                )
            if au is not None:
                save_hr_csv(hr_path, hr_data, au, partial=partial)
                if enable_ecg:
                    save_ecg_csv(
                        ecg_path,
                        ecg_data,
                        au,
                        partial=partial,
                        allow_empty=True,
                    )
        except Exception as save_exc:
            print(f"Could not save Polar CSV: {save_exc}", file=sys.stderr, flush=True)

        if interrupted is not None:
            raise interrupted


def main():
    p = argparse.ArgumentParser(
        description="Polar HR (+ optional ECG) to CSV; optional wait for tablet START anchor."
    )
    p.add_argument("--subject", required=True, help="Subject ID (same as tablet)")
    p.add_argument("--trial-cond", required=True, dest="trial_cond", help='Condition spinner text, e.g. "TH Low"')
    p.add_argument("--trial-num", required=True, dest="trial_num", help="Trial number string")
    p.add_argument(
        "--wait-for-tablet-start",
        action="store_true",
        help="Connect & stream HR before START; lock anchor/duration from data/polar_session_anchor.json when START is pressed.",
    )
    p.add_argument(
        "--anchor-wait-seconds",
        type=float,
        default=7200.0,
        help="Max seconds to wait for tablet anchor when using --wait-for-tablet-start (default: 2 h).",
    )
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument(
        "--duration-sec",
        type=float,
        help="Total recording window in seconds (ignored with --wait-for-tablet-start).",
    )
    g.add_argument(
        "--total-auction-sec",
        type=float,
        help="Auction duration in seconds; with --buffer-sec (ignored with --wait-for-tablet-start).",
    )
    p.add_argument(
        "--buffer-sec",
        type=float,
        default=300.0,
        help="Added to --total-auction-sec when that option is used (default: 300).",
    )
    p.add_argument(
        "--anchor-unix",
        type=float,
        default=None,
        help="Optional anchor for standalone mode (default: now at session start).",
    )
    p.add_argument("--data-dir", default=DATA_DIR, help="Data directory (default: data)")
    p.add_argument(
        "--polar-name",
        default=os.environ.get("VSPA_POLAR_NAME", "Polar"),
        help="Substring to match BLE device name (default: Polar)",
    )
    p.add_argument(
        "--ecg",
        action="store_true",
        help="Enable Polar PMD ECG (after START anchor when using --wait-for-tablet-start).",
    )
    args = p.parse_args()

    if args.wait_for_tablet_start:
        if args.duration_sec is not None or args.total_auction_sec is not None:
            p.error("With --wait-for-tablet-start, do not pass --duration-sec or --total-auction-sec.")
        dur = 0.0
        anchor = None
    else:
        if args.duration_sec is None and args.total_auction_sec is None:
            p.error("Provide --duration-sec or --total-auction-sec, or use --wait-for-tablet-start.")
        if args.duration_sec is not None:
            dur = float(args.duration_sec)
        else:
            dur = float(args.total_auction_sec) + float(args.buffer_sec)
        anchor = args.anchor_unix

    cfg = {
        "subjectId": args.subject,
        "trialCond": args.trial_cond,
        "trialNum": args.trial_num,
        "recordingDurationSeconds": dur,
        "anchorUnix": anchor,
    }

    asyncio.run(
        run_polar_session(
            cfg,
            args.polar_name.strip() or "Polar",
            args.data_dir,
            enable_ecg=args.ecg,
            wait_for_tablet_start=args.wait_for_tablet_start,
            anchor_wait_seconds=args.anchor_wait_seconds,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
