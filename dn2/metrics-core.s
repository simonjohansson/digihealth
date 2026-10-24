| SPDX-License-Identifier: GPL-2.0-or-later
| DN2 OS 1.12's finite, core-shaped idle/block producer. It owns exactly
| the two sites in mod.json; no timer, SHARC code or reply word is changed.
        .section .run, "ax"
        .balign 2
        .globl dhm_idle_hook, dhm_block_hook, dhm_reply
        .set dhm_reply, DHM_REPLY

dhm_idle_hook:
        jsr DHM_CREATE_MAIN              | original call, with its original stack
1:      addq.l #1, dhm_idle_line         | replaces the stock post-call BRA *
        bra.s 1b

dhm_block_hook:
        lea -20(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.w %sr, %d0
        move.l %d0, 16(%sp)
        jsr dhm_block
        move.l 16(%sp), %d0
        move.w %d0, %sr
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea 20(%sp), %sp
        link.w %a6, #-236               | exact displaced eight-byte prologue
        movem.l %d0-%d7/%a0-%a5, (%sp)
        jmp DHM_BLOCK_CONTINUE
