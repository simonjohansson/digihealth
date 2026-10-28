/* SPDX-License-Identifier: GPL-2.0-or-later */
/* DSP memory through core-dn2's peek (Elekloader #98). DSP_PEEK 0x06 starts a read: u32 address,
 * u16 words. DSP_PEEK_READ 0x07 returns its progress and words: u16 first word, u16 words
 * (1..256) -> u16 halfwords received, u16 halfwords expected, then the words, big-endian.
 * Status 0 done, 1 refused, 3 still arriving. */
#include "digitone-mk2/core.h"
#include "../remote_keys.h"
#include "dsp-peek.h"

enum { DSP_PEEK = 6, DSP_PEEK_READ = 7, READ_MAX = 256 };
enum { DONE, REFUSED, ARRIVING = 3 };

static unsigned get16(const unsigned char *p)
{
    return (unsigned)p[0] << 8 | p[1];
}

static void put16(unsigned char *p, unsigned value)
{
    p[0] = value >> 8;
    p[1] = value;
}

int dsp_peek_receive(const unsigned char *packed, unsigned length, unsigned char *reply)
{
    unsigned char request[9];
    unsigned command, first, count, received, total, i, word;
    const volatile unsigned short *data;
    int status;
    if (length < 4) return 0;
    command = packed[3] | ((packed[0] << 3) & 0x80);
    if (command != DSP_PEEK && command != DSP_PEEK_READ) return 0;
    reply[0] = packed[1] | ((packed[0] << 1) & 0x80);
    reply[1] = packed[2] | ((packed[0] << 2) & 0x80);
    reply[2] = command | 0x80;
    reply[3] = REFUSED;
    if (!rk_unpack(packed, length, request, command == DSP_PEEK ? 9 : 7)) return 4;
    if (command == DSP_PEEK) {
        reply[3] = core_dsp_peek(get16(request + 3) << 16 | get16(request + 5),
                                 get16(request + 7)) == CORE_DSP_PEEK_OK ? DONE : REFUSED;
        return 4;
    }
    first = get16(request + 3);
    count = get16(request + 5);
    status = core_dsp_peek_status(&received, &total);
    if (!count || count > READ_MAX || 2 * (first + count) > total) return 4;
    reply[3] = status == CORE_DSP_PEEK_REFUSED ? REFUSED : status == CORE_DSP_PEEK_BUSY ? ARRIVING : DONE;
    put16(reply + 4, received);
    put16(reply + 6, total);
    data = core_dsp_peek_data();
    for (i = 0; i < count; ++i) {
        word = data[2 * (first + i)] | (unsigned)data[2 * (first + i) + 1] << 16;
        put16(reply + 8 + 4 * i, word >> 16);
        put16(reply + 10 + 4 * i, word);
    }
    return 8 + 4 * count;
}
