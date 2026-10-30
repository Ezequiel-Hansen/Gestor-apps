"""Modelo y constantes compartidas por la aplicación."""

import os
from dataclasses import dataclass

ICON_SIZE = 24
ENV_C = dict(os.environ, LC_ALL="C")
SOURCES = ["Todos", "APT", "Snap", "Flatpak", "AppImage"]
SOURCE_COLORS = {
    "APT": "#c7254e",
    "Snap": "#0a7ea4",
    "Flatpak": "#4a6fa5",
    "AppImage": "#8a5a00",
}


@dataclass
class App:
    source: str
    id: str
    name: str
    version: str = ""
    size: int = 0
    desc: str = ""
    icon: str = ""
    system: bool = False
    scope: str = ""
