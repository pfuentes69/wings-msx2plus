import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from extract_audio import extract, read_8svx, read_hunks, wav_bytes


def fixture(compression=0, declared=4):
    vhdr = struct.pack('>IIIHBBI', declared, 0, 0, 8000, 1, compression, 65536)
    body = b'\x80\xff\x00\x7f'
    chunks = b'VHDR' + struct.pack('>I', 20) + vhdr + b'BODY' + struct.pack('>I', len(body)) + body
    return b'FORM' + struct.pack('>I', 4 + len(chunks)) + b'8SVX' + chunks


class AudioTests(unittest.TestCase):
    def test_signed_to_unsigned_wav_conversion(self):
        source = b'\x80\xff\x00\x7f'
        with wave.open(io.BytesIO(wav_bytes(source, 8000)), 'rb') as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 1, 8000))
            self.assertEqual(wav.readframes(4), b'\x00\x7f\x80\xff')

    def test_8svx_counts_and_rate(self):
        pcm, meta = read_8svx(fixture())
        self.assertEqual(pcm, b'\x80\xff\x00\x7f')
        self.assertEqual(meta['rate_hz'], 8000)

    def test_bad_8svx(self):
        for data in (b'FORM', fixture()[:-1], fixture(compression=1), fixture(declared=5)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                read_8svx(data)

    def test_hunk_structure_and_truncation(self):
        data = (ROOT / 'reference_assets/original_files/Wings_of_Fury/wofsongs').read_bytes()
        hunks = read_hunks(data)
        self.assertEqual([h['bytes'] for h in hunks], [276, 39020, 4])
        self.assertEqual(hunks[1]['symbols']['song1'], 20)
        for bad in (data[:3], data[:40], data[:2000], b'wrong'):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                read_hunks(bad)

    def test_extracted_audio_matches_sources_and_metadata(self):
        source = ROOT / 'reference_assets/original_files/Wings_of_Fury'
        files, meta = extract(source, 8363)
        self.assertEqual(len(meta['effects']), 8)
        self.assertEqual(len(meta['instruments']), 6)
        self.assertEqual([s['symbol'] for s in meta['music']['slots']], ['song1', 'song2', 'song3', 'song2', 'song4'])
        self.assertEqual(meta['music']['unique_song_definitions'], 4)
        for effect in meta['effects']:
            with wave.open(io.BytesIO(files[effect['wav']]), 'rb') as wav:
                signed = bytes(v ^ 128 for v in wav.readframes(wav.getnframes()))
            self.assertEqual(signed, (source / 'sounds' / effect['name']).read_bytes())
        for instrument in meta['instruments']:
            wav_path = instrument['wav']
            pcm, fields = read_8svx(files[wav_path[:-4] + '.8svx'])
            with wave.open(io.BytesIO(files[wav_path]), 'rb') as wav:
                self.assertEqual(wav.getframerate(), fields['rate_hz'])
                self.assertEqual(bytes(v ^ 128 for v in wav.readframes(wav.getnframes())), pcm)
        for path, expected in files.items():
            self.assertEqual((ROOT / 'assets_src/audio' / path).read_bytes(), expected, path)

    def test_music_previews_are_valid_non_silent_and_hashed(self):
        folder = ROOT / 'assets_src/audio/music/previews'
        manifest = json.loads((folder / 'manifest.json').read_text())
        self.assertFalse(manifest['complete_tracks'])
        self.assertEqual(len(manifest['previews']), 4)
        for entry in manifest['previews']:
            data = (folder / entry['file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
            with wave.open(io.BytesIO(data), 'rb') as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (2, 2, 44100))
                self.assertEqual(wav.getnframes(), 441000)
                self.assertGreater(len(set(wav.readframes(wav.getnframes()))), 128)
            self.assertGreater(entry['rms'], 1)


if __name__ == '__main__':
    unittest.main()
