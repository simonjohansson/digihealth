/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "metrics-core.h"

extern volatile const unsigned dhm_reply[];
extern unsigned core_keys_lock(void);
extern void core_keys_unlock(unsigned sr);

/* Keep the idle store on a data-only cache line, separate from hook code. */
volatile unsigned dhm_idle_line[4] __attribute__((aligned(16)));
static unsigned blocks, windows, position, idle_at, reference;
static unsigned sum_hi, sum_lo, maximum, samples, zero;
static volatile unsigned snapshot[DHM_WORDS] __attribute__((aligned(16)));

/* The block interrupt is the sole writer. Its reply word is a raw handler
 * span from the previous completed transfer, not total SHARC busy time. */
void dhm_block(void)
{
    unsigned value = dhm_reply[0], old, idle, delta, flags;
    ++blocks;
    if (value) {
        old = sum_lo;
        sum_lo += value;
        sum_hi += sum_lo < old;
        if (value > maximum) maximum = value;
        ++samples;
    } else {
        ++zero;
    }
    if (++position != DHM_WINDOW) return;
    idle = dhm_idle_line[0];
    delta = idle - idle_at;
    idle_at = idle;
    ++windows;
    /* The first window may start before the idle loop; never calibrate on it. */
    if (windows >= 2 && delta > reference) reference = delta;
    flags = DHM_CLOSED;
    if (windows >= 3 && reference) flags |= DHM_CPU_RELATIVE;
    if (samples) flags |= DHM_HANDLER;
    snapshot[0] = DHM_MAGIC;
    snapshot[1] = (DHM_VERSION << 16) | DHM_BYTES;
    snapshot[2] = flags;
    snapshot[3] = blocks;
    snapshot[4] = windows;
    snapshot[5] = DHM_WINDOW;
    snapshot[6] = idle;
    snapshot[7] = delta;
    snapshot[8] = reference;
    snapshot[9] = sum_hi;
    snapshot[10] = sum_lo;
    snapshot[11] = maximum;
    snapshot[12] = samples;
    snapshot[13] = zero;
    position = sum_hi = sum_lo = maximum = samples = zero = 0;
}

void dhm_read(unsigned out[DHM_WORDS])
{
    unsigned i, sr = core_keys_lock();
    for (i = 0; i < DHM_WORDS; ++i) out[i] = snapshot[i];
    core_keys_unlock(sr);
    /* A structurally valid unavailable reply before the first closed window. */
    if (!out[0]) {
        out[0] = DHM_MAGIC;
        out[1] = (DHM_VERSION << 16) | DHM_BYTES;
        out[5] = DHM_WINDOW;
    }
}

/* Read-only METRICS 0x04. Remote-input enable/session state is irrelevant. */
int dhm_receive(const unsigned char *packed, unsigned length, unsigned char *reply)
{
    unsigned i, value, words[DHM_WORDS];
    if (length < 4 || (packed[3] | ((packed[0] << 3) & 0x80)) != 4) return 0;
    reply[0] = packed[1] | ((packed[0] << 1) & 0x80);
    reply[1] = packed[2] | ((packed[0] << 2) & 0x80);
    reply[2] = 0x84; reply[3] = 1;
    if (length != 4 || packed[0] & 0x8f || packed[1] & 0x80 ||
        packed[2] & 0x80 || packed[3] & 0x80) return 4;
    dhm_read(words);
    reply[3] = 0;
    for (i = 0; i < DHM_WORDS; ++i) {
        value = words[i];
        reply[4+4*i] = value >> 24;
        reply[5+4*i] = value >> 16;
        reply[6+4*i] = value >> 8;
        reply[7+4*i] = value;
    }
    return 4 + DHM_BYTES;
}
