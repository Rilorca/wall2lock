# Waywallen Lockscreen & Login Sync 🎨🔒

[![Linux](https://img.shields.io/badge/Platform-Linux%20%7C%20Wayland-blue.svg)](https://wayland.freedesktop.org/)
[![GNOME](https://img.shields.io/badge/Desktop-GNOME%20Shell%20(GDM)-brightgreen.svg)](https://www.gnome.org/)
[![KDE / SDDM](https://img.shields.io/badge/KDE%20%2F%20SDDM-En%20Revisión-yellow.svg)](#-alcance-y-compatibilidad)
[![CPU Usage](https://img.shields.io/badge/CPU%20Idle-0.00%25-success.svg)](#-cómo-funciona-internamente)
[![Tests](https://img.shields.io/badge/Tests-19%2F19%20Passing-brightgreen.svg)](tests/run_tests.sh)

Sincronizador automático, reactivo y de alta fidelidad para llevar el fondo de pantalla animado de [Waywallen](https://github.com/waywallen) a la **pantalla de bloqueo (`Super+L`)** y al **gestor de inicio de sesión / reinicio (GDM y SDDM)** en Linux.

---

## ⚡ Instalación Rápida (Copy-Paste)

### Paso 1: Instala las dependencias de tu distribución

<details open>
<summary><b>Selecciona tu distribución de Linux:</b></summary>

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

### Paso 2: Clona e instala en un solo comando

Copia y pega este comando en tu terminal:

```bash
git clone https://github.com/Rilorca/waywallen-lockscreen-sync.git && cd waywallen-lockscreen-sync && ./install.sh
```

> **¿Qué hace este instalador?**
> 1. Instala los scripts en `~/.local/bin/`.
> 2. Configura la captura nativa GPU en el renderer de Waywallen.
> 3. Habilita los servicios de usuario en `systemd` para sincronización en tiempo real (0% CPU en reposo).
> 4. Realiza la primera sincronización de tu fondo actual.

---

### Paso 3: Configurar el Login Manager (Requerido para GDM / SDDM)

Para que el fondo de Waywallen se aplique en la pantalla de inicio al **encender o reiniciar el PC** (el objetivo central de este proyecto):

* **Si usas GNOME (GDM):**
  ```bash
  sudo ./setup-gdm-theme.sh
  ```
  *(Crea automáticamente una copia de respaldo del tema original del sistema y compila las reglas CSS necesarias con permisos para tu usuario).*

* **Si usas KDE Plasma (SDDM):**
  ```bash
  sudo ./setup-sddm-theme.sh
  ```

> [!TIP]
> Si ejecutas `./install.sh` de forma interactiva en la terminal, el instalador te ofrecerá aplicar automáticamente este paso con `sudo` al finalizar.

¡Listo! A partir de este momento, cada vez que elijas o cambies un fondo en Waywallen, tu pantalla de bloqueo (`Super+L`) y tu pantalla de inicio de sesión se sincronizarán al instante con la máxima resolución.

---

## 🎯 Alcance y Compatibilidad

| Entorno / Gestor | Estado | Detalles de Soporte |
| :--- | :---: | :--- |
| **GNOME Shell (Bloqueo `Super+L`)** | 🟢 **Verificado** | Sincronización instantánea sin reiniciar sesión ni parpadeos. |
| **GNOME Display Manager (GDM)** | 🟢 **Verificado** | Fondo persistente desde el encendido/reinicio del PC (pantalla de contraseña). |
| **Multi-Monitor (Resoluciones mixtas)** | 🟢 **Verificado** | Duplicación limpia 1:1 por pantalla (ej. 2K + 1080p) vía `monitors.xml`. |
| **Escenas complejas Wallpaper Engine** | 🟢 **Verificado** | Captura directa por GPU (`Gsk.Renderer`) y decodificación de texturas nativas (JPEG/PNG/DDS). |
| **KDE Plasma (Lockscreen)** | 🟡 **En Revisión** | Actualiza `kscreenlockerrc`. *Disponible para pruebas.* |
| **SDDM (Login Manager)** | 🟡 **En Revisión** | Script `setup-sddm-theme.sh` disponible. *En fase de pruebas activas.* |

> [!NOTE]
> **Nota sobre KDE / SDDM:**
> La lógica de actualización para `kscreenlockerrc` y el script de configuración de tema para SDDM están implementados e incluidos en el instalador; sin embargo, el desarrollo y verificación principal se realizaron sobre **GNOME Shell (Wayland) con GDM**. Si utilizas KDE Plasma o SDDM, las funciones están disponibles pero catalogadas como en revisión.

---

## 💎 Características Principales

* 🔋 **Cero impacto en batería y procesador (0.00% CPU en reposo)**: Funciona mediante eventos del kernel (`inotify` vía `systemd.path`). No hay procesos en segundo plano consumiendo memoria ni ejecutando bucles constantes.
* 🖼️ **Cero Pixelado (Ultra Alta Resolución)**:
  * Intercepta el fotograma renderizado por hardware directamente en la GPU (`Gsk.Renderer.render_texture`).
  * Desempaqueta texturas nativas de alta resolución (3897x2400+) en archivos `scene.pkg` modernos (`TEXV0005`), impidiendo el uso de thumbnails diminutos (160x160).
  * Almacena las capturas en disco persistente (`~/.local/share/waywallen/captures/`), sobreviviendo a cualquier reinicio.
* 🖥️ **Composición Multi-Monitor Inteligente**:
  * Detecta las dimensiones y posiciones exactas de tus pantallas en `~/.config/monitors.xml`.
  * Genera un lienzo compuesto unificado (ej. **4480x1440**) donde cada monitor recibe su imagen nítida mapeada 1:1, evitando que GDM estire o corte la imagen entre monitores.
* 🎨 **Calidad Full Chroma 4:4:4 (`subsampling=0`)**:
  * Exporta los fondos a JPEG con `quality=100` y submuestreo cromático desactivado, garantizando bordes nítidos en textos, personajes y arte digital.
* 🛡️ **Seguro y 100% Reversible**:
  * Cualquier modificación al tema del sistema conserva una copia de seguridad original con fecha y hash intactos.

---

## 🔄 Restauración y Desinstalación

Si en cualquier momento deseas volver a la configuración de fábrica:

1. **Restaurar el tema original de GDM:**
   ```bash
   sudo ./setup-gdm-theme.sh --restore
   ```
2. **Desactivar los servicios automáticos:**
   ```bash
   systemctl --user disable --now waywallen-lockscreen-sync.path waywallen-lockscreen-sync.service
   ```
3. *(Opcional)* Restaurar el `renderer.js` de la extensión de Waywallen:
   ```bash
   python3 patch-renderer.py --restore
   ```

---

## 🔍 Comandos de Verificación y Diagnóstico

Para comprobar el estado del servicio en tiempo real:
```bash
systemctl --user status waywallen-lockscreen-sync.path
```

Para verificar las dimensiones del fondo generado para tus monitores:
```bash
# Fondo del Lockscreen de usuario
identify ~/.local/share/waywallen/current_lock.jpg

# Fondo multi-monitor de GDM (Inicio del PC)
identify /usr/share/backgrounds/waywallen_lock.jpg
```

---

## 🧪 Pruebas Unitarias

El proyecto incluye una suite completa de 19 pruebas automatizadas con entornos simulados (mocks) que validan el comportamiento ante fallos, parsing TOML/XML, decodificación de paquetes `.pkg`, compatibilidad con texturas modernas y composición multi-monitor:

```bash
./tests/run_tests.sh
```

---

## 📦 Estructura del Proyecto

```text
waywallen-lockscreen-sync/
├── install.sh                  # Instalador interactivo y verificador de dependencias
├── sync-waywallen-lockscreen.sh # Script orquestador principal de sincronización
├── waywallen_extractor.py      # Motor de extracción de texturas y compositor multi-monitor
├── patch-renderer.py           # Hook dinámico para captura GPU en Waywallen (GNOME Shell)
├── setup-gdm-theme.sh          # Inyector y compilador del tema para GDM
├── setup-sddm-theme.sh         # Configurador auxiliar para SDDM
├── waywallen-lockscreen-sync.path    # Unidad systemd (Watcher reactivo inotify)
├── waywallen-lockscreen-sync.service # Unidad systemd (Lanzador atómico de sincronización)
├── build-plugin-zip.sh         # Empaquetador para la interfaz de plugins de Waywallen
└── tests/
    └── run_tests.sh            # Suite de pruebas unitarias (19/19 tests)
```

---

## 📄 Licencia

Distribuido bajo la licencia MIT. Consulta `LICENSE` para más detalles.
