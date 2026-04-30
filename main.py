from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager

from startScreen import StartScreen
#from bidScreen import bidScreen
#from resultScreen import resultScreen
#from endScreen import endScreen


Builder.load_file("startScreen.kv")

class VSPAVicApp(App):
    
    def build(self):

        sm = ScreenManager()

        sm.add_widget(StartScreen(name="start"))
        #sm.add_widget(bidScreen(name="bid"))
        #sm.add_widget(resultScreen(name="result"))
        #sm.add_widget(endScreen(name="end"))

        sm.current = "start"
        return sm
    
if __name__ == "__main__":
    VSPAVicApp().run()
        