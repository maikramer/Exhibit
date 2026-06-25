/*
 * exb-preset.h
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

#include <glib-object.h>
#include <gio/gio.h>

#include "exb-engine.h"

G_BEGIN_DECLS

#define EXB_TYPE_PRESET (exb_preset_get_type ())

G_DECLARE_FINAL_TYPE (ExbPreset, exb_preset, EXB, PRESET, GObject)

ExbPreset  *exb_preset_new             (void);
ExbPreset  *exb_preset_new_from_file   (GFile        *file);
ExbPreset  *exb_preset_new_from_engine (ExbEngine    *engine,
                                        const char   *name);

const char *exb_preset_get_name        (ExbPreset    *self);
void        exb_preset_set_name        (ExbPreset    *self,
                                        const char   *name);

void        exb_preset_apply           (ExbPreset    *self,
                                        ExbEngine    *engine);
void        exb_preset_save            (ExbPreset    *self,
                                        GFile        *file);

G_END_DECLS
