# -*- coding: utf-8 -*-
import sys
import json
from urllib.parse import urlencode, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]


def log(message, level=xbmc.LOGINFO):
    xbmc.log("[CODEX IPTV] {}".format(message), level)


def setting(key):
    return ADDON.getSetting(key).strip()


def credentials():
    server = setting("server").rstrip("/")
    username = setting("username")
    password = setting("password")
    return server, username, password


def configured():
    server, username, password = credentials()
    return bool(server and username and password)


def api_url(action=None, **params):
    server, username, password = credentials()
    query = {"username": username, "password": password}
    if action:
        query["action"] = action
    query.update(params)
    return "{}/player_api.php?{}".format(server, urlencode(query))


def api_get(action=None, **params):
    url = api_url(action, **params)
    req = Request(
        url,
        headers={
            "User-Agent": "CODEX-IPTV/0.1.0 Kodi",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=15) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return json.loads(payload)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        log("API error: {}".format(exc), xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "CODEX IPTV",
            "Unable to contact provider. Check settings.",
            xbmcgui.NOTIFICATION_ERROR,
            5000,
        )
        return None


def plugin_url(**params):
    return "{}?{}".format(BASE_URL, urlencode(params))


def add_folder(label, action, **params):
    item = xbmcgui.ListItem(label=label)
    item.setArt({"icon": "DefaultFolder.png"})
    params["action"] = action
    xbmcplugin.addDirectoryItem(
        HANDLE, plugin_url(**params), item, isFolder=True
    )


def add_action(label, action):
    item = xbmcgui.ListItem(label=label)
    item.setArt({"icon": "DefaultAddonService.png"})
    xbmcplugin.addDirectoryItem(
        HANDLE, plugin_url(action=action), item, isFolder=False
    )


def root_menu():
    xbmcplugin.setPluginCategory(HANDLE, "CODEX IPTV")

    if not configured():
        item = xbmcgui.ListItem(label="[B]Configure CODEX IPTV[/B]")
        item.setArt({"icon": "DefaultAddonService.png"})
        xbmcplugin.addDirectoryItem(
            HANDLE, plugin_url(action="settings"), item, isFolder=False
        )
        xbmcplugin.endOfDirectory(HANDLE)
        xbmcgui.Dialog().notification(
            "CODEX IPTV",
            "Enter your provider details in Settings.",
            xbmcgui.NOTIFICATION_INFO,
            5000,
        )
        return

    add_folder("Live TV", "live_categories")
    add_action("Test Connection", "test_connection")
    add_action("Settings", "settings")
    xbmcplugin.endOfDirectory(HANDLE)


def live_categories():
    data = api_get("get_live_categories")
    if not isinstance(data, list):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    xbmcplugin.setPluginCategory(HANDLE, "Live TV")
    for category in data:
        category_id = str(category.get("category_id", ""))
        name = category.get("category_name") or "Unnamed category"
        if category_id:
            add_folder(name, "live_streams", category_id=category_id)

    xbmcplugin.endOfDirectory(HANDLE)


def live_streams(category_id):
    data = api_get("get_live_streams", category_id=category_id)
    if not isinstance(data, list):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    server, username, password = credentials()
    xbmcplugin.setPluginCategory(HANDLE, "Channels")
    xbmcplugin.setContent(HANDLE, "videos")

    for stream in data:
        stream_id = str(stream.get("stream_id", ""))
        if not stream_id:
            continue

        name = stream.get("name") or "Unnamed channel"
        logo = stream.get("stream_icon") or ""
        extension = setting("stream_extension") or "ts"

        play_url = "{}/live/{}/{}/{}.{}".format(
            server, username, password, stream_id, extension
        )

        item = xbmcgui.ListItem(label=name)
        item.setProperty("IsPlayable", "true")
        item.setInfo("video", {"title": name, "mediatype": "video"})
        if logo:
            item.setArt({"thumb": logo, "icon": logo})
        else:
            item.setArt({"icon": "DefaultVideo.png"})

        xbmcplugin.addDirectoryItem(
            HANDLE,
            plugin_url(action="play", url=play_url, title=name),
            item,
            isFolder=False,
        )

    xbmcplugin.endOfDirectory(HANDLE)


def play(url, title):
    item = xbmcgui.ListItem(path=url)
    item.setLabel(title)
    item.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def test_connection():
    data = api_get()
    if not isinstance(data, dict):
        return

    user_info = data.get("user_info") or {}
    auth = str(user_info.get("auth", "0"))

    if auth == "1":
        status = user_info.get("status", "Active")
        xbmcgui.Dialog().ok(
            "CODEX IPTV",
            "Connection successful.\n\nAccount status: {}".format(status),
        )
    else:
        xbmcgui.Dialog().ok(
            "CODEX IPTV",
            "Provider responded, but authentication failed.",
        )


def open_settings():
    ADDON.openSettings()
    xbmc.executebuiltin("Container.Refresh")


def route():
    params = dict(parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 else {}
    action = params.get("action", "")

    if not action:
        root_menu()
    elif action == "live_categories":
        live_categories()
    elif action == "live_streams":
        live_streams(params.get("category_id", ""))
    elif action == "play":
        play(params.get("url", ""), params.get("title", "CODEX IPTV"))
    elif action == "test_connection":
        test_connection()
    elif action == "settings":
        open_settings()
    else:
        xbmcgui.Dialog().notification(
            "CODEX IPTV",
            "Unknown action.",
            xbmcgui.NOTIFICATION_ERROR,
            3000,
        )


if __name__ == "__main__":
    route()
