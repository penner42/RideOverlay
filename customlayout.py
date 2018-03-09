from kivy.uix.relativelayout import RelativeLayout


class CustomLayout(RelativeLayout):
    def __init__(self, **kwargs):
        super(CustomLayout, self).__init__(**kwargs)
        self._pages = None
        self._current_page = 0

    def add_page(self, widget):
        try:
            self._pages.append(widget)
        except AttributeError as e:
            self.add_widget(widget)
            self._pages = [widget]

    def next_page(self):
        self.remove_widget(self._pages[self._current_page])
        self._current_page += 1
        # throws IndexError if no more pages
        self.add_widget(self._pages[self._current_page])

    def prev_page(self):
        self.remove_widget(self._pages[self._current_page])
        self._current_page -= 1
        # throws IndexError if we tried to go past the beginning
        self.add_widget(self._pages[self._current_page])
