#ifndef FMDN_CLOCK_H
#define FMDN_CLOCK_H

#include <stdint.h>

/* Slot for a beacon time counter, or -1 if the counter is outside the
 * precomputed table. Never wraps: repeating slot 0 after the table ends
 * would advertise an EID the owner resolver no longer expects.
 *
 * counter and start are uint32 beacon times. start is the table's first
 * window (low K bits already clear). step is 2^K seconds (1024 when K=10).
 */
static inline int fmdn_slot_for_counter(uint32_t counter, uint32_t start,
                                        uint32_t step, int count)
{
    uint32_t slot;

    if (step == 0 || count <= 0) {
        return -1;
    }
    if (counter < start) {
        return -1;
    }
    slot = (counter - start) / step;
    if (slot >= (uint32_t)count) {
        return -1;
    }
    return (int)slot;
}

#endif /* FMDN_CLOCK_H */
