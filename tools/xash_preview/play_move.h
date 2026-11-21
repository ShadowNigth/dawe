#ifndef DAWE_PLAY_MOVE_H
#define DAWE_PLAY_MOVE_H

#define DAWE_STAND_HALF 36.f
#define DAWE_DUCK_HALF 18.f
#define DAWE_STAND_EYE 28.f
#define DAWE_DUCK_EYE 16.f
#define DAWE_WALK_SPEED 110.f
#define DAWE_RUN_SPEED 220.f
#define DAWE_DUCK_SPEED 76.f
#define DAWE_RAD 0.017453292519943295f

struct playermove_s;
void Dawe_Move(struct playermove_s *pm);
int Dawe_Hull(int index, float *mins, float *maxs);
#endif
