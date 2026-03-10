#include "nr_ncr_ctx.h"
#include "common/utils/LOG/log.h"
#include <string.h>

void nr_ncr_ctx_init(nr_ncr_ctx_t *ctx) { memset(ctx, 0, sizeof(*ctx)); }

void nr_ncr_ctx_log(const nr_ncr_ctx_t *ctx, const char *tag) {
  LOG_I(RRC, "[NCR][%s] enabled=%d ap_cfg=%d beamFieldWidth=%u nFields=%u refSCS=%u nRsrc=%u\n",
        tag, ctx->enabled, ctx->ap_cfg_present, ctx->aperiodicBeamFieldWidth,
        ctx->numberOfFields, ctx->referenceSCS, ctx->n_time_rsrc);
  for (int i=0;i<ctx->n_time_rsrc;i++) {
    LOG_I(RRC, "[NCR][%s] rsrc[%d] slotOff=%u symOff=%u durSym=%u\n",
          tag, i, ctx->time_rsrc[i].slotOffsetAperiodic, ctx->time_rsrc[i].symbolOffset, ctx->time_rsrc[i].durationInSymbols);
  }
}

