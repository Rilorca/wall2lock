#!/usr/bin/env python3
"""
patch-renderer.py: Integrates live frame capture into Waywallen GNOME extension renderer.
Captures the fully-rendered composite frame directly from the GPU paintable to /tmp/waywallen_capture_<index>.png
and automatically triggers sync-waywallen-lockscreen.sh.
"""

import sys
import os
import shutil
import argparse

DEFAULT_RENDERER = os.path.expanduser(
    "~/.local/share/gnome-shell/extensions/org.waywallen.gnome@waywallen.io/renderer/renderer.js"
)

def patch_renderer(path=DEFAULT_RENDERER):
    if not os.path.isfile(path):
        return False, f"renderer.js not found at: {path}"

    with open(path, "r", encoding="utf-8") as f:
        code = f.read()

    if "_captureFrame" in code:
        return True, "renderer.js is already patched"

    # Create backup if not already present
    backup_path = path + ".backup"
    if not os.path.isfile(backup_path):
        shutil.copyfile(path, backup_path)

    # 1. Imports
    target_import = "import Gtk from 'gi://Gtk?version=4.0';"
    if target_import not in code:
        return False, f"Target import line not found in {path}"
    new_imports = target_import + "\nimport Gsk from 'gi://Gsk?version=4.0';\nimport Graphene from 'gi://Graphene?version=1.0';"
    code = code.replace(target_import, new_imports, 1)

    # 2. Debounced notify function
    notify_func = """
let _syncDebounceId = 0;
function notifyCaptureUpdated() {
    if (_syncDebounceId)
        GLib.source_remove(_syncDebounceId);
    _syncDebounceId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 350, () => {
        _syncDebounceId = 0;
        try {
            const home = GLib.get_home_dir();
            const candidates = [
                `${home}/.local/bin/sync-waywallen-lockscreen.sh`,
                `${home}/Documentos/Proyectos/waywallen-lockscreen-sync/sync-waywallen-lockscreen.sh`
            ];
            for (const script of candidates) {
                if (GLib.file_test(script, GLib.FileTest.IS_EXECUTABLE)) {
                    GLib.spawn_command_line_async(script);
                    break;
                }
            }
        } catch (_e) {}
        return GLib.SOURCE_REMOVE;
    });
}
"""
    code = code.replace(new_imports, new_imports + "\n" + notify_func, 1)

    # 3. Reset in _onBindingReady
    binding_sig = "sx, sy, sw, sh, dx, dy, dw, dh, transform, cr, cg, cb, ca) {"
    if binding_sig not in code:
        return False, f"Binding signature not found in {path}"
    code = code.replace(binding_sig, binding_sig + "\n        this._frames = 0;\n        this._captured = false;", 1)

    # 4. Capture in _onFrameReady
    target_frame = """    _onFrameReady(_idx, _seq, fd) {
        if (fd >= 0)
            Waywallen.Display.close_fd(fd);
        this._frames = (this._frames ?? 0) + 1;
        this._paintable?.refresh();
    }"""
    if target_frame not in code:
        return False, f"_onFrameReady block not found in {path}"

    new_frame = """    _onFrameReady(_idx, _seq, fd) {
        if (fd >= 0)
            Waywallen.Display.close_fd(fd);
        this._frames = (this._frames ?? 0) + 1;
        this._paintable?.refresh();
        if (this._frames === 45 || this._frames === 90) {
            this._captureFrame();
        }
    }

    _captureFrame() {
        try {
            if (!this._paintable || !this._window)
                return;
            const r = this._window.get_renderer();
            if (!r)
                return;
            const snapshot = Gtk.Snapshot.new();
            const w = this._pw || this._monitor.get_geometry().width;
            const h = this._ph || this._monitor.get_geometry().height;
            this._paintable.snapshot(snapshot, w, h);
            const node = snapshot.to_node();
            if (!node)
                return;
            const rect = new Graphene.Rect();
            rect.init(0, 0, w, h);
            const tex = r.render_texture(node, rect);
            if (tex) {
                try {
                    const home = GLib.get_home_dir();
                    const capDir = `${home}/.local/share/waywallen/captures`;
                    GLib.mkdir_with_parents(capDir, 0o755);
                    const persistentPath = `${capDir}/waywallen_capture_${this._index}.png`;
                    tex.save_to_png(persistentPath);
                } catch (_e) {}
                try {
                    tex.save_to_png(`/tmp/waywallen_capture_${this._index}.png`);
                } catch (_e) {}
                notifyCaptureUpdated();
            }
        } catch (_e) {}
    }"""
    code = code.replace(target_frame, new_frame, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        os.chmod(path, 0o755)
    except Exception:
        pass

    return True, "Successfully patched renderer.js"

def restore_renderer(path=DEFAULT_RENDERER):
    backup_path = path + ".backup"
    if not os.path.isfile(backup_path):
        return False, f"Backup file not found at: {backup_path}"
    shutil.copyfile(backup_path, path)
    return True, f"Successfully restored {path} from backup"

def main():
    parser = argparse.ArgumentParser(description="Patch Waywallen renderer.js for live frame capture")
    parser.add_argument("--path", default=DEFAULT_RENDERER, help="Path to renderer.js")
    parser.add_argument("--restore", action="store_true", help="Restore original renderer.js from backup")
    args = parser.parse_args()

    if args.restore:
        ok, msg = restore_renderer(args.path)
    else:
        ok, msg = patch_renderer(args.path)

    if ok:
        print(f"Success: {msg}")
        sys.exit(0)
    else:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
