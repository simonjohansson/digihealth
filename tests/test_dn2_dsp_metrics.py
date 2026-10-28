# SPDX-License-Identifier: GPL-2.0-or-later
"""Execute the actual receiver; packets/CRC are built independently in Python."""
import binascii
import ctypes
import struct
import subprocess
import os
import shutil
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import digiusb as usb


def packet(seq=1, count=17, hi=0, lo=17000, maximum=1000, clock=1234, flags=1, reserved=0):
    payload = struct.pack('>8I', 0x44485331, count, hi, lo, maximum, clock, flags, reserved)
    halves = struct.unpack('>16H', payload) + (binascii.crc_hqx(payload, 0xffff),)
    return [0xd6000000 | (seq << 21) | (i << 16) | half for i, half in enumerate(halves)]


class Receiver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = Path(self.tmp.name)
        (p/'locks.c').write_text('unsigned core_keys_lock(void){return 0x2715;}\n'
                                'void core_keys_unlock(unsigned sr){if(sr!=0x2715)__builtin_trap();}\n')
        subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT/'dn2/dsp-metrics.c'), str(p/'locks.c'), '-o', str(p/'receiver.dylib')], check=True)
        self.lib = ctypes.CDLL(str(p/'receiver.dylib'))
        self.block = 0

    def tearDown(self):
        self.tmp.cleanup()

    def feed(self, words):
        for word in words:
            self.block = (self.block + 1) & 0xffffffff
            self.lib.dhs_block(ctypes.c_uint(word), ctypes.c_uint(self.block))

    def read(self):
        out = (ctypes.c_uint * 16)()
        self.lib.dhs_read(out)
        return list(out)

    def test_complete_wrap_duplicate_and_stale(self):
        self.assertEqual(self.read(), [0x44484331, 0x10040] + [0]*14)
        self.block = 0xfffffff0
        words = packet(7, count=0xfffffff0, hi=1, lo=0xfffffff0)
        self.feed(words[:8]); self.assertEqual(self.read()[2], 0)
        self.feed([words[7]]); self.feed(words[8:])
        out = self.read()
        self.assertEqual(out[2], 3); self.assertEqual(out[5:12], [7, 0xfffffff0, 1, 0xfffffff0, 1000, 1234, 1])
        self.assertEqual(out[12:15], [1, 0, 0])
        self.feed([words[-1]]*64); self.assertEqual(self.read()[2], 3)
        self.feed([words[-1]]); self.assertEqual(self.read()[2], 2)
        # Replaying an identical complete snapshot cannot renew freshness.
        self.feed(words); self.assertEqual(self.read()[2], 2)
        self.feed(packet(0, count=1, hi=2, lo=0x100, clock=4567)); self.assertEqual(self.read()[2], 3)
        self.assertEqual(self.read()[12], 2)

    def test_loss_crc_torn_sequence_and_restart(self):
        for change in ('gap', 'crc', 'torn', 'sequence', 'reset'):
            with self.subTest(change=change):
                words = packet(clock=self.block+1)
                if change == 'gap': words.pop(5)
                elif change == 'crc': words[-1] ^= 1
                elif change == 'torn': words[6] = (words[6] & 0xffff0000) | (words[7] & 0xffff)
                elif change == 'sequence': words[5] ^= 1 << 21
                else: words = words[:6] + packet(0)[:6]
                self.feed(words)
                self.assertEqual(self.read()[2], 0)
                self.feed([0]*65)
        self.assertGreater(self.read()[13], 0)
        self.assertGreater(self.read()[14], 0)
        self.feed(packet(0, clock=self.block+1))
        self.assertEqual(self.read()[2], 3)

    def test_invalid_payload_and_partial_timeout(self):
        for kw in ({'flags':0}, {'flags':3}, {'reserved':1}):
            self.feed(packet(**kw)); self.assertEqual(self.read()[2], 0)
        words = packet()
        self.feed(words[:1]); self.feed([words[0]]*65); self.feed(words[1:])
        self.assertEqual(self.read()[2], 0)
        self.feed(packet(clock=2345)); self.assertEqual(self.read()[2], 3)
        self.feed([0xd6110000]); self.assertEqual(self.read()[12], 1)

    def test_canonical_read_only_command(self):
        reply = (ctypes.c_ubyte * 80)()
        def call(body):
            data = (ctypes.c_ubyte * len(body))(*body)
            return self.lib.dhs_receive(data, len(body), reply)
        self.assertEqual(call([0, 0, 7, 4]), 0)
        self.assertEqual(call([0, 0, 7, 5]), 68)
        self.assertEqual(bytes(reply[:4]), b'\0\7\x85\0')
        self.assertEqual(struct.unpack('>16I', bytes(reply[4:68])), tuple(self.read()))
        for malformed in ([1,0,7,5], [0,0,7,5,0], [0,128,7,5], [128,0,7,5]):
            self.assertEqual(call(malformed), 4)
            self.assertEqual(reply[3], 1)


class CompiledReceiver(unittest.TestCase):
    def test_actual_coldfire_decoder(self):
        names = ('DN2_TEST_SYX', 'DN2_TEST_MAP', 'DN2_BRIDGE')
        if any(not os.environ.get(n) for n in names): self.skipTest('missing compiled firmware inputs')
        cross = os.environ.get('ELEKLOADER_CROSS', 'm68k-linux-gnu-')
        panel = Path(os.environ['DN2_BRIDGE']).with_name('panel_drive')
        if not panel.is_file() or not shutil.which(cross+'gcc'):
            self.skipTest('missing panel_drive or cross compiler')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(os.environ.get('DN2_TEST_OUT', temp))/'dsp-compiled'
            subprocess.run([sys.executable, str(ROOT/'tests/dn2_dsp_metrics_compiled.py'),
                            os.environ['DN2_TEST_SYX'], os.environ['DN2_TEST_MAP'],
                            str(panel), str(output), cross], check=True)


def host_payload(**changes):
    d = dict(zip(usb.DSP_METRICS_FIELDS, (0x44484331, 1, 64, 3, 100, 101, 7,
                 100, 0, 100000, 1000, 1234, 1, 7, 0, 0, 0)))
    d.update(changes)
    return struct.pack(usb.DSP_METRICS_FMT, *(d[n] for n in usb.DSP_METRICS_FIELDS))


class Client(unittest.TestCase):
    def test_layout_freshness_and_refusals(self):
        d = usb.decode_dsp_metrics(host_payload())
        self.assertTrue(d['available']); self.assertEqual(d['age_blocks'], 1)
        self.assertEqual(d['sum_ticks'], 100000)
        self.assertEqual(usb.unpack7(usb.req_dsp_metrics(7)[6:-1]), b'\0\7\5')
        for change in ({'version':2}, {'flags':7}, {'flags':1}, {'flags':2},
                       {'producer_flags':0}, {'reserved':1}, {'sequence':8}, {'now_blocks':165}):
            with self.assertRaises(ValueError): usb.decode_dsp_metrics(host_payload(**change))
        for blob in (b'', host_payload()[:-1], host_payload()+b'\0'):
            with self.assertRaises(ValueError): usb.decode_dsp_metrics(blob)
        self.assertFalse(usb.decode_dsp_metrics(host_payload(flags=2, now_blocks=165))['available'])
        d = usb.Diag(None)
        d._call = Mock(side_effect=[TimeoutError(), b'ok'])
        self.assertEqual(d.call(usb.req_dsp_metrics), b'ok')
        self.assertEqual(d._call.call_count, 2)

    def test_unsigned_deltas_and_reboot_baseline(self):
        before = usb.decode_dsp_metrics(host_payload(published_blocks=0xfffffff0, now_blocks=0xfffffff1,
                  callback_count=0xfffffff0, sum_hi=0xffffffff, sum_lo=0xfffffc18))
        after = usb.decode_dsp_metrics(host_payload(published_blocks=1, now_blocks=2,
                 callback_count=1, sum_hi=0, sum_lo=16000))
        self.assertEqual(usb.callback_window(before, after), {'count':17, 'ticks':17000, 'average':1000})
        self.assertIsNone(usb.callback_window(None, after))
        self.assertIsNone(usb.callback_window(after, after))
        before = usb.decode_dsp_metrics(host_payload())
        after = usb.decode_dsp_metrics(host_payload(published_blocks=117, now_blocks=118,
                 callback_count=117, sum_lo=117000))
        self.assertEqual(usb.callback_window(before, after)['average'], 1000)
        impossible = usb.decode_dsp_metrics(host_payload(published_blocks=117, now_blocks=118,
                     callback_count=117, sum_lo=117017))
        self.assertIsNone(usb.callback_window(before, impossible))
        reboot = usb.decode_dsp_metrics(host_payload(published_blocks=1, now_blocks=2,
                  callback_count=1, sum_lo=1000))
        self.assertIsNone(usb.callback_window(before, reboot))
        dsp_restart = usb.decode_dsp_metrics(host_payload(published_blocks=117, now_blocks=118,
                     callback_count=1, sum_lo=1000))
        self.assertIsNone(usb.callback_window(before, dsp_restart))
        stale = usb.decode_dsp_metrics(host_payload(flags=2, now_blocks=165))
        self.assertIsNone(usb.callback_window(stale, after))


if __name__ == '__main__':
    unittest.main()
