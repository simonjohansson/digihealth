# Digitone II OS 1.12

Experimental DigiHealth 1.5 with core-dn2 0.1. No FAST AUDIO, SRAM timer or
SHARC code changes. `tools/digiusb.py stats` now also reports relative CPU
activity, raw SHARC handler spans and the largest free ColdFire heap block.
[Measurement definitions, protocol and limits](METRICS.md) describe the exact
scope. Total DSP utilization, callback timing and peak stack are unavailable.
SYSTEM INFO and the legacy STATS timing-valid flag remain unavailable; the
relative CPU/raw handler figures use a separate read-only METRICS command.

Two isolated ColdFire hooks count idle-loop iterations and block interrupts;
the remaining functionality subscribes to core events. The generic producer
is kept in `metrics-core.c` / `metrics-core.s` for later core contribution.
The two SETTINGS rows, SYSTEM INFO and REMOTE KEYS, retain their behavior.
REMOTE KEYS is on at boot; turning it off refuses input and releases owned
keys while METRICS and the existing diagnostics still answer. DN2 advertises
input revision 3, product 3, OS 1.12; the mk1 firmware and input protocol are
unchanged. The new hooks passed a bounded physical producer/readback and
six-note audio check; see the measurement evidence and remaining limits.

## Build

Use an Elekloader checkout of `sharc`, m68k binutils/GCC and
your own pinned stock OS 1.12.
Its SHA-256 is
`7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35`.
No firmware or generated `.elemod`/map belongs in Git.

```sh
ELEKLOADER_CROSS=m68k-elf- PYTHONPATH=/path/to/elekloader python build.py --stock /path/to/Digitone_II_OS1.12.syx
python -m elekloader.sdk.build /path/to/elekloader/mods/core-dn2 --stock /path/to/Digitone_II_OS1.12.syx
python -m elekloader.lint out/digihealth-1.5.elemod --stock /path/to/Digitone_II_OS1.12.syx --with /path/to/core-0.1.elemod --json
```

Use the selected mise Python runtime for those commands. Link core,
DigiHealth and (for the showcase) Elekloader's `examples/hooks-check-dn2`.
Keep the resulting firmware and exact link manifest together locally.

**Showcase warning:** hooks-check draws five bars over every screen, erasing
parts of the stock UI. This is intentional diagnostic drawing and can look
like tearing. Its PERSONALIZE test also consumes TEMPO until reboot. Omit
hooks-check from a normal DigiHealth build.

## Remote input and readback

```sh
python tools/digiusb.py keys 'SETTINGS,DOWN,NO'
python tools/digiusb.py turn A -3
python tools/digiusb.py turn LEVEL 1
python tools/digiusb.py screen screen.pbm
python tools/dn2_check.py exact-link-manifest.json captures/
```

Buttons use the DN2 names in `keys.def`; `SYN`, `FX`, `MOD`, `PRESET`,
`KEYBOARD`, `ARP`, `PLUS`, `MINUS` and `NOTE_EDIT` are device-specific.
The dedicated input bridge invokes the stock driver, not arbitrary UI
functions from the MIDI receiver. A turn is one bounded impulse, -30..30
nonzero detents, with the same session, operation, duplicate/status and
no-replay handling as buttons. Holds still expire and preserve physical
ownership. Deadlines run only when the UI task can service them.

FRAME is read-only. The draw subscriber copies the composed 128x64 Bitmap
under the same short interrupt lock used by the reader. A request asks for
a fresh draw after the UI queue drains; the client waits for a new frame
generation and refuses stale frames on timeout. Bitmap width/height/stride
are checked before capture. PEEK retains its existing DDR/SRAM-only range.

The showcase checks independent counters and screenshots for all six UI
events, menu callbacks after reopening, ordered subscribers and consumed
versus pass-through TEMPO. It changes parameters/UI and arms TEMPO
consumption until reboot. Review the saved menus and the stock parameter
changes as well as the automatic assertions. It is a functional check,
not an audio-quality or long-term stability claim.

## Stock qualification

- Core owns the panel prologue, periodic counter and SysEx observer sites;
  see core-dn2's README and `tests/test_digitone2.py` for byte/ABI checks.
- The main buddy heap is `0x4029f0dc`, with mutex `0x445e2e40`, derived
  from the allocator at `0x401202c8`. Its base/list/order layout matches the established
  bounded walk; stock-image and emulator checks qualify this port.
- The existing Bitmap routines were matched by their instruction bodies
  and verified by the compiled overlay/menu run: invalidate `0x4011ca9a`,
  blit `0x40115adc`, fill `0x40114b22`, frame `0x40114906`, formatted text
  `0x401156f8`. Font 5 at `0x40294710` has matching glyph widths/data and
  its own relocated pointer header. String construction is `0x401ceab8`.
- Button group positions follow the stock decoder table at `0x401f3dec`;
  raw groups 0..6 only. Encoder indices 0..8 map to UI codes 1..9 through
  `0x401f3c10`. The factory label table is `0x401f3c34`. Some factory
  strings retain older names (SRC, STACK, MINUS); the client names follow
  the current DN2 panel and emulator-observed behaviour.

## Validation

The Rust `sysex_bridge` test uses the real stock router at `0x4012194e`
from the UI loop and captures the stock sender `0x401236d2`. It models
neither USB endpoints nor SHARC audio. Run `tests/test_dn2_firmware.py`
with the variables in its docstring after building this checkout and its
core companion. The tests and captures are separate from physical evidence.
The emulator checks include all 54 button positions against stock key state
and event IDs, all nine encoder routes, disabled-input refusal with diagnostics
still available, and preserved SysEx router registers for both USB sources
and both refused DIN sources. Existing host key tests pass. For Digitakt
1.53/1.54 and Digitone 1.44, the compiled sections, symbols, relocations and
contracts are identical to the original checkout; source-provenance metadata
differs as expected. Core alone matches stock in nine scripted screen captures.
On 23 Oct 2026 the DS03 showcase flashed over USB and rebooted after the
user pressed YES. Fresh device info reported DS03; HELLO and revision-3
capabilities responded. Read-only comparison of all 7,204 immutable runtime
bytes matched the exact linked candidate. Three clock comparisons differed
from the host by at most 0.3%. The physical functional check passed all six
UI events, encoder delivery, SETTINGS/PERSONALIZE callbacks after reopening,
subscriber ordering and consumed versus pass-through TEMPO. Saved screens
were reviewed independently of input acknowledgements. Longer project/audio
acceptance remains separate; no SHARC/audio-quality claim is made.

The follow-up DH03 build (core + DigiHealth only, no hooks-check) was
installed with remote YES after verifying the update dialog. Its version
and all 6,620 immutable runtime bytes matched. The clean UI, normal TEMPO,
encoder input, automatic 120 ms hold expiry and SYSTEM INFO on/off were
verified with fresh screens, stock key-state reads and published STATS.
Lease expiry closes that input session; open a new one for subsequent
actions. STATS publishes once a second, so poll for the new flag after a
toggle rather than treating the previous snapshot as a failed toggle.
Candidate identities and remaining qualification work are recorded in the
[DN2 PR preparation issue](https://github.com/simonjohansson/elekloader/issues/27).

Optional measured L2 apps use the sibling `core-dn2-metrics` and the new
[raw callback counters](DSP-METRICS.md). Ordinary L1/unmeasured L2 builds
keep their existing core. Physical 1.4 CPU/raw-handler evidence is separate
from the new 1.5 callback producer's pending physical qualification.
