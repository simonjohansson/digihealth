/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DIGIHEALTH_DSP_PEEK_H
#define DIGIHEALTH_DSP_PEEK_H

/* DSP_PEEK 0x06 and DSP_PEEK_READ 0x07 (dsp-peek.c); 0 for any other command. */
int dsp_peek_receive(const unsigned char *packed, unsigned length, unsigned char *reply);

#endif
