#ifndef CROSSMOD_BRIDGE_H
#define CROSSMOD_BRIDGE_H

#include <stdbool.h>

struct MarioState;

void crossmod_bridge_init(void);
void crossmod_bridge_shutdown(void);
void crossmod_bridge_poll(void);
bool crossmod_bridge_active(void);

/*
 * Makes SM64's Mario object an invisible gameplay proxy for the Minecraft
 * player. The real visible player is rendered by Minecraft.
 *
 * Minecraft melee attacks are converted into native SM64 object interaction
 * hits, so existing SM64 enemy behavior remains the authority for reactions.
 */
bool crossmod_bridge_apply_mario(struct MarioState *m);

#endif
