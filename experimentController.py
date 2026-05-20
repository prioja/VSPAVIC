import threading
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
    - Round 2+: walking (roundSeconds) -> 60s rest (bidWindowSeconds bid while stopped,
      then resultScreenSeconds results while stopped) -> treadmill win/loss -> walking again.
    - Treadmill outcome is applied when leaving the result screen, not at finalize.
    """

    def __init__(self, state, hardware=None, csvLogger=None):
        self.state = state
        self.hardware = hardware
        self.csvLogger = csvLogger if csvLogger is not None else AuctionCsvLogger()
        self.roundSeconds = 120.0
        self.bidWindowSeconds = 40.0
        self.resultScreenSeconds = 20.0
        # Start/stop Bertec this many seconds before the result screen closes.
        self.resultScreenBeltLeadSeconds = 10.0

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
            "bidWindowSeconds": float(getattr(self, "bidWindowSeconds", 0.0) or 0.0),
            "resultScreenSeconds": float(getattr(self, "resultScreenSeconds", 0.0) or 0.0),
            "restBreakSeconds": float(self.bidWindowSeconds or 0.0)
            + float(self.resultScreenSeconds or 0.0),
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
                "summary": self.roboModel.name(),
            },
        }

    def configureSessionTotalTimeSeconds(self, minSeconds, maxSeconds, includeInstantFirstRound=True):
        """
        Randomly choose a session total time and compute how many full cycles fit.

        After the instant first round, each cycle is:
        walking (roundSeconds) + rest bid (bidWindowSeconds) + results (resultScreenSeconds).
        """
        try:
            mn = float(minSeconds)
            mx = float(maxSeconds)
        except Exception:
            return False
        if mx < mn:
            mn, mx = mn

        chosen = float(random.uniform(mn, mx))
        self.state.minAuctionSeconds = mn
        self.state.maxAuctionSeconds = mx
        self.state.totalAuctionSeconds = chosen

        cycle = (
            float(self.roundSeconds or 0.0)
            + float(self.bidWindowSeconds or 0.0)
            + float(self.resultScreenSeconds or 0.0)
        )
        timedRounds = int(chosen // cycle) if cycle > 0 else 0
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

    def isWalkingPhase(self):
        if not getattr(self.state, "inWalkingPhase", False):
            return False
        if self.state.walkingEndPerf is None:
            return False
        return True

    def _sync_treadmill_speed_from_state(self):
        """Apply researcher/tablet treadmill speed text to hardware.walkSpeedMs."""
        if self.hardware is None:
            return
        raw = str(getattr(self.state, "treadmillSpeedSetting", "") or "").strip()
        if not raw:
            return
        cleaned = "".join(ch for ch in raw if (ch.isdigit() or ch in ".-"))
        try:
            sp = float(cleaned)
            if sp > 0.0:
                self.hardware.walkSpeedMs = sp
        except Exception:
            pass

    def _apply_treadmill_outcome(self, humanWon):
        if self.hardware is None:
            return
        self._sync_treadmill_speed_from_state()
        try:
            self.hardware.applyRoundOutcome(humanWon)
        except Exception as e:
            print("ExperimentController: treadmill command failed:", e)
        self.state.treadmillOutcomeApplied = True

    def applyTreadmillOutcomeForLastResult(self):
        """
        Apply win/loss belt commands once for the current lastResult.
        Called during the last ~10s on the result screen, or when leaving result.
        """
        if getattr(self.state, "treadmillOutcomeApplied", False):
            return
        result = self.state.lastResult
        if not isinstance(result, dict) or not result.get("humanParticipated"):
            return
        human_won = bool(result.get("humanWon"))

        def _belt_commands():
            self._apply_treadmill_outcome(human_won)

        if self.hardware is not None and getattr(self.hardware, "enabled", False):
            threading.Thread(target=_belt_commands, daemon=True).start()
        else:
            _belt_commands()

    def onReturningToBidAfterResult(self):
        """
        Leaving the result screen: ensure belt commands ran, then start walking phase.
        """
        self.applyTreadmillOutcomeForLastResult()
        self.beginWalkingPhase()

    def beginWalkingPhase(self):
        """Walk until roundSeconds elapses; then rest bid window begins (belts stopped)."""
        self.startIfNeeded()
        self.state.pendingInstantRound = False
        self.state.inWalkingPhase = True
        self.state.walkingStartPerf = time.perf_counter()
        self.state.walkingEndPerf = self.state.walkingStartPerf + float(self.roundSeconds)
        self.state.roundStartPerf = None
        self.state.roundEndPerf = None
        self.state.robotBidsLocked = []
        self.state.lastSubmittedBid = None
        self.state.auctionPaused = False
        self.state.pauseRemainingSeconds = None

    def onWalkingPhaseEnded(self):
        """End walking segment, stop belts, open the 40s rest bid window."""
        if self.state.walkingStartPerf is not None:
            self.state.pendingWalkMinutesForRobots = max(
                0.0,
                (time.perf_counter() - self.state.walkingStartPerf) / 60.0,
            )
        self.state.inWalkingPhase = False
        self.state.walkingEndPerf = None
        self.state.walkingStartPerf = None
        if self.hardware is not None:
            try:
                self.hardware.stopBelts()
            except Exception as e:
                print("ExperimentController: stop before rest bid failed:", e)
        self.beginRestBidWindow()

    def beginRestBidWindow(self):
        """Treadmill stopped; participant has bidWindowSeconds to submit a bid."""
        self.startIfNeeded()
        if self.state.pendingInstantRound:
            return

        if self.hardware is not None:
            try:
                self.hardware.stopBelts()
            except Exception as e:
                print("ExperimentController: stop for rest bid failed:", e)

        self.state.inWalkingPhase = False
        self.state.walkingEndPerf = None
        self.state.walkingStartPerf = None
        self.state.roundStartPerf = time.perf_counter()
        self.state.roundStartTimestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        self.state.roundEndPerf = self.state.roundStartPerf + float(self.bidWindowSeconds)
        self.state.robotBidsLocked = self.roboModel.get_bids()
        self.state.lastSubmittedBid = None
        self.state.auctionPaused = False
        self.state.pauseRemainingSeconds = None

    def startRoundIfNeeded(self):
        """
        Starts the *current* round (locks robot bids + sets round end time) if not already started.
        Used for the instant first round on first SUBMIT.
        """
        if self.state.roundStartPerf is not None:
            return
        self.state.roundStartPerf = time.perf_counter()
        self.state.roundStartTimestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        if self.state.pendingInstantRound:
            self.state.roundEndPerf = None
        else:
            self.state.roundEndPerf = self.state.roundStartPerf + float(self.bidWindowSeconds)
        self.state.robotBidsLocked = self.roboModel.get_bids()

    def onBidScreenEntered(self):
        """Bid screen shown; phase timers are started elsewhere (walking / rest bid)."""
        return

    def submitBidForCurrentRound(self, humanBid):
        """
        Records the *latest* submitted bid for the current round.
        (Multiple submits overwrite; only the last one counts at finalize.)
        """
        if self.isWalkingPhase():
            return None
        self.startIfNeeded()
        if self.state.roundStartPerf is None:
            self.startRoundIfNeeded()

        self.state.lastSubmittedBid = float(humanBid)
        return self.state.lastSubmittedBid

    def getWalkingSecondsRemaining(self):
        if not self.isWalkingPhase():
            return None
        if self.state.auctionPaused and self.state.pauseRemainingSeconds is not None:
            return max(0.0, float(self.state.pauseRemainingSeconds))
        return max(0.0, self.state.walkingEndPerf - time.perf_counter())

    def getSecondsRemaining(self):
        """Seconds left in the rest bid window (not walking)."""
        if self.isWalkingPhase():
            return None
        if self.state.roundEndPerf is None:
            return None
        if self.state.auctionPaused and self.state.pauseRemainingSeconds is not None:
            return max(0.0, float(self.state.pauseRemainingSeconds))
        return max(0.0, self.state.roundEndPerf - time.perf_counter())

    def _active_phase_remaining(self):
        if self.isWalkingPhase():
            return self.getWalkingSecondsRemaining()
        return self.getSecondsRemaining()

    def pauseAuction(self):
        """Pause walking or rest-bid countdown."""
        remaining = self._active_phase_remaining()
        if remaining is None or remaining <= 0.0:
            return False
        if self.state.auctionPaused:
            return False

        self.state.pauseRemainingSeconds = float(remaining)
        self.state.auctionPaused = True
        if self.isWalkingPhase():
            self.state.walkingEndPerf = time.perf_counter() + 10**9
        elif self.state.roundEndPerf is not None:
            self.state.roundEndPerf = time.perf_counter() + 10**9
        return True

    def resumeAuction(self):
        """Resume walking or rest-bid countdown after pauseAuction()."""
        if not self.state.auctionPaused:
            return False
        if self.state.pauseRemainingSeconds is None:
            self.state.auctionPaused = False
            return False

        end_at = time.perf_counter() + float(self.state.pauseRemainingSeconds)
        if self.isWalkingPhase():
            self.state.walkingEndPerf = end_at
        else:
            self.state.roundEndPerf = end_at
        self.state.pauseRemainingSeconds = None
        self.state.auctionPaused = False
        return True

    def toggleAuctionPause(self):
        if self.state.auctionPaused:
            return self.resumeAuction()
        return self.pauseAuction()

    def _round_walk_duration_minutes(self, round_start_perf, round_end_perf):
        """Wall-clock minutes for this round (used as Δt on the robo walk curve)."""
        if round_start_perf is None:
            return 0.0
        end = round_end_perf if round_end_perf is not None else time.perf_counter()
        return max(0.0, (end - round_start_perf) / 60.0)

    def _lowest_bid_winner_indices(self, current_bids):
        if not current_bids:
            return []
        lowest = min(current_bids)
        return [i for i, b in enumerate(current_bids) if b == lowest]

    def _apply_walk_to_tied_robo_winners(self, winner_indices, human_participated, walk_dt_minutes):
        """Every robot tied at the lowest bid walks (2-way or 3-way ties included)."""
        if walk_dt_minutes <= 0.0:
            return
        for idx in winner_indices:
            if human_participated and idx == 0:
                continue
            robo_idx = idx - 1 if human_participated else idx
            if 0 <= robo_idx < len(self.roboModel.robobidderlist):
                self.roboModel.robobidderlist[robo_idx].walk_for_duration(walk_dt_minutes)

    def finalizeRound(self):
        """
        Finalize one round using the LAST submitted human bid.
        Treadmill win/loss is applied later in onReturningToBidAfterResult().
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

        lowestBid = min(currentBids) if currentBids else None
        winner_indices = self._lowest_bid_winner_indices(currentBids)
        sortedBids = sorted(currentBids)
        payout = sortedBids[1] if len(sortedBids) > 1 else sortedBids[0]

        humanWon = humanParticipated and 0 in winner_indices
        if humanWon:
            self.state.totalPayout += payout

        walk_dt_minutes = float(getattr(self.state, "pendingWalkMinutesForRobots", 0.0) or 0.0)
        if walk_dt_minutes <= 0.0:
            walk_dt_minutes = self._round_walk_duration_minutes(
                self.state.roundStartPerf, roundEndPerf
            )
        self.state.pendingWalkMinutesForRobots = 0.0
        self._apply_walk_to_tied_robo_winners(
            winner_indices, humanParticipated, walk_dt_minutes
        )

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

        treadmillSpeedMs, treadmillDistanceKm = None, None
        if self.hardware is not None:
            treadmillSpeedMs, treadmillDistanceKm = self.hardware.readMetrics()

        result["treadmillSpeedMs"] = treadmillSpeedMs
        result["treadmillDistanceKm"] = treadmillDistanceKm

        self.csvLogger.appendRound(self.state, result)

        self.state.lastResult = result
        self.state.results.append(result)
        self.state.treadmillOutcomeApplied = False
        self.state.robotBidsLocked = []
        self.state.roundStartPerf = None
        self.state.roundEndPerf = None
        self.state.roundStartTimestamp = ""
        self.state.lastSubmittedBid = None
        self.state.pendingInstantRound = False
        self.state.auctionPaused = False
        self.state.pauseRemainingSeconds = None
        self.state.inWalkingPhase = False
        self.state.walkingEndPerf = None
        self.state.walkingStartPerf = None
        return result
