from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.config import Config


class CounterApp(App):
    def build(self):

        # -------------------------
        # FULLSCREEN MODE
        # -------------------------
        Config.set('graphics', 'fullscreen', 'auto')

        self.cents = 0

        # hold state
        self.hold_event = None
        self.step = 1
        self.direction = None

        # -------------------------
        # LAYOUT
        # -------------------------
        layout = BoxLayout(
            orientation='vertical',
            padding=50,
            spacing=50
        )

        # -------------------------
        # BIG DISPLAY
        # -------------------------
        self.label = Label(
            text=self.format_money(),
            font_size=300
        )
        layout.add_widget(self.label)

        # -------------------------
        # BUTTON ROW
        # -------------------------
        button_row = BoxLayout(
            spacing=120,
            size_hint=(1, 0.4)
        )

        minus_btn = Button(
            text="-",
            font_size=140
        )

        plus_btn = Button(
            text="+",
            font_size=140
        )

        # Bind touch events
        plus_btn.bind(on_press=self.plus_press, on_release=self.stop_hold)
        minus_btn.bind(on_press=self.minus_press, on_release=self.stop_hold)

        button_row.add_widget(minus_btn)
        button_row.add_widget(plus_btn)

        layout.add_widget(button_row)

        return layout

    # -------------------------
    # FORMAT MONEY
    # -------------------------
    def format_money(self):
        dollars = self.cents // 100
        cents = self.cents % 100
        return f"${dollars}.{cents:02d}"

    def update_display(self):
        self.label.text = self.format_money()

    # -------------------------
    # HOLD LOGIC (ACCELERATING)
    # -------------------------
    def start_hold(self, direction):
        self.direction = direction
        self.step = 1

        # run every 0.08s (~12.5x per second)
        self.hold_event = Clock.schedule_interval(self.hold_update, 0.08)

    def hold_update(self, dt):
        if self.direction == "up":
            self.cents += self.step
        else:
            self.cents = max(0, self.cents - self.step)

        # accelerate over time
        self.step = min(self.step + 1, 50)

        self.update_display()

    def stop_hold(self, instance):
        # stop repeating hold
        if self.hold_event:
            self.hold_event.cancel()
            self.hold_event = None

        # treat every interaction as at least 1 cent change on release
        if self.direction == "up":
            self.cents += 1
        elif self.direction == "down":
            self.cents = max(0, self.cents - 1)

        self.update_display()

        self.direction = None

    # -------------------------
    # BUTTON EVENTS
    # -------------------------
    def plus_press(self, instance):
        self.start_hold("up")

    def minus_press(self, instance):
        self.start_hold("down")


if __name__ == "__main__":
    CounterApp().run()