/* Third-person presentation and input for the standalone movement course. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "xash3d_types.h"
#include "const.h"
#include "cdll_int.h"
#include "entity_types.h"
#include "cl_entity.h"
#include "event_api.h"
#include "q_client.h"
#include "pmove.h"
struct hull_s;
#include "pm_defs.h"
#include "ref_params.h"
#include "dawe_sequences.h"
#include "play_move.h"
#include "play_client.h"

static cl_enginefunc_t *eng;
static cl_entity_t avatar;
static int controls, selected, ready, crouched, sequence, test, test_step, test_shots;
static float phase, speed, test_start, now, view_yaw, worldpos[3];
static const char *const player_names[] = {"SAS", "Phoenix"};
enum { FWD = 1, BACK = 2, LEFT = 4, RIGHT = 8, RUN = 16, DUCK = 32, TURNLEFT = 64, TURNRIGHT = 128 };

#define BUTTON(name, bit)                                       \
    static void name##_on(void) { controls |= bit; }             \
    static void name##_off(void) { controls &= ~bit; }
BUTTON(forward, FWD) BUTTON(back, BACK) BUTTON(left, LEFT) BUTTON(right, RIGHT)
BUTTON(run, RUN) BUTTON(duck, DUCK) BUTTON(turnleft, TURNLEFT) BUTTON(turnright, TURNRIGHT)

static void select_player(void)
{
    if (eng->Cmd_Argc() == 2) {
        const char *name = eng->Cmd_Argv(1);
        int player = !strcmp(name, "sas") ? 0 : !strcmp(name, "phoenix") ? 1 : -1;
        if (player >= 0) {
            if (selected != player) memset(&avatar, 0, sizeof(avatar));
            selected = player;
            return;
        }
    }
    eng->pfnConsolePrint("Uso: dawe_player sas | phoenix\n");
}

void Dawe_PlayInit(cl_enginefunc_t *api)
{
    eng = api;
#ifdef DAWE_LONG
    test = eng->CheckParm("-dawe-long-test", NULL) != 0;
#else
    test = eng->CheckParm("-dawe-play-test", NULL) != 0;
#endif
#define REGISTER(name) eng->pfnAddCommand("+dawe_" #name, name##_on); eng->pfnAddCommand("-dawe_" #name, name##_off)
    REGISTER(forward); REGISTER(back); REGISTER(left); REGISTER(right);
    REGISTER(run); REGISTER(duck); REGISTER(turnleft); REGISTER(turnright);
#undef REGISTER
    eng->pfnAddCommand("dawe_player", select_player);
}

void Dawe_PlayReset(void)
{
    memset(&avatar, 0, sizeof(avatar));
    controls = ready = crouched = sequence = test_step = test_shots = 0;
    phase = speed = test_start = now = 0.f;
}

static float clamp(float x, float low, float high) { return fminf(high, fmaxf(low, x)); }

void Dawe_PlayLook(float yaw, float pitch)
{
    float view[3];
    eng->GetViewAngles(view);
    view[0] = clamp(view[0] + 2.f*pitch, -32.f, 42.f);
    view[1] = remainderf(view[1] + 2.f*yaw, 360.f);
    eng->SetViewAngles(view);
}

void Dawe_PlayCommand(float dt, struct usercmd_s *cmd, int active)
{
    if (active) {
        Dawe_PlayLook(60.f * dt * (!!(controls & TURNLEFT) - !!(controls & TURNRIGHT)), 0.f);
        cmd->forwardmove = DAWE_WALK_SPEED * (!!(controls & FWD) - !!(controls & BACK));
        cmd->sidemove = DAWE_WALK_SPEED * (!!(controls & RIGHT) - !!(controls & LEFT));
        if (controls & RUN) cmd->buttons |= IN_RUN;
        if (controls & DUCK) cmd->buttons |= IN_DUCK;
    }
    eng->GetViewAngles(cmd->viewangles);
}

static void update_avatar(struct ref_params_s *p, float cy, float sy)
{
    // Clip families and direction labels are generated in import_assets.AGENT_CLIPS.
    // The test has no held weapon: the pistol tracks provide a neutral two-handed stance.
    static const char *const clips[3][4] = {
        {"crouch_ne_pistol", "crouch_nw_pistol", "crouch_se_pistol", "crouch_sw_pistol"},
        {"run_ne_pistol", "run_nw_pistol", "run_se_pistol", "run_sw_pistol"},
        {"walk_ne_pistol", "walk_nw_pistol", "walk_se_pistol", "walk_sw_pistol"},
    };
    crouched = p->viewheight[2] < (DAWE_STAND_EYE + DAWE_DUCK_EYE)*.5f;
    speed = hypotf(p->simvel[0], p->simvel[1]);
    float f = cy*p->simvel[0] + sy*p->simvel[1];
    float s = sy*p->simvel[0] - cy*p->simvel[1];
    float tie = speed*.04f; // Keep cardinal inputs stable despite angle/network quantization.
    int direction = (f < -tie ? 2 : 0) + (s < -tie ? 1 : 0);
    int family = crouched ? 0 : speed > (DAWE_RUN_SPEED + DAWE_WALK_SPEED)*.5f ? 1 : 2;
    if (speed <= 2.f) direction = 0;
    const char *clip = clips[family][direction];
    for (int i = 1; i < DAWE_AGENT_CLIPS; i++) {
        if (!strcmp(clip, agent_sequences[i].name)) {
            sequence = i;
            break;
        }
    }
    float reference = crouched ? DAWE_DUCK_SPEED : family == 1 ? DAWE_RUN_SPEED : DAWE_WALK_SPEED;
    if (speed > 2.f && agent_sequences[sequence].duration > 0.f && !p->paused) {
        phase += clamp(p->frametime, 0.f, .1f) * speed / (reference * agent_sequences[sequence].duration);
        phase -= floorf(phase);
    } else if (speed <= 2.f) {
        phase = .5f; // Hold a fixed sample; the bank has no authored idle.
    }
    memcpy(avatar.origin, p->simorg, sizeof(avatar.origin));
    avatar.origin[2] -= crouched ? DAWE_DUCK_HALF : DAWE_STAND_HALF;
    avatar.angles[1] = p->cl_viewangles[1];
    avatar.curstate.sequence = sequence;
    avatar.latched.prevsequence = sequence;
    avatar.curstate.frame = 256.f * phase;
    avatar.curstate.scale = 1.f;
}

void Dawe_PlayRefdef(struct ref_params_s *p)
{
    if (p->health <= 0 || p->intermission) { ready = 0; return; }
    now = p->time;
    view_yaw = p->cl_viewangles[1];
    memcpy(worldpos, p->simorg, sizeof(worldpos));
    float yaw = p->cl_viewangles[1] * DAWE_RAD, cy = cosf(yaw), sy = sinf(yaw);
    update_avatar(p, cy, sy);
    ready = 1;

    // Orbit the player and retract the boom on contact with the BSP. A small
    // margin prevents the near clip plane from peeking past walls.
    float arm = 114.f, pitch = clamp(13.f + p->cl_viewangles[0], -19.f, 55.f);
    float c = cosf(pitch * DAWE_RAD), s = sinf(pitch * DAWE_RAD);
    float anchor[3] = {p->simorg[0], p->simorg[1], p->simorg[2] + p->viewheight[2] - 8.f};
    float end[3] = {anchor[0] - arm*c*cy, anchor[1] - arm*c*sy, anchor[2] + arm*s};
    event_api_t *ev = eng->pEventAPI;
    pmtrace_t hit;
    ev->EV_SetUpPlayerPrediction(0, 0);
    ev->EV_PushPMStates();
    ev->EV_SetTraceHull(2);
    ev->EV_PlayerTrace(anchor, end, PM_WORLD_ONLY, -1, &hit);
    ev->EV_SetTraceHull(crouched ? 1 : 0);
    ev->EV_PopPMStates();
    float fraction = hit.startsolid ? 0.f : hit.fraction >= 1.f ? 1.f : fmaxf(0.f, hit.fraction - 6.f / arm);
    for (int i = 0; i < 3; i++) p->vieworg[i] = anchor[i] + fraction * (end[i] - anchor[i]);
    p->viewangles[0] = pitch;
    p->viewangles[1] = p->cl_viewangles[1];
    p->viewangles[2] = 0.f;
}

void Dawe_PlayDraw(void)
{
    if (!ready) return;
    if (!avatar.model) avatar.model = eng->CL_LoadModel(agent_models[selected], &avatar.curstate.modelindex);
    if (avatar.model) eng->CL_CreateVisibleEntity(ET_NORMAL, &avatar);
}

static void run_test(void)
{
    static const struct { float at; const char *tag, *command; } steps[] = {
#ifdef DAWE_LONG
        {0.f,   "patio",     "+dawe_forward; +dawe_run"},
        {.78f,  "approach",  ""},
        {1.50f, "door_south",""},
        {2.55f, "passage",   ""},
        {3.21f, "door_north",""},
        {3.96f, "junction",  "-dawe_forward"},
        {4.71f, "east",      "+dawe_forward; dawe_player phoenix"},
        {6.23f, "long_lane", ""},
        {7.78f, "end_wall",  "-dawe_forward; -dawe_run"},
        {8.03f, "stop",      "quit"},
#else
        {0.f,  "spawn",   "+dawe_forward"},
        {.55f, "walk",    "+dawe_run"},
        {.86f, "run",     ""},
        {1.65f,"blocked", "-dawe_run; +dawe_duck"},
        {2.61f,"under",   "-dawe_forward; -dawe_duck"},
        {2.96f,"held",    "+dawe_forward"},
        {4.05f,"exit",    "-dawe_forward; +dawe_back; +dawe_left; dawe_player phoenix"},
        {4.52f,"diagonal","-dawe_back; -dawe_left"},
        {4.80f,"stop",    "+dawe_turnleft"},
        {5.55f,"turned",  "-dawe_turnleft; +dawe_forward"},
        {6.03f,"advance", "-dawe_forward; quit"},
#endif
    };
    if (!ready || !avatar.model) return;
    if (!test_step) test_start = now;
    float elapsed = now - test_start;
    if (test_step < (int)(sizeof(steps)/sizeof(steps[0])) && elapsed >= steps[test_step].at) {
        char log[256];
        snprintf(log, sizeof(log), "Dawe play %s x=%.1f y=%.1f z=%.1f speed=%.1f duck=%d clip=%s agent=%s yaw=%.1f\n",
                 steps[test_step].tag, worldpos[0], worldpos[1], worldpos[2], speed, crouched,
                 agent_sequences[sequence].name, player_names[selected], view_yaw);
        eng->pfnConsolePrint(log);
#ifdef DAWE_LONG
        // A fixed heading makes the sector route independent of render FPS.
        if (!strcmp(steps[test_step].tag, "east")) {
            float view[3] = {0.f, -90.f, 0.f};
            eng->SetViewAngles(view);
        }
#endif
        if (steps[test_step].command[0]) eng->pfnClientCmd(steps[test_step].command);
        test_step++;
    }
#ifdef DAWE_LONG
    const int frames = 66;
    const char *prefix = "long";
#else
    const int frames = 50;
    const char *prefix = "play";
#endif
    if (test_shots < frames && elapsed >= test_shots * .12f) {
        char cmd[80];
        snprintf(cmd, sizeof(cmd), "screenshot scrshots/%s_%02d.png", prefix, test_shots++);
        eng->pfnClientCmd(cmd);
    }
}

void Dawe_PlayHUD(void)
{
    if (test) run_test();
}
