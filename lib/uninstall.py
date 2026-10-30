"""Construcción de planes para desinstalar aplicaciones."""

import glob
import os
import shlex

def remove_appimages(paths):
    def action(log):
        rc = 0
        for path in paths:
            try:
                os.remove(path)
                log(f"Eliminado: {path}\n")
            except OSError as exc:
                log(f"Error al eliminar {path}: {exc}\n")
                rc = 1
        pattern = os.path.expanduser("~/.local/share/applications/*.desktop")
        for desktop in glob.glob(pattern):
            try:
                with open(desktop, encoding="utf-8", errors="ignore") as file:
                    text = file.read()
                if any(path in text for path in paths):
                    os.remove(desktop)
                    log(f"Eliminado acceso directo: {desktop}\n")
            except OSError:
                pass
        return rc
    return action


def build_plan(apps, purge, autoremove):
    plan = []

    apt = [app.id for app in apps if app.source == "APT"]
    if apt:
        verb = "purge" if purge else "remove"
        script = f"apt-get {verb} -y " + " ".join(shlex.quote(package) for package in apt)
        if autoremove:
            script += " && apt-get autoremove -y"
        plan.append(("APT", ["pkexec", "env", "DEBIAN_FRONTEND=noninteractive",
                             "sh", "-c", script]))

    snaps = [app.id for app in apps if app.source == "Snap"]
    if snaps:
        command = ["pkexec", "snap", "remove"] + (["--purge"] if purge else []) + snaps
        plan.append(("Snap", command))

    by_scope = {}
    for app in apps:
        if app.source == "Flatpak":
            by_scope.setdefault(app.scope, []).append(app.id)
    for scope, ids in by_scope.items():
        flag = f"--{scope}" if scope in ("system", "user") else f"--installation={scope}"
        command = ["flatpak", "uninstall", "-y", "--noninteractive", flag]
        if purge:
            command.append("--delete-data")
        plan.append((f"Flatpak ({scope})", command + ids))

    local, root = [], []
    for app in apps:
        if app.source == "AppImage":
            (local if os.access(os.path.dirname(app.id), os.W_OK) else root).append(app.id)
    if local:
        plan.append(("AppImage", remove_appimages(local)))
    for path in root:
        plan.append((f"AppImage (root): {os.path.basename(path)}",
                     ["pkexec", "rm", "-f", path]))
    return plan
