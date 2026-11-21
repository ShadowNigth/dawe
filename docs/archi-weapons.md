# Arsenal de Archi y brazos de Cyberpunk en Godot

El proyecto y su complemento incluyen **24 primarias** (11 rifles, 7 subfusiles y 6 pesadas), **11 secundarias** (10 pistolas y Zeus x27) y **el kukri fijo**. La tienda agrupa las armas por tipo y desactiva las que no están instaladas. Las granadas (incluidas las variantes de humo) y el C4 que también aparecen en el repositorio fuente son equipo y no están integrados. No hay balística, daño, munición real ni multijugador.

Los modelos, texturas, iconos y secuencias proceden de [ShadowNigth/archi](https://github.com/ShadowNigth/archi/tree/43b46172606a31759637c90378782390f374c1ee). El brazo izquierdo Silverhand y el derecho proceden del Cyberpunk MultiRig usado en la revisión `cd4feb2` de Dawe. Los tres materiales de los brazos se guardan una sola vez en `cyberpunk-arms.vis`; cada arma mantiene su propio esqueleto, skin y clips. Las escopetas tubulares combinan sus secuencias originales de apertura, inserción y cierre; la XM1014 remuestrea segmentos con distintas tasas antes de unirlos. El nombre interno `bayonet` identifica el kukri.

**Audio:** se usan los WAV de Archi cuando están disponibles y se completan disparos y algunos eventos con cs2go y sourcesounds/csgo. El kukri conserva el audio de la versión anterior y el R8 usa marcas de recarga agregadas en Dawe porque sus secuencias no declaran cues. Las referencias sin audio resuelto se registran en `archi-weapon-pack.json`, junto a las rutas, revisiones y hashes de las muestras usadas. No se simulan efectos ausentes de impacto, munición o partículas. La disponibilidad de un recurso en GitHub no implica que tenga licencia de redistribución.

## Reconstruir el complemento

Necesitás Python 3.11+, `numpy`, `Pillow` y `soundfile`, el decodificador VTF precompilado de SourceIO (verificado en Linux x86‑64), y los recursos de presentación, mapa y agentes ya preparados en `godot/generated/`. Conservá los manifiestos de presentación originales antes de regenerar. Para recuperar la malla de brazos sin cambiar de rama y preparar las fuentes:

```sh
stage=third_party_assets/archi-build
mkdir -p "$stage" "$stage/compact" third_party_assets/taser

git clone https://github.com/ShadowNigth/archi.git third_party_assets/archi
git -C third_party_assets/archi checkout 43b46172606a31759637c90378782390f374c1ee
git clone https://github.com/REDxEYE/SourceIO.git third_party_assets/SourceIO
git -C third_party_assets/SourceIO checkout 7b179e354fd9e46822bb92fcd550895b752c1fc7
git clone --bare https://github.com/3kh0/cs2go.git third_party_assets/cs2go.git
git show cd4feb2:downloads/Dawe-Godot-Compra-Armas.zip > "$stage/cyberpunk.zip"
unzip -p "$stage/cyberpunk.zip" Dawe-Godot/godot/generated/deagle.glb > "$stage/silverhand.glb"
for sound in draw shoot; do
  gh api "repos/sourcesounds/csgo/contents/sound/weapons/taser/taser_${sound}.wav?ref=08f1bd6835d4f510d2ccaedeab6bb9f637b388ab" --jq .content \
    | base64 -d > "third_party_assets/taser/taser_${sound}.wav"
done

PYTHONPATH=third_party_assets python3 tools/build_archi_weapons.py \
  --source third_party_assets/archi --arms "$stage/silverhand.glb" --output "$stage"
python3 tools/build_archi_audio.py \
  --source third_party_assets/archi --output "$stage" \
  --fallback-cues godot/generated/weapon-sound-cues.json \
  --legacy-manifest godot/generated/presentation-sources.json \
  --cs2go-git third_party_assets/cs2go.git --taser-sounds third_party_assets/taser
python3 tools/share_archi_arms.py --source "$stage" --output "$stage/compact"
cp "$stage"/*.glb "$stage"/*.json "$stage"/buy-*.png "$stage"/*-drop.vis godot/generated/
cp "$stage"/compact/*.vis godot/generated/
cp "$stage"/audio/*.wav godot/generated/audio/
python3 tools/check_godot_assets.py --quality-viewmodels
python3 tools/package_archi_arsenal.py
```

Los GLB de las armas quedan disponibles en el taller para inspección y validación. El ZIP de juego distribuye los `.vis` compactos para no repetir las texturas y geometría de los brazos. `Dawe-Godot-Dust-II.zip` se genera por separado y no se modifica al empaquetar el arsenal.
