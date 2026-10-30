"""Utilidades y recolectores de aplicaciones por origen."""

import glob
import os
import re
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib  # noqa: E402

from .model import App


def run(cmd, env=None):
    """Ejecuta un comando y devuelve stdout (None si no existe el comando)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def human_size(n):
    if not n:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def parse_size(text):
    """'1.2 GB' -> bytes (formato SI que usa flatpak)."""
    text = (text or "").replace("\xa0", " ").replace(",", ".")
    match = re.match(r"\s*([\d.]+)\s*([kKMGT]?)B", text)
    if not match:
        return 0
    multiplier = {
        "": 1,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
    }[match.group(2)]
    try:
        return int(float(match.group(1)) * multiplier)
    except ValueError:
        return 0


GROUP = "Desktop Entry"


def read_desktop(path):
    """Devuelve (nombre, icono) de un .desktop, o None si no es una app visible."""
    key_file = GLib.KeyFile()
    try:
        key_file.load_from_file(path, GLib.KeyFileFlags.NONE)
    except GLib.Error:
        return None

    def get_string(key, localized=False):
        try:
            if localized:
                return key_file.get_locale_string(GROUP, key, None)
            return key_file.get_string(GROUP, key)
        except GLib.Error:
            return None

    def get_boolean(key):
        try:
            return key_file.get_boolean(GROUP, key)
        except GLib.Error:
            return False

    if get_string("Type") != "Application" or get_boolean("NoDisplay") or get_boolean("Hidden"):
        return None
    return (get_string("Name", True) or os.path.basename(path), get_string("Icon") or "")


def collect_apt():
    fmt = ("-f=${binary:Package}\t${Version}\t${Installed-Size}\t"
           "${db:Status-Abbrev}\t${binary:Summary}\n")
    out = run(["dpkg-query", "-W", fmt])
    if not out:
        return []

    gui = {}
    files = glob.glob("/usr/share/applications/*.desktop")
    if files:
        for line in (run(["dpkg", "-S"] + files) or "").splitlines():
            match = re.match(r"^(.+?): (/.+)$", line)
            if not match:
                continue
            info = read_desktop(match.group(2))
            if not info:
                continue
            for package in match.group(1).split(", "):
                gui.setdefault(package.strip(), info)

    apps = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or not parts[3].startswith("ii"):
            continue
        package, version, size_kib, _, summary = parts[:5]
        info = gui.get(package)
        try:
            size = int(size_kib) * 1024
        except ValueError:
            size = 0
        apps.append(App("APT", package, info[0] if info else package, version, size,
                        summary, info[1] if info else "", system=info is None))
    return apps


def collect_snap():
    out = run(["snap", "list"])
    if not out:
        return []
    apps = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        name, version, revision, _track, publisher = parts[:5]
        desktops = glob.glob(
            f"/var/lib/snapd/desktop/applications/{glob.escape(name)}_*.desktop"
        )
        info = None
        for desktop in desktops:
            info = read_desktop(desktop)
            if info:
                break
        try:
            size = os.path.getsize(f"/var/lib/snapd/snaps/{name}_{revision}.snap")
        except OSError:
            size = 0
        apps.append(App("Snap", name, info[0] if info else name, version, size,
                        f"Publicado por {publisher}", info[1] if info else "",
                        system=info is None))
    return apps


def collect_flatpak():
    columns = "--columns=application,name,version,installation,size,description"
    out = run(["flatpak", "list", columns])
    if not out:
        return []
    only_apps = run(["flatpak", "list", "--app", "--columns=application,installation"]) or ""
    app_keys = {tuple(line.split("\t")[:2]) for line in only_apps.splitlines()}
    apps = []
    for line in out.splitlines():
        parts = line.split("\t")
        parts += [""] * (6 - len(parts))
        app_id, name, version, installation, size, description = parts[:6]
        if not app_id:
            continue
        apps.append(App("Flatpak", app_id, name or app_id, version, parse_size(size),
                        description, app_id,
                        system=(app_id, installation) not in app_keys, scope=installation))
    return apps


def appimage_dirs():
    home = os.path.expanduser("~")
    names = ["Applications", "AppImages", ".local/bin", "bin", "Descargas",
             "Downloads", "Escritorio", "Desktop"]
    return [os.path.join(home, name) for name in names] + ["/opt"]


def collect_appimage():
    apps, seen = [], set()
    for directory in appimage_dirs():
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_file() or not entry.name.lower().endswith(".appimage"):
                continue
            path = os.path.realpath(entry.path)
            if path in seen:
                continue
            seen.add(path)
            name = re.sub(r"(?i)\.appimage$", "", entry.name)
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            apps.append(App("AppImage", path, name, "", size, path, ""))
    return apps


def collect_all():
    apps = []
    for collector in (collect_apt, collect_snap, collect_flatpak, collect_appimage):
        try:
            apps += collector()
        except Exception as exc:  # un origen que falla no debe romper el resto
            print(f"[aviso] {collector.__name__}: {exc}")
    apps.sort(key=lambda app: app.name.lower())
    return apps
