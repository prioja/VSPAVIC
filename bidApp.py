from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.config import Config


class CounterApp(App):
    def build(self):

        Config.set('graphics', 'fullscreen', 'auto')

        self.cents = 0

        # state
        self.hold_event = None
        self.delay_event = None
        self.holding = False
        self.direction = None
        self.step = 1

        layout = BoxLayout(orientation='vertical', padding=50, spacing=50)

        self.label = Label(
            text=self.format_money(),
            font_size=240
        )
        layout.add_widget(self.label)

        button_row = BoxLayout(spacing=120, size_hint=(1, 0.4))

        minus_btn = Button(text="-", font_size=140)
        plus_btn = Button(text="+", font_size=140)

        plus_btn.bind(on_press=self.plus_press, on_release=self.release)
        minus_btn.bind(on_press=self.minus_press, on_release=self.release)

        button_row.add_widget(minus_btn)
        button_row.add_widget(plus_btn)
        layout.add_widget(button_row)

        return layout

    # -------------------------
    # DISPLAY
    # -------------------------
    def format_money(self):
        return f"${self.cents // 100}.{self.cents % 100:02d}"

    def update(self):
        self.label.text = self.format_money()

    # -------------------------
    # HOLD START (DELAYED)
    # -------------------------
    def plus_press(self, instance):
        self.direction = "up"
        self.start_delay()

    def minus_press(self, instance):
        self.direction = "down"
        self.start_delay()

    def start_delay(self):
        # wait before starting hold (detect tap vs hold)
        self.delay_event = Clock.schedule_once(self.start_hold, 0.25)

    def start_hold(self, dt):
        self.holding = True
        self.step = 1
        self.hold_event = Clock.schedule_interval(self.hold_update, 0.08)

    # -------------------------
    # HOLD UPDATE
    # -------------------------
    def hold_update(self, dt):
        if self.direction == "up":
            self.cents += self.step
        else:
            self.cents = max(0, self.cents - self.step)

        self.step = min(self.step + 1, 50)
        self.update()

    # -------------------------
    # RELEASE (CLEAN STOP)
    # -------------------------
    def release(self, instance):

        # cancel delayed hold start
        if self.delay_event:
            self.delay_event.cancel()
            self.delay_event = None

        # if we were holding → stop cleanly
        if self.holding:
            if self.hold_event:
                self.hold_event.cancel()
                self.hold_event = None

            self.holding = False

        else:
            # this was just a TAP → single increment
            if self.direction == "up":
                self.cents += 1
            else:
                self.cents = max(0, self.cents - 1)

            self.update()

        self.direction = None


if __name__ == "__main__":
    CounterApp().run()