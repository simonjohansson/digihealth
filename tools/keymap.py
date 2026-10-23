# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared logical names and device maps from the firmware's X-macro table."""
import csv
from pathlib import Path

KEYS = {}
MAPS = {1: {}, 2: {}}
for line in (Path(__file__).resolve().parents[1] / 'keys.def').read_text().splitlines():
    if not line.startswith('KEY('):
        continue
    fields = next(csv.reader([line[4:-1]], skipinitialspace=True))
    number, name = int(fields[0]), fields[1]
    if number != len(KEYS) + 1 or name in KEYS or len(fields) != 8:
        raise ValueError('invalid shared key definition')
    KEYS[name] = number
    for product, offset in ((1, 2), (2, 5)):
        code, group, mask = (int(value, 0) for value in fields[offset:offset + 3])
        if code:
            MAPS[product][name] = (code, group, mask)

MAPS[3] = {}
DN2_IDS = {}
for line in (Path(__file__).resolve().parents[1] / 'dn2/keys.def').read_text().splitlines():
    if not line.startswith('KEY('):
        continue
    fields = next(csv.reader([line[4:-1]], skipinitialspace=True))
    number, name, code, group, mask = fields
    number, code, group, mask = (int(v, 0) for v in (number, code, group, mask))
    if name in DN2_IDS or number in DN2_IDS.values() or not 1 <= number <= 64:
        raise ValueError('invalid DN2 key definition')
    DN2_IDS[name] = number
    MAPS[3][name] = (code, group, mask)

SUPPORTED = {product: sum(1 << ((DN2_IDS if product == 3 else KEYS)[name] - 1) for name in mapping)
             for product, mapping in MAPS.items()}
