# Waywallen Lockscreen & Login Sync 🎨🔒

[![Linux](https://img.shields.io/badge/Platform-Linux%20%7C%20Wayland-blue.svg)](https://wayland.freedesktop.org/)
[![GNOME](https://img.shields.io/badge/Desktop-GNOME%20Shell%20(GDM)-brightgreen.svg)](https://www.gnome.org/)
[![KDE / SDDM](https://img.shields.io/badge/KDE%20%2F%20SDDM-In%20Review-yellow.svg)](#-scope--compatibility)
[![CPU Usage](https://img.shields.io/badge/CPU%20Idle-0.00%25-success.svg)](#-how-it-works)
[![Tests](https://img.shields.io/badge/Tests-19%2F19%20Passing-brightgreen.svg)](tests/run_tests.sh)

Automatic, reactive, and high-fidelity synchronizer that brings your active [Waywallen](https://github.com/waywallen) wallpaper directly to your **lock screen (`Super+L`)** and your **system boot/reboot greeter (GDM & SDDM)** on Linux.

---

## ⚡ Quick Installation (Copy-Paste)

### Step 1: Install dependencies for your distribution

<details open>
<summary><b>Select your Linux distribution:</b></summary>

* **Arch Linux / CachyOS / Manjaro:**
  ```bash
  sudo pacman -S python-pillow ffmpeg sqlite glib2
  ```

* **Ubuntu / Debian / Linux Mint:**
  ```bash
  sudo apt update && sudo apt install -y python3-pil ffmpeg sqlite3 libglib2.0-dev-bin
  ```

* **Fedora / RHEL:**
  ```bash
  sudo dnf install -y python3-pillow ffmpeg sqlite glib2-devel
  ```
</details>

---

### Step 2: Clone and install in a single command

Copy and paste this command into your terminal:

```bash
git clone https://github.com/Rilorca/waywallen-lockscreen-sync.git && cd waywallen-lockscreen-sync && ./install.sh
```

> **What does this installer do?**
> 1. Installs user scripts into `~/.local/bin/`.
> 2. Hooks native GPU frame capture into the Waywallen renderer.
> 3. Enables `systemd --user` units for reactive real-time synchronization (0% CPU at idle).
> 4. Runs an initial synchronization of your current active wallpaper.

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

That's it! Every time you pick or change a wallpaper in Waywallen, both your lock screen (`Super+L`) and your startup login screen will update instantly at full resolution.

---

## 🎯 Scope & Compatibility

| Desktop / Display Manager | Status | Support Details |
| :--- | :---: | :--- |
| **GNOME Shell (Lock screen `Super+L`)** | 🟢 **Verified** | Instant sync without session restarts or desktop flicker. |
| **GNOME Display Manager (GDM)** | 🟢 **Verified** | Persistent background from system power-on / reboot (password screen). |
| **Multi-Monitor (Mixed resolutions)** | 🟢 **Verified** | Clean 1:1 duplication per monitor (e.g. 2K + 1080p) via `monitors.xml`. |
| **Wallpaper Engine Complex Scenes** | 🟢 **Verified** | Direct GPU frame capture (`Gsk.Renderer`) and native texture extraction (JPEG/PNG/DDS). |
| **KDE Plasma (Lock screen)** | 🟡 **In Review** | Updates `kscreenlockerrc`. *Available for testing.* |
| **SDDM (Login Manager)** | 🟡 **In Review** | Helper script `setup-sddm-theme.sh` available. *Active testing.* |

> [!NOTE]
> **KDE / SDDM Note:**
> Configuration logic for `kscreenlockerrc` and SDDM themes is implemented and included. However, primary development and validation were conducted on **GNOME Shell (Wayland) with GDM**. Features for KDE Plasma and SDDM are functional but categorized as in review.

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
   systemctl --user disable --now waywallen-lockscreen-sync.path waywallen-lockscreen-sync.service
   ```
3. *(Optional)* Restore original Waywallen `renderer.js`:
   ```bash
   python3 patch-renderer.py --restore
   ```

---

## 🔍 Diagnostics & Status

Check service health in real-time:
```bash
systemctl --user status waywallen-lockscreen-sync.path
```

Inspect the generated wallpapers:
```bash
# User lock screen image
identify ~/.local/share/waywallen/current_lock.jpg

# GDM multi-monitor boot wallpaper
identify /usr/share/backgrounds/waywallen_lock.jpg
```

---

## 🧪 Unit Test Suite

The repository includes a comprehensive 19-test automated suite using sandboxed mocks covering failure handling, TOML/XML parsing, PKG texture decoding, modern image formats, and multi-monitor layouts:

```bash
./tests/run_tests.sh
```

---

## 📦 Project Layout

```text
waywallen-lockscreen-sync/
├── install.sh                  # Interactive installer and dependency verifier
├── sync-waywallen-lockscreen.sh # Main synchronization orchestrator
├── waywallen_extractor.py      # Texture extraction engine & multi-monitor compositor
├── patch-renderer.py           # Dynamic GPU frame capture hook for Waywallen
├── setup-gdm-theme.sh          # GDM theme compiler and CSS injector
├── setup-sddm-theme.sh         # SDDM theme configuration helper
├── waywallen-lockscreen-sync.path    # systemd inotify watcher
├── waywallen-lockscreen-sync.service # Atomic systemd oneshot sync unit
├── build-plugin-zip.sh         # Packager for Waywallen's plugin manager
└── tests/
    └── run_tests.sh            # Automated test suite (19/19 tests)
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
