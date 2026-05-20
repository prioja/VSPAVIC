from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.uix.image import Image
from kivy.uix.label import Label


class PassthroughLabel(Label):
    """Overlay label that does not block touches to widgets below (e.g. timer over SUBMIT)."""

    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp

from researchLink import sendMonitorEvent
from roundedButton import RoundedButton


def _monitor_round_started_payload(st, controller=None):
    """1-based round # for researcher monitor (len(completed) + 1 for the round now starting)."""
    n = 1
    if st is not None:
        n = len(getattr(st, "results", []) or []) + 1
    out = {
        "label": f"ROUND {n} STARTED",
        "roundNumber": n,
        "roundIndex": getattr(st, "roundIndex", None) if st is not None else None,
        "roundStartTimestamp": getattr(st, "roundStartTimestamp", None) if st is not None else None,
        "robotBidsLocked": list(getattr(st, "robotBidsLocked", []) or []) if st is not None else [],
    }
    if controller is not None and hasattr(controller, "getSessionConfigSnapshot"):
        try:
            snap = controller.getSessionConfigSnapshot() or {}
            out["roboModel"] = snap.get("roboModel") or {}
        except Exception:
            out["roboModel"] = {}
    return out


class BidScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)

        self.cents = 0
        self.roundTicker = None
        self.hasActiveRound = False
        self._helpFlashEv = None
        self._helpFlashCount = 0
        self._lastRoundStartPerf = None

        layout1 = BoxLayout(orientation="horizontal", size_hint=(1,0.2))
        # size_hint_x alone can be a very narrow strip before layout settles; min width keeps
        # HELP/PAUSE readable and matches first paint vs later frames.
        _side_btn_kw = dict(
            size_hint=(0.12, 0.4),
            size_hint_min_x=dp(108),
            font_size=60,
            bold=True,
            disabled=False,
            background_normal="",
            pos_hint={"center_y": 0.7},
            color=(0, 0, 0, 1),
        )
        self.helpBtn = RoundedButton(text="HELP", bg=(0.86, 0.08, 0.2, 1), **_side_btn_kw)
        logo = Image(source="figs/logo.png", size_hint=(0.25, 0.6), pos_hint={"center_y": 0.7}) 
        self.pauseBtn = RoundedButton(text="PAUSE", bg=(0.965, 0.784, 0.208, 1), **_side_btn_kw)

        # FloatLayout so pos_hint actually moves widgets (BoxLayout ignores it).
        layout2 = FloatLayout(size_hint=(1, 0.8))
        self.timerLabel = PassthroughLabel(
            text="Round: --:--",
            font_size=90,
            bold=True,
            size_hint=(None, None),
            pos_hint={"x": 0.1, "y": 0.02},
        )
        self.timerLabel.opacity = 0
        self.display = Label(
            text=self.formatMoney(),
            font_size=330,
            size_hint=(1, 0.2),
            pos_hint={"center_x": 0.5, "center_y": 0.9},
        )
        self.keypadGrid = GridLayout(
            cols=3,
            spacing=10,
            size_hint=(0.45, 0.6),
            pos_hint={"center_x": 0.5, "center_y": 0.45},
        )
        self._keypadButtons = []
        buttons = [
            "1", "2", "3",
            "4", "5", "6",
            "7", "8", "9",
            "0", "DEL", "C"
        ]

        for b in buttons:
            btn = Button(text=b, font_size=90, bold=True)
            btn.bind(on_press=self.onButtonPress)
            self._keypadButtons.append(btn)
            self.keypadGrid.add_widget(btn)

        self.submitBtn = RoundedButton(
            text="SUBMIT",
            bg=(0.5, 0.5, 0.5, 1),
            size_hint=(0.22, 0.08),
            size_hint_min=(dp(160), dp(52)),
            pos_hint={"center_x": 0.5, "y": 0.03},
            font_size=60,
            bold=True,
            disabled=True,
            color=(1, 1, 1, 1),
        )
        self.submitBtn.bind(on_press=self.onSubmit)

        
# --------------------- build -------------------------
        body = BoxLayout(orientation="vertical", padding=30)
        layout1.add_widget(self.helpBtn)
        layout1.add_widget(logo)
        layout1.add_widget(self.pauseBtn)
        

        layout2.add_widget(self.keypadGrid)
        layout2.add_widget(self.display)
        layout2.add_widget(self.submitBtn)

        body.add_widget(layout1)
        body.add_widget(layout2)

        self.overlay = FloatLayout()
        self.overlay.add_widget(body)
        self.overlay.add_widget(self.timerLabel)

        self._buildHelpOverlay()
        # helpRoot is attached only while HELP is open (see showHelp/hideHelp) so a
        # full-screen layer cannot intercept touches when the overlay is "invisible".

        self.helpBtn.bind(on_press=self.onHelpPressed)
        self.pauseBtn.bind(on_press=self.onPausePressed)

        self.add_widget(self.overlay)

# --------------------- money formatting -------------------------
    def formatMoney(self):
        return f"${self.cents //100}.{self.cents % 100:02d}"

    def updateDisplay(self):
        self.display.text = self.formatMoney()

        if self.cents == 0:
            self.submitBtn.disabled = True
            self.submitBtn.set_bg((0.5, 0.5, 0.5, 1))
        else:
            self.submitBtn.disabled = False
            self.submitBtn.set_bg((0.2, 0.7, 0.2, 1))

    def _set_bid_inputs_enabled(self, enabled):
        can_bid = bool(enabled)
        self.submitBtn.disabled = not can_bid
        if can_bid:
            self.updateDisplay()
        else:
            self.submitBtn.set_bg((0.5, 0.5, 0.5, 1))
        for btn in self._keypadButtons:
            btn.disabled = not can_bid

    def onButtonPress(self, instance):# --------------------- keypad logic -------------------------
        if instance.disabled:
            return
        text = instance.text

        if text == "C":
            self.cents = 0
        elif text == "DEL":
            self.cents = self.cents // 10
        else:
            self.cents = self.cents * 10 + int(text)

        self.updateDisplay()

    def _complete_instant_submit(self, bid):
        app = App.get_running_app()
        st = getattr(app, "state", None)
        if not hasattr(app, "controller"):
            return
        app.controller.submitBidForCurrentRound(bid)
        self._emit_event(
            app,
            "bid_submitted",
            {
                "label": "BID SUBMITTED",
                "bid": bid,
                "phase": "instant_round",
                "roundIndex": getattr(st, "roundIndex", None) if st else None,
            },
        )
        result = app.controller.finalizeRound()
        print("Round finalized (instant first round):", result)
        self.resetKeypad()
        self.goToResult()

    def onSubmit(self, *_):
        app = App.get_running_app()
        st = getattr(app, "state", None)
        prev_round_start = None if st is None else getattr(st, "roundStartPerf", None)

        if hasattr(app, "controller") and app.controller.isWalkingPhase():
            return

        bid = self.cents / 100.0
        if hasattr(app, "controller"):
            # First round after START: one submit finalizes immediately.
            if st is not None and getattr(st, "pendingInstantRound", False):
                # Brief delay so press color is visible before leaving this screen.
                Clock.schedule_once(
                    lambda _dt, b=bid: self._complete_instant_submit(b),
                    0.1,
                )
                return

            # Timed rounds: Submit can be pressed multiple times; only the last one counts.
            app.controller.submitBidForCurrentRound(bid)
            self.hasActiveRound = True
            self.startTickerIfNeeded()
            self._emit_event(
                app,
                "bid_submitted",
                {
                    "label": "BID SUBMITTED",
                    "bid": bid,
                    "phase": "timed_round",
                    "roundIndex": getattr(st, "roundIndex", None),
                    "secondsRemaining": app.controller.getSecondsRemaining(),
                },
            )

            # If this submit started the round (i.e., first submit of the round),
            # robot bids are now locked; emit them once.
            new_round_start = None if st is None else getattr(st, "roundStartPerf", None)
            if prev_round_start is None and new_round_start is not None:
                self._emit_event(
                    app,
                    "round_started",
                    _monitor_round_started_payload(st, getattr(app, "controller", None)),
                )
            print("Submitted (latest) bid:", bid)
        else:
            print("Submitted bid:", bid)

    def resetKeypad(self):
        self.cents = 0
        self.updateDisplay()

    def goToResult(self):
        """Show results; rebuild ResultScreen so edits to resultScreen.py apply without restarting."""
        import importlib
        import resultScreen as result_screen_mod

        root = App.get_running_app().root
        if root is None or not hasattr(root, "has_screen"):
            return

        importlib.reload(result_screen_mod)
        if root.has_screen("result"):
            old = root.get_screen("result")
            if hasattr(old, "cancelDismiss"):
                old.cancelDismiss()
            if hasattr(old, "actionGif"):
                old.actionGif.stop()
            root.remove_widget(old)

        root.add_widget(result_screen_mod.ResultScreen(name="result"))
        root.current = "result"

    def startTickerIfNeeded(self):
        if self.roundTicker is not None:
            return
        self.roundTicker = Clock.schedule_interval(self.onTick, 0.1)

    def stopTicker(self):
        if self.roundTicker is None:
            return
        self.roundTicker.cancel()
        self.roundTicker = None

    def _buildHelpOverlay(self):
        self.helpRoot = FloatLayout(opacity=0, disabled=True)

        dimmer = Widget(size_hint=(1, 1))
        with dimmer.canvas.before:
            Color(0, 0, 0, 0.35)
            self.helpDimmerRect = Rectangle(pos=dimmer.pos, size=dimmer.size)
        dimmer.bind(
            pos=lambda *_: setattr(self.helpDimmerRect, "pos", dimmer.pos),
            size=lambda *_: setattr(self.helpDimmerRect, "size", dimmer.size),
        )

        def dimmer_touch(widget, touch):
            # touch.x/y are window coords; collide_point expects local coords.
            if not widget.collide_point(*widget.to_widget(touch.x, touch.y, relative=False)):
                return False
            if self.helpCard.collide_point(
                *self.helpCard.to_widget(touch.x, touch.y, relative=False)
            ):
                return False
            self.hideHelp()
            return True

        dimmer.bind(on_touch_down=dimmer_touch)

        self.helpCard = BoxLayout(
            orientation="vertical",
            padding=24,
            spacing=18,
            size_hint=(0.72, 0.38),
            pos_hint={"center_x": 0.5, "center_y": 0.55},
        )
        with self.helpCard.canvas.before:
            Color(1, 1, 1, 0.96)
            self.helpCardBg = RoundedRectangle(
                pos=self.helpCard.pos,
                size=self.helpCard.size,
                radius=[18],
            )
        with self.helpCard.canvas.after:
            self.helpFlashColor = Color(0.86, 0.08, 0.2, 0.0)
            self.helpFlashOverlay = RoundedRectangle(
                pos=self.helpCard.pos,
                size=self.helpCard.size,
                radius=[18],
            )
        self.helpCard.bind(
            pos=self._syncHelpCardGfx,
            size=self._syncHelpCardGfx,
        )

        title = Label(
            text="ALERT",
            font_size=44,
            bold=True,
            color=(0.1, 0.1, 0.1, 1),
            size_hint=(1, None),
            height=56,
        )
        body = Label(
            text="A researcher has been notified.\n\nPlease wait for assistance.\n\nTap outside this box or press OK to close.",
            font_size=30,
            color=(0.15, 0.15, 0.15, 1),
            valign="middle",
            halign="center",
            text_size=(None, None),
        )
        body.bind(size=lambda inst, s: setattr(inst, "text_size", (s[0] - 10, s[1])))

        ok = RoundedButton(text="OK", font_size=44, bold=True, bg=(0.2, 0.45, 0.85, 1), size_hint=(1, 0.22))
        ok.bind(on_press=lambda *_: self.hideHelp())

        self.helpCard.add_widget(title)
        self.helpCard.add_widget(body)
        self.helpCard.add_widget(ok)

        self.helpRoot.add_widget(dimmer)
        self.helpRoot.add_widget(self.helpCard)

    def _syncHelpCardGfx(self, *args):
        self.helpCardBg.pos = self.helpCard.pos
        self.helpCardBg.size = self.helpCard.size
        self.helpFlashOverlay.pos = self.helpCard.pos
        self.helpFlashOverlay.size = self.helpCard.size

    def _cancelHelpFlash(self):
        if self._helpFlashEv is not None:
            self._helpFlashEv.cancel()
            self._helpFlashEv = None
        self.helpFlashColor.a = 0.0

    def _pulse_help_flash(self, *_):
        self._helpFlashCount += 1
        self.helpFlashColor.a = 0.55 if (self._helpFlashCount % 2) else 0.0
        if self._helpFlashCount >= 8:
            self._cancelHelpFlash()

    def showHelp(self):
        if self.helpRoot.parent is None:
            self.overlay.add_widget(self.helpRoot)
        self.helpRoot.disabled = False
        self.helpRoot.opacity = 1
        self._helpFlashCount = 0
        self._cancelHelpFlash()
        self._helpFlashEv = Clock.schedule_interval(self._pulse_help_flash, 0.12)

    def hideHelp(self):
        self._cancelHelpFlash()
        self.helpRoot.opacity = 0
        self.helpRoot.disabled = True
        if self.helpRoot.parent is not None:
            self.helpRoot.parent.remove_widget(self.helpRoot)

    def _log_ui_event_csv(self, app, event, detail=None):
        logger = getattr(app, "auctionCsv", None)
        st = getattr(app, "state", None)
        if logger is None or st is None:
            return
        logger.appendUiEvent(st, event, detail)

    def _emit_event(self, app, event, detail=None):
        # 1) tablet -> researcher terminal (optional link)
        sendMonitorEvent(event, detail or {})
        # 2) local per-session events CSV
        self._log_ui_event_csv(app, event, detail or {})

    def onHelpPressed(self, *_):
        app = App.get_running_app()
        st = getattr(app, "state", None)
        payload = {}
        if st is not None:
            payload = {
                "label": "ALERT",
                "message": "Participant pressed HELP",
                "subjectId": getattr(st, "subjectId", None),
                "trialCond": getattr(st, "trialCond", None),
                "trialNum": getattr(st, "trialNum", None),
                "sessionStartTimestamp": getattr(st, "sessionStartTimestamp", None),
                "roundIndex": getattr(st, "roundIndex", None),
            }
        self._emit_event(app, "help_pressed", payload)
        self.showHelp()

    def onPausePressed(self, *_):
        app = App.get_running_app()
        if not hasattr(app, "controller"):
            return
        st = getattr(app, "state", None)
        if st is not None and getattr(st, "pendingInstantRound", False):
            return
        if app.controller.getSecondsRemaining() is None and not app.controller.isWalkingPhase():
            return

        was_paused = bool(getattr(st, "auctionPaused", False)) if st is not None else False
        if not app.controller.toggleAuctionPause():
            return
        self.updatePauseButton()
        now_paused = bool(getattr(st, "auctionPaused", False)) if st is not None else False
        secs_left = app.controller.getWalkingSecondsRemaining()
        if secs_left is None:
            secs_left = app.controller.getSecondsRemaining()
        pause_detail = {
            "label": "PAUSED EXPERIMENT" if now_paused else "RESUMED EXPERIMENT",
            "message": "Auction timer paused" if now_paused else "Auction timer resumed",
            "secondsRemaining": secs_left,
            "toggledFromPaused": was_paused,
        }
        self._emit_event(app, "auction_paused" if now_paused else "auction_resumed", pause_detail)

    def updatePauseButton(self):
        app = App.get_running_app()
        st = getattr(app, "state", None)
        # Keep PAUSE visually the same as HELP (never use Button.disabled — Kivy greys it).
        # When pausing is not available, onPausePressed is a no-op.
        self.pauseBtn.disabled = False
        if not hasattr(app, "controller") or st is None:
            self.pauseBtn.text = "PAUSE"
            return
        if getattr(st, "pendingInstantRound", False):
            self.pauseBtn.text = "PAUSE"
            return
        if not (
            (hasattr(app, "controller") and app.controller.isWalkingPhase())
            or app.controller.getSecondsRemaining() is not None
        ):
            self.pauseBtn.text = "PAUSE"
            return
        self.pauseBtn.text = "RESUME" if getattr(st, "auctionPaused", False) else "PAUSE"

    def onTick(self, *_):
        app = App.get_running_app()
        if not hasattr(app, "controller"):
            return
        st = getattr(app, "state", None)
        if st is not None and getattr(st, "pendingInstantRound", False):
            return

        ctrl = app.controller
        walking_remaining = ctrl.getWalkingSecondsRemaining()
        if walking_remaining is not None:
            self._set_bid_inputs_enabled(False)
            self.hasActiveRound = True
            self.timerLabel.opacity = 1
            mins = int(walking_remaining // 60)
            secs = int(walking_remaining % 60)
            if st is not None and getattr(st, "auctionPaused", False):
                self.timerLabel.text = f"Walk (paused): {mins:02d}:{secs:02d}"
            else:
                self.timerLabel.text = f"Walk: {mins:02d}:{secs:02d}"
            self.updatePauseButton()
            if walking_remaining <= 0.0 and not (
                st is not None and getattr(st, "auctionPaused", False)
            ):
                self.hasActiveRound = False
                ctrl.onWalkingPhaseEnded()
                self.hasActiveRound = True
                self._sync_bid_screen_phase(app)
            return

        remaining = ctrl.getSecondsRemaining()
        if remaining is None:
            self.timerLabel.text = "Round: --:--"
            self.timerLabel.opacity = 0
            self._set_bid_inputs_enabled(False)
            self.updatePauseButton()
            return

        self._set_bid_inputs_enabled(True)
        self.timerLabel.opacity = 1
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        if st is not None and getattr(st, "auctionPaused", False):
            self.timerLabel.text = f"Bid (paused): {mins:02d}:{secs:02d}"
        else:
            self.timerLabel.text = f"Place bid: {mins:02d}:{secs:02d}"
        self.updatePauseButton()

        if remaining <= 0.0 and self.hasActiveRound and not (
            st is not None and getattr(st, "auctionPaused", False)
        ):
            self.hasActiveRound = False
            self.stopTicker()
            self.timerLabel.opacity = 0
            self._set_bid_inputs_enabled(False)
            result = app.controller.finalizeRound()
            print("Round finalized:", result)
            self.resetKeypad()
            self.goToResult()

    def _sync_bid_screen_phase(self, app):
        st = getattr(app, "state", None)
        ctrl = getattr(app, "controller", None)
        if ctrl is None:
            return

        if st is not None and getattr(st, "pendingInstantRound", False):
            self._set_bid_inputs_enabled(True)
            self.timerLabel.opacity = 0
            self.updatePauseButton()
            return

        if ctrl.isWalkingPhase():
            self.hasActiveRound = True
            self.timerLabel.opacity = 1
            self._set_bid_inputs_enabled(False)
            self.startTickerIfNeeded()
        elif ctrl.getSecondsRemaining() is not None:
            started_now = (
                st is not None
                and getattr(st, "roundStartPerf", None) is not None
                and self._lastRoundStartPerf != getattr(st, "roundStartPerf", None)
            )
            if started_now:
                self._emit_event(
                    app,
                    "round_started",
                    _monitor_round_started_payload(st, ctrl),
                )
            self._lastRoundStartPerf = (
                None if st is None else getattr(st, "roundStartPerf", None)
            )
            self.hasActiveRound = True
            self.timerLabel.opacity = 1
            self._set_bid_inputs_enabled(True)
            self.startTickerIfNeeded()
        else:
            self._set_bid_inputs_enabled(False)
            self.timerLabel.opacity = 0

        self.updatePauseButton()

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        self.hideHelp()
        if hasattr(app, "controller"):
            app.controller.onBidScreenEntered()

        self.stopTicker()
        self.hasActiveRound = False
        self._sync_bid_screen_phase(app)
