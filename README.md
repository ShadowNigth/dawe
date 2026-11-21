# Dawe — prototipo de shooter en Godot 4

**Godot es el motor principal del proyecto.** La escena de arranque está en [`godot/project.godot`](godot/project.godot). El prototipo tiene movimiento local, primera y tercera persona, SAS y Phoenix, y los modelos de primera persona de USP-S, Glock-18, Desert Eagle, AK-47, M4A4, AWP y kukri del [pack Archi](docs/archi-weapons.md). Los modelos de arma reproducen animaciones; todavía no hay balística, daño, bots ni multijugador.

## Descargar el proyecto con los activos incluidos

1. **[Proyecto, armas, agentes y sonidos (.zip)](downloads/Dawe-Godot-Compra-Armas.zip?raw=true)**
2. **[Mapa completo de Dust II (.zip)](downloads/Dawe-Godot-Dust-II.zip?raw=true)**

Extraé **ambos ZIP en el mismo lugar** para que compartan la carpeta `Dawe-Godot`. Abrí `Dawe-Godot/godot/project.godot` con Godot 4.5 o posterior, esperá a que termine la importación y presioná **F5**. El primer ZIP también funciona solo en la pista local. No hace falta correr los scripts de importación para jugar.

## Abrir el proyecto

Abrí `godot/project.godot` con **Godot 4.5 o posterior** y presioná **F6** desde `main.tscn` o **F5** desde el proyecto. Sin importar recursos de terceros, funciona la pista local con figuras de reemplazo: un patio, un paso angosto y una rampa que permite probar el movimiento y la cámara.

| Control | Acción |
| --- | --- |
| WASD / ratón | Correr / mirar |
| Shift / Ctrl / Espacio | Caminar / agacharse / saltar |
| M | Abrir el selector de equipos con logos (CT/SAS o T/Phoenix); se abre también al iniciar |
| B | Abrir o cerrar la tienda de práctica. Elegí una primaria y una secundaria |
| 1 / 2 / 3 / rueda | Primaria / secundaria / kukri fijo / recorrer armas disponibles |
| G / E | Soltar el arma equipada / recoger y equipar la más cercana al alcance |
| V | Alternar entre primera y tercera persona |
| Clic izquierdo / R / F | Disparo o tajo con el kukri / recarga / inspección (la Deagle alterna las dos inspecciones de Archi) |
| Clic derecho | Silenciador USP-S (también T) / mira AWP (dos aumentos) / estocada con el kukri |
| Tab / Retroceso / Escape | Mostrar radar con posición y rumbo / volver al inicio / liberar el ratón |

## Movimiento, escalones y audio

- SAS y Phoenix muestran despegue, descenso y aterrizaje en tercera persona. Las poses se generan para las tres posturas de arma y no empujan el cuerpo físico.
- El movimiento usa velocidades por arma, aceleración, fricción, salto y límite de dirección en el aire de referencia de CS2. WASD corre por defecto; Shift camina y Ctrl agacha. El salto no se repite al mantener Espacio. El prototipo conserva la cápsula y el ascenso de escalones de hasta 34 cm de Godot para el mapa; no replica subtick ni predicción online.
- Las seis armas usan el audio de Archi: disparos, desenfundes, recargas, correderas, cerrojo de AWP y rosca de USP-S, según las muestras que contiene el pack. El disparo de la USP-S cambia con el silenciador. Se conservan los sonidos anteriores del cuchillo y del ambiente: Archi no incluye los WAV del kukri.
- Los modelos conservan las poses del pack de origen. Los guantes Sport Vice se ligan al rig de cada arma; las mangas y los dedos se ajustan para que no se separen durante los gestos.

## Instalar los activos locales

Para reconstruir los activos preparados que incluye el ZIP, el importador descarga las **revisiones fijadas** de cs2go y MultiRig y deja un inventario con sus SHA-256. Revisá las [notas de procedencia y licencias](docs/godot-migration.md#procedencia-y-límites-de-uso) antes de compartir cualquier derivado.

Desde la raíz, con **Python 3.10+**, Node.js y [Basis Universal](https://github.com/BinomialLLC/basis_universal) (`basisu` 1.16+ con KTX2):

```sh
python3 tools/import_assets.py             # omitilo si ya tenés el inventario actualizado
npm ci --prefix tools/agent_assets
python3 -m pip install numpy Pillow soundfile         # en tu entorno virtual
python3 tools/build_godot_assets.py --basisu /ruta/basisu
```

Esto genera `godot/generated/` con la **malla de Dust II**, su **colisión independiente**, radar y navegación de referencia. El nivel arranca frente a **Puertas Largas**. También genera **SAS y Phoenix**, cada uno con la pose base y los **36 ciclos** disponibles. Si `godot/generated/` ya existe, el generador no lo pisa: conservá una copia y armá uno nuevo, o elegí otro destino con `--output`.

Para reconstruir los modelos, animaciones, iconos y WAV de primera persona activos, seguí la [guía de conversión de Archi](docs/archi-weapons.md). No hacen falta Blender ni Source para ejecutar el ZIP ya preparado. Para forzar la pista local aun con Dust II instalado: `godot --path godot -- --training`.

## Vista texturizada de Puertas Largas

La demo de Arena usa un recorte texturizado de Dust II sobre la colisión real. `B` abre la tienda de práctica (sin saldo ni restricciones de equipo), `1` selecciona la primaria, `2` la secundaria y `3` el kukri. `G` tira el arma de fuego; `E` recoge o intercambia por la que encuentre cerca. El kukri siempre queda en su ranura. El ZIP de escritorio incluye modelos GLB y las mallas de suelo `.vis`; el recorte web se genera aparte. El archivo automático de fuentes de GitHub es distinto.

Para reproducir el recorte, después de generar `dust2.glb`, los agentes y las armas:

```sh
python3 tools/build_godot_preview.py
godot --path godot -- --visual-preview
```

El generador crea paquetes `.vis` en `godot/generated/`, que el juego también puede leer sin importar los GLB en el editor. Conservan la malla, las texturas, los esqueletos y los clips de esta demo, incluidos los mapas de normales disponibles y los parámetros de metalizado y rugosidad de las armas. Fuera del recorte texturizado, el mapa sigue en modo de diagnóstico; el arranque habitual usa el Dust II visual completo cuando su GLB ya fue importado.

## Recorrer Puertas Largas con la colisión real

El modo de diagnóstico muestra **la misma geometría física que usa el controlador**, sin depender de importar las texturas, los agentes ni el modelo visual en el editor. Usa una malla simplificada en apariencia, no en colisión. La preparación normal ya genera el archivo; si tenés un `godot/generated/` de la versión anterior:

```sh
python3 tools/build_dust2_collision.py
# Abrir en el patio de Puertas Largas, con radar en Tab.
godot --path godot -- --collision-preview
```

El recorrido verificado pasa por las dos puertas, rodea Larga hasta la bajada, entra al foso, vuelve por la pendiente y sigue hasta la rampa de A. Se puede caminar todo ese trayecto sin saltar. Esto no reemplaza la importación visual completa descrita arriba.

## Pruebas

```sh
# Verificar el paquete generado sin abrir el editor
python3 tools/check_godot_assets.py --quality-viewmodels

# Importar una vez y ejecutar las pruebas con Godot desde la terminal
# (usar godot4 en lugar de godot si así se llama tu ejecutable)
godot --headless --path godot --import
godot --headless --path godot --script res://tests/smoke.gd -- --training
godot --headless --path godot --script res://tests/smoke.gd -- --require-assets
# Después de ejecutar tools/build_godot_preview.py:
godot --headless --path godot --script res://tests/smoke.gd -- --require-preview
godot --headless --path godot --script res://tests/dust2_route.gd -- --collision-preview
```

La prueba de la pista comprueba paredes, rampas, agachado con transición de cámara, salto, frenado, control aéreo, velocidad por arma, contra-strafe y que el salto requiere contacto con el suelo. También verifica cinco escalones, un salto a una repisa de 94 cm y que la cámara se retraiga al rozar una esquina. La prueba de Dust II recorre además la escalera real de Corta en ambas direcciones. `dust2_route.gd` usa el mismo controlador e input de movimiento que el jugador en la malla física: no teletransporta entre puntos. La prueba con activos comprueba el punto inicial de Dust II, que se cargue la geometría de colisión, los materiales, los bancos de animación, el cambio de pose de los huesos durante recarga y retroceso, la rueda para cambiar de arma y la visibilidad del silenciador antes y después de sus eventos. También verifica los logos y el bloqueo del menú, las ranuras 1/2/3, las muestras de disparo de la USP-S, la mira y el cerrojo de AWP, las marcas de recarga y el ciclo de tirar y recuperar la USP-S con su estado de silenciador. `--require-preview` comprueba además el recorte texturizado de la demo.

## Más información

- [Decisiones de la migración y trabajo pendiente](docs/godot-migration.md)
- [Guía histórica de Xash3D](docs/xash3d.md) y [reconstrucción BSP de Puertas Largas](docs/dust2-long.md). No son dependencias del proyecto Godot.
