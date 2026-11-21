#!/usr/bin/env python3
"""Stage Archi WAVs and translate MDL sequence sound events to Godot cues."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import wave


WAVS = {
    'ak-47': ('ak47-1', 'ak47-2'), 'awp': ('awp1',), 'deagle': ('deagle-1', 'deagle-2'),
    'glock': ('glock18-1', 'glock18-2'), 'm4a4': ('m4a1_unsil-1', 'm4a1_unsil-2'),
    'usp-s': ('usp1', 'usp2'), 'usp-s-open': ('usp_unsil-1',),
}
BANKS = {'ak-47': 'ak47', 'awp': 'awp', 'deagle': 'deagle', 'glock': 'glock18',
         'm4a4': 'm4a1s', 'usp-s': 'usps'}
SOURCE = '43b46172606a31759637c90378782390f374c1ee'


def effect_name(weapon, event):
    suffix = event.rsplit('.', 1)[-1].lower()
    if suffix.startswith('lookat') and suffix[6:].isdigit():
        return 'lookat_f' + suffix[6:]
    if weapon == 'usp-s':
        suffix = {'silencerscrewonstart': 'sil_screw_on_start'}.get(suffix, suffix)
        if suffix.startswith('silencerscrew'):
            suffix = 'sil_screw' + suffix.removeprefix('silencerscrew')
    return suffix


def build(root, output, fallback, legacy_manifest=None):
    audio = output/'audio'
    audio.mkdir(parents=True, exist_ok=True)
    samples, missing = {}, set()

    def copy_sample(source, name):
        destination = audio/(name+'.wav')
        with wave.open(str(source), 'rb') as sample:
            if sample.getsampwidth() not in (1, 2) or sample.getnchannels() not in (1, 2) or sample.getnframes() == 0:
                raise ValueError(f'WAV no compatible con Godot: {source}')
        shutil.copyfile(source, destination)
        samples[name] = {'path': source.relative_to(root).as_posix(), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        return name

    shots = {k: [copy_sample(root/'sound'/(n+'.wav'), n) for n in names] for k, names in WAVS.items()}
    zoom = {action: copy_sample(root/f'sound/cs2_awp/zoom_{action}.wav', f'awp_zoom_{action}') for action in ('in', 'out')}
    cues = {}
    variants = {}
    for path in sorted(output.glob('*-source-events.json')):
        weapon = path.name.removesuffix('-source-events.json')
        bank = BANKS.get(weapon)
        events = json.loads(path.read_text())
        variants[weapon] = sorted(events)
        for clip, entries in events.items():
            result = []
            for fraction, event in entries:
                file = effect_name(weapon, event)
                source = root/f'sound/cs2_{bank}/{file}.wav'
                if not bank or not source.is_file():
                    missing.add(event)
                    continue
                name = f'{bank}_{file}'
                if name not in samples:
                    copy_sample(source, name)
                result.append([fraction, name, -12.0])
            if result:
                cues[f'{weapon}/{clip}'] = sorted(result)
    # Archi references base-game knife sounds but does not contain a single
    # kukri/knife WAV. Keep the game's existing knife sounds for those actions.
    original = json.loads(fallback.read_text())
    for clip, events in original.items():
        if clip.startswith('bayonet/') and events:
            cues.setdefault(clip, events)
    (output/'weapon-sound-cues.json').write_text(json.dumps(cues, indent=2)+'\n')
    (output/'archi-weapon-pack.json').write_text(json.dumps({
        'repository': 'ShadowNigth/archi', 'revision': SOURCE, 'shots': shots, 'zoom': zoom,
        'samples': samples, 'source_sequences': variants, 'unavailable_source_sounds': sorted(missing),
    }, indent=2)+'\n')
    if legacy_manifest:
        original = json.loads(legacy_manifest.read_text())
        for name in samples:
            original['files'].pop(f'audio/{name}.wav', None)
        original['files'].pop('weapon-sound-cues.json', None)
        (output/'presentation-sources.json').write_text(json.dumps(original, indent=2)+'\n')
    print(f'{len(samples)} WAV de Archi, {len(cues)} secuencias con audio; {len(missing)} referencias ausentes del pack')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fallback-cues', type=Path, required=True)
    parser.add_argument('--legacy-manifest', type=Path)
    args = parser.parse_args()
    build(args.source, args.output, args.fallback_cues, args.legacy_manifest)


if __name__ == '__main__':
    main()
