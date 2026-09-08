# -*- coding: utf-8 -*-

import json
import sys

from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin


ADDON = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]


# ============================================================
# LOGGING / SETTINGS
# ============================================================

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
    url = api_url(action, **params)

    req = Request(
        url,
        headers={
            "User-Agent": "CODEX-IPTV/0.2.1 Kodi",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(req, timeout=15) as response:
            payload = response.read().decode(
                "utf-8",
                errors="replace",
            )

            return json.loads(payload)

    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        log(
            "API error: {}".format(exc),
            xbmc.LOGERROR,
        )

        xbmcgui.Dialog().notification(
            "CODEX IPTV",
            "Unable to contact provider. Check settings.",
            xbmcgui.NOTIFICATION_ERROR,
            5000,
        )

        return None


# ============================================================
# HELPERS
# ============================================================

def plugin_url(**params):
    return "{}?{}".format(
        BASE_URL,
        urlencode(params),
    )


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def first_value(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value

    return ""


def first_backdrop(value):
    if isinstance(value, list) and value:
        return value[0] or ""

    if isinstance(value, str):
        return value

    return ""


def year_from_date(value):
    if not value:
        return 0

    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return 0


def cast_to_tuples(value):
    if not value:
        return []

    if isinstance(value, list):
        cast = []

        for entry in value:
            if isinstance(entry, (list, tuple)):
                if not entry:
                    continue

                name = str(entry[0]).strip()

                role = (
                    str(entry[1]).strip()
                    if len(entry) > 1
                    else ""
                )

                if name:
                    cast.append(
                        (name, role)
                    )

            elif isinstance(entry, dict):
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
                        (name, role)
                    )

            else:
                name = str(entry).strip()

                if name:
                    cast.append(
                        (name, "")
                    )

        return cast

    return [
        (name.strip(), "")
        for name in str(value).split(",")
        if name.strip()
    ]


def add_folder(label, action, art=None, info=None, **params):
    item = xbmcgui.ListItem(label=label)

    if art:
        item.setArt(art)
    else:
        item.setArt({
            "icon": "DefaultFolder.png",
        })

    if info:
        item.setInfo(
            "video",
            info,
        )

    params["action"] = action

    xbmcplugin.addDirectoryItem(
        HANDLE,
        plugin_url(**params),
        item,
        isFolder=True,
    )


def add_action(label, action, art=None, **params):
    item = xbmcgui.ListItem(label=label)

    if art:
        item.setArt(art)
    else:
        item.setArt({
            "icon": "DefaultAddonService.png",
        })

    params["action"] = action

    xbmcplugin.addDirectoryItem(
        HANDLE,
        plugin_url(**params),
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

        item.setArt({
            "icon": "DefaultAddonService.png",
        })

        xbmcplugin.addDirectoryItem(
            HANDLE,
            plugin_url(action="settings"),
            item,
            isFolder=False,
        )

        xbmcplugin.endOfDirectory(HANDLE)

        xbmcgui.Dialog().notification(
            "CODEX IPTV",
            "Enter your provider details in Settings.",
            xbmcgui.NOTIFICATION_INFO,
            5000,
        )

        return

    add_folder(
        "Live TV",
        "live_categories",
    )

    add_folder(
        "Movies",
        "movie_categories",
    )

    add_folder(
        "TV Shows",
        "series_categories",
    )

    add_folder(
        "Favourites",
        "favourites",
    )

    add_action(
        "Search",
        "search",
    )

    add_action(
        "Settings",
        "settings",
    )

    xbmcplugin.endOfDirectory(HANDLE)


# ============================================================
# LIVE TV
# ============================================================

def live_categories():
    data = api_get(
        "get_live_categories"
    )

    if not isinstance(data, list):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )
        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        "Live TV",
    )

    for category in data:
        category_id = str(
            category.get(
                "category_id",
                "",
            )
        )

        name = (
            category.get("category_name")
            or "Unnamed category"
        )

        if category_id:
            add_folder(
                name,
                "live_streams",
                category_id=category_id,
            )

    xbmcplugin.endOfDirectory(HANDLE)


def live_streams(category_id):
    data = api_get(
        "get_live_streams",
        category_id=category_id,
    )

    if not isinstance(data, list):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )
        return

    server, username, password = credentials()

    xbmcplugin.setPluginCategory(
        HANDLE,
        "Channels",
    )

    xbmcplugin.setContent(
        HANDLE,
        "videos",
    )

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
            stream.get("stream_icon")
            or ""
        )

        extension = (
            setting("stream_extension")
            or "ts"
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

        if logo:
            item.setArt({
                "thumb": logo,
                "icon": logo,
            })
        else:
            item.setArt({
                "icon": "DefaultVideo.png",
            })

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

    xbmcplugin.endOfDirectory(HANDLE)


# ============================================================
# MOVIES
# ============================================================

def movie_categories():
    data = api_get(
        "get_vod_categories"
    )

    if not isinstance(data, list):
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
            category.get("category_name")
            or "Unnamed category"
        )

        if category_id:
            add_folder(
                name,
                "movie_list",
                category_id=category_id,
            )

    xbmcplugin.endOfDirectory(HANDLE)


def movie_list(category_id):
    data = api_get(
        "get_vod_streams",
        category_id=category_id,
    )

    if not isinstance(data, list):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )
        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        "Movies",
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
            movie.get("stream_icon"),
            movie.get("cover"),
        )

        plot = first_value(
            movie.get("plot"),
            movie.get("description"),
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

        art = {}

        if poster:
            art.update({
                "poster": poster,
                "thumb": poster,
                "icon": poster,
            })

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
            art=art or None,
            info=info,
            vod_id=stream_id,
            fallback_title=name,
        )

    xbmcplugin.endOfDirectory(HANDLE)


def movie_details(vod_id, fallback_title):
    data = api_get(
        "get_vod_info",
        vod_id=vod_id,
    )

    if not isinstance(data, dict):
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
        info_data.get("description"),
    )

    poster = first_value(
        info_data.get("cover_big"),
        info_data.get("movie_image"),
        info_data.get("cover"),
    )

    backdrop = first_backdrop(
        info_data.get("backdrop_path")
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

    cast_raw = first_value(
        info_data.get("cast"),
        info_data.get("actors"),
    )

    cast = cast_to_tuples(
        cast_raw
    )

    release_date = (
        info_data.get("releasedate")
        or ""
    )

    year = year_from_date(
        release_date
    )

    rating = safe_float(
        info_data.get("rating"),
        0.0,
    )

    duration = safe_int(
        info_data.get("duration_secs"),
        0,
    )

    trailer_id = (
        info_data.get("youtube_trailer")
        or ""
    )

    container_extension = (
        movie_data.get("container_extension")
        or "mp4"
    )

    stream_id = str(
        first_value(
            movie_data.get("stream_id"),
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

    art = {}

    if poster:
        art.update({
            "poster": poster,
            "thumb": poster,
            "icon": poster,
        })

    if backdrop:
        art["fanart"] = backdrop

    video_info = {
        "title": title,
        "mediatype": "movie",
        "plot": plot,
    }

    if genre:
        video_info["genre"] = genre

    if country:
        video_info["country"] = country

    if director:
        video_info["director"] = director

    if cast:
        video_info["cast"] = cast

    if release_date:
        video_info["date"] = release_date

    if year:
        video_info["year"] = year

    if rating:
        video_info["rating"] = rating

    if duration:
        video_info["duration"] = duration

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

    if art:
        play_item.setArt(art)
    else:
        play_item.setArt({
            "icon": "DefaultVideo.png",
        })

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

        if art:
            trailer_item.setArt(art)
        else:
            trailer_item.setArt({
                "icon": "DefaultVideo.png",
            })

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

    xbmcplugin.endOfDirectory(HANDLE)


def play_trailer(trailer_id, title):
    if not trailer_id:
        xbmcgui.Dialog().notification(
            "CODEX IPTV",
            "No trailer is available for this movie.",
            xbmcgui.NOTIFICATION_INFO,
            3000,
        )
        return

    if not xbmc.getCondVisibility(
        "System.HasAddon(plugin.video.youtube)"
    ):
        xbmcgui.Dialog().notification(
            "CODEX IPTV",
            "Install the YouTube add-on to watch trailers.",
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

    if not isinstance(data, list):
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
            category.get("category_name")
            or "Unnamed category"
        )

        if category_id:
            add_folder(
                name,
                "series_list",
                category_id=category_id,
            )

    xbmcplugin.endOfDirectory(HANDLE)


def series_list(category_id):
    data = api_get(
        "get_series",
        category_id=category_id,
    )

    if not isinstance(data, list):
        xbmcplugin.endOfDirectory(
            HANDLE,
            succeeded=False,
        )
        return

    xbmcplugin.setPluginCategory(
        HANDLE,
        "TV Shows",
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
            show.get("stream_icon"),
        )

        backdrop = first_backdrop(
            show.get("backdrop_path")
        )

        plot = first_value(
            show.get("plot"),
            show.get("description"),
        )

        genre = (
            show.get("genre")
            or ""
        )

        year = safe_int(
            show.get("year"),
            0,
        )

        rating = safe_float(
            show.get("rating"),
            0.0,
        )

        art = {}

        if poster:
            art.update({
                "poster": poster,
                "thumb": poster,
                "icon": poster,
            })

        if backdrop:
            art["fanart"] = backdrop

        info = {
            "title": name,
            "mediatype": "tvshow",
            "plot": plot,
        }

        if genre:
            info["genre"] = genre

        if year:
            info["year"] = year

        if rating:
            info["rating"] = rating

        add_folder(
            name,
            "series_seasons",
            art=art or None,
            info=info,
            series_id=series_id,
            series_name=name,
        )

    xbmcplugin.endOfDirectory(HANDLE)


def series_seasons(series_id, series_name):
    data = api_get(
        "get_series_info",
        series_id=series_id,
    )

    if not isinstance(data, dict):
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

    poster = first_value(
        show_info.get("cover"),
        show_info.get("movie_image"),
    )

    backdrop = first_backdrop(
        show_info.get("backdrop_path")
    )

    season_numbers = []

    if isinstance(seasons, list):
        for season in seasons:
            season_number = safe_int(
                first_value(
                    season.get("season_number"),
                    season.get("season"),
                ),
                0,
            )

            if season_number not in season_numbers:
                season_numbers.append(
                    season_number
                )

    if isinstance(episodes, dict):
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
        season_name = (
            "Season {}".format(
                season_number
            )
        )

        art = {}

        if poster:
            art.update({
                "poster": poster,
                "thumb": poster,
                "icon": poster,
            })

        if backdrop:
            art["fanart"] = backdrop

        add_folder(
            season_name,
            "series_episodes",
            art=art or None,
            info={
                "title": season_name,
                "mediatype": "season",
                "season": season_number,
                "tvshowtitle": series_name,
            },
            series_id=series_id,
            series_name=series_name,
            season_number=str(
                season_number
            ),
        )

    xbmcplugin.endOfDirectory(HANDLE)


def series_episodes(
    series_id,
    series_name,
    season_number,
):
    data = api_get(
        "get_series_info",
        series_id=series_id,
    )

    if not isinstance(data, dict):
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

    if isinstance(episodes, dict):
        season_episodes = (
            episodes.get(season_key)
            or episodes.get(season_number)
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
        show_info.get("movie_image"),
    )

    show_backdrop = first_backdrop(
        show_info.get("backdrop_path")
    )

    for episode in season_episodes:
        episode_id = str(
            first_value(
                episode.get("id"),
                episode.get("stream_id"),
            )
        )

        if not episode_id:
            continue

        episode_number = safe_int(
            first_value(
                episode.get("episode_num"),
                episode.get("episode_number"),
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
            episode_info.get("description"),
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
                episode_info.get("rating"),
                episode.get("rating"),
            ),
            0.0,
        )

        thumbnail = first_value(
            episode_info.get(
                "movie_image"
            ),
            episode_info.get(
                "cover_big"
            ),
            episode_info.get(
                "cover"
            ),
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
            "tvshowtitle": series_name,
            "mediatype": "episode",
            "season": safe_int(
                season_number,
                0,
            ),
            "episode": episode_number,
            "plot": plot,
        }

        if duration:
            video_info["duration"] = (
                duration
            )

        if rating:
            video_info["rating"] = rating

        item.setInfo(
            "video",
            video_info,
        )

        art = {}

        if thumbnail:
            art.update({
                "thumb": thumbnail,
                "icon": thumbnail,
            })

        if show_poster:
            art["poster"] = show_poster

        if show_backdrop:
            art["fanart"] = show_backdrop

        if art:
            item.setArt(art)
        else:
            item.setArt({
                "icon": "DefaultVideo.png",
            })

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

    xbmcplugin.endOfDirectory(HANDLE)


# ============================================================
# PLAYBACK
# ============================================================

def play(url, title):
    item = xbmcgui.ListItem(
        path=url
    )

    item.setLabel(title)

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

def coming_soon(section, folder=False):
    xbmcgui.Dialog().notification(
        "CODEX IPTV",
        (
            "{} is coming in this "
            "development build."
        ).format(section),
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
# CONNECTION / SETTINGS
# ============================================================

def test_connection():
    data = api_get()

    if not isinstance(data, dict):
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

    if auth == "1":
        status = user_info.get(
            "status",
            "Active",
        )

        xbmcgui.Dialog().ok(
            "CODEX IPTV",
            (
                "Connection successful.\n\n"
                "Account status: {}"
            ).format(status),
        )

    else:
        xbmcgui.Dialog().ok(
            "CODEX IPTV",
            (
                "Provider responded, but "
                "authentication failed."
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
            )
        )

    elif action == "movie_categories":
        movie_categories()

    elif action == "movie_list":
        movie_list(
            params.get(
                "category_id",
                "",
            )
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
            )
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
                "CODEX IPTV",
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


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    route()