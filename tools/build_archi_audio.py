#!/usr/bin/env python3
"""Stage Archi WAVs and translate MDL sequence sound events to Godot cues."""
import argparse
import hashlib
import json
import struct
import io
import subprocess
from pathlib import Path
import wave


WAVS = {
    'ak-47': ('ak47-1', 'ak47-2'), 'awp': ('awp1',), 'deagle': ('deagle-1', 'deagle-2'),
    'glock': ('glock18-1', 'glock18-2'), 'm4a4': ('m4a1_unsil-1', 'm4a1_unsil-2'),
    'usp-s': ('usp1', 'usp2'), 'usp-s-open': ('usp_unsil-1',),
    'm4a1-s': ('m4a1-1',), 'm4a1-s-open': ('m4a1_unsil-1', 'm4a1_unsil-2'),
    'aug': ('aug-1',), 'famas': ('famas-1', 'famas-2'), 'g3sg1': ('g3sg1-1',),
    'galil': ('galil-1', 'galil-2'), 'sg-553': ('sg552-1', 'sg552-2'),
    'ssg-08': ('scout_fire-1',), 'mac-10': ('mac10-1',), 'p90': ('p90-1',),
    'ump-45': ('ump45-1',), 'm249': ('m249-1',), 'xm1014': ('xm1014-1',),
    'dual-berettas': ('elite_fire',), 'five-seven': ('fiveseven-1',),
}
BANKS = {'ak-47': 'ak47', 'awp': 'awp', 'deagle': 'deagle', 'glock': 'glock18',
         'm4a4': 'm4a1s', 'm4a1-s': 'm4a1s', 'usp-s': 'usps',
         'aug': 'aug', 'famas': 'famas', 'g3sg1': 'g3sg1', 'galil': 'galilar', 'scar-20': 'scar20',
         'sg-553': 'sg553', 'ssg-08': 'ssg08', 'bizon': 'bizon', 'mac-10': 'mac10', 'mp5-sd': 'mp5sd',
         'mp7': 'mp7', 'mp9': 'mp9', 'p90': 'p90', 'ump-45': 'ump45', 'm249': 'm249', 'negev': 'negev',
         'mag-7': 'mag7', 'nova': 'nova', 'sawed-off': 'sawedoff', 'xm1014': 'xm1014',
         'cz75': 'p250', 'dual-berettas': 'elites', 'five-seven': 'fiveseven', 'p2000': 'p2000',
         'p250': 'p250', 'r8': 'revolver', 'tec-9': 'tec9', 'zeus': 'taser'}
FALLBACK_SHOTS = {'bizon': 'bizon-1', 'cz75': 'cz75a-1', 'mag-7': 'mag7-1', 'mp5-sd': 'mp5_01',
                  'mp7': 'mp7-1', 'mp9': 'mp9-1', 'negev': 'negev-1', 'nova': 'nova-1',
                  'p250': 'p250-1', 'p2000': 'hkp2000-1', 'r8': 'revolver-1_01', 'sawed-off': 'sawedoff-1',
                  'scar-20': 'scar20_01', 'tec-9': 'tec9-1'}
FALLBACK_BANKS = {'mag-7': 'mag7', 'tec-9': 'tec9', 'bizon': 'bizon', 'mp5-sd': 'mp5',
                  'scar-20': 'scar20', 'ssg-08': 'ssg08', 'g3sg1': 'g3sg1'}
CS2GO = '7cce816747b11d6eb26b2f4ece8b68ccc740c5eb'
TASER = '08f1bd6835d4f510d2ccaedeab6bb9f637b388ab'
SOURCE = '43b46172606a31759637c90378782390f374c1ee'


def effect_name(weapon, event):
    suffix = event.rsplit('.', 1)[-1].lower()
    if suffix.startswith('lookat') and suffix[6:].isdigit():
        return 'lookat_f' + suffix[6:]
    if weapon == 'dual-berettas':
        suffix = {'lclipin': 'leftclipin', 'rclipin': 'rightclipin', 'taunttap1': 'taunt_tap',
                  'taunttap2': 'taunt_tap', 'tauntstarttap': 'taunt_tap'}.get(suffix, suffix)
    if suffix == 'insertshell':
        return 'insertshell_01'
    if suffix == 'pumpduringshot':
        return 'pump'
    if weapon == 'm4a1-s':
        suffix = {'silencerscrewonstart': 'sil_screw_on_start', 'silencerscrewoffend': 'sil_screw_off_end'}.get(suffix, suffix)
        if suffix.startswith('silencerscrew'):
            suffix = 'sil_screw_' + suffix.removeprefix('silencerscrew')
        if event.startswith('Weapon_M4A1S.') and suffix in ('boltback', 'boltforward'):
            suffix = 'sil_' + suffix
    if weapon == 'usp-s':
        suffix = {'silencerscrewonstart': 'sil_screw_on_start'}.get(suffix, suffix)
        if suffix.startswith('silencerscrew'):
            suffix = 'sil_screw' + suffix.removeprefix('silencerscrew')
    return suffix


def build(root, output, fallback, legacy_manifest=None, cs2go=None, taser=None):
    audio = output/'audio'
    audio.mkdir(parents=True, exist_ok=True)
    samples, missing = {}, set()

    def copy_sample(source, name, directory=root, repo='ShadowNigth/archi', revision=SOURCE):
        destination = audio/(name+'.wav')
        raw = source.read_bytes()
        with wave.open(io.BytesIO(raw), 'rb') as sample:
            if sample.getsampwidth() not in (1, 2) or sample.getnchannels() not in (1, 2) or sample.getnframes() == 0:
                raise ValueError(f'WAV no compatible con Godot: {source}')
            if struct.unpack_from('<I', raw, 4)[0] + 8 > len(raw):
                # Repair the length of Archi's truncated Zeus WAV without
                # changing the available PCM samples.
                repaired = io.BytesIO()
                with wave.open(repaired, 'wb') as wav:
                    wav.setparams(sample.getparams())
                    wav.writeframes(sample.readframes(sample.getnframes()))
                destination.write_bytes(repaired.getvalue())
            else:
                destination.write_bytes(raw)
        samples[name] = {'path': source.relative_to(directory).as_posix(),
                         'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                         'source_sha256': hashlib.sha256(raw).hexdigest(), 'repository': repo, 'revision': revision}
        return name

    def cs2go_sample(file):
        if file in samples:
            return file
        if cs2go is None:
            return None
        path = f'packages/assets/public/audio/{file}.ogg'
        result = subprocess.run(['git', f'--git-dir={cs2go}', 'show', f'{CS2GO}:{path}'], capture_output=True)
        if result.returncode:
            return None
        import soundfile as sf
        signal, rate = sf.read(io.BytesIO(result.stdout), dtype='float32')
        destination = audio/(file+'.wav')
        sf.write(destination, signal, rate, subtype='PCM_16')
        samples[file] = {'path': path, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                         'repository': '3kh0/cs2go', 'revision': CS2GO}
        return file

    active = {p.name.removesuffix('-source-events.json') for p in output.glob('*-source-events.json')}
    shots = {k: [copy_sample(root/'sound'/(n+'.wav'), n) for n in names] for k, names in WAVS.items()
             if k.removesuffix('-open') in active}
    for weapon, sound in FALLBACK_SHOTS.items():
        if weapon in active:
            clip = cs2go_sample(sound)
            if not clip:
                raise ValueError(f'Muestra de disparo faltante: {weapon}/{sound}')
            shots[weapon] = [clip]
    if 'zeus' in active:
        if not taser:
            raise ValueError('Zeus necesita --taser-sounds para el disparo de CS:GO')
        for source in sorted(taser.glob('*.wav')):
            copy_sample(source, source.stem, directory=taser, repo='sourcesounds/csgo', revision=TASER)
        shots['zeus'] = ['taser_shoot']
        for source in root.rglob('taser_charging.wav'):
            copy_sample(source, 'taser_charging')
            break
    zoom = {}
    for weapon in ('awp', 'aug', 'g3sg1', 'scar-20', 'sg-553', 'ssg-08'):
        bank = BANKS[weapon]
        pair = {}
        for action in ('in', 'out'):
            source = root/f'sound/cs2_{bank}/zoom_{action}.wav'
            if not source.is_file() and (root/f'sound/cs2_{bank}/zoom.wav').is_file():
                source = root/f'sound/cs2_{bank}/zoom.wav'
            if source.is_file():
                pair[action] = copy_sample(source, f'{bank}_zoom_{action}')
            else:
                clip = cs2go_sample(f'{FALLBACK_BANKS.get(weapon, bank)}_zoom')
                if clip:
                    pair[action] = clip
        zoom[weapon] = pair
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
                name = f'{bank}_{file}'
                if bank and source.is_file():
                    if name not in samples:
                        copy_sample(source, name)
                elif name not in samples:
                    fallback_bank = FALLBACK_BANKS.get(weapon, bank)
                    aliases = {'pumpback': 'pump_back', 'pumpforward': 'pump_forward'}
                    name = cs2go_sample(f'{fallback_bank}_{aliases.get(file, file)}') if fallback_bank and not file.startswith('weaponmove') else None
                    if not name:
                        missing.add(event)
                        continue
                result.append([fraction, name, -12.0])
            if result:
                cues[f'{weapon}/{clip}'] = sorted(result)
    if 'r8' in active:
        for action, entries in {'draw': [(0, 'draw')], 'reload': [(0.07, 'sideback'), (.18, 'clipout'), (.5, 'clipin'), (.79, 'siderelease')]}.items():
            values = []
            for time, name in entries:
                cue = f'revolver_{name}'
                if cue not in samples:
                    copy_sample(root/f'sound/cs2_revolver/{name}.wav', cue)
                values.append([time, cue, -12.0])
            cues.setdefault(f'r8/{action}', values)
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
    print(f'{len(samples)} WAV ({sum(x["repository"] == "ShadowNigth/archi" for x in samples.values())} de Archi), '
          f'{len(cues)} secuencias con audio; {len(missing)} referencias no incluidas')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fallback-cues', type=Path, required=True)
    parser.add_argument('--legacy-manifest', type=Path)
    parser.add_argument('--cs2go-git', type=Path)
    parser.add_argument('--taser-sounds', type=Path)
    args = parser.parse_args()
    build(args.source, args.output, args.fallback_cues, args.legacy_manifest, args.cs2go_git, args.taser_sounds)


if __name__ == '__main__':
    main()
