#ifndef CROSSMOD_BRIDGE_H
#define CROSSMOD_BRIDGE_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

struct MarioState;
struct Controller;
struct Camera;

struct CrossmodRenderPose {
    unsigned long frame;
    float camera_x;
    float camera_y;
    float camera_z;
    float yaw;
    float pitch;
    float roll;
    float fov;
};

void crossmod_bridge_init(void);
void crossmod_bridge_shutdown(void);
void crossmod_bridge_poll(void);
bool crossmod_bridge_active(void);
void crossmod_bridge_mouse_wheel(int delta);

/*
 * Native-authority mode:
 * Minecraft supplies controls/items, while SM64 owns movement, collision,
 * actions, missions, warps, save data and progression for the whole game.
 */
void crossmod_bridge_apply_controller(struct Controller *controller);
void crossmod_bridge_after_mario_update(struct MarioState *m);
void crossmod_bridge_override_camera(struct Camera *camera);

/* Rebuild nearby Minecraft block CollisionShapes as native SM64 surfaces. */
void crossmod_bridge_load_block_surfaces(void);

/* Current host camera for Universal-Modder-style frame reprojection. */
bool crossmod_bridge_get_render_pose(struct CrossmodRenderPose *out_pose);

#ifdef __cplusplus
}
#endif

#endif
