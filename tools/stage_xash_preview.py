#!/usr/bin/env python3
"""Prepara una sala local para verificar armas o agentes en Xash3D (Linux)."""
import argparse
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from import_assets import AGENTS, AGENT_CLIPS, WEAPON_CLIPS
import dust2_long

ROOT = Path(__file__).resolve().parents[1]
GAME = 'dawe_preview'
WEAPONS = {'usp-s': ('usp', 'USP-S'), 'ak-47': ('ak47', 'AK-47')}
STATIC_MODEL = ROOT / 'third_party_assets/usp_idle_goldsrc/v_dawe_usp_idle.mdl'


def default_model(weapon):
    tag, _ = WEAPONS[weapon]
    model = ROOT / 'third_party_assets' / f'{tag}_goldsrc' / f'v_dawe_{tag}.mdl'
    return STATIC_MODEL if weapon == 'usp-s' and not model.is_file() else model


def write_wad(path, lumps):
    body = bytearray()
    directory = bytearray()
    for name, kind, data in lumps:
        directory += struct.pack('<iiiBBBB16s', 12 + len(body), len(data), len(data),
                                 kind, 0, 0, 0, name.encode('ascii'))
        body += data
    path.write_bytes(struct.pack('<4sii', b'WAD3', len(lumps), 12 + len(body)) + body + directory)


def mip_texture(name, colors):
    size = 64
    levels = [size >> i for i in range(4)]
    mips = [bytes((2 if x < max(1, n // 32) or y < max(1, n // 32) else
                   1 if (x >= n // 2) != (y >= n // 2) else 0)
                  for y in range(n) for x in range(n)) for n in levels]
    offsets = [40 + sum(len(level) for level in mips[:i]) for i in range(4)]
    palette = bytes(chan for color in colors for chan in color).ljust(256 * 3, b'\0')
    return (struct.pack('<16s6i', name.encode('ascii'), size, size, *offsets)
            + b''.join(mips) + struct.pack('<H', 256) + palette + b'\0\0')


def brush(x0, y0, z0, x1, y1, z1, texture):
    a, b, c, d = (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)
    e, f, g, h = (x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)
    # Vista desde fuera: VHLT espera los puntos en orden horario.
    faces = ((c, b, a), (f, g, h), (h, d, a), (f, b, c), (e, a, b), (g, c, d))
    return '{\n' + '\n'.join(
        ' '.join(f'( {x} {y} {z} )' for x, y, z in face) + f' {texture} 0 0 0 1 1'
        for face in faces) + '\n}'


def prepare_room(maps, tools, play=False, long_sector=False):
    colors = {
        'dawe_wall': ((100, 127, 139), (104, 131, 144), (71, 94, 111)),
        'dawe_floor': ((72, 81, 88), (76, 86, 92), (50, 57, 65)),
        'dawe_mark': ((200, 145, 65), (222, 166, 79), (115, 85, 58)),
    }
    map_path = maps / (dust2_long.MAP + '.map' if long_sector else 'dawe_room.map')
    blocks = [
        (-128, -128, -16, 192, 128, 0, 'dawe_floor'),
        (-128, -128, 144, 192, 128, 160, 'dawe_floor'),
        (-128, -128, 0, -112, 128, 144, 'dawe_wall'),
        (176, -128, 0, 192, 128, 144, 'dawe_wall'),
        (-112, -128, 0, 176, -112, 144, 'dawe_wall'),
        (-112, 112, 0, 176, 128, 144, 'dawe_wall'),
        (174, -40, 52, 176, 40, 56, 'dawe_mark'),
    ]
    entities = ['{\n"classname" "info_player_start"\n"origin" "-56 0 36"\n"angle" "0"\n}']
    entities += [f'{{\n"classname" "light"\n"origin" "{x} 0 112"\n"_light" "245 248 255 350"\n}}'
                 for x in (-62, 42, 138)]
    if play:
        # Flat local movement course: the central lintel admits only the duck hull.
        blocks = [
            (-336, -256, -16, 416, 256, 0, 'dawe_floor'),
            (-336, -256, 176, 416, 256, 192, 'dawe_floor'),
            (-336, -256, 0, -320, 256, 176, 'dawe_wall'),
            (400, -256, 0, 416, 256, 176, 'dawe_wall'),
            (-320, -256, 0, 400, -240, 176, 'dawe_wall'),
            (-320, 240, 0, 400, 256, 176, 'dawe_wall'),
            (-24, -48, 62, 56, 48, 99, 'dawe_mark'),
            (-24, -72, 0, 56, -48, 104, 'dawe_wall'),
            (-24, 48, 0, 56, 72, 104, 'dawe_wall'),
            (152, 64, 0, 208, 184, 96, 'dawe_mark'),
            (184, -176, 0, 264, -100, 96, 'dawe_mark'),
        ]
        entities = ['{\n"classname" "info_player_start"\n"origin" "-208 0 36"\n"angle" "0"\n}']
        entities.extend(f'{{\n"classname" "light"\n"origin" "{x} {y} 150"\n'
                        '"_light" "245 248 255 650"\n}'
                        for x in (-236, -86, 104, 284) for y in (-144, 0, 144))
    if long_sector:
        world, entities = dust2_long.long_layout(brush)
        textures = list(dust2_long.long_textures())
    else:
        world = [brush(*block) for block in blocks]
        textures = [(name, 67, mip_texture(name, rgb)) for name, rgb in colors.items()]
    write_wad(maps / 'dawe_test.wad', textures)
    map_path.write_text('\n'.join(['{', '"classname" "worldspawn"', '"wad" "dawe_test.wad"',
                                    *world, '}', *entities]) + '\n', encoding='ascii')
    for tool, args in [('hlcsg', ['-nowadtextures']), ('hlbsp', []), ('hlvis', []), ('hlrad', [])]:
        subprocess.run([str(tools / tool), *args, map_path.name], cwd=maps, check=True)
    bsp = map_path.with_suffix('.bsp')
    if not bsp.is_file() or bsp.read_bytes()[:4] != struct.pack('<I', 30):
        raise ValueError('No se generó un BSP GoldSrc v30')


def preview_sequences(model, weapon="usp-s"):
    return read_sequences(model, WEAPON_CLIPS[weapon], allow_idle_only=weapon == 'usp-s')


def read_sequences(model, expected, allow_idle_only=False):
    data = model.read_bytes()
    if len(data) < 244 or data[:8] != b'IDST\x0a\x00\x00\x00':
        raise ValueError(f'El modelo no es un MDL GoldSrc v10: {model}')
    count, offset = struct.unpack_from('<II', data, 164)
    stride = 176  # mstudioseqdesc_t (MDL v10)
    valid_counts = (1, len(expected)) if allow_idle_only else (len(expected),)
    if count not in valid_counts or offset < 244 or offset + stride * count > len(data):
        raise ValueError('Tabla de secuencias inválida para esta prueba')
    sequences = []
    for i in range(count):
        start = offset + i * stride
        label = data[start:start+32].split(b'\0', 1)[0].decode('ascii')
        fps, = struct.unpack_from('<f', data, start + 32)
        frames, = struct.unpack_from('<I', data, start + 56)
        if label != expected[i] or not math.isfinite(fps) or fps <= 0 or not frames:
            raise ValueError(f'Secuencia inesperada: {label}')
        sequences.append((label, (frames - 1) / fps))
    return sequences


def sequence_header(name, values):
    return ('static const struct { const char *name; float duration; } ' + name + '[] = {\n'
            + ''.join(f'    {{"{label}", {seconds:.7f}f}},\n' for label, seconds in values) + '};\n')


def play_delta(text):
    fields = {
        'clientdata_t': [*(f'velocity[{i}], DT_FLOAT | DT_SIGNED, 16, 8' for i in range(3)),
                         'flags, DT_INTEGER, 32, 1'],
        'entity_state_player_t': ['usehull, DT_INTEGER, 2, 1', 'movetype, DT_INTEGER, 4, 1',
                                  'onground, DT_INTEGER | DT_SIGNED, 12, 1'],
        'usercmd_t': ['viewangles[0], DT_ANGLE, 16, 1', 'viewangles[1], DT_ANGLE, 16, 1',
                      'forwardmove, DT_FLOAT | DT_SIGNED, 16, 8', 'sidemove, DT_FLOAT | DT_SIGNED, 16, 8',
                      'buttons, DT_SHORT, 16, 1'],
    }
    for table, entries in fields.items():
        header = f'\n{table} none\n{{\n'
        text = text.replace(header, header + ''.join(f'    DEFINE_DELTA({v}),\n' for v in entries))
    return text


def stage(sdk, vhlt, model, output, cc, weapon="usp-s", agents_dir=None, play=False, long_sector=False):
    if long_sector and not play:
        raise ValueError('--dust2-long requiere --play')
    map_name = dust2_long.MAP if long_sector else 'dawe_room'
    if play and agents_dir is None:
        raise ValueError('--play requiere --agents-dir')
    if agents_dir is not None:
        tag, title = ('play', 'Locomocion') if play else ('agents', 'SAS y Phoenix')
        if long_sector:
            title = 'Dust II - Puertas Largas'
        models = {f'dawe_{key}.mdl': agents_dir / key / f'dawe_{key}.mdl' for key in AGENTS}
        take_tables = [read_sequences(path, AGENT_CLIPS) for path in models.values()]
        if any(table != take_tables[0] for table in take_tables[1:]):
            raise ValueError('Los MDL de agentes no tienen la misma tabla de locomoción')
        model_name = ''
        sequences = [('idle', 0.)]
        agent_header = (f'#define DAWE_AGENTS {len(models)}\n'
                        f'#define DAWE_AGENT_CLIPS {len(AGENT_CLIPS)}\n'
                        'static const char *const agent_models[] = {\n'
                        + ''.join(f'    "models/{name}",\n' for name in models) + '};\n'
                        + sequence_header('agent_sequences', take_tables[0]))
    else:
        sequences = preview_sequences(model, weapon)
        tag, title = WEAPONS[weapon]
        model_name = f'v_dawe_{tag}.mdl'
        models = {model_name: model}
        agent_header = ''
    if not (sdk / '3rdparty/library_suffix/include/build.h').is_file():
        raise FileNotFoundError('Faltan los encabezados/submódulos del árbol fuente de Xash3D')
    for tool in ('hlcsg', 'hlbsp', 'hlvis', 'hlrad'):
        if not (vhlt / tool).is_file():
            raise FileNotFoundError(vhlt / tool)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Ya existe {output}. Elegí otro destino con --output.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.xash-preview-', dir=output.parent) as temp:
        staged = Path(temp) / 'base'
        mod = staged / GAME
        for folder in ('maps', 'models', 'cl_dlls', 'dlls'):
            (mod / folder).mkdir(parents=True)
        for name, path in models.items():
            shutil.copyfile(path, mod / 'models' / name)
        (mod / 'gameinfo.txt').write_text(f'''basedir "dawe_preview"
title "Dawe - Sala {title}"
startmap "{map_name}"
gamemode "singleplayer_only"
gamedll_linux "dlls/dawe.so"
dllpath "cl_dlls"
''', encoding='ascii')
        sources = ROOT / 'tools/xash_preview'
        delta = (sources / 'delta.lst').read_text(encoding='ascii')
        (mod / 'delta.lst').write_text(play_delta(delta) if play else delta, encoding='ascii')
        if play:
            shutil.copyfile(sources / 'play.cfg', mod / 'dawe_play.cfg')
        if long_sector:
            dust2_long.write_sky(mod / 'gfx/env')
        (mod / f'{GAME}.rc').write_text(('exec dawe_play.cfg\n' if play else '') + 'stuffcmds\n', encoding='ascii')
        # El motor exige que exista gfx.wad incluso en la pista sin HUD.
        write_wad(mod / 'gfx.wad', [('conchars', 68, bytes(128 * 128))])
        header = Path(temp) / 'dawe_sequences.h'
        header.write_text(f'#define DAWE_VIEWMODEL "models/{model_name}"\n'
                          f'#define DAWE_WEAPON_TAG "{tag}"\n'
                          f'#define DAWE_WEAPON_NAME "{title}"\n'
                          f'#define DAWE_NUM_SEQUENCES {len(sequences)}\n'
                          + sequence_header('sequences', sequences) + agent_header
                          + ('#define DAWE_PLAY 1\n' if play else '')
                          + (f'#define DAWE_LONG 1\n#define DAWE_START_X {dust2_long.START[0]}\n'
                             f'#define DAWE_START_Y {dust2_long.START[1]}\n'
                             f'#define DAWE_SKY "{dust2_long.SKY}"\n' if long_sector else ''), encoding='ascii')
        includes = [f'-I{header.parent}'] + [f'-I{sdk / path}' for path in ('engine', 'common', 'pm_shared', 'public',
                                                   '3rdparty/library_suffix/include')]
        for source, library in [('client.c', 'cl_dlls/client.so'), ('server.c', 'dlls/dawe.so')]:
            units = [str(sources / source)]
            if play:
                units.append(str(sources / 'play_move.c'))
                if source == 'client.c':
                    units.append(str(sources / 'play_client.c'))
            subprocess.run([cc, '-std=gnu11', '-Werror', '-fPIC', '-shared', *includes,
                            *units, '-o', str(mod / library), '-lm'], check=True)
        prepare_room(mod / 'maps', vhlt, play, long_sector)
        staged.rename(output)
    print(f'Sala: {output / GAME / "maps" / (map_name+".bsp")}')
    print(f'XASH3D_BASEDIR="{output}" xash3d -game {GAME} -clientlib cl_dlls/client.so '
          f'-dll dlls/dawe.so -ref soft -console -noip -nosound +map {map_name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xash-src', required=True, type=Path)
    parser.add_argument('--vhlt-bin', required=True, type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--weapon', choices=WEAPONS)
    group.add_argument('--agents-dir', type=Path, help='raíz de los MDL de SAS y Phoenix')
    parser.add_argument('--play', action='store_true', help='activa la pista de locomoción (requiere --agents-dir)')
    parser.add_argument('--dust2-long', action='store_true', help='usa el sector Puertas Largas (requiere --play)')
    parser.add_argument('--model', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'third_party_assets/xash_preview')
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    try:
        if args.agents_dir and args.model:
            parser.error('--model no se puede usar con --agents-dir')
        weapon = args.weapon or 'usp-s'
        model = None if args.agents_dir else (args.model or default_model(weapon)).resolve()
        stage(args.xash_src.resolve(), args.vhlt_bin.resolve(), model, args.output.resolve(),
              args.cc, weapon, args.agents_dir, args.play, args.dust2_long)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'No se pudo preparar la sala: {error}\n')


if __name__ == '__main__':
    main()
