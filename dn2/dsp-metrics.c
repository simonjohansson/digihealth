/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "dsp-metrics.h"

extern unsigned core_keys_lock(void);
extern void core_keys_unlock(unsigned sr);

/* One IRQ writer. Stock does not clear reply header 2; repeated words must
 * neither advance assembly nor renew a completed snapshot's freshness. */
static unsigned parts[8], published[8];
static unsigned current, first, next, sequence, crc, previous, active;
static unsigned seen, published_at, published_sequence, accepted, crc_errors, dropped;

static unsigned crc_half(unsigned value, unsigned half)
{
    unsigned bit;
    value ^= half;
    for (bit = 0; bit < 16; ++bit)
        value = ((value << 1) ^ ((value & 0x8000) ? 0x1021u : 0)) & 0xffff;
    return value;
}

void dhs_block(unsigned word, unsigned cf_blocks)
{
    unsigned index = (word >> 16) & 31, seq = (word >> 21) & 7;
    unsigned half = word & 0xffff, i, same;
    current = cf_blocks;
    if (active && current - first > DHC_FRESH_BLOCKS) {
        active = 0;
        ++dropped;
    }
    if (word == previous) return;
    previous = word;
    if (word >> 24 != 0xd6 || index > 16) {
        if (active) ++dropped;
        active = 0;
        return;
    }
    if (index == 0) {
        if (active) ++dropped;
        active = 1;
        first = current;
        sequence = seq;
        next = 0;
        crc = 0xffff;
    } else if (!active || seq != sequence || index != next) {
        if (active) ++dropped;
        active = 0;
        return;
    }
    if (index < 16) {
        if (index & 1) parts[index >> 1] |= half;
        else parts[index >> 1] = half << 16;
        crc = crc_half(crc, half);
        next = index + 1;
        return;
    }
    active = 0;
    if (half != crc) { ++crc_errors; return; }
    if (parts[0] != 0x44485331u || parts[6] != 1 || parts[7] != 0) {
        ++dropped;
        return;
    }
    same = seen;
    for (i = 0; i < 8; ++i) if (parts[i] != published[i]) same = 0;
    if (same) { ++dropped; return; }
    for (i = 0; i < 8; ++i) published[i] = parts[i];
    published_at = current;
    published_sequence = sequence;
    seen = 1;
    ++accepted;
}

void dhs_read(unsigned out[DHC_WORDS])
{
    unsigned sr = core_keys_lock();
    out[0] = DHC_MAGIC;
    out[1] = (DHC_VERSION << 16) | DHC_BYTES;
    out[2] = seen ? DHC_SEEN : 0;
    if (seen && current - published_at <= DHC_FRESH_BLOCKS) out[2] |= DHC_FRESH;
    out[3] = published_at;
    out[4] = current;
    out[5] = published_sequence;
    out[6] = published[1];
    out[7] = published[2];
    out[8] = published[3];
    out[9] = published[4];
    out[10] = published[5];
    out[11] = published[6];
    out[12] = accepted;
    out[13] = crc_errors;
    out[14] = dropped;
    out[15] = 0;
    core_keys_unlock(sr);
}

/* Read-only DSP_METRICS 0x05; old METRICS/STATS formats stay unchanged. */
int dhs_receive(const unsigned char *packed, unsigned length, unsigned char *reply)
{
    unsigned i, value, words[DHC_WORDS];
    if (length < 4 || (packed[3] | ((packed[0] << 3) & 0x80)) != 5) return 0;
    reply[0] = packed[1] | ((packed[0] << 1) & 0x80);
    reply[1] = packed[2] | ((packed[0] << 2) & 0x80);
    reply[2] = 0x85; reply[3] = 1;
    if (length != 4 || packed[0] & 0x8f || packed[1] & 0x80 ||
        packed[2] & 0x80 || packed[3] & 0x80) return 4;
    dhs_read(words);
    reply[3] = 0;
    for (i = 0; i < DHC_WORDS; ++i) {
        value = words[i];
        reply[4+4*i] = value >> 24;
        reply[5+4*i] = value >> 16;
        reply[6+4*i] = value >> 8;
        reply[7+4*i] = value;
    }
    return 4 + DHC_BYTES;
}
