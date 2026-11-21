#!/usr/bin/env python3
"""Extrae la selección de prototipo sin hacer checkout ni copiarla a Git."""

import argparse
import gzip
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODELS = "packages/assets/public/models/"
SOURCES = {
    "cs2go": ("https://github.com/3kh0/cs2go.git", "7cce816747b11d6eb26b2f4ece8b68ccc740c5eb"),
    "multirig": (
        "https://github.com/goribby/Cyberpunk2077-MultiRig.git",
        "e028a5dadc9c215d46258aba57fb9da7d57556cd",
    ),
}
AGENTS = {"sas": "ctm-sas", "phoenix": "tm-phoenix"}
AGENT_CLIPS = ("idle", *(
    f"{motion}_{direction}_{stance}"
    for motion in ("crouch", "run", "walk")
    for direction in ("ne", "nw", "se", "sw")
    for stance in ("knife", "pistol", "rifle")
))
AK_CLIPS = ("idle", "draw", "shoot1", "reload", "lookat01")
USP_CLIPS = (*AK_CLIPS, "silencer_attach", "silencer_detach")
WEAPON_CLIPS = {"ak-47": AK_CLIPS, "usp-s": USP_CLIPS}
BAYONET_CLIPS = ("idle1", "idle2", "draw", "light_miss1", "light_miss2", "heavy_miss1", "lookat01", "lookat01_draw")
GODOT_WEAPON_CLIPS = {**WEAPON_CLIPS, "bayonet": BAYONET_CLIPS}
CS2GO_MODELS = (
    "maps/dust2.glb.gz",
    "maps/dust2-physics.glb.gz",
    "maps/dust2-overview.json",
    "maps/dust2-radar.png",
    "maps/dust2-nav.json",
    "maps/dust2-places.json",
    "agents/roster/ctm-sas.glb",
    "agents/roster/tm-phoenix.glb",
    "animations/locomotion/diagonal.glb",
    "animations/locomotion/source.json",
    "ak-47.glb",
    "usp-s.glb",
    "bayonet.glb",
    "bayonet.source.json",
    "animations/bayonet/source.json",
    *(f"animations/bayonet/{clip}.glb" for clip in BAYONET_CLIPS),
    *(
        path
        for weapon, clips in WEAPON_CLIPS.items()
        for path in (
            f"viewmodels/{weapon}.glb",
            *(f"viewmodels/{weapon}/{clip}.glb" for clip in clips),
        )
    ),
)
FILES = {
    "cs2go": [(MODELS + path, path.removesuffix(".gz")) for path in CS2GO_MODELS],
    "multirig": [("Cyberpunk_Rig.blend", "Cyberpunk_Rig.blend"), ("README.md", "README.md")],
}


def git(*args, stdout=None):
    subprocess.run(["git", *map(str, args)], stdout=stdout, check=True)


def inspect_glb(path):
    """Valida la cabecera y enumera requisitos de importación sin leer la malla."""
    with path.open("rb") as stream:
        header = stream.read(20)
        if len(header) != 20:
            raise ValueError(f"Cabecera GLB incompleta: {path}")
        magic, version, length, chunk_size, kind = struct.unpack("<4sIII4s", header)
        if (magic, version, length, kind) != (b"glTF", 2, path.stat().st_size, b"JSON"):
            raise ValueError(f"Cabecera GLB inválida: {path}")
        if chunk_size > length - 20:
            raise ValueError(f"Bloque JSON fuera de los límites: {path}")
        data = json.loads(stream.read(chunk_size))
    return {
        **{key: len(data.get(key, [])) for key in ("meshes", "skins", "animations", "images")},
        "extensionsUsed": data.get("extensionsUsed", []),
        "extensionsRequired": data.get("extensionsRequired", []),
        "externalUris": sorted({
            uri
            for item in data.get("buffers", []) + data.get("images", [])
            if (uri := item.get("uri")) and not uri.startswith("data:")
        }),
    }


def import_assets(output):
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Ya existe {output}. Elegí otro destino con --output.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".assets-", dir=output.parent) as tmp:
        work = Path(tmp)
        stage = work / "assets"
        report = {}
        for name, (url, revision) in SOURCES.items():
            repo = work / f"{name}.git"
            git("init", "--bare", "--quiet", repo)
            git("-C", repo, "remote", "add", "origin", url)
            git("-C", repo, "config", "remote.origin.promisor", "true")
            git("-C", repo, "config", "remote.origin.partialclonefilter", "blob:none")
            git("-C", repo, "fetch", "--quiet", "--depth=1", "--filter=blob:none", "origin", revision)
            entries = []
            for original, relative in FILES[name]:
                print(f"Extrayendo {name}/{relative}", flush=True)
                dst = stage / name / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                is_gzip = original.endswith(".gz")
                raw = work / "download.gz" if is_gzip else dst
                with raw.open("wb") as stream:
                    git("-C", repo, "show", f"{revision}:{original}", stdout=stream)
                if is_gzip:
                    with gzip.open(raw, "rb") as source, dst.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    raw.unlink()
                entries.append({
                    "source": original,
                    "file": f"{name}/{relative}",
                    "bytes": dst.stat().st_size,
                    **({"glb": inspect_glb(dst)} if dst.suffix == ".glb" else {}),
                })
            report[name] = {"repository": url, "revision": revision, "files": entries}
        (stage / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "third_party_assets", help="directorio nuevo de destino")
    args = parser.parse_args()
    try:
        import_assets(args.output.absolute())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"No se pudo completar la importación: {error}\n")
    print(f"Inventario: {args.output / 'inventory.json'}")


if __name__ == "__main__":
    main()
