#pragma once
#include <stdint.h>
#include <stdbool.h>

#define NCR_AP_MAX_RSRC 16

typedef struct {
  uint16_t slotOffsetAperiodic;
  uint8_t  symbolOffset;
  uint8_t  durationInSymbols;
} ncr_ap_time_rsrc_t;

typedef struct {
  bool enabled;                 // ncr-FwdConfig setup/release 的狀態
  bool ap_cfg_present;          // aperiodicFwdConfig setup/release 是否存在
  uint8_t aperiodicBeamFieldWidth;
  uint8_t numberOfFields;
  uint8_t referenceSCS;         // 0..4 (15/30/60/120/240)
  uint8_t n_time_rsrc;
  ncr_ap_time_rsrc_t time_rsrc[NCR_AP_MAX_RSRC];
} nr_ncr_ctx_t;

void nr_ncr_ctx_init(nr_ncr_ctx_t *ctx);
void nr_ncr_ctx_log(const nr_ncr_ctx_t *ctx, const char *tag);
