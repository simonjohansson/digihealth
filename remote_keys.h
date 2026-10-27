/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef REMOTE_KEYS_H
#define REMOTE_KEYS_H

enum { RK_CAPS = 0x10, RK_OPEN, RK_ACTION, RK_STATUS, RK_CANCEL };
enum { RK_PRESS = 1, RK_RELEASE, RK_TAP, RK_TURN };
enum { RK_NONE, RK_ACCEPTED, RK_COMPLETED, RK_CANCELLED, RK_EXPIRED, RK_FAILED };
enum { RK_OK, RK_INVALID, RK_UNKNOWN, RK_BUSY, RK_STALE, RK_OVERLAP, RK_OFF };
enum { RK_KEY_COUNT = 57 };

int rk_receive(const unsigned char *packed, unsigned length, unsigned char *reply);
/* A request's 7-bit packing, exactly COUNT bytes long, or 0. */
int rk_unpack(const unsigned char *src, unsigned length, unsigned char *dst, unsigned count);
void rk_tick(void *ctrl);

#endif
