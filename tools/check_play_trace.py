#!/usr/bin/env python3
"""Comprueba un log de Xash3D obtenido con -dawe-play-test."""
import argparse
from pathlib import Path
import re

LINE = re.compile(r'Dawe play (\w+) x=([-\d.]+) y=([-\d.]+) z=([-\d.]+) speed=([\d.]+) '
                  r'duck=([01]) clip=(\w+) agent=(\w+) yaw=([-\d.]+)')
ROOM_STEPS = ('spawn', 'walk', 'run', 'blocked', 'under', 'held', 'exit', 'diagonal', 'stop', 'turned', 'advance')

LONG_STEPS = ('patio', 'approach', 'door_south', 'passage', 'door_north', 'junction', 'east',
              'long_lane', 'end_wall', 'stop')


def long_checks(points):
    patio, approach, south, hall, north, junction, east, lane, wall, stop = points
    return {
        'salida desde el patio': abs(patio[0] + 240) < 1 and -190 < approach[0] < 0,
        'primer arco': 45 < south[0] < 200 and abs(south[1]) < 2,
        'corredor entre los arcos': 230 < hall[0] < 400 and 180 < hall[3] < 234
                                   and hall[5] == 'run_ne_pistol',
        'salida por el segundo arco': 450 < north[0] < 550 and abs(north[1]) < 2,
        'llegada al recodo': 565 < junction[0] < 672 and abs(east[0] - junction[0]) < 12,
        'giro y avance lateral por Larga': abs(lane[0] - east[0]) < 12 and -440 < lane[1] < -230
                                         and abs(lane[7] + 90) < 2 and lane[6] == 'Phoenix',
        'cierre sólido del recorte': -618 < wall[1] < -614 and wall[3] < 2 and stop[3] < 2
                                     and abs(stop[1] - wall[1]) < 1,
        'todo el recorrido queda sobre el piso': all(35 < s[2] < 38 and s[4] == 0 for s in points),
    }


def check(path, long_sector=False):
    log = path.read_text(encoding='utf-8', errors='replace')
    samples = LINE.findall(log)
    if tuple(s[0] for s in samples) != (LONG_STEPS if long_sector else ROOM_STEPS):
        raise ValueError('Faltan pasos o están fuera de orden en la prueba de locomoción')
    points = [
        (float(x), float(y), float(z), float(speed), int(duck), clip, agent, float(yaw))
        for _, x, y, z, speed, duck, clip, agent, yaw in samples
    ]
    checks = long_checks(points) if long_sector else room_checks(points)
    failed = [label for label, ok in checks.items() if not ok]
    if failed:
        raise ValueError('Falló: ' + ', '.join(failed))
    print(f'{path}: {len(checks)} puntos de control verificados')


def room_checks(points):
    spawn, walk, run, blocked, under, held, exit_, diagonal, stop, turned, advance = points
    return {
        'punto inicial': abs(spawn[0] + 208) < 1 and spawn[4] == 0,
        'caminata': walk[0] > spawn[0] + 35 and 100 < walk[3] < 120 and walk[5] == 'walk_ne_pistol',
        'carrera': run[0] > walk[0] + 40 and 205 < run[3] < 230 and run[5] == 'run_ne_pistol',
        'colisión de pie': -41 < blocked[0] < -39 and blocked[3] < 2 and blocked[4] == 0,
        'paso bajo el dintel': -8 < under[0] < 56 and 17 < under[2] < 20 and under[4] == 1
                               and 70 < under[3] < 82 and under[5] == 'crouch_ne_pistol',
        'no se levanta bajo el obstáculo': abs(held[0] - under[0]) < 8 and held[4] == 1 and held[3] < 2,
        'se levanta al salir': exit_[0] > 90 and 35 < exit_[2] < 38 and exit_[4] == 0,
        'diagonal normalizada y recambio de agente': diagonal[0] < exit_[0] - 19 and diagonal[1] > 19
            and 100 < diagonal[3] < 120 and diagonal[5:7] == ('walk_sw_pistol', 'Phoenix'),
        'se detiene al soltar': stop[3] < 2 and abs(stop[0] - diagonal[0]) < 8 and abs(stop[1] - diagonal[1]) < 8,
        'giro de cámara': turned[3] < 2 and 65 < turned[7] < 115,
        'avance relativo a la cámara': advance[1] > turned[1] + 29 and abs(advance[0] - turned[0]) < 18
                                       and 100 < advance[3] < 120,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dust2-long', action='store_true', help='validar el recorrido de Puertas Largas')
    p.add_argument('log', type=Path, nargs='+')
    args = p.parse_args()
    try:
        for path in args.log:
            check(path, args.dust2_long)
    except (OSError, ValueError) as exc:
        p.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
