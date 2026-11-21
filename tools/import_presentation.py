#!/usr/bin/env python3
"""Install logos, local audio and a short generated wind loop for the Godot demo."""
import argparse
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

import numpy as np
import soundfile as sf

from import_assets import ROOT, SOURCES, GODOT_WEAPON_CLIPS

AUDIO = (
    'ak47-1', 'ak47_boltpull', 'ak47_clipin', 'ak47_clipout', 'ak47_draw',
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


def unsuppressed_shot(path):
    # This source pack only ships Weapon_USP.SilencedShot. Create a distinct
    # fallback for the open muzzle instead of filtering/down-pitching that clip.
    rng = np.random.default_rng(223)
    rate = 22050
    t = np.arange(int(.42*rate))/rate
    noise = rng.uniform(-1, 1, t.size)
    body = .48*np.sin(2*np.pi*(195*t - 130*t*t))*np.exp(-37*t)
    boom = (.50*noise + .28*np.convolve(noise, np.ones(5)/5, mode='same'))*np.exp(-27*t)
    crack = .68*(noise - np.r_[0., noise[:-1]])*np.exp(-230*t)
    sharp = (1-np.exp(-5700*t))*(body+boom+crack)
    for delay, gain in ((.019, .17), (.052, .11), (.091, .06)):
        frames = round(delay*rate)
        sharp[frames:] += sharp[:-frames]*gain
    sf.write(path, np.tanh(sharp*1.4)*.93, rate, subtype='PCM_16')


def clip_cues(read):
    weapons = {'usp-s': 'usp', 'ak-47': 'ak47', 'm4a4': 'm4a1'}
    parts = {'draw', 'clipin', 'clipout', 'boltpull', 'boltback', 'boltforward', 'slideback', 'sliderelease'}
    out = {}
    for weapon, clips in GODOT_WEAPON_CLIPS.items():
        for clip in clips:
            if clip.startswith('idle') or clip == 'shoot1':
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
                if weapon in weapons and kind in parts and name.split('.')[0] in (f'weapon_{weapons[weapon]}', 'weapon_galilar'):
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


def extract(repo, output):
    url, revision = SOURCES['cs2go']
    output.mkdir(parents=True, exist_ok=True)
    (output/'audio').mkdir(exist_ok=True)
    def read(relative):
        return subprocess.check_output(['git', '-C', str(repo), '-c', 'gc.auto=0', 'show',
                                        f'{revision}:packages/assets/public/{relative}'])

    targets = [(f'audio/{src}.ogg', f'audio/{Path(src).name}.wav') for src in AUDIO]
    targets += [(f'icons/team-{team}.png', f'team-{team}.png') for team in ('ct', 't')]
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
    unsuppressed = output/'audio/usp-unsuppressed.wav'
    unsuppressed_shot(unsuppressed)
    manifest['audio/usp-unsuppressed.wav'] = dict(source='Dawe: synthesized open muzzle (fallback)',
                                                 sha256=hashlib.sha256(unsuppressed.read_bytes()).hexdigest())
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
    args = p.parse_args()
    if args.repo:
        extract(args.repo, args.output)
    else:
        url, revision = SOURCES['cs2go']
        with tempfile.TemporaryDirectory(prefix='dawe-presentation-') as temp:
            subprocess.run(['git','init','--bare','-q',temp], check=True)
            subprocess.run(['git','-C',temp,'remote','add','origin',url], check=True)
            subprocess.run(['git','-C',temp,'config','remote.origin.promisor','true'], check=True)
            subprocess.run(['git','-C',temp,'fetch','--depth=1','--filter=blob:none','origin',revision], check=True)
            extract(temp, args.output)


if __name__ == '__main__':
    main()
