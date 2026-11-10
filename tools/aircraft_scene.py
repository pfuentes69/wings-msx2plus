"""Independent pixel-level reference for cropped aircraft display checks."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scenery_pixel(x, y):
    heights = (0,0,0,0,1,2,4,6,8,9,10,11,12,11,10,8,
               7,6,4,2,1,0,0,0,0,0,0,0,0,0,0,0,
               0,0,0,1,3,5,7,9,10,12,14,13,12,10,8,7,
               8,9,8,7,5,4,3,1,0,0,0,0,0,0,0,0)
    x %= 512
    height = heights[x // 8] // 2
    if y < 4:
        return 0
    if height and 13 - height <= y < 14:
        return 12 if y == 13 - height else 15
    if y < 14 and y in (6, 11) and (x + (0 if y == 6 else 17)) % 64 < 12:
        return 11
    return 13


class AircraftScene:
    def __init__(self):
        self.folder = ROOT / 'assets_msx/hellcat'
        self.metadata = json.loads((self.folder / 'manifest.json').read_text())['animation']
        self.frames = self.metadata['frames']
        self.palette = (self.folder / 'palette.bin').read_bytes()

    def page(self, shape, x, y, camera=None):
        if not 0 <= shape < len(self.frames):
            raise ValueError('invalid aircraft shape index')
        frame = self.frames[shape]
        source = (self.folder / frame['file']).read_bytes()
        if len(source) != frame['width'] * frame['height'] // 2:
            raise ValueError('packed shape size mismatch')
        result = bytearray(32768)
        if camera is not None:
            for row in range(16):
                for column in range(0, 256, 2):
                    result[(196 + row) * 128 + column // 2] = (
                        scenery_pixel(camera + column, row) * 16
                        + scenery_pixel(camera + column + 1, row))
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
                if pixel:
                    address = dy * 128 + dx // 2
                    mask = 240 if dx & 1 else 15
                    result[address] = (result[address] & mask) | (pixel if dx & 1 else pixel << 4)
        return result
