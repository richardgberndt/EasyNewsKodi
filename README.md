![EasyNews Kodi banner](images/banner.jpg)


| <a href="https://ko-fi.com/tetsuox" target="_blank"><img src="https://storage.ko-fi.com/cdn/kofi6.png?v=6" style="height: 45px !important;width: 162px !important;" ></a> | [https://ko-fi.com/tetsuox](https://ko-fi.com/tetsuox) |
| --- | --- |

# EasyNews Kodi add-on

**EasyNews Video by Tetsuo** is a Kodi video add-on that searches the [EasyNews](https://www.easynews.com/) retention database and plays members-only streams. It supports saved newsgroups, search and play history, experimental VLC playback (superior to Kodi player with some Easynews streams), TMDB discovery, a local downloads folder browser, optional split-file lookup, and related tools.

**Requirements:** Kodi **19+** (Matrix). An active **EasyNews** membership.

**Disclaimer:** This add-on is not affiliated with EasyNews. You are responsible for complying with their terms of service and applicable law.

---

## Installation

It's best to install the respository to make sure you receive all future updates.

- Enable "Unknown Sources" in Kodi Settings > System > Add-ons
- Enable "Update official add-ons from: Any repositories" in Kodi Settings > System > Add-ons
- Install EasyNews repository using either the zipfile or from a Kodi file manager source, links below
- Install latest version of EasyNews from the EasyNews repo

**First add a source in Kodi:**

Settings > File Manager > Add Source

https://tetsuosoft.github.io/EasyNewsKodi/EasyNewsRepo

**Then install the EasyNews repo:**

Addon > Install from zipfile > EasyNewsRepo > repository.easynewsx-1.0.0.zip

**Then install the Addon:**

Addon > Install from repository > EasyNews Repository > Video Addons > EasyNews

If you prefer to install the repo by direct ZIP Install it's here:

https://tetsuosoft.github.io/EasyNewsKodi/EasyNewsRepo/repository.easynewsx-1.0.0.zip

After the repository is installed, Kodi can automatically check or you can manually check for updates, depending on your Kodi settings.

---

## Latest release v6.6.1

- Fixed thumbnails were not showing in search results after Easynews changed stuff!

## Previous releases 

6.6.0

After user requests on [Reddit](https://www.reddit.com/r/Addons4Kodi/):

- Fixed startup crash on some older Kodi boxes.
- Play with NOSEEK — new context-menu option on search results and play history; can help streams start faster on some setups. Note: no seeking or skipping a stream is possible for movies launched with this option
- Search sort order — sort results by post date (newest or oldest) or file size (smallest or largest).

6.5.1

- Search cache — Revisit the same search faster when paging back or switching size. Cache saved for 30 mins.
- Video size — Default to All, 720p, 1080p, or 4K; change anytime from the main menu or search results.
- Account usage — Main menu shows plan and gigs left; tap to refresh.
- Better EasyNews routing — Streams use your account's best route / server farm when available; Tools can show your current route.
- TMDB discovery — Browse and search movies and TV; drill into episodes and search EasyNews in one tap.

6.4.2

After user requests on Reddit, Easynews member plan and download usage remaining is now shown on the main screen

v6.4.1

Better backward compatibility on Kodi 19 (Matrix); experimental VLC playback with context menu additions; more robust Easynews stream seeking and recovery; clearer Easynews error reporting and more reliable downloads and cancellation; Kodi 20 (Nexus) and newer remain supported.

---

## How to release

`tools/release.py` bumps the add-on version, rebuilds the Kodi repository index, and packs the install zip. It uses only the Python 3 standard library.

```bash
python3 tools/release.py --check
python3 tools/release.py 6.6.2 --news "- What changed." --dry-run
python3 tools/release.py 6.6.2 --news "- What changed."
```

`--check` succeeds when these all show the same version: `plugin.video.easynewsx/addon.xml` (`version` and the first `<news>` line), `ADDON_VERSION` in `resources/lib/easynews/constants.py`, the welcome line in `resources/userguide.json`, the plugin entry in root `addons.xml`, and the `## Latest release` heading in this README. It also checks that `addons.xml.md5` matches `addons.xml`.

A release updates those spots. Notes that were under Latest release move under Previous releases. Root `addons.xml` is rebuilt from each top-level add-on directory's `addon.xml` (the video add-on and, when you add one, a repository add-on), and `addons.xml.md5` is rewritten beside it. The first release replaces the short `addons.xml` stub with those real add-on elements.

The zip is `<datadir>/<addon id>/<addon id>-<version>.zip`. Its top folder is the add-on id. `__MACOSX`, `.DS_Store`, AppleDouble `._*` files, and Python bytecode are left out. Passing the current version again rebuilds the index and the zip. An existing `<news>` block for that version stays put unless you pass `--news`.

Hosting URLs are set in `tools/release.json`, or with `--datadir`, `--info-url`, `--checksum-url`, and `--datadir-url`:

- `datadir` — local folder for built zips. Default `dist`, relative to the repository root.
- `info_url` — public URL of `addons.xml` (Kodi `<info>`).
- `checksum_url` — public URL of `addons.xml.md5` (Kodi `<checksum>`).
- `datadir_url` — public base URL for `<datadir zip="true">`. Kodi then requests `<datadir_url>/<addon id>/<addon id>-<version>.zip`.

Empty URL fields skip repository add-on URL edits. When a repository add-on source directory is present, a release writes each non-empty URL into its `addon.xml` and packs that add-on with the same datadir layout.

`EasyNewsRepo/repository.easynewsx-1.0.0.zip` stays in the tree as the upstream installer. Its info and checksum point at `https://raw.githubusercontent.com/tetsuosoft/EasyNewsKodi/main/addons.xml` and `addons.xml.md5`, and its datadir is `https://kodi.clientsite.co.uk/`.

---

## Issues

- **Repository:** [github.com/tetsuosoft/EasyNewsKodi](https://github.com/tetsuosoft/EasyNewsKodi)
- Report bugs or feature requests via **GitHub Issues**.

| <a href="https://ko-fi.com/tetsuox" target="_blank"><img src="https://storage.ko-fi.com/cdn/kofi6.png?v=6" style="height: 45px !important;width: 162px !important;" ></a> | [https://ko-fi.com/tetsuox](https://ko-fi.com/tetsuox) |
| --- | --- |

---

## License

See the add-on package for license information (e.g. GPL v3 where stated in source files).
