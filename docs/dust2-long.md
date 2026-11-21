# Puertas Largas: recorte BSP de Dust II

## Referencia y decisiones

Se usaron los recursos `dust2-physics.glb`, `dust2-nav.json` y `dust2-places.json` de la revisión fijada de cs2go. En planta se cruzaron las paredes del export físico con los polígonos navegables y las zonas *Outside Long*, *Long Doors* y *Long A*. Los nombres y las medidas del recorte se tomaron de esa referencia, no de un supuesto BSP original de CS 1.6.

Para replantear a mano en unidades GoldSrc se tomó como origen el punto aproximado `(x, z) = (16.5, -8)` en los metros del GLB. El norte queda hacia `+X` y el este hacia `-Y` en la reconstrucción:

```text
X = (-z_glb - 8) / 0.0254
Y = (16.5 - x_glb) / 0.0254
```

| Rasgo | Referencia en planta | Reconstrucción |
| --- | --- | --- |
| Patio exterior | Aproximación ancha desde el sur y el oeste | Patio al sur; el jugador aparece en `X=-240, Y=0` mirando a los arcos |
| Puertas Largas | Paso angosto entre `x≈13.6–19.3 m`, desde `z≈−7.5 m` hasta `−19.4 m` | Corredor de unas 224 unidades de ancho, con dos arcos separados por 450 unidades y dos pares de hojas fijas entreabiertas |
| Salida a Larga | Justo detrás del arco norte se puede doblar hacia el este | Recodo a la derecha, tramo exterior y pared sólida al final del recorte |

`tools/dust2_long.py` contiene la geometría editable. Se usan volúmenes cerrados y prismas convexos para las hojas diagonales y los segmentos de los arcos. El piso es plano; se preservan el patio, el estrechamiento y el giro, no las pendientes ni los desniveles originales. No se reconstruyeron el foso, el sitio A ni las conexiones con el resto de Dust II. Las puertas no tienen bisagras animadas; sus hojas sí son sólidas.

El WAD, el cielo y la iluminación son propios del prototipo. El BSP no requiere los GLB durante la ejecución; ni sus texturas ni su malla se incrustan. La herramienta de preparación genera el `.map`, el `.bsp`, los recursos y las bibliotecas del modo local. El `.bsp` solo no sustituye un mapa de CS 1.6.

## Comprobación reproducible

Generar el escenario con `--play --dust2-long` (ver la [guía de Xash3D](xash3d.md)). Lanzar el mapa `dawe_long` con `-dawe-long-test` y guardar la salida. La rutina dirige a SAS desde el patio, atraviesa los dos pares de puertas, gira hacia Larga, cambia a Phoenix y avanza hasta la pared de cierre. Para comprobar el resultado usando sólo el estado del servidor local, agregar `+cl_nopred 1`.

```sh
python3 tools/check_play_trace.py --dust2-long LOG
```

Las capturas `scrshots/long_*.png` muestran el recorrido real renderizado por Xash3D. El modo de prueba sale por sí solo; sin la opción de prueba se controla normalmente con WASD, Shift, Ctrl, mouse y los selectores de agente.
