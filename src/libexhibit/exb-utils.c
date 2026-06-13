/*
 * exb-utils.c
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

#include "exb-enums.h"
#include "exb-utils.h"
#include "exb-global.h"
#include "graphene.h"

#include <f3d/engine_c_api.h>
#include <f3d/options_c_api.h>

graphene_vec3_t
exb_direction_to_graphene_vec3 (ExbDirection direction)
{
  switch (direction)
    {
    case EXB_DIRECTION_POSITIVE_X:
      {
        return *graphene_vec3_x_axis ();
      }
    case EXB_DIRECTION_NEGATIVE_X:
      {
        graphene_vec3_t v;
        graphene_vec3_init (&v, -1, 0, 0);
        return v;
      }
    case EXB_DIRECTION_POSITIVE_Y:
      {
        return *graphene_vec3_y_axis ();
      }
    case EXB_DIRECTION_NEGATIVE_Y:
      {
        graphene_vec3_t v;
        graphene_vec3_init (&v, 0, -1, 0);
        return v;
      }
    case EXB_DIRECTION_POSITIVE_Z:
      {
        return *graphene_vec3_z_axis ();
      }
    case EXB_DIRECTION_NEGATIVE_Z:
      {
        graphene_vec3_t v;
        graphene_vec3_init (&v, 0, 0, -1);
        return v;
      }
    default:
      {
        return *graphene_vec3_zero ();
      }
    }
}

const char *
exb_f3d_options_get_as_string (f3d_options_t *options,
                               const char    *name)
{
  const char *f3d_str = NULL;
  const char *result = NULL;

  f3d_str = f3d_options_get_as_string_representation (options, name);

  if (!f3d_str)
    return NULL;

  result = g_strdup (f3d_str);
  f3d_options_free_string (f3d_str);

  return result;
}

const char *
exb_f3d_options_get_closest_option (f3d_options_t *options,
                                    const char    *f3d_key,
                                    unsigned int  *distance)
{
  char *f3d_closest_key = NULL;
  const char *result = NULL;
  unsigned int local_distance = 0;

  if (!distance)
    distance = &local_distance;

  f3d_options_get_closest_option (options, f3d_key, &f3d_closest_key, distance);

  if (!f3d_closest_key)
    return NULL;

  result = g_strdup (f3d_closest_key);
  f3d_options_free_string (f3d_closest_key);

  return result;
}
