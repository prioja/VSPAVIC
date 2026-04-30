# This is the code prior to the split python to kv

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.spinner import SpinnerOption
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle



class BigOption(SpinnerOption):     # --- Spinner Menu Text ---
    def __init__(self, **kwargs):
        
        super().__init__(**kwargs)
        self.font_size = 42
        self.bold = True


class RoundedButton(Button):        # --- Rounded Button ---
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self.background_normal = ""  # removes default rectangle image
        self.background_color = (0, 0, 0, 0)  # fully transparent

        with self.canvas.before:
            Color(0.965, 0.784, 0.208, 1)  # yellow color
            self.rect = RoundedRectangle(radius=[15], pos=self.pos, size=self.size)

        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        
        super().__init__(orientation='vertical', spacing=50, padding=200, **kwargs)
        
        # --- Image ---
        self.add_widget(Image(source='figs/welcome.png', size_hint=(1, 0.75), pos_hint={"center_x": 0.5}))

        # --- Subject ID ---
        subject_layout = BoxLayout(size_hint=(.6, 0.1),pos_hint={"center_x": 0.5})
        subject_layout.add_widget(Label(text="Subject ID: \n(e.g. 001)", bold=True, font_size=60, size_hint=(0.4, 1)))

        self.subject_input = TextInput(multiline=False, font_size=60, font_name="Roboto-Bold.ttf", size_hint=(0.6, 1))
        subject_layout.add_widget(self.subject_input)
        self.add_widget(subject_layout)

        # --- Trial Condition ---
        trial_type_layout = BoxLayout(size_hint=(0.6, 0.1),pos_hint={"center_x": 0.5})
        trial_type_layout.add_widget(Label(text="Trial Condition:", bold=True,font_size=60, size_hint=(0.4, 1)))

        self.trial_type_spinner = Spinner(text="Select Condition", font_size=58, bold = True,values=["TH ~ Take Home", "PF ~ Proflex", "VS ~ VSPA"], size_hint=(0.6, 1),option_cls=BigOption)
        trial_type_layout.add_widget(self.trial_type_spinner)
        self.add_widget(trial_type_layout)

        # --- Trial Number ---
        trial_num_layout = BoxLayout(size_hint=(0.6, 0.1), pos_hint={"center_x": 0.5})
        trial_num_layout.add_widget(Label(text="Trial Number:", font_size=60, bold = True, size_hint=(0.4, 1)))

        self.trial_num_spinner = Spinner(text="Select Trial", size_hint=(0.6, 1), bold = True, font_size=58, values=["1", "2"], option_cls=BigOption)
        trial_num_layout.add_widget(self.trial_num_spinner)
        self.add_widget(trial_num_layout)

        # --- BEGIN BUTTON (ROUNDED) ---
        self.begin_btn = RoundedButton(text="START",size_hint=(.15, 0.15), pos_hint={"center_x":0.5},disabled=True,font_size=80,bold = True,color=(0, 0, 0, 1))  # text color white

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