#!/usr/bin/env python3
"""
Polar HR (+ optional ECG) to CSV files matching auction session names.

No JSON or tablet handshake: pass subject / condition / trial and how long to record.

From the ``betApp`` directory::

    python3 heartRate.py --subject 001 --trial-cond "TH Low" --trial-num 1 --duration-sec 3900

Or auction length plus buffer::

    python3 heartRate.py --subject 001 --trial-cond "TH Low" --trial-num 1 --total-auction-sec 3600 --buffer-sec 300

Outputs under ``data/``:

- ``…_HR_polar.csv`` — always written (header + rows; ``seconds_since_auction_anchor`` uses ``--anchor-unix`` or recording start).
- ``…_ECG_polar.csv`` — with ``--ecg`` only (header-only if no samples).

Uses ``VSPA_MONITOR_HOST`` / ``VSPA_MONITOR_PORT`` for ``hr_sensor_connected`` when set.

On Ctrl+C or errors, partial data is flushed and CSVs are still written in ``finally``.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import math
import os
import sys
import time
from datetime import datetime
from types import SimpleNamespace

from bleak import BleakScanner

from auctionCsv import DATA_DIR, build_ecg_polar_log_csv_path, build_hr_polar_log_csv_path
from PolarH10 import PolarH10

try:
    from researchLink import sendMonitorEvent
except Exception:
    sendMonitorEvent = None


def unix_to_timestamp_12hr_local(t):
    dt = datetime.fromtimestamp(float(t))
    return dt.strftime("%Y-%m-%d %I:%M:%S %p")


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


async def collect_hr_ecg_for_duration(polar_device, hr_data, ecg_data, duration_sec, pos: list[int]):
    start = time.perf_counter()
    while True:
        drain_polar_hr_ecg(polar_device, hr_data, ecg_data, pos)
        elapsed = time.perf_counter() - start
        if elapsed >= duration_sec:
            break
        await asyncio.sleep(min(1.0, duration_sec - elapsed))


async def run_polar_session(
    cfg: dict,
    polar_name_substr: str,
    data_dir: str,
    *,
    enable_ecg: bool = False,
):
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

    st = _state_from_cli(cfg["subjectId"], cfg["trialCond"], cfg["trialNum"])
    hr_path = build_hr_polar_log_csv_path(st, data_dir=data_dir)
    ecg_path = build_ecg_polar_log_csv_path(st, data_dir=data_dir)

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
                "Recording will continue — check sensor and BLE name filter.\n",
                flush=True,
            )

        if enable_ecg:
            try:
                await polar.start_ecg_stream()
                ecg_enabled = True
                drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
            except Exception as exc:
                print(f"ECG stream not started ({exc}); HR only.\n", flush=True)

        if sendMonitorEvent is not None:
            sendMonitorEvent(
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
            save_hr_csv(hr_path, hr_data, anchor_unix, partial=partial)
            if enable_ecg:
                save_ecg_csv(
                    ecg_path,
                    ecg_data,
                    anchor_unix,
                    partial=partial,
                    allow_empty=True,
                )
        except Exception as save_exc:
            print(f"Could not save Polar CSV: {save_exc}", file=sys.stderr, flush=True)

        if interrupted is not None:
            raise interrupted


def main():
    p = argparse.ArgumentParser(description="Polar HR (+ optional ECG) to CSV files.")
    p.add_argument("--subject", required=True, help="Subject ID (same as tablet)")
    p.add_argument("--trial-cond", required=True, dest="trial_cond", help='Condition spinner text, e.g. "TH Low"')
    p.add_argument("--trial-num", required=True, dest="trial_num", help="Trial number string")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--duration-sec",
        type=float,
        help="Total recording window in seconds (e.g. auction length + buffer).",
    )
    g.add_argument(
        "--total-auction-sec",
        type=float,
        help="Auction duration in seconds; combined with --buffer-sec.",
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
        help="Optional Unix time anchor for seconds_since_auction_anchor (default: now when recording starts).",
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
        help="Enable Polar PMD ECG stream (writes ECG CSV).",
    )
    args = p.parse_args()

    if args.duration_sec is not None:
        dur = float(args.duration_sec)
    else:
        dur = float(args.total_auction_sec) + float(args.buffer_sec)

    cfg = {
        "subjectId": args.subject,
        "trialCond": args.trial_cond,
        "trialNum": args.trial_num,
        "recordingDurationSeconds": dur,
        "anchorUnix": args.anchor_unix,
    }

    asyncio.run(
        run_polar_session(
            cfg,
            args.polar_name.strip() or "Polar",
            args.data_dir,
            enable_ecg=args.ecg,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
