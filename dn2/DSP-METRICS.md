# Optional DN2 SHARC callback counters

DigiHealth 1.5 adds a read-only callback-counter report for the optional
`dn2-master-mono32-l2-metrics-v1` Elekloader core. Build the measured L2 app
with `mods/core-dn2-metrics` and include this helper. Run the usual
`python tools/digiusb.py stats 10`; it probes the new command automatically.
No extra compiler, upload or inspection step is required in a mod project.
Ordinary L1/unmeasured L2 mods keep their existing core and report callback
timing unavailable. Existing HELLO, STATS, METRICS, remote keys and FRAME stay
compatible. The OLED retains its legacy timing display; new counters use USB.

The producer counts completed render calls, cumulative raw EMUCLK ticks and
the largest span since producer boot. It excludes init. The span includes
the wrapper's dispatch/frame/read overhead; it is not a bare kernel cycle
count, percent utilization or total DSP load. The host derives an average
from two coherent counter snapshots using unsigned differences; it does not
divide cumulative ticks by a wrapping 32-bit lifetime count. A new baseline
is required after detected resets/gaps or an impossible interval. Without a
boot epoch, a missed reboot whose counters overtake an old baseline cannot
always be detected. Maximum is explicitly since producer boot, not per second.

## Owned channel and stale data

The exact DN2 1.12 optional core claims `sharc:reply-header:2`; the linker also
infers the claim, so omitting it cannot evade a declared-owner conflict.
It writes one framed word into offset 8 of the selected reply page at the
qualified handler tail. Header 2 persists in stock; it is not cleared.
Known copied-header consumers exclude it, but an apparently unused raw-buffer
accessor exists at `0x400cfbe0`. It is preserved. This is a bounded exact-stock
contract, not a claim that the field is globally unread on every path/version.

Each frozen snapshot is eight uint32 words: `DHS1`, callback count, tick sum
high/low, maximum, freeze EMUCLK, producer flags (1), reserved (0). Seventeen
frames carry its 16 big-endian halfwords and CRC16-CCITT (initial `0xffff`).
A frame is `0xd6000000 | (sequence_mod8 << 21) | (index << 16) | halfword`.
The SHARC store uses the same halfword rotation as the stock handler counter.
One IRQ writer reads the previous completed ColdFire reply copy; it accepts
only a complete same-sequence, ordered, CRC-valid snapshot with known fields.

Identical repeated words cannot advance assembly. They cannot restart an
expired partial snapshot, and replaying an identical complete snapshot cannot
renew freshness. Loss, changed sequence, invalid index/tag and CRC errors
cannot publish partial data; a subsequent valid index-0 packet recovers.
The last complete snapshot is fresh for at most **64 advancing ColdFire block
interrupts**. This domain does not age if that interrupt stops; a static read
alone is not host-time or whole-device liveness. Qualification must verify
advancing CF and callback counters. No new timer hook is used.

## USB report

Canonical `DSP_METRICS` command `0x05` has no arguments. Payload is exactly
64 bytes, big-endian. Unsupported older helpers refuse it and the client
keeps the existing statistics path.

| Offset | Type | Meaning |
|---:|---|---|
| 0 | u32 | Magic `0x44484331` (`DHC1`) |
| 4 / 6 | u16 / u16 | Layout 1 / payload bytes 64 |
| 8 | u32 | Flags: 1 fresh in CF-block domain, 2 complete snapshot seen |
| 12 / 16 | u32 / u32 | CF blocks at publication / current CF blocks |
| 20 | u32 | Packet sequence, 0..7 |
| 24 | u32 | Cumulative completed render count, modulo 2^32 |
| 28 / 32 | u32 / u32 | Cumulative tick sum high / low, modulo 2^64 |
| 36 / 40 | u32 / u32 | Maximum raw span / snapshot EMUCLK |
| 44 | u32 | Producer flags, exactly 1 for this producer |
| 48 / 52 / 56 | u32 | Accepted snapshots / CRC errors / dropped partial or invalid snapshots |
| 60 | u32 | Reserved, zero |

Before a complete packet, flags and result fields are zero (current CF/error
counters may advance). Stale data retains its raw counters with fresh clear;
the client prints unavailable. It rejects malformed layouts/flags/age and
interval averages above the producer's maximum. It never converts ticks to
microseconds or percentages without a separately qualified physical clock.

## Checks and physical boundary

The producer stays inside the existing 920-byte L1 gap: 628 linked code bytes
plus padding/guard in 768 bytes, and 76 actual state bytes within 152 bytes.
The 48-byte keyed pitch table is retained, followed by 56 zero bytes. L2 stays
32 KiB; no new memory grant. The wrapper adds eight stack bytes: measured core
124 + app at most 420 = existing gross 544. Ordinary core 116/app428 stays
unchanged. Declared stack limits are not observed peak stack or free DSP RAM.

Actual C and ASM coupled runs each pass 16 coherent advancing USB snapshots,
zero CRC/dropped snapshots and preserved code. Their 58,432 stereo sample
frames match exactly, with 0.125 peak and silent initial/final sections.
Remote capabilities, FRAME and legacy heap reporting still work. A separate
unmeasured-core control remains unavailable while CF blocks advance. The
actual compiled ColdFire decoder passes complete, missing, frozen, replayed,
expired-index0, CRC, torn-halfword and lost-index cases. Host tests also cover
sequence changes, reset recovery, wrap, canonical requests and malformed
replies. The old compiled router/register/disabled-input/all-key checks pass;
an initial report-directory harness error was corrected and rerun.

The added IRQ call chain uses at most 72 transient bytes in this compiled
build: 20 trampoline + 4 call return + 16 metrics frame + 8 arguments +
4 nested return + 20 receiver frame. This remains inside the stock prologue's
240-byte envelope, leaving 168 bytes of that envelope; it is not a whole-OS
interrupt nesting margin. Compiled SR restoration and omitted-hook/SR-restore
negative controls pass. Hardware overhead is not inferred from these sizes.

Physical callback clock/read overhead, matching measured C/ASM project/FX
and audio checks remain parent-owned acceptance gates. The physically checked
1.4 relative-CPU/raw-handler results do not qualify this new SHARC producer.
Total DSP idle/busy, physical peak stack and live DSP heap remain unavailable.
[Issue #11](https://github.com/simonjohansson/digihealth/issues/11) stays open.
