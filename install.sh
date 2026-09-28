#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Instalando waywallen-lockscreen-sync..."

# 0. Verificar dependencias básicas
MISSING_DEPS=()
for cmd in python3 ffmpeg sqlite3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        MISSING_DEPS+=("$cmd")
    fi
done

if ! python3 -c "from PIL import Image" >/dev/null 2>&1; then
    MISSING_DEPS+=("python3-pillow")
fi

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo -e "\033[0;33m[AVISO] Faltan dependencias necesarias: ${MISSING_DEPS[*]}\033[0m"
    echo "Instálalas con tu gestor de paquetes:"
    echo "  - Arch / CachyOS / Manjaro: sudo pacman -S python-pillow ffmpeg sqlite glib2"
    echo "  - Ubuntu / Debian:          sudo apt install python3-pil ffmpeg sqlite3 libglib2.0-dev-bin"
    echo "  - Fedora:                   sudo dnf install python3-pillow ffmpeg sqlite glib2-devel"
    echo ""
    read -p "¿Deseas continuar de todas formas? (s/N): " -r CONFIRM
    if [[ ! "$CONFIRM" =~ ^[sSyY]$ ]]; then
        exit 1
    fi
fi

# 1. Copiar scripts a ~/.local/bin y preparar directorio de capturas
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/waywallen/captures"
cp -f "$SCRIPT_DIR/sync-waywallen-lockscreen.sh" "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/sync-waywallen-lockscreen.sh"
cp -f "$SCRIPT_DIR/waywallen_extractor.py" "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/waywallen_extractor.py"

# 2. Integrar captura nativa de alta fidelidad con renderer de GNOME si está disponible
if [[ -f "$SCRIPT_DIR/patch-renderer.py" ]]; then
    echo "Configurando captura nativa de alta resolución con Waywallen..."
    python3 "$SCRIPT_DIR/patch-renderer.py" || true
    pkill -f "renderer.js" 2>/dev/null || true
fi

# 3. Copiar unidades de systemd
mkdir -p "$HOME/.config/systemd/user"
cp -f "$SCRIPT_DIR/waywallen-lockscreen-sync.service" "$HOME/.config/systemd/user/"
cp -f "$SCRIPT_DIR/waywallen-lockscreen-sync.path" "$HOME/.config/systemd/user/"

# 3. Recargar e iniciar watcher y servicio al arranque
systemctl --user daemon-reload
systemctl --user enable waywallen-lockscreen-sync.service
systemctl --user enable --now waywallen-lockscreen-sync.path

# 4. Ejecutar sincronización inicial
"$HOME/.local/bin/sync-waywallen-lockscreen.sh"

echo ""
echo "¡Instalación de usuario completada con éxito!"
echo "El lockscreen se sincronizará automáticamente:"
echo "  1) En cada arranque del PC / inicio de sesión (vía service)"
echo "  2) En tiempo real cada vez que cambies de fondo en Waywallen (vía path)"
echo ""

# Detectar gestor de pantalla (GDM vs SDDM)
if systemctl is-active --quiet gdm 2>/dev/null || pgrep -x gdm >/dev/null 2>&1 || [[ "${XDG_CURRENT_DESKTOP:-}" == *"GNOME"* ]]; then
    echo "============================================================"
    echo " Se detectó GNOME Display Manager (GDM)."
    echo " Para que el fondo se vea al encender el PC (reinicio/login):"
    echo "   sudo $SCRIPT_DIR/setup-gdm-theme.sh"
    echo "============================================================"
elif systemctl is-active --quiet sddm 2>/dev/null || pgrep -x sddm >/dev/null 2>&1; then
    echo "============================================================"
    echo " Se detectó SDDM."
    echo " Para habilitar el fondo en SDDM (pantalla previa al login):"
    echo "   sudo $SCRIPT_DIR/setup-sddm-theme.sh"
    echo "============================================================"
else
    echo "Para habilitar el fondo en el inicio del PC según tu gestor:"
    echo "  GNOME/GDM: sudo $SCRIPT_DIR/setup-gdm-theme.sh"
    echo "  SDDM:      sudo $SCRIPT_DIR/setup-sddm-theme.sh"
fi
