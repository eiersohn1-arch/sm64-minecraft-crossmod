#ifndef CROSSMOD_BRIDGE_H
#define CROSSMOD_BRIDGE_H

#include <stdbool.h>

struct MarioState;
struct Controller;

void crossmod_bridge_init(void);
void crossmod_bridge_shutdown(void);
void crossmod_bridge_poll(void);
bool crossmod_bridge_active(void);

/*
 * Native-authority mode:
 * Minecraft supplies controls/items, while SM64 owns movement, collision,
 * actions, warps and progression for the entire game.
 */
void crossmod_bridge_apply_controller(struct Controller *controller);
void crossmod_bridge_after_mario_update(struct MarioState *m);

#endif
