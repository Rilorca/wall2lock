#!/usr/bin/env python3
import os
import sys
import argparse
import struct
import ctypes
import subprocess
import shutil
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps

def resolve_path(base, rel):
    if not rel or rel == "NULL":
        return None
    if os.path.isabs(rel):
        return rel
    return os.path.join(base, rel)

def extract_video_frame(video_path, output_path):
    """Extract a high quality full-resolution frame from a video file."""
    if not os.path.isfile(video_path):
        return False
    try:
        cmd = ['ffmpeg', '-y', '-ss', '00:00:01', '-i', video_path, '-vframes', '1', '-q:v', '2', output_path]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return True
    except Exception:
        pass
    try:
        cmd = ['ffmpeg', '-y', '-i', video_path, '-vframes', '1', '-q:v', '2', output_path]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return True
    except Exception:
        pass
    return False

def extract_pkg_texture(pkg_path, output_path):
    """Extract native high-res texture from a Wallpaper Engine scene.pkg file."""
    if not os.path.isfile(pkg_path):
        return False
    try:
        with open(pkg_path, 'rb') as f:
            header_peek = f.read(65536)
            if not header_peek.startswith(b'\x08\x00\x00\x00PKGV'):
                return False
            magic_len = struct.unpack('<I', header_peek[:4])[0]
            offset = 4 + magic_len
            file_count = struct.unpack('<I', header_peek[offset:offset+4])[0]
            offset += 4
            files = []
            f.seek(offset)
            for _ in range(file_count):
                name_len = struct.unpack('<I', f.read(4))[0]
                name = f.read(name_len).decode('utf-8', errors='ignore')
                f_off, f_len = struct.unpack('<II', f.read(8))
                files.append((name, f_off, f_len))
            header_end = f.tell()

            tex_files = [x for x in files if x[0].endswith('.tex')]
            if not tex_files:
                return False
            tex_files.sort(key=lambda x: x[2], reverse=True)

            # Try the largest textures (usually background/character artwork)
            for best in tex_files[:5]:
                f.seek(header_end + best[1])
                content = f.read(best[2])

                # 1. Check for modern Wallpaper Engine embedded raw images (JPEG, PNG, WebP)
                for magic, ext in [(b'\xff\xd8\xff', '.jpg'), (b'\x89PNG\r\n\x1a\n', '.png'), (b'RIFF', '.webp')]:
                    idx = content.find(magic)
                    if idx != -1:
                        if magic == b'RIFF' and content[idx+8:idx+12] != b'WEBP':
                            continue
                        temp_raw = os.path.join(tempfile.gettempdir(), f"pkg_raw_{os.getpid()}_{best[1]}{ext}")
                        try:
                            with open(temp_raw, 'wb') as raw_f:
                                raw_f.write(content[idx:])
                            subprocess.check_call(['ffmpeg', '-y', '-i', temp_raw, '-q:v', '2', output_path],
                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                                return True
                        except Exception:
                            pass
                        finally:
                            if os.path.isfile(temp_raw):
                                try:
                                    os.remove(temp_raw)
                                except Exception:
                                    pass

                # 2. Check for LZ4-compressed DDS textures (TEXB0004/TEXB0003)
                texb_idx = content.find(b'TEXB0004')
                if texb_idx != -1:
                    try:
                        lz4_path = None
                        for cand in ['/usr/lib/liblz4.so', '/usr/lib/liblz4.so.1', 'liblz4.so', 'liblz4.so.1']:
                            try:
                                lz4_lib = ctypes.CDLL(cand)
                                lz4_path = cand
                                break
                            except Exception:
                                continue
                        if lz4_path:
                            lz4_lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
                            lz4_lib.LZ4_decompress_safe.restype = ctypes.c_int

                            hdr_bytes = content[texb_idx+9:texb_idx+45]
                            _, _, _, fmt, w, h, _, uncomp_sz, comp_sz = struct.unpack('<IIIIIIIII', hdr_bytes)
                            comp_data = content[texb_idx+45:texb_idx+45+comp_sz]
                            dst = ctypes.create_string_buffer(uncomp_sz)
                            res = lz4_lib.LZ4_decompress_safe(comp_data, dst, comp_sz, uncomp_sz)
                            if res == uncomp_sz:
                                dds_hdr = bytearray(128)
                                dds_hdr[0:4] = b'DDS '
                                struct.pack_into('<I', dds_hdr, 4, 124)
                                struct.pack_into('<I', dds_hdr, 8, 0x81007)
                                struct.pack_into('<I', dds_hdr, 12, h)
                                struct.pack_into('<I', dds_hdr, 16, w)
                                struct.pack_into('<I', dds_hdr, 20, uncomp_sz)
                                struct.pack_into('<I', dds_hdr, 76, 32)
                                struct.pack_into('<I', dds_hdr, 80, 0x4)
                                dds_hdr[84:88] = b'DXT5' if fmt == 5 else b'DXT1'
                                struct.pack_into('<I', dds_hdr, 108, 0x1000)

                                temp_dds = os.path.join(tempfile.gettempdir(), f"pkg_tex_{os.getpid()}.dds")
                                with open(temp_dds, 'wb') as ddf:
                                    ddf.write(dds_hdr)
                                    ddf.write(dst.raw)

                                subprocess.check_call(['ffmpeg', '-y', '-i', temp_dds, '-q:v', '2', output_path],
                                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                try:
                                    os.remove(temp_dds)
                                except Exception:
                                    pass

                                if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                                    return True
                    except Exception:
                        pass
    except Exception:
        pass
    return False

def extract_high_res_image(item_type, full_item_path, preview_full_path, output_path):
    """Extract best available resolution image for a wallpaper."""
    item_dir = os.path.dirname(full_item_path) if full_item_path else None

    # 1. Video wallpapers (MP4 / WebM)
    if item_type == "video" and full_item_path and os.path.isfile(full_item_path):
        if extract_video_frame(full_item_path, output_path):
            return True

    # 2. Scene / PKG wallpapers
    if full_item_path and full_item_path.endswith('.pkg') and os.path.isfile(full_item_path):
        if extract_pkg_texture(full_item_path, output_path):
            return True

    if item_dir:
        candidate_pkg = os.path.join(item_dir, "scene.pkg")
        if os.path.isfile(candidate_pkg):
            if extract_pkg_texture(candidate_pkg, output_path):
                return True

        # Check for any high-res images in workshop dir
        for name in ["preview.jpg", "preview.png", "preview.jpeg", "preview.webp"]:
            candidate = os.path.join(item_dir, name)
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 50000:
                try:
                    subprocess.check_call(['ffmpeg', '-y', '-i', candidate, '-q:v', '2', output_path],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                        return True
                except Exception:
                    pass

    # 3. Static image wallpapers
    if full_item_path and os.path.isfile(full_item_path):
        try:
            subprocess.check_call(['ffmpeg', '-y', '-i', full_item_path, '-vframes', '1', '-q:v', '2', output_path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception:
            pass

    # 4. Preview fallback (scale if small)
    if preview_full_path and os.path.isfile(preview_full_path):
        # Guard: check preview dimensions. If tiny (<300x300), look for any larger image in directory
        is_tiny = False
        try:
            with Image.open(preview_full_path) as pimg:
                if pimg.width < 300 or pimg.height < 300:
                    is_tiny = True
        except Exception:
            pass

        if is_tiny and item_dir:
            for root, _, fnames in os.walk(item_dir):
                for fn in fnames:
                    if fn.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) and not fn.startswith('.'):
                        cand_path = os.path.join(root, fn)
                        try:
                            with Image.open(cand_path) as cimg:
                                if cimg.width >= 400 and cimg.height >= 400:
                                    preview_full_path = cand_path
                                    is_tiny = False
                                    break
                        except Exception:
                            pass
                if not is_tiny:
                    break

        try:
            subprocess.check_call(['ffmpeg', '-y', '-i', preview_full_path, '-vframes', '1', '-vf',
                                   r'scale=w=max(1920\,iw):h=-2:flags=lanczos', '-q:v', '2', output_path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception:
            try:
                subprocess.check_call(['ffmpeg', '-y', '-i', preview_full_path, '-vframes', '1', '-q:v', '2', output_path],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                    return True
            except Exception:
                pass

    return False

def parse_monitors_xml(monitors_xml_path):
    """Parse GNOME ~/.config/monitors.xml and return logical monitors list."""
    if not monitors_xml_path or not os.path.isfile(monitors_xml_path):
        return []
    try:
        tree = ET.parse(monitors_xml_path)
        config = tree.find('configuration')
        if config is None:
            return []
        monitors = []
        for lm in config.findall('logicalmonitor'):
            x_el = lm.find('x')
            y_el = lm.find('y')
            w_el = lm.find('.//width')
            h_el = lm.find('.//height')
            if x_el is not None and y_el is not None and w_el is not None and h_el is not None:
                monitors.append({
                    'x': int(x_el.text),
                    'y': int(y_el.text),
                    'w': int(w_el.text),
                    'h': int(h_el.text)
                })
        return monitors
    except Exception:
        return []

def get_capture_dir():
    """Get persistent capture directory with fallback."""
    custom = os.environ.get("WAYWALLEN_CAPTURE_DIR")
    if custom:
        return custom
    return os.path.expanduser("~/.local/share/waywallen/captures")

def find_monitor_capture(idx, capture_dir=None):
    """Find capture file for monitor index in persistent cache or /tmp."""
    cap_dir = capture_dir or get_capture_dir()
    for d in [cap_dir, "/tmp"]:
        p = os.path.join(d, f"waywallen_capture_{idx}.png")
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            return p
    return None

def compose_multi_monitor(source_image_path, target_gdm_path, monitors, capture_dir=None):
    """Composite the wallpaper duplicated onto each monitor on the virtual stage."""
    sorted_monitors = sorted(monitors, key=lambda m: (m['x'], m['y'])) if monitors else []

    if not monitors or len(monitors) <= 1:
        cap0 = find_monitor_capture(0, capture_dir)
        src = cap0 if cap0 else source_image_path
        img = Image.open(src)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(target_gdm_path, "JPEG", quality=100, subsampling=0)
        return True

    canvas_w = max(m['x'] + m['w'] for m in monitors)
    canvas_h = max(m['y'] + m['h'] for m in monitors)
    canvas = Image.new('RGB', (canvas_w, canvas_h), (0, 0, 0))

    fallback_img = None
    if os.path.isfile(source_image_path):
        try:
            fallback_img = Image.open(source_image_path)
        except Exception:
            pass

    for idx, m in enumerate(sorted_monitors):
        cap_file = find_monitor_capture(idx, capture_dir)
        mon_img = None
        if cap_file:
            try:
                mon_img = Image.open(cap_file)
            except Exception:
                pass

        if mon_img is None and fallback_img is not None:
            mon_img = ImageOps.fit(fallback_img, (m['w'], m['h']), method=Image.Resampling.LANCZOS)
        elif mon_img is not None:
            if mon_img.size != (m['w'], m['h']):
                mon_img = ImageOps.fit(mon_img, (m['w'], m['h']), method=Image.Resampling.LANCZOS)

        if mon_img:
            if mon_img.mode != 'RGB':
                mon_img = mon_img.convert('RGB')
            canvas.paste(mon_img, (m['x'], m['y']))

    canvas.save(target_gdm_path, 'JPEG', quality=100, subsampling=0)
    return True

def safe_write_target(src_file, dst_file):
    """Safely write to destination file even if parent directory is not user-writable."""
    if not dst_file or not os.path.isfile(src_file):
        return False
    dst_dir = os.path.dirname(os.path.abspath(dst_file))
    try:
        if os.access(dst_dir, os.W_OK):
            tmp = dst_file + f".tmp_{os.getpid()}"
            shutil.copyfile(src_file, tmp)
            os.replace(tmp, dst_file)
        elif os.access(dst_file, os.W_OK):
            with open(src_file, 'rb') as fsrc, open(dst_file, 'wb') as fdst:
                shutil.copyfileobj(fsrc, fdst)
        else:
            return False
        try:
            os.chmod(dst_file, 0o644)
        except Exception:
            pass
        return True
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description="Waywallen high-res lockscreen and multi-monitor compositor")
    parser.add_argument("--type", required=True, help="Wallpaper type (video, scene, image)")
    parser.add_argument("--lib", required=True, help="Library base path")
    parser.add_argument("--item", required=True, help="Item path relative or absolute")
    parser.add_argument("--preview", default="NULL", help="Preview path relative or absolute")
    parser.add_argument("--user-out", required=True, help="Target path for single user wallpaper")
    parser.add_argument("--gdm-out", required=True, help="Target path for GDM multi-monitor wallpaper")
    parser.add_argument("--sddm-out", default="", help="Target path for SDDM wallpaper")
    parser.add_argument("--monitors", default="", help="Path to monitors.xml")

    args = parser.parse_args()

    full_item = resolve_path(args.lib, args.item)
    full_preview = resolve_path(args.lib, args.preview)

    temp_single = os.path.join(tempfile.gettempdir(), f"wp_single_{os.getpid()}.jpg")
    temp_gdm = os.path.join(tempfile.gettempdir(), f"wp_gdm_{os.getpid()}.jpg")

    try:
        live_cap0 = find_monitor_capture(0)
        if live_cap0:
            img = Image.open(live_cap0)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(temp_single, 'JPEG', quality=100, subsampling=0)
            success = True
        else:
            success = extract_high_res_image(args.type, full_item, full_preview, temp_single)
        if not success or not os.path.isfile(temp_single):
            print(f"Error: Could not extract image source for wallpaper: {full_item}", file=sys.stderr)
            sys.exit(1)

        # 1. Update single user wallpaper
        os.makedirs(os.path.dirname(os.path.abspath(args.user_out)), exist_ok=True)
        safe_write_target(temp_single, args.user_out)

        # 2. Update multi-monitor composite for GDM
        monitors_path = args.monitors or os.path.expanduser("~/.config/monitors.xml")
        monitors = parse_monitors_xml(monitors_path)
        compose_multi_monitor(args.user_out, temp_gdm, monitors)

        if os.path.isfile(temp_gdm):
            safe_write_target(temp_gdm, args.gdm_out)

        # 3. Optional SDDM wallpaper
        if args.sddm_out:
            safe_write_target(args.user_out, args.sddm_out)

        print(f"Success: Lockscreen and GDM wallpaper updated (monitors: {len(monitors)})")
    finally:
        for f in [temp_single, temp_gdm]:
            if os.path.isfile(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

if __name__ == "__main__":
    main()

