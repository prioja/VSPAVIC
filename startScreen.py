from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle


# --- ROUNDED BUTTON ---
class RoundedButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.background_normal = ""  # removes default rectangle image
        self.background_color = (0, 0, 0, 0)  # fully transparent

        with self.canvas.before:
            Color(0.2, 0.7, 1, 1)  # blue color
            self.rect = RoundedRectangle(radius=[15], pos=self.pos, size=self.size)

        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=30, padding=200, **kwargs)

        # --- Image ---
        self.add_widget(Image(source='figs/welcome.png', size_hint=(1, 0.5), pos_hint={"center_x": 0.5}))

        # --- Subject ID ---
        subject_layout = BoxLayout(size_hint=(1, 0.1))
        subject_layout.add_widget(Label(
            text="Subject ID: \n(e.g. 001)",
            bold=True,
            font_size=42,
            size_hint=(0.6, 1)
        ))

        self.subject_input = TextInput(multiline=False, font_size=34, font_name="Roboto-Bold.ttf")
        subject_layout.add_widget(self.subject_input)
        self.add_widget(subject_layout)

        # --- Trial Condition ---
        trial_type_layout = BoxLayout(size_hint=(1, 0.1))
        trial_type_layout.add_widget(Label(
            text="Trial Condition:",
            bold=True,
            font_size=42,
            size_hint=(0.6, 1)
        ))

        self.trial_type_spinner = Spinner(
            text="Select Condition",
            font_size=36,
            bold = True,
            values=["TH ~ Take Home", "PF ~ Proflex", "VS ~ VSPA"]
        )
        trial_type_layout.add_widget(self.trial_type_spinner)
        self.add_widget(trial_type_layout)

        # --- Trial Number ---
        trial_num_layout = BoxLayout(size_hint=(1, 0.1))
        trial_num_layout.add_widget(Label(
            text="Trial Number:",
            font_size=42,
            bold = True,
            size_hint=(0.6, 1)
        ))

        self.trial_num_spinner = Spinner(
            text="Select Trial",
            bold = True,
            font_size=36,
            values=["1", "2"]
        )
        trial_num_layout.add_widget(self.trial_num_spinner)
        self.add_widget(trial_num_layout)

        # --- BEGIN BUTTON (ROUNDED) ---
        self.begin_btn = RoundedButton(
            text="Begin",
            size_hint=(.25, 0.13),
            pos_hint={"center_x":0.5},
            disabled=True,
            font_size=34,
            bold = True,
            color=(1, 1, 1, 1)  # text color white
        )

        self.begin_btn.bind(on_press=self.start_trial)
        self.add_widget(self.begin_btn)

        # --- VALIDATION ---
        self.subject_input.bind(text=lambda *args: self.check_valid())
        self.trial_type_spinner.bind(text=lambda *args: self.check_valid())
        self.trial_num_spinner.bind(text=lambda *args: self.check_valid())

    # --- VALIDATION ---
    def check_valid(self):
        subject_id = self.subject_input.text.strip()
        trial_type = self.trial_type_spinner.text
        trial_num = self.trial_num_spinner.text

        is_valid = (
            subject_id != "" and
            trial_type != "Select Condition" and
            trial_num != "Select Trial"
        )

        self.begin_btn.disabled = not is_valid
        self.begin_btn.opacity = 1 if is_valid else 0.4

    # --- START ---
    def start_trial(self, instance):
        print("=== STARTING EXPERIMENT ===")
        print("Subject ID:", self.subject_input.text)
        print("Trial Condition:", self.trial_type_spinner.text)
        print("Trial Number:", self.trial_num_spinner.text)


class MyApp(App):
    def build(self):
        self.title = "VSPAVIC Experiment"
        return MainLayout()


if __name__ == "__main__":
    MyApp().run()