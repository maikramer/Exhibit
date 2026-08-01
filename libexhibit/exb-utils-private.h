/*
 * exb-utils-private.h
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

#include "exb-utils.h"
#include "exb-global.h"
#include "graphene.h"

#include <glib.h>

G_BEGIN_DECLS

graphene_vec3_t exb_direction_to_graphene_vec3     (ExbDirection direction);

const char *    exb_f3d_options_get_as_string      (f3d_options_t *options,
                                                    const char    *name);

const char *    exb_f3d_options_get_closest_option (f3d_options_t *options,
                                                    const char    *f3d_key,
                                                    unsigned int  *distance);

G_END_DECLS
