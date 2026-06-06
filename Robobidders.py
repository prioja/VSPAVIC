import numpy as np

# One-sided uniform multiplier on curve value after walking (1.05–1.15).
mulLo, mulHi = 1.05, 1.15


class robobidder():
    # behavior:
    #   walk: follows exponential trend ~ k_i * e^(b * t) (t = cumulative walk time)
    #   k_i: per-robot intercept (population k + one-time noise at __init__)

    def __init__(self, k, b):
        self.k = k
        self.b = b
        self.walk_time = 0.0
        # Minutes banked from each human walking phase since this robot last won.
        self.pendingWalkMinutes = 0.0
        # One-time noise sets each robot's personal k_i for the whole session.
        self.k_i = self.k + np.random.normal(loc=0, scale=0.025)
        self.robovalue = self.k_i

    def bankWalkMinutes(self, duration):
        """Accumulate uncredited walk time until this robot wins again."""
        self.pendingWalkMinutes += max(0.0, float(duration))

    def applyPendingWalk(self):
        """Advance the bid curve by all banked walk time; reset the bank."""
        dt = float(self.pendingWalkMinutes or 0.0)
        if dt <= 0.0:
            return 0.0
        self.pendingWalkMinutes = 0.0
        self.walk_for_duration(dt)
        return dt

    def walk(self, walk_end_time, walk_start_time):
        """Advance along k_i*exp(b*t) by adding (walk_end_time - walk_start_time) to cumulative t."""
        dt = max(0.0, float(walk_end_time) - float(walk_start_time))
        self.walk_for_duration(dt)

    def walk_for_duration(self, duration):
        """Add ``duration`` (same units as ``b``, e.g. minutes) and set value on the curve."""
        self.walk_time += max(0.0, float(duration))
        base = self.k_i * np.exp(self.b * self.walk_time)
        multiplier = float(np.random.uniform(mulLo, mulHi))
        self.robovalue = base * multiplier

    def robobid(self):
        return round(float(self.robovalue), 2)


class roboModel():

    def __init__(self, k, b, num_robobidders):
        self.k = k
        self.b = b
        self.robobidderlist = []
        for i in range(num_robobidders):
            self.robobidderlist.append(robobidder(k, b))

    def get_bids(self):
        return [rb.robobid() for rb in self.robobidderlist]

    def bankWalkMinutesForAll(self, duration):
        for rb in self.robobidderlist:
            rb.bankWalkMinutes(duration)

    def name(self):
        modelName = "k: {:.4f}, b: {:.4f}, number of robobidders: {}"
        return modelName.format(self.k, self.b, len(self.robobidderlist))
