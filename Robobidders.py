import numpy as np


class robobidder():
    # behavior:
    #   walk: follows exponential trend ~ k * e^(b * t) (t = cumulative walk time)
    #   robobid: returns current robovalue (noise only at __init__)

    def __init__(self, k, b):
        self.k = k
        self.b = b
        self.walk_time = 0.0
        # One-time noise so bidders differ within and across sessions.
        self.robovalue = self.k + np.random.normal(loc=0, scale=0.01)

    def walk(self, walk_end_time, walk_start_time):
        """Advance along k*exp(b*t) by adding (walk_end_time - walk_start_time) to cumulative t."""
        dt = max(0.0, float(walk_end_time) - float(walk_start_time))
        self.walk_for_duration(dt)

    def walk_for_duration(self, duration):
        """Add ``duration`` (same units as ``b``, e.g. minutes) and set value on the curve."""
        self.walk_time += max(0.0, float(duration))
        self.robovalue = self.k * np.exp(self.b * self.walk_time)

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
