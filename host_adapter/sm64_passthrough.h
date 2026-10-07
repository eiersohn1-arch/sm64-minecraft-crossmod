#pragma once
#ifdef __cplusplus
extern "C" {
#endif

struct MarioState;

void um_passthrough_start(void);
void um_passthrough_stop(void);
int um_passthrough_connected(void);
int um_passthrough_minecraft_authority(void);

void um_passthrough_neutralize_controller(struct MarioState *m);
void um_passthrough_apply_mario_proxy(struct MarioState *m);
void um_passthrough_override_camera(void);
void um_passthrough_before_frame(void);
void um_passthrough_frame(void);

void um_passthrough_key_event(int vk, int down);
void um_passthrough_mouse_button(int button, int down);
void um_passthrough_raw_mouse(int dx, int dy);
void um_passthrough_scroll(int delta);
void um_passthrough_pointer(int x, int y, int width, int height);
void um_passthrough_view(int width, int height);
void um_passthrough_focus_changed(int focused);
int um_passthrough_pointer_locked(void);

#ifdef __cplusplus
}
#endif
