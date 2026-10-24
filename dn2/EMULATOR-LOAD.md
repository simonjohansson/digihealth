# DN2 C/ASM load comparison in DigiKit

On 24 October 2026, three alternating C/ASM pairs ran the unchanged external
L2 sine firmwares through DigiKit's existing coupled emulator. Both programs
produced identical audio. ASM used about 1,175 fewer modeled busy instructions
per held-note block, a small change in the complete stock-plus-mod workload.
This is emulator evidence; it does not measure the physical SHARC clock,
cycles, DSP headroom or the new callback producer proposed in #11.

## Existing tools and definitions

The run used `Emu`/`status.load`, `pk_dsp_budget.busy_per_block` and
`load_pct`, and the existing `spikes` report. Its alternating order and host
thread-CPU-per-audio-second comparison follow `coupled_ab`. No profiler or
native binary was rebuilt. The relevant client, `load.rs`, `coupled_ab` and
`spikes` source files are byte-identical between the runtime source pin below
and upstream `bb96348b06ca106dcdd11b4c81e7076f3d253bb6`.

- `status.load` exists in this binary. It closes windows at least one emulated
  second long and blends new results 50/50; its first DSP window may be null.
  It is useful for live feedback, but its smoothed values are not independent
  per-condition measurements.
- The table uses unsmoothed counter deltas with the existing budget helper:
  `(instructions - idle_skip) / audio_blocks`. Model percent assumes one
  instruction/cycle and 1 GHz / 1,500 blocks/s.
- The stock-mix estimates multiply that model by DigiKit's DN2 nominal factor
  1.138261 or high factor 1.326075. The factors come from a manual-based stock
  instruction-mix model. Applying them to new code is an assumption, not a
  measured speed or a guaranteed upper bound.
- Host CPU is DSP worker thread CPU seconds per emulated audio second on this
  Mac. It measures emulator cost. ColdFire/controller CPU and wall time are
  recorded separately; neither is physical-device utilization.

Sources: [load arithmetic](https://github.com/ElekLabs/digikit/blob/bb96348b06ca106dcdd11b4c81e7076f3d253bb6/packages/emulator/control/src/load.rs),
[budget helper](https://github.com/ElekLabs/digikit/blob/bb96348b06ca106dcdd11b4c81e7076f3d253bb6/tools/patchkit/pk_dsp_budget.py),
[paired host comparison](https://github.com/ElekLabs/digikit/blob/bb96348b06ca106dcdd11b4c81e7076f3d253bb6/tools/devtools/coupled_ab.py),
[stall report](https://github.com/ElekLabs/digikit/blob/bb96348b06ca106dcdd11b4c81e7076f3d253bb6/tools/devtools/spikes.py).

## Equal workloads and results

Each run starts a fresh process and cold-loads one exact firmware, verifies
installed app bytes and both callback bindings, warms for 1,500 frames, then
measures silent and held MIDI note 69 windows of 1,500 requested blocks each.
There are 300 settling blocks after note-on. Execution order is C/ASM,
ASM/C, C/ASM. The existing benchmark lock is held exclusively. Code remains
byte-exact afterward, app state changes during the note, and every capture
has equal stereo channels and the expected zero or 0.125 peak.

Medians of three runs per cell:

| Workload | Program | Busy instructions/block | Model % | Stock-factor estimate nominal/high % | Host DSP CPU/audio s |
|---|---|---:|---:|---:|---:|
| Silent | C | 337,640.745 | 50.6461 | 57.6485 / 67.1605 | 20.1032 |
| Silent | ASM | 336,483.756 | 50.4726 | 57.4510 / 66.9304 | 20.0060 |
| Note 69 | C | 337,658.760 | 50.6488 | 57.6516 / 67.1641 | 20.1404 |
| Note 69 | ASM | 336,483.848 | 50.4726 | 57.4510 / 66.9304 | 19.9999 |

Held-note ASM/C host CPU ratios are 0.9843, 0.9894 and 0.9935. That small
host difference is not a hardware speedup measurement or a statistical
confidence interval. The modeled whole-workload instruction reduction is
0.348%; this does not mean the ASM kernel alone is only 0.348% cheaper.
The entry wrappers continue rendering while their gain is zero, so silent
output does not imply the app executes no DSP instructions.

All six runs pass: zero missing blocks, traps and code mismatches. The first
48,000 stereo sample frames match exactly across all runs of each condition:

- Silent PCM SHA-256: `f1c0c5c01066641d72000fb5482f94fef207768ace595b78e6969dffd9bb57ba`.
- Note PCM SHA-256: `8ea8ce7b51fd6d0ecca27a5e43bfd966ef2ea2fe29ba731b569ca18952007905`.

Host load average ranged 2.37–4.78. The fast tier builds one additional region
inside each silent window (21→22), so those host timings include that cost;
held-note windows remain at 22. The generic binary uses its fast tier and
interpreter, with zero AOT block instructions. `spikes` attributes the slow
headless generation to DSP emulation: roughly 20 host CPU seconds per audio
second. With no sound-card sink, its behind-real-time windows are host-speed
observations; they do not establish physical-device underruns.

## Reproduction identity and limits

Runtime source: `ded547e14e63977c1a6e808812d46243e13c43d0` (PX-fixed tree).
Existing `digi-emud` SHA-256:
`1058f5eb8c2cc5e148140960933ec1e9fdfc26fa71a3285a1ead93a083bb5156`.
Python 3.12.13 was selected through mise. Inputs are the same owner-supplied
DN2 1.12 stock and ready session as previous C/ASM checks. Both firmware
builds retain DigiHealth **1.3** and Elekloader `14e55c6`; this comparison does
not test the separately qualified 1.4 hooks or change an app/source file.

Firmware hashes are C
`63d17ffed02ddc4b141adaa1cbca9f80a7cd98ac7571cbb64fd439172bc477c9`
and ASM
`d93516ef54b9b6fcec9771852325d0c59eaf46ef09287458bf36549aff87bd2b`.
Private reports retain each before/after status, PCM, spike records, source
hashes and input identities under `out/digikit-load-pairs/`; no firmware or
capture is committed. An initial local-socket permission refusal ran no
comparison; the separate successful run contains all six pairs.

The emulator tools already answer modeled utilization and host cost. Actual
callback cycles still need the bounded producer, owned transport and physical
clock/overhead qualification tracked in
[#11](https://github.com/simonjohansson/digihealth/issues/11). Total DSP idle/busy
and physical peak stack remain separate work. These figures must not replace
DigiHealth's unavailable labels on hardware.
