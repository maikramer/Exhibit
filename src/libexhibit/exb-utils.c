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

#include <f3d/engine_c_api.h>
#include <f3d/options_c_api.h>

/**
 * exb_get_allowed_extensions:
 *
 * Returns: (transfer full): (array zero-terminated=1) (nullable): A list of strings
 */
char **
exb_get_allowed_extensions (void)
{
  g_autofree f3d_reader_info_t *readers = NULL;
  GPtrArray *array;
  int count = 0;

  f3d_engine_autoload_plugins ();

  readers = f3d_engine_get_readers_info (&count);
  if (!readers)
    return NULL;

  array = g_ptr_array_new_with_free_func (g_free);

  for (int i = 0; i < count; i++)
    {
      if (readers[i].extensions)
        {
          for (char **ext = readers[i].extensions; *ext; ext++)
            {
              g_ptr_array_add (array, g_strdup (*ext));
            }
        }
    }

  g_ptr_array_add (array, NULL);
  return (char **) g_ptr_array_free (array, FALSE);
}

const char *
exb_direction_to_string (ExbDirection direction)
{
  switch (direction)
    {
    case EXB_DIRECTION_POSITIVE_X:
      return "+X";
    case EXB_DIRECTION_NEGATIVE_X:
      return "-X";
    case EXB_DIRECTION_POSITIVE_Y:
      return "+Y";
    case EXB_DIRECTION_NEGATIVE_Y:
      return "-Y";
    case EXB_DIRECTION_POSITIVE_Z:
      return "+Z";
    case EXB_DIRECTION_NEGATIVE_Z:
      return "-Z";
    default:
      return NULL;
    }
}

gboolean
exb_direction_from_string (const char *str,
                           ExbDirection *out)
{
  g_return_val_if_fail (str != NULL, FALSE);
  g_return_val_if_fail (out != NULL, FALSE);

  if (g_str_equal (str, "+X"))
    {
      *out = EXB_DIRECTION_POSITIVE_X;
      return TRUE;
    }
  if (g_str_equal (str, "-X"))
    {
      *out = EXB_DIRECTION_NEGATIVE_X;
      return TRUE;
    }
  if (g_str_equal (str, "+Y"))
    {
      *out = EXB_DIRECTION_POSITIVE_Y;
      return TRUE;
    }
  if (g_str_equal (str, "-Y"))
    {
      *out = EXB_DIRECTION_NEGATIVE_Y;
      return TRUE;
    }
  if (g_str_equal (str, "+Z"))
    {
      *out = EXB_DIRECTION_POSITIVE_Z;
      return TRUE;
    }
  if (g_str_equal (str, "-Z"))
    {
      *out = EXB_DIRECTION_NEGATIVE_Z;
      return TRUE;
    }

  return FALSE;
}

const char *
exb_sprite_type_to_string (ExbSpriteType type)
{
  switch (type)
    {
    case EXB_SPRITE_TYPE_GAUSSIAN:
      return "gaussian";
    case EXB_SPRITE_TYPE_SPHERE:
      return "sphere";
    default:
      return NULL;
    }
}

gboolean
exb_sprite_type_from_string (const char *str,
                             ExbSpriteType *out)
{
  g_return_val_if_fail (str != NULL, FALSE);
  g_return_val_if_fail (out != NULL, FALSE);

  if (g_str_equal (str, "gaussian"))
    {
      *out = EXB_SPRITE_TYPE_GAUSSIAN;
      return TRUE;
    }
  if (g_str_equal (str, "sphere"))
    {
      *out = EXB_SPRITE_TYPE_SPHERE;
      return TRUE;
    }

  return FALSE;
}

const char *
exb_blending_mode_to_string (ExbBlendingMode mode)
{
  switch (mode)
    {
    case EXB_BLENDING_MODE_DDP:
      return "ddp";
    case EXB_BLENDING_MODE_SORT:
      return "sort";
    case EXB_BLENDING_MODE_STOCHASTIC:
      return "stochastic";
    default:
      return NULL;
    }
}

gboolean
exb_blending_mode_from_string (const char *str,
                               ExbBlendingMode *out)
{
  g_return_val_if_fail (str != NULL, FALSE);
  g_return_val_if_fail (out != NULL, FALSE);

  if (g_str_equal (str, "ddp"))
    {
      *out = EXB_BLENDING_MODE_DDP;
      return TRUE;
    }
  if (g_str_equal (str, "sort"))
    {
      *out = EXB_BLENDING_MODE_SORT;
      return TRUE;
    }
  if (g_str_equal (str, "stochastic"))
    {
      *out = EXB_BLENDING_MODE_STOCHASTIC;
      return TRUE;
    }

  return FALSE;
}

/* ExbAntiAliasingMode */

const char *
exb_anti_aliasing_mode_to_string (ExbAntiAliasingMode mode)
{
  switch (mode)
    {
    case EXB_ANTI_ALIASING_MODE_FXAA:
      return "fxaa";
    case EXB_ANTI_ALIASING_MODE_SSAA:
      return "ssaa";
    case EXB_ANTI_ALIASING_MODE_TAA:
      return "taa";
    default:
      return NULL;
    }
}

gboolean
exb_anti_aliasing_mode_from_string (const char *str,
                                    ExbAntiAliasingMode *out)
{
  g_return_val_if_fail (str != NULL, FALSE);
  g_return_val_if_fail (out != NULL, FALSE);

  if (g_str_equal (str, "fxaa"))
    {
      *out = EXB_ANTI_ALIASING_MODE_FXAA;
      return TRUE;
    }
  if (g_str_equal (str, "ssaa"))
    {
      *out = EXB_ANTI_ALIASING_MODE_SSAA;
      return TRUE;
    }
  if (g_str_equal (str, "taa"))
    {
      *out = EXB_ANTI_ALIASING_MODE_TAA;
      return TRUE;
    }

  return FALSE;
}

char *
exb_f3d_options_get_as_string (f3d_options_t *options,
                               const char    *name)
{
  const char *f3d_str = NULL;
  char *result = NULL;

  g_message ("get as string: %s", name);

  f3d_str = f3d_options_get_as_string_representation (options, name);

  if (!f3d_str)
    return NULL;

  result = g_strdup (f3d_str);
  f3d_options_free_string (f3d_str);

  return result;
}

char *
exb_f3d_options_get_closest_option (f3d_options_t *options,
                                    const char    *f3d_key,
                                    unsigned int  *distance)
{
  char *f3d_closest_key = NULL;
  char *result = NULL;
  unsigned int local_distance = 0;

  g_message ("get closest option");

  if (!distance)
    distance = &local_distance;

  f3d_options_get_closest_option (options, f3d_key, &f3d_closest_key, distance);

  if (!f3d_closest_key)
    return NULL;

  result = g_strdup (f3d_closest_key);
  f3d_options_free_string (f3d_closest_key);

  return result;
}
