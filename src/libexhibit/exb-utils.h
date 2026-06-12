/*
 * exb-utils.h
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
#include <glib.h>

G_BEGIN_DECLS

#include <f3d/engine_c_api.h>
#include <f3d/camera_c_api.h>
#include <f3d/engine_c_api.h>
#include <f3d/image_c_api.h>
#include <f3d/options_c_api.h>
#include <f3d/scene_c_api.h>
#include <f3d/window_c_api.h>

G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_engine_t, f3d_engine_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_context_t, f3d_context_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_image_t, f3d_image_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_options_t, f3d_options_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_light_state_t, f3d_light_state_free)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_reader_info_t, f3d_engine_free_readers_info)

G_DEFINE_AUTO_CLEANUP_CLEAR_FUNC (f3d_color_t, (void (*) (f3d_color_t *)) NULL)
G_DEFINE_AUTO_CLEANUP_CLEAR_FUNC (f3d_light_state_t, f3d_light_state_free)
G_DEFINE_AUTO_CLEANUP_CLEAR_FUNC (f3d_colormap_t, f3d_colormap_free)

typedef enum
{
  EXB_DIRECTION_POSITIVE_X,
  EXB_DIRECTION_NEGATIVE_X,
  EXB_DIRECTION_POSITIVE_Y,
  EXB_DIRECTION_NEGATIVE_Y,
  EXB_DIRECTION_POSITIVE_Z,
  EXB_DIRECTION_NEGATIVE_Z,
} ExbDirection;

typedef enum
{
  EXB_SPRITE_TYPE_SPHERE,
  EXB_SPRITE_TYPE_GAUSSIAN,
} ExbSpriteType;

typedef enum
{
  EXB_BLENDING_MODE_DDP,
  EXB_BLENDING_MODE_SORT,
  EXB_BLENDING_MODE_STOCHASTIC,
} ExbBlendingMode;

typedef enum
{
  EXB_ANTI_ALIASING_MODE_FXAA,
  EXB_ANTI_ALIASING_MODE_SSAA,
  EXB_ANTI_ALIASING_MODE_TAA,
} ExbAntiAliasingMode;

G_END_DECLS
