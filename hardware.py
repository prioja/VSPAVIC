"""
Treadmill control for the Bertec over TCP (via `BertecMan.Bertec`).

- Use `TreadmillHardware` from the Kivy app: quick commands only (no blocking loops).
- Run this file directly for a terminal smoke test: `python hardware.py`
"""

import os
import time

from BertecMan import Bertec


class TreadmillHardware:
    """Thin wrapper around `Bertec` with experiment-friendly helpers."""

    def __init__(
        self,
        viconPcIp=None,
        enabled=None,
        walkSpeedMs=0,
        walkAccelMs2=0.1,
        stopAccelMs2=0.1,
        defaultInclineDeg=0.0,
    ):
        self.viconPcIp = viconPcIp or os.environ.get("VSPA_BERTEC_IP", "141.212.77.30")
        if enabled is None:
            enabled = os.environ.get("VSPA_TREADMILL", "").strip().lower() in ("1", "true", "yes")
        self.enabled = bool(enabled)

        self.walkSpeedMs = walkSpeedMs
        self.walkAccelMs2 = walkAccelMs2
        self.stopAccelMs2 = stopAccelMs2
        self.defaultInclineDeg = defaultInclineDeg

        self.bt = None
        self.lastConnectError = None
        # Cache of our last intended motion state to avoid spamming commands.
        # Possible values: "walking", "stopped", None (unknown).
        self.lastMotionState = None
        self.walkingSpeedThresholdMs = 0.05

    @property
    def isConnected(self):
        return self.bt is not None

    def connect(self):
        """Open socket + reader thread. Call once when the tablet is on the lab network."""
        if not self.enabled:
            print("TreadmillHardware: disabled (set VSPA_TREADMILL=1 to enable).")
            return
        if self.isConnected:
            return
        print(f"TreadmillHardware: connecting to {self.viconPcIp}...")
        self.lastConnectError = None
        try:
            self.bt = Bertec(viconPC_IP=self.viconPcIp)
            self.bt.start()
            print("TreadmillHardware: connected.")
        except Exception as e:
            self.lastConnectError = repr(e)
            self.bt = None
            print("TreadmillHardware: connection failed:", e)

    def disconnect(self):
        if self.bt is None:
            return
        try:
            self.stopBelts()
            time.sleep(0.3)
        except Exception as e:
            print("TreadmillHardware: stop before disconnect failed:", e)
        try:
            self.bt.stop()
        except Exception as e:
            print("TreadmillHardware: Bertec.stop failed:", e)
        self.bt = None
        print("TreadmillHardware: disconnected.")

    def setIncline(self, inclineDeg):
        if not self.isConnected:
            return
        self.bt.write_command(speedR=0.0, speedL=0.0, incline=float(inclineDeg))

    def stopBelts(self):
        if not self.isConnected:
            return
        print("TreadmillHardware: COMMAND stopBelts()")
        self.bt.write_command(
            speedR=0.0,
            speedL=0.0,
            accR=self.stopAccelMs2,
            accL=self.stopAccelMs2,
        )
        self.lastMotionState = "stopped"

    def startBelts(self, speedMs=None, accelMs2=None):
        if not self.isConnected:
            return
        sp = float(self.walkSpeedMs if speedMs is None else speedMs)
        ac = float(self.walkAccelMs2 if accelMs2 is None else accelMs2)
        print(f"TreadmillHardware: COMMAND startBelts(speed={sp}, accel={ac})")
        self.bt.write_command(speedR=sp, speedL=sp, accR=ac, accL=ac)
        self.lastMotionState = "walking"

    def isWalking(self):
        """
        Best-effort check of current treadmill motion.
        Uses measured speed when available; falls back to last commanded state.
        """
        if not self.isConnected:
            return False
        try:
            return float(self.bt.speed) > self.walkingSpeedThresholdMs
        except Exception:
            return self.lastMotionState == "walking"

    def prepareSession(self):
        """Belts stopped, incline set to default (non-blocking)."""
        if not self.enabled:
            return
        self.connect()
        if self.isConnected:
            try:
                self.bt.reset_odometer()
            except Exception as e:
                print("TreadmillHardware: reset_odometer failed:", e)
        self.setIncline(self.defaultInclineDeg)
        self.stopBelts()
        self.lastMotionState = "stopped"

    def readMetrics(self):
        """
        Current belt speed (m/s) and integrated distance (km) since last odometer reset.
        `prepareSession` resets the odometer so distance is per session when connected at START.
        """
        if not self.isConnected:
            return None, None
        try:
            return float(self.bt.speed), float(self.bt.distance)
        except Exception as e:
            print("TreadmillHardware: readMetrics failed:", e)
            return None, None

    def applyRoundOutcome(self, humanWon):
        """
        Hook after each auction round.
        Replace speeds / policy anytime — keep this single call site from `ExperimentController`.
        """
        if not self.enabled or not self.isConnected:
            if self.enabled and not self.isConnected:
                print("TreadmillHardware: enabled but not connected (no commands sent).")
            return
        currentlyWalking = self.isWalking()
        print(f"TreadmillHardware: applyRoundOutcome(humanWon={humanWon}) currentlyWalking={currentlyWalking}")

        # Win: keep walking for another 2 minutes -> if already walking, do nothing.
        if humanWon:
            if currentlyWalking:
                return
            self.startBelts()
            return

        # Loss: stop -> if already stopped, do nothing.
        if not currentlyWalking:
            return
        self.stopBelts()


def runTerminalDemo():
    """Original interactive CLI flow (blocking); not used by the GUI."""
    treadmill = TreadmillHardware(enabled=True)
    treadmill.connect()
    if not treadmill.isConnected:
        print("Demo aborted (no Bertec connection).")
        return

    TARGET_INCLINE = treadmill.defaultInclineDeg
    try:
        print(f"--- Setting incline to {TARGET_INCLINE}° (belts stopped) ---")
        treadmill.setIncline(TARGET_INCLINE)

        print("Waiting for treadmill to reach target incline...")
        while abs(treadmill.bt.incline - TARGET_INCLINE) > 0.1:
            print(f"Current incline: {treadmill.bt.incline:.2f}°", end="\r")
            time.sleep(0.5)
        print(f"\nTarget incline reached ({TARGET_INCLINE}°).")

        print("\n--- STANDBY ---")
        input("Press ENTER when the participant is ready to start the belts...")

        print(f"Starting belts at {treadmill.walkSpeedMs} m/s...")
        treadmill.startBelts()

        print("Belts are running. Press Ctrl+C to stop the session.")
        while True:
            time.sleep(1)
            print(
                f"Speed: {treadmill.bt.speed:.2f} m/s | Dist: {treadmill.bt.distance:.3f} km",
                end="\r",
            )

    except KeyboardInterrupt:
        print("\n\nStopping belts (incline unchanged)...")
        treadmill.stopBelts()
        time.sleep(2)

    finally:
        treadmill.disconnect()


if __name__ == "__main__":
    runTerminalDemo()
