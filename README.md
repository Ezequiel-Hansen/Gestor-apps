# Gestor de aplicaciones

Aplicación gráfica para consultar aplicaciones instaladas desde APT, Snap, Flatpak y AppImage, y desinstalarlas desde una sola ventana.

## Requisitos

- Ubuntu o una distribución basada en Debian con `apt`.
- Python 3.
- GTK 3 y PyGObject. El instalador comprueba estas dependencias y, si faltan, solicita la contraseña para instalarlas.
- `pkexec` (polkit) para desinstalar paquetes que requieren permisos de administrador. Sin `pkexec`, la aplicación puede abrirse, pero algunas desinstalaciones no estarán disponibles.

## Instalación

1. Descarga o copia el proyecto completo; conserva juntos `install.sh`, `gestor_apps.py` y la carpeta `lib/`.
2. Abre una terminal en esa carpeta.
3. Ejecuta:

   ```bash
   chmod +x install.sh
   ./install.sh
   ```

   **No ejecutes el instalador con `sudo`.** La aplicación se instala para tu usuario y pedirá autorización cuando sea necesaria.

Al finalizar, puedes abrir **Gestor de aplicaciones** desde el menú de aplicaciones o ejecutarlo desde la terminal con:

```bash
gestor-apps
```

Si el comando no se encuentra, cierra y vuelve a abrir la sesión o ejecútalo directamente:

```bash
"$HOME/.local/bin/gestor-apps"
```

## Ejecución sin instalar

Si las dependencias ya están instaladas, también puedes iniciar la aplicación desde la carpeta del proyecto:

```bash
python3 gestor_apps.py
```

## Desinstalación

Desde la carpeta del proyecto, ejecuta:

```bash
./install.sh --desinstalar
```

También se acepta `--uninstall`. Esto elimina la aplicación instalada, su comando de terminal y su acceso directo del menú; no desinstala las dependencias del sistema ni las aplicaciones gestionadas.

## Problemas habituales

| Problema | Qué hacer |
|---|---|
| `No encuentro la carpeta lib` | Comprueba que ejecutas `install.sh` desde una copia completa del proyecto y que `lib/` está junto al instalador. |
| Falta GTK o PyGObject | Vuelve a ejecutar `./install.sh`; en Ubuntu/Debian instalará `python3-gi` y `gir1.2-gtk-3.0` si faltan. |
| `gestor-apps: command not found` | Abre una nueva sesión o usa `"$HOME/.local/bin/gestor-apps"`. |
| No se pueden desinstalar paquetes del sistema | Comprueba que `pkexec` está instalado y que polkit está disponible en tu sesión. |


## Implementacion a futuro 

1. Que funcione en mas distros de Linux
