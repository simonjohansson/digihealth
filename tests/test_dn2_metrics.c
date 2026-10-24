/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#ifndef REPLY
#define REPLY 0xfffffff0u
#endif
volatile const unsigned dhm_reply[] = { REPLY };
static unsigned locked;
unsigned core_keys_lock(void) { assert(!locked); locked = 1; return 0x2300; }
void core_keys_unlock(unsigned sr) { assert(locked && sr == 0x2300); locked = 0; }
#include "../dn2/metrics-core.c"

static void window(unsigned idle)
{
    unsigned i;
    dhm_idle_line[0] += idle;
    for (i = 0; i < DHM_WINDOW; ++i) dhm_block();
}

int main(void)
{
    unsigned out[DHM_WORDS], saved[DHM_WORDS], i;
    unsigned char request[] = {0, 2, 3, 4}, reply[4+DHM_BYTES];
    uint64_t total = (uint64_t)(unsigned)REPLY * DHM_WINDOW;
    dhm_read(out);
    assert(out[0] == DHM_MAGIC && out[1] == 0x00010038 && !out[2]);
    assert(out[5] == 1500);
    window(1000000);             /* do not calibrate on the startup window */
    dhm_read(out);
    assert(out[2] == (DHM_CLOSED | (REPLY ? DHM_HANDLER : 0)) && !out[8]);
    assert(out[9] == total >> 32 && out[10] == (unsigned)total);
    assert(out[11] == REPLY && out[12] == (REPLY ? 1500u : 0u));
    assert(out[13] == (REPLY ? 0u : 1500u));
    window(1000);
    dhm_read(out);
    assert(!(out[2] & DHM_CPU_RELATIVE) && out[8] == 1000);
    window(500);
    dhm_read(out);
    assert(out[2] & DHM_CPU_RELATIVE);
    assert(out[7] == 500 && out[8] == 1000 && out[3] == 4500);
    memcpy(saved, out, sizeof(out));
    for (i = 0; i < 1499; ++i) dhm_block();
    dhm_read(out);
    assert(!memcmp(saved, out, sizeof(out))); /* partial window is not published */
    dhm_idle_line[0] += 2000;
    dhm_block();
    dhm_read(out);
    assert(out[7] == 2000 && out[8] == 2000); /* new best reference */
    position = 0; idle_at = dhm_idle_line[0] = 0xfffffff0u;
    blocks = 0xfffffffeu;
    window(48);
    dhm_read(out);
    assert(out[6] == 32 && out[7] == 48 && out[3] == 1498); /* wrap */

    assert(dhm_receive(request, 4, reply) == 60);
    assert(reply[0] == 2 && reply[1] == 3 && reply[2] == 0x84 && !reply[3]);
    assert(!memcmp(reply+4, "DHM1\0\1\0\x38", 8));
    for (i = 0; i < DHM_WORDS; ++i) {
        unsigned value = (unsigned)reply[4+4*i]<<24 | (unsigned)reply[5+4*i]<<16 |
                         (unsigned)reply[6+4*i]<<8 | reply[7+4*i];
        assert(value == out[i]);
    }
    request[0] = 0x70; /* both sequence bytes may carry their eighth bit */
    assert(!dhm_receive(request, 4, reply)); /* a different command, delegated */
    request[0] = 0x60;
    assert(dhm_receive(request, 4, reply) == 60 && reply[0] == 130 && reply[1] == 131);
    request[0] = 1;
    assert(dhm_receive(request, 4, reply) == 4 && reply[3] == 1);
    request[0] = 0; request[1] = 0x80;
    assert(dhm_receive(request, 4, reply) == 4 && reply[3] == 1);
    request[1] = 2;
    assert(dhm_receive(request, 5, reply) == 4 && reply[3] == 1);
    assert(!dhm_receive(request, 3, reply));
    request[3] = 0x10;
    assert(!dhm_receive(request, 4, reply)); /* existing remote commands delegated */
    assert(!locked);
    return 0;
}
