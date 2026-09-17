#!/usr/bin/env bash
set -euo pipefail

# Configurable paths with environment overrides for flexibility and unit testing
GDM_WALLPAPER="${GDM_WALLPAPER:-/usr/share/backgrounds/waywallen_lock.jpg}"
GRESOURCE_FILE="${GRESOURCE_FILE:-/usr/share/gnome-shell/gnome-shell-theme.gresource}"
TARGET_USER="${TARGET_USER:-${SUDO_USER:-$USER}}"
BACKUP_FILE="${GRESOURCE_FILE}.backup"

# Helper print functions
info() { echo -e "\033[0;34m[INFO]\033[0m $*"; }
success() { echo -e "\033[0;32m[OK]\033[0m $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; }

# Handle restore option
if [[ "${1:-}" == "--restore" || "${1:-}" == "--uninstall" ]]; then
    info "Restaurando tema original de GDM..."
    if [[ ! -f "$BACKUP_FILE" ]]; then
        error "No se encontró archivo de respaldo en: $BACKUP_FILE"
        exit 1
    fi
    cp -f "$BACKUP_FILE" "$GRESOURCE_FILE"
    chmod 644 "$GRESOURCE_FILE"
    success "Tema original restaurado con éxito desde $BACKUP_FILE"
    exit 0
fi

# Check root privileges if modifying system files
if [[ "$GRESOURCE_FILE" == "/usr"* ]] && [[ $EUID -ne 0 ]]; then
    error "Este script requiere permisos de superusuario (root) para configurar el tema de GDM."
    error "Por favor ejecuta: sudo $0"
    exit 1
fi

# Verify required tools
for tool in gresource glib-compile-resources; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        error "Herramienta requerida no encontrada: $tool"
        exit 1
    fi
done

if [[ ! -f "$GRESOURCE_FILE" ]]; then
    error "No se encontró el archivo gresource en: $GRESOURCE_FILE"
    exit 1
fi

# 1. Crear respaldo si no existe
if [[ ! -f "$BACKUP_FILE" ]]; then
    info "Creando respaldo de seguridad en: $BACKUP_FILE"
    cp -f "$GRESOURCE_FILE" "$BACKUP_FILE"
    chmod 644 "$BACKUP_FILE"
else
    info "Respaldo existente detectado en: $BACKUP_FILE"
fi

# 2. Asegurar ruta pública del fondo con permisos de escritura para el usuario
info "Configurando ruta global del wallpaper: $GDM_WALLPAPER"
mkdir -p "$(dirname "$GDM_WALLPAPER")"
touch "$GDM_WALLPAPER"
if [[ -n "$TARGET_USER" ]]; then
    chown "$TARGET_USER:$TARGET_USER" "$GDM_WALLPAPER" 2>/dev/null || true
fi
chmod 644 "$GDM_WALLPAPER"

# 3. Extraer recursos del tema a un directorio temporal
TMP_WORK="$(mktemp -d)"
trap 'rm -rf "$TMP_WORK"' EXIT

info "Extrayendo recursos del tema GNOME Shell..."
RESOURCES=$(gresource list "$GRESOURCE_FILE" | grep "^/org/gnome/shell/theme/" || true)
if [[ -z "$RESOURCES" ]]; then
    error "No se pudieron listar los recursos de: $GRESOURCE_FILE"
    exit 1
fi

XML_ENTRIES=()
while IFS= read -r res_path; do
    rel_path="${res_path#/org/gnome/shell/theme/}"
    dest_file="$TMP_WORK/$rel_path"
    mkdir -p "$(dirname "$dest_file")"
    gresource extract "$GRESOURCE_FILE" "$res_path" > "$dest_file"
    XML_ENTRIES+=("$rel_path")
done <<< "$RESOURCES"

# 4. Inyectar regla CSS para el fondo de GDM
CSS_RULES="
/* Waywallen GDM Sync Rule */
.login-dialog {
  background-color: transparent !important;
}
#lockDialogGroup {
  background-image: url('file://$GDM_WALLPAPER') !important;
  background-repeat: no-repeat !important;
  background-size: 100% 100% !important;
  background-position: 0 0 !important;
}
"

info "Inyectando reglas CSS para carga directa desde $GDM_WALLPAPER..."
MODIFIED_CSS=0
for css_candidate in gnome-shell.css gnome-shell-dark.css gnome-shell-light.css gnome-shell-high-contrast.css gdm.css gdm3.css; do
    css_path="$TMP_WORK/$css_candidate"
    if [[ -f "$css_path" ]]; then
        echo "$CSS_RULES" >> "$css_path"
        MODIFIED_CSS=$((MODIFIED_CSS + 1))
    fi
done

if [[ $MODIFIED_CSS -eq 0 ]]; then
    # Si no había un archivo estándar existente, crear gnome-shell.css
    echo "$CSS_RULES" > "$TMP_WORK/gnome-shell.css"
    XML_ENTRIES+=("gnome-shell.css")
fi

# 5. Generar XML para glib-compile-resources
XML_FILE="$TMP_WORK/gnome-shell-theme.gresource.xml"
{
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<gresources>'
    echo '  <gresource prefix="/org/gnome/shell/theme">'
    # Eliminar duplicados si los hay
    printf "%s\n" "${XML_ENTRIES[@]}" | sort -u | while IFS= read -r entry; do
        echo "    <file>$entry</file>"
    done
    echo '  </gresource>'
    echo '</gresources>'
} > "$XML_FILE"

# 6. Compilar nuevo gresource
COMPILED_RESOURCE="$TMP_WORK/gnome-shell-theme.gresource"
info "Compilando tema con glib-compile-resources..."
glib-compile-resources --sourcedir="$TMP_WORK" --target="$COMPILED_RESOURCE" "$XML_FILE"

# 7. Instalar el nuevo archivo gresource
info "Instalando tema modificado en: $GRESOURCE_FILE"
install -m 644 "$COMPILED_RESOURCE" "$GRESOURCE_FILE"

success "¡GDM configurado exitosamente!"
echo ""
echo "El tema de inicio de sesión de GNOME (GDM) ahora leerá directamente:"
echo "  $GDM_WALLPAPER"
echo "Permisos de escritura asignados a: $TARGET_USER"
echo ""
echo "Para sincronizar tu wallpaper actual de inmediato, ejecuta:"
echo "  sync-waywallen-lockscreen.sh"
echo "Y para restaurar el tema original de fábrica en cualquier momento:"
echo "  sudo $0 --restore"
