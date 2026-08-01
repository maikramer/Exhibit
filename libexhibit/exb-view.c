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
#include "exb-debug.h"

struct _ExbView {
  GtkGLArea parent_instance;
};

typedef struct
{
  ExbEngine *engine;

  GtkGesture *drag_gesture;
  GtkGesture *zoom_gesture;
  GtkEventController *scroll_controller;

  bool always_point_up;
  bool interactive;

  double prev_scale;
  double drag_prev_x;
  double drag_prev_y;

  bool engine_is_initialized;

} ExbViewPrivate;

G_DEFINE_FINAL_TYPE_WITH_PRIVATE (ExbView, exb_view, GTK_TYPE_GL_AREA)

enum
{
  PROP_0,
  PROP_ENGINE,
  PROP_ALWAYS_POINT_UP,
  PROP_INTERACTIVE,
  N_PROPS
};

static GParamSpec *properties[N_PROPS];

void exb_view_set_engine (ExbView *self, ExbEngine *engine);

static void
exb_view_get_property (GObject    *object,
                       guint       prop_id,
                       GValue     *value,
                       GParamSpec *pspec G_GNUC_UNUSED)
{
  ExbView *self = EXB_VIEW (object);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_return_if_fail (EXB_IS_VIEW (self));

  switch (prop_id)
    {
    case PROP_ENGINE:
      g_value_set_object (value, exb_view_get_engine (self));
      break;

    case PROP_ALWAYS_POINT_UP:
      g_value_set_boolean (value, priv->always_point_up);
      break;

    case PROP_INTERACTIVE:
      g_value_set_boolean (value, priv->interactive);
      break;

    default:
      g_assert_not_reached ();
    }
}

static void
exb_view_set_property (GObject      *object,
                       guint         prop_id,
                       const GValue *value G_GNUC_UNUSED,
                       GParamSpec   *pspec G_GNUC_UNUSED)
{
  ExbView *self = EXB_VIEW (object);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_return_if_fail (EXB_IS_VIEW (self));

  switch (prop_id)
    {
    case PROP_ALWAYS_POINT_UP:
      priv->always_point_up = g_value_get_boolean (value);
      break;

    case PROP_INTERACTIVE:
      priv->interactive = g_value_get_boolean (value);
      break;

    case PROP_ENGINE:
      exb_view_set_engine (self, g_value_get_object (value));
      break;

    default:
      g_assert_not_reached ();
    }
}

static void
exb_view_dispose (GObject *object)
{
  ExbView *self = EXB_VIEW (object);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_return_if_fail (EXB_IS_VIEW (self));

  g_message ("ExbView: Finalizing");

  g_clear_object (&priv->engine);

  G_OBJECT_CLASS (exb_view_parent_class)->dispose (object);
}

static void
exb_view_realize (GtkWidget *widget)
{
  ExbView *self = EXB_VIEW (widget);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  EXB_ENTRY;

  if (!priv->engine_is_initialized)
    {
      _exb_engine_initialize (priv->engine);
      priv->engine_is_initialized = TRUE;
    }

  EXB_EXIT;
}

static void
exb_view_unrealize (GtkWidget *widget)
{
  ExbView *self = EXB_VIEW (widget);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  EXB_ENTRY;

  _exb_engine_finalize (priv->engine);
  priv->engine_is_initialized = FALSE;

  g_signal_connect_object (priv->engine, "changed",
                           G_CALLBACK (gtk_gl_area_queue_render), GTK_GL_AREA (self), G_CONNECT_SWAPPED);

  EXB_EXIT;
}

static gboolean
exb_view_render (GtkGLArea    *gl_area,
                 GdkGLContext *gl_context G_GNUC_UNUSED)
{
  ExbView *self = EXB_VIEW (gl_area);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);
  uint width, height;

  EXB_ENTRY;

  g_return_val_if_fail (EXB_IS_VIEW (self), TRUE);

  gtk_gl_area_make_current (gl_area);

  width = gtk_widget_get_width (GTK_WIDGET (gl_area));
  height = gtk_widget_get_height (GTK_WIDGET (gl_area));

  exb_engine_set_size (priv->engine, width, height);
  exb_engine_render (priv->engine);

  EXB_RETURN (TRUE);
}

static void
exb_view_snapshot (GtkWidget   *widget,
                   GtkSnapshot *snapshot)
{
  ExbView *self = EXB_VIEW (widget);
  ExbViewPrivate *priv = exb_view_get_instance_private (self);
  GdkRGBA color;

  if (priv->engine_is_initialized && !exb_engine_get_loading_file (priv->engine))
    {
       color = (GdkRGBA){ 0.0f, 0.0f, 0.0f, 1.0f };
    }
  else
    {
       color = (GdkRGBA){ 1.0f, 1.0f, 1.0f, 1.0f };
    }

  gtk_snapshot_append_color (snapshot,
                             &color,
                             &GRAPHENE_RECT_INIT (0, 0,
                                                  gtk_widget_get_width (widget),
                                                  gtk_widget_get_height (widget)));

  GTK_WIDGET_CLASS (exb_view_parent_class)->snapshot (widget, snapshot);
}

static gboolean
on_scroll (GtkEventControllerScroll *controller G_GNUC_UNUSED,
           gdouble                   dx G_GNUC_UNUSED,
           gdouble                   dy,
           ExbView                  *self)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_return_val_if_fail (EXB_IS_VIEW (self), TRUE);

  if (!priv->interactive)
    return TRUE;

  exb_engine_zoom (priv->engine, 1.0 - 0.1 * dy);

  gtk_gl_area_queue_render (GTK_GL_AREA (self));
  return TRUE;
}

static void
on_zoom_begin (ExbView *self)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_return_if_fail (EXB_IS_VIEW (self));

  priv->prev_scale = 1.0;
}

static void
on_zoom_changed (ExbView *self,
                 gdouble scale)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_return_if_fail (EXB_IS_VIEW (self));

  if (!priv->interactive)
    return;

  exb_engine_zoom (priv->engine, (scale - priv->prev_scale) * 0.1);

  priv->prev_scale = scale;

  gtk_gl_area_queue_render (GTK_GL_AREA (self));
}

static void
on_drag_begin (ExbView *self)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_message ("ExbView: drag begin");

  priv->drag_prev_x = 0;
  priv->drag_prev_y = 0;
}

static void
on_drag_update (ExbView        *self,
                gdouble         offset_x,
                gdouble         offset_y,
                GtkGestureDrag *gesture)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);
  double dx, dy;
  guint button;

  g_return_if_fail (EXB_IS_VIEW (self));

  if (!priv->interactive)
    return;

  dx = offset_x - priv->drag_prev_x;
  dy = offset_y - priv->drag_prev_y;

  g_message ("ExbView: drag: %f %f", dx, dy);

  button = gtk_gesture_single_get_current_button (GTK_GESTURE_SINGLE (gesture));

  if (button == 1)
    {
      if (!priv->always_point_up)
        exb_engine_rotate (priv->engine, dx, dy);
      else
        exb_engine_rotate_with_limit (priv->engine, dx, dy);
    }
  else if (button == 2)
    {
      exb_engine_pan (priv->engine, dx, dy);
    }

  gtk_gl_area_queue_render (GTK_GL_AREA (self));

  priv->drag_prev_x = offset_x;
  priv->drag_prev_y = offset_y;
}

static void
exb_view_init (ExbView *self)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_message ("ExbView: Initializing instance");
  g_return_if_fail (EXB_IS_VIEW (self));

  priv->always_point_up = TRUE;
  priv->interactive = TRUE;
  priv->engine_is_initialized = FALSE;

  gtk_gl_area_set_allowed_apis (GTK_GL_AREA (self), GDK_GL_API_GL);
  gtk_gl_area_set_has_depth_buffer (GTK_GL_AREA (self), TRUE);
  gtk_gl_area_set_auto_render (GTK_GL_AREA (self), TRUE);

  g_signal_connect_object (self, "realize",
                           G_CALLBACK (exb_view_realize), NULL, G_CONNECT_DEFAULT);
  g_signal_connect_object (self, "unrealize",
                           G_CALLBACK (exb_view_unrealize), NULL, G_CONNECT_DEFAULT);
  g_signal_connect_object (self, "render",
                           G_CALLBACK (exb_view_render), NULL, G_CONNECT_DEFAULT);

  priv->drag_gesture = gtk_gesture_drag_new ();
  gtk_gesture_single_set_button (GTK_GESTURE_SINGLE (priv->drag_gesture), 0);
  g_signal_connect_object (priv->drag_gesture, "drag-begin",
                           G_CALLBACK (on_drag_begin), self, G_CONNECT_SWAPPED);
  g_signal_connect_object (priv->drag_gesture, "drag-update",
                           G_CALLBACK (on_drag_update), self, G_CONNECT_SWAPPED);
  gtk_widget_add_controller (GTK_WIDGET (self),
                             GTK_EVENT_CONTROLLER (priv->drag_gesture));

  priv->zoom_gesture = gtk_gesture_zoom_new ();
  g_signal_connect_object (priv->zoom_gesture, "begin",
                           G_CALLBACK (on_zoom_begin), self, G_CONNECT_SWAPPED);
  g_signal_connect_object (priv->zoom_gesture, "scale-changed",
                           G_CALLBACK (on_zoom_changed), self, G_CONNECT_SWAPPED);
  gtk_widget_add_controller (GTK_WIDGET (self),
                             GTK_EVENT_CONTROLLER (priv->zoom_gesture));

  priv->scroll_controller =
      gtk_event_controller_scroll_new (GTK_EVENT_CONTROLLER_SCROLL_VERTICAL |
                                       GTK_EVENT_CONTROLLER_SCROLL_DISCRETE);
  g_signal_connect_object (priv->scroll_controller, "scroll",
                           G_CALLBACK (on_scroll), self, G_CONNECT_DEFAULT);
  gtk_widget_add_controller (GTK_WIDGET (self),
                             priv->scroll_controller);
}

static void
exb_view_class_init (ExbViewClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  GtkWidgetClass *widget_class = GTK_WIDGET_CLASS (klass);

  object_class->dispose = exb_view_dispose;
  object_class->get_property = exb_view_get_property;
  object_class->set_property = exb_view_set_property;
  widget_class->snapshot = exb_view_snapshot;

  properties[PROP_ENGINE] =
      g_param_spec_object ("engine",
                           NULL, NULL,
                           EXB_TYPE_ENGINE,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_ALWAYS_POINT_UP] =
      g_param_spec_boolean ("always-point-up",
                            NULL, NULL,
                            TRUE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_INTERACTIVE] =
      g_param_spec_boolean ("interactive",
                            NULL, NULL,
                            TRUE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  g_object_class_install_properties (object_class, N_PROPS, properties);
}

/**
 * exb_view_new:
 *
 * Returns: (transfer full): A new #ExbView
 */
ExbView *
exb_view_new (void)
{
  return g_object_new (EXB_TYPE_VIEW, NULL);
}

/**
 * exb_view_get_engine:
 * @self: a #ExbView
 *
 * Returns: (transfer none): The #ExbEngine
 */
ExbEngine *
exb_view_get_engine (ExbView *self)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);
  return priv->engine;
}

/**
 * exb_view_set_engine:
 * @self: a #ExbView
 * @engine: a #ExbEngine
 *
 */
void
exb_view_set_engine (ExbView   *self,
                     ExbEngine *engine)
{
  ExbViewPrivate *priv = exb_view_get_instance_private (self);

  g_return_if_fail (EXB_IS_VIEW (self));
  g_return_if_fail (EXB_IS_ENGINE (engine));

  g_set_object (&priv->engine, engine);

  priv->engine_is_initialized = FALSE;

  g_signal_connect_object (priv->engine, "changed",
                           G_CALLBACK (gtk_gl_area_queue_render),
                           GTK_GL_AREA (self),
                           G_CONNECT_SWAPPED);
}
