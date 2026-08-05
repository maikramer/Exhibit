/*
 * exb-debug.h
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

#include <glib.h>

#ifndef EXB_LOG_LEVEL_TRACE
# define EXB_LOG_LEVEL_TRACE ((GLogLevelFlags)(1 << G_LOG_LEVEL_USER_SHIFT))
#endif

/* Silent unless EXB_TRACE is set. Cached — property get/set is a hot path. */
static inline gboolean
exb_trace_enabled (void)
{
  static gssize cached = -1;

  if (G_UNLIKELY (cached < 0))
    cached = g_getenv ("EXB_TRACE") != NULL ? 1 : 0;
  return cached > 0;
}

# define EXB_ENTRY                                                       \
   G_STMT_START {                                                        \
     if (G_UNLIKELY (exb_trace_enabled ()))                              \
       g_log (G_LOG_DOMAIN, EXB_LOG_LEVEL_TRACE, "ENTRY: %s():%d",       \
              G_STRFUNC, __LINE__);                                      \
   } G_STMT_END
# define EXB_EXIT                                                        \
   G_STMT_START {                                                        \
     if (G_UNLIKELY (exb_trace_enabled ()))                              \
       g_log (G_LOG_DOMAIN, EXB_LOG_LEVEL_TRACE,                         \
              "EXIT: %s()" G_GINT64_FORMAT, G_STRFUNC);                  \
      return;                                                            \
   } G_STMT_END
# define EXB_RETURN(_r)                                                  \
   G_STMT_START {                                                        \
      __typeof__(_r) __trace_retval = (_r);                              \
      if (G_UNLIKELY (exb_trace_enabled ()))                             \
        g_log (G_LOG_DOMAIN, EXB_LOG_LEVEL_TRACE,                        \
               "EXIT: %s() = %" G_GINT64_FORMAT,                         \
               G_STRFUNC, (gint64) __trace_retval);                      \
      return __trace_retval;                                             \
   } G_STMT_END
