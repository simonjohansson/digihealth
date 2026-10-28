| SPDX-License-Identifier: GPL-2.0-or-later
| Digitone II OS 1.12; see dn2/README.md for stock qualification.
.equ STR_CTOR, 0x401ceab8
.equ INVALIDATE, 0x4011ca9a
.equ BLIT, 0x40115adc
.equ FILLRECT, 0x40114b22
.equ FRAMERECT, 0x40114906
.equ TEXTF, 0x401156f8
.equ FONT5, 0x40294710
.equ LOCK, 0x40001608
.equ UNLOCK, 0x4000172a
.equ HEAPMTX, 0x445e2e40
.equ HEAPCB, 0x4029f0dc
.equ SYSEX_SEND, fw_sysex_send
| No render/idle timing claim: DTIM0 stays stopped and SHARC is untouched.
.equ DTCN0, dn2_clock
.equ CUR_TCB, 0x4664bcdc
.equ IDLE_TCB, 0
.equ IDLE_PC, 0
.equ SYSEX_A3, 0x40207f9e

.globl fw_dn2_fillrect, fw_dn2_framerect
.set fw_dn2_fillrect, FILLRECT
.set fw_dn2_framerect, FRAMERECT
