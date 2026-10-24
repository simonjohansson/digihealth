# SPDX-License-Identifier: GPL-2.0-or-later
"""Run bounded compiled-hook probes; all writes affect only emulator memory."""

import json, struct, subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
firmware, manifest_path, panel, output, cross = sys.argv[1:]
out = Path(output)
out.mkdir(parents=True, exist_ok=True)
manifest = json.loads(Path(manifest_path).read_text())["_map"]
symbols = {
    p[2]: int(p[0], 16)
    for line in subprocess.check_output(
        [cross + "nm", "-n", str(root / "out/digihealth.work/sysinfo.s.o")], text=True
    ).splitlines()
    if len(p := line.split()) == 3
}
probe_base = manifest["dn2_clock"] + symbols["tx"] - symbols["dn2_clock"]
# Borrow only the helper's unused TX buffer in this isolated emulator probe.
# Replace the ISR continuation so the synthetic call never runs a stock RTE.
source = f""" .text
 .globl probe
probe:
 lea -48(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 move.w %sr,%d0
 move.l %d0,44(%sp)
"""
for i in range(8):
    source += f" move.l #0x1111000{i},%d{i}\n"
for i in range(7):
    source += f" movea.l #0x2222000{i},%a{i}\n"
source += f""" move.w #0x2715,%sr
 jsr 0x40025e36
 move.l 44(%sp),%d0
 move.w %d0,%sr
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea 48(%sp),%sp
 rts
 .org 0x200
continuation:
 lea -8(%sp),%sp
 movem.l %d0/%a0,(%sp)
 move.w %sr,%d0
 movea.l #{probe_base + 0x300:#x},%a0
 move.l %d0,(%a0)
 movem.l (%sp),%d0/%a0
 lea 8(%sp),%sp
 unlk %a6
 rts
"""
(out / "probe.s").write_text(source)
for cmd in [
    [cross + "as", "-mcpu=54455", "-o", str(out / "probe.o"), str(out / "probe.s")],
    [
        cross + "ld",
        f"-Ttext={probe_base:#x}",
        "-e",
        "probe",
        "-o",
        str(out / "probe.elf"),
        str(out / "probe.o"),
    ],
    [cross + "objcopy", "-O", "binary", str(out / "probe.elf"), str(out / "probe.bin")],
]:
    subprocess.run(cmd, check=True)
probe = (out / "probe.bin").read_bytes()
loc = {}
for line in subprocess.check_output(
    [cross + "nm", "-n", str(root / "out/digihealth.work/metrics-core.c.o")], text=True
).splitlines():
    parts = line.split()
    if len(parts) == 3:
        loc[parts[2]] = int(parts[0], 16)
base = manifest["dhm_idle_line"]
addr = {
    name: base + loc[name] - loc["dhm_idle_line"]
    for name in ("snapshot", "position", "blocks", "zero")
}
for kind in ["active", "omitted", "sr-negative"]:
    steps = [
        f"poke:{probe_base:#x}:{probe.hex()}",
        f"poke:{probe_base + 0x300:#x}:00000000",
        f"poke:0x40025e3e:4ef9{probe_base + 0x200:08x}",
        "poke:0x800053a4:00000064",
    ]
    for name, value in [("position", 1499), ("blocks", 1499), ("zero", 1499)]:
        steps.append(f"poke:{addr[name]:#x}:{value:08x}")
    if kind == "omitted":
        steps.append("poke:0x40025e36:4e56ff1448d73fff")
    if kind == "sr-negative":
        steps.append(f"poke:{manifest['dhm_block_hook'] + 24:#x}:4e71")
    steps += [
        "send:00",
        f"peek:{addr['snapshot']:#x}:56",
        f"peek:{probe_base + 0x300:#x}:4",
    ]
    cmd = [
        panel,
        firmware,
        "--base",
        "7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35",
        "--after",
        "10M",
        "--call-at",
        "0x4002e464",
        "--call-fn",
        f"{probe_base:#x}",
        "--regs-at",
        "0x40025e36,0x40025e3e",
        "--steps",
        ",".join(steps),
    ]
    p = subprocess.run(cmd, text=True, capture_output=True)
    (out / f"{kind}.json").write_text(p.stdout)
    (out / f"{kind}.stderr").write_text(p.stderr)
    if p.returncode:
        print(p.stdout)
        raise RuntimeError((kind, p.returncode))
    r = json.loads(p.stdout)
    before, after = r["regs"][-2:]
    assert before["d"] == after["d"]
    assert before["a"][:6] == after["a"][:6]
    sp = int(before["a"][7], 16)
    assert int(after["a"][6], 16) == sp - 4
    assert int(after["a"][7], 16) == sp - 240
    assert after["stack"] == before["d"][:4]
    sr = int(r["results"][-1]["hex"], 16) & 0xFFFF
    if kind == "sr-negative":
        assert sr != 0x2715, sr
    else:
        assert sr == 0x2715, hex(sr)
    snap = bytes.fromhex(r["results"][-2]["hex"])
    if kind == "omitted":
        assert snap == bytes(56)
    else:
        assert struct.unpack_from(">I", snap)[0] == 0x44484D31
        assert struct.unpack_from(">I", snap, 12)[0] == 1500
    print(kind, "PASS", "SR", hex(sr), "delta", sp - int(after["a"][7], 16))
