/*
 * exb-engine.h
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

#include <gtk/gtk.h>

G_BEGIN_DECLS

#define EXB_TYPE_ENGINE (exb_engine_get_type())

G_DECLARE_DERIVABLE_TYPE (ExbEngine, exb_engine, EXB, ENGINE, GObject)

struct _ExbEngineClass
{
  GObjectClass parent_class;
};

void        exb_engine_set_file(ExbEngine *self,
                                GFile     *file);
GFile      *exb_engine_get_file(ExbEngine *self);

GdkTexture *exb_engine_render_texture (ExbEngine *self);

char      **exb_engine_get_allowed_extensions(void);

gboolean    exb_engine_render (ExbEngine *self);

void        exb_engine_set_size (ExbEngine *self,
                                 uint       width,
                                 uint       height);

ExbEngine  *exb_engine_new_standalone (void);

void        exb_engine_zoom (ExbEngine *self,
                             double     factor);

G_END_DECLS
