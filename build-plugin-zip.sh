#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_ZIP="$SCRIPT_DIR/wall2lock.zip"
TMP_STAGE="$(mktemp -d)"

trap 'rm -rf "$TMP_STAGE"' EXIT

echo "Construyendo paquete de plugin para Wall2Lock: $OUTPUT_ZIP"

# 1. Crear estructura interna
mkdir -p "$TMP_STAGE/bin"
mkdir -p "$TMP_STAGE/i18n"

# 2. Copiar scripts y servicios
cp -f "$SCRIPT_DIR/sync-wall2lock.sh" "$TMP_STAGE/bin/sync-wall2lock.sh"
chmod +x "$TMP_STAGE/bin/sync-wall2lock.sh"

cp -f "$SCRIPT_DIR/wall2lock_extractor.py" "$TMP_STAGE/bin/wall2lock_extractor.py"
chmod +x "$TMP_STAGE/bin/wall2lock_extractor.py"

cp -f "$SCRIPT_DIR/patch-renderer.py" "$TMP_STAGE/patch-renderer.py"
chmod +x "$TMP_STAGE/patch-renderer.py"

cp -f "$SCRIPT_DIR/install.sh" "$TMP_STAGE/install.sh"
chmod +x "$TMP_STAGE/install.sh"

cp -f "$SCRIPT_DIR/setup-gdm-theme.sh" "$TMP_STAGE/setup-gdm-theme.sh"
chmod +x "$TMP_STAGE/setup-gdm-theme.sh"

cp -f "$SCRIPT_DIR/setup-sddm-theme.sh" "$TMP_STAGE/setup-sddm-theme.sh"
chmod +x "$TMP_STAGE/setup-sddm-theme.sh"

cp -f "$SCRIPT_DIR/wall2lock.service" "$TMP_STAGE/wall2lock.service"
cp -f "$SCRIPT_DIR/wall2lock.path" "$TMP_STAGE/wall2lock.path"

# 3. Crear plugin.toml
cat <<'EOF' > "$TMP_STAGE/plugin.toml"
[plugin]
id = "org.waywallen.lockscreen-sync"
name = "Lockscreen & SDDM Sync"
version = "1.0.0"
entry = "main.lua"
entry_version = 4

[plugin.i18n]
directory = "i18n"
EOF

# 4. Crear main.lua
cat <<'EOF' > "$TMP_STAGE/main.lua"
local M = {}

function M.info()
    return {
        name = "lockscreen_sync",
        display_name = tr("Lockscreen & SDDM Sync"),
        status = {
            {
                id = "lockscreen_status",
                label = tr("Lockscreen Sync"),
                order = 10,
            },
        },
        actions = {
            {
                id = "sync_action",
                kind = "invoke",
                label = tr("Sync Lockscreen"),
                order = 20,
            },
        },
        capabilities = {},
    }
end

M.actions = {}
function M.actions.status(ctx)
    return {
        status = {
            lockscreen_status = "Active",
        },
        actions = {
            sync_action = { visible = true, enabled = true },
        },
    }
end

function M.actions.invoke(ctx, action_id, values)
    if ctx and ctx.log then
        ctx.log("lockscreen_sync: action " .. tostring(action_id))
    end
end

return M
EOF

# 5. Crear traducciones
cat <<'EOF' > "$TMP_STAGE/i18n/es.po"
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"

msgid "Lockscreen & SDDM Sync"
msgstr "Sincronizador de Lockscreen y SDDM"

msgid "Lockscreen Sync"
msgstr "Sincronización Lockscreen"

msgid "Sync Lockscreen Now"
msgstr "Sincronizar Lockscreen Ahora"
EOF

# 6. Generar files.txt estricto (requerido por Waywallen)
(
    cd "$TMP_STAGE"
    find . -type f ! -name "files.txt" | sed 's|^\./||' | sort > files.txt
    # Añadir files.txt a la lista de archivos si no estaba
    echo "files.txt" >> files.txt
    sort -u files.txt -o files.txt
)

# 7. Empaquetar con python3 (zipfile) asegurando que plugin.toml esté en la raíz
python3 - <<PYEOF
import os
import zipfile

stage_dir = "$TMP_STAGE"
zip_path = "$OUTPUT_ZIP"

with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(stage_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, stage_dir)
            zf.write(full_path, rel_path)

print(f"Paquete ZIP generado exitosamente en: {zip_path}")
PYEOF

cp -f "$OUTPUT_ZIP" "$SCRIPT_DIR/waywallen-lockscreen-sync.zip"

echo "Contenido de files.txt en el paquete:"
cat "$TMP_STAGE/files.txt"
