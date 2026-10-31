"""Ventana principal del Gestor de aplicaciones."""

import os
import re
import subprocess
import threading


def _prepare_gtk_environment():
    snap_roots = tuple(
        os.environ[name]
        for name in ("SNAP", "SNAP_DATA", "SNAP_USER_DATA", "SNAP_USER_COMMON")
        if os.environ.get(name)
    )
    gtk_path_variables = (
        "GSETTINGS_SCHEMA_DIR",
        "GI_TYPELIB_PATH",
        "GTK_EXE_PREFIX",
        "GTK_PATH",
        "GIO_MODULE_DIR",
        "GDK_PIXBUF_MODULEDIR",
        "GDK_PIXBUF_MODULE_FILE",
        "GTK_IM_MODULE_FILE",
    )
    for name in gtk_path_variables:
        value = os.environ.get(name)
        if not value:
            continue
        paths = value.split(os.pathsep)
        filtered_paths = [
            path
            for path in paths
            if not any(path == root or path.startswith(root + os.sep) for root in snap_roots)
        ]
        if len(filtered_paths) != len(paths):
            if filtered_paths:
                os.environ[name] = os.pathsep.join(filtered_paths)
            else:
                os.environ.pop(name, None)

    backend = os.environ.get("GDK_BACKEND", "")
    if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY"):
        if not backend or any(item in ("wayland", "*") for item in backend.split(",")):
            # The GTK 3 Wayland backend expects keys absent from recent GNOME schemas.
            os.environ["GDK_BACKEND"] = "x11"


_prepare_gtk_environment()

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango  # noqa: E402

from .collectors import collect_all, human_size
from .dialogs import RunDialog
from .model import ENV_C, ICON_SIZE, SOURCES, SOURCE_COLORS
from .uninstall import build_plan


class Window(Gtk.Window):
    C_ICON, C_NAME, C_SRC, C_ID, C_VER, C_SIZE, C_BYTES, C_DESC, C_IDX, C_SYS = range(10)

    def __init__(self):
        super().__init__(title="Gestor de aplicaciones")
        self.set_default_size(1100, 650)
        self.apps = []
        self._icon_cache = {}

        header = Gtk.HeaderBar(show_close_button=True, title="Gestor de aplicaciones")
        self.set_titlebar(header)
        self.refresh_btn = Gtk.Button.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.BUTTON
        )
        self.refresh_btn.set_tooltip_text("Volver a leer las aplicaciones instaladas")
        self.refresh_btn.connect("clicked", self.refresh)
        header.pack_start(self.refresh_btn)
        self.remove_btn = Gtk.Button(label="Desinstalar")
        self.remove_btn.get_style_context().add_class("destructive-action")
        self.remove_btn.set_sensitive(False)
        self.remove_btn.connect("clicked", self.on_uninstall)
        header.pack_end(self.remove_btn)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(root)

        bar = Gtk.Box(spacing=8)
        for margin in ("margin_top", "margin_start", "margin_end"):
            bar.set_property(margin, 8)
        self.search = Gtk.SearchEntry(placeholder_text="Buscar por nombre, paquete o descripción…")
        self.search.connect("search-changed", self.on_filter_changed)
        bar.pack_start(self.search, True, True, 0)

        self.combo = Gtk.ComboBoxText()
        for source in SOURCES:
            self.combo.append_text(source)
        self.combo.set_active(0)
        self.combo.connect("changed", self.on_filter_changed)
        bar.pack_start(self.combo, False, False, 0)

        self.show_system = Gtk.CheckButton(label="Mostrar librerías y paquetes de sistema")
        self.show_system.connect("toggled", self.on_filter_changed)
        bar.pack_start(self.show_system, False, False, 0)
        root.pack_start(bar, False, False, 0)

        self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, str,
                                   GObject.TYPE_INT64, str, int, bool)
        self.filter = self.store.filter_new()
        self.filter.set_visible_func(self.visible)
        self.sorted = Gtk.TreeModelSort(model=self.filter)
        self.sorted.set_sort_column_id(self.C_NAME, Gtk.SortType.ASCENDING)

        self.tree = Gtk.TreeView(model=self.sorted)
        self.tree.set_rubber_banding(True)
        self.tree.set_search_column(self.C_NAME)
        self.tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.tree.get_selection().connect("changed", self.on_selection_changed)
        self.tree.connect("key-press-event", self.on_key)
        self.build_columns()

        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        scroll.set_vexpand(True)
        root.pack_start(scroll, True, True, 0)

        status_bar = Gtk.Box(spacing=8)
        for margin in ("margin_start", "margin_end", "margin_bottom"):
            status_bar.set_property(margin, 8)
        self.spinner = Gtk.Spinner()
        self.status = Gtk.Label(xalign=0)
        status_bar.pack_start(self.spinner, False, False, 0)
        status_bar.pack_start(self.status, True, True, 0)
        root.pack_start(status_bar, False, False, 0)

        self.refresh()

    def build_columns(self):
        column = Gtk.TreeViewColumn("Aplicación")
        icon_renderer = Gtk.CellRendererPixbuf()
        name_renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        column.pack_start(icon_renderer, False)
        column.pack_start(name_renderer, True)
        column.add_attribute(icon_renderer, "pixbuf", self.C_ICON)
        column.add_attribute(name_renderer, "text", self.C_NAME)
        column.set_sort_column_id(self.C_NAME)
        column.set_resizable(True)
        column.set_fixed_width(280)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.tree.append_column(column)

        def add(title, index, width, sort=None, expand=False, func=None):
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
            new_column = Gtk.TreeViewColumn(title, renderer, text=index)
            new_column.set_sort_column_id(sort if sort is not None else index)
            new_column.set_resizable(True)
            new_column.set_expand(expand)
            if width:
                new_column.set_min_width(width)
            if func:
                new_column.set_cell_data_func(renderer, func)
            self.tree.append_column(new_column)

        def color_source(_column, cell, model, iterator, _data):
            source = model[iterator][self.C_SRC]
            cell.set_property("foreground", SOURCE_COLORS.get(source, "#000000"))
            cell.set_property("weight", Pango.Weight.BOLD)

        add("Origen", self.C_SRC, 90, func=color_source)
        add("Paquete / ID", self.C_ID, 200)
        add("Versión", self.C_VER, 110)
        add("Tamaño", self.C_SIZE, 90, sort=self.C_BYTES)
        add("Descripción", self.C_DESC, 200, expand=True)

    def icon(self, spec):
        if spec in self._icon_cache:
            return self._icon_cache[spec]
        theme = Gtk.IconTheme.get_default()
        pixbuf = None
        try:
            if spec and spec.startswith("/") and os.path.exists(spec):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(spec, ICON_SIZE, ICON_SIZE)
            elif spec and theme.has_icon(spec):
                pixbuf = theme.load_icon(spec, ICON_SIZE, 0)
        except GLib.Error:
            pixbuf = None
        if pixbuf is None:
            try:
                pixbuf = theme.load_icon("application-x-executable", ICON_SIZE, 0)
            except GLib.Error:
                pixbuf = None
        self._icon_cache[spec] = pixbuf
        return pixbuf

    def refresh(self, *_):
        self.spinner.start()
        self.status.set_text("Leyendo aplicaciones instaladas (apt, snap, flatpak, AppImage)…")
        self.refresh_btn.set_sensitive(False)
        threading.Thread(target=lambda: GLib.idle_add(self.loaded, collect_all()),
                         daemon=True).start()

    def loaded(self, apps):
        self.apps = apps
        self.store.clear()
        for index, app in enumerate(apps):
            self.store.append([self.icon(app.icon), app.name, app.source, app.id, app.version,
                               human_size(app.size), app.size, app.desc, index, app.system])
        self.spinner.stop()
        self.refresh_btn.set_sensitive(True)
        self.filter.refilter()
        self.update_status()
        return False

    def visible(self, model, iterator, _data):
        row = model[iterator]
        if row[self.C_SYS] and not self.show_system.get_active():
            return False
        source = self.combo.get_active_text()
        if source not in (None, "Todos") and row[self.C_SRC] != source:
            return False
        query = self.search.get_text().strip().lower()
        if query:
            haystack = f"{row[self.C_NAME]} {row[self.C_ID]} {row[self.C_DESC]}".lower()
            if query not in haystack:
                return False
        return True

    def on_filter_changed(self, *_):
        self.filter.refilter()
        self.update_status()

    def update_status(self):
        counts = {}
        for row in self.sorted:
            counts[row[self.C_SRC]] = counts.get(row[self.C_SRC], 0) + 1
        total = sum(counts.values())
        detail = " · ".join(f"{source}: {count}" for source, count in sorted(counts.items()))
        self.status.set_text(f"{total} elementos" + (f"  ({detail})" if detail else ""))

    def on_selection_changed(self, selection):
        self.remove_btn.set_sensitive(selection.count_selected_rows() > 0)

    def on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Delete and self.remove_btn.get_sensitive():
            self.on_uninstall()
            return True
        return False

    def selected_apps(self):
        model, paths = self.tree.get_selection().get_selected_rows()
        return [self.apps[model[model.get_iter(path)][self.C_IDX]] for path in paths]

    def message(self, kind, title, text):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=kind,
                                   buttons=Gtk.ButtonsType.CLOSE, text=title)
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()

    def confirm(self, apps):
        """Muestra qué se va a borrar. Devuelve (purge, autoremove) o None."""
        extra = []
        apt_ids = [app.id for app in apps if app.source == "APT"]
        if apt_ids:
            result = subprocess.run(["apt-get", "-s", "remove"] + apt_ids,
                                    capture_output=True, text=True, env=ENV_C)
            if result.returncode != 0:
                error = (result.stderr or result.stdout).strip()[-1500:]
                self.message(Gtk.MessageType.ERROR, "APT no puede quitar esos paquetes", error)
                return None
            base = {package.split(":")[0] for package in apt_ids}
            removed = re.findall(r"^Remv (\S+)", result.stdout, re.M)
            extra = [package for package in removed if package.split(":")[0] not in base]

        dialog = Gtk.Dialog(title="Confirmar desinstalación", transient_for=self, modal=True)
        dialog.set_default_size(560, 440)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        confirm_button = dialog.add_button("Desinstalar", Gtk.ResponseType.OK)
        confirm_button.get_style_context().add_class("destructive-action")
        box = dialog.get_content_area()
        box.set_spacing(8)
        for margin in ("margin_top", "margin_start", "margin_end", "margin_bottom"):
            box.set_property(margin, 10)

        lines = ["Se desinstalará:"]
        lines += [f"  • {app.name}   [{app.source}: {app.id}]" for app in apps]
        if extra:
            lines += ["", f"⚠ APT también eliminará {len(extra)} paquete(s) que dependen de ellos:"]
            lines += [f"  • {package}" for package in extra]
        buffer = Gtk.TextBuffer()
        buffer.set_text("\n".join(lines))
        view = Gtk.TextView(buffer=buffer, editable=False, monospace=True, cursor_visible=False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.add(view)
        scroll.set_vexpand(True)
        box.pack_start(scroll, True, True, 0)

        purge = Gtk.CheckButton(label="Borrar también configuración y datos (purge)")
        box.pack_start(purge, False, False, 0)
        autoremove = Gtk.CheckButton(
            label="Ejecutar «apt autoremove» para quitar dependencias huérfanas"
        )
        if apt_ids:
            box.pack_start(autoremove, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        options = ((purge.get_active(), autoremove.get_active())
                   if response == Gtk.ResponseType.OK else None)
        dialog.destroy()
        return options

    def on_uninstall(self, *_):
        apps = self.selected_apps()
        if not apps:
            return
        options = self.confirm(apps)
        if options is None:
            return
        dialog = RunDialog(self, build_plan(apps, *options))
        dialog.run()
        dialog.destroy()
        self.refresh()
        


def main():
    window = Window()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
