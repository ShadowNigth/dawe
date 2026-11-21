#!/usr/bin/env python3
"""Build the standalone game and optional full-arsenal ZIP from generated assets."""
import argparse
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from archi_catalog import EXTRA_MODELS

ROOT = Path(__file__).resolve().parents[1]
BASE = {'ak-47', 'awp', 'bayonet', 'deagle', 'glock', 'm4a4', 'usp-s'}
LIMIT = 100 * 1024 * 1024


def write_zip(path, inventory):
    temporary = path.with_suffix('.tmp')
    try:
        hashes = {}
        with ZipFile(temporary, 'w', ZIP_DEFLATED, compresslevel=6) as out:
            for name, source in sorted(inventory.items()):
                name = 'Dawe-Godot/' + name
                data = source.read_bytes()
                hashes[name] = sha256(data).digest()
                out.writestr(name, data)
        if temporary.stat().st_size >= LIMIT:
            raise ValueError(f'{path.name} supera el límite de GitHub')
        with ZipFile(temporary) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist()) == hashes.keys()
            assert all(sha256(archive.read(name)).digest() == digest for name, digest in hashes.items())
        temporary.replace(path)
        print(path.name, len(hashes), path.stat().st_size, sha256(path.read_bytes()).hexdigest())
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=ROOT/'godot/generated')
    parser.add_argument('--output', type=Path, default=ROOT/'downloads')
    args = parser.parse_args()
    game = {p.relative_to(ROOT).as_posix(): p for pattern in ('godot/scripts/*', 'godot/tests/*', 'godot/*.tscn',
             'godot/*.godot', 'docs/*.md', 'README.md', 'tools/*.py') for p in ROOT.glob(pattern) if p.is_file()}
    extra = {}

    def asset(target, name):
        target['godot/generated/'+name] = args.assets/name

    for name in ('sas.glb', 'phoenix.glb', 'team-ct.png', 'team-t.png', 'cyberpunk-arms.vis',
                 'usp-s.json', 'archi-weapon-pack.json', 'weapon-sound-cues.json', 'presentation-sources.json'):
        asset(game, name)
    asset(extra, 'm4a1-s.json')
    # Include the original event references so the coverage in the manifests
    # can be audited without the Source assets.
    for names, target in ((BASE, game), (EXTRA_MODELS, extra)):
        for name in names:
            asset(target, name+'.vis')
            asset(target, name+'-source-events.json')
            if name != 'bayonet':
                asset(target, name+'-drop.vis')
                asset(target, 'buy-'+name+'.png')
    for path in (args.assets/'audio').glob('*.wav'):
        asset(game, 'audio/'+path.name)
    args.output.mkdir(parents=True, exist_ok=True)
    write_zip(args.output/'Dawe-Godot-Compra-Armas.zip', game)
    write_zip(args.output/'Dawe-Godot-Arsenal-Archi.zip', extra)


if __name__ == '__main__':
    main()
