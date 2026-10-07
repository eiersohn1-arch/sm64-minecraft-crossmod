#pragma once

#ifdef __cplusplus
extern "C" {
#endif

struct MarioState;

void native_minecraft_pre_mario_action(struct MarioState *m);
void native_minecraft_tick(struct MarioState *m);
void native_minecraft_apply_proxy(struct MarioState *m);
void native_minecraft_override_camera(void);

int native_minecraft_active(void);
int native_minecraft_has_authority(void);
int native_minecraft_first_person(void);
int native_minecraft_selected_slot(void);
int native_minecraft_pointer_locked(void);

void native_minecraft_key_event(int vk, int down);
void native_minecraft_mouse_button(int button, int down);
void native_minecraft_raw_mouse(int dx, int dy);
void native_minecraft_focus_changed(int focused);

int native_minecraft_block_count(void);
int native_minecraft_get_block(int index, int *x, int *y, int *z, int *type);

void native_minecraft_get_render_state(
    float *x, float *y, float *z,
    float *yaw, float *pitch,
    int *first_person, int *selected_slot, int *inventory_open
);

#ifdef __cplusplus
}
#endif
