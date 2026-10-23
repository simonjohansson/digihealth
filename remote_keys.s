| SPDX-License-Identifier: GPL-2.0-or-later
        .section .run, "ax"
        .globl rk_now
rk_now:
        .ifdef DN2
        jmp core_millis
        .else
        move.l  KEY_CLOCK, %d0
        .endif
        rts
