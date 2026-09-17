#!/usr/bin/env bash
set -e

# Configurable paths with environment overrides for flexibility and unit testing
GDM_WALLPAPER="${GDM_WALLPAPER:-/usr/share/backgrounds/waywallen_lock.jpg}"
SDDM_WALLPAPER="${SDDM_WALLPAPER:-/usr/share/sddm/waywallen_lock.jpg}"
USER_WALLPAPER="${USER_WALLPAPER:-$HOME/.local/share/waywallen/current_lock.jpg}"
DB_PATH="${DB_PATH:-$HOME/.local/share/waywallen/waywallen-v2.db}"
CONFIG_PATH="${CONFIG_PATH:-$HOME/.config/waywallen/config.toml}"

# Ensure DBus session bus address is available (crucial for systemd --user services at boot)
if [[ -z "$DBUS_SESSION_BUS_ADDRESS" ]]; then
    USER_ID=$(id -u)
    if [[ -S "/run/user/$USER_ID/bus" ]]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus"
    fi
fi

# Extract current wallpaper ID from config.toml
if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "Config not found: $CONFIG_PATH"
    exit 1
fi

# 1. First attempt: global last_wallpaper
WALLPAPER_ID=$(awk -F '=' '/^\[global\]/,/^\[/ { if ($1 ~ /^\s*last_wallpaper\s*$/) { gsub(/["[:space:]]/, "", $2); print $2 } }' "$CONFIG_PATH" | head -n 1)

# 2. Fallback: look for display-specific wallpaper that is not empty, not 0, not none
if [[ -z "$WALLPAPER_ID" || "$WALLPAPER_ID" == "0" || "$WALLPAPER_ID" == "none" ]]; then
    WALLPAPER_ID=$(awk -F '=' '/^\s*last_wallpaper\s*=/ { gsub(/["[:space:]]/, "", $2); if ($2 != "" && $2 != "0" && $2 != "none") { print $2 } }' "$CONFIG_PATH" | head -n 1)
fi

if [[ -z "$WALLPAPER_ID" ]]; then
    echo "Could not determine current wallpaper ID"
    exit 1
fi

# Query database for item info
if [[ ! -f "$DB_PATH" ]]; then
    echo "Database not found: $DB_PATH"
    exit 1
fi

QUERY="SELECT item.type, library.path, item.path, item.preview_path FROM item JOIN library ON item.library_id = library.id WHERE item.id = $WALLPAPER_ID;"
RESULT=$(sqlite3 -noheader -list -separator '|' "$DB_PATH" "$QUERY" 2>/dev/null || true)

if [[ -z "$RESULT" ]]; then
    echo "No item found in DB for ID $WALLPAPER_ID"
    exit 1
fi

IFS='|' read -r TYPE LIB_PATH ITEM_PATH PREVIEW_PATH <<< "$RESULT"

# Function to resolve full path
resolve_path() {
    local base="$1"
    local rel="$2"
    if [[ "$rel" = /* ]]; then
        echo "$rel"
    else
        echo "$base/$rel"
    fi
}

USER_DIR="$(dirname "$USER_WALLPAPER")"
mkdir -p "$USER_DIR"
TARGET_TEMP="${USER_DIR}/.extract_tmp_$$.jpg"
SOURCE_IMG=""

# Clean up temp file on exit
trap 'rm -f "$TARGET_TEMP" 2>/dev/null || true' EXIT

# Determine source file
if [[ "$TYPE" == "video" ]]; then
    FULL_VIDEO=$(resolve_path "$LIB_PATH" "$ITEM_PATH")
    if [[ -f "$FULL_VIDEO" ]]; then
        # Extract high quality frame from video (1 second in, fallback to beginning)
        ffmpeg -y -ss 00:00:01 -i "$FULL_VIDEO" -vframes 1 -q:v 2 "$TARGET_TEMP" 2>/dev/null || \
        ffmpeg -y -i "$FULL_VIDEO" -vframes 1 -q:v 2 "$TARGET_TEMP" 2>/dev/null || true
        if [[ -s "$TARGET_TEMP" ]]; then
            SOURCE_IMG="$TARGET_TEMP"
        fi
    fi
fi

# If not video or video extraction failed, check preview path
if [[ -z "$SOURCE_IMG" ]]; then
    if [[ -n "$PREVIEW_PATH" && "$PREVIEW_PATH" != "NULL" ]]; then
        PREV_FULL=$(resolve_path "$LIB_PATH" "$PREVIEW_PATH")
        if [[ -f "$PREV_FULL" ]]; then
            SOURCE_IMG="$PREV_FULL"
        fi
    fi
fi

# Fallback to item path directly (e.g. static image)
if [[ -z "$SOURCE_IMG" ]]; then
    ITEM_FULL=$(resolve_path "$LIB_PATH" "$ITEM_PATH")
    if [[ -f "$ITEM_FULL" ]]; then
        SOURCE_IMG="$ITEM_FULL"
    fi
fi

if [[ -z "$SOURCE_IMG" || ! -f "$SOURCE_IMG" ]]; then
    echo "Could not find image source for wallpaper"
    exit 1
fi

# Convert to standard high-quality JPEG if not already from TARGET_TEMP
if [[ "$SOURCE_IMG" != "$TARGET_TEMP" ]]; then
    # Use ffmpeg to convert GIF/PNG/WebP/etc. to clean full JPEG
    ffmpeg -y -i "$SOURCE_IMG" -vframes 1 -q:v 2 "$TARGET_TEMP" 2>/dev/null || true
    if [[ ! -s "$TARGET_TEMP" ]]; then
        # Fallback copy if ffmpeg fails
        cp -f "$SOURCE_IMG" "$TARGET_TEMP"
    fi
fi

# Atomically replace USER_WALLPAPER
mv -f "$TARGET_TEMP" "$USER_WALLPAPER"
chmod 644 "$USER_WALLPAPER" 2>/dev/null || true

# If GDM file is writable, copy there (Login Screen / Greeter at PC boot)
if [[ -w "$GDM_WALLPAPER" ]]; then
    cp -f "$USER_WALLPAPER" "$GDM_WALLPAPER" 2>/dev/null || cat "$USER_WALLPAPER" > "$GDM_WALLPAPER" 2>/dev/null || true
    chmod 644 "$GDM_WALLPAPER" 2>/dev/null || true
elif [[ -w "$(dirname "$GDM_WALLPAPER")" ]]; then
    GDM_TEMP="$(dirname "$GDM_WALLPAPER")/.gdm_tmp_$$.jpg"
    cp -f "$USER_WALLPAPER" "$GDM_TEMP" 2>/dev/null || true
    if [[ -f "$GDM_TEMP" ]]; then
        mv -f "$GDM_TEMP" "$GDM_WALLPAPER" 2>/dev/null || true
        chmod 644 "$GDM_WALLPAPER" 2>/dev/null || true
    fi
fi

# If SDDM file is writable, copy there
if [[ -w "$SDDM_WALLPAPER" ]]; then
    cp -f "$USER_WALLPAPER" "$SDDM_WALLPAPER" 2>/dev/null || cat "$USER_WALLPAPER" > "$SDDM_WALLPAPER" 2>/dev/null || true
    chmod 644 "$SDDM_WALLPAPER" 2>/dev/null || true
elif [[ -w "$(dirname "$SDDM_WALLPAPER")" ]]; then
    SDDM_TEMP="$(dirname "$SDDM_WALLPAPER")/.sddm_tmp_$$.jpg"
    cp -f "$USER_WALLPAPER" "$SDDM_TEMP" 2>/dev/null || true
    if [[ -f "$SDDM_TEMP" ]]; then
        mv -f "$SDDM_TEMP" "$SDDM_WALLPAPER" 2>/dev/null || true
        chmod 644 "$SDDM_WALLPAPER" 2>/dev/null || true
    fi
fi

# Update GNOME background and screensaver
if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.background picture-uri "file://$USER_WALLPAPER" 2>/dev/null || true
    gsettings set org.gnome.desktop.background picture-uri-dark "file://$USER_WALLPAPER" 2>/dev/null || true
    gsettings set org.gnome.desktop.screensaver picture-uri "file://$USER_WALLPAPER" 2>/dev/null || true
fi

# Update KDE Lockscreen if available
if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file kscreenlockerrc --group Greeter --key WallpaperPlugin org.kde.image 2>/dev/null || true
    kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General --key Image "$USER_WALLPAPER" 2>/dev/null || true
    kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General --key PreviewImage "$USER_WALLPAPER" 2>/dev/null || true
fi

echo "Lock screen and desktop wallpaper updated successfully to: $USER_WALLPAPER"
