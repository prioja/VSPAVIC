import numpy as np
from scipy.stats import truncnorm

# Truncated-normal multiplier on curve value after walking (0.85–1.15, mean 1.0).
mulMu, mulSigma = 1.0, 0.05
mulLo, mulHi = 0.85, 1.15
mulA = (mulLo - mulMu) / mulSigma
mulB = (mulHi - mulMu) / mulSigma


class robobidder():
    # behavior:
    #   walk: follows exponential trend ~ k_i * e^(b * t) (t = cumulative walk time)
    #   k_i: per-robot intercept (population k + one-time noise at __init__)

    def __init__(self, k, b):
        self.k = k
        self.b = b
        self.walk_time = 0.0
        # One-time noise sets each robot's personal k_i for the whole session.
        self.k_i = self.k + np.random.normal(loc=0, scale=0.025)
        self.robovalue = self.k_i

    def walk(self, walk_end_time, walk_start_time):
        """Advance along k_i*exp(b*t) by adding (walk_end_time - walk_start_time) to cumulative t."""
        dt = max(0.0, float(walk_end_time) - float(walk_start_time))
        self.walk_for_duration(dt)

    def walk_for_duration(self, duration):
        """Add ``duration`` (same units as ``b``, e.g. minutes) and set value on the curve."""
        self.walk_time += max(0.0, float(duration))
        base = self.k_i * np.exp(self.b * self.walk_time)
        multiplier = float(truncnorm.rvs(mulA, mulB, loc=mulMu, scale=mulSigma))
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

    def name(self):
        modelName = "k: {:.4f}, b: {:.4f}, number of robobidders: {}"
        return modelName.format(self.k, self.b, len(self.robobidderlist))
