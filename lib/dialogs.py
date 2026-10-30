"""Diálogos gráficos y ejecución de tareas de desinstalación."""

import shlex
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


class RunDialog(Gtk.Dialog):
    def __init__(self, parent, plan):
        super().__init__(title="Desinstalando…", transient_for=parent, modal=True)
        self.set_default_size(680, 400)
        self.running = True
        self.ok = True

        self.close_btn = self.add_button("Cerrar", Gtk.ResponseType.CLOSE)
        self.close_btn.set_sensitive(False)

        box = self.get_content_area()
        box.set_spacing(8)
        for margin in ("margin_top", "margin_start", "margin_end", "margin_bottom"):
            box.set_property(margin, 10)

        head = Gtk.Box(spacing=8)
        self.spinner = Gtk.Spinner()
        self.spinner.start()
        self.title_lbl = Gtk.Label(label="Trabajando… puede pedirte tu contraseña.", xalign=0)
        head.pack_start(self.spinner, False, False, 0)
        head.pack_start(self.title_lbl, True, True, 0)
        box.pack_start(head, False, False, 0)

        self.buf = Gtk.TextBuffer()
        self.view = Gtk.TextView(buffer=self.buf, editable=False, monospace=True)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.view)
        scroll.set_vexpand(True)
        box.pack_start(scroll, True, True, 0)

        self.connect("delete-event", lambda *_: self.running)
        self.show_all()
        threading.Thread(target=self.worker, args=(plan,), daemon=True).start()

    def log(self, text):
        GLib.idle_add(self._append, text)

    def _append(self, text):
        self.buf.insert(self.buf.get_end_iter(), text)
        mark = self.buf.create_mark(None, self.buf.get_end_iter(), False)
        self.view.scroll_mark_onscreen(mark)
        return False

    def worker(self, plan):
        for title, action in plan:
            self.log(f"\n▶ {title}\n")
            if callable(action):
                rc = action(self.log)
            else:
                self.log("$ " + " ".join(shlex.quote(arg) for arg in action) + "\n")
                try:
                    process = subprocess.Popen(action, stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT, text=True, bufsize=1)
                    for line in process.stdout:
                        self.log(line)
                    rc = process.wait()
                except FileNotFoundError:
                    self.log(f"No se encontró el comando: {action[0]}\n")
                    rc = 127
            if rc == 0:
                self.log("✔ Correcto\n")
            else:
                self.ok = False
                extra = " (autenticación cancelada o denegada)" if rc in (126, 127) else ""
                self.log(f"✘ Falló con código {rc}{extra}\n")
        GLib.idle_add(self.finish)

    def finish(self):
        self.running = False
        self.spinner.stop()
        self.title_lbl.set_text("Terminado correctamente." if self.ok
                                else "Terminó con errores, revisa el registro.")
        self.set_title("Desinstalación finalizada")
        self.close_btn.set_sensitive(True)
        return False
