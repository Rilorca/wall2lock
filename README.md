# Waywallen Lockscreen, GDM & SDDM Sync

Sincronizador automático del fondo de pantalla activo en [Waywallen](https://github.com/waywallen) hacia la pantalla de bloqueo (GNOME / KDE Plasma) y los gestores de inicio de sesión **GDM (GNOME Display Manager)** y **SDDM**.

## Características
- **Garantía total de pantalla al reiniciar el PC y en bloqueo**: Funciona tanto si recién se prendió el computador (pantalla de inicio GDM / SDDM antes del login) como dentro de la sesión activa con `Super+L`.
- **Soporte nativo para GDM (GNOME)**: Inyecta y compila limpiamente la regla de background en `gnome-shell-theme.gresource` apuntando a `/usr/share/backgrounds/waywallen_lock.jpg`. Esto evita que GDM muestre la pantalla gris `#222226` por defecto.
- **Sin necesidad de sudo recurrente**: La configuración de permisos del archivo `/usr/share/backgrounds/waywallen_lock.jpg` se realiza una sola vez. Cada cambio de wallpaper posterior se actualiza inmediatamente por el usuario sin contraseñas.
- **Conversión universal a JPEG de alta fidelidad**: Utiliza `ffmpeg` para extraer fotogramas limpios de videos (MP4, WebM) y convertir previsualizaciones (GIF animado, PNG, WebP) a JPEG estándar compatible con lockscreens.
- **Soporte completo GNOME**: Configura de manera atómica y simultánea `picture-uri` (modo claro), `picture-uri-dark` (modo oscuro) y `org.gnome.desktop.screensaver picture-uri`.
- **Compatibilidad KDE Plasma**: Configura `kscreenlockerrc` (`Image` y `PreviewImage`).
- **Soporte SDDM**: Actualiza `/usr/share/sddm/waywallen_lock.jpg` para entornos KDE / SDDM.
- **Suite de Pruebas Unitarias Integrada (15 pruebas)**: Valida con mocks aislados la robustez ante fallos, parsing toml, sqlite3, ffmpeg, gsettings, compilación/restauración de GDM y el parser St de GNOME Shell.

## Estructura del Proyecto
- `sync-waywallen-lockscreen.sh`: Script principal de extracción, conversión a JPEG y actualización de fondos.
- `setup-gdm-theme.sh`: Script con permisos root para configurar el tema de GDM en GNOME (con soporte para `--restore`).
- `setup-sddm-theme.sh`: Script auxiliar con permisos root para configurar SDDM.
- `waywallen-lockscreen-sync.path`: Unidad `systemd` que vigila cambios en `~/.config/waywallen/config.toml` para actualización en caliente.
- `waywallen-lockscreen-sync.service`: Servicio `systemd` que se ejecuta al inicio de sesión gráfica (`graphical-session.target`) y ante eventos del path.
- `install.sh`: Script de instalación y habilitación automática de servicios.
- `tests/run_tests.sh`: Suite automatizada de pruebas unitarias.

## Instalación y Configuración

### 1. Instalación de usuario
```bash
./install.sh
```

### 2. Configurar la pantalla de inicio al encender el PC

- **Si usas GNOME (GDM)**:
  ```bash
  sudo ./setup-gdm-theme.sh
  ```
  *(Crea el respaldo automático y compila el tema para leer `/usr/share/backgrounds/waywallen_lock.jpg`).*

- **Si usas KDE Plasma (SDDM)**:
  ```bash
  sudo ./setup-sddm-theme.sh
  ```

### Restauración del tema de fábrica en GDM
Si en algún momento deseas revertir GDM a su tema por defecto:
```bash
sudo ./setup-gdm-theme.sh --restore
```

## Instalación como Plugin en Waywallen (.zip)
El proyecto incluye un generador de paquetes `.zip` para la interfaz de Waywallen:
1. Genera el paquete zip:
   ```bash
   ./build-plugin-zip.sh
   ```
2. Abre la ventana principal de **Waywallen**.
3. Ve a **Plugins** y haz clic en el botón **`+`** (arriba a la derecha).
4. Selecciona el archivo generado:
   `waywallen-lockscreen-sync.zip`
5. ¡Listo! El plugin aparecerá listado en la sección **User** de Waywallen.

## Pruebas Unitarias
Para ejecutar la suite de pruebas unitarias automatizada:
```bash
bash tests/run_tests.sh
```
