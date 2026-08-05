/*
 * exb-engine-private.h
 *
 * Copyright 2026 Nokse <nokse@posteo.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include "exb-engine.h"

G_BEGIN_DECLS

void     _exb_engine_initialize (ExbEngine *self);
void     _exb_engine_finalize   (ExbEngine *self);

/* NDC in [-1, 1], y up. Used for zoom/orbit-under-cursor (fork nav). */
void     _exb_engine_zoom_at_ndc   (ExbEngine *self,
                                    gdouble     factor,
                                    gdouble     ndc_x,
                                    gdouble     ndc_y);
void     _exb_engine_rotate_at_ndc (ExbEngine *self,
                                    gdouble     dx,
                                    gdouble     dy,
                                    gdouble     ndc_x,
                                    gdouble     ndc_y,
                                    gboolean    with_limit);

G_END_DECLS
