# Waywallen Lockscreen & Login Sync (GDM / SDDM)

Sincronizador automático y reactivo del fondo de pantalla activo en [Waywallen](https://github.com/waywallen) hacia la pantalla de bloqueo y el gestor de inicio de sesión del sistema (**GDM** y **SDDM**).

---

## 🎯 Alcance del Software y Compatibilidad

| Entorno / Componente | Estado | Soporte |
| :--- | :---: | :--- |
| **GNOME Shell (Lockscreen `Super+L`)** | 🟢 **Verificado** | Sincronización en tiempo real sin reiniciar sesión ni procesos. |
| **GNOME Display Manager (GDM)** | 🟢 **Verificado** | Fondo persistente desde el encendido del PC / reinicio (pantalla de login). |
| **Multi-Monitor (Resoluciones mixtas)** | 🟢 **Verificado** | Duplicación limpia por pantalla (ej. 2K + 1080p) vía `monitors.xml`. |
| **Escenas complejas Wallpaper Engine** | 🟢 **Verificado** | Captura directa por GPU (`Gsk.Renderer`), sin capas faltantes ni partes flotantes. |
| **KDE Plasma (Lockscreen)** | 🟡 **En Revisión** | Configura `kscreenlockerrc`. *Pendiente de validación exhaustiva en Plasma 6.* |
| **SDDM (Simple Desktop Display Manager)**| 🟡 **En Revisión** | Script `setup-sddm-theme.sh` disponible. *En fase de pruebas activas.* |

> [!NOTE]
> **Compatibilidad KDE / SDDM (En Revisión):**
> La lógica de actualización para `kscreenlockerrc` y el script de configuración de tema para SDDM están implementados e incluidos en el instalador; sin embargo, el desarrollo y verificación principal se realizaron sobre **GNOME Shell (Wayland) con GDM**. Si utilizas KDE Plasma o SDDM, las funciones están disponibles pero catalogadas como experimentales / en revisión.

---

## 🚀 Instalación y Configuración

### 1. Prerrequisitos

En sistemas basados en Arch Linux / CachyOS / Manjaro:
```bash
sudo pacman -S python python-pillow ffmpeg glib2
```
*(En Fedora / Ubuntu, asegúrate de tener `python3-pillow`, `ffmpeg` y las utilidades `glib2` / `glib-compile-resources`).*

### 2. Instalación de usuario (Recomendado)

Ejecuta el script de instalación automática:
```bash
git clone https://github.com/tu-usuario/waywallen-lockscreen-sync.git
cd waywallen-lockscreen-sync
./install.sh
```

El script se encarga de:
1. Copiar `sync-waywallen-lockscreen.sh` y `waywallen_extractor.py` a `~/.local/bin/`.
2. Parchear el renderer de Waywallen en GNOME (`renderer.js`) para habilitar la captura nativa GPU en tiempo real.
3. Habilitar el watcher reactivo de `systemd --user` (`waywallen-lockscreen-sync.path`).
4. Realizar la sincronización inicial del fondo actual.

### 3. Configurar la pantalla de inicio al encender el PC

Para que el fondo aparezca inmediatamente al prender el PC (antes de iniciar sesión):

* **Si usas GNOME (GDM):**
  ```bash
  sudo ./setup-gdm-theme.sh
  ```
  *(Crea un respaldo de seguridad del tema original y compila el `gresource` de GDM para cargar `/usr/share/backgrounds/waywallen_lock.jpg` con permisos de usuario).*

* **Si usas KDE Plasma (SDDM):**
  ```bash
  sudo ./setup-sddm-theme.sh
  ```

---

### Restauración del tema original de fábrica

Si en algún momento deseas revertir GDM a su tema por defecto sin fondo personalizado:
```bash
sudo ./setup-gdm-theme.sh --restore
```

---

### Instalación alternativa como Plugin en Waywallen (.zip)

Si prefieres gestionarlo desde la interfaz gráfica de Waywallen:
1. Genera el paquete zip:
   ```bash
   ./build-plugin-zip.sh
   ```
2. Abre **Waywallen** -> **Plugins** -> haz clic en el botón **`+`** (arriba a la derecha).
3. Selecciona el archivo `waywallen-lockscreen-sync.zip`.

---

## ⚙️ ¿Cómo funciona internamente?

### 1. Modelo 100% Reactivo (0% de CPU en reposo)
El software no utiliza demonios pesados ni bucles infinitos:
* **`waywallen-lockscreen-sync.path`**: Se apoya en la API `inotify` del kernel Linux vía `systemd --user`. Permanece dormido a **0.00% CPU** y solo reacciona cuando Waywallen actualiza `~/.config/waywallen/config.toml`.
* **Ejecución atómica**: El script de extracción y composición solo corre una vez tras el cambio de fondo, tarda aproximadamente **80 a 150 milisegundos** y **termina de inmediato**.

### 2. Captura Nativa GPU en Tiempo Real (`Gsk.Renderer`)
Las escenas animadas de Wallpaper Engine (`scene.pkg`) contienen esqueletos 2D/3D (Spine/Puppet), sombreadores dinámicos y decenas de capas separadas. Extraer solo imágenes estáticas del archivo genera transparencias rotas y partes flotantes.
* Nuestro parche en `renderer.js` intercepta el búfer final directamente desde la GPU (`Gsk.Renderer.render_texture`) una vez que la escena termina de cargar sus capas.
* Esto garantiza que el fotograma exportado contenga el personaje completo, efectos visuales y colores exactos.

### 3. Composición Multi-Monitor Inteligente
En sistemas con múltiples monitores de distinta resolución (por ejemplo, Monitor 1 en 2560x1440 y Monitor 2 en 1920x1080):
* Consulta la topología física y coordenadas en `~/.config/monitors.xml`.
* Genera un lienzo compuesto unificado (ej. **4480x1440**) donde cada monitor recibe su fotograma duplicado y mapeado 1:1.
* Evita que el gestor de pantalla estire una sola imagen deformándola o cortándola a través de los monitores.

### 4. Compresión Full Chroma 4:4:4 (`subsampling=0`)
La exportación a JPEG se realiza con `quality=100` y `subsampling=0` (4:4:4 sin compresión cromática), preservando la nitidez en bordes de alto contraste, textos y delineados de personajes estilo anime.

---

## 🔍 Monitoreo y Diagnóstico

Para revisar el estado de los servicios en tu sesión de usuario:
```bash
systemctl --user status waywallen-lockscreen-sync.path
systemctl --user status waywallen-lockscreen-sync.service
```

Para inspeccionar las imágenes generadas actualmente:
```bash
# Fondo para GNOME screensaver / lockscreen
identify ~/.local/share/waywallen/current_lock.jpg

# Fondo para GDM greeter (multi-monitor)
identify /usr/share/backgrounds/waywallen_lock.jpg
```

---

## 🧪 Suite de Pruebas Unitarias

El repositorio incluye una batería de pruebas automatizadas con entornos simulados (mocks) que validan el comportamiento ante fallos, parsing TOML/XML, decodificación de paquetes, inyección CSS y composición multi-monitor:

```bash
./tests/run_tests.sh
```

---

## 📂 Estructura del Repositorio

* `install.sh`: Instalador de usuario y configurador de servicios.
* `sync-waywallen-lockscreen.sh`: Orquestador principal de sincronización.
* `waywallen_extractor.py`: Motor de composición multi-monitor y extracción de alta fidelidad.
* `patch-renderer.py`: Hook para captura de fotogramas GPU en el renderer de GNOME Shell.
* `setup-gdm-theme.sh`: Inyector y compilador del tema para GDM (`glib-compile-resources`).
* `setup-sddm-theme.sh`: Configurador auxiliar para SDDM.
* `waywallen-lockscreen-sync.path` / `.service`: Unidades de systemd para ejecución automática.
* `build-plugin-zip.sh`: Empaquetador para la UI de Waywallen.
* `tests/run_tests.sh`: Suite de pruebas unitarias (18 tests).
