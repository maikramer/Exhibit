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

#include <f3d/engine_c_api.h>

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
