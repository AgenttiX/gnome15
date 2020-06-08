from __future__ import print_function
import gi
# from gi.repository import Cairo
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import Gtk
from gi.repository import Pango

# print(dir(Gtk.WrapMode))
# print(dir(Pango))
# print(dir(Pango.Alignment))
# print(dir(Gtk.Align))
# print(dir(Gtk.Align))
# print(dir(Gtk.Expander))

# gi.require_foreign("cairo")
# from gi.repository import cairo
# print(dir(cairo))
# print(dir(cairo.Context))

import cairo
from gi.repository import GConf
from gi.repository import Gst
from gi.repository import GstBase
from gi.repository import PangoCairo


def find_name(obj, name):
    lst = []
    name_lower = name.lower()
    for elem in dir(obj):
        if name_lower in elem.lower():
            lst.append(elem)
        for sub_elem in dir(getattr(obj, elem)):
            if name_lower in sub_elem.lower():
                lst.append(elem + " -> " + sub_elem)
    return lst


def save_contents(obj, path):
    f = open(path, "w")
    lst = dir(obj)
    f.write(str(obj))
    for name in lst:
        f.write(name + " " * (50 - len(name)) + " " + str(dir(getattr(obj, name))) + "\n")


def print_contents(obj):
    lst = dir(obj)
    print(obj)
    for name in lst:
        print(name, " " * (50 - len(name)), dir(getattr(obj, name)))


# out = find_name(Gst, "sink")
# for line in out:
#     print(line)

# save_contents(Gdk, "gdk.txt")
# print_contents(Gst)
# d = dir(GstBase)
# print(d)

save_contents(Gtk, "gtk.txt")
# print_contents(Gtk)
# print_contents(Pango)
