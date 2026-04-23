from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image




class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=30, padding=150, **kwargs)

        self.totalsubjPayout = 3.24
        layout = BoxLayout(orientation="vertical", padding=30, spacing=60,size_hint=(1, 0.6))
        header1 = Label(text = "GAME OVER", size_hint=(1,0.1), font_size = 120, bold=True, pos_hint={"center_x": 0.5})
        header2 = Label(text = "Thank you for playing!", size_hint=(1,0.1), font_size = 60, bold=True, pos_hint={"center_x": 0.5})
        logo = Image(source='figs/logo.png', size_hint=(1, 0.8),size=(500,500))
        payoutLayout = BoxLayout(orientation = "horizontal",spacing=20,padding=30,size_hint=(0.3, 0.2), pos_hint={"center_x": 0.5})
        total = Label(text=f"Total Payout: ${self.totalsubjPayout:.2f}", font_size = 120, bold=True)

        layout.add_widget(header1)  
        layout.add_widget(header2)
        layout.add_widget(logo)   
        self.add_widget(layout)
        payoutLayout.add_widget(total)
        self.add_widget(payoutLayout)


class MyApp(App):
    def build(self):
        self.title = "VSPAVIC Experiment"
        return MainLayout()


if __name__ == "__main__":
    MyApp().run()