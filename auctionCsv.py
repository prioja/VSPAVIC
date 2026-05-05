"""
Append auction results to a per-session CSV.

Auction format (Vickrey second-price, lowest-bid wins):
  The lowest bid wins the item; the clearing price / payout side uses the
  second-lowest bid among all bids (human + robots). Same structure as a standard
  Vickrey auction but inverted from highest-bid wording.

Files (matches your terminal naming):
  auctionFilename = "VSPAVIC" + subject + "_A_" + condition + trial + ".csv"
  Example: VSPAVIC001_A_TH1.csv where TH + 1 is short condition code + trial number.

Heart-rate path:
  hrFilename = "VSPAVIC" + subject + "_HR_" + condition + trial + ".csv"
  (computed below; HR logging not implemented yet — commented example in appendRound.)
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
    Returns (auctionPath, hrPath, auctionFilename, hrFilename).
    """
    subj = "".join((state.subjectId or "").split())
    cc = conditionCodeFromUI(state.trialCond)
    trial = (state.trialNum or "").strip()
    if not trial or trial == "Select Trial":
        trial = "X"

    condTrial = f"{cc}{trial}"
    auctionFilename = f"VSPAVIC{subj}_A_{condTrial}.csv"
    hrFilename = f"VSPAVIC{subj}_HR_{condTrial}.csv"

    os.makedirs(dataDir, exist_ok=True)
    auctionPath = os.path.join(dataDir, auctionFilename)
    hrPath = os.path.join(dataDir, hrFilename)

    return auctionPath, hrPath, auctionFilename, hrFilename


def buildEventsCsvPath(state, dataDir=DATA_DIR):
    """Companion log for UI events (HELP / PAUSE), same folder as the auction CSV."""
    auctionPath, _hrPath, _af, _hf = buildSessionPaths(state, dataDir)
    root, ext = os.path.splitext(auctionPath)
    return f"{root}_events{ext}"


def _cell(value):
    if value is None:
        return ""
    return value


class AuctionCsvLogger:
    """One CSV per session; one row per finalized round.
    UI events (HELP / PAUSE) append to a sibling ``*_events.csv`` file.
    """

    # Table columns (metadata like subject/condition/trial are written as a title block above)
    HEADERS = [
        "round_number",
        "round_start_timestamp",
        "round_end_timestamp",
        "subject_bid",
        "human_won",
        "lowest_bid",
        "vickrey_price_second_lowest",
        "total_subject_winnings",
        "treadmill_speed",
        "treadmill_distance",
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
        "m/s",
        "m",
    ]

    EVENT_HEADERS = [
        "wall_timestamp",
        "event",
        "round_index",
        "pending_instant_round",
        "auction_paused",
        "detail_json",
    ]

    def __init__(self, dataDir=DATA_DIR):
        self.dataDir = dataDir

    def appendUiEvent(self, state, event, detail=None):
        """
        Log a BidScreen (or other) UI event to ``<auctionBasename>_events.csv``.

        ``event`` examples: help_pressed, auction_paused, auction_resumed.
        ``detail`` is optional JSON-serializable context (merged into detail_json column).
        """
        if not state.subjectId or not state.subjectId.strip():
            print("AuctionCsvLogger: skip UI event (no subject id yet).", event)
            return

        detail = dict(detail) if detail else {}
        path = buildEventsCsvPath(state, self.dataDir)
        wall_ts = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        row = [
            wall_ts,
            event,
            getattr(state, "roundIndex", ""),
            int(bool(getattr(state, "pendingInstantRound", False))),
            int(bool(getattr(state, "auctionPaused", False))),
            json.dumps(detail, separators=(",", ":"), default=str),
        ]

        try:
            file_exists = os.path.isfile(path)
            write_header = not file_exists or os.path.getsize(path) == 0

            with open(path, "a", newline="") as f:
                w = csv.writer(f)
                if write_header:
                    w.writerow(["subjectId", state.subjectId.strip()])
                    w.writerow(["trialCondition", state.trialCond])
                    w.writerow(["trialNumber", state.trialNum])
                    w.writerow(["sessionStartTimestamp", _cell(getattr(state, "sessionStartTimestamp", ""))])
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

        auctionPath, hrPath, auctionFilename, hrFilename = buildSessionPaths(
            state, self.dataDir
        )

        # Heart-rate file (future): same naming as terminal script — uncomment when wiring HR.
        # hrFilename = f"VSPAVIC{subj}_HR_{condTrial}.csv"
        # hrPath = os.path.join(self.dataDir, hrFilename)
        _ = hrFilename, hrPath, auctionFilename

        treadmillSpeedMs = result.get("treadmillSpeedMs")
        treadmillDistanceKm = result.get("treadmillDistanceKm")
        treadmillDistanceM = None if treadmillDistanceKm is None else float(treadmillDistanceKm) * 1000.0

        row = [
            result.get("roundIndex", ""),
            _cell(result.get("roundStartTimestamp")),
            _cell(result.get("roundEndTimestamp", result.get("timestamp", ""))),
            result.get("humanBid", ""),
            result.get("humanWon", ""),
            result.get("lowestBid", ""),
            result.get("payout", ""),
            result.get("totalPayout", ""),
            _cell(treadmillSpeedMs),
            _cell(treadmillDistanceM),
        ]

        try:
            fileExists = os.path.isfile(auctionPath)
            writeHeader = not fileExists or os.path.getsize(auctionPath) == 0

            with open(auctionPath, "a", newline="") as f:
                w = csv.writer(f)
                if writeHeader:
                    # Title / metadata block
                    w.writerow(["subjectId", state.subjectId.strip()])
                    w.writerow(["trialCondition", state.trialCond])
                    w.writerow(["trialNumber", state.trialNum])
                    w.writerow(["sessionStartTimestamp", _cell(result.get("sessionStartTimestamp"))])
                    w.writerow(["auctionType", "Vickrey second-price (lowest bid wins)"])
                    w.writerow([])  # blank line between metadata and table

                    # Table header + units row
                    w.writerow(self.HEADERS)
                    w.writerow(self.UNITS)
                w.writerow(row)
        except Exception as e:
            print("AuctionCsvLogger: failed to write", auctionPath, e)
