"""
GIF playback without relying on Kivy's built-in GIF decoder.

Some Kivy/SDL builds fail to load GIFs even when Pillow can decode them.
This widget advances frames manually and uploads RGBA bytes to a Texture.
"""

from pathlib import Path

from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.image import Image


class PillowGifImage(Image):
    """Display an animated GIF using Pillow + manual texture updates."""

    def __init__(self, fps=12.0, **kwargs):
        kwargs.setdefault("allow_stretch", True)
        kwargs.setdefault("keep_ratio", True)
        super().__init__(**kwargs)
        self._gifPath = None
        self._pil = None
        self._frameIndex = 0
        self._nFrames = 1
        self._dt = 1.0 / max(1.0, float(fps))
        self._ev = None

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        try:
            if self._pil is not None:
                self._pil.close()
        except Exception:
            pass
        self._pil = None

    def start(self, gifPath):
        self.stop()
        self._gifPath = Path(gifPath)
        try:
            from PIL import Image as PILImage  # noqa: WPS433 — runtime import ok here

            self._pil = PILImage.open(str(self._gifPath))
            self._nFrames = getattr(self._pil, "n_frames", 1)
            self._frameIndex = 0
            self._renderCurrentFrame()
            self._ev = Clock.schedule_interval(self._tick, self._dt)
        except Exception:
            self._pil = None
            self.texture = None

    def _tick(self, _dt):
        if self._pil is None:
            return False
        self._frameIndex = (self._frameIndex + 1) % max(1, self._nFrames)
        self._renderCurrentFrame()
        return True

    def _renderCurrentFrame(self):
        if self._pil is None:
            return
        self._pil.seek(self._frameIndex)
        frame = self._pil.convert("RGBA")
        w, h = frame.size
        data = frame.tobytes()

        if self.texture is None or self.texture.size != (w, h):
            tex = Texture.create(size=(w, h), colorfmt="rgba")
            tex.flip_vertical()
            self.texture = tex
        self.texture.blit_buffer(data, colorfmt="rgba", bufferfmt="ubyte")

        # Manual texture uploads sometimes don't repaint until another UI event happens.
        # Force Kivy to schedule a redraw of this widget's graphics subtree.
        try:
            self.canvas.ask_update()
        except Exception:
            pass
