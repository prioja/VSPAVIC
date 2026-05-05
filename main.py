from kivy.config import Config
Config.set("graphics", "fullscreen", "auto")

import os
import signal

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager

from auctionCsv import AuctionCsvLogger
from experimentController import ExperimentController
from hardware import TreadmillHardware
from state import State
from startScreen import StartScreen
from bidScreen import BidScreen
from resultScreen import ResultScreen
from endScreen import EndScreen

class VSPAVicApp(App):
    
    def build(self):
        self.title = "VSPAVIC Experiment"

        # Make Ctrl+C / SIGTERM stop the app cleanly (disconnect treadmill, etc.)
        def _handleSignal(*_args):
            try:
                App.get_running_app().stop()
            except Exception:
                pass

        try:
            signal.signal(signal.SIGINT, _handleSignal)
            signal.signal(signal.SIGTERM, _handleSignal)
        except Exception:
            # Some environments may disallow signal handlers; safe to ignore.
            pass

        self.state = State()
        # Total number of rounds in this session. After this many finalized rounds,
        # the app will navigate to the End screen instead of returning to bidding.
        # Set before launch: export VSPA_TOTAL_ROUNDS=10
        try:
            self.state.totalRounds = int(os.environ.get("VSPA_TOTAL_ROUNDS", "10"))
        except Exception:
            self.state.totalRounds = 10
        # Enable treadmill control by default for the experiment.
        # (Previously required setting VSPA_TREADMILL=1.)
        self.hardware = TreadmillHardware(enabled=True)
        self.auctionCsv = AuctionCsvLogger()
        self.controller = ExperimentController(
            self.state,
            hardware=self.hardware,
            csvLogger=self.auctionCsv,
        )

        sm = ScreenManager()

        sm.add_widget(StartScreen(name="start"))
        sm.add_widget(BidScreen(name="bid"))
        sm.add_widget(ResultScreen(name="result"))
        sm.add_widget(EndScreen(name="end"))

        sm.current = "start"
        return sm

    def on_stop(self):
        hw = getattr(self, "hardware", None)
        if hw is not None:
            hw.disconnect()

if __name__ == "__main__":
    VSPAVicApp().run()
        