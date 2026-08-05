/*
 * exb-postfx.h
 *
 * Post-processing compositor: builds F3D final_shader GLSL from effect state.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include <glib.h>

G_BEGIN_DECLS

typedef struct
{
  gboolean bloom;
  gdouble  bloom_threshold; /* 0..1; post-tonemap LDR default ~0.25 */
  gdouble  bloom_intensity; /* 0..5 */
  gdouble  bloom_radius;    /* 1..16 px sample spread */

  gboolean godrays;
  gdouble  godrays_intensity; /* 0..5 */
  gdouble  godrays_decay;     /* 0.8..1 */
  gdouble  godrays_density;   /* 0.1..2 */
  gdouble  godrays_weight;    /* 0..1 */
} ExbPostFxState;

void   exb_postfx_state_init_defaults (ExbPostFxState *state);

/* Caller owns returned string. NULL when no effect active. */
gchar *exb_postfx_build_shader        (const ExbPostFxState *state);

G_END_DECLS
