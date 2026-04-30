from kivy.uix.screenmanager import ScreenManager, Screen
from datetime import datetime
from Robobidders import *
from numpy import random
import numpy as np


class Controller:

    def __init__(self, state, robo_model):

        self.state = state
        self.robo_model = robo_model

        # Robo-bidder  parameters
        k = 0.4395073979128712
        b = 0.05735650555767768 
        robo_models = roboModel(k,b,2) 

        # Inintialize parameters
        self.minTime = 1 # 35 min default - 1 min for testing
        self.maxTime = 5 # 45 min default - 5 min for testing
        self.totalAuctionTime = random.choice(range(self.minTime, self.maxTime))
        self.auctionStartTime = 0.00
        self.totalRounds = 0
        self.roundLength = 120 # 2 minute rounds
        self.trial = 0


        # The startScreen should start now
        self.trialCond = ""
        self.trialNum = ""
        self.subjID = ""
        

             

        self.auctionFilename = "VSPAVIC" + self.subjID + "_A_" + self.trialCond + self.trialNum + ".csv"
        self.hrFilename = "VSPAVIC" + self.subjID + "_HR_" + self.trialCond + self.trialNum + ".csv"
