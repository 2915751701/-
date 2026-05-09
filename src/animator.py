from pathlib import Path
from PIL import Image
from atlas import load_manifest


class PetAnimator:
    def __init__(self, frames_dir: Path):
        self.frames_dir = frames_dir
        self.manifest = load_manifest(frames_dir)
        self._images = {}
        for state, info in self.manifest.items():
            existing = [p for p in info["frames"] if (self.frames_dir / p).exists()]
            if existing:
                self._images[state] = [Image.open(self.frames_dir / p) for p in existing]
                info["frames"] = existing
                info["durations"] = info["durations"][:len(existing)]

        self._state = "idle"
        self._frame_index = 0
        self._elapsed = 0
        self._durations = self.manifest[self._state]["durations"]
        self._images_for_state = self._images[self._state]
        self._speed = 1.0
        self._loop = True
        self._finished = False

    @property
    def state(self) -> str:
        return self._state

    @property
    def frame_count(self) -> int:
        return len(self._images_for_state)

    def set_state(self, state: str):
        if state == self._state:
            return
        if state not in self._images:
            raise ValueError(f"Unknown state: {state}")
        self._state = state
        self._frame_index = 0
        self._elapsed = 0
        self._durations = self.manifest[state]["durations"]
        self._images_for_state = self._images[state]
        if state == "review":
            self._speed = 0.5
            self._loop = False
        elif state == "failed":
            self._speed = 0.5
            self._loop = True
        else:
            self._speed = 1.0
            self._loop = True
        self._finished = False

    def update(self, dt_ms: int):
        """Advance animation by dt_ms milliseconds."""
        if self._finished:
            return
        self._elapsed += dt_ms * self._speed
        duration = self._durations[self._frame_index]
        while self._elapsed >= duration:
            self._elapsed -= duration
            next_index = self._frame_index + 1
            if next_index >= len(self._durations):
                if self._loop:
                    self._frame_index = 0
                else:
                    self._frame_index = len(self._durations) - 1
                    self._finished = True
                    break
            else:
                self._frame_index = next_index
            duration = self._durations[self._frame_index]

    def current_frame(self) -> Image.Image:
        return self._images_for_state[self._frame_index]

    def current_duration_ms(self) -> int:
        return self._durations[self._frame_index]
