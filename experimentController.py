import time
from datetime import datetime
import random

from auctionCsv import AuctionCsvLogger
from Robobidders import roboModel


class ExperimentController:
    """
    Minimal controller to bridge GUI -> experiment logic.

    Auction: Vickrey second-price with lowest bid winning — among all bids (human + robots),
    the lowest bid wins; the associated second-lowest bid is used as the Vickrey price /
    payout term (same second-price logic as usual Vickrey, inverted from “highest wins”).

    Round flow:
    - First round after START is instant: first SUBMIT finalizes immediately (no timer).
    - Later rounds are 2 minutes: when BidScreen appears (after Result), the timed round
      starts immediately (robot bids lock + countdown visible). Multiple SUBMITs
      overwrite; winner decided at buzzer using last SUBMIT.
    """

    def __init__(self, state, hardware=None, csvLogger=None):
        self.state = state
        self.hardware = hardware
        self.csvLogger = csvLogger if csvLogger is not None else AuctionCsvLogger()
        self.roundSeconds = 120.0

        # Robo-bidder parameters (from your terminal script)
        self.robo_k = 0.4395073979128712
        self.robo_b = 0.05735650555767768
        self.robo_n = 2
        self.roboModel = roboModel(self.robo_k, self.robo_b, self.robo_n)

    def getSessionConfigSnapshot(self):
        """
        A small, JSON-serializable config snapshot suitable for monitor/event logging.
        """
        st = self.state
        return {
            "roundSeconds": float(getattr(self, "roundSeconds", 0.0) or 0.0),
            "totalRounds": getattr(st, "totalRounds", None),
            "totalAuctionSeconds": getattr(st, "totalAuctionSeconds", None),
            "minAuctionSeconds": getattr(st, "minAuctionSeconds", None),
            "maxAuctionSeconds": getattr(st, "maxAuctionSeconds", None),
            "auctionType": "Vickrey second-price (lowest bid wins)",
            "roboModel": {
                "name": type(self.roboModel).__name__,
                "count": int(getattr(self, "robo_n", 0) or 0),
                "k": float(getattr(self, "robo_k", 0.0) or 0.0),
                "b": float(getattr(self, "robo_b", 0.0) or 0.0),
            },
        }

    def configureSessionTotalTimeSeconds(self, minSeconds, maxSeconds, includeInstantFirstRound=True):
        """
        Randomly choose a session total bidding time in [minSeconds, maxSeconds] and
        compute totalRounds by rounding down the number of timed rounds that fit.

        totalRounds = timedRounds + (1 if includeInstantFirstRound else 0)
        """
        try:
            mn = float(minSeconds)
            mx = float(maxSeconds)
        except Exception:
            return False
        if mx < mn:
            mn, mx = mx, mn

        chosen = float(random.uniform(mn, mx))
        self.state.minAuctionSeconds = mn
        self.state.maxAuctionSeconds = mx
        self.state.totalAuctionSeconds = chosen

        rs = float(self.roundSeconds or 0.0)
        timedRounds = int(chosen // rs) if rs > 0 else 0
        base = 1 if includeInstantFirstRound else 0
        self.state.totalRounds = max(base, base + timedRounds)
        return True

    def startIfNeeded(self):
        if self.state.auctionStarted:
            return
        self.state.auctionStarted = True
        self.state.auctionStartPerf = time.perf_counter()

    def markFirstRoundInstant(self):
        """Call when participant presses START (before first bid)."""
        self.state.pendingInstantRound = True

    def startRoundIfNeeded(self):
        """
        Starts the *current* round (locks robot bids + sets round end time) if not already started.

        Important: this does NOT run just because BidScreen is shown.
        We'll call it on the first submit of a round.
        """
        if self.state.roundStartPerf is not None:
            return
        self.state.roundStartPerf = time.perf_counter()
        self.state.roundStartTimestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        if self.state.pendingInstantRound:
            self.state.roundEndPerf = None
        else:
            self.state.roundEndPerf = self.state.roundStartPerf + self.roundSeconds
        self.state.robotBidsLocked = self.roboModel.get_bids()

    def startTimedRoundNow(self):
        """
        Begin a timed (120s) round immediately: lock robot bids and start countdown.

        Used when returning to BidScreen after Result (round 2+), so the timer is visible
        as soon as the participant can bid — not on first SUBMIT.
        """
        self.startIfNeeded()
        if self.state.pendingInstantRound:
            return
        if self.state.roundStartPerf is not None:
            return

        self.state.roundStartPerf = time.perf_counter()
        self.state.roundStartTimestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        self.state.roundEndPerf = self.state.roundStartPerf + self.roundSeconds
        self.state.robotBidsLocked = self.roboModel.get_bids()
        self.state.lastSubmittedBid = None
        self.state.auctionPaused = False
        self.state.pauseRemainingSeconds = None

    def onBidScreenEntered(self):
        """Call from BidScreen.on_pre_enter to auto-start timed rounds when appropriate."""
        self.startTimedRoundNow()

    def submitBidForCurrentRound(self, humanBid):
        """
        Records the *latest* submitted bid for the current round.
        (Multiple submits overwrite; only the last one counts at finalize.)
        """
        self.startIfNeeded()
        # If the round hasn't begun yet (first instant round), start it here.
        # If BidScreen already started a timed round on entry, do not restart here.
        if self.state.roundStartPerf is None:
            self.startRoundIfNeeded()

        self.state.lastSubmittedBid = float(humanBid)
        return self.state.lastSubmittedBid

    def getSecondsRemaining(self):
        if self.state.roundEndPerf is None:
            return None
        if self.state.auctionPaused and self.state.pauseRemainingSeconds is not None:
            return max(0.0, float(self.state.pauseRemainingSeconds))
        return max(0.0, self.state.roundEndPerf - time.perf_counter())

    def pauseAuction(self):
        """Pause timed round countdown (does nothing if there is no active timer)."""
        if self.state.roundEndPerf is None:
            return False
        if self.state.auctionPaused:
            return False

        remaining = max(0.0, self.state.roundEndPerf - time.perf_counter())
        if remaining <= 0.0:
            return False
        self.state.pauseRemainingSeconds = float(remaining)
        self.state.auctionPaused = True
        # Shift end time far into the future so perf_counter-based countdown freezes.
        self.state.roundEndPerf = time.perf_counter() + 10**9
        return True

    def resumeAuction(self):
        """Resume timed round countdown after pauseAuction()."""
        if not self.state.auctionPaused:
            return False
        if self.state.pauseRemainingSeconds is None:
            self.state.auctionPaused = False
            return False

        self.state.roundEndPerf = time.perf_counter() + float(self.state.pauseRemainingSeconds)
        self.state.pauseRemainingSeconds = None
        self.state.auctionPaused = False
        return True

    def toggleAuctionPause(self):
        if self.state.auctionPaused:
            return self.resumeAuction()
        return self.pauseAuction()

    def finalizeRound(self):
        """
        Finalize one round using the LAST submitted human bid.
        Returns a plain dict you can show on a Result screen later.
        """
        self.startIfNeeded()
        if self.state.roundStartPerf is None:
            raise RuntimeError("Round has not started yet. Call submitBidForCurrentRound() first.")

        roundEndPerf = time.perf_counter()
        roundEndTimestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

        self.state.roundIndex += 1
        humanParticipated = self.state.lastSubmittedBid is not None
        self.state.humanBid = float(self.state.lastSubmittedBid) if humanParticipated else None

        currentBids = ([] if self.state.humanBid is None else [self.state.humanBid]) + list(
            self.state.robotBidsLocked
        )
        self.state.currentBids = currentBids

        lowestBid = min(currentBids)
        lowestBidIdx = currentBids.index(lowestBid)  # 0 means human (only if humanParticipated)
        sortedBids = sorted(currentBids)
        payout = sortedBids[1] if len(sortedBids) > 1 else sortedBids[0]

        humanWon = humanParticipated and lowestBidIdx == 0
        if humanWon:
            self.state.totalPayout += payout
        else:
            # Update the winning robot's "walk" model so future bids change.
            # This mirrors your terminal logic at a high level.
            # (We don't yet have per-round timing wired in, so we use roundIndex as a simple proxy.)
            if humanParticipated:
                winnerRobot = self.roboModel.robobidderlist[lowestBidIdx - 1]
            else:
                winnerRobot = self.roboModel.robobidderlist[lowestBidIdx]
            tEnd = float(self.state.roundIndex + 1)
            tStart = float(self.state.roundIndex)
            winnerRobot.walk(tEnd, tStart)

        result = {
            "timestamp": roundEndTimestamp,
            "roundEndTimestamp": roundEndTimestamp,
            "roundEndPerf": roundEndPerf,
            "roundIndex": self.state.roundIndex,
            "roundStartTimestamp": self.state.roundStartTimestamp or "",
            "sessionStartTimestamp": getattr(self.state, "sessionStartTimestamp", "") or "",
            "humanBid": self.state.humanBid,
            "humanParticipated": humanParticipated,
            "robotBids": list(self.state.robotBidsLocked),
            "currentBids": list(currentBids),
            "lowestBid": lowestBid,
            "payout": payout,
            "humanWon": humanWon,
            "totalPayout": self.state.totalPayout,
        }

        if self.hardware is not None and humanParticipated:
            try:
                self.hardware.applyRoundOutcome(humanWon)
            except Exception as e:
                print("ExperimentController: treadmill command failed:", e)

        treadmillSpeedMs, treadmillDistanceKm = None, None
        if self.hardware is not None:
            treadmillSpeedMs, treadmillDistanceKm = self.hardware.readMetrics()

        result["treadmillSpeedMs"] = treadmillSpeedMs
        result["treadmillDistanceKm"] = treadmillDistanceKm

        self.csvLogger.appendRound(self.state, result)

        self.state.lastResult = result
        self.state.results.append(result)
        # Clear round state so the next submit starts a new round.
        self.state.robotBidsLocked = []
        self.state.roundStartPerf = None
        self.state.roundEndPerf = None
        self.state.roundStartTimestamp = ""
        self.state.lastSubmittedBid = None
        self.state.pendingInstantRound = False
        self.state.auctionPaused = False
        self.state.pauseRemainingSeconds = None
        return result

