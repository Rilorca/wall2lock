#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Instalando Wall2Lock..."

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
    echo "  - Arch / CachyOS / Manjaro: sudo pacman -S python-pillow ffmpeg sqlite glib2 libadwaita"
    echo "  - Ubuntu / Debian:          sudo apt install python3-pil ffmpeg sqlite3 libglib2.0-dev-bin gir1.2-adw-1"
    echo "  - Fedora:                   sudo dnf install python3-pillow ffmpeg sqlite glib2-devel libadwaita"
    echo ""
    read -p "¿Deseas continuar de todas formas? (s/N): " -r CONFIRM
    if [[ ! "$CONFIRM" =~ ^[sSyY]$ ]]; then
        exit 1
    fi
fi

# 1. Copiar scripts a ~/.local/bin y preparar directorio de capturas
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/waywallen/captures"
mkdir -p "$HOME/.local/share/applications"

# Script principal de sincronización
cp -f "$SCRIPT_DIR/sync-wall2lock.sh" "$HOME/.local/bin/wall2lock-sync"
chmod +x "$HOME/.local/bin/wall2lock-sync"
ln -sf "$HOME/.local/bin/wall2lock-sync" "$HOME/.local/bin/sync-waywallen-lockscreen.sh"

# Motor extractor de fondos
cp -f "$SCRIPT_DIR/wall2lock_extractor.py" "$HOME/.local/bin/wall2lock_extractor.py"
chmod +x "$HOME/.local/bin/wall2lock_extractor.py"
ln -sf "$HOME/.local/bin/wall2lock_extractor.py" "$HOME/.local/bin/waywallen_extractor.py"

# Interfaz gráfica Adwaita
cp -f "$SCRIPT_DIR/wall2lock_gui.py" "$HOME/.local/bin/wall2lock-gui"
chmod +x "$HOME/.local/bin/wall2lock-gui"
ln -sf "$HOME/.local/bin/wall2lock-gui" "$HOME/.local/bin/waywallen-lockscreen-sync-gui"

# Acceso directo de escritorio
cp -f "$SCRIPT_DIR/wall2lock-gui.desktop" "$HOME/.local/share/applications/"
rm -f "$HOME/.local/share/applications/waywallen-lockscreen-sync-gui.desktop" 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$HOME/.local/share/applications" || true

# Instalar iconos de la aplicación
if [[ -f "$SCRIPT_DIR/assets/wall2lock.png" ]]; then
    for sz in 512 256 128 64 48 32; do
        SZ_DIR="$HOME/.local/share/icons/hicolor/${sz}x${sz}/apps"
        mkdir -p "$SZ_DIR"
        python3 -c "from PIL import Image; Image.open('$SCRIPT_DIR/assets/wall2lock.png').resize(($sz, $sz)).save('$SZ_DIR/wall2lock.png')" 2>/dev/null || cp -f "$SCRIPT_DIR/assets/wall2lock.png" "$SZ_DIR/wall2lock.png"
        ln -sf "$SZ_DIR/wall2lock.png" "$SZ_DIR/io.github.rilorca.wall2lock.png"
    done
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# 2. Integrar captura nativa de alta fidelidad con renderer de GNOME si está disponible
if [[ -f "$SCRIPT_DIR/patch-renderer.py" ]]; then
    echo "Configurando captura nativa de alta resolución con Waywallen..."
    python3 "$SCRIPT_DIR/patch-renderer.py" || true
    pkill -f "renderer.js" 2>/dev/null || true
fi

# 3. Desactivar y limpiar unidades antiguas de systemd si existen
systemctl --user stop waywallen-lockscreen-sync.path 2>/dev/null || true
systemctl --user disable waywallen-lockscreen-sync.path waywallen-lockscreen-sync.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/waywallen-lockscreen-sync.path" "$HOME/.config/systemd/user/waywallen-lockscreen-sync.service" 2>/dev/null || true

# 4. Copiar e iniciar nuevas unidades de systemd para Wall2Lock
mkdir -p "$HOME/.config/systemd/user"
cp -f "$SCRIPT_DIR/wall2lock.service" "$HOME/.config/systemd/user/"
cp -f "$SCRIPT_DIR/wall2lock.path" "$HOME/.config/systemd/user/"

systemctl --user daemon-reload
systemctl --user enable wall2lock.service
systemctl --user enable --now wall2lock.path

# 5. Ejecutar sincronización inicial
"$HOME/.local/bin/wall2lock-sync"

echo ""
echo "¡Instalación de Wall2Lock completada con éxito!"
echo "El lockscreen se sincronizará automáticamente:"
echo "  1) En cada arranque del PC / inicio de sesión (vía service)"
echo "  2) En tiempo real cada vez que cambies de fondo en Waywallen o skwd-wall (vía path)"
echo "  3) Puedes abrir el centro de control en cualquier momento buscando 'Wall2Lock' o con 'wall2lock-gui'"
echo ""

# Detectar gestor de pantalla (GDM vs SDDM)
if systemctl is-active --quiet gdm 2>/dev/null || pgrep -x gdm >/dev/null 2>&1 || [[ "${XDG_CURRENT_DESKTOP:-}" == *"GNOME"* ]]; then
    echo "============================================================"
    echo " [PASO FUNDAMENTAL] Configuración de tema para GDM:"
    echo " Para que el fondo se cargue al encender el PC en el login:"
    echo "   sudo $SCRIPT_DIR/setup-gdm-theme.sh"
    echo "============================================================"
    if [[ -t 0 ]]; then
        read -p "¿Deseas configurar GDM ahora mismo con sudo? (S/n): " -r RUN_GDM
        if [[ -z "$RUN_GDM" || "$RUN_GDM" =~ ^[sSyY]$ ]]; then
            sudo "$SCRIPT_DIR/setup-gdm-theme.sh"
        fi
    fi
elif systemctl is-active --quiet sddm 2>/dev/null || pgrep -x sddm >/dev/null 2>&1; then
    echo "============================================================"
    echo " [PASO FUNDAMENTAL] Configuración de tema para SDDM:"
    echo " Para que el fondo se cargue en la pantalla de inicio de SDDM:"
    echo "   sudo $SCRIPT_DIR/setup-sddm-theme.sh"
    echo "============================================================"
    if [[ -t 0 ]]; then
        read -p "¿Deseas configurar SDDM ahora mismo con sudo? (S/n): " -r RUN_SDDM
        if [[ -z "$RUN_SDDM" || "$RUN_SDDM" =~ ^[sSyY]$ ]]; then
            sudo "$SCRIPT_DIR/setup-sddm-theme.sh"
        fi
    fi
else
    echo "Para habilitar el fondo en el inicio del PC según tu gestor de login:"
    echo "  GNOME/GDM: sudo $SCRIPT_DIR/setup-gdm-theme.sh"
    echo "  SDDM:      sudo $SCRIPT_DIR/setup-sddm-theme.sh"
fi
