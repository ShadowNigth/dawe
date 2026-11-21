# Dawe — prototipo para Xash3D FWGS

La **USP-S** y la **AK-47** ya tienen modelos de primera persona compilados y probados en Xash3D FWGS, con antebrazos y manos del MultiRig. También podés recorrer una **pista local con SAS o Phoenix** y probar los ciclos de locomoción diagonal de cs2go con cámara en tercera persona. También está disponible una **reconstrucción parcial de Puertas Largas de Dust II** como BSP independiente. El prototipo no tiene combate.

## Probar el modelo dentro de Xash3D

La sala tiene una cámara fija sin movimiento ni disparos. El servidor local precarga el MDL y lo asigna como modelo de primera persona; lo dibuja el renderizador de Xash3D. No se necesita una instalación de Half-Life ni de CS. Para recrear la prueba en Linux hacen falta Python 3.9+, un compilador C, el árbol fuente de [Xash3D FWGS](https://github.com/FWGS/xash3d-fwgs/tree/11ed246c885d710ca1682370c66ee6594ac2d25a) con sus submódulos, el ejecutable y los datos de esa misma versión (incluidos `extras.pk3` y el renderizador `soft`), y los binarios de [VHLT](https://github.com/FreeSlave/vhlt/tree/13b83f91d093ef146a9a78834578994d85f99d96).

Con el MDL ya compilado según la sección siguiente:

```sh
python3 tools/stage_xash_preview.py --xash-src /ruta/xash3d-fwgs --vhlt-bin /ruta/vhlt/bin
XASH3D_BASEDIR="$PWD/third_party_assets/xash_preview" \
XASH3D_EXTRAS_PAK1=/ruta/xash3d/extras.pk3 \
  /ruta/xash3d/xash3d -game dawe_preview -clientlib cl_dlls/client.so \
  -dll dlls/dawe.so -ref soft -console -noip -nosound +map dawe_room
```

Si tu instalación no encuentra la biblioteca del menú, indicá su ruta con `-menulib /ruta/xash3d/libmenu.so`. El script compila un BSP v30 con texturas propias, dos bibliotecas locales de prueba y copia el modelo al directorio del juego. Para repetir el armado, usá un destino nuevo con `--output` y ajustá `XASH3D_BASEDIR`.

En la consola del juego, `dawe_anim reload` reproduce la recarga y vuelve al reposo. También podés pasar `idle`, `draw`, `shoot1`, `lookat01` y, para la USP-S, `silencer_attach` y `silencer_detach`. El disparo en esta sala sólo reproduce la animación.

Para la comprobación automática, agregá `-dawe-animate -windowed -width 960 -height 540` antes de `+map`: Xash3D recorre las secuencias con movimiento del modelo elegido, deja capturas en `dawe_preview/scrshots/` y se cierra. Alternativamente, `-dawe-capture` guarda dos imágenes de reposo con el modelo activado y desactivado. En el sandbox se usaron `SDL_VIDEODRIVER=dummy` y `SDL_AUDIODRIVER=dummy`. Las advertencias sobre sprites y sonidos de Half-Life no afectan esta prueba.

## Compilar los modelos animados

Después de extraer los recursos (ver abajo), ejecutar desde la raíz con Blender 4.5 o posterior y un `studiomdl` de GoldSrc, como [studiomdlPlusPlus](https://github.com/G2Pavon/studiomdlPlusPlus/tree/8929f89d6ec6fddb84aed541db00f8178a7f86c4):

```sh
blender --background --python-exit-code 1 --python tools/build_viewmodel.py
cd third_party_assets/usp_goldsrc
studiomdl usp.qc  # o el nombre del binario que hayas instalado
```

El exportador activa **ambas pistas del GLB** (manos y piezas del arma), las muestrea a 30 fps y las transfiere a un esqueleto reducido con pesos rígidos. La escala animada del silenciador se convierte en eventos que cambian su grupo de cuerpo (`bodygroup`), porque el MDL clásico no guarda escalas por hueso. Un cliente distinto debe implementar el evento 5001 para alternar ese grupo. Para la USP-S, el resultado es `v_dawe_usp.mdl` (GoldSrc v10, 41 huesos):

| Secuencia | Fotogramas | Qué muestra |
| --- | ---: | --- |
| `idle` | 1 | Reposo (el clip original es una pose fija) |
| `draw` | 30 | Desenfunde |
| `shoot1` | 12 | Disparo |
| `reload` | 65 | Recarga y movimiento del cargador |
| `lookat01` | 193 | Inspección |
| `silencer_attach` | 146 | Montaje del silenciador |
| `silencer_detach` | 146 | Desmontaje del silenciador |

La sala toma la **USP-S** por defecto si está compilada. Con la **AK-47**, `dawe_anim` ofrece los cinco clips disponibles; no hay secuencias de silenciador. Sigue disponible el exportador de la prueba fija, `tools/build_usp_idle.py`, y se puede seleccionar su MDL con `stage_xash_preview.py --model RUTA`. Los modelos no reemplazan directamente sus equivalentes de CS 1.6: el orden de secuencias y los eventos son propios de Dawe. El destino del exportador debe ser nuevo; para elegir otro, agregá `-- --output RUTA` al comando de Blender.

### AK-47

```sh
blender --background --python-exit-code 1 --python tools/build_viewmodel.py -- --weapon ak-47
(cd third_party_assets/ak47_goldsrc && studiomdl ak47.qc)
python3 tools/stage_xash_preview.py --weapon ak-47 --xash-src /ruta/xash3d-fwgs \
  --vhlt-bin /ruta/vhlt/bin --output third_party_assets/xash_ak47
```

Para abrir la sala de la AK-47 usá el mismo comando de Xash3D de arriba con `XASH3D_BASEDIR="$PWD/third_party_assets/xash_ak47"`. El MDL GoldSrc v10 resultante, `v_dawe_ak47.mdl`, trae 42 huesos (incluidos dos auxiliares para las uniones de las muñecas) y 264 fotogramas a 30 fps: `idle` (1), `draw` (30), `shoot1` (23), `reload` (73) y `lookat01` (137). La recarga incluye el movimiento del cargador y el disparo el del cerrojo; ambos se toman de la pista del arma. Si las pistas terminan con un fotograma de diferencia, se mantiene la última pose de la pista más corta sin estirarla.

## Compilar y probar a SAS y Phoenix

El exportador de agentes no necesita Blender. Requiere Node.js con npm, Python con NumPy y Pillow, [Basis Universal](https://github.com/BinomialLLC/basis_universal) (`basisu`, v1.16+ con soporte KTX2) y el mismo `studiomdl` indicado arriba. Después de extraer los recursos:

```sh
npm ci --prefix tools/agent_assets
python3 -m pip install numpy Pillow  # dentro de tu entorno virtual
python3 tools/build_agents.py --basisu /ruta/basisu
(cd third_party_assets/agents_goldsrc/sas && studiomdl sas.qc)
(cd third_party_assets/agents_goldsrc/phoenix && studiomdl phoenix.qc)
python3 tools/stage_xash_preview.py --agents-dir third_party_assets/agents_goldsrc \
  --xash-src /ruta/xash3d-fwgs --vhlt-bin /ruta/vhlt/bin --output third_party_assets/xash_agents
```

Abrí la sala con el comando de Xash3D de arriba, cambiando `XASH3D_BASEDIR` a `"$PWD/third_party_assets/xash_agents"`. En la consola, **`dawe_agent walk_ne_pistol`** cambia la secuencia de ambos agentes; `dawe_agent` sin argumentos lista los nombres. El argumento `-dawe-agents-capture` genera capturas de la pose de referencia y de tres ciclos representativos en `dawe_preview/scrshots/`, y después sale.

Cada MDL tiene **36 secuencias en bucle** a 30 fps: caminata (`walk`), carrera (`run`) y desplazamiento agachado (`crouch`), en cuatro diagonales (`ne`, `nw`, `se`, `sw`) y con tres poses de manos (`knife`, `pistol`, `rifle`). `idle` es la pose de referencia del esqueleto, no un clip de reposo del juego. Se conservan las mallas de cuerpo y guantes; Meshopt se decodifica, las texturas base se reducen a BMP indexado y cada vértice se liga al hueso de mayor peso para el MDL clásico. El resultado puede mostrar pliegues en articulaciones. En la sala de exhibición, los ciclos se ven **en el lugar**, sin armas acopladas ni control de movimiento.

## Recorrer la pista en tercera persona

Con los dos MDL anteriores listos, generá una instancia separada de la sala:

```sh
python3 tools/stage_xash_preview.py --play --agents-dir third_party_assets/agents_goldsrc \
  --xash-src /ruta/xash3d-fwgs --vhlt-bin /ruta/vhlt/bin --output third_party_assets/xash_play
```

Usá el comando de apertura de Xash3D de arriba con `XASH3D_BASEDIR="$PWD/third_party_assets/xash_play"`. Dentro del mapa:

- **WASD** mueve al personaje con relación a la cámara. **Shift** corre; **Ctrl** agacha. Probá pasar por debajo del travesaño amarillo: de pie bloquea el paso, y si soltás Ctrl debajo no podés levantarte hasta salir.
- **Mouse** para orbitar; **←/→** también giran la cámara. La cámara se acerca al personaje cuando se cruza con el escenario.
- **1/2** cambia de SAS a Phoenix sin reiniciar. También podés usar `dawe_player sas` o `dawe_player phoenix`.

La velocidad y dirección **resultantes** (no sólo las teclas) eligen el ciclo y su ritmo. Para las direcciones cardinales se reutiliza la diagonal vecina; al parar se mantiene una pose fija, pues el banco no trae un reposo animado. La física local usa una pista plana con colisiones BSP, deslizamiento por paredes y dos cajas de colisión, de pie y agachado. No hay salto, armas, enemigos, ni multijugador.

Para repetir la prueba automática, agregá `-dawe-play-test -windowed -width 960 -height 540` antes de `+map` y guardá la salida en un log. `python3 tools/check_play_trace.py LOG` valida el recorrido, los cambios de animación y el movimiento desde la nueva orientación de la cámara. La prueba guarda capturas en `dawe_preview/scrshots/`; podés repetirla con `+cl_nopred 1` para verificar el recorrido usando sólo el estado recibido del servidor local.

## Recorrer Puertas Largas de Dust II

Con los dos modelos de agente compilados, agregá `--dust2-long` al modo de recorrido:

```sh
python3 tools/stage_xash_preview.py --play --dust2-long \
  --agents-dir third_party_assets/agents_goldsrc --xash-src /ruta/xash3d-fwgs \
  --vhlt-bin /ruta/vhlt/bin --output third_party_assets/xash_long
```

Usá el comando de apertura de arriba con `XASH3D_BASEDIR="$PWD/third_party_assets/xash_long"` y `+map dawe_long`. Ambos agentes y los controles son los mismos que en la pista. El sector incluye el patio exterior, los dos arcos de Puertas Largas y el giro hacia Larga. Es un recorte de piso plano construido con brushes y materiales propios, no un port completo de Dust II. El [replanteo y la prueba](dust2-long.md) detallan qué se trasladó de los recursos originales.

## Extraer los recursos de prueba

Con Git y Python 3.9 o posterior, desde la raíz del proyecto:

```sh
python3 tools/import_assets.py
```

El importador extrae archivos seleccionados de revisiones fijas; no hace checkout de los repos completos. El destino por defecto es `third_party_assets/` (unos 117 MiB extraídos, fuera de Git). Si ya existe, se puede indicar un directorio nuevo con `--output`. Si lo extrajiste antes de este cambio, volvé a importar en una carpeta nueva para obtener los clips que falten. Usá `--assets RUTA` con `build_agents.py`, o `-- --assets RUTA` con Blender. `inventory.json` registra las rutas de origen, los tamaños y las extensiones glTF de cada GLB.

| Recurso | Archivo local (dentro de `third_party_assets/`) |
| --- | --- |
| Dust II: geometría visual, malla física y radar | `cs2go/maps/dust2.glb`, `dust2-physics.glb`, `dust2-overview.json`, `dust2-radar.png` |
| Dust II: navegación y zonas de referencia | `cs2go/maps/dust2-nav.json` y `dust2-places.json` |
| Agentes con esqueleto, sin clips embebidos | `cs2go/agents/roster/ctm-sas.glb` y `tm-phoenix.glb` |
| Locomoción de agentes (36 clips y procedencia) | `cs2go/animations/locomotion/diagonal.glb` y `source.json` |
| AK-47 y USP-S de mundo, sin texturas embebidas | `cs2go/ak-47.glb` y `usp-s.glb` |
| Armas de primera persona | `cs2go/viewmodels/ak-47.glb` y `usp-s.glb`; la USP-S incluye siete clips y la AK-47 cinco; ambos están portados |
| MultiRig de Cyberpunk 2077 | `multirig/Cyberpunk_Rig.blend` (Blender 4.0) |

## Camino a Xash3D

- **Mapa:** Dust II no es un BSP. El GLB visual requiere decodificar Meshopt y texturas Basis/KTX2; el GLB físico requiere Meshopt. Para Puertas Largas se reconstruyó un sector cerrado con brushes en un `.map` a partir de la referencia física y de navegación. Queda continuar con los sectores adyacentes y sus desniveles; no sirve renombrar el GLB o convertir cada triángulo en un brush.
- **Agentes:** ya están compilados como MDL de tercera persona para la sala. La pista local conecta las secuencias con el desplazamiento, la dirección y la postura. Para convertirlos en jugadores de una partida todavía faltan las hitboxes de combate y la integración con el resto del juego.
- **Armas y brazos:** usar el modelo de primera persona (con texturas WebP embebidas) para construir el `v_*.mdl`; el de mundo sirve como base para `w_*.mdl`, pero su material no trae imágenes. Los clips de cs2go separan la animación de manos de la de piezas del arma. Hay que sincronizarlas, no aplicar ambas pistas al mismo esqueleto sin distinguir sus huesos.

### MultiRig: adaptación de los brazos

El `.blend` contiene el armature `Rig` (149 huesos, incluidos controles IK y auxiliares), mallas de dedos ligadas al armature y variantes de brazos. Se puede usar **como rig de autoría en Blender**; Xash3D no ejecuta sus controles IK. Los nombres y las jerarquías no coinciden con los clips de cs2go. Primer mapeo anatómico, a comprobar en pose antes de hornear:

| cs2go | MultiRig izquierdo | MultiRig derecho |
| --- | --- | --- |
| `arm_upper_L` / `arm_upper_R` | `LeftArm` | `RightArm` |
| `arm_lower_L` / `arm_lower_R` | `LeftForeArm` | `RightForeArm` |
| `hand_L` / `hand_R` | `LeftHand` | `RightHand` |
| `finger_index_0_L` / `finger_index_0_R` | `LeftHandIndex1` | `RightHandIndex1` |

La versión animada usa los antebrazos y manos estándar y transfiere las direcciones de brazo, muñeca y falanges sin exportar el IK. Se verificó en el renderizador software de Xash3D que la recarga mueve el cargador, que cada clip cambia la pose y que los eventos cambian la visibilidad del silenciador. El ajuste fino del contacto de los dedos queda pendiente; con pesos rígidos pueden verse pliegues bruscos en manos y muñecas.

## Permisos

Los recursos se mantienen fuera de Git. El radar de Dust II identifica a Valve como autor; no se verificaron permisos para redistribuir los recursos de cs2go. El `readme` interno del MultiRig acredita el rig a Goribby y las mallas/texturas a CD Projekt Red, y excluye el uso comercial. Eso no equivale a permiso de redistribución de los recursos originales. Antes de publicar un build con ellos, verificar los permisos aplicables o reemplazarlos por recursos propios o con licencia compatible.
