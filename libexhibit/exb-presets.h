/*
 * exb-presets.h
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

#include <gio/gio.h>

#include "exb-preset.h"

G_BEGIN_DECLS

#define EXB_TYPE_PRESETS (exb_presets_get_type ())

G_DECLARE_FINAL_TYPE (ExbPresets, exb_presets, EXB, PRESETS, GObject)

ExbPresets *exb_presets_new             (void);

void        exb_presets_add_search_path (ExbPresets  *self,
                                         const char  *path);
void        exb_presets_set_search_path (ExbPresets  *self,
                                         const char * const *paths);
ExbPreset  *exb_presets_lookup          (ExbPresets  *self,
                                         const char  *name);

G_END_DECLS
