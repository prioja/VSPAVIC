"""
Round outcome screen: different layouts for win vs lose.
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

        root = BoxLayout(orientation="vertical", padding=40, spacing=20)

        # Visual feedback (logo + animated gif)
        self.logoImage = Image(source="", size_hint=(1, 0.55), allow_stretch=True, keep_ratio=True)
        # Pillow-driven GIF (avoids Kivy/SDL GIF loader issues on some builds).
        self.actionGif = PillowGifImage(fps=12.0, source="", size_hint=(1, 0.35))

        self.winTitle = Label(text="You won this round.", font_size=56, bold=True, size_hint=(1, 0.12))
        self.winBody = Label(
            text="Please keep walking (per protocol).",
            font_size=44,
            size_hint=(1, 0.12),
        )

        self.loseTitle = Label(
            text="You did not win this round.",
            font_size=56,
            bold=True,
            size_hint=(1, 0.12),
        )
        self.loseBody = Label(
            text="Please sit/rest (per protocol).",
            font_size=44,
            size_hint=(1, 0.12),
        )

        self.stack = BoxLayout(orientation="vertical", spacing=10, size_hint=(1, 0.35))
        self.stack.add_widget(self.winTitle)
        self.stack.add_widget(self.winBody)
        self.stack.add_widget(self.loseTitle)
        self.stack.add_widget(self.loseBody)

        self.detailLabel = Label(
            text="",
            font_size=36,
            bold=True,
            halign="center",
            valign="middle",
            size_hint=(1, 0.35),
        )
        self.detailLabel.bind(size=self.detailLabel.setter("text_size"))

        self.hintLabel = Label(
            text="",
            font_size=36,
            bold=True,
            size_hint=(1, 0.1),
        )
        self.hintLabel.opacity = 0

        root.add_widget(self.logoImage)
        root.add_widget(self.actionGif)
        root.add_widget(self.stack)
        root.add_widget(self.detailLabel)
        root.add_widget(self.hintLabel)
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
            self.logoImage.source = str(figsDir / "won_logo.png")
            self.actionGif.opacity = 1
            self.actionGif.start(str(figsDir / "walking.gif"))
            # won_logo already communicates win/walk — hide redundant labels
            self.winTitle.opacity = 0
            self.winBody.opacity = 0
            self.loseTitle.opacity = 0
            self.loseBody.opacity = 0
            self.stack.opacity = 0
            self.stack.size_hint_y = 0.001
        else:
            self.logoImage.source = str(figsDir / "lost_logo.png")
            self.actionGif.stop()
            self.actionGif.opacity = 0
            self.winTitle.opacity = 0
            self.winBody.opacity = 0
            if humanParticipated:
                self.loseTitle.text = "You did not win this round."
                self.loseBody.text = "Please sit/rest (per protocol)."
            else:
                self.loseTitle.text = "No bid was submitted before time expired."
                self.loseBody.text = "Please sit/rest (per protocol)."
            self.loseTitle.opacity = 1
            self.loseBody.opacity = 1
            self.stack.opacity = 1
            self.stack.size_hint_y = 0.35

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
                f"Payout (2nd lowest): ${payout:.2f}\n"
                f"Total winnings: ${total:.2f}"
            )
        else:
            self.detailLabel.text = ""

        # Intentionally hide any countdown text; the screen auto-dismisses silently.
        self.hintLabel.text = ""
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

        # roundIndex starts at -1 and increments on finalizeRound(), so after N rounds
        # it will be N-1. Navigate to End when last round has been finalized.
        if totalRounds is not None and totalRounds > 0 and st is not None and st.roundIndex >= (totalRounds - 1):
            if hasattr(root, "has_screen") and root.has_screen("end"):
                root.current = "end"
            return

        if hasattr(root, "has_screen") and root.has_screen("bid"):
            root.current = "bid"
