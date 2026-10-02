#!/usr/bin/env python3
"""
wall2lock_gui.py - Simple Libadwaita GUI for Wall2Lock
Provides a clean, GNOME/Adwaita interface with toggles for:
1. Activar / Desactivar la sincronización activa (systemd path watcher)
2. Iniciar con el sistema en el arranque / inicio de sesión (systemd enable/disable)
3. Mostrar / Ocultar el icono en la bandeja del sistema (StatusNotifierItem)
"""

import os
import sys
import json
import logging
import subprocess
import threading
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Adw, Gio, GLib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CONFIG_DIR = os.path.expanduser("~/.config/wall2lock")
LEGACY_CONFIG_DIR = os.path.expanduser("~/.config/waywallen-lockscreen-sync")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "gui_settings.json")
LEGACY_SETTINGS_FILE = os.path.join(LEGACY_CONFIG_DIR, "gui_settings.json")

SYNC_SCRIPT = os.path.expanduser("~/.local/bin/wall2lock-sync")
LEGACY_SYNC_SCRIPT = os.path.expanduser("~/.local/bin/sync-waywallen-lockscreen.sh")

SNI_XML = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Scroll">
      <arg name="delta" type="i" direction="in"/>
      <arg name="orientation" type="s" direction="in"/>
    </method>

    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus">
      <arg name="status" type="s"/>
    </signal>
  </interface>
</node>
"""


def load_settings():
    for path in (SETTINGS_FILE, LEGACY_SETTINGS_FILE):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error cargando configuración desde {path}: {e}")
    return {"show_tray": True}


def save_settings(settings):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logging.error(f"Error guardando configuración: {e}")


def get_sync_script():
    if os.path.isfile(SYNC_SCRIPT) and os.access(SYNC_SCRIPT, os.X_OK):
        return SYNC_SCRIPT
    if os.path.isfile(LEGACY_SYNC_SCRIPT) and os.access(LEGACY_SYNC_SCRIPT, os.X_OK):
        return LEGACY_SYNC_SCRIPT
    return SYNC_SCRIPT


def is_sync_active():
    """Verifica si wall2lock.path (o legacy) está activo."""
    for unit in ("wall2lock.path", "waywallen-lockscreen-sync.path"):
        res = subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit], capture_output=True)
        if res.returncode == 0:
            return True
    return False


def set_sync_active(enable: bool):
    """Inicia o detiene el watcher path de systemd."""
    cmd = "start" if enable else "stop"
    # Prioritizar wall2lock.path
    unit = "wall2lock.path"
    check = subprocess.run(["systemctl", "--user", "list-unit-files", "wall2lock.path"], capture_output=True, text=True)
    if "wall2lock.path" not in check.stdout:
        unit = "waywallen-lockscreen-sync.path"

    res = subprocess.run(["systemctl", "--user", cmd, unit], capture_output=True, text=True)
    return res.returncode == 0, res.stderr.strip()


def is_startup_enabled():
    """Verifica si wall2lock.path (o legacy) está habilitado al inicio."""
    for unit in ("wall2lock.path", "waywallen-lockscreen-sync.path"):
        res = subprocess.run(["systemctl", "--user", "is-enabled", "--quiet", unit], capture_output=True)
        if res.returncode == 0:
            return True
    return False


def set_startup_enabled(enable: bool):
    """Habilita o deshabilita los servicios de systemd para inicio automático."""
    cmd = "enable" if enable else "disable"
    units = ["wall2lock.path", "wall2lock.service"]
    check = subprocess.run(["systemctl", "--user", "list-unit-files", "wall2lock.path"], capture_output=True, text=True)
    if "wall2lock.path" not in check.stdout:
        units = ["waywallen-lockscreen-sync.path", "waywallen-lockscreen-sync.service"]

    res = subprocess.run(
        ["systemctl", "--user", cmd] + units,
        capture_output=True,
        text=True
    )
    return res.returncode == 0, res.stderr.strip()


class StatusNotifierManager:
    """Implementa org.kde.StatusNotifierItem vía Gio.DBus nativo."""

    def __init__(self, on_activate_cb=None):
        self.on_activate_cb = on_activate_cb
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.owner_id = None
        self.reg_id = None
        self.service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-wall2lock"
        self._enabled = False

    def is_enabled(self):
        return self._enabled

    def enable(self):
        if self._enabled or self.owner_id is not None:
            return
        self._enabled = True
        try:
            node_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
            interface_info = node_info.interfaces[0]

            def method_call(conn, sender, object_path, interface_name, method_name, parameters, invocation):
                if method_name in ("Activate", "ContextMenu", "SecondaryActivate"):
                    if self.on_activate_cb:
                        GLib.idle_add(self.on_activate_cb)
                invocation.return_value(None)

            def get_property(conn, sender, object_path, interface_name, property_name):
                props = {
                    "Category": GLib.Variant("s", "ApplicationStatus"),
                    "Id": GLib.Variant("s", "wall2lock"),
                    "Title": GLib.Variant("s", "Wall2Lock"),
                    "Status": GLib.Variant("s", "Active"),
                    "WindowId": GLib.Variant("i", 0),
                    "IconThemePath": GLib.Variant("s", ""),
                    "ItemIsMenu": GLib.Variant("b", False),
                    "Menu": GLib.Variant("o", "/NO_DBUSMENU"),
                    "IconName": GLib.Variant("s", "wall2lock"),
                    "IconPixmap": GLib.Variant("a(iiay)", []),
                    "OverlayIconName": GLib.Variant("s", ""),
                    "OverlayIconPixmap": GLib.Variant("a(iiay)", []),
                    "AttentionIconName": GLib.Variant("s", ""),
                    "AttentionIconPixmap": GLib.Variant("a(iiay)", []),
                    "AttentionMovieName": GLib.Variant("s", ""),
                    "ToolTip": GLib.Variant(
                        "(sa(iiay)ss)",
                        ("wall2lock", [], "Wall2Lock", "Sincronizador de fondo para pantalla de bloqueo y greeter")
                    )
                }
                return props.get(property_name, None)

            self.reg_id = self.bus.register_object(
                "/StatusNotifierItem",
                interface_info,
                method_call,
                get_property,
                None
            )

            def on_name_acquired(conn, name):
                try:
                    proxy = Gio.DBusProxy.new_sync(
                        conn,
                        Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                        None,
                        "org.kde.StatusNotifierWatcher",
                        "/StatusNotifierWatcher",
                        "org.kde.StatusNotifierWatcher",
                        None
                    )
                    proxy.RegisterStatusNotifierItem("(s)", name)
                    logging.info("Icono Wall2Lock registrado con éxito en StatusNotifierWatcher")
                except Exception as ex:
                    logging.warning(f"No se pudo registrar con StatusNotifierWatcher: {ex}")

            self.owner_id = Gio.bus_own_name(
                Gio.BusType.SESSION,
                self.service_name,
                Gio.BusNameOwnerFlags.NONE,
                None,
                on_name_acquired,
                None
            )
        except Exception as e:
            logging.error(f"Fallo al habilitar icono en la bandeja: {e}")

    def disable(self):
        self._enabled = False
        if self.owner_id is not None:
            try:
                Gio.bus_unown_name(self.owner_id)
            except Exception:
                pass
            self.owner_id = None
        if self.reg_id is not None:
            try:
                self.bus.unregister_object(self.reg_id)
            except Exception:
                pass
            self.reg_id = None
        logging.info("Icono de bandeja desactivado")


class Wall2LockWindow(Adw.ApplicationWindow):
    def __init__(self, app, tray_manager):
        super().__init__(application=app, title="Wall2Lock")
        self.app = app
        self.tray_manager = tray_manager
        self.settings = load_settings()
        self.updating_ui = False

        self.set_default_size(440, 360)
        self.set_resizable(False)
        self.set_icon_name("wall2lock")

        # Configurar intercepción de cierre para minimizar al tray si está activado
        self.connect("close-request", self.on_close_request)

        # Toast Overlay para notificaciones en la UI
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        # Contenedor vertical principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)

        # HeaderBar con estilo nativo Adwaita
        header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="Wall2Lock", subtitle="Waywallen & skwd-wall")
        header.set_title_widget(title_widget)

        # Botón para sincronizar manualmente ahora
        self.btn_sync = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Sincronizar ahora")
        self.btn_sync.connect("clicked", self.on_sync_now_clicked)
        header.pack_end(self.btn_sync)

        main_box.append(header)

        # Página de preferencias de Adwaita
        pref_page = Adw.PreferencesPage()
        main_box.append(pref_page)

        pref_group = Adw.PreferencesGroup()
        pref_group.set_title("Opciones de sincronización")
        pref_group.set_description("Controla el monitoreo del fondo de pantalla y su arranque")
        pref_page.add(pref_group)

        # --- TOGGLE 1: Activar/Desactivar Sincronización activa ---
        self.row_active = Adw.SwitchRow()
        self.row_active.set_title("Sincronización activa")
        self.row_active.set_subtitle("Monitorea cambios y actualiza el lockscreen/SDDM")
        self.row_active.add_prefix(Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic"))
        self.row_active.connect("notify::active", self.on_active_toggled)
        pref_group.add(self.row_active)

        # --- TOGGLE 2: Inicio automático en el startup ---
        self.row_startup = Adw.SwitchRow()
        self.row_startup.set_title("Iniciar con el sistema")
        self.row_startup.set_subtitle("Activar automáticamente al encender o iniciar sesión")
        self.row_startup.add_prefix(Gtk.Image.new_from_icon_name("system-run-symbolic"))
        self.row_startup.connect("notify::active", self.on_startup_toggled)
        pref_group.add(self.row_startup)

        # --- TOGGLE 3: Mostrar icono en la bandeja del sistema ---
        self.row_tray = Adw.SwitchRow()
        self.row_tray.set_title("Icono en la bandeja del sistema")
        self.row_tray.set_subtitle("Muestra el icono en la barra de tareas y minimiza al cerrar")
        self.row_tray.add_prefix(Gtk.Image.new_from_icon_name("preferences-system-symbolic"))
        self.row_tray.connect("notify::active", self.on_tray_toggled)
        pref_group.add(self.row_tray)

        # Cargar estados iniciales
        self.refresh_states()

    def refresh_states(self):
        """Lee el estado del sistema y actualiza los toggles sin disparar callbacks redundantes."""
        self.updating_ui = True
        try:
            self.row_active.set_active(is_sync_active())
            self.row_startup.set_active(is_startup_enabled())
            self.row_tray.set_active(self.settings.get("show_tray", True))
        finally:
            self.updating_ui = False

    def on_active_toggled(self, widget, param):
        if self.updating_ui:
            return
        target_state = widget.get_active()
        ok, err = set_sync_active(target_state)
        if ok:
            msg = "Sincronización activada" if target_state else "Sincronización detenida"
            self.show_toast(msg)
        else:
            self.show_toast(f"Error al cambiar estado: {err or 'Fallo desconocido'}")
            # Revertir
            self.updating_ui = True
            widget.set_active(not target_state)
            self.updating_ui = False

    def on_startup_toggled(self, widget, param):
        if self.updating_ui:
            return
        target_state = widget.get_active()
        ok, err = set_startup_enabled(target_state)
        if ok:
            msg = "Inicio automático activado" if target_state else "Inicio automático desactivado"
            self.show_toast(msg)
        else:
            self.show_toast(f"Error en systemd: {err or 'Fallo desconocido'}")
            self.updating_ui = True
            widget.set_active(not target_state)
            self.updating_ui = False

    def on_tray_toggled(self, widget, param):
        if self.updating_ui:
            return
        target_state = widget.get_active()
        self.settings["show_tray"] = target_state
        save_settings(self.settings)

        if target_state:
            self.tray_manager.enable()
            self.show_toast("Icono de bandeja activado")
        else:
            self.tray_manager.disable()
            self.show_toast("Icono de bandeja desactivado")

    def on_sync_now_clicked(self, button):
        """Ejecuta una sincronización inmediata."""
        self.btn_sync.set_sensitive(False)
        self.show_toast("Sincronizando fondos de pantalla...")

        def run_sync():
            script = get_sync_script()
            res = subprocess.run([script], capture_output=True, text=True)
            GLib.idle_add(self.on_sync_finished, res.returncode == 0, res.stderr)

        threading.Thread(target=run_sync, daemon=True).start()

    def on_sync_finished(self, success, err):
        self.btn_sync.set_sensitive(True)
        if success:
            self.show_toast("¡Fondo sincronizado correctamente!")
        else:
            self.show_toast("Error en la sincronización")

    def show_toast(self, message):
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def on_close_request(self, window):
        """Si la bandeja está activa, minimiza a la bandeja en lugar de salir."""
        if self.tray_manager.is_enabled():
            self.set_visible(False)
            return True
        return False


class Wall2LockApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.rilorca.wall2lock",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.window = None
        self.tray_manager = StatusNotifierManager(on_activate_cb=self.toggle_window_visibility)

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        start_minimized = "--minimized" in args or "-m" in args or "--tray" in args
        self.activate_app(start_minimized=start_minimized)
        return 0

    def do_activate(self):
        self.activate_app(start_minimized=False)

    def activate_app(self, start_minimized=False):
        if not self.window:
            self.window = Wall2LockWindow(self, self.tray_manager)

        # Iniciar bandeja si está configurado
        settings = load_settings()
        if settings.get("show_tray", True):
            self.tray_manager.enable()

        if not start_minimized:
            self.window.set_visible(True)
            self.window.present()

    def toggle_window_visibility(self):
        if not self.window:
            self.activate_app(start_minimized=False)
            return

        if self.window.is_visible() and self.window.is_active():
            self.window.set_visible(False)
        else:
            self.window.set_visible(True)
            self.window.present()

    def do_shutdown(self):
        if self.tray_manager:
            self.tray_manager.disable()
        Adw.Application.do_shutdown(self)


def main():
    app = Wall2LockApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
