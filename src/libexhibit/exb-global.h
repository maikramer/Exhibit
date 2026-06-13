/*
 * exb-global.h
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
  EXB_SPRITE_TYPE_CIRCLE,
  EXB_SPRITE_TYPE_STDDEV,
  EXB_SPRITE_TYPE_BOUND,
  EXB_SPRITE_TYPE_CROSS,
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

char ** exb_get_allowed_extensions (void);

G_END_DECLS
