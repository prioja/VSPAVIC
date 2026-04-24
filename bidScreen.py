from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.screenmanager import Screen, ScreenManager


class firstBid(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)

        self.cents = 0

        layout1 = BoxLayout(orientation="vertical",size_hint=(1,1), padding=30, spacing=30)
        logo = Image(source="figs/logo.png", size_hint=(0.25, 0.1), pos_hint={"center_x": 0.5})
        header = Label(text = "PLEASE PLACE BID", size_hint=(1, 0.05), font_size = 45, bold=True)
        self.display = Label(text=self.format_money(), font_size = 330, size_hint=(1, 0.2), pos_hint={"center_ y": 0.2})
        grid = GridLayout(cols=3, spacing=10, size_hint=(.45,0.25), pos_hint={"center_x": 0.5})
        buttons = [
            "1", "2", "3",
            "4", "5", "6",
            "7", "8", "9",
            "0", "C", "DEL"
        ]

        for b in buttons:
            btn = Button(text=b, font_size=90, bold=True)
            btn.bind(on_press=self.on_button_press)
            grid.add_widget(btn)

        self.submit_btn = Button(text="SUBMIT",size_hint=(0.15, 0.05),pos_hint={"center_x": 0.5},font_size=50, bold=True, disabled=True,background_normal="",background_color=(0, 0, 0, 0))
        
        with self.submit_btn.canvas.before:
            self.btn_color = Color(0.5, 0.5, 0.5, 1)
            self.submit_rect = RoundedRectangle(size=self.submit_btn.size,pos=self.submit_btn.pos,radius=[15])
        self.submit_btn.bind(pos=self.update_rect, size=self.update_rect)

# --------------------- build -------------------------
        layout1.add_widget(logo)
        layout1.add_widget(header)
        layout1.add_widget(self.display)
        self.add_widget(layout1)

        layout1.add_widget(grid)
        layout1.add_widget(self.submit_btn)

# --------------------- money formatting -------------------------
    def format_money(self):
        return f"${self.cents //100}.{self.cents % 100:02d}"

    def update_display(self):
        self.display.text = self.format_money()

        if self.cents == 0:
            self.submit_btn.disabled = True
            self.btn_color.rgb = (0.5, 0.5, 0.5)  # gray
        else:
            self.submit_btn.disabled = False
            self.btn_color.rgb = (0.2, 0.7, 0.2)  # green

    def on_button_press(self, instance):# --------------------- keypad logic -------------------------
        text = instance.text

        if text == "C":
            self.cents = 0
        elif text == "DEL":
            self.cents = self.cents // 10
        else:
            self.cents = self.cents * 10 + int(text)

        self.update_display()

    def update_rect(self, *args): # round button
        self.submit_rect.pos = self.submit_btn.pos
        self.submit_rect.size = self.submit_btn.size

class MyApp(App):
    def build(self):

        self.title = "VSPAVIC Experiment"
        return firstBid()


if __name__ == "__main__":
    MyApp().run()