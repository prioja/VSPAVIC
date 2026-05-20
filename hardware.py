"""
Treadmill control for the Bertec over TCP (via `BertecMan.Bertec`).

- Use `TreadmillHardware` from the Kivy app: quick commands only (no blocking loops).
- Run this file directly for a terminal smoke test: `python hardware.py`
"""

import os
import threading
import time

from BertecMan import Bertec


class TreadmillHardware:
    """Thin wrapper around `Bertec` with experiment-friendly helpers."""

    def __init__(
        self,
        viconPcIp=None,
        enabled=None,
        walkSpeedMs=None,
        walkAccelMs2=0.1,
        stopAccelMs2=0.1,
        defaultInclineDeg=0.0,
    ):
        self.viconPcIp = viconPcIp or os.environ.get("VSPA_BERTEC_IP", "141.212.77.30")
        if enabled is None:
            enabled = os.environ.get("VSPA_TREADMILL", "").strip().lower() in ("1", "true", "yes")
        self.enabled = bool(enabled)

        if walkSpeedMs is None:
            raw = os.environ.get("VSPA_WALK_SPEED_MS", "1.0").strip()
            try:
                walkSpeedMs = float(raw)
            except Exception:
                walkSpeedMs = 1.0
        self.walkSpeedMs = max(0.0, float(walkSpeedMs))
        self.walkAccelMs2 = walkAccelMs2
        self.stopAccelMs2 = stopAccelMs2
        self.defaultInclineDeg = defaultInclineDeg

        self.bt = None
        self.lastConnectError = None
        # Cache of our last intended motion state to avoid spamming commands.
        # Possible values: "walking", "stopped", None (unknown).
        self.lastMotionState = None
        self.walkingSpeedThresholdMs = 0.05
        self._connect_lock = threading.Lock()

    @property
    def isConnected(self):
        return self.bt is not None

    def ensure_connected(self, retries=2):
        """Connect if needed (safe to call before belt commands)."""
        if not self.enabled:
            return False
        if self.isConnected:
            return True
        with self._connect_lock:
            if self.isConnected:
                return True
            for attempt in range(max(1, int(retries))):
                self.connect()
                if self.isConnected:
                    return True
                if attempt + 1 < retries:
                    time.sleep(0.5)
        return self.isConnected

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
        if not self.ensure_connected():
            return
        self.bt.write_command(speedR=0.0, speedL=0.0, incline=float(inclineDeg))

    def stopBelts(self):
        if not self.ensure_connected():
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
        if not self.ensure_connected():
            print("TreadmillHardware: startBelts skipped (not connected to Bertec).")
            return False
        sp = float(self.walkSpeedMs if speedMs is None else speedMs)
        if sp <= 0.0:
            print(
                "TreadmillHardware: startBelts skipped (walkSpeedMs is 0). "
                "Set treadmill speed on the researcher config or VSPA_WALK_SPEED_MS."
            )
            return False
        ac = float(self.walkAccelMs2 if accelMs2 is None else accelMs2)
        print(f"TreadmillHardware: COMMAND startBelts(speed={sp}, accel={ac})")
        try:
            self.bt.write_command(speedR=sp, speedL=sp, accR=ac, accL=ac)
        except Exception as e:
            print("TreadmillHardware: startBelts write_command failed:", e)
            return False
        self.lastMotionState = "walking"
        return True

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
        """Belts stopped, incline set to default. Runs on a worker thread from the GUI."""
        if not self.enabled:
            return
        if not self.ensure_connected(retries=3):
            print("TreadmillHardware: prepareSession aborted (no Bertec connection).")
            return
        if self.isConnected:
            try:
                self.bt.reset_odometer()
            except Exception as e:
                print("TreadmillHardware: reset_odometer failed:", e)
        self.setIncline(self.defaultInclineDeg)
        self.stopBelts()
        self.lastMotionState = "stopped"

    def prepareSession_async(self):
        """Non-blocking version for START — avoids freezing if Bertec is unreachable."""
        if not self.enabled:
            return

        def _run():
            try:
                self.prepareSession()
            except Exception as e:
                print("TreadmillHardware: prepareSession_async failed:", e)

        threading.Thread(target=_run, daemon=True).start()

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
        Hook after each auction round (after the result screen).
        Win -> start belts at walkSpeedMs; loss -> stop belts.
        """
        if not self.enabled:
            return
        if not self.ensure_connected(retries=3):
            print(
                "TreadmillHardware: applyRoundOutcome skipped — not connected to "
                f"{self.viconPcIp} (last error: {self.lastConnectError})."
            )
            return

        currentlyWalking = self.isWalking()
        print(
            f"TreadmillHardware: applyRoundOutcome(humanWon={humanWon}) "
            f"currentlyWalking={currentlyWalking} walkSpeedMs={self.walkSpeedMs}"
        )

        if humanWon:
            if currentlyWalking:
                return
            self.startBelts()
            return

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
