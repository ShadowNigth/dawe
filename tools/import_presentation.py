#!/usr/bin/env python3
"""Install logos, local audio and a short generated wind loop for the Godot demo."""
import argparse
import base64
import hashlib
import json
import io
import math
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import wave
from urllib.request import urlopen

import numpy as np
import soundfile as sf

from import_assets import ROOT, SOURCES, GODOT_WEAPON_CLIPS

AUDIO = (
    'ak47-1', 'ak47_boltpull', 'ak47_clipin', 'ak47_clipout', 'ak47_draw',
    'glock18-1', 'glock_draw', 'glock_clipout', 'glock_clipin', 'glock_slideback', 'glock_sliderelease',
    'deagle-1', 'de_draw', 'de_clipout', 'de_clipin', 'de_slideback', 'de_slideforward',
    'awp1', 'awp_draw', 'awp_clipout', 'awp_clipin', 'awp_boltback', 'awp_boltforward', 'zoom',
    'm4a1-1', 'm4a1_draw', 'm4a1_clipin', 'm4a1_clipout', 'm4a1_boltback', 'm4a1_boltforward',
    *(f'suppressor-1-silencerscrew{n}' for n in ('onstart', 1, 2, 3, 4, 5)),
    'usp1', 'usp_clipin', 'usp_clipout', 'usp_draw', 'usp_slideback', 'usp_sliderelease',
    *(f'source/{name}' for name in ('jump', 'land', 'gear-1', 'gear-2', 'gear-3', 'ui-confirm',
                                   'knife-deploy', 'knife-stab', 'knife-swing1', 'knife-swing2')),
    *(f'source/step-{ground}-{i}' for ground in ('concrete', 'sand') for i in range(1, 5)),
)


def wind_loop(path):
    # Circular, deterministic filtered noise. No external music or field recording.
    count, rate = 96000, 16000
    rng = random.Random(417)
    raw = [rng.uniform(-1, 1) for _ in range(count)]
    slow = sum(raw[-100:]) / 100
    values = bytearray()
    for i in range(count):
        slow += (raw[i] - raw[i-100]) / 100
        gust = .68 + .20 * math.sin(math.tau * i / count) + .09 * math.cos(3 * math.tau * i / count)
        sample = (slow * .8 + (raw[i] + raw[i-7] + raw[i-14]) * .012) * gust
        values.extend(struct.pack('<h', int(sample * 27000)))
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        out.writeframes(values)


def audio_pcm(data):
    points, rate = sf.read(io.BytesIO(data), dtype='float32', always_2d=True)
    mono = points.mean(axis=1)
    target = 22050
    if rate != target:
        # Short anti-alias window before interpolation, for FX playback.
        if rate > target:
            taps = np.hanning(15)
            mono = np.convolve(mono, taps / taps.sum(), mode='same')
        mono = np.interp(np.arange(round(len(mono)*target/rate))*rate/target, np.arange(len(mono)), mono)
    return mono, target


OPEN_USP_REV = '08f1bd6835d4f510d2ccaedeab6bb9f637b388ab'
OPEN_USP_HASHES = ('5c540332524856ac0935d18fdcb54b9552becc3705d8d1ee1bc5cdcd466a063f',
                   'fc96dc9651c0e27706d96ccf5b2b110d4d1d2e0a8883f279a3de67a37dcdf756',
                   '74014641c026966b4e2498c58ee79c6816803b4fa70eee74662cf9110edad96e')


def install_open_usp(output, manifest, local=None):
    """Use the original CS:GO unmounted USP-S samples, never a synthetic substitute."""
    for i, expected in enumerate(OPEN_USP_HASHES, 1):
        filename = f'usp_unsilenced_{i:02}.wav'
        origin = f'sound/weapons/usp/{filename}'
        if local:
            data = (local / filename).read_bytes()
        else:
            with urlopen(f'https://api.github.com/repos/sourcesounds/csgo/contents/{origin}?ref={OPEN_USP_REV}', timeout=20) as src:
                data = base64.b64decode(json.load(src)['content'])
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'Muestra de USP inesperada: {filename}')
        target = f'audio/usp-unsuppressed-{i:02}.wav'
        mono, rate = audio_pcm(data)
        sf.write(output/target, mono, rate, subtype='PCM_16')
        manifest[target] = dict(repository='https://github.com/sourcesounds/csgo', revision=OPEN_USP_REV,
                                source=origin, source_sha256=expected,
                                sha256=hashlib.sha256((output/target).read_bytes()).hexdigest())


def clip_cues(read):
    weapons = {'usp-s': 'usp', 'ak-47': 'ak47', 'm4a4': 'm4a1', 'glock': 'glock', 'deagle': 'de', 'awp': 'awp'}
    parts = {'draw', 'clipin', 'clipout', 'boltpull', 'boltback', 'boltforward', 'slideback', 'sliderelease', 'slideforward'}
    out = {}
    for weapon, clips in GODOT_WEAPON_CLIPS.items():
        for clip in clips:
            if clip.startswith('idle') or (clip == 'shoot1' and weapon != 'awp'):
                continue
            section = 'animations' if weapon == 'bayonet' else 'viewmodels'
            data = read(f'models/{section}/{weapon}/{clip}.glb')
            size, = struct.unpack_from('<I', data, 12)
            events = json.loads(data[20:20+size])['animations'][0].get('extras', {}).get('events', [])
            cues = []
            for event in events:
                name = event.get('m_name', '')
                kind = name.split('.')[-1]
                sample = None
                if weapon in weapons and kind in parts and name.split('.')[0] in (f'weapon_{weapons[weapon]}', 'weapon_galilar', 'weapon_deagle'):
                    sample = f'{weapons[weapon]}_{kind}'
                elif weapon == 'usp-s' and kind.startswith('silencerscrew'):
                    sample = 'suppressor-1-' + kind
                elif name.startswith('weapon.weaponmove'):
                    sample = 'gear-' + name[-1]
                elif name == 'weapon_knife.draw.large':
                    sample = 'knife-deploy'
                elif name == 'weapon_knife.swish.light':
                    sample = 'knife-swing2' if clip.endswith('2') else 'knife-swing1'
                elif name == 'weapon_knife.swish.heavy':
                    sample = 'knife-stab'
                elif name in ('inspect.gear.ultrasmall', 'inspect.gear.small', 'weapon_knife.draw.gear'):
                    sample = 'gear-1'
                if sample:
                    time = round(event['m_flStartTime']['m_flValue'], 6)
                    level = -23.0 if sample.startswith('gear-') else -13.0
                    cues.append([time, sample, level])
            if cues:
                out[f'{weapon}/{clip}'] = sorted(cues, key=lambda cue: cue[0])
    return out


def extract(repo, output, usp_dir=None):
    url, revision = SOURCES['cs2go']
    output.mkdir(parents=True, exist_ok=True)
    (output/'audio').mkdir(exist_ok=True)
    def read(relative):
        return subprocess.check_output(['git', '-C', str(repo), '-c', 'gc.auto=0', 'show',
                                        f'{revision}:packages/assets/public/{relative}'])

    targets = [(f'audio/{src}.ogg', f'audio/{Path(src).name}.wav') for src in AUDIO]
    targets += [(f'icons/team-{team}.png', f'team-{team}.png') for team in ('ct', 't')]
    targets += [(f"icons/{id}.png", f"buy-{id}.png") for id in GODOT_WEAPON_CLIPS if id != "bayonet"]
    manifest = {}
    for source, target in targets:
        data = read(source)
        if source.endswith('.ogg'):
            mono, rate = audio_pcm(data)
            sf.write(output/target, mono, rate, subtype='PCM_16')
        else:
            (output/target).write_bytes(data)
        manifest[target] = dict(source=f'packages/assets/public/{source}', source_sha256=hashlib.sha256(data).hexdigest(),
                                sha256=hashlib.sha256((output/target).read_bytes()).hexdigest())
    install_open_usp(output, manifest, usp_dir)
    cue_file = output/'weapon-sound-cues.json'
    cues = clip_cues(read)
    for entries in cues.values():
        for _, sample, _ in entries:
            if f'audio/{sample}.wav' not in manifest:
                raise ValueError(f'Cue has no installed sample: {sample}')
    cue_file.write_text(json.dumps(cues, indent=2)+'\n')
    manifest[cue_file.name] = dict(source='cs2go: normalized sound events from viewmodel GLB animation extras',
                                   sha256=hashlib.sha256(cue_file.read_bytes()).hexdigest())
    wind = output/'audio/desert-wind.wav'
    wind_loop(wind)
    manifest['audio/desert-wind.wav'] = dict(source='Dawe: generated wind', sha256=hashlib.sha256(wind.read_bytes()).hexdigest())
    (output/'presentation-sources.json').write_text(json.dumps(dict(repository=url, revision=revision, files=manifest), indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, help='existing cs2go checkout or bare repository')
    p.add_argument('--output', type=Path, default=ROOT/'godot/generated')
    p.add_argument('--usp-dir', type=Path, help='local directory containing the pinned original USP WAVs')
    args = p.parse_args()
    if args.repo:
        extract(args.repo, args.output, args.usp_dir)
    else:
        url, revision = SOURCES['cs2go']
        with tempfile.TemporaryDirectory(prefix='dawe-presentation-') as temp:
            subprocess.run(['git','init','--bare','-q',temp], check=True)
            subprocess.run(['git','-C',temp,'remote','add','origin',url], check=True)
            subprocess.run(['git','-C',temp,'config','remote.origin.promisor','true'], check=True)
            subprocess.run(['git','-C',temp,'fetch','--depth=1','--filter=blob:none','origin',revision], check=True)
            extract(temp, args.output, args.usp_dir)


if __name__ == '__main__':
    main()
