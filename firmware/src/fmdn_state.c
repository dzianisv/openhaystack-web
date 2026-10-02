#include "fmdn_state.h"

#include <string.h>

#include "nrf.h"
#include "nrf5x-compat.h"
#include "app_util_platform.h"

#if NRF_SDK_VERSION >= 15
#include "nrf_soc.h"
#include "nrf_sdh_soc.h"
#include "nrf_pwr_mgmt.h"
#else
#include "softdevice_handler.h"
#endif

/* Last page of application flash, kept out of the linker FLASH region.
 * nRF52832: 0x7F000 (4 KiB). nRF52810: 0x2F000 (4 KiB). nRF51822: 0x3FC00 (1 KiB).
 * A power cycle restores this counter instead of restarting at slot 0.
 * Time spent powered off is not added: there is no clock while the chip is off.
 */
#if defined(NRF52832_XXAA)
#define FMDN_STATE_PAGE_ADDR 0x0007F000u
#define FMDN_STATE_PAGE_SIZE 4096u
#elif defined(NRF52810_XXAA)
#define FMDN_STATE_PAGE_ADDR 0x0002F000u
#define FMDN_STATE_PAGE_SIZE 4096u
#elif defined(NRF51)
#define FMDN_STATE_PAGE_ADDR 0x0003FC00u
#define FMDN_STATE_PAGE_SIZE 1024u
#else
#error "FMDN state page is not defined for this chip"
#endif

#define FMDN_STATE_MAGIC 0x4E444D46u /* 'FMDN' little-endian */
#define FMDN_STATE_SALT  0xA5A5A5A5u
#define FMDN_REC_WORDS   8u

typedef struct {
    uint32_t magic;
    uint32_t table_start;
    uint32_t step;
    uint32_t counter;
    uint32_t checksum;
    uint32_t reserved[3];
} fmdn_rec_t;

_Static_assert(sizeof(fmdn_rec_t) == FMDN_REC_WORDS * 4u, "FMDN record must be 8 words");
_Static_assert((FMDN_STATE_PAGE_ADDR % FMDN_STATE_PAGE_SIZE) == 0u, "state page misaligned");
_Static_assert((FMDN_STATE_PAGE_SIZE % sizeof(fmdn_rec_t)) == 0u, "page is not a whole number of records");

static volatile uint8_t save_pending;
static volatile uint32_t save_counter;
static uint32_t next_addr;
static uint32_t bound_start;
static uint32_t bound_step;
static uint8_t sd_enabled;
static volatile uint8_t flash_done;
static volatile uint32_t flash_result;

static uint32_t rec_checksum(uint32_t table_start, uint32_t step, uint32_t counter)
{
    return FMDN_STATE_MAGIC ^ table_start ^ step ^ counter ^ FMDN_STATE_SALT;
}

static int rec_matches(const fmdn_rec_t *rec, uint32_t table_start, uint32_t step)
{
    if (rec->magic != FMDN_STATE_MAGIC) {
        return 0;
    }
    if (rec->table_start != table_start || rec->step != step) {
        return 0;
    }
    if (rec->checksum != rec_checksum(table_start, step, rec->counter)) {
        return 0;
    }
    return 1;
}

static void nvmc_wait(void)
{
    while (NRF_NVMC->READY == NVMC_READY_READY_Busy) {
    }
}

static void nvmc_erase_page(uint32_t address)
{
    uint32_t nested = __get_PRIMASK();
    __disable_irq();
    NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Een;
    nvmc_wait();
    NRF_NVMC->ERASEPAGE = address;
    nvmc_wait();
    NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Ren;
    nvmc_wait();
    if (nested == 0) {
        __enable_irq();
    }
}

static void nvmc_write_words(uint32_t address, const uint32_t *src, uint32_t num_words)
{
    uint32_t nested = __get_PRIMASK();
    volatile uint32_t *dst = (volatile uint32_t *)address;
    uint32_t i;

    __disable_irq();
    NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Wen;
    nvmc_wait();
    for (i = 0; i < num_words; i++) {
        dst[i] = src[i];
        nvmc_wait();
    }
    NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Ren;
    nvmc_wait();
    if (nested == 0) {
        __enable_irq();
    }
}

#if NRF_SDK_VERSION >= 15
static void fmdn_soc_evt(uint32_t evt_id, void *context)
{
    (void)context;
    if (evt_id == NRF_EVT_FLASH_OPERATION_SUCCESS) {
        flash_result = NRF_SUCCESS;
        flash_done = 1;
    } else if (evt_id == NRF_EVT_FLASH_OPERATION_ERROR) {
        flash_result = NRF_ERROR_INTERNAL;
        flash_done = 1;
    }
}

NRF_SDH_SOC_OBSERVER(m_fmdn_soc_obs, 1, fmdn_soc_evt, NULL);

static uint32_t sd_op_wait(uint32_t err)
{
    if (err != NRF_SUCCESS) {
        return err;
    }
    while (!flash_done) {
        nrf_pwr_mgmt_run();
    }
    return flash_result;
}

static uint32_t sd_erase_page(void)
{
    flash_done = 0;
    return sd_op_wait(sd_flash_page_erase(FMDN_STATE_PAGE_ADDR / FMDN_STATE_PAGE_SIZE));
}

static uint32_t sd_write_words(uint32_t address, uint32_t const *src, uint32_t num_words)
{
    flash_done = 0;
    return sd_op_wait(sd_flash_write((uint32_t *)address, src, num_words));
}
#else
static void fmdn_sys_evt(uint32_t evt_id)
{
    if (evt_id == NRF_EVT_FLASH_OPERATION_SUCCESS) {
        flash_result = NRF_SUCCESS;
        flash_done = 1;
    } else if (evt_id == NRF_EVT_FLASH_OPERATION_ERROR) {
        flash_result = NRF_ERROR_INTERNAL;
        flash_done = 1;
    }
}

static uint32_t sd_op_wait(uint32_t err)
{
    if (err != NRF_SUCCESS) {
        return err;
    }
    while (!flash_done) {
        (void)sd_app_evt_wait();
    }
    return flash_result;
}

static uint32_t sd_erase_page(void)
{
    flash_done = 0;
    return sd_op_wait(sd_flash_page_erase(FMDN_STATE_PAGE_ADDR / FMDN_STATE_PAGE_SIZE));
}

static uint32_t sd_write_words(uint32_t address, uint32_t const *src, uint32_t num_words)
{
    flash_done = 0;
    return sd_op_wait(sd_flash_write((uint32_t *)address, src, num_words));
}
#endif

static void fill_rec(fmdn_rec_t *rec, uint32_t counter)
{
    memset(rec, 0xFF, sizeof(*rec));
    rec->magic = FMDN_STATE_MAGIC;
    rec->table_start = bound_start;
    rec->step = bound_step;
    rec->counter = counter;
    rec->checksum = rec_checksum(bound_start, bound_step, counter);
}

static int write_rec_at(uint32_t address, uint32_t counter)
{
    fmdn_rec_t rec;
    fill_rec(&rec, counter);
    if (!sd_enabled) {
        nvmc_write_words(address, (const uint32_t *)&rec, FMDN_REC_WORDS);
        return 1;
    }
    if (sd_write_words(address, (const uint32_t *)&rec, FMDN_REC_WORDS) != NRF_SUCCESS) {
        COMPAT_NRF_LOG_INFO("[FMDN] flash write failed");
        return 0;
    }
    return 1;
}

static int erase_state_page(void)
{
    if (!sd_enabled) {
        nvmc_erase_page(FMDN_STATE_PAGE_ADDR);
        return 1;
    }
    if (sd_erase_page() != NRF_SUCCESS) {
        COMPAT_NRF_LOG_INFO("[FMDN] flash erase failed");
        return 0;
    }
    return 1;
}

static uint32_t scan_page(uint32_t table_start, uint32_t step, int *found)
{
    const fmdn_rec_t *page = (const fmdn_rec_t *)FMDN_STATE_PAGE_ADDR;
    uint32_t n = FMDN_STATE_PAGE_SIZE / sizeof(fmdn_rec_t);
    uint32_t i;
    uint32_t counter = table_start;
    int last = -1;

    *found = 0;
    for (i = 0; i < n; i++) {
        if (page[i].magic == 0xFFFFFFFFu) {
            break;
        }
        if (rec_matches(&page[i], table_start, step)) {
            counter = page[i].counter;
            last = (int)i;
            *found = 1;
        }
    }
    if (last >= 0 && (uint32_t)last + 1u < n && page[last + 1].magic == 0xFFFFFFFFu) {
        next_addr = FMDN_STATE_PAGE_ADDR + ((uint32_t)last + 1u) * sizeof(fmdn_rec_t);
    } else if (!*found && page[0].magic == 0xFFFFFFFFu) {
        next_addr = FMDN_STATE_PAGE_ADDR;
    } else {
        /* Full, or trailing garbage. Next save erases. */
        next_addr = 0;
    }
    return counter;
}

uint32_t fmdn_state_load_or_init(uint32_t table_start, uint32_t step)
{
    int found = 0;
    uint32_t counter;

    bound_start = table_start;
    bound_step = step;
    counter = scan_page(table_start, step, &found);
    if (!found) {
        if (!erase_state_page()) {
            next_addr = 0;
            return table_start;
        }
        next_addr = FMDN_STATE_PAGE_ADDR;
        if (!write_rec_at(next_addr, table_start)) {
            return table_start;
        }
        next_addr += sizeof(fmdn_rec_t);
        return table_start;
    }
    COMPAT_NRF_LOG_INFO("[FMDN] restored beacon counter %u", counter);
    return counter;
}

void fmdn_state_sd_is_enabled(void)
{
#if NRF_SDK_VERSION < 15
    softdevice_sys_evt_handler_set(fmdn_sys_evt);
#endif
    sd_enabled = 1;
}

void fmdn_state_request_save(uint32_t counter)
{
    save_counter = counter;
    save_pending = 1;
}

void fmdn_state_flush_if_pending(void)
{
    uint32_t counter;

    if (!save_pending) {
        return;
    }
    counter = save_counter;
    if (next_addr == 0 ||
        next_addr + sizeof(fmdn_rec_t) > FMDN_STATE_PAGE_ADDR + FMDN_STATE_PAGE_SIZE) {
        if (!erase_state_page()) {
            return;
        }
        next_addr = FMDN_STATE_PAGE_ADDR;
    }
    if (!write_rec_at(next_addr, counter)) {
        return;
    }
    next_addr += sizeof(fmdn_rec_t);
    if (save_counter == counter) {
        save_pending = 0;
    }
}
