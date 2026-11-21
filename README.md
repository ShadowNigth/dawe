# Dawe — prototipo de shooter en Godot 4

**Godot es el motor principal del proyecto.** La escena de arranque está en [`godot/project.godot`](godot/project.godot). El prototipo tiene movimiento local, primera y tercera persona, SAS y Phoenix, y los modelos de primera persona de USP-S y AK-47. Los modelos de arma reproducen animaciones; todavía no hay balística, daño, bots ni multijugador.

## Descargar el proyecto con los activos incluidos

**[Descargar Dawe para Godot con modelos y texturas (.zip)](downloads/Dawe-Godot-MultiRig-con-activos.zip?raw=true)**

El ZIP contiene el proyecto y los activos preparados de Dust II, SAS, Phoenix, y las versiones mejoradas de la USP-S y la AK-47 con los brazos del MultiRig. Extraé todo, abrí `godot/project.godot` con Godot 4.5 o posterior, esperá a que se importen los recursos y presioná **F5**. No hace falta ejecutar los scripts de importación para usar el ZIP.

## Abrir el proyecto

Abrí `godot/project.godot` con **Godot 4.5 o posterior** y presioná **F6** desde `main.tscn` o **F5** desde el proyecto. Sin importar recursos de terceros, funciona la pista local con figuras de reemplazo: un patio, un paso angosto y una rampa que permite probar el movimiento y la cámara.

| Control | Acción |
| --- | --- |
| WASD / ratón | Mover / mirar |
| Shift / Ctrl / Espacio | Correr / agacharse / saltar |
| 1 / 2 | SAS / Phoenix |
| 3 / 4 | USP-S / AK-47 |
| V | Alternar entre primera y tercera persona |
| Clic izquierdo / R / F | Animación de disparo / recarga / inspección |
| T | Quitar o colocar el silenciador con la USP-S equipada. Si estás en tercera persona, cambia a primera para mostrar la animación. |
| Tab / Retroceso / Escape | Mostrar radar con posición y rumbo / volver al inicio / liberar el ratón |

## Instalar los activos locales

Para reconstruir los activos preparados que incluye el ZIP, el importador descarga las **revisiones fijadas** de cs2go y MultiRig y deja un inventario con sus SHA-256. Revisá las [notas de procedencia y licencias](docs/godot-migration.md#procedencia-y-límites-de-uso) antes de compartir cualquier derivado.

Desde la raíz, con **Python 3.10+**, Node.js y [Basis Universal](https://github.com/BinomialLLC/basis_universal) (`basisu` 1.16+ con KTX2):

```sh
python3 tools/import_assets.py             # omitilo si ya tenés el inventario actualizado
npm ci --prefix tools/agent_assets
python3 -m pip install numpy Pillow         # en tu entorno virtual
python3 tools/build_godot_assets.py --basisu /ruta/basisu
```

Esto genera `godot/generated/` con la **malla de Dust II**, su **colisión independiente**, radar y navegación de referencia. El nivel arranca frente a **Puertas Largas**. También genera **SAS y Phoenix**, cada uno con la pose base y los **36 ciclos** disponibles. Si `godot/generated/` ya existe, el generador no lo pisa: conservá una copia y armá uno nuevo, o elegí otro destino con `--output`.

Para sumar los modelos de primera persona, con **Blender 4.5+**:

```sh
for weapon in usp-s ak-47; do
  blender --background --python-exit-code 1 --python tools/build_godot_viewmodel.py -- \
    --weapon "$weapon" --output "third_party_assets/${weapon}_bake"
  python3 tools/port_godot_viewmodel.py --weapon "$weapon" \
    --smd "third_party_assets/${weapon}_bake"
done
```

Se hornea el MultiRig con la geometría original de brazos y arma, hasta cuatro pesos por vértice y mapas de color, normales y rugosidad/metalizado del arma, **sin compilar MDL ni BSP**. Cada arma entra como GLB con su esqueleto y el conjunto de clips disponible: **7 para USP-S**, incluido montar/desmontar el silenciador, y **5 para AK-47**. Abrí o volvé a importar el proyecto y dejá terminar la importación de Godot antes de ejecutarlo. Para forzar la pista local aun con Dust II instalado: `godot --path godot -- --training`.

## Vista texturizada de Puertas Largas

La demo de Arena muestra un recorte de la **malla visual texturizada** de Dust II sobre la colisión real. Arranca con SAS: `2` cambia a Phoenix, `V` muestra los brazos y el arma en primera persona, y `3` / `4` equipan la USP-S y la AK-47. Los materiales y las animaciones se generan de los GLB preparados arriba; están incluidos en el ZIP de `downloads/`. El archivo automático de fuentes de GitHub es distinto.

Para reproducir ese recorte en Godot, después de generar `dust2.glb` y los cuatro GLB de agentes y armas:

```sh
python3 tools/build_godot_preview.py
godot --path godot -- --visual-preview
```

El generador crea paquetes `.vis` en `godot/generated/`, que el juego también puede leer sin importar los GLB en el editor. Conservan la malla, las texturas, los esqueletos y los clips de esta demo, incluidos los mapas de normales, metalizado, rugosidad y oclusión de las armas. Fuera del recorte texturizado, el mapa sigue en modo de diagnóstico; el arranque habitual usa el Dust II visual completo cuando su GLB ya fue importado.

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
godot --headless --path godot --script res://tests/smoke.gd -- --require-preview
godot --headless --path godot --script res://tests/dust2_route.gd -- --collision-preview
```

La prueba de la pista comprueba paredes, rampas, agachado, salto, aterrizaje y que la cámara se retraiga al rozar una esquina. `dust2_route.gd` usa el mismo controlador e input de movimiento que el jugador en la malla física: no teletransporta entre puntos. La prueba con activos comprueba el punto inicial de Dust II, que se cargue la geometría de colisión, los materiales, los bancos de animación, el cambio de pose de los huesos y la visibilidad del silenciador antes y después de los dos eventos, y el estado al cambiar de cámara y de arma. `--require-preview` comprueba además el recorte texturizado de la demo.

## Más información

- [Decisiones de la migración y trabajo pendiente](docs/godot-migration.md)
- [Guía histórica de Xash3D](docs/xash3d.md) y [reconstrucción BSP de Puertas Largas](docs/dust2-long.md). No son dependencias del proyecto Godot.
