/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DN2_METRICS_CORE_H
#define DN2_METRICS_CORE_H

enum { DHM_MAGIC = 0x44484d31u, DHM_VERSION = 1, DHM_WORDS = 14,
       DHM_BYTES = 4 * DHM_WORDS, DHM_WINDOW = 1500 };
enum { DHM_CLOSED = 1, DHM_CPU_RELATIVE = 2, DHM_HANDLER = 4 };
extern volatile unsigned dhm_idle_line[4];
void dhm_block(void);
void dhm_read(unsigned out[DHM_WORDS]);
int dhm_receive(const unsigned char *packed, unsigned length, unsigned char *reply);

#endif
