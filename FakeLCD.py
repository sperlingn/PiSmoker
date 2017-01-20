from curses import initscr, noecho

# Char LCD plate button names.
SELECT = 115
RIGHT = 100
DOWN = 120
UP = 119
LEFT = 97


class Adafruit_CharLCDPlate:
    def __init__(self):
        self.screen = initscr()
        noecho()
        self.screen.nodelay(1)

    def message(self, text):
        # print text
        self.screen.addstr(5, 5, text)
        self.screen.refresh()

    def home(self):
        self.screen.clear()

    # self.screen.refresh()

    def is_pressed(self, button):
        c = self.screen.getch()
        if c == button:
            return True
        else:
            return False

    def clear(self):
        self.screen.clear()
