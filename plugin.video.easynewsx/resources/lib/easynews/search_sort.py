# -*- coding: utf-8 -*-
"""Easynews search result sort order (date / file size)."""
import xbmc
import xbmcgui

from resources.lib.easynews import context as ctx
from resources.lib.easynews import search_resolution

SETTING_ID = "general.date_sort_order"

# 0 date desc, 1 date asc, 2 size asc, 3 size desc
SORT_CHOICES = (
    (0, 33008, "dtime", "-"),
    (1, 33009, "dtime", "+"),
    (3, 33064, "dsize", "-"),
    (2, 33063, "dsize", "+"),
)


def get_search_sort_order():
    try:
        n = int(ctx.addon.getSetting(SETTING_ID) or 0)
    except Exception:
        n = 0
    if n not in (0, 1, 2, 3):
        return 0
    return n


def set_search_sort_order(value):
    try:
        n = int(value)
    except Exception:
        n = 0
    if n not in (0, 1, 2, 3):
        n = 0
    ctx.addon.setSetting(SETTING_ID, str(n))


def sort_display_name(order=None, brief=False):
    if order is None:
        order = get_search_sort_order()
    for val, sid, _field, _dir in SORT_CHOICES:
        if val == order:
            try:
                name = ctx.addon.getLocalizedString(sid)
            except Exception:
                name = ""
            if name:
                if brief:
                    name = name.replace(" (default)", "")
                return name
            break
    return "Post date newest first" if brief else "Post date newest first (default)"


def sort_dir_for_url(direction):
    """Encode + so query parsers do not treat s1d=+ as a space (web UI uses %2B)."""
    if direction == "+":
        return "%2B"
    return direction


def sort_api_query(order=None):
    """
    Easynews advanced search sort params (matches global5 web UI).

    Date-primary:  s1=dtime,  s2=nrfile, s3=dsize  (all share s1d)
    Size-primary:  s1=dsize,  s2=nrfile, s3=dsize  (all share s1d)
    """
    if order is None:
        order = get_search_sort_order()
    for val, _sid, field, direction in SORT_CHOICES:
        if val == order:
            return {
                "s1": field,
                "s1d": direction,
                "s2": "nrfile",
                "s2d": direction,
                "s3": "dsize",
                "s3d": direction,
            }
    return {
        "s1": "dtime",
        "s1d": "-",
        "s2": "nrfile",
        "s2d": "-",
        "s3": "dsize",
        "s3d": "-",
    }


def apply_search_sort_action(value, query="", newsgroup="", page="1"):
    set_search_sort_order(value)
    sort_name = sort_display_name(get_search_sort_order())
    if search_resolution._has_search_context(query):
        q_label = search_resolution.query_display_label(query)
        try:
            xbmcgui.Dialog().notification(
                "EasyNews",
                ctx.addon.getLocalizedString(33054) % (q_label, sort_name),
                xbmcgui.NOTIFICATION_INFO,
                3500,
            )
        except Exception:
            pass
        xbmc.sleep(100)
        xbmc.executebuiltin(
            "Container.Update({})".format(
                search_resolution.searchresults_plugin_url(query, newsgroup, "1")
            )
        )
        return
    try:
        xbmcgui.Dialog().notification(
            "EasyNews",
            "Sort: {}".format(sort_name),
            xbmcgui.NOTIFICATION_INFO,
            2500,
        )
    except Exception:
        pass
    xbmc.executebuiltin("Container.Refresh")
