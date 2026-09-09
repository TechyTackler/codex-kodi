# -*- coding: utf-8 -*-

import base64
import json
import sys
import time

from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin


# ============================================================
# CODEX IPTV
# ============================================================

ADDON = xbmcaddon.Addon()

HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_VERSION = ADDON.getAddonInfo("version")
ADDON_PATH = ADDON.getAddonInfo("path")
ADDON_ICON = ADDON.getAddonInfo("icon")
ADDON_FANART = ADDON.getAddonInfo("fanart")


# ============================================================
# LOGGING / SETTINGS
# ============================================================

def log(message, level=xbmc.LOGINFO):
    xbmc.log(
        "[CODEX IPTV] {}".format(message),
        level,
    )


def setting(key):
    return ADDON.getSetting(key).strip()


def credentials():
    server = setting("server").rstrip("/")
    username = setting("username")
    password = setting("password")

    return server, username, password


def configured():
    server, username, password = credentials()

    return bool(
        server
        and username
        and password
    )


# ============================================================
# PROVIDER API
# ============================================================

def api_url(action=None, **params):
    server, username, password = credentials()

    query = {
        "username": username,
        "password": password,
    }

    if action:
        query["action"] = action

    query.update(params)

    return "{}/player_api.php?{}".format(
        server,
        urlencode(query),
    )


def api_get(action=None, **params):
    url = api_url(
        action,
        **params
    )

    req = Request(
        url,
        headers={
            "User-Agent": (
                "CODEX-IPTV/{} Kodi"
            ).format(
                ADDON_VERSION
            ),
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(
            req,
            timeout=15,
        ) as response:
            payload = response.read().decode(
                "utf-8",
                errors="replace",
            )

            return json.loads(
                payload
            )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
    ) as exc:
        log(
            "API error: {}".format(exc),
            xbmc.LOGERROR,
        )

        xbmcgui.Dialog().notification(
            ADDON_NAME,
            (
                "Unable to contact provider. "
                "Check your connection and settings."
            ),
            xbmcgui.NOTIFICATION_ERROR,
            5000,
        )

        return None



# ============================================================
# EPG
# ============================================================

def decode_epg_text(value):
    """
    Decode Base64-encoded EPG text safely.

    Some Xtream providers return plain text while others return
    Base64-encoded titles and descriptions, so this helper
    tolerates both formats.
    """
    if value in (None, ""):
        return ""

    raw_value = (
        value
        if isinstance(value, bytes)
        else str(value).encode("utf-8", errors="ignore")
    )

    try:
        padding = (4 - (len(raw_value) % 4)) % 4

        if padding:
            raw_value += b"=" * padding

        decoded = base64.b64decode(
            raw_value,
            validate=True,
        ).decode(
            "utf-8",
            errors="replace",
        )

        if decoded.strip():
            return decoded.strip()

    except (
        ValueError,
        UnicodeDecodeError,
        base64.binascii.Error,
    ):
        pass

    return str(value).strip()


def format_epg_time(value):
    """
    Format an Xtream EPG date/time value for the CODEX UI.
    """
    if not value:
        return ""

    try:
        parsed = datetime.strptime(
            str(value),
            "%Y-%m-%d %H:%M:%S",
        )

        return parsed.strftime("%H:%M")

    except (
        TypeError,
        ValueError,
    ):
        return ""


def epg_progress(
    start_timestamp,
    stop_timestamp,
    now_timestamp=None,
):
    """
    Return programme progress as an integer percentage from 0-100.
    """
    start = safe_int(start_timestamp, 0)
    stop = safe_int(stop_timestamp, 0)

    if not start or not stop or stop <= start:
        return 0

    now_value = (
        safe_int(now_timestamp, 0)
        if now_timestamp is not None
        else int(time.time())
    )

    if now_value <= start:
        return 0

    if now_value >= stop:
        return 100

    elapsed = now_value - start
    duration = stop - start

    return max(
        0,
        min(
            100,
            int(round((elapsed / float(duration)) * 100)),
        ),
    )


def normalise_epg_listing(listing):
    """
    Convert one provider EPG listing into a CODEX-friendly structure.
    """
    if not isinstance(listing, dict):
        return {}

    start_value = listing.get("start") or ""
    end_value = listing.get("end") or ""

    return {
        "id": str(listing.get("id", "")),
        "epg_id": str(listing.get("epg_id", "")),
        "channel_id": str(listing.get("channel_id", "")),
        "stream_id": str(listing.get("stream_id", "")),
        "title": decode_epg_text(listing.get("title", "")),
        "description": decode_epg_text(
            listing.get("description", "")
        ),
        "start": str(start_value),
        "end": str(end_value),
        "start_time": format_epg_time(start_value),
        "end_time": format_epg_time(end_value),
        "start_timestamp": safe_int(
            listing.get("start_timestamp"),
            0,
        ),
        "stop_timestamp": safe_int(
            listing.get("stop_timestamp"),
            0,
        ),
    }


def get_short_epg(
    stream_id,
    limit=4,
):
    """
    Retrieve and normalise the short EPG window for one live stream.

    Provider order is preserved.
    """
    if not stream_id:
        return []

    data = api_get(
        "get_short_epg",
        stream_id=stream_id,
        limit=limit,
    )

    if not isinstance(data, dict):
        return []

    listings = data.get("epg_listings") or []

    if not isinstance(listings, list):
        return []

    normalised = []

    for listing in listings:
        item = normalise_epg_listing(listing)

        if item:
            normalised.append(item)

    return normalised


def get_now_next_epg(
    stream_id,
    limit=4,
    now_timestamp=None,
):
    """
    Return CODEX Now / Next EPG data for one live stream.

    The current programme is determined from provider timestamps.
    The next programme is the first future listing after it.
    """
    listings = get_short_epg(
        stream_id,
        limit=limit,
    )

    current_time = (
        safe_int(now_timestamp, 0)
        if now_timestamp is not None
        else int(time.time())
    )

    current_programme = None
    next_programme = None

    for listing in listings:
        start = safe_int(
            listing.get("start_timestamp"),
            0,
        )
        stop = safe_int(
            listing.get("stop_timestamp"),
            0,
        )

        if start and stop and start <= current_time < stop:
            current_programme = listing
            continue

        if start and start > current_time and next_programme is None:
            next_programme = listing

    if current_programme and next_programme is None:
        current_stop = safe_int(
            current_programme.get("stop_timestamp"),
            0,
        )

        for listing in listings:
            start = safe_int(
                listing.get("start_timestamp"),
                0,
            )

            if start and current_stop and start >= current_stop:
                next_programme = listing
                break

    if current_programme:
        current_programme = dict(current_programme)
        current_programme["progress"] = epg_progress(
            current_programme.get("start_timestamp"),
            current_programme.get("stop_timestamp"),
            now_timestamp=current_time,
        )

    return {
        "available": bool(
            current_programme
            or next_programme
        ),
        "now": current_programme,
        "next": next_programme,
        "listings": listings,
    }


# ============================================================
# GENERAL HELPERS
# ============================================================

def plugin_url(**params):
    return "{}?{}".format(
        BASE_URL,
        urlencode(params),
    )


def safe_int(value, default=0):
    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def first_value(*values):
    for value in values:
        if value not in (
            None,
            "",
            [],
            {},
        ):
            return value

    return ""


def first_backdrop(value):
    if isinstance(
        value,
        list,
    ):
        for item in value:
            if item:
                return item

        return ""

    if isinstance(
        value,
        str,
    ):
        return value

    return ""


def year_from_date(value):
    if not value:
        return 0

    try:
        return int(
            str(value)[:4]
        )

    except (
        TypeError,
        ValueError,
    ):
        return 0


def format_unix_date(value):
    timestamp = safe_int(
        value,
        0,
    )

    if not timestamp:
        return ""

    try:
        return datetime.fromtimestamp(
            timestamp
        ).strftime(
            "%d %B %Y"
        )

    except (
        ValueError,
        OSError,
        OverflowError,
    ):
        return ""


def cast_to_tuples(value):
    if not value:
        return []

    if isinstance(
        value,
        list,
    ):
        cast = []

        for entry in value:
            if isinstance(
                entry,
                (list, tuple),
            ):
                if not entry:
                    continue

                name = str(
                    entry[0]
                ).strip()

                role = (
                    str(
                        entry[1]
                    ).strip()
                    if len(entry) > 1
                    else ""
                )

                if name:
                    cast.append(
                        (
                            name,
                            role,
                        )
                    )

            elif isinstance(
                entry,
                dict,
            ):
                name = str(
                    first_value(
                        entry.get("name"),
                        entry.get("actor"),
                    )
                ).strip()

                role = str(
                    first_value(
                        entry.get("role"),
                        entry.get("character"),
                    )
                ).strip()

                if name:
                    cast.append(
                        (
                            name,
                            role,
                        )
                    )

            else:
                name = str(
                    entry
                ).strip()

                if name:
                    cast.append(
                        (
                            name,
                            "",
                        )
                    )

        return cast

    return [
        (
            name.strip(),
            "",
        )
        for name in str(
            value
        ).split(",")
        if name.strip()
    ]


def base_art(
    icon=None,
    thumb=None,
    poster=None,
    fanart=None,
    landscape=None,
):
    art = {}

    icon = first_value(
        icon,
        thumb,
        poster,
        ADDON_ICON,
    )

    thumb = first_value(
        thumb,
        poster,
        icon,
        ADDON_ICON,
    )

    fanart = first_value(
        fanart,
        landscape,
        ADDON_FANART,
    )

    if icon:
        art["icon"] = icon

    if thumb:
        art["thumb"] = thumb

    if poster:
        art["poster"] = poster

    if fanart:
        art["fanart"] = fanart

    if landscape:
        art["landscape"] = landscape

    return art


def apply_art(item, art=None):
    final_art = {
        "icon": ADDON_ICON,
        "thumb": ADDON_ICON,
        "fanart": ADDON_FANART,
    }

    if art:
        final_art.update(
            {
                key: value
                for key, value in art.items()
                if value
            }
        )

    item.setArt(
        final_art
    )


def add_folder(
    label,
    action,
    art=None,
    info=None,
    **params
):
    item = xbmcgui.ListItem(
        label=label
    )

    apply_art(
        item,
        art,
    )

    if info:
        item.setInfo(
            "video",
            info,
        )

    params["action"] = action

    xbmcplugin.addDirectoryItem(
        HANDLE,
        plugin_url(
            **params
        ),
        item,
        isFolder=True,
    )


def add_action(
    label,
    action,
    art=None,
    info=None,
    **params
):
    item = xbmcgui.ListItem(
        label=label
    )

    apply_art(
        item,
        art,
    )

    if info:
        item.setInfo(
            "video",
            info,
        )

    params["action"] = action

    xbmcplugin.addDirectoryItem(
        HANDLE,
        plugin_url(
            **params
        ),
        item,
        isFolder=False,
    )


# ============================================================
# CODEX HOME
# ============================================================

def root_menu():
    xbmcplugin.setPluginCategory(
        HANDLE,
        "CODEX IPTV",
    )

    if not configured():
        item = xbmcgui.ListItem(
            label="[B]Configure CODEX IPTV[/B]"
        )

        apply_art(
            item,
            base_art(),
        )

        item.setInfo(
            "video",
            {
                "title": (
                    "Configure CODEX IPTV"
                ),
                "plot": (
                    "Enter the connection details "
                    "for your authorised "
                    "Xtream-compatible IPTV service."
                ),
            },
        )

        xbmcplugin.addDirectoryItem(
            HANDLE,
            plugin_url(
                action="settings"
            ),
            item,
            isFolder=False,
        )

        xbmcplugin.endOfDirectory(
            HANDLE
        )

        xbmcgui.Dialog().notification(
            ADDON_NAME,
            (
                "Enter your provider details "
                "in Settings."
            ),
            xbmcgui.NOTIFICATION_INFO,
            5000,
        )

        return

    add_folder(
        "Live TV",
        "live_categories",
        art=base_art(),
        info={
            "title": "Live TV",
            "plot": (
                "Browse live television channels "
                "from your configured provider."
            ),
        },
    )

    add_folder(
        "Movies",
        "movie_categories",
        art=base_art(),
        info={
            "title": "Movies",
            "plot": (
                "Browse the movie catalogue "
                "available from your provider."
            ),
        },
    )

    add_folder(
        "TV Shows",
        "series_categories",
        art=base_art(),
        info={
            "title": "TV Shows",
            "plot": (
                "Browse television series, seasons "
                "and episodes."
            ),
        },
    )

    add_folder(
        "Favourites",
        "favourites",
        art=base_art(),
        info={
            "title": "Favourites",
            "plot": (
                "Quick access to favourite "
                "CODEX content."
            ),
        },
    )

    add_action(
        "Search",
        "search",
        art=base_art(),
        info={
            "title": "Search",
            "plot": (
                "Search across CODEX IPTV content."
            ),
        },
    )

    add_action(
        "Refresh CODEX",
        "refresh",
        art=base_art(),
        info={
            "title": "Refresh CODEX",
            "plot": (
                "Reload the current CODEX view."
            ),
        },
    )

    add_action(
        "Settings",
        "settings",
        art=base_art(),
        info={
            "title": "Settings",
            "plot": (
                "Open CODEX IPTV provider "
                "and playback settings."
            ),
        },
    )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


# ============================================================
# LIVE TV
# ============================================================

def live_categories():
    data = api_get(
        "get_live_categories"
    )

    if not isinstance(
        data,
        list,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        "Live TV",
    )

    # Provider order is deliberately preserved.
    # No sorting or custom window handling is performed.
    for category in data:
        category_id = str(
            category.get(
                "category_id",
                "",
            )
        )

        name = (
            category.get(
                "category_name"
            )
            or "Unnamed category"
        )

        if not category_id:
            continue

        add_folder(
            name,
            "live_streams",
            art=base_art(),
            info={
                "title": name,
                "plot": (
                    "Browse live channels "
                    "in {}."
                ).format(
                    name
                ),
            },
            category_id=category_id,
            category_name=name,
        )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def live_streams(
    category_id,
    category_name="Channels",
):
    data = api_get(
        "get_live_streams",
        category_id=category_id,
    )

    if not isinstance(
        data,
        list,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    server, username, password = credentials()

    extension = (
        setting(
            "stream_extension"
        )
        or "ts"
    )

    xbmcplugin.setPluginCategory(
        HANDLE,
        category_name or "Channels",
    )

    xbmcplugin.setContent(
        HANDLE,
        "videos",
    )

    # Provider order is deliberately preserved.
    # EPG helpers remain available but are intentionally not
    # called in this clean baseline.
    for stream in data:
        stream_id = str(
            stream.get(
                "stream_id",
                "",
            )
        )

        if not stream_id:
            continue

        name = (
            stream.get("name")
            or "Unnamed channel"
        )

        logo = (
            stream.get(
                "stream_icon"
            )
            or ""
        )

        play_url = (
            "{}/live/{}/{}/{}.{}".format(
                server,
                username,
                password,
                stream_id,
                extension,
            )
        )

        item = xbmcgui.ListItem(
            label=name
        )

        item.setProperty(
            "IsPlayable",
            "true",
        )

        item.setInfo(
            "video",
            {
                "title": name,
                "mediatype": "video",
            },
        )

        apply_art(
            item,
            base_art(
                icon=logo,
                thumb=logo,
                fanart=ADDON_FANART,
            ),
        )

        xbmcplugin.addDirectoryItem(
            HANDLE,
            plugin_url(
                action="play",
                url=play_url,
                title=name,
            ),
            item,
            isFolder=False,
        )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


# ============================================================
# MOVIES
# ============================================================

def movie_categories():
    data = api_get(
        "get_vod_categories"
    )

    if not isinstance(
        data,
        list,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        "Movies",
    )

    for category in data:
        category_id = str(
            category.get(
                "category_id",
                "",
            )
        )

        name = (
            category.get(
                "category_name"
            )
            or "Unnamed category"
        )

        if category_id:
            add_folder(
                name,
                "movie_list",
                art=base_art(),
                info={
                    "title": name,
                    "plot": (
                        "Browse movies in {}."
                    ).format(
                        name
                    ),
                },
                category_id=category_id,
                category_name=name,
            )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def movie_list(
    category_id,
    category_name="Movies",
):
    data = api_get(
        "get_vod_streams",
        category_id=category_id,
    )

    if not isinstance(
        data,
        list,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        category_name or "Movies",
    )

    xbmcplugin.setContent(
        HANDLE,
        "movies",
    )

    for movie in data:
        stream_id = str(
            movie.get(
                "stream_id",
                "",
            )
        )

        if not stream_id:
            continue

        name = (
            movie.get("name")
            or "Unnamed movie"
        )

        poster = first_value(
            movie.get(
                "stream_icon"
            ),
            movie.get(
                "cover"
            ),
        )

        backdrop = first_backdrop(
            movie.get(
                "backdrop_path"
            )
        )

        plot = first_value(
            movie.get("plot"),
            movie.get(
                "description"
            ),
        )

        genre = (
            movie.get("genre")
            or ""
        )

        year = safe_int(
            movie.get("year"),
            0,
        )

        rating = safe_float(
            movie.get("rating"),
            0.0,
        )

        art = base_art(
            icon=poster,
            thumb=poster,
            poster=poster,
            fanart=backdrop,
            landscape=backdrop,
        )

        info = {
            "title": name,
            "mediatype": "movie",
            "plot": plot,
        }

        if year:
            info["year"] = year

        if rating:
            info["rating"] = rating

        if genre:
            info["genre"] = genre

        add_folder(
            name,
            "movie_details",
            art=art,
            info=info,
            vod_id=stream_id,
            fallback_title=name,
        )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def movie_details(
    vod_id,
    fallback_title,
):
    data = api_get(
        "get_vod_info",
        vod_id=vod_id,
    )

    if not isinstance(
        data,
        dict,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    info_data = (
        data.get("info")
        or {}
    )

    movie_data = (
        data.get("movie_data")
        or {}
    )

    server, username, password = credentials()

    title = first_value(
        info_data.get("name"),
        movie_data.get("name"),
        fallback_title,
        "Movie",
    )

    plot = first_value(
        info_data.get("plot"),
        info_data.get(
            "description"
        ),
    )

    tagline = first_value(
        info_data.get("tagline"),
        info_data.get(
            "o_name"
        ),
    )

    poster = first_value(
        info_data.get(
            "cover_big"
        ),
        info_data.get(
            "movie_image"
        ),
        info_data.get("cover"),
        movie_data.get(
            "stream_icon"
        ),
    )

    backdrop = first_backdrop(
        info_data.get(
            "backdrop_path"
        )
    )

    genre = (
        info_data.get("genre")
        or ""
    )

    country = (
        info_data.get("country")
        or ""
    )

    director = (
        info_data.get("director")
        or ""
    )

    cast = cast_to_tuples(
        first_value(
            info_data.get("cast"),
            info_data.get(
                "actors"
            ),
        )
    )

    release_date = first_value(
        info_data.get(
            "releasedate"
        ),
        info_data.get(
            "release_date"
        ),
    )

    year = first_value(
        safe_int(
            info_data.get("year"),
            0,
        ),
        year_from_date(
            release_date
        ),
    )

    rating = safe_float(
        info_data.get("rating"),
        0.0,
    )

    duration = safe_int(
        first_value(
            info_data.get(
                "duration_secs"
            ),
            movie_data.get(
                "duration_secs"
            ),
        ),
        0,
    )

    trailer_id = (
        info_data.get(
            "youtube_trailer"
        )
        or ""
    )

    container_extension = (
        movie_data.get(
            "container_extension"
        )
        or "mp4"
    )

    stream_id = str(
        first_value(
            movie_data.get(
                "stream_id"
            ),
            vod_id,
        )
    )

    play_url = (
        "{}/movie/{}/{}/{}.{}".format(
            server,
            username,
            password,
            stream_id,
            container_extension,
        )
    )

    xbmcplugin.setPluginCategory(
        HANDLE,
        title,
    )

    xbmcplugin.setContent(
        HANDLE,
        "movies",
    )

    art = base_art(
        icon=poster,
        thumb=poster,
        poster=poster,
        fanart=backdrop,
        landscape=backdrop,
    )

    video_info = {
        "title": title,
        "mediatype": "movie",
        "plot": plot,
    }

    if tagline:
        video_info["tagline"] = (
            tagline
        )

    if genre:
        video_info["genre"] = (
            genre
        )

    if country:
        video_info["country"] = (
            country
        )

    if director:
        video_info["director"] = (
            director
        )

    if cast:
        video_info["cast"] = (
            cast
        )

    if release_date:
        video_info["premiered"] = (
            release_date
        )

    if year:
        video_info["year"] = safe_int(
            year,
            0,
        )

    if rating:
        video_info["rating"] = (
            rating
        )

    if duration:
        video_info["duration"] = (
            duration
        )

    play_item = xbmcgui.ListItem(
        label="[B]Play Movie[/B]"
    )

    play_item.setProperty(
        "IsPlayable",
        "true",
    )

    play_item.setInfo(
        "video",
        video_info,
    )

    apply_art(
        play_item,
        art,
    )

    xbmcplugin.addDirectoryItem(
        HANDLE,
        plugin_url(
            action="play",
            url=play_url,
            title=title,
        ),
        play_item,
        isFolder=False,
    )

    if trailer_id:
        trailer_item = xbmcgui.ListItem(
            label="Watch Trailer"
        )

        trailer_item.setInfo(
            "video",
            video_info,
        )

        apply_art(
            trailer_item,
            art,
        )

        xbmcplugin.addDirectoryItem(
            HANDLE,
            plugin_url(
                action="play_trailer",
                trailer_id=trailer_id,
                title=title,
            ),
            trailer_item,
            isFolder=False,
        )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def play_trailer(
    trailer_id,
    title,
):
    if not trailer_id:
        xbmcgui.Dialog().notification(
            ADDON_NAME,
            (
                "No trailer is available "
                "for this movie."
            ),
            xbmcgui.NOTIFICATION_INFO,
            3000,
        )

        return

    if not xbmc.getCondVisibility(
        "System.HasAddon(plugin.video.youtube)"
    ):
        xbmcgui.Dialog().notification(
            ADDON_NAME,
            (
                "Install the YouTube add-on "
                "to watch trailers."
            ),
            xbmcgui.NOTIFICATION_INFO,
            5000,
        )

        return

    trailer_url = (
        "plugin://plugin.video.youtube/"
        "play/?video_id={}"
    ).format(
        trailer_id
    )

    xbmc.Player().play(
        trailer_url
    )


# ============================================================
# TV SHOWS / SERIES
# ============================================================

def series_categories():
    data = api_get(
        "get_series_categories"
    )

    if not isinstance(
        data,
        list,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        "TV Shows",
    )

    for category in data:
        category_id = str(
            category.get(
                "category_id",
                "",
            )
        )

        name = (
            category.get(
                "category_name"
            )
            or "Unnamed category"
        )

        if category_id:
            add_folder(
                name,
                "series_list",
                art=base_art(),
                info={
                    "title": name,
                    "plot": (
                        "Browse TV shows in {}."
                    ).format(
                        name
                    ),
                },
                category_id=category_id,
                category_name=name,
            )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def series_list(
    category_id,
    category_name="TV Shows",
):
    data = api_get(
        "get_series",
        category_id=category_id,
    )

    if not isinstance(
        data,
        list,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        category_name or "TV Shows",
    )

    xbmcplugin.setContent(
        HANDLE,
        "tvshows",
    )

    for show in data:
        series_id = str(
            show.get(
                "series_id",
                "",
            )
        )

        if not series_id:
            continue

        name = (
            show.get("name")
            or "Unnamed show"
        )

        poster = first_value(
            show.get("cover"),
            show.get(
                "stream_icon"
            ),
        )

        backdrop = first_backdrop(
            show.get(
                "backdrop_path"
            )
        )

        plot = first_value(
            show.get("plot"),
            show.get(
                "description"
            ),
        )

        genre = (
            show.get("genre")
            or ""
        )

        year = safe_int(
            first_value(
                show.get("year"),
                year_from_date(
                    show.get(
                        "releaseDate"
                    )
                ),
            ),
            0,
        )

        rating = safe_float(
            show.get("rating"),
            0.0,
        )

        cast = cast_to_tuples(
            first_value(
                show.get("cast"),
                show.get("actors"),
            )
        )

        director = (
            show.get("director")
            or ""
        )

        release_date = first_value(
            show.get(
                "releaseDate"
            ),
            show.get(
                "releasedate"
            ),
        )

        art = base_art(
            icon=poster,
            thumb=poster,
            poster=poster,
            fanart=backdrop,
            landscape=backdrop,
        )

        info = {
            "title": name,
            "tvshowtitle": name,
            "mediatype": "tvshow",
            "plot": plot,
        }

        if genre:
            info["genre"] = genre

        if year:
            info["year"] = year

        if rating:
            info["rating"] = rating

        if cast:
            info["cast"] = cast

        if director:
            info["director"] = (
                director
            )

        if release_date:
            info["premiered"] = (
                release_date
            )

        add_folder(
            name,
            "series_seasons",
            art=art,
            info=info,
            series_id=series_id,
            series_name=name,
        )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def series_seasons(
    series_id,
    series_name,
):
    data = api_get(
        "get_series_info",
        series_id=series_id,
    )

    if not isinstance(
        data,
        dict,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    show_info = (
        data.get("info")
        or {}
    )

    seasons = (
        data.get("seasons")
        or []
    )

    episodes = (
        data.get("episodes")
        or {}
    )

    xbmcplugin.setPluginCategory(
        HANDLE,
        series_name,
    )

    xbmcplugin.setContent(
        HANDLE,
        "seasons",
    )

    show_poster = first_value(
        show_info.get("cover"),
        show_info.get(
            "movie_image"
        ),
    )

    show_backdrop = first_backdrop(
        show_info.get(
            "backdrop_path"
        )
    )

    show_plot = first_value(
        show_info.get("plot"),
        show_info.get(
            "description"
        ),
    )

    show_genre = (
        show_info.get("genre")
        or ""
    )

    show_rating = safe_float(
        show_info.get("rating"),
        0.0,
    )

    show_release_date = first_value(
        show_info.get(
            "releaseDate"
        ),
        show_info.get(
            "releasedate"
        ),
    )

    show_year = safe_int(
        first_value(
            show_info.get("year"),
            year_from_date(
                show_release_date
            ),
        ),
        0,
    )

    season_numbers = []
    season_data_map = {}

    if isinstance(
        seasons,
        list,
    ):
        for season in seasons:
            season_number = safe_int(
                first_value(
                    season.get(
                        "season_number"
                    ),
                    season.get(
                        "season"
                    ),
                ),
                0,
            )

            if season_number not in season_numbers:
                season_numbers.append(
                    season_number
                )

            season_data_map[
                season_number
            ] = season

    if isinstance(
        episodes,
        dict,
    ):
        for season_key in episodes.keys():
            season_number = safe_int(
                season_key,
                0,
            )

            if season_number not in season_numbers:
                season_numbers.append(
                    season_number
                )

    season_numbers.sort()

    for season_number in season_numbers:
        season_data = (
            season_data_map.get(
                season_number,
                {},
            )
            or {}
        )

        season_name = first_value(
            season_data.get("name"),
            "Season {}".format(
                season_number
            ),
        )

        season_poster = first_value(
            season_data.get("cover"),
            season_data.get(
                "cover_big"
            ),
            show_poster,
        )

        season_plot = first_value(
            season_data.get("overview"),
            season_data.get("plot"),
            show_plot,
        )

        art = base_art(
            icon=season_poster,
            thumb=season_poster,
            poster=season_poster,
            fanart=show_backdrop,
            landscape=show_backdrop,
        )

        info = {
            "title": season_name,
            "tvshowtitle": (
                series_name
            ),
            "mediatype": "season",
            "season": season_number,
            "plot": season_plot,
        }

        if show_genre:
            info["genre"] = (
                show_genre
            )

        if show_rating:
            info["rating"] = (
                show_rating
            )

        if show_year:
            info["year"] = (
                show_year
            )

        add_folder(
            season_name,
            "series_episodes",
            art=art,
            info=info,
            series_id=series_id,
            series_name=series_name,
            season_number=str(
                season_number
            ),
        )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def series_episodes(
    series_id,
    series_name,
    season_number,
):
    data = api_get(
        "get_series_info",
        series_id=series_id,
    )

    if not isinstance(
        data,
        dict,
    ):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )

        return

    episodes = (
        data.get("episodes")
        or {}
    )

    show_info = (
        data.get("info")
        or {}
    )

    season_key = str(
        safe_int(
            season_number,
            0,
        )
    )

    season_episodes = []

    if isinstance(
        episodes,
        dict,
    ):
        season_episodes = (
            episodes.get(
                season_key
            )
            or episodes.get(
                season_number
            )
            or []
        )

    if not isinstance(
        season_episodes,
        list,
    ):
        season_episodes = []

    xbmcplugin.setPluginCategory(
        HANDLE,
        "{} - Season {}".format(
            series_name,
            season_key,
        ),
    )

    xbmcplugin.setContent(
        HANDLE,
        "episodes",
    )

    server, username, password = credentials()

    show_poster = first_value(
        show_info.get("cover"),
        show_info.get(
            "movie_image"
        ),
    )

    show_backdrop = first_backdrop(
        show_info.get(
            "backdrop_path"
        )
    )

    show_genre = (
        show_info.get("genre")
        or ""
    )

    for episode in season_episodes:
        episode_id = str(
            first_value(
                episode.get("id"),
                episode.get(
                    "stream_id"
                ),
            )
        )

        if not episode_id:
            continue

        episode_number = safe_int(
            first_value(
                episode.get(
                    "episode_num"
                ),
                episode.get(
                    "episode_number"
                ),
            ),
            0,
        )

        title = first_value(
            episode.get("title"),
            episode.get("name"),
            "Episode {}".format(
                episode_number
            ),
        )

        episode_info = (
            episode.get("info")
            or {}
        )

        plot = first_value(
            episode_info.get("plot"),
            episode_info.get(
                "description"
            ),
            episode.get("plot"),
        )

        duration = safe_int(
            first_value(
                episode_info.get(
                    "duration_secs"
                ),
                episode.get(
                    "duration_secs"
                ),
            ),
            0,
        )

        rating = safe_float(
            first_value(
                episode_info.get(
                    "rating"
                ),
                episode.get(
                    "rating"
                ),
            ),
            0.0,
        )

        release_date = first_value(
            episode_info.get(
                "releasedate"
            ),
            episode_info.get(
                "release_date"
            ),
            episode.get(
                "releasedate"
            ),
        )

        thumbnail = first_value(
            episode_info.get(
                "movie_image"
            ),
            episode_info.get(
                "cover_big"
            ),
            episode_info.get("cover"),
            episode.get(
                "stream_icon"
            ),
            show_poster,
        )

        container_extension = (
            episode.get(
                "container_extension"
            )
            or "mp4"
        )

        play_url = (
            "{}/series/{}/{}/{}.{}".format(
                server,
                username,
                password,
                episode_id,
                container_extension,
            )
        )

        label = title

        if episode_number:
            label = (
                "{:02d}. {}".format(
                    episode_number,
                    title,
                )
            )

        item = xbmcgui.ListItem(
            label=label
        )

        item.setProperty(
            "IsPlayable",
            "true",
        )

        video_info = {
            "title": title,
            "tvshowtitle": (
                series_name
            ),
            "mediatype": "episode",
            "season": safe_int(
                season_number,
                0,
            ),
            "episode": (
                episode_number
            ),
            "plot": plot,
        }

        if duration:
            video_info["duration"] = (
                duration
            )

        if rating:
            video_info["rating"] = (
                rating
            )

        if release_date:
            video_info["aired"] = (
                release_date
            )

        if show_genre:
            video_info["genre"] = (
                show_genre
            )

        item.setInfo(
            "video",
            video_info,
        )

        apply_art(
            item,
            base_art(
                icon=thumbnail,
                thumb=thumbnail,
                poster=show_poster,
                fanart=show_backdrop,
                landscape=(
                    show_backdrop
                ),
            ),
        )

        xbmcplugin.addDirectoryItem(
            HANDLE,
            plugin_url(
                action="play",
                url=play_url,
                title=title,
            ),
            item,
            isFolder=False,
        )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


# ============================================================
# PLAYBACK
# ============================================================

def play(
    url,
    title,
):
    if not url:
        xbmcgui.Dialog().notification(
            ADDON_NAME,
            "No playback URL was supplied.",
            xbmcgui.NOTIFICATION_ERROR,
            3000,
        )

        return

    item = xbmcgui.ListItem(
        path=url
    )

    item.setLabel(
        title
    )

    item.setProperty(
        "IsPlayable",
        "true",
    )

    xbmcplugin.setResolvedUrl(
        HANDLE,
        True,
        item,
    )


# ============================================================
# DEVELOPMENT PLACEHOLDERS
# ============================================================

def coming_soon(
    section,
    folder=False,
):
    xbmcgui.Dialog().notification(
        ADDON_NAME,
        (
            "{} is coming in this "
            "development build."
        ).format(
            section
        ),
        xbmcgui.NOTIFICATION_INFO,
        3000,
    )

    if folder:
        xbmcplugin.setPluginCategory(
            HANDLE,
            section,
        )

        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=True,
        )


# ============================================================
# REFRESH
# ============================================================

def refresh_codex():
    xbmcgui.Dialog().notification(
        ADDON_NAME,
        "Refreshing CODEX...",
        xbmcgui.NOTIFICATION_INFO,
        2000,
    )

    xbmc.executebuiltin(
        "Container.Refresh"
    )


# ============================================================
# CONNECTION / SETTINGS
# ============================================================

def test_connection():
    data = api_get()

    if not isinstance(
        data,
        dict,
    ):
        return

    user_info = (
        data.get("user_info")
        or {}
    )

    auth = str(
        user_info.get(
            "auth",
            "0",
        )
    )

    if auth != "1":
        xbmcgui.Dialog().ok(
            ADDON_NAME,
            (
                "Provider responded, but "
                "authentication failed."
            ),
        )

        return

    status = (
        user_info.get("status")
        or "Active"
    )

    expiry = format_unix_date(
        user_info.get(
            "exp_date"
        )
    )

    active_cons = safe_int(
        user_info.get(
            "active_cons"
        ),
        0,
    )

    max_connections = safe_int(
        user_info.get(
            "max_connections"
        ),
        0,
    )

    lines = [
        "Connection successful.",
        "",
        "Account status: {}".format(
            status
        ),
    ]

    if expiry:
        lines.append(
            "Expires: {}".format(
                expiry
            )
        )

    if max_connections:
        lines.append(
            "Connections: {} / {}".format(
                active_cons,
                max_connections,
            )
        )

    lines.extend(
        [
            "",
            "CODEX IPTV v{}".format(
                ADDON_VERSION
            ),
        ]
    )

    xbmcgui.Dialog().ok(
        ADDON_NAME,
        "\n".join(
            lines
        ),
    )


def open_settings():
    ADDON.openSettings()

    xbmc.executebuiltin(
        "Container.Refresh"
    )


# ============================================================
# ROUTER
# ============================================================

def route():
    params = (
        dict(
            parse_qsl(
                sys.argv[2][1:]
            )
        )
        if len(sys.argv) > 2
        else {}
    )

    action = params.get(
        "action",
        "",
    )

    if not action:
        root_menu()

    elif action == "live_categories":
        live_categories()

    elif action == "live_streams":
        live_streams(
            params.get(
                "category_id",
                "",
            ),
            params.get(
                "category_name",
                "Channels",
            ),
        )

    elif action == "movie_categories":
        movie_categories()

    elif action == "movie_list":
        movie_list(
            params.get(
                "category_id",
                "",
            ),
            params.get(
                "category_name",
                "Movies",
            ),
        )

    elif action == "movie_details":
        movie_details(
            params.get(
                "vod_id",
                "",
            ),
            params.get(
                "fallback_title",
                "Movie",
            ),
        )

    elif action == "play_trailer":
        play_trailer(
            params.get(
                "trailer_id",
                "",
            ),
            params.get(
                "title",
                "Movie",
            ),
        )

    elif action == "series_categories":
        series_categories()

    elif action == "series_list":
        series_list(
            params.get(
                "category_id",
                "",
            ),
            params.get(
                "category_name",
                "TV Shows",
            ),
        )

    elif action == "series_seasons":
        series_seasons(
            params.get(
                "series_id",
                "",
            ),
            params.get(
                "series_name",
                "TV Show",
            ),
        )

    elif action == "series_episodes":
        series_episodes(
            params.get(
                "series_id",
                "",
            ),
            params.get(
                "series_name",
                "TV Show",
            ),
            params.get(
                "season_number",
                "0",
            ),
        )

    elif action == "play":
        play(
            params.get(
                "url",
                "",
            ),
            params.get(
                "title",
                ADDON_NAME,
            ),
        )

    elif action == "favourites":
        coming_soon(
            "Favourites",
            folder=True,
        )

    elif action == "search":
        coming_soon(
            "Search",
            folder=False,
        )

    elif action == "refresh":
        refresh_codex()

    elif action == "test_connection":
        test_connection()

    elif action == "settings":
        open_settings()

    else:
        xbmcgui.Dialog().notification(
            ADDON_NAME,
            "Unknown action.",
            xbmcgui.NOTIFICATION_ERROR,
            3000,
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    route()