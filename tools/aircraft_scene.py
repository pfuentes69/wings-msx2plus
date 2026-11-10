"""Independent pixel-level reference for cropped aircraft display checks."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AircraftScene:
    def __init__(self):
        self.folder = ROOT / 'assets_msx/hellcat'
        self.metadata = json.loads((self.folder / 'manifest.json').read_text())['animation']
        self.frames = self.metadata['frames']
        self.palette = (self.folder / 'palette.bin').read_bytes()

    def page(self, shape, x, y):
        if not 0 <= shape < len(self.frames):
            raise ValueError('invalid aircraft shape index')
        frame = self.frames[shape]
        source = (self.folder / frame['file']).read_bytes()
        if len(source) != frame['width'] * frame['height'] // 2:
            raise ValueError('packed shape size mismatch')
        result = bytearray(32768)
        for sy in range(frame['height']):
            dy = y + frame['dy'] + sy
            if not 0 <= dy < 212:
                continue
            for sx in range(frame['width']):
                dx = x + frame['dx'] + sx
                if not 0 <= dx < 256:
                    continue
                packed = source[sy * (frame['width'] // 2) + sx // 2]
                pixel = (packed & 15) if sx & 1 else (packed >> 4)
                result[dy * 128 + dx // 2] |= pixel if dx & 1 else pixel << 4
        return result
