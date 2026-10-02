# Wall2Lock 🎨🔒

[![Linux](https://img.shields.io/badge/Platform-Linux%20%7C%20Wayland-blue.svg)](https://wayland.freedesktop.org/)
[![GNOME](https://img.shields.io/badge/Desktop-GNOME%20Shell%20(GDM)-brightgreen.svg)](https://www.gnome.org/)
[![KDE / SDDM](https://img.shields.io/badge/KDE%20%2F%20SDDM-Verified-brightgreen.svg)](#-scope--compatibility)
[![CPU Usage](https://img.shields.io/badge/CPU%20Idle-0.00%25-success.svg)](#-how-it-works)
[![Tests](https://img.shields.io/badge/Tests-22%2F22%20Passing-brightgreen.svg)](tests/run_tests.sh)

**Wall2Lock** is an automatic, reactive, and high-fidelity synchronizer that brings your active desktop wallpaper (from **[Waywallen](https://github.com/waywallen)** or **[skwd-wall](https://github.com/liixini/skwd-wall)**) directly to your **lock screen (`Super+L`)** and your **system boot/reboot greeter (GDM & SDDM)** on Linux.

---

## ⚡ Quick Installation (Copy-Paste)

### Step 1: Install dependencies for your distribution

<details open>
<summary><b>Select your Linux distribution:</b></summary>

* **Arch Linux / CachyOS / Manjaro:**
  ```bash
  sudo pacman -S python-pillow ffmpeg sqlite glib2 libadwaita
  ```

* **Ubuntu / Debian / Linux Mint:**
  ```bash
  sudo apt update && sudo apt install -y python3-pil ffmpeg sqlite3 libglib2.0-dev-bin gir1.2-adw-1
  ```

* **Fedora / RHEL:**
  ```bash
  sudo dnf install -y python3-pillow ffmpeg sqlite glib2-devel libadwaita
  ```
</details>

---

### Step 2: Clone and install in a single command

Copy and paste this command into your terminal:

```bash
git clone https://github.com/Rilorca/waywallen-lockscreen-sync.git wall2lock && cd wall2lock && ./install.sh
```

> **What does this installer do?**
> 1. Installs `wall2lock-sync`, `wall2lock_extractor.py`, and `wall2lock-gui` into `~/.local/bin/`.
> 2. Sets up backward-compatible symlinks (`sync-waywallen-lockscreen.sh`, etc.).
> 3. Hooks native GPU frame capture into the Waywallen renderer (GNOME).
> 4. Enables `wall2lock.path` and `wall2lock.service` user units for 0% CPU reactive sync.
> 5. Installs the desktop launcher for the control center (`wall2lock-gui.desktop`).
> 6. Runs an initial synchronization of your current active wallpaper.

---

### Step 3: Configure the Login Manager (Required for GDM / SDDM)

To display the synced wallpaper immediately upon **powering on or restarting your PC** (the core goal of this project):

* **If you use GNOME (GDM):**
  ```bash
  sudo ./setup-gdm-theme.sh
  ```
  *(Automatically creates a safety backup of your original system theme and compiles the CSS rules into `gnome-shell-theme.gresource` with write permissions for your user).*

* **If you use KDE Plasma (SDDM):**
  ```bash
  sudo ./setup-sddm-theme.sh
  ```

> [!TIP]
> When running `./install.sh` interactively in a terminal, it will automatically prompt you to run this step with `sudo` right away.

---

## 🖥️ Minimalist Control Center (Libadwaita GUI)

**Wall2Lock** includes a simple, native Libadwaita / GTK4 control panel with system tray support:

Launch it from your application launcher as **"Wall2Lock"** or via terminal:
```bash
wall2lock-gui
```

### What does it offer?
* **Toggle 1: Sincronización activa**: Enable or pause the real-time wallpaper watcher without disabling boot setup (`systemctl --user start/stop wall2lock.path`).
* **Toggle 2: Iniciar con el sistema**: Enable or disable automated startup on boot/login (`systemctl --user enable/disable wall2lock.path wall2lock.service`).
* **Toggle 3: Icono en la bandeja del sistema**: Show or hide the quick tray icon in KDE Plasma / GNOME app indicator bar, with minimize-to-tray on window close.
* **Sync Now Button (`↻`)**: Instantly re-synchronize the current active wallpaper with a single click.

---

## 🎯 Scope & Compatibility

| Desktop / Display Manager | Status | Support Details |
| :--- | :---: | :--- |
| **GNOME Shell (Lock screen `Super+L`)** | 🟢 **Verified** | Instant sync without session restarts or desktop flicker. |
| **GNOME Display Manager (GDM)** | 🟢 **Verified** | Persistent background from system power-on / reboot (password screen). |
| **Multi-Monitor (Mixed resolutions)** | 🟢 **Verified** | Clean 1:1 duplication per monitor (e.g. 2K + 1080p) via `monitors.xml` or Wayland outputs. |
| **Wallpaper Engine Complex Scenes** | 🟢 **Verified** | Direct GPU frame capture (`Gsk.Renderer`), decompression of TEXB0003/TEXB0004 LZ4 textures, and native textures (JPEG/PNG/DDS). |
| **KDE Plasma (Lock screen)** | 🟢 **Verified** | Preserves `org.skwd.wall.plasma` plugin for live animation, with static image fallback. |
| **SDDM (Login Manager)** | 🟢 **Verified** | Instant atomic sync from both Waywallen and skwd-wall. |

> [!NOTE]
> **Dual-Engine Architecture (Waywallen & skwd-wall):**
> Wall2Lock automatically detects whether you are using Waywallen or skwd-wall (`skwd-helm`, `skwd-walld`, `org.skwd.wall.plasma`). On KDE Plasma with SDDM, it extracts high-resolution textures directly from Wallpaper Engine scenes or video wallpapers and updates SDDM's background while keeping your live interactive Plasma lockscreen untouched.

---

## 💎 Key Features

* 🔋 **Zero Battery & CPU Overhead (0.00% CPU at Idle)**: Powered by kernel-level filesystem events (`inotify` via `systemd.path`). No long-running daemon polling or consuming background RAM.
* 🖼️ **Zero Pixelation (Ultra-High Resolution)**:
  * Intercepts the final hardware-rendered frame directly on the GPU (`Gsk.Renderer.render_texture`).
  * Unpacks native ultra-res textures (3897x2400+) from modern Wallpaper Engine `scene.pkg` archives (`TEXV0005`), eliminating low-res fallback thumbnails (160x160).
  * Stores GPU captures in persistent disk cache (`~/.local/share/waywallen/captures/`), surviving system reboots.
* 🖥️ **Smart Multi-Monitor Compositing**:
  * Reads physical topology and screen coordinates from `~/.config/monitors.xml`.
  * Builds a unified virtual canvas (e.g., **4480x1440**) where each screen receives a sharp, un-stretched 1:1 frame.
* 🎨 **Full Chroma 4:4:4 Quality (`subsampling=0`)**:
  * Saves images at maximum JPEG quality with chroma subsampling disabled, preserving crystal-clear character outlines, text, and high-contrast edges.
* 🛡️ **Safe & 100% Reversible**:
  * Preserves original system theme files with automatic backups and verifiable checksums.

---

## 🔄 Revert & Uninstallation

To restore factory settings at any time:

1. **Restore the original GDM theme:**
   ```bash
   sudo ./setup-gdm-theme.sh --restore
   ```
2. **Disable automated user units:**
   ```bash
   systemctl --user disable --now wall2lock.path wall2lock.service
   ```
3. *(Optional)* Restore original Waywallen `renderer.js`:
   ```bash
   python3 patch-renderer.py --restore
   ```

---

## 🔍 Diagnostics & Status

Check service health in real-time:
```bash
systemctl --user status wall2lock.path
```

Inspect the generated wallpapers:
```bash
# User lock screen image
identify ~/.local/share/waywallen/current_lock.jpg

# GDM multi-monitor boot wallpaper
identify /usr/share/backgrounds/waywallen_lock.jpg

# SDDM wallpaper
identify /usr/share/sddm/waywallen_lock.jpg
```

---

## 🧪 Unit Test Suite

The repository includes a comprehensive 22-test automated suite using sandboxed mocks covering failure handling, TOML/XML parsing, PKG texture decoding, modern image formats, multi-monitor layouts, and the Adwaita GUI:

```bash
./tests/run_tests.sh
```

---

## 📦 Project Layout

```text
wall2lock/
├── install.sh                  # Interactive installer and dependency verifier
├── sync-wall2lock.sh           # Main synchronization orchestrator
├── wall2lock_extractor.py      # Texture extraction engine & multi-monitor compositor
├── wall2lock_gui.py            # Minimalist Adwaita GUI & StatusNotifierItem tray manager
├── wall2lock-gui.desktop       # Desktop application entry
├── patch-renderer.py           # Dynamic GPU frame capture hook for Waywallen
├── setup-gdm-theme.sh          # GDM theme compiler and CSS injector
├── setup-sddm-theme.sh         # SDDM theme configuration helper
├── wall2lock.path              # systemd inotify watcher
├── wall2lock.service           # Atomic systemd oneshot sync unit
├── build-plugin-zip.sh         # Packager for Waywallen's plugin manager
└── tests/
    └── run_tests.sh            # Automated test suite (22/22 tests passing)
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
