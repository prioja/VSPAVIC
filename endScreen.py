from pathlib import Path

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen


class EndScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        root = BoxLayout(orientation="vertical", spacing=30, padding=150)

        title = Label(
            text="GAME OVER",
            font_size=120,
            bold=True,
            size_hint=(1, 0.18),
            halign="center",
            valign="middle",
        )
        title.bind(size=title.setter("text_size"))

        thanks = Label(
            text="Thank you for playing!",
            font_size=60,
            bold=True,
            size_hint=(1, 0.12),
            halign="center",
            valign="middle",
        )
        thanks.bind(size=thanks.setter("text_size"))

        baseDir = Path(__file__).resolve().parent
        logo = Image(source=str(baseDir / "figs" / "logo.png"), size_hint=(1, 0.45), allow_stretch=True, keep_ratio=True)

        self.totalLabel = Label(
            text="Total Payout: $0.00",
            font_size=110,
            bold=True,
            size_hint=(1, 0.25),
            halign="center",
            valign="middle",
        )
        self.totalLabel.bind(size=self.totalLabel.setter("text_size"))

        root.add_widget(title)
        root.add_widget(thanks)
        root.add_widget(logo)
        root.add_widget(self.totalLabel)

        self.add_widget(root)
        self.bind(on_pre_enter=self.refresh)

    def refresh(self, *_):
        app = App.get_running_app()
        st = getattr(app, "state", None)
        total = 0.0 if st is None else float(getattr(st, "totalPayout", 0.0) or 0.0)
        self.totalLabel.text = f"Total Payout: ${total:.2f}"