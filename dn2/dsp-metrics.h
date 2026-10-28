/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DN2_DSP_METRICS_H
#define DN2_DSP_METRICS_H

enum { DHC_MAGIC = 0x44484331u, DHC_VERSION = 1, DHC_WORDS = 16,
       DHC_BYTES = 4 * DHC_WORDS, DHC_FRESH_BLOCKS = 64 };
enum { DHC_FRESH = 1, DHC_SEEN = 2 };
void dhs_block(unsigned word, unsigned cf_blocks);
void dhs_read(unsigned out[DHC_WORDS]);
int dhs_receive(const unsigned char *packed, unsigned length, unsigned char *reply);

#endif
