"""Recover aircraft frame-table facts and drawing origins from supplied assets."""
import hashlib
import json
from pathlib import Path
import re

SOURCE = Path('reference_assets/original_files/Wings_of_Fury/wings')


def mapping(executable=SOURCE):
    blob = executable.read_bytes()
    for offset, opcode in [(0x392, '90680004'), (0x396, '92680006'),
                            (0x56a, '90680004'), (0x56e, '92680006')]:
        if blob[offset:offset + 4] != bytes.fromhex(opcode):
            raise ValueError('drawing-origin instruction evidence differs from the supplied executable')
    def table(prefix, count):
        start = blob.find(prefix)
        if start < 0 or blob.find(prefix, start + 1) >= 0:
            raise ValueError('frame table anchor is missing or ambiguous')
        payload = blob[start:start + count * 4]
        if len(payload) != count * 4 or not re.fullmatch(rb'(hc[0-9a-f]{2})+', payload):
            raise ValueError('invalid aircraft frame table')
        return dict(file_offset=start, names=[payload[i:i + 4].decode() for i in range(0, len(payload), 4)])
    left = table(b'hc0fhc28hc29hc2a', 26)
    right = table(b'hc05hc22hc23hc24', 26)
    pitch = table(b'hc0ahc0ahc09hc09', 20)
    # Data joins selected for this MSX transition, not a port of the original state machine.
    ltr = left['names'][1:12] + right['names'][16:]
    rtl = right['names'][:12] + left['names'][16:]
    if len(ltr) != 21 or len(rtl) != 22 or ltr[0] != 'hc28' or ltr[-1] != 'hc22' or rtl[-1] != 'hc28':
        raise ValueError('unexpected recovered banking sequence')
    # Both endpoints include the same artwork's level view; close explicitly on hc05.
    ltr.append('hc05')
    return dict(executable=str(executable), sha256=hashlib.sha256(blob).hexdigest(),
        source_tables=dict(left_bank=left, right_bank=right, pitch=pitch),
        msx_transitions=dict(left_to_right=ltr, right_to_left=rtl),
        timing='MSX-authored: one sequence step per five 150 Hz core ticks',
        drawing_origin_evidence=dict(file_offsets=[0x392, 0x396, 0x56a, 0x56e],
            semantics='draw X/Y subtract signed header words at offsets 4/6'),
        mirror_origin_rule='reflected origin_x = padded_width - original origin_x; validated by 20 stored fa/fb pairs')


if __name__ == '__main__':
    print(json.dumps(mapping(), indent=2))
