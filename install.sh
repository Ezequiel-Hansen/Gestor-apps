#!/usr/bin/env bash
# ============================================================================
#  Instalador de "Gestor de aplicaciones" para Ubuntu
#
#  Uso:
#     ./install.sh                  Instala la app para el usuario actual
#     ./install.sh --desinstalar    Quita la app
#
#  Requisito: tener gestor_apps.py y la carpeta lib junto a este script.
#  No hace falta ejecutarlo con sudo (solo pedirá contraseña si faltan
#  dependencias del sistema).
# ============================================================================
set -euo pipefail

APP_ID="gestor-apps"
APP_NAME="Gestor de aplicaciones"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_FILE="$SCRIPT_DIR/gestor_apps.py"
SRC_MODULES="$SCRIPT_DIR/lib"

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_DIR/$APP_ID"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/$APP_ID"
DESKTOP_DIR="$DATA_DIR/applications"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"

# ---- utilidades de salida --------------------------------------------------
if [ -t 1 ]; then
    G=$'\033[1;32m'; Y=$'\033[1;33m'; R=$'\033[1;31m'; B=$'\033[1;34m'; N=$'\033[0m'
else
    G=""; Y=""; R=""; B=""; N=""
fi
info()  { echo "${B}==>${N} $*"; }
ok()    { echo "${G} ✔${N} $*"; }
warn()  { echo "${Y} !${N} $*"; }
fail()  { echo "${R} ✘ $*${N}" >&2; exit 1; }

# ---- comprobaciones previas ------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
    fail "No ejecutes este script como root ni con sudo: se instalaría en la carpeta de root.
   Ejecútalo como tu usuario normal:  ./install.sh"
fi

refrescar_menus() {
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
}

# ---- desinstalación --------------------------------------------------------
if [ "${1:-}" = "--desinstalar" ] || [ "${1:-}" = "--uninstall" ]; then
    info "Desinstalando $APP_NAME..."
    rm -rf "$INSTALL_DIR"
    rm -f "$LAUNCHER" "$DESKTOP_FILE"
    refrescar_menus
    ok "$APP_NAME fue desinstalado."
    exit 0
fi

if [ -n "${1:-}" ]; then
    fail "Opción desconocida: $1
   Uso: ./install.sh [--desinstalar]"
fi

[ -f "$SRC_FILE" ] || fail "No encuentro gestor_apps.py en: $SCRIPT_DIR
   Pon install.sh y gestor_apps.py en la misma carpeta."
[ -d "$SRC_MODULES" ] || fail "No encuentro la carpeta lib en: $SCRIPT_DIR
   Pon la carpeta lib junto a install.sh."

command -v /usr/bin/python3 >/dev/null 2>&1 || fail "No se encontró /usr/bin/python3."

# ---- dependencias ----------------------------------------------------------
info "Comprobando dependencias (Python + GTK 3)..."
gtk_ok() {
    /usr/bin/python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf
PY
}

if gtk_ok; then
    ok "Dependencias ya instaladas."
else
    warn "Faltan dependencias. Se instalarán: python3-gi gir1.2-gtk-3.0"
    command -v apt-get >/dev/null 2>&1 || fail "Este instalador necesita apt (Ubuntu/Debian)."
    sudo apt-get update
    sudo apt-get install -y python3-gi gir1.2-gtk-3.0
    gtk_ok || fail "GTK 3 sigue sin estar disponible para Python tras instalar."
    ok "Dependencias instaladas."
fi

if ! command -v pkexec >/dev/null 2>&1; then
    warn "No se encontró 'pkexec' (polkit). Sin él no se podrán desinstalar paquetes de APT/Snap."
    warn "Instálalo con:  sudo apt install policykit-1   (o 'polkitd pkexec' en Ubuntu reciente)"
fi

# ---- copiar archivos -------------------------------------------------------
info "Instalando archivos en $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"
install -m 755 "$SRC_FILE" "$INSTALL_DIR/gestor_apps.py"
install -d "$INSTALL_DIR/lib"
install -m 644 "$SRC_MODULES"/*.py "$INSTALL_DIR/lib/"
ok "Programa y módulos copiados."

# ---- lanzador de terminal --------------------------------------------------
cat > "$LAUNCHER" <<EOF
#!/bin/sh
exec /usr/bin/python3 "$INSTALL_DIR/gestor_apps.py" "\$@"
EOF
chmod 755 "$LAUNCHER"
ok "Comando creado: $APP_ID"

# ---- acceso directo en el menú de aplicaciones -----------------------------
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Gestor de paquetes
Comment=Ver y desinstalar aplicaciones de APT, Snap, Flatpak y AppImage
Exec=/usr/bin/python3 $INSTALL_DIR/gestor_apps.py
Icon=system-software-install
Terminal=false
StartupNotify=true
Categories=System;Settings;PackageManager;
Keywords=apt;snap;flatpak;appimage;desinstalar;aplicaciones;paquetes;
EOF
chmod 644 "$DESKTOP_FILE"
refrescar_menus
ok "Acceso directo creado en el menú de aplicaciones."

# ---- aviso sobre PATH ------------------------------------------------------
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR no está en tu PATH. Para usar el comando '$APP_ID' desde la terminal,"
       warn "cierra y vuelve a abrir la sesión (Ubuntu lo agrega solo si la carpeta existe al iniciar)." ;;
esac

echo
ok "¡Instalación completa!"
echo "   • Búscalo en el menú de aplicaciones como: $APP_NAME"
echo "   • O ejecútalo desde la terminal con:       $APP_ID"
echo "   • Para quitarlo:                           ./install.sh --desinstalar"
