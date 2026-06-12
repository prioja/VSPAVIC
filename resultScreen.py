"""
Round outcome screen: logo + GIF + bid summary.
Uses the same Label sizing pattern as endScreen.py (size_hint + text_size bind).
"""

from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from gifWidget import PillowGifImage

DETAIL_SUMMARY_FONT_SIZE = 100


def _centered_label(**kwargs):
    lbl = Label(halign="center", valign="middle", bold=True, **kwargs)
    lbl.bind(size=lbl.setter("text_size"))
    return lbl


class ResultScreen(Screen):
    dismissAfterSeconds = 20.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.dismissEvent = None
        self.treadmillLeadEvent = None
        self._layout = FloatLayout()
        self.add_widget(self._layout)

        content = BoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            padding=[40, 60, 50, 40],
            spacing=0,
        )

        self.logoImage = Image(
            source="",
            size_hint=(1, 0.4),
            pos_hint={"center_y": 1},
            allow_stretch=True,
            keep_ratio=True,
        )

        self.actionGif = PillowGifImage(
            fps=12.0,
            source="",
            size_hint=(1, 0.5)
        )

        self.detailLabel = _centered_label(
            text="",
            font_size=DETAIL_SUMMARY_FONT_SIZE,
            size_hint=(1, 0.1),
        )

        content.add_widget(self.logoImage)
        content.add_widget(self.actionGif)
        content.add_widget(self.detailLabel)

        self._layout.add_widget(content)

        self.bind(on_pre_enter=self.refresh)

    def _apply_font_sizes(self):
        self.detailLabel.font_size = DETAIL_SUMMARY_FONT_SIZE

    def on_leave(self, *_):
        self.cancelDismiss()
        self.cancelTreadmillLead()
        self.actionGif.stop()

    def refresh(self, *_):
        baseDir = Path(__file__).resolve().parent
        figsDir = baseDir / "figs"

        app = App.get_running_app()
        ctrl = getattr(app, "controller", None)
        if ctrl is not None:
            self.dismissAfterSeconds = float(
                getattr(ctrl, "resultScreenSeconds", self.dismissAfterSeconds) or 20.0
            )

        print(
            "[ResultScreen]",
            str(Path(__file__).resolve()),
            f"DETAIL={DETAIL_SUMMARY_FONT_SIZE}",
        )

        self._apply_font_sizes()

        result = getattr(getattr(app, "state", None), "lastResult", None)
        humanWon = bool(result.get("humanWon")) if isinstance(result, dict) else False

        if humanWon:
            self.logoImage.source = str(figsDir / "won_logo.png")
            self.actionGif.opacity = 1
            self.actionGif.start(str(figsDir / "walking.gif"))
        else:
            self.logoImage.source = str(figsDir / "lost_logo.png")
            sittingGif = figsDir / "sitting.gif"
            if sittingGif.exists():
                self.actionGif.opacity = 1
                self.actionGif.start(str(sittingGif))
            else:
                self.actionGif.stop()
                self.actionGif.opacity = 0

        if isinstance(result, dict):
            lowest = result.get("lowestBid", None)
            if lowest is None:
                self.detailLabel.text = "Winning Bid: N/A"
            else:
                self.detailLabel.text = f"Winning Bid: ${float(lowest):.2f}"
        else:
            self.detailLabel.text = ""

        Clock.schedule_once(lambda *_: self._apply_font_sizes(), 0)

        self.scheduleDismiss()
        self.scheduleTreadmillLead()

    def cancelTreadmillLead(self, *_):
        if self.treadmillLeadEvent is None:
            return
        self.treadmillLeadEvent.cancel()
        self.treadmillLeadEvent = None

    def scheduleTreadmillLead(self):
        """Start/stop Bertec during the last N seconds on this screen."""
        self.cancelTreadmillLead()
        app = App.get_running_app()
        ctrl = getattr(app, "controller", None)
        if ctrl is None:
            return
        lead = float(getattr(ctrl, "resultScreenBeltLeadSeconds", 10.0) or 10.0)
        delay = max(0.0, float(self.dismissAfterSeconds) - lead)
        self.treadmillLeadEvent = Clock.schedule_once(
            lambda *_: self._applyTreadmillLead(),
            delay,
        )

    def _applyTreadmillLead(self):
        self.treadmillLeadEvent = None
        app = App.get_running_app()
        ctrl = getattr(app, "controller", None)
        if ctrl is not None:
            ctrl.applyTreadmillOutcomeForLastResult()

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

        if hasattr(root, "has_screen") and root.has_screen("bid"):
            ctrl = getattr(app, "controller", None)
            if ctrl is not None and st is not None:
                # All auctions done — show one last 2-min walk on the bid screen, then end.
                if totalRounds is not None and totalRounds > 0 and not ctrl.hasMoreAuctions():
                    st.sessionClosingWalk = True
                else:
                    st.sessionClosingWalk = False
                ctrl.onReturningToBidAfterResult()
            root.current = "bid"
