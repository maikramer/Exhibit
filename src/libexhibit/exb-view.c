/*
 * exb-view.c
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

#include "exb-engine.h"
#include "exb-engine-private.h"
#include "exb-view.h"

struct _ExbView {
    GtkGLArea parent_instance;
};

typedef struct
{
  ExbEngine *engine;
} ExbViewPrivate;

G_DEFINE_FINAL_TYPE_WITH_PRIVATE (ExbView, exb_view, GTK_TYPE_GL_AREA)

enum
{
  PROP_0,
  PROP_ENGINE,
  N_PROPS
};

static GParamSpec *properties[N_PROPS];

/**
 * exb_view_get_engine:
 * @self: a #ExbView
 *
 * Returns: (transfer none): The #ExbEngine
 */
ExbEngine *
exb_view_get_engine(ExbView *self)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);
  return priv->engine;
}

static void
exb_view_get_property (GObject    *object,
                       guint       prop_id,
                       GValue     *value,
                       GParamSpec *pspec)
{
  ExbView *self = EXB_VIEW (object);

  switch (prop_id)
    {
    case PROP_ENGINE:
      g_value_set_object (value, exb_view_get_engine (self));
      break;
    default:
      break;
    }
}

static void
exb_view_set_property (GObject      *object,
                       guint         prop_id,
                       const GValue *value,
                       GParamSpec   *pspec)
{
  ExbView *self = EXB_VIEW (object);

  switch (prop_id)
    {
    case PROP_ENGINE:
      /* exb_view_set_file (self, g_value_get_object (value)); */
      break;
    default:
      break;
    }
}

static void
exb_view_finalize (GObject *object)
{
  g_message ("ExbView: Finalizing");
  ExbView *self = EXB_VIEW (object);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_clear_object (&priv->engine);

  G_OBJECT_CLASS (exb_view_parent_class)->finalize (object);
}

static void
exb_view_realize (GtkWidget *widget)
{
  ExbView *self = EXB_VIEW (widget);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  _exb_engine_initialize (priv->engine, false);
}

static gboolean
exb_view_render(GtkGLArea    *gl_area,
                GdkGLContext *gl_context)
{
  ExbView *self = EXB_VIEW (gl_area);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);
  uint width, height;

  g_message ("rendering");

  gtk_gl_area_make_current (gl_area);

  width = gtk_widget_get_width (GTK_WIDGET (gl_area));
  height = gtk_widget_get_height (GTK_WIDGET (gl_area));

  exb_engine_set_size(priv->engine, width, height);

  exb_engine_render(priv->engine);

  return true;
}

static void
exb_view_init (ExbView *self)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_message ("ExbView: Initializing instance");

  gtk_gl_area_set_allowed_apis (GTK_GL_AREA (self), GDK_GL_API_GL);
  gtk_gl_area_set_has_depth_buffer (GTK_GL_AREA (self), TRUE);
  gtk_gl_area_set_auto_render (GTK_GL_AREA (self), TRUE);

  priv->engine = g_object_new (EXB_TYPE_ENGINE, NULL);

  g_signal_connect (self, "realize", G_CALLBACK (exb_view_realize), NULL);
  g_signal_connect (self, "render", G_CALLBACK (exb_view_render), NULL);
}

static void
exb_view_class_init (ExbViewClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->finalize = exb_view_finalize;
  object_class->get_property = exb_view_get_property;
  object_class->set_property = exb_view_set_property;

  properties[PROP_ENGINE] =
      g_param_spec_object ("engine",
                           NULL, NULL,
                           EXB_TYPE_ENGINE,
                           G_PARAM_READWRITE | G_PARAM_EXPLICIT_NOTIFY | G_PARAM_STATIC_STRINGS);

  g_object_class_install_properties (object_class, N_PROPS, properties);
}
