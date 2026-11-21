/* Standalone local Xash3D preview and movement course. */
#include <string.h>
#include "xash3d_types.h"
#include "edict.h"
#include "eiface.h"
#include "entity_state.h"
#include "dawe_sequences.h"
#ifdef DAWE_PLAY
#include "play_move.h"
#endif

static enginefuncs_t eng;
static int view_model;
#ifndef DAWE_AGENTS
static const char model_path[] = DAWE_VIEWMODEL;
#endif

void GiveFnptrsToDll(enginefuncs_t *api, globalvars_t *globals) { eng = *api; }
void worldspawn(entvars_t *v) {}
void info_player_start(entvars_t *v) {}
void light(entvars_t *v) {}
void light_environment(entvars_t *v) {}
void player(entvars_t *v) {}

static void noop(void) {}
static void sys_error(const char *message) {}
static void ent_noop(edict_t *ent) {}
static void pair_noop(edict_t *a, edict_t *b) {}
static void pm_init(struct playermove_s *pm) {}
static void pm_move(struct playermove_s *pm, qboolean server)
{
#ifdef DAWE_PLAY
    Dawe_Move(pm);
#endif
}
static void active(edict_t *first, int edicts, int players) {}
static const char *description(void) { return "Dawe | " DAWE_WEAPON_NAME " model check"; }
static int zero(void) { return 0; }
static void cmd_start(const edict_t *player, const struct usercmd_s *cmd, unsigned int seed) {}
static void cmd_end(const edict_t *player) {}
static void userinfo(edict_t *ent, char *info) {}
static void custom(edict_t *ent, customization_t *data) {}
static void keyvalue(edict_t *ent, KeyValueData *kv)
{
    if (strcmp(kv->szKeyName, "classname") == 0)
        ent->v.classname = eng.pfnAllocString(kv->szValue);
    kv->fHandled = 1;
}

static int spawn(edict_t *ent)
{
    if (eng.pfnIndexOfEdict(ent) == 0) {
#ifdef DAWE_AGENTS
        for (int i = 0; i < DAWE_AGENTS; i++) {
            int model = eng.pfnPrecacheModel((char *)agent_models[i]);
            eng.pfnAlertMessage(at_console, "Dawe: precache %s (index %d)\n", agent_models[i], model);
        }
#else
        view_model = eng.pfnPrecacheModel((char *)model_path);
        eng.pfnAlertMessage(at_console, "Dawe: precache %s (index %d)\n", model_path, view_model);
#endif
#ifdef DAWE_LONG
        eng.pfnCVarSetString("sv_skyname", DAWE_SKY);
#endif
        eng.pfnLightStyle(0, "m");
    }
    return 0;
}

static qboolean connect_local(edict_t *ent, const char *name, const char *addr, char reject[128])
{
    if (strcmp(addr, "loopback") == 0 || strcmp(addr, "localhost") == 0)
        return 1;
    strcpy(reject, "Prueba local.");
    return 0;
}

static void put_client(edict_t *ent)
{
#ifdef DAWE_LONG
    const float origin[3] = {DAWE_START_X, DAWE_START_Y, DAWE_STAND_HALF + .125f};
#elif defined(DAWE_PLAY)
    const float origin[3] = {-208, 0, DAWE_STAND_HALF + .125f};
#else
    const float origin[3] = {-56, 0, 36};
#endif
    ent->v.flags |= FL_CLIENT;
    ent->v.health = 100;
#ifdef DAWE_PLAY
    ent->v.movetype = MOVETYPE_WALK;
    ent->v.solid = SOLID_SLIDEBOX;
    ent->v.view_ofs[2] = DAWE_STAND_EYE;
    float mins[3], maxs[3];
    Dawe_Hull(0, mins, maxs);
    eng.pfnSetSize(ent, mins, maxs);
#else
    ent->v.movetype = MOVETYPE_NONE;
#ifdef DAWE_AGENTS
    ent->v.view_ofs[2] = 8;
#else
    ent->v.view_ofs[2] = 28;
#endif
#endif
    eng.pfnSetOrigin(ent, origin);
}

static void visibility(edict_t *view, edict_t *client, unsigned char **pvs, unsigned char **pas)
{
    *pvs = *pas = NULL;
}

static void client_data(const edict_t *ent, int weapons, clientdata_t *cd)
{
    memcpy(cd->origin, ent->v.origin, sizeof(cd->origin));
    memcpy(cd->view_ofs, ent->v.view_ofs, sizeof(cd->view_ofs));
    cd->viewmodel = view_model;
    cd->health = ent->v.health;
#ifdef DAWE_PLAY
    memcpy(cd->velocity, ent->v.velocity, sizeof(cd->velocity));
    cd->flags = ent->v.flags;
#endif
    cd->fov = 90;
}

static int pack(entity_state_t *state, int index, edict_t *ent, edict_t *host, int flags, int player, unsigned char *set)
{
    if (ent != host) return 0;
    state->number = index;
    state->entityType = 1;
#ifdef DAWE_PLAY
    state->movetype = ent->v.movetype;
    state->usehull = (ent->v.flags & FL_DUCKING) != 0;
    state->onground = 0;
#endif
    memcpy(state->origin, ent->v.origin, sizeof(state->origin));
    return 1;
}

static void baseline(int player, int index, entity_state_t *state, edict_t *ent, int model, vec3_t mins, vec3_t maxs)
{
    memcpy(state->origin, ent->v.origin, sizeof(state->origin));
    state->modelindex = ent->v.modelindex;
}

static int hull(int index, float *mins, float *maxs)
{
#ifdef DAWE_PLAY
    return Dawe_Hull(index, mins, maxs);
#else
    return 0;
#endif
}
static int weapon_data(struct edict_s *player, struct weapon_data_s *data) { return 0; }
static int connectionless(const struct netadr_s *adr, const char *args, char *buffer, int *size)
{
    *size = 0;
    return 0;
}

int GetEntityAPI2(DLL_FUNCTIONS *api, int *version)
{
    if (*version != INTERFACE_VERSION) {
        *version = INTERFACE_VERSION;
        return 0;
    }
    *api = (DLL_FUNCTIONS) {
        .pfnGameInit = noop, .pfnSpawn = spawn, .pfnThink = ent_noop,
        .pfnUse = pair_noop, .pfnTouch = pair_noop, .pfnBlocked = pair_noop,
        .pfnKeyValue = keyvalue, .pfnSetAbsBox = ent_noop, .pfnResetGlobalState = noop,
        .pfnClientConnect = connect_local, .pfnClientDisconnect = ent_noop, .pfnClientKill = ent_noop,
        .pfnClientPutInServer = put_client, .pfnClientCommand = ent_noop, .pfnClientUserInfoChanged = userinfo,
        .pfnServerActivate = active, .pfnServerDeactivate = noop,
        .pfnPlayerPreThink = ent_noop, .pfnPlayerPostThink = ent_noop, .pfnStartFrame = noop,
        .pfnParmsNewLevel = noop, .pfnParmsChangeLevel = noop, .pfnGetGameDescription = description,
        .pfnPlayerCustomization = custom, .pfnSys_Error = sys_error, .pfnPM_Init = pm_init, .pfnPM_Move = pm_move,
        .pfnSetupVisibility = visibility, .pfnUpdateClientData = client_data, .pfnAddToFullPack = pack,
        .pfnCreateBaseline = baseline, .pfnRegisterEncoders = noop, .pfnGetWeaponData = weapon_data,
        .pfnCmdStart = cmd_start, .pfnCmdEnd = cmd_end, .pfnConnectionlessPacket = connectionless,
        .pfnGetHullBounds = hull, .pfnCreateInstancedBaselines = noop, .pfnAllowLagCompensation = zero,
    };
    return 1;
}
