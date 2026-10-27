# SPDX-License-Identifier: GPL-2.0-or-later
"""The DN2 DSP_PEEK client (dn2/dsp-peek.c on the unit): requests, and reads assembled from replies."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import digiusb as usb


class FakeDiag:
    """Answers DSP_PEEK and DSP_PEEK_READ for DSP memory WORDS at ADDRESS, ARRIVING after some polls."""

    def __init__(self, address, words, arriving=2):
        self.address, self.words, self.arriving, self.started = address, words, arriving, None

    def call(self, builder, *args):
        if builder is usb.req_dsp_peek:
            start, count = args
            self.started = (start - self.address) // 4, count
            return b''
        first, count = args
        base, total = self.started
        received = 2 * total if self.arriving <= 0 else 0
        self.arriving -= 1
        words = self.words[base + first:base + first + count]
        return struct.pack('>HH', received, 2 * total) + b''.join(struct.pack('>I', w) for w in words)


class Client(unittest.TestCase):
    def test_requests(self):
        self.assertEqual(usb.unpack7(usb.req_dsp_peek(7, 0x2df000, 1)[6:-1]),
                         b'\0\7\6' + struct.pack('>IH', 0x2df000, 1))
        self.assertEqual(usb.unpack7(usb.req_dsp_peek_read(7, 256, 256)[6:-1]),
                         b'\0\7\7' + struct.pack('>HH', 256, 256))
        for address, words in ((0x2df002, 1), (0x2df000, 0), (0x2df000, usb.DSP_PEEK_MAX + 1)):
            with self.assertRaises(ValueError):
                usb.req_dsp_peek(1, address, words)

    def test_a_read_comes_back_in_the_dsps_byte_order(self):
        words = list(range(0x10203040, 0x10203040 + 1500))
        d = FakeDiag(0x200a8000, words)
        with patch.object(usb.time, 'sleep'):
            data = usb.dsp_peek(d, 0x200a8000, 4 * 1300 + 2)        # two requests, chunked reads, a tail
        self.assertEqual(data, b''.join(struct.pack('<I', w) for w in words[:1301])[:4 * 1300 + 2])

    def test_no_dsp_side_times_out_with_its_reason(self):
        d = FakeDiag(0x2df000, [0], arriving=10 ** 9)
        with patch.object(usb.time, 'sleep'), patch.object(usb.time, 'monotonic', side_effect=[0, 0, 100]):
            with self.assertRaisesRegex(TimeoutError, 'only a build with a SHARC mod'):
                usb.dsp_peek(d, 0x2df000, 4)


if __name__ == '__main__':
    unittest.main()
