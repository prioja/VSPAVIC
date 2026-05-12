"""
Round outcome screen: logo + GIF + optional no-bid message + bid/payout summary.
Reads `app.state.lastResult` on each visit.
"""

from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from gifWidget import PillowGifImage


class ResultScreen(Screen):
    # How long the outcome stays visible before returning to bidding.
    dismissAfterSeconds = 20.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.dismissEvent = None

        root = BoxLayout(
            orientation="vertical",
            padding=[40, 200, 40, 40],
            spacing=20,
        )

        self.logoImage = Image(source="", size_hint=(1, 0.48), allow_stretch=True, keep_ratio=True)
        self.actionGif = PillowGifImage(fps=12.0, source="", size_hint=(1, 0.52))

        # Only used when the participant did not bid before the buzzer (see refresh).
        self.loseTitle = Label(
            text="No bid was submitted before time expired.",
            font_size=68,
            bold=True,
            size_hint=(1, 0.12),
            halign="center",
            valign="middle",
        )
        self.loseTitle.bind(size=self.loseTitle.setter("text_size"))

        self.messageStack = BoxLayout(orientation="vertical", spacing=10, size_hint=(1, 0.35))
        self.messageStack.add_widget(self.loseTitle)

        self.detailLabel = Label(
            text="",
            font_size=54,
            bold=True,
            halign="center",
            valign="middle",
            size_hint=(1, 0.42),
        )
        self.detailLabel.bind(size=self.detailLabel.setter("text_size"))

        root.add_widget(self.logoImage)
        root.add_widget(self.actionGif)
        root.add_widget(self.messageStack)
        root.add_widget(self.detailLabel)
        self.add_widget(root)

        self.bind(on_pre_enter=self.refresh)

    def on_leave(self, *_):
        self.cancelDismiss()
        self.actionGif.stop()

    def refresh(self, *_):
        baseDir = Path(__file__).resolve().parent
        figsDir = baseDir / "figs"

        app = App.get_running_app()
        result = getattr(getattr(app, "state", None), "lastResult", None)
        humanWon = bool(result.get("humanWon")) if isinstance(result, dict) else False
        humanParticipated = bool(result.get("humanParticipated", True)) if isinstance(result, dict) else True

        if humanWon:
            self.logoImage.size_hint_y = 0.48
            self.actionGif.size_hint_y = 0.52
            self.logoImage.source = str(figsDir / "won_logo.png")
            self.actionGif.opacity = 1
            self.actionGif.start(str(figsDir / "walking.gif"))
            self.loseTitle.opacity = 0
            self.messageStack.opacity = 0
            self.messageStack.size_hint_y = 0.001
        else:
            self.logoImage.source = str(figsDir / "lost_logo.png")
            sittingGif = figsDir / "sitting.gif"
            if sittingGif.exists():
                self.actionGif.opacity = 1
                self.actionGif.start(str(sittingGif))
            else:
                self.actionGif.stop()
                self.actionGif.opacity = 0

            if humanParticipated:
                self.loseTitle.opacity = 0
                self.messageStack.opacity = 0
                self.messageStack.size_hint_y = 0.001
                self.logoImage.size_hint_y = 0.36
                self.actionGif.size_hint_y = 0.64
            else:
                self.loseTitle.text = "No bid was submitted before time expired."
                self.loseTitle.opacity = 1
                self.messageStack.opacity = 1
                self.messageStack.size_hint_y = 0.12
                self.logoImage.size_hint_y = 0.32
                self.actionGif.size_hint_y = 0.56

        if isinstance(result, dict):
            hb = result.get("humanBid", None)
            payout = float(result.get("payout", 0.0))
            lowest = float(result.get("lowestBid", 0.0))
            total = float(result.get("totalPayout", 0.0))
            if hb is None:
                bidLine = "Your bid: (none)"
            else:
                bidLine = f"Your bid: ${float(hb):.2f}"
            self.detailLabel.text = (
                f"{bidLine}  |  Lowest bid: ${lowest:.2f}  |  "
                f"Payout: ${payout:.2f}\n\n"
                f"Total winnings: ${total:.2f}"
            )
        else:
            self.detailLabel.text = ""

        self.scheduleDismiss()

    def cancelDismiss(self, *_):
        if self.dismissEvent is None:
            return
        self.dismissEvent.cancel()
        self.dismissEvent = None

    def scheduleDismiss(self):
        self.cancelDismiss()
        self.dismissEvent = Clock.schedule_once(
            lambda *_: self.goToBid(),
            self.dismissAfterSeconds,
        )

    def goToBid(self):
        self.cancelDismiss()
        app = App.get_running_app()
        st = getattr(app, "state", None)
        root = getattr(app, "root", None)
        if root is None:
            return

        totalRounds = None if st is None else getattr(st, "totalRounds", None)
        try:
            totalRounds = int(totalRounds) if totalRounds is not None else None
        except Exception:
            totalRounds = None

        if totalRounds is not None and totalRounds > 0 and st is not None and st.roundIndex >= (totalRounds - 1):
            if hasattr(root, "has_screen") and root.has_screen("end"):
                root.current = "end"
            return

        if hasattr(root, "has_screen") and root.has_screen("bid"):
            root.current = "bid"
