

class State:
    def __init__(self):
        # Participant/session info (filled on Start screen)
        self.subjectId = ""
        self.trialCond = ""
        self.trialNum = ""
        self.sessionStartTimestamp = ""
        self.roundStartTimestamp = ""

        # Auction timing/state
        self.auctionStarted = False
        self.auctionStartPerf = None  # set on first SUBMIT (perf_counter seconds)

        # Round bookkeeping
        self.roundIndex = -1
        self.roundStartPerf = None
        self.roundEndPerf = None
        self.lastSubmittedBid = None
        # First round after START: submit finalizes immediately (no 2-min timer).
        self.pendingInstantRound = False

        # Pause (timed rounds only): freezes countdown by shifting roundEndPerf forward.
        self.auctionPaused = False
        self.pauseRemainingSeconds = None

        # Current round values
        self.humanBid = 0.0
        self.robotBidsLocked = []
        self.currentBids = []

        # Outcomes / totals
        self.lastResult = None
        self.results = []
        self.totalPayout = 0.0

        # Session end condition (configured in main.py)
        self.totalRounds = None

        # Optional session timing config (randomized per session)
        self.totalAuctionSeconds = None
        self.minAuctionSeconds = None
        self.maxAuctionSeconds = None

        # Researcher-provided session settings (sent from researcher machine at launch)
        self.treadmillSpeedSetting = ""  # free-form (e.g. "1.2 m/s" or "1.2")
        self.preferredStiffnessNPerMm = ""  # free-form numeric text (N/mm)



