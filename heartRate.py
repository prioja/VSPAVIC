#!/usr/bin/env python3
"""
Standalone Polar HR (+ optional ECG) aligned to the tablet auction session.

Prerequisite: run the betApp and press START so ``data/hr_session_ready.json`` exists
(``auctionCsv.write_hr_session_sidecar`` — uses ``totalAuctionSeconds`` + 5 min buffer).

From the ``betApp`` directory::

    python3 heartRate.py

ECG is **off** by default (Polar PMD can prevent HR notifications on some machines). Use ``--ecg`` to
enable ECG streaming alongside HR.

Uses ``VSPA_MONITOR_HOST`` / ``VSPA_MONITOR_PORT`` (or ``HOST`` / ``PORT``) to notify the
researcher when the Polar HR stream is live (``hr_sensor_connected``).

HR CSV columns: wall timestamp (12h local), ``heart_rate_bpm``, ``seconds_since_auction_anchor``
(Unix sample time minus ``anchorUnix`` from the sidecar; same machine = same clock).

On Ctrl+C, process exit, or other errors during recording, any HR/ECG collected so far is flushed
from the device buffers and written to the same CSV paths (header-only HR if no samples yet).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from types import SimpleNamespace

from bleak import BleakScanner

from auctionCsv import DATA_DIR, HR_SESSION_SIDECAR, build_hr_polar_log_csv_path
from PolarH10 import PolarH10

try:
    from researchLink import sendMonitorEvent
except Exception:
    sendMonitorEvent = None


def unix_to_timestamp_12hr_local(t):
    dt = datetime.fromtimestamp(float(t))
    return dt.strftime("%Y-%m-%d %I:%M:%S %p")


def wait_for_config(path: str, timeout_sec: float, poll_sec: float = 1.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        time.sleep(poll_sec)
    raise SystemExit(
        f"Timed out after {timeout_sec:.0f}s waiting for {path!r}.\n"
        "Start the tablet session (START) so the app writes the sidecar, then re-run."
    )


def _state_from_cfg(cfg: dict) -> SimpleNamespace:
    return SimpleNamespace(
        subjectId=str(cfg.get("subjectId", "") or ""),
        trialCond=str(cfg.get("trialCond", "") or ""),
        trialNum=str(cfg.get("trialNum", "") or ""),
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
            w.writerow(
                [
                    unix_to_timestamp_12hr_local(tu),
                    values[i],
                    f"{tu - float(anchor_unix):.6f}",
                    f"{tu:.6f}",
                ]
            )
    tag = " (partial / interrupted)" if partial else ""
    print(f"HR data saved{tag} to {hr_path}")


def save_ecg_csv(ecg_path: str, ecg_data: dict, anchor_unix: float, *, partial: bool = False) -> None:
    wall = ecg_data.get("wall_times") or []
    vals = ecg_data.get("values") or []
    if len(wall) == 0 or len(vals) != len(wall):
        return
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
        for tu, v in zip(wall, vals):
            tu = float(tu)
            w.writerow(
                [
                    unix_to_timestamp_12hr_local(tu),
                    int(v),
                    f"{tu - float(anchor_unix):.6f}",
                    f"{tu:.6f}",
                ]
            )
    tag = " (partial / interrupted)" if partial else ""
    print(f"ECG data saved{tag} to {ecg_path}")


def drain_polar_hr_ecg(polar_device, hr_data: dict, ecg_data: dict, pos: list[int]) -> None:
    """Append any new HR/ECG samples from the device buffers into *hr_data* / *ecg_data*.
    pos must be a two-element list [hr_pos, ecg_pos] updated in place.
    """
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
    """Poll BLE buffers until at least one HR sample is copied into *hr_data* or *timeout_sec* elapses."""
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
    cfg: dict, polar_name_substr: str, data_dir: str, *, enable_ecg: bool = False
):
    duration_sec = float(cfg.get("recordingDurationSeconds") or 0.0)
    anchor_unix = float(cfg.get("anchorUnix") or time.time())
    if duration_sec <= 0:
        raise SystemExit(
            "recordingDurationSeconds is missing or zero in sidecar "
            "(is totalAuctionSeconds set in the app?)."
        )

    st = _state_from_cfg(cfg)
    hr_path = build_hr_polar_log_csv_path(st, data_dir=data_dir)
    ecg_path = hr_path.replace("_HR_polar.csv", "_ECG_polar.csv")

    print(
        f"Session: subject={st.subjectId!r} cond={st.trialCond!r} trial={st.trialNum!r}\n"
        f"Recording {duration_sec:.1f}s (auction total + buffer); anchor_unix={anchor_unix:.3f}\n"
        f"HR file -> {hr_path}\n"
    )

    devices = await BleakScanner.discover()
    sub = polar_name_substr.lower()
    for device in devices:
        name = device.name or ""
        if sub not in name.lower():
            continue

        print(f"Found Polar device: {device.name} — {device.address}")
        polar = PolarH10(device)
        await polar.connect()
        await polar.get_device_info()
        await polar.print_device_info()
        await polar.start_hr_stream()
        await asyncio.sleep(0.5)

        hr_data = {"times": [], "values": []}
        ecg_data = {"wall_times": [], "values": []}
        buf_pos = [0, 0]

        n0 = await wait_for_first_hr_samples(polar, hr_data, ecg_data, buf_pos, timeout_sec=25.0)
        if n0 == 0:
            print(
                "No HR samples yet (strap/skin contact, Bluetooth, or wrong device). "
                "Recording will continue — if still empty, check the sensor and BLE name filter.\n",
                flush=True,
            )

        ecg_enabled = False
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
                    "message": "Polar HR stream running; recording aligned to auction sidecar anchor.",
                    "subjectId": st.subjectId,
                    "trialCond": st.trialCond,
                    "trialNum": st.trialNum,
                    "recordingDurationSeconds": duration_sec,
                    "anchorUnix": anchor_unix,
                    "hrCsvPath": os.path.basename(hr_path),
                    "hrSamplesReceived": n0,
                    "ecgEnabled": ecg_enabled,
                },
            )

        print("Recording… (Ctrl+C to abort)\n", flush=True)
        interrupted = None
        try:
            await collect_hr_ecg_for_duration(polar, hr_data, ecg_data, duration_sec, buf_pos)
        except BaseException as exc:
            interrupted = exc
        finally:
            drain_polar_hr_ecg(polar, hr_data, ecg_data, buf_pos)
            partial = interrupted is not None
            try:
                save_hr_csv(hr_path, hr_data, anchor_unix, partial=partial)
                if ecg_enabled and len(ecg_data.get("values") or []) > 0:
                    save_ecg_csv(ecg_path, ecg_data, anchor_unix, partial=partial)
            except Exception as save_exc:
                print(f"Could not save Polar CSV: {save_exc}", file=sys.stderr, flush=True)
            try:
                if ecg_enabled:
                    await polar.stop_ecg_stream()
                await polar.stop_hr_stream()
                await polar.disconnect()
            except Exception as cleanup_exc:
                print(f"Polar disconnect cleanup: {cleanup_exc}", file=sys.stderr, flush=True)
            if interrupted is not None:
                raise interrupted
        return

    print("No Polar device found matching", repr(polar_name_substr))


def main():
    p = argparse.ArgumentParser(description="Polar HR session aligned to betApp auction sidecar.")
    p.add_argument(
        "--config",
        default=os.path.join(DATA_DIR, HR_SESSION_SIDECAR),
        help=f"Path to sidecar JSON (default: {DATA_DIR}/{HR_SESSION_SIDECAR})",
    )
    p.add_argument("--data-dir", default=DATA_DIR, help="Data directory (default: data)")
    p.add_argument(
        "--wait-seconds",
        type=float,
        default=7200.0,
        help="Max time to wait for sidecar before exit (default: 2 h)",
    )
    p.add_argument(
        "--polar-name",
        default=os.environ.get("VSPA_POLAR_NAME", "Polar"),
        help="Substring to match BLE device name (default: Polar)",
    )
    p.add_argument(
        "--ecg",
        action="store_true",
        help="Enable Polar PMD ECG stream (default: HR only). ECG can block or starve HR on some hosts.",
    )
    args = p.parse_args()

    cfg_path = os.path.abspath(args.config)
    print(f"Waiting for session sidecar: {cfg_path}")
    cfg = wait_for_config(cfg_path, args.wait_seconds)

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
