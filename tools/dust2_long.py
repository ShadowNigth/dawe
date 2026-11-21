"""Hand-built BSP slice of Long Doors, surveyed in the cs2go Dust II exports."""
import math
from pathlib import Path
import struct

START = (-240, 0)
SKY = 'dawe_day'
MAP = 'dawe_long'
SIZE = 128


def extrude(outline, lo, hi, texture, axis='z'):
    """Brush from a convex, counterclockwise outline in the plane of extrusion."""
    def point(uv, w):
        u, v = uv
        return (u, v, w) if axis == 'z' else (w, u, v)

    low = [point(uv, lo) for uv in outline]
    high = [point(uv, hi) for uv in outline]
    faces = [(low[0], low[1], low[2]), (high[2], high[1], high[0])]
    faces += [(low[i], high[i], high[(i+1) % len(outline)]) for i in range(len(outline))]
    return '{\n' + '\n'.join(' '.join(f'( {x:.4f} {y:.4f} {z:.4f} )' for x, y, z in face)
                             + f' {texture} 0 0 0 1 1' for face in faces) + '\n}'


def long_layout(box):
    """Return world brushes and lights. Playable floor is deliberately level."""
    blocks = []

    def b(x0, y0, z0, x1, y1, z1, tex='dl_stucco'):
        blocks.append(box(x0, y0, z0, x1, y1, z1, tex))

    # Shell is sealed by opaque floor and sky brushes. Build up the corners with volumes,
    # leaving the wide approach, the narrow double-door corridor and a right turn to Long.
    b(-448, -680, -24, 816, 472, 0, 'dl_sand')
    b(-448, -680, 464, 816, 472, 480, 'sky')
    b(-448, -680, 0, -432, 472, 464, 'sky')
    b(800, -680, 0, 816, 472, 464, 'sky')
    b(-432, -680, 0, 800, -664, 464, 'sky')
    b(-432, 456, 0, 800, 472, 464, 'sky')
    buildings = [(-432, -664, -16, -118, 228), (-16, -664, 458, -112, 256),
                 (-16, 112, 458, 456, 248), (458, 214, 800, 456, 208),
                 (-432, 420, -16, 456, 210), (778, -664, 800, 214, 208),
                 (-432, -118, -410, 420, 208), (458, -664, 778, -632, 180)]
    for x0, y0, x1, y1, h in buildings:
        b(x0, y0, 0, x1, y1, h)
        b(x0, y0, h, x1, y1, h+8, 'dl_trim')

    # A dark passage interrupted by two stone arches with static, diagonal door leaves.
    b(10, -112, 191, 443, 112, 228, 'dl_lime')
    for x in (-10, 440):
        lo, hi = x-10, x+10
        b(lo, -112, 0, hi, -89, 175, 'dl_stone')
        b(lo, 89, 0, hi, 112, 175, 'dl_stone')
        b(lo, -112, 175, hi, 112, 220, 'dl_stone')
        arch = [(-89, 112), (-73, 145), (-48, 162), (-24, 172), (24, 172),
                (48, 162), (73, 145), (89, 112)]
        for (u, z), (v, w) in zip(arch, arch[1:]):
            blocks.append(extrude([(u, z), (v, w), (v, 175), (u, 175)], lo, hi, 'dl_stone', 'x'))
        for side in (-1, 1):
            pivot = (x + 4 * side, side * 89)
            tip = (pivot[0] + 49 * side, side * 26)
            dx, dy = tip[0]-pivot[0], tip[1]-pivot[1]
            length = math.hypot(dx, dy)
            ox, oy = -dy*4/length, dx*4/length
            outline = [(pivot[0]-ox, pivot[1]-oy), (tip[0]-ox, tip[1]-oy),
                       (tip[0]+ox, tip[1]+oy), (pivot[0]+ox, pivot[1]+oy)]
            blocks.append(extrude(outline, 2, 112, 'dl_wood'))

    # Art pass: plaster bands, shade awning, closed shutters and wooden boxes.
    for x0, y0, x1, y1 in [(-400, -118, -30, -115), (-400, 416, -30, 420),
                           (498, 210, 742, 214), (774, -614, 778, 192)]:
        b(x0, y0, 0, x1, y1, 25, 'dl_base')
        b(x0, y0, 118, x1, y1, 124, 'dl_trim')
    b(-330, -115, 26, -259, -111, 114, 'dl_teal')
    b(-330, -118, 118, -245, -82, 124, 'dl_trim')
    b(-357, 184, 0, -301, 250, 55, 'dl_crate')
    b(-356, 204, 55, -313, 248, 94, 'dl_crate')
    b(286, -111, 0, 344, -62, 53, 'dl_crate')
    b(293, -111, 53, 344, -71, 92, 'dl_crate')
    b(771, -493, 24, 778, -414, 119, 'dl_teal')
    b(680, -628, 0, 742, -576, 62, 'dl_crate')
    b(470, -615, 0, 519, -555, 48, 'dl_crate')
    b(505, 123, 0, 557, 182, 56, 'dl_crate')
    b(622, -629, 82, 702, -627, 117, 'dl_teal')
    # Lower relief along the corridor wall and short beams overhead.
    for x in (84, 201, 370):
        b(x, -112, 0, x+12, -104, 191, 'dl_stone')
        b(x, 104, 0, x+12, 112, 191, 'dl_stone')
        b(x, -104, 181, x+12, 104, 191, 'dl_trim')
    for x in (554, 700):
        b(x, 201, 0, x+18, 214, 208, 'dl_lime')
    lights = [(-284, 135, 153, 570), (-292, -35, 164, 480), (-70, 0, 122, 430),
              (48, 0, 153, 405), (158, 0, 166, 350), (262, 0, 166, 390),
              (390, 0, 143, 490), (506, -9, 165, 565), (635, 104, 187, 600),
              (630, -174, 187, 820), (619, -376, 193, 690), (619, -557, 188, 660)]
    entities = [f'{{\n"classname" "info_player_start"\n"origin" "{START[0]} {START[1]} 36"\n"angle" "0"\n}}']
    entities.extend(f'{{\n"classname" "light"\n"origin" "{x} {y} {z}"\n"_light" "255 234 190 {power}"\n}}'
                    for x, y, z, power in lights)
    entities.append('{\n"classname" "light_environment"\n"origin" "600 -190 318"\n'
                    '"pitch" "-65"\n"angle" "35"\n"_light" "255 231 189 425"\n}')
    return blocks, entities


COLORS = {
    'dl_stucco': (193, 156, 112), 'dl_lime': (222, 194, 153), 'dl_trim': (161, 124, 86),
    'dl_sand': (171, 134, 91), 'dl_stone': (169, 137, 102), 'dl_base': (139, 107, 76),
    'dl_wood': (112, 73, 44), 'dl_teal': (61, 104, 111), 'dl_crate': (132, 91, 55),
    'sky': (119, 173, 212),
}


def texel(name, x, y):
    # Repeatable tiled grain without shipping original game textures.
    seed = ((x * 31337 + y * 6971 + 733) ^ (x * y * 1097)) & 65535
    grain = (seed ^ (seed >> 5) ^ (seed << 7)) % 9 - 4
    if name == 'dl_wood':
        plank = (y + ((x // 17) % 3)) % 26
        return grain + (-21 if x % 19 < 2 else plank//8) + (16 if y in range(34,41) or y in range(94,101) else 0)
    if name == 'dl_crate':
        edge = min(x, y, SIZE-1-x, SIZE-1-y)
        brace = abs(x-y) < 7 or abs(x+y-(SIZE-1)) < 7
        return grain + (20 if edge < 9 or brace else -16 if y % 32 < 2 else -1)
    if name == 'dl_teal':
        return grain + (-24 if y % 13 < 2 else 14 if y % 13 == 2 else 0) + (-7 if x % 42 < 2 else 0)
    if name in ('dl_stone', 'dl_base'):
        return grain + (-21 if y % 23 < 2 or (x + 31*(y//23)) % 62 < 2 else (x//16+y//23)%7 - 1)
    return grain + round(5 * math.sin(x*math.tau/64) * math.cos(y*math.tau/128))


def long_textures():
    for name, rgb in COLORS.items():
        size = SIZE
        width = size
        level = bytes(128 + texel(name, x, y) for y in range(size) for x in range(size))
        levels = [level]
        for _ in range(3):
            level = bytes(sum(level[y*width+x+i*width+j] for i in (0,1) for j in (0,1))//4
                          for y in range(0, width, 2) for x in range(0, width, 2))
            levels.append(level)
            width //= 2
        palette = bytes(max(0, min(255, chan + shift-128)) for shift in range(256) for chan in rgb)
        offsets = [40 + sum(map(len, levels[:i])) for i in range(4)]
        data = struct.pack('<16s6i', name.encode('ascii'), size, size, *offsets)
        yield name, 67, data + b''.join(levels) + struct.pack('<H', 256) + palette + b'\0\0'


def write_sky(folder: Path):
    """Original low-detail skybox; TGA BGR as accepted by the software renderer."""
    folder.mkdir(parents=True, exist_ok=True)
    size = 64
    header = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, size, size, 24, 32)
    for face in ('ft', 'bk', 'lf', 'rt', 'up', 'dn'):
        pixels = bytearray()
        for row in range(size):
            y = 0. if face == 'dn' else 1. if face == 'up' else 1. - row/(size-1)
            for _ in range(size):
                rgb = (round(177-92*y), round(201-50*y), round(213-13*y))
                pixels.extend(reversed(rgb))
        (folder / f'{SKY}{face}.tga').write_bytes(header + pixels)
