/* Shared server and prediction movement for the flat, local BSP course. */
#include <math.h>
#include <string.h>
#include "xash3d_types.h"
#include "const.h"
#include "q_client.h"
#include "pmove.h"
struct hull_s;
#include "pm_defs.h"
#include "play_move.h"

int Dawe_Hull(int index, float *mins, float *maxs)
{
    if (index < 0 || index > 2) return 0;
    float width = index == 2 ? 0.f : 16.f;
    float height = index == 0 ? DAWE_STAND_HALF : index == 1 ? DAWE_DUCK_HALF : 0.f;
    maxs[0] = maxs[1] = width;
    maxs[2] = height;
    for (int i = 0; i < 3; i++) mins[i] = -maxs[i];
    return 1;
}

static void set_stance(playermove_t *pm)
{
    int duck = (pm->cmd.buttons & IN_DUCK) != 0, previous = pm->usehull == 1;
    if (duck != previous) {
        int saved = pm->usehull;
        float target[3] = {pm->origin[0], pm->origin[1],
            pm->origin[2] + (duck ? DAWE_DUCK_HALF - DAWE_STAND_HALF : DAWE_STAND_HALF - DAWE_DUCK_HALF)};
        pm->usehull = duck;
        pmtrace_t test = pm->PM_PlayerTrace(target, target, PM_WORLD_ONLY, -1);
        if (!(test.startsolid || test.allsolid)) memcpy(pm->origin, target, sizeof(target));
        else pm->usehull = saved; // Keep crouched until there is room for the larger hull.
    }
    pm->view_ofs[2] = pm->usehull == 1 ? DAWE_DUCK_EYE : DAWE_STAND_EYE;
    if (pm->usehull == 1) pm->flags |= FL_DUCKING;
    else pm->flags &= ~FL_DUCKING;
}

void Dawe_Move(playermove_t *pm)
{
    pm->numtouch = 0;
    if (pm->dead || pm->spectator || pm->frametime <= 0.f) return;
    set_stance(pm);
    // This fixture is flat: the hull is swept at floor height, no gravity or steps.
    pm->onground = 0;
    pm->flags |= FL_ONGROUND;
    float f = pm->cmd.forwardmove, s = pm->cmd.sidemove;
    float length = hypotf(f, s);
    float speed = pm->usehull == 1 ? DAWE_DUCK_SPEED :
                  (pm->cmd.buttons & IN_RUN) ? DAWE_RUN_SPEED : DAWE_WALK_SPEED;
    float dt = pm->frametime;
    float yaw = pm->cmd.viewangles[1] * DAWE_RAD;
    float cy = cosf(yaw), sy = sinf(yaw);
    float factor = speed / fmaxf(length, DAWE_WALK_SPEED);
    float v[3] = {(cy*f + sy*s)*factor, (sy*f - cy*s)*factor, 0.f};
    float start[3];
    memcpy(start, pm->origin, sizeof(start));
    memcpy(pm->angles, pm->cmd.viewangles, sizeof(pm->angles));
    for (int bump = 0; bump < 3 && dt > 0.0001f && hypotf(v[0], v[1]) > .01f; bump++) {
        float end[3] = {pm->origin[0]+dt*v[0], pm->origin[1]+dt*v[1], pm->origin[2]};
        pmtrace_t hit = pm->PM_PlayerTrace(pm->origin, end, PM_WORLD_ONLY, -1);
        if (hit.startsolid || hit.allsolid) break;
        memcpy(pm->origin, hit.endpos, sizeof(end));
        if (hit.fraction >= 1.f) break;
        dt *= 1.f - hit.fraction;
        float inward = v[0]*hit.plane.normal[0] + v[1]*hit.plane.normal[1];
        if (inward >= -.001f) break;
        v[0] -= inward*hit.plane.normal[0];
        v[1] -= inward*hit.plane.normal[1];
    }
    for (int i = 0; i < 2; i++) pm->velocity[i] = (pm->origin[i] - start[i]) / pm->frametime;
    pm->velocity[2] = 0.f;
}
