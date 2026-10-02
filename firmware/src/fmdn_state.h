#ifndef FMDN_STATE_H
#define FMDN_STATE_H

#include <stdint.h>

/* Last persisted beacon counter for this table, or table_start if the page
 * has no record for it. Writes the initial record with NVMC. Call before
 * the SoftDevice is enabled.
 */
uint32_t fmdn_state_load_or_init(uint32_t table_start, uint32_t step);

/* Later saves go through sd_flash_write. Call once the SoftDevice is up. */
void fmdn_state_sd_is_enabled(void);

/* ISR-safe. The main loop flushes. */
void fmdn_state_request_save(uint32_t counter);

void fmdn_state_flush_if_pending(void);

#endif /* FMDN_STATE_H */
