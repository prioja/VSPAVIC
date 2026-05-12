"""
Start screen UI (participant info entry).

"""

from datetime import datetime

from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.spinner import SpinnerOption
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle

from researchLink import SESSION_START_RESEARCHER_REMINDERS, sendMonitorEvent
from auctionCsv import write_hr_session_sidecar


class BigOption(SpinnerOption):  # Spinner menu text
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_size = 42
        self.bold = True


class RoundedButton(Button):  # Rounded yellow button
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)

        with self.canvas.before:
            Color(0.965, 0.784, 0.208, 1)
            self.rect = RoundedRectangle(radius=[15], pos=self.pos, size=self.size)

        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class StartLayout(BoxLayout):
    def __init__(self, onStart, **kwargs):
        super().__init__(orientation="vertical", spacing=50, padding=200, **kwargs)
        self._onStart = onStart
        
        # --- Image ---
        self.add_widget(Image(source='figs/welcome.png', size_hint=(1, 0.75), pos_hint={"center_x": 0.5}))

        # --- Subject ID ---
        subject_layout = BoxLayout(size_hint=(.6, 0.1),pos_hint={"center_x": 0.5})
        subject_layout.add_widget(Label(text="Subject ID: \n(e.g. 001)", bold=True, font_size=60, size_hint=(0.4, 1)))

        # Avoid hard-depending on a local font file; Kivy default font works fine.
        self.subjectInput = TextInput(multiline=False, font_size=60, size_hint=(0.6, 1))
        subject_layout.add_widget(self.subjectInput)
        self.add_widget(subject_layout)

        # --- Trial Condition ---
        trial_type_layout = BoxLayout(size_hint=(0.6, 0.1),pos_hint={"center_x": 0.5})
        trial_type_layout.add_widget(Label(text="Trial Condition:", bold=True,font_size=60, size_hint=(0.4, 1)))

        self.trialTypeSpinner = Spinner(text="Select Condition", font_size=58, bold = True,values=["TH ~ Take Home", "PF ~ Proflex", "VS ~ VSPA"], size_hint=(0.6, 1),option_cls=BigOption)
        trial_type_layout.add_widget(self.trialTypeSpinner)
        self.add_widget(trial_type_layout)

        # --- Trial Number ---
        trial_num_layout = BoxLayout(size_hint=(0.6, 0.1), pos_hint={"center_x": 0.5})
        trial_num_layout.add_widget(Label(text="Trial Number:", font_size=60, bold = True, size_hint=(0.4, 1)))

        self.trialNumSpinner = Spinner(text="Select Trial", size_hint=(0.6, 1), bold = True, font_size=58, values=["1", "2"], option_cls=BigOption)
        trial_num_layout.add_widget(self.trialNumSpinner)
        self.add_widget(trial_num_layout)

        # --- BEGIN BUTTON (ROUNDED) ---
        self.beginBtn = RoundedButton(
            text="START",
            size_hint=(0.15, 0.15),
            pos_hint={"center_x": 0.5},
            disabled=True,
            font_size=80,
            bold=True,
            color=(0, 0, 0, 1),
        )
        self.beginBtn.bind(on_press=lambda *_: self._onStart())
        self.add_widget(self.beginBtn)

        # --- VALIDATION ---
        self.subjectInput.bind(text=lambda *args: self.checkValid())
        self.trialTypeSpinner.bind(text=lambda *args: self.checkValid())
        self.trialNumSpinner.bind(text=lambda *args: self.checkValid())

    # --- VALIDATION ---
    def checkValid(self):
        subjectId = self.subjectInput.text.strip()
        trialType = self.trialTypeSpinner.text
        trialNum = self.trialNumSpinner.text

        is_valid = (
            subjectId != "" and
            trialType != "Select Condition" and
            trialNum != "Select Trial"
        )

        self.beginBtn.disabled = not is_valid
        self.beginBtn.opacity = 1 if is_valid else 0.4

class StartScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = StartLayout(onStart=self.onStartPressed)
        self.add_widget(self.layout)

    def onStartPressed(self):
        subjectId = self.layout.subjectInput.text.strip()
        trialCond = self.layout.trialTypeSpinner.text
        trialNum = self.layout.trialNumSpinner.text

        # Store values on shared state (created in main.py).
        app = App.get_running_app()
        if hasattr(app, "state"):
            app.state.subjectId = subjectId
            app.state.trialCond = trialCond
            app.state.trialNum = trialNum
            app.state.sessionStartTimestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        if hasattr(app, "controller"):
            app.controller.markFirstRoundInstant()

        # Notify researcher + log to events CSV once the session metadata exists.
        st = getattr(app, "state", None)
        cfg = app.controller.getSessionConfigSnapshot() if hasattr(app, "controller") else {}
        # Only include Preferred Stiffness for VSPA sessions.
        try:
            isVspa = bool(trialCond.strip().startswith("VS"))
        except Exception:
            isVspa = False
        if not isVspa:
            if isinstance(cfg, dict):
                cfg = dict(cfg)
                cfg.pop("preferredStiffnessNPerMm", None)
        stiffness_for_monitor = (
            getattr(st, "preferredStiffnessNPerMm", "") if isVspa else "N/A"
        )
        session_payload = {
            "label": "SESSION STARTED",
            "message": "Participant pressed START",
            "subjectId": getattr(st, "subjectId", None) if st else None,
            "trialCond": getattr(st, "trialCond", None) if st else None,
            "trialNum": getattr(st, "trialNum", None) if st else None,
            "sessionStartTimestamp": getattr(st, "sessionStartTimestamp", None) if st else None,
            "totalAuctionSeconds": getattr(st, "totalAuctionSeconds", None) if st else None,
            "totalAuctionMinutes": (float(getattr(st, "totalAuctionSeconds", 0.0) or 0.0) / 60.0) if getattr(st, "totalAuctionSeconds", None) is not None else None,
            "totalRounds": getattr(st, "totalRounds", None) if st else None,
            "researcherReminders": list(SESSION_START_RESEARCHER_REMINDERS),
            "config": cfg,
        }
        # Researcher-provided session settings (entered on researcher machine at app launch)
        if st is not None:
            session_payload["treadmillSpeedSetting"] = getattr(st, "treadmillSpeedSetting", "")
            session_payload["heartRateBaselineSetting"] = getattr(st, "heartRateBaselineSetting", "")
            session_payload["preferredStiffnessNPerMm"] = stiffness_for_monitor
            try:
                hr_sidecar = write_hr_session_sidecar(st)
                print("HR session sidecar for Polar script:", hr_sidecar)
            except Exception as e:
                print("write_hr_session_sidecar failed:", e)
        sendMonitorEvent("session_started", session_payload)
        logger = getattr(app, "auctionCsv", None)
        if logger is not None and st is not None:
            logger.appendUiEvent(st, "session_started", session_payload)

        hardware = getattr(app, "hardware", None)
        if hardware is not None and getattr(hardware, "enabled", False):
            hardware.prepareSession()

        print("=== STARTING EXPERIMENT ===")
        print("Subject ID:", subjectId)
        print("Trial Condition:", trialCond)
        print("Trial Number:", trialNum)

        # If/when you add the bid screen, this will take you there.
        root = App.get_running_app().root
        if hasattr(root, "has_screen") and root.has_screen("bid"):
            root.current = "bid"