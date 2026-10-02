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

def decode_single_tex_content(content, lz4_lib):
    """Decode raw .tex bytes to a PIL Image (RGBA or RGB)."""
    # 1. Raw image
    for magic, ext in [(b'\xff\xd8\xff', '.jpg'), (b'\x89PNG\r\n\x1a\n', '.png'), (b'RIFF', '.webp')]:
        idx = content.find(magic)
        if idx != -1:
            if magic == b'RIFF' and content[idx+8:idx+12] != b'WEBP':
                continue
            temp_raw = os.path.join(tempfile.gettempdir(), f"pkg_raw_{os.getpid()}_{idx}{ext}")
            temp_out = os.path.join(tempfile.gettempdir(), f"pkg_out_{os.getpid()}_{idx}.png")
            try:
                with open(temp_raw, 'wb') as raw_f:
                    raw_f.write(content[idx:])
                subprocess.check_call(['ffmpeg', '-y', '-i', temp_raw, temp_out],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.isfile(temp_out):
                    img = Image.open(temp_out)
                    img.load()
                    return img
            except Exception:
                pass
            finally:
                for f in [temp_raw, temp_out]:
                    if os.path.isfile(f):
                        try: os.remove(f)
                        except Exception: pass

    # 2. TEXB0004 / TEXB0003
    idx4 = content.find(b'TEXB0004')
    idx3 = content.find(b'TEXB0003')
    if (idx4 != -1 or idx3 != -1) and lz4_lib:
        texb_idx = idx4 if idx4 != -1 else idx3
        is_v4 = (texb_idx == idx4)
        try:
            if is_v4:
                hdr_bytes = content[texb_idx+9:texb_idx+45]
                _, _, _, fmt, w, h, _, uncomp_sz, comp_sz = struct.unpack('<IIIIIIIII', hdr_bytes)
                comp_data = content[texb_idx+45:texb_idx+45+comp_sz]
            else:
                hdr_bytes = content[texb_idx+9:texb_idx+41]
                _, _, fmt, w, h, _, uncomp_sz, comp_sz = struct.unpack('<IIIIIIII', hdr_bytes)
                comp_data = content[texb_idx+41:texb_idx+41+comp_sz]

            dst = ctypes.create_string_buffer(uncomp_sz)
            res = lz4_lib.LZ4_decompress_safe(comp_data, dst, comp_sz, uncomp_sz)
            if res == uncomp_sz:
                fourcc = b'DXT1' if uncomp_sz == (w * h // 2) else b'DXT5'
                dds_hdr = bytearray(128)
                dds_hdr[0:4] = b'DDS '
                struct.pack_into('<I', dds_hdr, 4, 124)
                struct.pack_into('<I', dds_hdr, 8, 0x81007)
                struct.pack_into('<I', dds_hdr, 12, h)
                struct.pack_into('<I', dds_hdr, 16, w)
                struct.pack_into('<I', dds_hdr, 20, uncomp_sz)
                struct.pack_into('<I', dds_hdr, 76, 32)
                struct.pack_into('<I', dds_hdr, 80, 0x4)
                dds_hdr[84:88] = fourcc
                struct.pack_into('<I', dds_hdr, 108, 0x1000)

                temp_dds = os.path.join(tempfile.gettempdir(), f"pkg_dds_{os.getpid()}_{texb_idx}.dds")
                temp_png = os.path.join(tempfile.gettempdir(), f"pkg_png_{os.getpid()}_{texb_idx}.png")
                try:
                    with open(temp_dds, 'wb') as ddf:
                        ddf.write(dds_hdr)
                        ddf.write(dst.raw)
                    subprocess.check_call(['ffmpeg', '-y', '-i', temp_dds, temp_png],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.isfile(temp_png):
                        img = Image.open(temp_png)
                        img.load()
                        return img
                finally:
                    for f in [temp_dds, temp_png]:
                        if os.path.isfile(f):
                            try: os.remove(f)
                            except Exception: pass
        except Exception:
            pass

    return None

def composite_pkg_scene(pkg_path, output_path):
    """Parse scene.json from scene.pkg and composite all 2D layers in render order."""
    if not os.path.isfile(pkg_path):
        return False
    try:
        import json
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
            file_map = {name: (f_off, f_len) for name, f_off, f_len in files}

            if 'scene.json' not in file_map:
                return False

            soff, slen = file_map['scene.json']
            f.seek(header_end + soff)
            scene_data = json.loads(f.read(slen).decode('utf-8', errors='ignore'))
            objects = scene_data.get('objects', [])
            if not objects or len(objects) < 2:
                return False

            proj = scene_data.get('general', {}).get('orthogonalprojection', {})
            canvas_w = int(proj.get('width', 3840))
            canvas_h = int(proj.get('height', 2160))

            lz4_lib = None
            for cand in ['/usr/lib/liblz4.so', '/usr/lib/liblz4.so.1', 'liblz4.so', 'liblz4.so.1']:
                try:
                    lz4_lib = ctypes.CDLL(cand)
                    lz4_lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
                    lz4_lib.LZ4_decompress_safe.restype = ctypes.c_int
                    break
                except Exception:
                    continue

            canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 255))
            tex_cache = {}
            rendered_count = 0

            for obj in objects:
                img_model = obj.get('image')
                if not img_model or img_model not in file_map:
                    continue
                moff, mlen = file_map[img_model]
                f.seek(header_end + moff)
                try:
                    mdata = json.loads(f.read(mlen).decode('utf-8', errors='ignore'))
                except Exception:
                    continue

                mat = mdata.get('material')
                if not mat or mat not in file_map:
                    continue
                matoff, matlen = file_map[mat]
                f.seek(header_end + matoff)
                try:
                    matdata = json.loads(f.read(matlen).decode('utf-8', errors='ignore'))
                    passes = matdata.get('passes', [])
                    if not passes:
                        continue
                    tex_name = passes[0].get('textures', [None])[0]
                except Exception:
                    continue

                if not tex_name:
                    continue

                if tex_name not in tex_cache:
                    targets = [tex_name, f'materials/{tex_name}.tex', f'materials/{tex_name}']
                    if not tex_name.endswith('.tex'):
                        targets.append(f'{tex_name}.tex')
                    tex_key = None
                    for t in targets:
                        if t in file_map:
                            tex_key = t
                            break
                    if not tex_key:
                        tex_cache[tex_name] = None
                    else:
                        toff, tlen = file_map[tex_key]
                        f.seek(header_end + toff)
                        tex_bytes = f.read(tlen)
                        tex_cache[tex_name] = decode_single_tex_content(tex_bytes, lz4_lib)

                tex_img = tex_cache[tex_name]
                if not tex_img:
                    continue

                origin_str = obj.get('origin')
                size_str = obj.get('size')
                if not origin_str or not size_str:
                    continue
                try:
                    ox, oy = [float(v) for v in origin_str.split()[:2]]
                    sw, sh = [float(v) for v in size_str.split()[:2]]
                except Exception:
                    continue

                if sw <= 0 or sh <= 0:
                    continue

                resized = tex_img.resize((int(sw), int(sh)), Image.Resampling.LANCZOS)
                x = int(ox - sw / 2)
                y = int(canvas_h - oy - sh / 2)

                if resized.mode == 'RGBA':
                    canvas.paste(resized, (x, y), resized)
                else:
                    canvas.paste(resized, (x, y))
                rendered_count += 1

            if rendered_count >= 2:
                final = canvas.convert('RGB')
                final.save(output_path, 'JPEG', quality=98, subsampling=0)
                return True
    except Exception:
        pass
    return False

def extract_pkg_texture(pkg_path, output_path):
    """Extract native high-res texture or composite 2D scene from a Wallpaper Engine scene.pkg file."""
    if not os.path.isfile(pkg_path):
        return False

    # 1. Try compositing multi-layer scene if scene.json exists with multiple objects
    if composite_pkg_scene(pkg_path, output_path):
        return True

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

                # 2. Check for LZ4-compressed DDS textures (TEXB0004 / TEXB0003)
                idx4 = content.find(b'TEXB0004')
                idx3 = content.find(b'TEXB0003')
                if idx4 != -1 or idx3 != -1:
                    try:
                        lz4_lib = None
                        for cand in ['/usr/lib/liblz4.so', '/usr/lib/liblz4.so.1', 'liblz4.so', 'liblz4.so.1']:
                            try:
                                lz4_lib = ctypes.CDLL(cand)
                                lz4_path = cand
                                break
                            except Exception:
                                continue
                        if lz4_lib:
                            lz4_lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
                            lz4_lib.LZ4_decompress_safe.restype = ctypes.c_int

                            texb_idx = idx4 if idx4 != -1 else idx3
                            if texb_idx == idx4:
                                hdr_bytes = content[texb_idx+9:texb_idx+45]
                                _, _, _, fmt, w, h, _, uncomp_sz, comp_sz = struct.unpack('<IIIIIIIII', hdr_bytes)
                                comp_data = content[texb_idx+45:texb_idx+45+comp_sz]
                            else:
                                hdr_bytes = content[texb_idx+9:texb_idx+41]
                                _, _, fmt, w, h, _, uncomp_sz, comp_sz = struct.unpack('<IIIIIIII', hdr_bytes)
                                comp_data = content[texb_idx+41:texb_idx+41+comp_sz]

                            if w >= 200 and h >= 200:
                                dst = ctypes.create_string_buffer(uncomp_sz)
                                res = lz4_lib.LZ4_decompress_safe(comp_data, dst, comp_sz, uncomp_sz)
                                if res == uncomp_sz:
                                    fourcc = b'DXT1' if uncomp_sz == (w * h // 2) else b'DXT5'
                                    dds_hdr = bytearray(128)
                                    dds_hdr[0:4] = b'DDS '
                                    struct.pack_into('<I', dds_hdr, 4, 124)
                                    struct.pack_into('<I', dds_hdr, 8, 0x81007)
                                    struct.pack_into('<I', dds_hdr, 12, h)
                                    struct.pack_into('<I', dds_hdr, 16, w)
                                    struct.pack_into('<I', dds_hdr, 20, uncomp_sz)
                                    struct.pack_into('<I', dds_hdr, 76, 32)
                                    struct.pack_into('<I', dds_hdr, 80, 0x4)
                                    dds_hdr[84:88] = fourcc
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
        for name in ["preview.jpg", "preview.png", "preview.jpeg", "preview.webp", "preview.gif"]:
            candidate = os.path.join(item_dir, name)
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 10000:
                try:
                    subprocess.check_call(['ffmpeg', '-y', '-ss', '0', '-i', candidate, '-vframes', '1', '-q:v', '2', output_path],
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

def find_steam_workshop_item(we_id):
    """Find Steam workshop content directory for a given Wallpaper Engine ID."""
    if not we_id:
        return None
    we_id = str(we_id).strip().strip("'\"")
    home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(home, ".local/share/Steam/steamapps/workshop/content/431960", we_id),
        os.path.join(home, ".steam/steam/steamapps/workshop/content/431960", we_id),
        os.path.join(home, ".steam/root/steamapps/workshop/content/431960", we_id),
    ]
    for path in search_dirs:
        if os.path.isdir(path):
            return path
    return None

def detect_skwd_wallpaper():
    """Detect current wallpaper from skwd-wall / skwd-helm / plasma settings."""
    import json
    # 1. Try skwd-helm current --json
    try:
        res = subprocess.run(['skwd-helm', 'current', '--json'], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            for out in data.get('outputs', []):
                if out.get('connected') and (out.get('we_id') or out.get('current') or out.get('path')):
                    we_id = out.get('we_id') or out.get('current')
                    wtype = out.get('type') or ('we' if we_id and str(we_id).isdigit() else 'static')
                    return {
                        'engine': 'skwd',
                        'type': wtype,
                        'we_id': str(we_id) if we_id and str(we_id).isdigit() else '',
                        'path': out.get('path', ''),
                        'name': out.get('name', ''),
                    }
    except Exception:
        pass

    # 2. Try kscreenlockerrc
    kscreen = os.path.expanduser('~/.config/kscreenlockerrc')
    if os.path.isfile(kscreen):
        try:
            with open(kscreen, 'r', errors='ignore') as f:
                content = f.read()
            import re
            m = re.search(r'Assignment\s*=\s*(\{.*?\})', content)
            if m:
                ass = json.loads(m.group(1))
                src = ass.get('source', {})
                kind = src.get('kind', 'we')
                path = src.get('path', '')
                we_id = os.path.basename(path) if (kind == 'we' and path) else ''
                return {
                    'engine': 'skwd',
                    'type': kind,
                    'path': path,
                    'we_id': we_id
                }
        except Exception:
            pass

    # 3. Try skwd-wall-v2 config.json
    cfg_file = os.path.expanduser('~/.config/skwd-wall-v2/config.json')
    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, 'r', errors='ignore') as f:
                cfg_data = json.load(f)
            key = cfg_data.get('components', {}).get('wallpaperSelector', {}).get('lastAppliedKey', '')
            if key:
                if key.startswith('we:'):
                    return {'engine': 'skwd', 'type': 'we', 'we_id': key.split(':', 1)[1], 'path': ''}
                return {'engine': 'skwd', 'type': 'static', 'we_id': '', 'path': key}
        except Exception:
            pass

    # 4. Try wall.sqlite
    db_path = os.path.expanduser('~/.local/share/skwd-wall-v2/wall.sqlite')
    if os.path.isfile(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path, timeout=1)
            c = conn.cursor()
            c.execute("SELECT key, type, video_file, we_id, thumb FROM meta ORDER BY last_applied DESC LIMIT 1;")
            row = c.fetchone()
            conn.close()
            if row:
                key, mtype, vfile, wid, thumb = row
                return {
                    'engine': 'skwd',
                    'type': mtype or 'we',
                    'we_id': wid or (key.split(':', 1)[1] if key and key.startswith('we:') else ''),
                    'path': vfile or thumb or '',
                    'thumb': thumb or ''
                }
        except Exception:
            pass

    return None

def extract_skwd_wallpaper(output_path, skwd_info=None):
    """Extract full-resolution wallpaper from skwd-wall."""
    if not skwd_info:
        skwd_info = detect_skwd_wallpaper()
    if not skwd_info:
        return False

    wtype = skwd_info.get('type', 'we')
    we_id = skwd_info.get('we_id', '')
    wpath = skwd_info.get('path', '')

    # 1. Wallpaper Engine type
    if wtype == 'we' or (we_id and str(we_id).isdigit()):
        ws_dir = wpath if (wpath and os.path.isdir(wpath)) else find_steam_workshop_item(we_id)
        if ws_dir and os.path.isdir(ws_dir):
            scene_pkg = os.path.join(ws_dir, 'scene.pkg')
            if os.path.isfile(scene_pkg):
                if extract_pkg_texture(scene_pkg, output_path):
                    return True

            # Check preview files in workshop dir
            for name in ["preview.gif", "preview.jpg", "preview.png", "preview.jpeg", "preview.webp"]:
                cand = os.path.join(ws_dir, name)
                if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                    try:
                        subprocess.check_call(['ffmpeg', '-y', '-ss', '0', '-i', cand, '-vframes', '1', '-q:v', '2', output_path],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                            return True
                    except Exception:
                        pass

        # Try skwd we-thumbs cache
        if we_id:
            thumb_cache = os.path.expanduser(f"~/.cache/skwd-wall-v2/we-thumbs/{we_id}.webp")
            if os.path.isfile(thumb_cache):
                try:
                    subprocess.check_call(['ffmpeg', '-y', '-i', thumb_cache, '-q:v', '2', output_path],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                        return True
                except Exception:
                    pass

    # 2. Video type
    if wtype == 'video' or (wpath and wpath.lower().endswith(('.mp4', '.mkv', '.webm', '.mov'))):
        if wpath and os.path.isfile(wpath):
            if extract_video_frame(wpath, output_path):
                return True

    # 3. Static image type
    if wpath and os.path.isfile(wpath):
        try:
            subprocess.check_call(['ffmpeg', '-y', '-i', wpath, '-vframes', '1', '-q:v', '2', output_path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception:
            pass

    # 4. Fallback to thumbnail from info
    thumb = skwd_info.get('thumb')
    if thumb and os.path.isfile(thumb):
        try:
            subprocess.check_call(['ffmpeg', '-y', '-i', thumb, '-q:v', '2', output_path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception:
            pass

    return False

def main():
    parser = argparse.ArgumentParser(description="Waywallen & skwd-wall high-res lockscreen and SDDM/GDM compositor")
    parser.add_argument("--source", default="auto", choices=["auto", "skwd", "waywallen"], help="Source engine")
    parser.add_argument("--type", default="", help="Wallpaper type (video, scene, image)")
    parser.add_argument("--lib", default="", help="Library base path")
    parser.add_argument("--item", default="", help="Item path relative or absolute")
    parser.add_argument("--preview", default="NULL", help="Preview path relative or absolute")
    parser.add_argument("--user-out", required=True, help="Target path for single user wallpaper")
    parser.add_argument("--gdm-out", default="", help="Target path for GDM multi-monitor wallpaper")
    parser.add_argument("--sddm-out", default="", help="Target path for SDDM wallpaper")
    parser.add_argument("--monitors", default="", help="Path to monitors.xml")

    args = parser.parse_args()

    full_item = resolve_path(args.lib, args.item) if args.item else None
    full_preview = resolve_path(args.lib, args.preview) if args.preview else None

    temp_single = os.path.join(tempfile.gettempdir(), f"wp_single_{os.getpid()}.jpg")
    temp_gdm = os.path.join(tempfile.gettempdir(), f"wp_gdm_{os.getpid()}.jpg")

    try:
        live_cap0 = find_monitor_capture(0)
        success = False

        # 1. skwd branch
        if args.source == "skwd" or (args.source == "auto" and (not full_item or not os.path.exists(full_item))):
            skwd_info = detect_skwd_wallpaper()
            if skwd_info:
                success = extract_skwd_wallpaper(temp_single, skwd_info)

        # 2. Fallback or explicit waywallen
        if not success:
            if live_cap0:
                img = Image.open(live_cap0)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(temp_single, 'JPEG', quality=100, subsampling=0)
                success = True
            elif args.type and full_item:
                success = extract_high_res_image(args.type, full_item, full_preview, temp_single)

        if not success or not os.path.isfile(temp_single):
            print(f"Error: Could not extract image source for wallpaper: {full_item or 'skwd'}", file=sys.stderr)
            sys.exit(1)

        # 1. Update single user wallpaper
        os.makedirs(os.path.dirname(os.path.abspath(args.user_out)), exist_ok=True)
        safe_write_target(temp_single, args.user_out)

        # 2. Update multi-monitor composite for GDM if requested
        if args.gdm_out:
            monitors_path = args.monitors or os.path.expanduser("~/.config/monitors.xml")
            monitors = parse_monitors_xml(monitors_path)
            compose_multi_monitor(args.user_out, temp_gdm, monitors)
            if os.path.isfile(temp_gdm):
                safe_write_target(temp_gdm, args.gdm_out)

        # 3. Update SDDM wallpaper if requested
        if args.sddm_out:
            safe_write_target(args.user_out, args.sddm_out)

        print(f"Success: Lockscreen / SDDM wallpaper updated successfully to {args.user_out}")
    finally:
        for f in [temp_single, temp_gdm]:
            if os.path.isfile(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

if __name__ == "__main__":
    main()


