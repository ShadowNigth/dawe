#ifndef DAWE_PLAY_CLIENT_H
#define DAWE_PLAY_CLIENT_H

struct ref_params_s;
struct usercmd_s;
void Dawe_PlayInit(cl_enginefunc_t *api);
void Dawe_PlayReset(void);
void Dawe_PlayCommand(float dt, struct usercmd_s *cmd, int active);
void Dawe_PlayLook(float yaw, float pitch);
void Dawe_PlayRefdef(struct ref_params_s *p);
void Dawe_PlayDraw(void);
void Dawe_PlayHUD(void);
#endif
