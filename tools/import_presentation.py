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

from import_assets import ROOT, SOURCES

AUDIO = (
    'ak47-1', 'ak47_boltpull', 'ak47_clipin', 'ak47_clipout', 'ak47_draw',
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


def extract(repo, output):
    url, revision = SOURCES['cs2go']
    output.mkdir(parents=True, exist_ok=True)
    (output/'audio').mkdir(exist_ok=True)
    targets = [(f'audio/{src}.ogg', f'audio/{Path(src).name}.wav') for src in AUDIO]
    targets += [(f'icons/team-{team}.png', f'team-{team}.png') for team in ('ct', 't')]
    manifest = {}
    for source, target in targets:
        data = subprocess.check_output(['git', '-C', str(repo), 'show', f'{revision}:packages/assets/public/{source}'])
        if source.endswith('.ogg'):
            mono, rate = audio_pcm(data)
            sf.write(output/target, mono, rate, subtype='PCM_16')
            if target == 'audio/usp1.wav':
                taps = np.hanning(25)
                muted = output/'audio/usp1-muted.wav'
                sf.write(muted, np.convolve(mono, taps/taps.sum(), mode='same')*.8, rate, subtype='PCM_16')
                manifest['audio/usp1-muted.wav'] = dict(source='Dawe: filtered usp1.ogg', sha256=hashlib.sha256(muted.read_bytes()).hexdigest())
        else:
            (output/target).write_bytes(data)
        manifest[target] = dict(source=f'packages/assets/public/{source}', source_sha256=hashlib.sha256(data).hexdigest(),
                                sha256=hashlib.sha256((output/target).read_bytes()).hexdigest())
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
