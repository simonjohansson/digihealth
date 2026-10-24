/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <digitone-mk2/core.h>
#include "../remote_keys.h"
#include "metrics-core.h"

extern void diag_rx(const unsigned char *body, unsigned length);
static const unsigned char header[6] = {0xf0,0,0x20,0x3c,0x7d,0};
static unsigned char frame[1024];
static unsigned generation;
static volatile unsigned frame_requested;

void dn2_tick(void *ctrl)
{
    if (frame_requested && fw_ui_queue[1] == 0)
        *((volatile unsigned char *)ctrl + 0x20) = 1;
}

void dn2_sysex(const unsigned char *message, unsigned length, unsigned source)
{
    unsigned i;
    if ((source != 2 && source != 4) || length < 7 || message[length-1] != 0xf7)
        return;
    for (i=0; i<6; ++i) if (message[i] != header[i]) return;
    diag_rx(message+6, length-7);
}

/* Capture after every other draw subscriber. Bitmap: width +4, height +8,
 * stride in 32-bit words +12, pixel pointer +16. Only the full OLED frame. */
void dn2_frame(const unsigned *bmp, void *ctrl)
{
    const unsigned char *pixels;
    unsigned i, sr;
    (void)ctrl;
    if (bmp[1] != 128 || bmp[2] != 64 || bmp[3] != 2 || fw_ui_queue[1]) return;
    pixels = (const unsigned char *)bmp[4];
    sr = core_keys_lock();
    for (i=0; i<sizeof(frame); ++i) frame[i] = pixels[i];
    if (!++generation) ++generation;
    frame_requested = 0;
    core_keys_unlock(sr);
}

/* FRAME 0x15: exact canonical three-byte request, reply generation + pixels.
 * Copy under the same lock as publication: no mixed frames on the MIDI task. */
int dn2_receive(const unsigned char *packed, unsigned length, unsigned char *reply)
{
    unsigned i, sr;
    int metrics = dhm_receive(packed, length, reply);
    if (metrics) return metrics;
    if (length < 4 || (packed[3] | ((packed[0] << 3) & 0x80)) != 0x15)
        return rk_receive(packed, length, reply);
    reply[0] = packed[1] | ((packed[0] << 1) & 0x80);
    reply[1] = packed[2] | ((packed[0] << 2) & 0x80);
    reply[2] = 0x95; reply[3] = 1;
    if (length != 4 || packed[0] & 0x8f || packed[1] & 0x80 ||
        packed[2] & 0x80 || packed[3] & 0x80) return 4;
    sr = core_keys_lock();
    frame_requested = 1;
    if (!generation) { reply[3]=3; core_keys_unlock(sr); return 4; }
    reply[3]=0;
    reply[4]=generation>>24; reply[5]=generation>>16;
    reply[6]=generation>>8; reply[7]=generation;
    for (i=0; i<sizeof(frame); ++i) reply[8+i]=frame[i];
    core_keys_unlock(sr);
    return 1032;
}

extern void fw_dn2_fillrect(void *, int, int, int, int, int);
extern void fw_dn2_framerect(void *, int, int, int, int, int);
void dn2_checkbox(void *bmp, int x, int y, unsigned checked)
{
    fw_dn2_framerect(bmp,x,y,x+6,y+6,1);
    if (checked) fw_dn2_fillrect(bmp,x+2,y+2,x+4,y+4,1);
}
