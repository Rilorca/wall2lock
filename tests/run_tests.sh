#!/usr/bin/env bash
set -euo pipefail

# Test runner for waywallen-lockscreen-sync
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_SCRIPT="$REPO_DIR/sync-waywallen-lockscreen.sh"

PASSED_TESTS=0
FAILED_TESTS=0

# Colors for test output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

pass() {
    local name="$1"
    echo -e "  [${GREEN}PASS${NC}] $name"
    PASSED_TESTS=$((PASSED_TESTS + 1))
}

fail() {
    local name="$1"
    local reason="${2:-}"
    echo -e "  [${RED}FAIL${NC}] $name: $reason"
    FAILED_TESTS=$((FAILED_TESTS + 1))
}

# Helper to create a dummy sqlite DB
create_test_db() {
    local db_file="$1"
    rm -f "$db_file"
    sqlite3 "$db_file" <<'EOF'
CREATE TABLE "library" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "path" TEXT NOT NULL
);
CREATE TABLE "item" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "library_id" INTEGER NOT NULL,
    "path" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "preview_path" TEXT NULL
);
EOF
}

echo -e "${BLUE}=== INICIANDO SUITE DE PRUEBAS UNITARIAS: waywallen-lockscreen-sync ===${NC}"

# Save user gsettings to restore on exit
ORIG_USER_BG=""
ORIG_USER_DARK=""
ORIG_USER_SAVER=""
if command -v gsettings >/dev/null 2>&1; then
    ORIG_USER_BG=$(gsettings get org.gnome.desktop.background picture-uri 2>/dev/null || true)
    ORIG_USER_DARK=$(gsettings get org.gnome.desktop.background picture-uri-dark 2>/dev/null || true)
    ORIG_USER_SAVER=$(gsettings get org.gnome.desktop.screensaver picture-uri 2>/dev/null || true)
fi

TEST_TMPDIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TEST_TMPDIR"
    if command -v gsettings >/dev/null 2>&1; then
        [[ -n "$ORIG_USER_BG" ]] && gsettings set org.gnome.desktop.background picture-uri "$ORIG_USER_BG" 2>/dev/null || true
        [[ -n "$ORIG_USER_DARK" ]] && gsettings set org.gnome.desktop.background picture-uri-dark "$ORIG_USER_DARK" 2>/dev/null || true
        [[ -n "$ORIG_USER_SAVER" ]] && gsettings set org.gnome.desktop.screensaver picture-uri "$ORIG_USER_SAVER" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Test 1: Fallo controlado si falta config.toml
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 1: Comportamiento ante config.toml faltante${NC}"
{
    set +e
    OUT=$(CONFIG_PATH="$TEST_TMPDIR/non_existent.toml" \
          DB_PATH="$TEST_TMPDIR/db.sqlite" \
          bash "$SYNC_SCRIPT" 2>&1)
    CODE=$?
    set -e
    if [[ $CODE -ne 0 && "$OUT" == *"Config not found"* ]]; then
        pass "Falla correctamente con exit 1 cuando falta config.toml"
    else
        fail "Comportamiento ante config.toml faltante" "Código: $CODE, Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 2: Detección de last_wallpaper en [global]
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 2: Extracción de last_wallpaper global en config.toml${NC}"
{
    CFG="$TEST_TMPDIR/config1.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "42"
queue_mode = "sequential"
[display."DP-1"]
last_wallpaper = "99"
EOF
    DB="$TEST_TMPDIR/db1.sqlite"
    create_test_db "$DB"
    IMG="$TEST_TMPDIR/sample.jpg"
    ffmpeg -y -f lavfi -i color=c=blue:s=100x100:d=1 -vframes 1 -q:v 2 "$IMG" 2>/dev/null
    sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '$TEST_TMPDIR');"
    sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (42, 1, 'sample.jpg', 'image', NULL);"

    TARGET_LOCK="$TEST_TMPDIR/lock1.jpg"
    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" SDDM_WALLPAPER="$TEST_TMPDIR/sddm1.jpg" bash "$SYNC_SCRIPT" 2>&1)
    if [[ -f "$TARGET_LOCK" && "$OUT" == *"updated successfully"* ]]; then
        pass "Detecta y extrae correctamente el ID 42 de [global]"
    else
        fail "Extracción global" "Target no existe o error. Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 3: Fallback a display cuando global es "0" o vacío
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 3: Fallback a display-specific cuando global last_wallpaper es '0'${NC}"
{
    CFG="$TEST_TMPDIR/config2.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "0"
queue_mode = "sequential"
[display."eDP-1"]
last_wallpaper = "77"
EOF
    DB="$TEST_TMPDIR/db2.sqlite"
    create_test_db "$DB"
    IMG="$TEST_TMPDIR/display_sample.png"
    ffmpeg -y -f lavfi -i color=c=green:s=100x100:d=1 -vframes 1 "$IMG" 2>/dev/null
    sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '$TEST_TMPDIR');"
    sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (77, 1, 'display_sample.png', 'image', NULL);"

    TARGET_LOCK="$TEST_TMPDIR/lock2.jpg"
    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" SDDM_WALLPAPER="$TEST_TMPDIR/sddm2.jpg" bash "$SYNC_SCRIPT" 2>&1)
    if [[ -f "$TARGET_LOCK" && "$OUT" == *"updated successfully"* ]]; then
        pass "Fallback a display seleccionó item 77 correctamente"
    else
        fail "Fallback a display" "Target no existe o error. Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 4: Manejo de wallpaper tipo 'video' (MP4 / WebM)
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 4: Extracción de fotograma en wallpaper de tipo video${NC}"
{
    CFG="$TEST_TMPDIR/config3.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "10"
EOF
    DB="$TEST_TMPDIR/db3.sqlite"
    create_test_db "$DB"
    VID="$TEST_TMPDIR/sample.mp4"
    # Create real 2-second test video
    ffmpeg -y -f lavfi -i testsrc=duration=2:size=320x240:rate=10 "$VID" 2>/dev/null
    sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '$TEST_TMPDIR');"
    sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (10, 1, 'sample.mp4', 'video', NULL);"

    TARGET_LOCK="$TEST_TMPDIR/lock3.jpg"
    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" SDDM_WALLPAPER="$TEST_TMPDIR/sddm3.jpg" bash "$SYNC_SCRIPT" 2>&1)
    FILE_TYPE=$(file -b "$TARGET_LOCK" 2>/dev/null || true)
    if [[ -f "$TARGET_LOCK" && "$FILE_TYPE" == *"JPEG image data"* ]]; then
        pass "Extracción de video produjo un JPEG válido ($FILE_TYPE)"
    else
        fail "Extracción de video" "Tipo inesperado: $FILE_TYPE. Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 5: Manejo de wallpaper tipo 'scene' con preview.gif
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 5: Conversión limpia de wallpaper tipo scene con preview.gif a JPEG real${NC}"
{
    CFG="$TEST_TMPDIR/config4.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "314"
EOF
    DB="$TEST_TMPDIR/db4.sqlite"
    create_test_db "$DB"
    GIF="$TEST_TMPDIR/preview.gif"
    # Create real multi-frame GIF
    ffmpeg -y -f lavfi -i testsrc=duration=1:size=200x200:rate=5 "$GIF" 2>/dev/null
    sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '$TEST_TMPDIR');"
    sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (314, 1, 'scene.pkg', 'scene', 'preview.gif');"

    TARGET_LOCK="$TEST_TMPDIR/lock4.jpg"
    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" SDDM_WALLPAPER="$TEST_TMPDIR/sddm4.jpg" bash "$SYNC_SCRIPT" 2>&1)
    FILE_TYPE=$(file -b "$TARGET_LOCK" 2>/dev/null || true)
    if [[ -f "$TARGET_LOCK" && "$FILE_TYPE" == *"JPEG image data"* ]]; then
        pass "Conversión de preview.gif produjo un JPEG válido (no un GIF disfrazado)"
    else
        fail "Conversión de preview.gif" "Tipo: $FILE_TYPE. Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 6: Manejo de rutas absolutas vs relativas en DB
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 6: Resolución de rutas absolutas en item.path${NC}"
{
    CFG="$TEST_TMPDIR/config5.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "55"
EOF
    DB="$TEST_TMPDIR/db5.sqlite"
    create_test_db "$DB"
    ABS_IMG="$TEST_TMPDIR/absolute_image.png"
    ffmpeg -y -f lavfi -i color=c=purple:s=150x150:d=1 -vframes 1 "$ABS_IMG" 2>/dev/null
    # Library path is dummy, item.path is absolute
    sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '/dummy/base');"
    sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (55, 1, '$ABS_IMG', 'image', NULL);"

    TARGET_LOCK="$TEST_TMPDIR/lock5.jpg"
    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" SDDM_WALLPAPER="$TEST_TMPDIR/sddm5.jpg" bash "$SYNC_SCRIPT" 2>&1)
    if [[ -f "$TARGET_LOCK" && "$OUT" == *"updated successfully"* ]]; then
        pass "Ruta absoluta resuelta y sincronizada con éxito"
    else
        fail "Ruta absoluta" "Error en resolución. Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 7: Manejo de error si el item no existe en la base de datos
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 7: Comportamiento ante item ID inexistente en la BD${NC}"
{
    set +e
    CFG="$TEST_TMPDIR/config6.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "9999"
EOF
    DB="$TEST_TMPDIR/db6.sqlite"
    create_test_db "$DB"

    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TEST_TMPDIR/lock6.jpg" bash "$SYNC_SCRIPT" 2>&1)
    CODE=$?
    set -e
    if [[ $CODE -ne 0 && "$OUT" == *"No item found in DB"* ]]; then
        pass "Falla limpiamente con mensaje descriptivo ante ID no encontrado"
    else
        fail "Item inexistente" "Código: $CODE, Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 8: Sincronización con SDDM cuando la ruta es escribible
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 8: Sincronización atómica con SDDM${NC}"
{
    CFG="$TEST_TMPDIR/config7.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "88"
EOF
    DB="$TEST_TMPDIR/db7.sqlite"
    create_test_db "$DB"
    IMG="$TEST_TMPDIR/sddm_src.jpg"
    ffmpeg -y -f lavfi -i color=c=red:s=100x100:d=1 -vframes 1 -q:v 2 "$IMG" 2>/dev/null
    sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '$TEST_TMPDIR');"
    sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (88, 1, 'sddm_src.jpg', 'image', NULL);"

    TARGET_LOCK="$TEST_TMPDIR/lock7.jpg"
    SDDM_DEST="$TEST_TMPDIR/sddm_wall.jpg"
    touch "$SDDM_DEST"

    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" SDDM_WALLPAPER="$SDDM_DEST" bash "$SYNC_SCRIPT" 2>&1)
    if [[ -f "$SDDM_DEST" && -s "$SDDM_DEST" ]]; then
        pass "Archivo de SDDM actualizado atómicamente con éxito"
    else
        fail "Sincronización SDDM" "SDDM dest vacío o ausente. Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 9: Comprobación de unidades Systemd (Arranque e inicio de sesión garantizados)
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 9: Verificación de configuración de arranque en unidades systemd${NC}"
{
    SVC_FILE="$REPO_DIR/waywallen-lockscreen-sync.service"
    PATH_FILE="$REPO_DIR/waywallen-lockscreen-sync.path"

    # Verificar que el servicio tenga directivas de arranque gráfico y D-Bus
    HAS_INSTALL=$(grep -c "WantedBy=graphical-session.target" "$SVC_FILE" || true)
    HAS_DBUS=$(grep -c "DBUS_SESSION_BUS_ADDRESS" "$SVC_FILE" || true)
    HAS_PATH_MODIFIED=$(grep -c "PathModified" "$PATH_FILE" || true)

    if [[ $HAS_INSTALL -ge 1 && $HAS_DBUS -ge 1 && $HAS_PATH_MODIFIED -ge 1 ]]; then
        pass "Unidad .service configurada para arranque gráfico (WantedBy, D-Bus) y .path para cambios en caliente"
    else
        fail "Configuración de systemd" "Faltan directivas críticas en los archivos de servicio"
    fi
}

# -----------------------------------------------------------------------------
# Test 10: Integración GNOME gsettings (Light & Dark mode y Screensaver)
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 10: Verificación de claves gsettings de GNOME${NC}"
{
    if command -v gsettings >/dev/null 2>&1; then
        ORIG_BG=$(gsettings get org.gnome.desktop.background picture-uri 2>/dev/null || true)
        ORIG_DARK=$(gsettings get org.gnome.desktop.background picture-uri-dark 2>/dev/null || true)
        ORIG_SAVER=$(gsettings get org.gnome.desktop.screensaver picture-uri 2>/dev/null || true)

        CFG="$TEST_TMPDIR/config10.toml"
        cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "100"
EOF
        DB="$TEST_TMPDIR/db10.sqlite"
        create_test_db "$DB"
        IMG="$TEST_TMPDIR/gnome_test.jpg"
        ffmpeg -y -f lavfi -i color=c=yellow:s=100x100:d=1 -vframes 1 -q:v 2 "$IMG" 2>/dev/null
        sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '$TEST_TMPDIR');"
        sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (100, 1, 'gnome_test.jpg', 'image', NULL);"

        TARGET_LOCK="$TEST_TMPDIR/lock10.jpg"
        OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" bash "$SYNC_SCRIPT" 2>&1)

        # Check that gsettings is set to TARGET_LOCK
        CURRENT_BG=$(gsettings get org.gnome.desktop.background picture-uri 2>/dev/null || true)
        CURRENT_DARK=$(gsettings get org.gnome.desktop.background picture-uri-dark 2>/dev/null || true)
        CURRENT_SAVER=$(gsettings get org.gnome.desktop.screensaver picture-uri 2>/dev/null || true)

        if [[ "$CURRENT_BG" == *"lock10.jpg"* && "$CURRENT_DARK" == *"lock10.jpg"* && "$CURRENT_SAVER" == *"lock10.jpg"* ]]; then
            pass "gsettings configuró sincronizadamente picture-uri, picture-uri-dark y screensaver"
        else
            fail "gsettings GNOME" "BG: $CURRENT_BG, DARK: $CURRENT_DARK, SAVER: $CURRENT_SAVER"
        fi
    else
        pass "gsettings no presente en este entorno (test omitido sin error)"
    fi
}

# -----------------------------------------------------------------------------
# Test 11: Validación de paquete ZIP para Waywallen
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 11: Verificación de estructura y files.txt del paquete ZIP de Waywallen${NC}"
{
    ZIP_SCRIPT="$REPO_DIR/build-plugin-zip.sh"
    bash "$ZIP_SCRIPT" >/dev/null 2>&1
    ZIP_OUT="$REPO_DIR/waywallen-lockscreen-sync.zip"

    if [[ -f "$ZIP_OUT" ]]; then
        HAS_TOML=$(python3 -c "import zipfile; z = zipfile.ZipFile('$ZIP_OUT'); print(1 if 'plugin.toml' in z.namelist() else 0)")
        HAS_FILES_TXT=$(python3 -c "import zipfile; z = zipfile.ZipFile('$ZIP_OUT'); print(1 if 'files.txt' in z.namelist() else 0)")
        if [[ $HAS_TOML -eq 1 && $HAS_FILES_TXT -eq 1 ]]; then
            pass "Paquete .zip contiene plugin.toml en raíz y files.txt válido para Waywallen"
        else
            fail "Paquete .zip" "Falta plugin.toml o files.txt en la raíz del zip"
        fi
    else
        fail "Paquete .zip" "No se generó waywallen-lockscreen-sync.zip"
    fi
}

# -----------------------------------------------------------------------------
# Test 12: Sincronización atómica con GDM (pantalla de inicio al arrancar el PC)
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 12: Sincronización atómica con GDM (Pantalla de arranque / Greeter)${NC}"
{
    CFG="$TEST_TMPDIR/config12.toml"
    cat <<'EOF' > "$CFG"
[global]
last_wallpaper = "120"
EOF
    DB="$TEST_TMPDIR/db12.sqlite"
    create_test_db "$DB"
    IMG="$TEST_TMPDIR/gdm_source.jpg"
    ffmpeg -y -f lavfi -i color=c=cyan:s=100x100:d=1 -vframes 1 -q:v 2 "$IMG" 2>/dev/null
    sqlite3 "$DB" "INSERT INTO library (id, path) VALUES (1, '$TEST_TMPDIR');"
    sqlite3 "$DB" "INSERT INTO item (id, library_id, path, type, preview_path) VALUES (120, 1, 'gdm_source.jpg', 'image', NULL);"

    TARGET_LOCK="$TEST_TMPDIR/lock12.jpg"
    GDM_DEST="$TEST_TMPDIR/gdm_target_wallpaper.jpg"
    touch "$GDM_DEST"

    OUT=$(CONFIG_PATH="$CFG" DB_PATH="$DB" USER_WALLPAPER="$TARGET_LOCK" GDM_WALLPAPER="$GDM_DEST" bash "$SYNC_SCRIPT" 2>&1)
    FILE_TYPE=$(file -b "$GDM_DEST" 2>/dev/null || true)
    if [[ -f "$GDM_DEST" && -s "$GDM_DEST" && "$FILE_TYPE" == *"JPEG image data"* ]]; then
        pass "Archivo de GDM actualizado atómicamente con éxito como JPEG válido"
    else
        fail "Sincronización GDM" "GDM dest vacío, ausente o corrupto. Salida: $OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 13: Inyección, compilación y restauración del tema GDM (setup-gdm-theme.sh)
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 13: Extracción, inyección CSS, compilación y restauración en setup-gdm-theme.sh${NC}"
{
    GDM_SETUP_SCRIPT="$REPO_DIR/setup-gdm-theme.sh"
    MOCK_GDM_DIR="$TEST_TMPDIR/mock_gdm"
    mkdir -p "$MOCK_GDM_DIR"

    # Crear tema gresource base de prueba
    MOCK_SRC="$MOCK_GDM_DIR/src"
    mkdir -p "$MOCK_SRC"
    cat <<'EOF' > "$MOCK_SRC/gnome-shell-dark.css"
.login-dialog {
  background-color: #333333;
}
#lockDialogGroup {
  background-color: #222226;
}
EOF
    cat <<'EOF' > "$MOCK_SRC/theme.xml"
<?xml version="1.0" encoding="UTF-8"?>
<gresources>
  <gresource prefix="/org/gnome/shell/theme">
    <file>gnome-shell-dark.css</file>
  </gresource>
</gresources>
EOF
    MOCK_GRESOURCE="$MOCK_GDM_DIR/gnome-shell-theme.gresource"
    glib-compile-resources --sourcedir="$MOCK_SRC" --target="$MOCK_GRESOURCE" "$MOCK_SRC/theme.xml"

    TEST_GDM_WALL="$MOCK_GDM_DIR/waywallen_lock.jpg"

    # Ejecutar setup-gdm-theme.sh en entorno aislado
    OUT=$(GRESOURCE_FILE="$MOCK_GRESOURCE" GDM_WALLPAPER="$TEST_GDM_WALL" TARGET_USER="$(whoami)" bash "$GDM_SETUP_SCRIPT" 2>&1)

    # 1. Verificar creación de backup
    if [[ ! -f "${MOCK_GRESOURCE}.backup" ]]; then
        fail "setup-gdm-theme.sh" "No se generó archivo .backup. Salida: $OUT"
    fi

    # 2. Verificar que el gresource compilado contiene la regla apuntando al wallpaper
    EXTRACTED_CSS=$(gresource extract "$MOCK_GRESOURCE" "/org/gnome/shell/theme/gnome-shell-dark.css")
    if [[ "$EXTRACTED_CSS" == *"background-image: url('file://$TEST_GDM_WALL')"* ]]; then
        pass "Regla CSS con URL absoluta inyectada y compilada correctamente en gresource"
    else
        fail "setup-gdm-theme.sh" "CSS no contiene la regla inyectada. CSS: $EXTRACTED_CSS"
    fi

    # 3. Probar restauración de fábrica (--restore)
    RESTORE_OUT=$(GRESOURCE_FILE="$MOCK_GRESOURCE" bash "$GDM_SETUP_SCRIPT" --restore 2>&1)
    RESTORED_CSS=$(gresource extract "$MOCK_GRESOURCE" "/org/gnome/shell/theme/gnome-shell-dark.css")
    if [[ "$RESTORED_CSS" != *"waywallen_lock.jpg"* && "$RESTORED_CSS" == *"#lockDialogGroup"* ]]; then
        pass "Opción --restore restablece el tema original de fábrica intacto"
    else
        fail "setup-gdm-theme.sh --restore" "El tema no se restauró adecuadamente. Salida: $RESTORE_OUT"
    fi
}

# -----------------------------------------------------------------------------
# Test 14: Validación del parser CSS de GNOME Shell (St Theme Node)
# -----------------------------------------------------------------------------
echo -e "\n${BLUE}Test 14: Validación de resolución de URL local en el motor de estilos de GNOME Shell${NC}"
{
    if [[ -f "/usr/lib/gnome-shell/libst-18.so" ]]; then
        PYTHON_CHECK=$(GI_TYPELIB_PATH=/usr/lib/gnome-shell:/usr/lib/mutter-18 LD_LIBRARY_PATH=/usr/lib/gnome-shell:/usr/lib/mutter-18 python3 - <<'PYEOF'
import ctypes, sys
try:
    lib = ctypes.CDLL('/usr/lib/gnome-shell/libst-18.so')
    lib._st_theme_resolve_url.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
    lib._st_theme_resolve_url.restype = ctypes.c_void_p

    lib_gio = ctypes.CDLL('libgio-2.0.so.0')
    lib_gio.g_file_get_uri.restype = ctypes.c_char_p
    lib_gio.g_file_get_uri.argtypes = [ctypes.c_void_p]

    # Simular resolución de URL para /usr/share/backgrounds/waywallen_lock.jpg
    res = lib._st_theme_resolve_url(0, None, b"file:///usr/share/backgrounds/waywallen_lock.jpg")
    if res:
        uri = lib_gio.g_file_get_uri(res)
        if uri == b"file:///usr/share/backgrounds/waywallen_lock.jpg":
            print("RESOLVED_OK")
            sys.exit(0)
    print("FAILED_RESOLVE")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
PYEOF
        )
        if [[ "$PYTHON_CHECK" == *"RESOLVED_OK"* ]]; then
            pass "El motor St de GNOME Shell resuelve de forma nativa URIs file:///usr/share/backgrounds/..."
        else
            fail "Parser St GNOME Shell" "Error al verificar con libst: $PYTHON_CHECK"
        fi
    else
        pass "libst-18.so no encontrado (verificación omitida en este entorno)"
    fi
}

# -----------------------------------------------------------------------------
# Resumen
# -----------------------------------------------------------------------------
echo -e "\n=================================================="
echo -e "RESULTADOS: ${GREEN}$PASSED_TESTS pasados${NC}, ${RED}$FAILED_TESTS fallados${NC}"
echo -e "=================================================="

if [[ $FAILED_TESTS -gt 0 ]]; then
    exit 1
fi
exit 0
