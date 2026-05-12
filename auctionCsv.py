"""
Append auction results to a per-session CSV.

Auction format (Vickrey second-price, lowest-bid wins):
  The lowest bid wins the item; the clearing price / payout side uses the
  second-lowest bid among all bids (human + robots). Same structure as a standard
  Vickrey auction but inverted from highest-bid wording.

Files (matches your terminal naming):
  auctionFilename = "VSPAVIC" + subject + "_A_" + condition + trial + ".csv"
  Example: VSPAVIC001_A_TH1.csv where TH + 1 is short condition code + trial number.
"""

import csv
import json
import os
from datetime import datetime

DATA_DIR = "data"


def conditionCodeFromUI(trialCondText):
    """Map start-screen spinner text to a short code for the filename."""
    if not trialCondText or trialCondText == "Select Condition":
        return "UNK"
    t = trialCondText.strip()
    if t.startswith("TH"):
        return "TH"
    if t.startswith("PF"):
        return "PF"
    if t.startswith("VS"):
        return "VS"
    return "UNK"


def buildSessionPaths(state, dataDir=DATA_DIR):
    """
    Returns (auctionPath, auctionFilename).
    """
    subj = "".join((state.subjectId or "").split())
    cc = conditionCodeFromUI(state.trialCond)
    trial = (state.trialNum or "").strip()
    if not trial or trial == "Select Trial":
        trial = "X"

    condTrial = f"{cc}{trial}"
    auctionFilename = f"VSPAVIC{subj}_{condTrial}_A.csv"

    os.makedirs(dataDir, exist_ok=True)
    auctionPath = os.path.join(dataDir, auctionFilename)

    return auctionPath, auctionFilename


def buildEventsCsvPath(state, dataDir=DATA_DIR):
    """Companion log for UI events (HELP / PAUSE), same folder as the auction CSV."""
    auctionPath, _af = buildSessionPaths(state, dataDir)
    root, ext = os.path.splitext(auctionPath)
    return f"{root}_events{ext}"


def _cell(value):
    if value is None:
        return ""
    return value


def _trial_cond_is_vspa(state):
    try:
        return (state.trialCond or "").strip().startswith("VS")
    except Exception:
        return False


def _preferred_stiffness_metadata(state):
    """VSPA (VS*) trials use stored stiffness; other conditions log N/A."""
    if not _trial_cond_is_vspa(state):
        return "N/A"
    return _cell(getattr(state, "preferredStiffnessNPerMm", ""))


def _excel_text(value):
    """
    Prevent Excel from displaying ####### for narrow timestamp columns by forcing
    text rendering while keeping the value human-readable in the CSV.
    """
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    # Excel interprets ="..." as a formula returning text.
    return f'="{s}"'


def _split_session_timestamp(ts):
    """
    Input is usually: YYYY-MM-DD HH:MM:SS AM/PM
    Returns (date_str, time_str). Falls back to simple splitting.
    """
    if ts is None:
        return "", ""
    s = str(ts).strip()
    if not s:
        return "", ""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %I:%M:%S %p")
        return dt.strftime("%m-%d-%Y"), dt.strftime("%I:%M:%S %p")
    except Exception:
        parts = s.split()
        if len(parts) >= 2:
            return parts[0], " ".join(parts[1:])
        return s, ""


def _time_only(ts):
    """Return only the time portion from a session/round timestamp string."""
    _d, _t = _split_session_timestamp(ts)
    return _t or ""


class AuctionCsvLogger:
    """One CSV per session; one row per finalized round.
    UI events (HELP / PAUSE) append to a sibling ``*_events.csv`` file.
    """

    # Table columns (metadata like subject/condition/trial are written as a title block above)
    HEADERS = [
        "Round #",
        "Start Time",
        "End Time",
        "Subject Bid",
        "Human Won",
        "Lowest Bid",
        "Vickrey Price",
        "Total Winnings",
        "Distance",
    ]

    # Units row, written directly under HEADERS (helps during analysis in Excel/R/etc.)
    UNITS = [
        "",
        "",
        "",
        "$",
        "",
        "$",
        "$",
        "$",
        "m",
    ]

    EVENT_HEADERS = [
        "Timestamp:",
        "Label",
    ]

    def __init__(self, dataDir=DATA_DIR):
        self.dataDir = dataDir

    def appendUiEvent(self, state, event, detail=None):
        """
        Log a BidScreen (or other) UI event to ``<auctionBasename>_events.csv``.

        Only logs the researcher-relevant events (HELP / PAUSE).
        """
        if event not in ("help_pressed", "auction_paused", "auction_resumed"):
            return
        if not state.subjectId or not state.subjectId.strip():
            print("AuctionCsvLogger: skip UI event (no subject id yet).", event)
            return

        detail = dict(detail) if detail else {}
        path = buildEventsCsvPath(state, self.dataDir)
        wall_ts = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        label = detail.get("label")
        if not label:
            if event == "help_pressed":
                label = "ALERT"
            elif event == "auction_paused":
                label = "PAUSED EXPERIMENT"
            elif event == "auction_resumed":
                label = "RESUMED EXPERIMENT"
            else:
                label = event
        row = [
            _excel_text(wall_ts),
            str(label),
        ]

        try:
            file_exists = os.path.isfile(path)
            write_header = not file_exists or os.path.getsize(path) == 0

            with open(path, "a", newline="") as f:
                w = csv.writer(f)
                if write_header:
                    w.writerow(["subjID:", state.subjectId.strip()])
                    w.writerow(["Condition:", state.trialCond])
                    w.writerow(["Trial #:", state.trialNum])
                    _d, _t = _split_session_timestamp(getattr(state, "sessionStartTimestamp", ""))
                    w.writerow(["Date:", _excel_text(_d)])
                    w.writerow(["Experiment Time:", _excel_text(_t)])
                    w.writerow(["Treadmill Speed:", _cell(getattr(state, "treadmillSpeedSetting", ""))])
                    w.writerow(["Heart Rate (Baseline):", _cell(getattr(state, "heartRateBaselineSetting", ""))])
                    w.writerow(["Preferred Stiffness (N/mm):", _preferred_stiffness_metadata(state)])
                    w.writerow(["logType", "ui_events"])
                    w.writerow([])
                    w.writerow(self.EVENT_HEADERS)
                w.writerow(row)
        except Exception as e:
            print("AuctionCsvLogger: failed to write UI event", path, e)

    def appendRound(self, state, result):
        """Append one row from `ExperimentController.finalizeRound` result dict."""
        if not state.subjectId or not state.subjectId.strip():
            print("AuctionCsvLogger: skip write (no subject id yet).")
            return

        auctionPath, _ = buildSessionPaths(state, self.dataDir)

        treadmillSpeedMs = result.get("treadmillSpeedMs")
        treadmillDistanceKm = result.get("treadmillDistanceKm")
        treadmillDistanceM = None if treadmillDistanceKm is None else float(treadmillDistanceKm) * 1000.0

        row = [
            result.get("roundIndex", ""),
            _excel_text(_time_only(result.get("roundStartTimestamp"))),
            _excel_text(_time_only(result.get("roundEndTimestamp", result.get("timestamp", "")))),
            result.get("humanBid", ""),
            result.get("humanWon", ""),
            result.get("lowestBid", ""),
            result.get("payout", ""),
            result.get("totalPayout", ""),
            _cell(treadmillDistanceM),
        ]

        try:
            fileExists = os.path.isfile(auctionPath)
            writeHeader = not fileExists or os.path.getsize(auctionPath) == 0

            with open(auctionPath, "a", newline="") as f:
                w = csv.writer(f)
                if writeHeader:
                    # Title / metadata block
                    w.writerow(["subjID:", state.subjectId.strip()])
                    w.writerow(["Condition:", state.trialCond])
                    w.writerow(["Trial #:", state.trialNum])
                    _d, _t = _split_session_timestamp(result.get("sessionStartTimestamp"))
                    w.writerow(["Date:", _excel_text(_d)])
                    w.writerow(["Experiment Time:", _excel_text(_t)])
                    w.writerow(["Treadmill Speed:", _cell(getattr(state, "treadmillSpeedSetting", ""))])
                    w.writerow(["Heart Rate (Baseline):", _cell(getattr(state, "heartRateBaselineSetting", ""))])
                    w.writerow(["Preferred Stiffness (N/mm):", _preferred_stiffness_metadata(state)])
                    w.writerow([])  # blank line between metadata and table

                    # Table header + units row
                    w.writerow(self.HEADERS)
                    w.writerow(self.UNITS)
                w.writerow(row)
        except Exception as e:
            print("AuctionCsvLogger: failed to write", auctionPath, e)
