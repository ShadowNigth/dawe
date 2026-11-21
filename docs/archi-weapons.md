# Armas de Archi en Godot

El ZIP de escritorio trae **USP-S, Glock-18, Desert Eagle, AK-47, M4A4, AWP y kukri** (ranura 3). El resto del arsenal del repositorio fuente no se agrega a la tienda. Los nombres internos de inventario permanecen estables; `bayonet` ahora identifica el kukri. Los modelos de primera persona, las texturas e iconos provienen de [ShadowNigth/archi](https://github.com/ShadowNigth/archi/tree/43b46172606a31759637c90378782390f374c1ee). Se convierten localmente, no se cargan en red durante el juego.

El conversor lee los `.mdl/.vvd/.vtx`, las claves incrustadas y los bloques `.ani`, las texturas VTF y los guantes Sport Vice con mangas de los SMD de `Sport_gloves`. Conserva las secuencias de origen y las variantes exportadas (también las de munición/impacto, aunque este prototipo no tiene esos sistemas). La recarga funciona con **R**, la inspección con **F** (alterna las dos de Deagle), y la USP-S pone o saca su silenciador con **clic derecho**. Los cambios de corredera de la USP-S y la Glock se hornean desde sus secuencias auxiliares. No se emula toda la máquina de estados, partículas ni mezclas del motor Source.

`archi-weapon-pack.json` registra las muestras realmente importadas con rutas y SHA‑256. La M4A4 usa las variantes `m4a1_unsil-*` de este banco y la USP-S abierta `usp_unsil-1.wav`. Archi no incluye WAV del kukri ni parte de los sonidos de manipulación que referencian sus MDL. El kukri conserva los sonidos anteriores de tajo y estocada; los demás eventos sin muestra quedan sin efecto asignado. El ambiente, los pasos y el salto no se reemplazan. Los activos del pack pertenecen a sus titulares; que sean accesibles en GitHub no otorga una licencia de redistribución.

## Reconstruir

Requiere Python 3.11+, `numpy` y `Pillow`, y una plataforma compatible con el decodificador VTF precompilado de [SourceIO](https://github.com/REDxEYE/SourceIO) (verificado en Linux x86‑64). SourceIO es una herramienta externa, no una dependencia de ejecución de Godot. En la raíz de Dawe, con `godot/generated/` ya preparado con el mapa, los agentes y la presentación del juego:

```sh
git clone https://github.com/ShadowNigth/archi.git third_party_assets/archi
git -C third_party_assets/archi checkout 43b46172606a31759637c90378782390f374c1ee
git clone https://github.com/REDxEYE/SourceIO.git third_party_assets/SourceIO
git -C third_party_assets/SourceIO checkout 7b179e354fd9e46822bb92fcd550895b752c1fc7
python3 -m pip install numpy Pillow
mkdir -p third_party_assets/archi-build
PYTHONPATH=third_party_assets python3 tools/build_archi_weapons.py \
  --source third_party_assets/archi --output third_party_assets/archi-build
python3 tools/build_archi_audio.py \
  --source third_party_assets/archi --output third_party_assets/archi-build \
  --fallback-cues godot/generated/weapon-sound-cues.json \
  --legacy-manifest godot/generated/presentation-sources.json
cp -R third_party_assets/archi-build/. godot/generated/
python3 tools/check_godot_assets.py --quality-viewmodels
```

Las mallas de arma caída se generan junto con los modelos de primera persona; los `.vis` equipados sirven a la vista web. Si estás reconstruyendo desde cero, `tools/import_presentation.py` prepara primero los sonidos que quedan como alternativa y los logos. Conservá una copia de sus `weapon-sound-cues.json` y `presentation-sources.json` si vas a regenerar varias veces.
