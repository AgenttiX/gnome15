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

from gi.repository import Gtk as gtk

import gnome15.g15locale as g15locale
import gnome15.g15profile as g15profile
import gnome15.g15driver as g15driver
import gnome15.util.g15uigconf as g15uigconf
import gnome15.util.g15gconf as g15gconf
import gnome15.g15globals as g15globals
import gnome15.g15theme as g15theme
import gnome15.g15screen as g15screen
import gnome15.g15plugin as g15plugin

logger = logging.getLogger(__name__)
_ = g15locale.get_translation("macros", modfile=__file__).ugettext

# Plugin details - All of these must be provided
id = "macros"
name = _("Macro Information")
description = _("Displays the currently active macro profile and a summary of available keys.\
Also, the screen will be cycled to when a macro is activated and the key will be \
highlighted.")
author = "Brett Smith <tanktarta@blueyonder.co.uk>"
copyright = _("Copyright (C)2010 Brett Smith")
site = "http://www.russo79.com/gnome15"
has_preferences = True
unsupported_models = [g15driver.MODEL_G110, g15driver.MODEL_Z10, g15driver.MODEL_G11, g15driver.MODEL_MX5500,
                      g15driver.MODEL_G930, g15driver.MODEL_G35]
actions = {
    g15driver.PREVIOUS_SELECTION: _("Previous macro"),
    g15driver.NEXT_SELECTION: _("Next macro"),
    g15driver.NEXT_PAGE: _("Next page"),
    g15driver.PREVIOUS_PAGE: _("Previous page")
}


def create(gconf_key, gconf_client, screen):
    return G15Macros(gconf_client, gconf_key, screen)


def show_preferences(parent, driver, gconf_client, gconf_key):
    widget_tree = gtk.Builder()
    widget_tree.add_from_file(os.path.join(os.path.dirname(__file__), "macros.ui"))
    dialog = widget_tree.get_object("MacrosDialog")
    dialog.set_transient_for(parent)
    g15uigconf.configure_checkbox_from_gconf(gconf_client, "%s/raise" % gconf_key, "RaisePageCheckbox", True,
                                             widget_tree)
    dialog.run()
    dialog.hide()


"""
Represents a mount as a single item in a menu
"""


class MacroMenuItem(g15theme.MenuItem):
    def __init__(self, macro, component_id):
        g15theme.MenuItem.__init__(self, component_id)
        self.macro = macro

    def get_theme_properties(self):
        item_properties = g15theme.MenuItem.get_theme_properties(self)
        item_properties["item_name"] = self.macro.name
        item_properties["item_type"] = ""
        item_properties["item_key"] = ",".join(g15driver.get_key_names(self.macro.keys))
        for r in range(0, len(self.macro.keys)):
            item_properties["icon%d" % (r + 1)] = os.path.join(g15globals.image_dir, "key-%s.png" % self.macro.keys[r])
        return item_properties

    def get_default_theme_dir(self):
        return os.path.join(os.path.dirname(__file__), "default")

    def activate(self):
        pass


"""
Macros plugin class
"""


class G15Macros(g15plugin.G15MenuPlugin):

    def __init__(self, gconf_client, gconf_key, screen):
        g15plugin.G15MenuPlugin.__init__(self, gconf_client, gconf_key, screen,
                                         ["preferences-desktop-keyboard-shortcuts", "input-keyboard"], id, name)

    def activate(self):
        self._get_configuration()
        g15plugin.G15MenuPlugin.activate(self)
        self._notify_handles = []
        self._notify_handles.append(
            self.gconf_client.notify_add("/apps/gnome15/%s/active_profile" % self.screen.device.uid,
                                         self._profiles_changed))
        self._notify_handles.append(
            self.gconf_client.notify_add("/apps/gnome15/%s/locked" % self.screen.device.uid, self._profiles_changed))
        g15profile.profile_listeners.append(self._profiles_changed)
        self.listener = MacrosScreenChangeAdapter(self)
        self.screen.add_screen_change_listener(self.listener)

    def deactivate(self):
        g15plugin.G15MenuPlugin.deactivate(self)
        for h in self._notify_handles:
            self.gconf_client.notify_remove(h)
        g15profile.profile_listeners.remove(self._profiles_changed)
        self.screen.remove_screen_change_listener(self.listener)

    @staticmethod
    def get_theme_path():
        return os.path.join(os.path.dirname(__file__), "default")

    def get_theme_properties(self):
        properties = g15plugin.G15MenuPlugin.get_theme_properties(self)
        properties["title"] = self._active_profile.name
        properties["mkey"] = "M%d" % self._mkey
        properties["icon"] = self._get_active_profile_icon_path()
        return properties

    def _get_active_profile_icon_path(self):
        if self._active_profile is None:
            return None
        return self._active_profile.get_profile_icon_path(self.screen.height)

    """
    Screen change listener callbacks
    
    """

    def memory_bank_changed(self):
        g15screen.run_on_redraw(self._reload_and_popup)

    """
    Private functions
    """

    def _profiles_changed(self, arg0=None, arg1=None, arg2=None, arg3=None):
        self._reload_and_popup()

    def _reload(self):
        self.load_menu_items()
        self.screen.redraw(self.page)

    def _reload_and_popup(self):
        self._reload()
        if g15gconf.get_bool_or_default(self.gconf_client, "%s/raise" % self.gconf_key, True):
            self._popup()

    def load_menu_items(self):
        """
        Reload all items for the current profile and bank
        """
        self._get_configuration()
        self.menu.remove_all_children()
        self.page.set_title(_("Macros - %s") % self._active_profile.name)

        macro_keys = []
        macros = []
        self._load_profile(self._active_profile, macros, macro_keys)
        macros.sort(self._comparator)
        for macro in macros:
            self.menu.add_child(MacroMenuItem(macro, "macro-%s" % macro.key_list_key))

    def _load_profile(self, profile, macros, macro_keys):
        for bank in profile.macros.values():
            for m in bank[self._mkey - 1]:
                if m.keys not in macro_keys:
                    macros.append(m)
                    macro_keys.append(m.keys)
        if profile.base_profile is not None and profile.base_profile != "":
            self._load_profile(g15profile.get_profile(profile.device, profile.base_profile), macros, macro_keys)

    @staticmethod
    def _comparator(o1, o2):
        return o1.compare(o2)

    def _get_configuration(self):
        self._mkey = self.screen.get_memory_bank()
        self._active_profile = g15profile.get_active_profile(self.screen.device)

    def _popup(self):
        """
        Popup the page
        """
        self._raise_timer = self.screen.set_priority(self.page, g15screen.PRI_HIGH, revert_after=4.0)
        self.screen.redraw(self.page)

    def _remove_macro(self, macro):
        """
        Remove a macro from the menu
        """
        logger.info("Removing macro %s", str(macro.name))
        self.menu.remove_child(self._get_item_for_macro(macro))
        self.screen.redraw(self.page)

    def _get_item_for_macro(self, macro):
        """
        Get the menu item for the given macro
        """
        for item in self.menu.get_children():
            if isinstance(item, MacroMenuItem) and item.macro == macro:
                return item

    def _add_macro(self, macro):
        """
        Add a new macro to the menu
        """
        item = MacroMenuItem(macro, self, "macro-%s" % macro.key_list_key)
        self.menu.add_child(item)


class MacrosScreenChangeAdapter(g15screen.ScreenChangeAdapter):
    def __init__(self, plugin):
        self.plugin = plugin

    def memory_bank_changed(self, new_bank_number):
        self.plugin._get_configuration()
        self.plugin._reload()
        if g15gconf.get_bool_or_default(self.plugin.gconf_client, "%s/raise" % self.plugin.gconf_key, True):
            self.plugin._popup()
