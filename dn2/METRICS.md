# DN2 metrics, version 1

DigiHealth 1.4 adds two ColdFire hooks on exact Digitone II OS 1.12 and a
read-only `METRICS` command. Run the usual `python tools/digiusb.py stats 10`.
The client detects this capability; older helpers refuse the new command
and retain their legacy STATS path. Remote buttons, encoders, FRAME, protocol
1 HELLO/STATS/PEEK and the 96-byte STATS layout are unchanged. METRICS is
available even with REMOTE KEYS off. No timer is started or reconfigured.

## What is measured

- **CPU relative to the best idle window:** iterations of an isolated idle
  increment/branch loop during each 1,500 ColdFire block interrupts. The
  first window is excluded from calibration; the highest later count is
  the reference. The figure becomes available from the third closed window
  when that reference is nonzero. `1 - idle_window / idle_reference` measures
  task activity relative to the best observed idle opportunity in this boot,
  excluding the interrupt baseline. The reference may improve later and a
  busy boot can give a biased reference. This is not absolute CPU utilization
  or a calibrated measure of all interrupt time. The counting loop itself
  consumes otherwise idle time and changes its memory/cache traffic.
- **Raw SHARC handler span:** the previous completed reply copy's first word,
  sampled at block-interrupt entry; 64-bit sum, maximum, nonzero sample count
  and zero count for the window. This is the firmware's EMUCLK span around
  a command handler. It is not total DSP load, callback cost, a DSP-completed
  block counter or a calibrated percentage. A frozen reply can repeat a span;
  continuing ColdFire interrupts alone do not prove continuing SHARC work.
- **ColdFire heap:** the existing locked buddy-heap walk supplies free bytes,
  largest observed free block, per-order counts and walk faults. A nonzero
  fault count means the walk is incomplete/unqualified. This covers one
  allocator, not all RAM, static buffers, stack or SHARC memory.

A window is approximately one second only while the expected 48 kHz /
32-sample stream supplies 1,500 block interrupts per second. The raw block
count is published so a physical test can calibrate that assumption against
host time. No CPU/DSP clock frequency is inferred by this client. Window
counts/idle totals wrap unsigned; idle deltas and the 64-bit span sum retain
wrap behavior explicitly. Snapshot reads mask interrupts with the same
core lock used by the existing diagnostics; no mixed-window counter copy.
The old STATS heap snapshot has its own generation, so its publication need
not coincide with a METRICS window.

Total DSP idle/busy load, calibrated callback cost, hardware cycle margin,
live SHARC heap and physical peak stack remain **unavailable**. Build-time
code/data capacities and declared stack limits are separate static facts.
They are not reported as runtime free DSP memory.

## Core-shaped hook ownership

`metrics-core.c` holds the counter/publication logic; `metrics-core.s` holds
only the two finite stock adapters, with addresses in `mod.json`:

| Site | Original bytes | Adapter |
|---|---|---|
| `0x400cf24e` | `4eb94002e8d0` | Make the original call to `0x4002e8d0`, then count in place of the original post-call idle spin at `0x400cf246`. |
| `0x40025e36` | `4e56ff1448d73fff` | Save volatile D0/D1/A0/A1 and SR, collect the raw window, restore, replay `link.w a6,#-236; movem.l d0-d7/a0-a5,(sp)`, continue at `0x40025e3e`. |

The reply literal at `0x40025e8c` points to `0x800053a4`; the producer only
reads it. No reply/effect-audio word, SHARC instruction, pinned app bridge,
app reservation or core API changes. Idle data occupies a dedicated aligned
16-byte cache line. These stock sites are owned exclusively by DigiHealth;
Elekloader refuses another mod that claims either. They are reusable core
candidates rather than hidden private patches; a later core contribution can
move these isolated files and give all mods one owner for the sites.

## Wire format

Request `0x04 METRICS` has no arguments and must have the exact canonical
three-byte decoded request (`u16 sequence, u8 command`). Successful reply
payload is exactly 56 bytes, big-endian:

| Offset | Type | Meaning |
|---:|---|---|
| 0 | u32 | Magic `0x44484d31` (`DHM1`) |
| 4 | u16 | Layout version 1 |
| 6 | u16 | Payload bytes, 56 |
| 8 | u32 | Flags: 1 closed window; 2 relative CPU reference available; 4 nonzero handler samples available |
| 12 | u32 | ColdFire block interrupts at this window's close |
| 16 | u32 | Closed-window count |
| 20 | u32 | Interrupts per window, 1,500 |
| 24 | u32 | Idle-loop total at close |
| 28 | u32 | This window's idle delta |
| 32 | u32 | Best idle delta, excluding the first window |
| 36 / 40 | u32 / u32 | Raw handler-span sum, high / low halves |
| 44 | u32 | Largest raw handler span |
| 48 | u32 | Nonzero handler samples |
| 52 | u32 | Zero samples |

Before the first completed window the header/window size is valid and all
flags/results are zero. The reader refuses unknown versions, lengths, flags
and inconsistent sample/reference combinations. METRICS is a known read, so
lost replies may be retried; actions keep their existing no-replay behavior.
A successful command and a plausible number do not establish physical timing
accuracy or memory ownership.

## Evidence and next measurement

Stock SHA-256:
`7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35`.
The two hook sites and reply literal were independently extracted from that
owner-supplied image and disassembled before use. Synthetic tests compile
and execute the actual C producer for zero and large spans, sum carry, idle
and block wrap, first/reference windows, partial-window nonpublication and
canonical/refused requests. They do not measure hardware performance.

[DigiKit's health investigation](https://github.com/ElekLabs/digikit/blob/38dfbe4ae88263511eed95691c07fc07e17b6f26/docs/findings/41-digikit-health.md)
supplies the two hook leads and explains the relative idle reference.
[The independent load investigation](https://github.com/angellinares/dn2_firmware_explore/blob/39815895720b84c59ce2fa0ff5b13bd47dc415d2/docs/sharc-load.md)
rejects the raw handler word as whole-DSP load. Its separately added idle
meter has threshold/interrupt and torn-read limitations; its 1.11 addresses
and reply scratch are not imported here.

[Issue #10](https://github.com/simonjohansson/digihealth/issues/10) tracks this
increment and remaining calibration. An owned coherent DSP-to-ColdFire
transport plus exact SHARC callback/idle hooks is the next measurement step;
it must coexist with the current exclusive C/ASM app and preserve stock
reply/effect audio. The first 1.4 ColdFire hooks have the bounded physical
qualification below; they do not qualify a new SHARC producer.


## First implementation checks

The exact-stock module builds and lints with core-dn2 0.1 and the existing C
L2 sine without overlap. The combined decoded update is 1,933,848 bytes,
leaving 163,304 bytes below the measured 2 MiB cap. The helper itself has
6,176 code and 3,760 BSS bytes with the tested m68k-elf GCC 16.2.0 build.

The compiled block producer is a leaf with a 16-byte C frame/save. Together
with the 20-byte trampoline and four-byte call return, its transient depth
is 40 bytes, inside the original handler's 240-byte prologue envelope. This
bounds this hook's added stack demand, not every interrupt nesting or whole
OS stack margin. No hardware cycle-overhead bound is claimed.

Nine targeted host/compiled-firmware tests pass, including real SysEx router
register ABI, remote-input disabled behavior with METRICS still available,
all 54 buttons and nine encoder routes, and the synthetic producer cases.
The compiled hook probe seeds D/A registers and SR, executes the actual
helper, verifies the exact original frame and restored SR, and detects both
an omitted hook and a deliberately omitted SR restore. It substitutes a
bounded emulator-only continuation instead of running a synthetic frame
through the stock ISR's RTE; this is an ABI check, not real interrupt timing.
The independent legacy-client fallback test also passes. The full host suite
runs 50 tests with seven missing-input skips (43 pass); the client self-test
passes. The initial compiled-test run had a missing report directory; after
creating it, all nine targeted tests ran cleanly on the exact candidate.

Private reports, firmware candidates, disassembly and emulator probes stay
under `out/`. None is committed. The initial implementation checks preceded the separate physical results below;
the earlier port's 1.3 physical results alone did not qualify these hooks.


## Bounded physical producer/readback check

On 24 October 2026 the parent task installed the exact C-L2 candidate above,
then independently verified device version `HC14`, helper `digihealth 1.4`,
remote buttons and a fresh FRAME. All 7,512 immutable ColdFire runtime bytes
matched the linked candidate, SHA-256
`05f65ad9a5b0471654a0703919cb8c4c7cb6e665c57b42866fdf4be89b0e5a22`.
No device operation was performed by the implementation subagent.

Forty coherent METRICS/STATS snapshots and separate live ColdFire block
counter reads covered 10.3728846 host seconds. Windows 58 through 68 were
observed, each with 1,500 nonzero raw handler samples and no zero samples.
The observed live-counter slope was 1,500.01 block interrupts per host second.
This supports the intended window cadence; it is not a SHARC clock/cycle
calibration. Relative CPU ranged from 26.646% to 31.143% against the rolling
best observed idle reference. Raw handler averages ranged from 423,934.138
to 424,396.917 ticks. None of these is absolute CPU or total DSP utilization.

Heap walks had zero faults, with 30,706,624 free bytes and a largest free
block of 16 MiB in that workload. Three readings through the ordinary
`digiusb.py stats` client displayed those fields and unavailable metrics as
specified. This is one allocator, not general free RAM or DSP memory.

A separate six-note C-L2 audio regression then passed: 18.005333 seconds,
864,256 stereo frames, 1,688 host capture buffers and zero dropped buffers.
MIDI notes 48/60/69/72/81/84 followed the external example's deliberate
one-octave phase change. Channels were identical, peak was 0.17857146, the
final second was silent, and maximum pitch error was 0.081284 cent at nominal
48 kHz. The capture clock was not independently calibrated. Capture SHA-256:
`ceda000fcbf2181c7ab75d67db34fa212470cdaf5a3cf9ff9e926b7fe3fc5845`;
PCM SHA-256:
`583981781e170dc6a9c57417a15f594810a5f8085fa02e024a6dd90f20f7e810`.

Private physical evidence:
`/Users/simonjohansson/src/elekloader-sharc/out/digihealth14-20261024/`,
including `physical-metrics-report.json`, `HC14-physical-report.json`, client
output, readback and capture logs. These results do not measure added IRQ
cycle/cache overhead, whole-OS interrupt margin, total DSP load, callback
cost, peak stack, broader stock-project stress or a calibrated C/ASM speed
comparison. [Issue #11](https://github.com/simonjohansson/digihealth/issues/11)
tracks the next owned SHARC producer/transport slice.


## Callback timing feasibility before integration

[Issue #11](https://github.com/simonjohansson/digihealth/issues/11) owns the
next small slice. An isolated offline prototype, compiled with Selache
`2b26d3b75c53063575bc5c820fa0d38879335187`, fits its render wrapper, frozen
snapshot serializer and exact-stock tail adapter in **628 code bytes and
76 state bytes**. The proposed L2-only layout allows 704 linked code bytes
plus a 64-byte guard and 152 state bytes inside the existing L1 ownership;
it preserves the 52-byte pitch table and grants no additional RAM. A direct
C prototype did not fit and was refused; the budget was not enlarged. This
is a feasibility result, not an accepted Elekloader ABI or installed feature.

The wrapper adds an eight-byte call frame. Keep the current gross borrowed
stack ceiling at 544 bytes: 116 bridge + 8 measurement + at most **420 app**.
An otherwise valid app declaring 428 bytes must be refused when measured.
Existing unmeasured/L1 contracts keep their present limit. A later integration
needs matching Python/TypeScript checks and both boundary tests; the private
prototype has only checked that arithmetic and actual fixture depth.

Actual unchanged external C and ASM L2 renders were compared with direct
calls for eight blocks each. Output and app state match exactly, output
guards remain intact, and the write watch detects no code writes. Synthetic
caller-inclusive maximum depths change from 108 to 116 bytes for C and 52
to 60 bytes for ASM. Those depths establish the wrapper overhead in these
fixtures; they are not physical peak-stack observations.

The exact OS 1.12 tail at PC16 `0x1c9e5f` has live reply pointer I4 and
SISD MODE1 `0x39011cf8` in captured idle and genuinely sounding contexts.
Both contexts, plus hostile unrelated modifiers/circular settings, preserve
I4, live registers, flags, active/inactive banks and the circular stock
stack over 17 serialized words; the adapter performs no stack writes. The
stock continuation restores I2/I5/R10/R11/R13/R14/R15 before using them,
which permits this adapter's narrow scratch set. The runner is binary32;
this is not arbitrary-mode or full 40-bit arithmetic execution proof.

The proposed reply header word 2 remains **unqualified for ownership**.
Exact stock direct base literals and the parameter reader were checked:
its valid field/sample offsets begin after the header. That does not exclude
indirect consumers, aliases, other projects or FX paths. A tagged 17-word
sequence with a frozen snapshot and CRC16 works offline; receiver loss,
duplicate, restart, torn-read and CRC refusal tests, normal build integration,
physical timebase/overhead calibration and audio regression remain required.
No SHARC telemetry code is installed by DigiHealth 1.4. Total DSP idle/busy
and bounded physical stack high-water are subsequent, separate measurements.

The separate [paired DigiKit C/ASM load comparison](EMULATOR-LOAD.md) uses
existing emulator tools. Its modeled load and host CPU costs are not physical
DSP timing. The user has now approved bounded L2 callback integration; actual
channel qualification and mirrored validation remain its installation gates.
