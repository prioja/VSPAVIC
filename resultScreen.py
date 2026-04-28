from kivy.app import App
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout

class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=30, padding=150, **kwargs)
        
        self.subjBid = 3.54
        self.roboBid1 = 4.34
        self.roboBid2 = 3.75

        self.didWin = True # Change for test losing

        Layout1 = BoxLayout(orientation="vertical", padding=30, spacing=60,size_hint=(1, 0.6))

        if self.didWin:
            Logo = Image(source="figs/won_logo.png",size_hint=(1, 0.8))
            gif = Image(source="figs/walking.gif")
            wBid = Label(text=f"Winning Bid: ${self.subjBid:.2f}", font_size = 100, bold=True, size_hint=(1,0.2))

            Layout2 = BoxLayout(orientation="horizontal", padding=30, spacing=60,size_hint=(1, 0.1))
            displayBid1 = Label(text=f"Bid 2:", font_size = 80, bold=True)
            displayBid2 = Label(text=f"Bid 3:", font_size = 80, bold=True)
        
            Layout3 = BoxLayout(orientation="horizontal", padding=30, spacing=60,size_hint=(1, 0.1))
            Bid1 = Label(text=f"${self.roboBid1:.2f}", font_size = 70, bold=True)
            Bid2 = Label(text=f"${self.roboBid2:.2f}", font_size = 70, bold=True) 

        else:
            Logo = Image(source="figs/lost_logo.png",size_hint=(1, 0.8))
            gif = Image(source="figs/walking.gif")
            wBid = Label(text=f"Your Bid: ${self.subjBid:.2f}", font_size = 100, bold=True, size_hint=(1,0.2))
            
            Layout2 = BoxLayout(orientation="horizontal", padding=30, spacing=60,size_hint=(1, 0.1))
            displayBid1 = Label(text=f"Bid 2:", font_size = 80, bold=True)
            displayBid2 = Label(text=f"Bid 3:", font_size = 80, bold=True)
        
            Layout3 = BoxLayout(orientation="horizontal", padding=30, spacing=60,size_hint=(1, 0.1))
            Bid1 = Label(text=f"${self.roboBid1:.2f}", font_size = 70, bold=True)
            Bid2 = Label(text=f"${self.roboBid2:.2f}", font_size = 70, bold=True) 

        Layout1.add_widget(Logo)
        Layout1.add_widget(gif)
        Layout1.add_widget(wBid)
       
        self.add_widget(Layout1)
        Layout2.add_widget(displayBid1)
        Layout2.add_widget(displayBid2)
        self.add_widget(Layout2)
        Layout3.add_widget(Bid1)
        Layout3.add_widget(Bid2)
        self.add_widget(Layout3)

class MyApp(App):
    def build(self):
        self.title = "VSPAVIC Experiment"
        return MainLayout()


if __name__ == "__main__":
    MyApp().run()