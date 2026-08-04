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
#include <graphene.h>
#include <libdex.h>

#include "exb-preset.h"

G_BEGIN_DECLS

#define EXB_TYPE_ENGINE (exb_engine_get_type())

G_DECLARE_DERIVABLE_TYPE (ExbEngine, exb_engine, EXB, ENGINE, GObject)

struct _ExbEngineClass
{
  GObjectClass parent_class;
};

ExbEngine * exb_engine_new               (void);
ExbEngine * exb_engine_new_standalone    (void);
DexFuture * exb_engine_load_file         (ExbEngine *self,
                                          GFile     *file);
void        exb_engine_set_size          (ExbEngine *self,
                                          uint       width,
                                          uint       height);
GFile *     exb_engine_get_file          (ExbEngine *self);
int         exb_engine_get_animations_n  (ExbEngine *self);
void        exb_engine_play_animation    (ExbEngine *self);
GdkTexture *exb_engine_render_texture    (ExbEngine *self);
gboolean    exb_engine_render            (ExbEngine *self);
void        exb_engine_zoom              (ExbEngine *self,
                                          gdouble     factor);
void        exb_engine_pan               (ExbEngine *self,
                                          gdouble     dx,
                                          gdouble     dy);
void        exb_engine_rotate            (ExbEngine *self,
                                          gdouble     dx,
                                          gdouble     dy);
void        exb_engine_rotate_with_limit (ExbEngine *self,
                                          gdouble     dx,
                                          gdouble     dy);
void        exb_engine_reset_camera      (ExbEngine *self);
void        exb_engine_apply_preset      (ExbEngine *self,
                                          ExbPreset *preset);
gboolean    exb_engine_get_loading_file  (ExbEngine *self);
void        exb_engine_reset             (ExbEngine *self);

G_END_DECLS
