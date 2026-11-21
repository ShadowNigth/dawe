/* Local exhibit and movement course: the engine renders all studio models. */
#include <stdio.h>
#include <string.h>
#include "xash3d_types.h"
#include "cdll_int.h"
#include "cl_entity.h"
#include "ref_params.h"
#include "studio_event.h"
#include "entity_types.h"
#include "dawe_sequences.h"
#ifdef DAWE_PLAY
#include "play_client.h"
#include "play_move.h"
#endif

struct playermove_s;
struct netadr_s;
struct mstudioevent_s;
struct tempent_s;

static cl_enginefunc_t eng;
static int capture;
enum { SEQ_IDLE = 0, SEQ_RELOAD = 3, SEQ_ATTACH = 5, SEQ_DETACH = 6 };

static int model_frames;
static int animate_capture, active_sequence, silencer_body, shot;
static int recording_sequence = 1;
static float pose_time, started;

#if defined(DAWE_AGENTS) && !defined(DAWE_PLAY)
static cl_entity_t agents[DAWE_AGENTS];
static int agent_sequence, agent_ready, agent_capture, capture_tick;
static float agent_start;
static const char *const demo_clips[] = {"idle", "walk_ne_pistol", "run_nw_knife", "crouch_sw_rifle"};
enum { AGENT_SAMPLES = 8, DEMO_COUNT = sizeof(demo_clips) / sizeof(demo_clips[0]),
       DEMO_SHOTS = 1 + (DEMO_COUNT - 1) * AGENT_SAMPLES };

static int find_agent_sequence(const char *name)
{
    for (int i = 0; i < DAWE_AGENT_CLIPS; i++)
        if (!strcmp(name, agent_sequences[i].name)) return i;
    return -1;
}

static void agent_command(void)
{
    int i = eng.Cmd_Argc() == 2 ? find_agent_sequence(eng.Cmd_Argv(1)) : -1;
    if (i >= 0) {
        agent_sequence = i;
        agent_start = eng.GetClientTime();
    } else {
        eng.pfnConsolePrint("Uso: dawe_agent <secuencia>. Disponibles:\n");
        for (i = 0; i < DAWE_AGENT_CLIPS; i++) {
            eng.pfnConsolePrint(agent_sequences[i].name);
            eng.pfnConsolePrint(i % 3 == 0 ? "\n" : ", ");
        }
    }
}

static void draw_agents(void)
{
    float now = eng.GetClientTime(), phase = 0;
    if (agent_capture && capture_tick < 4 * DEMO_SHOTS) {
        int frame = capture_tick / 4;
        int demo = frame ? 1 + (frame-1) / AGENT_SAMPLES : 0;
        int sample = frame ? (frame-1) % AGENT_SAMPLES : 0;
        agent_sequence = find_agent_sequence(demo_clips[demo]);
        phase = (float)sample / AGENT_SAMPLES;
    } else if (agent_sequences[agent_sequence].duration > 0) {
        phase = (now - agent_start) / agent_sequences[agent_sequence].duration;
        if (phase < 0) phase = 0;
        phase -= (int)phase;
    }
    agent_ready = 0;
    for (int i = 0; i < DAWE_AGENTS; i++) {
        cl_entity_t *ent = &agents[i];
        if (!ent->model) ent->model = eng.CL_LoadModel(agent_models[i], &ent->curstate.modelindex);
        if (!ent->model) continue;
        ent->origin[0] = 55;
        ent->origin[1] = i ? -33 : 33;
        ent->angles[1] = i ? 155 : 205;
        ent->curstate.sequence = agent_sequence;
        ent->curstate.frame = 256.f * phase;
        ent->curstate.scale = 1;
        ent->latched.prevsequence = agent_sequence;
        agent_ready += eng.CL_CreateVisibleEntity(ET_NORMAL, ent) != 0;
    }
}

static void capture_agents(void)
{
    if (!agent_capture || agent_ready != DAWE_AGENTS) return;
    if (capture_tick >= 4 * DEMO_SHOTS) {
        eng.pfnClientCmd("quit");
    } else if (capture_tick % 4 == 2) {
        int frame = capture_tick / 4;
        char cmd[128];
        snprintf(cmd, sizeof(cmd), "screenshot scrshots/agents_%s_%02d.png",
                 agent_sequences[agent_sequence].name, frame ? (frame-1) % AGENT_SAMPLES : 0);
        eng.pfnClientCmd(cmd);
    }
    capture_tick++;
}
#endif

static void play_sequence(int index)
{
    if (index == SEQ_ATTACH) silencer_body = 1;  // Attach starts with the part hidden.
    if (index == SEQ_DETACH) silencer_body = 0;  // Detach starts with it attached.
    active_sequence = index;
    started = pose_time;
    eng.pfnWeaponAnim(index, silencer_body);
}

static void animation_command(void)
{
    if (model_frames && eng.Cmd_Argc() == 2) {
        for (int i = 0; i < DAWE_NUM_SEQUENCES; i++) {
            if (strcmp(eng.Cmd_Argv(1), sequences[i].name) == 0) {
                play_sequence(i);
                return;
            }
        }
    }
    eng.pfnConsolePrint("Uso en la sala: dawe_anim <secuencia>. Disponibles: ");
    for (int i = 0; i < DAWE_NUM_SEQUENCES; i++) {
        eng.pfnConsolePrint(sequences[i].name);
        eng.pfnConsolePrint(i + 1 == DAWE_NUM_SEQUENCES ? "\n" : ", ");
    }
}

int Initialize(cl_enginefunc_t *api, int version)
{
    if (version != CLDLL_INTERFACE_VERSION) return 0;
    eng = *api;
#if defined(DAWE_AGENTS) && !defined(DAWE_PLAY)
    agent_capture = eng.CheckParm("-dawe-agents-capture", NULL) != 0;
#endif
    capture = eng.CheckParm("-dawe-capture", NULL) != 0;
    animate_capture = !capture && DAWE_NUM_SEQUENCES > 1 && eng.CheckParm("-dawe-animate", NULL) != 0;
    return 1;
}

void V_CalcRefdef(ref_params_t *p)
{
#ifdef DAWE_PLAY
    Dawe_PlayRefdef(p);
    return;
#endif
    cl_entity_t *view = eng.GetViewModel();
    for (int i = 0; i < 3; i++) {
        p->vieworg[i] = p->simorg[i] + p->viewheight[i];
        p->viewangles[i] = p->cl_viewangles[i];
    }
    memcpy(view->origin, p->vieworg, sizeof(view->origin));
    memcpy(view->angles, p->viewangles, sizeof(view->angles));
    view->angles[0] *= -1;
    if (view->model) {
        model_frames++;
        view->curstate.body = silencer_body;
        pose_time = p->time;
    }
}

int HUD_Redraw(float time, int intermission)
{
#ifdef DAWE_PLAY
    Dawe_PlayHUD();
    return 1;
#elif defined(DAWE_AGENTS)
    capture_agents();
#endif
    // Comparison frames distinguish the engine's viewmodel pass from the BSP.
    if (capture && model_frames == 12) eng.pfnClientCmd("screenshot scrshots/dawe_" DAWE_WEAPON_TAG ".png");
    if (capture && model_frames == 18) eng.pfnClientCmd("r_drawviewmodel 0; screenshot scrshots/dawe_empty.png");
    if (capture && model_frames == 24) eng.pfnClientCmd("quit");
    if (animate_capture && model_frames >= 12) {
        if (active_sequence == SEQ_IDLE && recording_sequence < DAWE_NUM_SEQUENCES) {
            shot = 0;
            play_sequence(recording_sequence++);
        } else if (active_sequence == SEQ_IDLE) {
            eng.pfnClientCmd("quit");
        } else {
            float duration = sequences[active_sequence].duration;
            float age = pose_time - started;
            int samples = active_sequence == SEQ_RELOAD ? 16 : 4;
            if (shot < samples && age >= duration * (shot + .2f) / samples) {
                char cmd[128];
                snprintf(cmd, sizeof(cmd), "screenshot scrshots/%s_%02d.png",
                         sequences[active_sequence].name, shot++);
                eng.pfnClientCmd(cmd);
            }
            if (age >= duration + .15f) play_sequence(SEQ_IDLE);
        }
    } else if (active_sequence && pose_time - started > sequences[active_sequence].duration + .04f) {
        play_sequence(SEQ_IDLE);
    }
    return 1;
}

void HUD_Init(void)
{
#ifdef DAWE_PLAY
    Dawe_PlayInit(&eng);
#elif defined(DAWE_AGENTS)
    eng.pfnAddCommand("dawe_agent", agent_command);
#else
    eng.pfnAddCommand("dawe_anim", animation_command);
#endif
}

void HUD_CreateEntities(void)
{
#ifdef DAWE_PLAY
    Dawe_PlayDraw();
#elif defined(DAWE_AGENTS)
    draw_agents();
#endif
}

void HUD_Reset(void)
{
#ifdef DAWE_PLAY
    Dawe_PlayReset();
#elif defined(DAWE_AGENTS)
    memset(agents, 0, sizeof(agents));
    agent_sequence = find_agent_sequence("walk_ne_pistol");
    agent_ready = capture_tick = 0;
    agent_start = eng.GetClientTime();
#endif
}

#define VOID(name) void name(void) {}
VOID(HUD_Shutdown)
VOID(HUD_DrawNormalTriangles) VOID(HUD_DrawTransparentTriangles) VOID(CAM_Think)
VOID(IN_ActivateMouse) VOID(IN_DeactivateMouse) VOID(IN_Accumulate) VOID(IN_ClearStates)

int HUD_VidInit(void) { return 1; }
int HUD_UpdateClientData(client_data_t *data, float time) { return 1; }
void HUD_PlayerMove(struct playermove_s *pm, int server)
{
#ifdef DAWE_PLAY
    Dawe_Move(pm);
#endif
}
void HUD_PlayerMoveInit(struct playermove_s *pm) {}
char HUD_PlayerMoveTexture(char *name) { return 'C'; }
int HUD_ConnectionlessPacket(const struct netadr_s *from, const char *args, char *out, int *size) { *size = 0; return 0; }
int HUD_GetHullBounds(int hull, float *mins, float *maxs)
{
#ifdef DAWE_PLAY
    return Dawe_Hull(hull, mins, maxs);
#else
    return 0;
#endif
}
void HUD_Frame(double time) {}
void HUD_PostRunCmd(struct local_state_s *from, struct local_state_s *to, struct usercmd_s *cmd, int run, double t, unsigned int seed) {}
int HUD_Key_Event(int event, int key, const char *binding) { return 1; }
int HUD_AddEntity(int type, cl_entity_t *ent, const char *name) { return 1; }
void HUD_StudioEvent(const mstudioevent_t *event, const cl_entity_t *ent)
{
    if (event->event == 5001 && ent == eng.GetViewModel()) {
        int next_body = event->options[0] == '1';
        if (silencer_body != next_body)
            eng.pfnConsolePrint(next_body ? "Dawe: silenciador oculto\n" : "Dawe: silenciador visible\n");
        silencer_body = next_body;
        eng.GetViewModel()->curstate.body = silencer_body;
    }
}
void HUD_TxferLocalOverrides(entity_state_t *state, const clientdata_t *data) { memcpy(state->origin, data->origin, sizeof(state->origin)); }
void HUD_ProcessPlayerState(entity_state_t *dst, const entity_state_t *src) { *dst = *src; }
void HUD_TxferPredictionData(entity_state_t *ps, const entity_state_t *pps, clientdata_t *cd, const clientdata_t *pcd, weapon_data_t *wd, const weapon_data_t *pwd) {}
void HUD_TempEntUpdate(double time, double client, double gravity, struct tempent_s **available, struct tempent_s **active, int (*add)(cl_entity_t *), void (*play)(struct tempent_s *, float)) {}
cl_entity_t *HUD_GetUserEntity(int index) { return NULL; }
void Demo_ReadBuffer(int size, byte *data) {}
int CL_IsThirdPerson(void) { return 0; }
void CL_CameraOffset(float *offset) {}
void CL_CreateMove(float t, struct usercmd_s *cmd, int active)
{
#ifdef DAWE_PLAY
    Dawe_PlayCommand(t, cmd, active);
#endif
}
#ifdef DAWE_PLAY
void IN_ClientLookEvent(float yaw, float pitch) { Dawe_PlayLook(yaw, pitch); }
void IN_ClientMoveEvent(float forward, float side) {} // Keyboard-only translation in the test course.
#endif
void IN_MouseEvent(int state) {}
void *KB_Find(const char *name) { return NULL; }
