"""Shared rounded button with press background swap (used on start + bid screens)."""

from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle

# Background while pressed (like Kivy ``background_down``).
PRESS_BG = (0.102, 0.710, 0.929, 1)


class RoundedButton(Button):
    """Rounded fill; solid background color while pressed (no blink/flash animation)."""

    def __init__(self, bg=(0.5, 0.5, 0.5, 1), radius=15, press_bg=PRESS_BG, **kwargs):
        super().__init__(**kwargs)

        self._radius = radius
        self._base_bg = self._normalize_bg(bg)
        self._press_bg = self._normalize_bg(press_bg)
        self._pressed = False

        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)

        with self.canvas.before:
            self.color_instr = Color(*self._base_bg)
            self.rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[radius],
            )

        self.bind(
            pos=self.update_rect,
            size=self.update_rect,
            disabled=self._on_disabled,
        )

    @staticmethod
    def _normalize_bg(bg):
        bg = tuple(bg)
        if len(bg) == 3:
            return (bg[0], bg[1], bg[2], 1.0)
        return tuple(bg)

    def set_bg(self, bg):
        """Update normal fill (e.g. SUBMIT gray vs green)."""
        self._base_bg = self._normalize_bg(bg)
        if not self._pressed:
            self.color_instr.rgba = self._base_bg

    def _touch_inside(self, touch):
        return self.collide_point(*self.to_widget(touch.x, touch.y, relative=False))

    def _set_pressed(self, pressed):
        self._pressed = bool(pressed) and not self.disabled
        self.color_instr.rgba = self._press_bg if self._pressed else self._base_bg

    def _on_disabled(self, *_args):
        if self.disabled:
            self._set_pressed(False)
        else:
            self.color_instr.rgba = self._base_bg

    def on_touch_down(self, touch):
        if self.disabled or not self._touch_inside(touch):
            return False
        self._set_pressed(True)
        touch.grab(self)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        inside = self._touch_inside(touch)
        self._set_pressed(False)
        if inside and not self.disabled:
            self.dispatch("on_press")
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        self._set_pressed(self._touch_inside(touch))
        return True

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
