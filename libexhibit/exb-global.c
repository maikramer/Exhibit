/*
 * exb-global.c
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
#include "exb-global.h"
#include "exb-utils.h"

#include <f3d/engine_c_api.h>

/**
 * exb_get_allowed_extensions:
 *
 * Returns: (transfer full) (array zero-terminated=1) (nullable): A list of strings
 */
gchar **
exb_get_allowed_extensions (void)
{
  g_autoptr (GPtrArray) array = g_ptr_array_new_with_free_func (g_free);
  g_autoptr (f3d_reader_info_t) readers = NULL;
  gint count = 0;

  f3d_engine_autoload_plugins ();

  if (!(readers = f3d_engine_get_readers_info (&count)))
    {
      return NULL;
    }

  for (gint i = 0; i < count; i++)
    {
      if (readers[i].extensions)
        {
          for (gchar **ext = readers[i].extensions; *ext != NULL; ext++)
            {
              g_ptr_array_add (array, g_strdup (*ext));
            }
        }
    }

  g_ptr_array_add (array, NULL);
  return (gchar **) g_ptr_array_free (g_steal_pointer (&array), FALSE);
}

/**
 * exb_get_allowed_mime_types:
 *
 * Returns: (transfer full) (array zero-terminated=1) (nullable): A list of strings
 */
gchar **
exb_get_allowed_mime_types (void)
{
  g_autoptr (GPtrArray) array = g_ptr_array_new_with_free_func (g_free);
  g_autoptr (f3d_reader_info_t) readers = NULL;
  gint count = 0;

  f3d_engine_autoload_plugins ();

  if (!(readers = f3d_engine_get_readers_info (&count)))
    {
      return NULL;
    }

  for (gint i = 0; i < count; i++)
    {
      if (readers[i].mime_types)
        {
          for (gchar **mime = readers[i].mime_types; *mime != NULL; mime++)
            {
              g_ptr_array_add (array, g_strdup (*mime));
            }
        }
    }

  g_ptr_array_add (array, NULL);
  return (gchar **) g_ptr_array_free (g_steal_pointer (&array), FALSE);
}
