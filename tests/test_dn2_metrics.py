# SPDX-License-Identifier: GPL-2.0-or-later
"""Host checks for the real DN2 metrics producer and its wire/client boundary."""

import contextlib
import io
import os
import shutil
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import digiusb as usb


def payload(**changes):
    d = dict(
        zip(
            usb.METRICS_FIELDS,
            (
                0x44484D31,
                1,
                56,
                7,
                4500,
                3,
                1500,
                100000,
                500,
                1000,
                0,
                150000,
                100,
                1500,
                0,
            ),
        )
    )
    d.update(changes)
    return struct.pack(usb.METRICS_FMT, *(d[k] for k in usb.METRICS_FIELDS))


class Metrics(unittest.TestCase):
    def test_actual_c_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in (0, 100, 0xFFFFFFF0):
                with self.subTest(reply=value):
                    exe = str(Path(tmp) / "metrics")
                    subprocess.run(
                        [
                            "cc",
                            "-std=c99",
                            "-Wall",
                            "-Wextra",
                            "-Werror",
                            "-DREPLY=%du" % value,
                            str(ROOT / "tests/test_dn2_metrics.c"),
                            "-o",
                            exe,
                        ],
                        check=True,
                    )
                    subprocess.run([exe], check=True)

    def test_compiled_hook_abi(self):
        names = ("DN2_TEST_SYX", "DN2_TEST_MAP", "DN2_BRIDGE")
        if any(not os.environ.get(n) for n in names):
            self.skipTest("missing " + ", ".join(names))
        cross = os.environ.get("ELEKLOADER_CROSS", "m68k-linux-gnu-")
        panel = Path(os.environ["DN2_BRIDGE"]).with_name("panel_drive")
        if not panel.is_file() or not shutil.which(cross + "as"):
            self.skipTest("missing panel_drive or cross assembler")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(os.environ.get("DN2_TEST_OUT", temp)) / "metrics-abi"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/dn2_metrics_abi.py"),
                    os.environ["DN2_TEST_SYX"],
                    os.environ["DN2_TEST_MAP"],
                    str(panel),
                    str(output),
                    cross,
                ],
                check=True,
            )

    def test_layout_and_units(self):
        d = usb.decode_metrics(payload())
        self.assertEqual(d["cpu_relative"], 0.5)
        self.assertEqual(d["handler_average"], 100)
        d = usb.decode_metrics(
            payload(handler_sum_hi=1, handler_sum_lo=0, handler_max=3000000)
        )
        self.assertEqual(d["handler_average"], 2**32 / 1500)
        self.assertEqual(usb.unpack7(usb.req_metrics(7)[6:-1]), b"\0\7\4")

    def test_unavailable_and_warmup(self):
        d = usb.decode_metrics(
            payload(
                flags=0,
                blocks=0,
                windows=0,
                idle_total=0,
                idle_window=0,
                idle_reference=0,
                handler_sum_lo=0,
                handler_max=0,
                handler_samples=0,
            )
        )
        self.assertNotIn("cpu_relative", d)
        self.assertNotIn("handler_average", d)
        d = usb.decode_metrics(payload(flags=5, windows=2))
        self.assertNotIn("cpu_relative", d)
        self.assertIn("handler_average", d)

    def test_malformed_snapshot_is_refused(self):
        for p in (
            payload()[:-1],
            payload() + b"\0",
            payload(version=2),
            payload(bytes=52),
            payload(magic=0),
            payload(flags=15),
            payload(window_blocks=1499),
            payload(idle_reference=0),
            payload(idle_window=1001),
            payload(handler_samples=1499),
            payload(handler_max=99),
            payload(flags=3),
            payload(flags=7, windows=2),
        ):
            with self.subTest(payload=p.hex()):
                with self.assertRaises(ValueError):
                    usb.decode_metrics(p)

    def test_legacy_command_fallback(self):
        raw = struct.pack(
            usb.STATS_FMT,
            1,
            1,
            1,
            66000000,
            39600000,
            30000,
            1500,
            0,
            0,
            14000000,
            0,
            21,
            60000000,
        ) + bytes(48)

        class OldHelper:
            def call(self, builder):
                if builder is usb.req_metrics:
                    raise usb._RequestRefused("unknown command")
                self.assert_stats = builder is usb.req_stats
                return raw

        helper = OldHelper()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            usb.cmd_stats(helper, ["1"])
        self.assertTrue(helper.assert_stats)
        self.assertIn("DSP  60.0", out.getvalue())

    def test_reporting_and_legacy_stats(self):
        fields = [1, 0, 60, 1000, 0, 0, 0, 0, 0, 14000000, 0, 21, 0]
        raw = struct.pack(usb.STATS_FMT, *fields) + struct.pack(
            ">24H", *([0] * 20 + [1, 0, 0, 0])
        )
        s = usb.decode_stats(raw)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            usb.show_stats(s, usb.decode_metrics(payload()))
        text = out.getvalue()
        self.assertIn("relative to rolling best idle window", text)
        self.assertIn("raw EMUCLK ticks", text)
        self.assertIn("total DSP load and peak stack: unavailable", text)
        self.assertIn("sample pool free: unavailable on DN2", text)
        self.assertNotIn("audio stopped", text)
        self.assertEqual(s["heap_largest"], 16 << 20)
        fields[1] = 1
        fields[3:7] = [66000000, 39600000, 30000, 1500]
        s = usb.decode_stats(struct.pack(usb.STATS_FMT, *fields) + bytes(48))
        self.assertAlmostEqual(s["dsp"], 0.6)
        fields[1] = 0
        s = usb.decode_stats(struct.pack(usb.STATS_FMT, *fields) + bytes(48))
        self.assertNotIn("dsp", s)  # invalid legacy timing is not an observation


if __name__ == "__main__":
    unittest.main()
