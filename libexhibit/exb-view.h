/*
 * exb-view.h
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

#include "exb-engine.h"

#include <gtk/gtk.h>

G_BEGIN_DECLS

#define EXB_TYPE_VIEW (exb_view_get_type())

G_DECLARE_FINAL_TYPE (ExbView, exb_view, EXB, VIEW, GtkGLArea)

ExbEngine * exb_view_get_engine (ExbView *self);

G_END_DECLS
