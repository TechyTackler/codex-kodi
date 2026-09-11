# CODEX Kodi

Kodi video add-on and repository for **CODEX IPTV**.

CODEX provides a clean Kodi interface for connecting to a compatible Xtream-based IPTV service and browsing Live TV, Movies and Series.

> **CODEX IPTV does not contain or provide any streams or media content.**
> Users must supply their own compatible IPTV service.

## Current Version

### v0.4.0

CODEX IPTV currently includes:

- Xtream-compatible provider settings
- Provider connection testing
- Live TV categories
- Live TV channel listings
- Native Kodi Live TV playback
- XMLTV-powered Now & Next programme information
- Movie categories
- Movie listings
- Movie details and metadata
- Movie playback
- Trailer support where supplied by the provider
- Series categories
- Series listings
- Seasons and episodes
- Episode playback
- Provider artwork including posters and backdrops
- Global CODEX Search across:
  - Live TV
  - Movies
  - Series
- CODEX Favourites with separate:
  - Live TV
  - Movies
  - Series
- Persistent local favourites stored within the Kodi profile
- Add and remove favourites directly from Kodi context menus
- Live TV programme information within CODEX Favourites
- CODEX branded interface artwork

## Search

CODEX Search provides a single search across the connected provider's Live TV, Movie and Series catalogues.

Search results are identified by content type:

- `[Live TV]`
- `[Movie]`
- `[Series]`

Live TV results can be played directly, while Movies and Series open their normal CODEX detail screens.

## Favourites

CODEX includes its own favourites system independently of Kodi's global Favourites feature.

The Favourites section is divided into:

- Live TV
- Movies
- Series

Use the context menu on supported content and select:

`Add to CODEX Favourites`

or:

`Remove from CODEX Favourites`

Favourites are stored locally within the Kodi profile and persist between Kodi sessions.

Provider usernames, passwords and playback URLs are not stored in the CODEX favourites file.

## Programme Guide

Where supported by the connected IPTV provider, CODEX retrieves XMLTV programme data for Live TV.

Live channel listings can display:

- Current programme
- Current programme start and finish times
- Programme description
- Next programme
- Next programme start and finish times

Programme information is retrieved from the user's configured IPTV provider.

## Installation

The CODEX Kodi repository can be installed using:

`repository.codex-1.0.0.zip`

Repository ZIP:

https://techytackler.github.io/codex-kodi/repository.codex-1.0.0.zip

Once installed, use the CODEX Repository within Kodi to install or update **CODEX IPTV**.

## GitHub Pages

GitHub Pages is published from the `main` branch root.

Repository metadata:

- https://techytackler.github.io/codex-kodi/repo/addons.xml
- https://techytackler.github.io/codex-kodi/repo/addons.xml.md5

Current CODEX IPTV package:

- https://techytackler.github.io/codex-kodi/repo/plugin.video.codex/plugin.video.codex-0.4.0.zip

## Repository

Source code:

https://github.com/TechyTackler/codex-kodi

Developed by **TechyTackler**.

## Requirements

- Kodi with Python 3 add-on support
- Internet connection
- Compatible Xtream-based IPTV service
- Valid provider server address, username and password

Available content, artwork, metadata, programme information and playback compatibility depend on the IPTV provider configured by the user.

## Disclaimer

CODEX Kodi does not provide, host, distribute or include any television channels, video streams, playlists or other media content.

Users must supply their own compatible IPTV service and are responsible for ensuring they have the necessary rights and permissions to access any content used with this add-on.

Use only with IPTV services and streams you are authorised to access.
