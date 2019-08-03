#  Gnome15 - Suite of tools for the Logitech G series keyboards and headsets
#  Copyright (C) 2010 Brett Smith <tanktarta@blueyonder.co.uk>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
# import time

import dbus
# import gobject
import gtk
# from lxml import etree
# from PIL import Image

import gnome15.g15locale as g15locale
# import gnome15.g15globals as g15globals
import gnome15.g15screen as g15screen
# import gnome15.util.g15convert as g15convert
import gnome15.util.g15uigconf as g15uigconf
import gnome15.util.g15gconf as g15gconf
import gnome15.util.g15cairo as g15cairo
import gnome15.util.g15icontools as g15icontools
import gnome15.g15theme as g15theme
import gnome15.g15driver as g15driver
import gnome15.g15plugin as g15plugin
import gnome15.dbusmenu as dbusmenu

logger = logging.getLogger(__name__)
_ = g15locale.get_translation("indicator-messages", modfile=__file__).ugettext

# Only works in Unity
if "XDG_CURRENT_DESKTOP" not in os.environ or os.environ["XDG_CURRENT_DESKTOP"] != "Unity":
    raise Exception("Only works in Ubuntu Unity desktop")

# Plugin details - All of these must be provided
id = "indicator-messages"
name = _("Indicator Messages")
description = _("Indicator that shows waiting messages.")
author = "Brett Smith <tanktarta@blueyonder.co.uk>"
copyright = _("Copyright (C)2010 Brett Smith")
site = "http://www.russo79.com/gnome15"
has_preferences = True
unsupported_models = [g15driver.MODEL_G110, g15driver.MODEL_G11, g15driver.MODEL_G930, g15driver.MODEL_G35]
actions = {
    g15driver.PREVIOUS_SELECTION: _("Previous item"),
    g15driver.NEXT_SELECTION: _("Next item"),
    g15driver.NEXT_PAGE: _("Next page"),
    g15driver.PREVIOUS_PAGE: _("Previous page"),
    g15driver.SELECT: _("Activate item")
}


def create(gconf_key, gconf_client, screen):
    return G15IndicatorMessages(gconf_client, gconf_key, screen)


"""
Indicator Messages  DBUSMenu property names
"""

APP_RUNNING = "app-running"
INDICATOR_LABEL = "indicator-label"
INDICATOR_ICON = "indicator-icon"
RIGHT_SIDE_TEXT = "right-side-text"

"""
Indicator Messages DBUSMenu types
"""
TYPE_APPLICATION_ITEM = "application-item"
TYPE_INDICATOR_ITEM = "indicator-item"


def show_preferences(parent, driver, gconf_client, gconf_key):
    widget_tree = gtk.Builder()
    widget_tree.add_from_file(os.path.join(os.path.dirname(__file__), "indicator-messages.ui"))
    dialog = widget_tree.get_object("IndicatorMessagesDialog")
    dialog.set_transient_for(parent)
    g15uigconf.configure_checkbox_from_gconf(gconf_client, "%s/raise" % gconf_key, "RaisePageCheckbox", True,
                                             widget_tree)
    dialog.run()
    dialog.hide()


class IndicatorMessagesMenuEntry(dbusmenu.DBUSMenuEntry):
    def __init__(self, id, properties, menu):
        dbusmenu.DBUSMenuEntry.__init__(self, id, properties, menu)

    def set_properties(self, properties):
        dbusmenu.DBUSMenuEntry.set_properties(self, properties)
        if self.type == TYPE_INDICATOR_ITEM and INDICATOR_LABEL in self.properties:
            self.label = self.properties[INDICATOR_LABEL]
        if self.type == TYPE_INDICATOR_ITEM:
            self.icon = self.properties[INDICATOR_ICON] if INDICATOR_ICON in self.properties else None

    def get_alt_label(self):
        return self.properties[RIGHT_SIDE_TEXT] if RIGHT_SIDE_TEXT in self.properties else ""

    def is_app_running(self):
        return APP_RUNNING in self.properties and self.properties[APP_RUNNING]


class IndicatorMessagesMenu(dbusmenu.DBUSMenu):
    def __init__(self, session_bus, on_change=None):
        try:
            dbusmenu.DBUSMenu.__init__(self, session_bus, "com.canonical.indicator.messages",
                                       "/com/canonical/indicator/messages/menu", "com.canonical.dbusmenu", on_change,
                                       True)
        except dbus.DBusException as dbe:
            logger.debug("Could not create DBUS menu, trying alternative", exc_info=dbe)
            dbusmenu.DBUSMenu.__init__(self, session_bus, "org.ayatana.indicator.messages",
                                       "/org/ayatana/indicator/messages/menu", "org.ayatana.dbusmenu", on_change, False)

    def create_entry(self, id, properties):
        return IndicatorMessagesMenuEntry(id, properties, self)


class G15IndicatorMessages(g15plugin.G15MenuPlugin):
    def __init__(self, gconf_client, gconf_key, screen):
        g15plugin.G15MenuPlugin.__init__(self, gconf_client, gconf_key, screen, ["indicator-messages"], id, name)
        self._hide_timer = None
        self._session_bus = None
        self._gconf_client = gconf_client
        self._session_bus = dbus.SessionBus()

    def activate(self):
        self._status_icon = None
        self._raise_timer = None
        self._attention = False
        self._light_control = None

        g15plugin.G15MenuPlugin.activate(self)

        # Start listening for events
        if self._messages_menu.natty:
            self._session_bus.add_signal_receiver(self._icon_changed,
                                                  dbus_interface="com.canonical.indicator.messages.service",
                                                  signal_name="IconChanged")
            self._session_bus.add_signal_receiver(self._attention_changed,
                                                  dbus_interface="com.canonical.indicator.messages.service",
                                                  signal_name="AttentionChanged")
        else:
            self._session_bus.add_signal_receiver(self._icon_changed,
                                                  dbus_interface="org.ayatana.indicator.messages.service",
                                                  signal_name="IconChanged")
            self._session_bus.add_signal_receiver(self._attention_changed,
                                                  dbus_interface="org.ayatana.indicator.messages.service",
                                                  signal_name="AttentionChanged")

    def create_menu(self):
        self._messages_menu = IndicatorMessagesMenu(self._session_bus)
        self._messages_menu.on_change = self._menu_changed
        self._check_status()
        return g15theme.DBusMenu(self._messages_menu)

    def deactivate(self):
        g15plugin.G15MenuPlugin.deactivate(self)
        self._stop_blink()
        if self._messages_menu.natty:
            self._session_bus.remove_signal_receiver(self._icon_changed,
                                                     dbus_interface="com.canonical.indicator.messages.service",
                                                     signal_name="IconChanged")
            self._session_bus.remove_signal_receiver(self._attention_changed,
                                                     dbus_interface="com.canonical.indicator.messages.service",
                                                     signal_name="AttentionChanged")
        else:
            self._session_bus.remove_signal_receiver(self._icon_changed,
                                                     dbus_interface="org.ayatana.indicator.messages.service",
                                                     signal_name="IconChanged")
            self._session_bus.remove_signal_receiver(self._attention_changed,
                                                     dbus_interface="org.ayatana.indicator.messages.service",
                                                     signal_name="AttentionChanged")

    def create_page(self):
        page = g15plugin.G15MenuPlugin.create_page(self)
        page.panel_painter = self._paint_panel
        return page

    def get_theme_properties(self):
        return {
            "title": _("Messages"),
            "alt_title": "",
            "icon": g15icontools.get_icon_path("indicator-messages-new" if self._attention else "indicator-messages"),
            "attention": self._attention
        }

    """
    Messages Service callbacks
    """

    def _icon_changed(self, new_icon):
        pass

    def _attention_changed(self, attention):
        self._attention = attention
        if self._attention == 1:
            self._start_blink()
            if self.screen.driver.get_bpp() == 1:
                self.thumb_icon = g15cairo.load_surface_from_file(
                    os.path.join(os.path.dirname(__file__), "mono-mail-new.gif"))
            else:
                self.thumb_icon = g15cairo.load_surface_from_file(g15icontools.get_icon_path("indicator-messages-new"))
            self._popup()
        else:
            self._stop_blink()
            if self.screen.driver.get_bpp() == 16:
                self.thumb_icon = g15cairo.load_surface_from_file(g15icontools.get_icon_path("indicator-messages"))
            self.screen.redraw()

    def _menu_changed(self, menu=None, property=None, value=None):
        #        self._messages_menu.menu_changed(menu, property, value)
        self._popup()

    def _check_status(self):
        """
        indicator-messages replaces indicator-me from Oneiric, so we get the current status icon if available
        to show that on the panel too
        """
        self._status_icon = None
        for c in self._messages_menu.menu_map:
            menu_entry = self._messages_menu.menu_map[c]
            if menu_entry.toggle_type == dbusmenu.TOGGLE_TYPE_RADIO and menu_entry.toggle_state == 1:
                icon_name = menu_entry.get_icon_name()
                if icon_name is not None and \
                        icon_name in ["user-available", "user-away",
                                      "user-busy", "user-offline",
                                      "user-invisible", "user-indeterminate"]:
                    self._status_icon = g15cairo.load_surface_from_file(g15icontools.get_icon_path(icon_name))

    """
    Private
    """

    def _start_blink(self):
        if not self._light_control:
            self._light_control = self.screen.driver.acquire_control_with_hint(g15driver.HINT_MKEYS,
                                                                               val=g15driver.MKEY_LIGHT_1 | g15driver.MKEY_LIGHT_2 | g15driver.MKEY_LIGHT_3)
            self._light_control.blink(off_val=self._get_mkey_value)

    def _get_mkey_value(self):
        return g15driver.get_mask_for_memory_bank(self.screen.get_memory_bank())

    def _stop_blink(self):
        if self._light_control:
            self.screen.driver.release_control(self._light_control)
            self._light_control = None

    def _popup(self):
        self._check_status()
        if g15gconf.get_bool_or_default(self.gconf_client, "%s/raise" % self.gconf_key, True):
            if not self.page.is_visible():
                self._raise_timer = self.screen.set_priority(self.page, g15screen.PRI_HIGH, revert_after=4.0)
                self.screen.redraw(self.page)
            else:
                self._reset_raise()

    def _reset_raise(self):
        """
        Reset the timer if the page is already visible because of a timer
        """
        if self.screen.is_on_timer(self.page):
            self._raise_timer = self.screen.set_priority(self.page, g15screen.PRI_HIGH, revert_after=4.0)
        self.screen.redraw(self.page)

    def _paint_panel(self, canvas, allocated_size, horizontal):
        if self.page is not None:
            t = 0
            if self.thumb_icon is not None and self._attention == 1:
                t += g15cairo.paint_thumbnail_image(allocated_size, self.thumb_icon, canvas)
            if self._status_icon is not None:
                t += g15cairo.paint_thumbnail_image(allocated_size, self._status_icon, canvas)
            return t
