#include "crossmod_bridge.h"
#include "sm64.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif

#include "crossmod_ws_api.h"

#include "game/area.h"
#include "game/camera.h"
#include "game/game_init.h"
#include "game/interaction.h"
#include "game/level_update.h"
#include "game/mario.h"
#include "game/object_list_processor.h"
#include "game/save_file.h"
#include "engine/math_util.h"
#include "engine/surface_collision.h"
#include "engine/surface_load.h"
#include "engine/graph_node.h"
#include "object_constants.h"
#include "object_fields.h"
#include "surface_terrains.h"

extern struct CameraFOVStatus sFOVState;

#define CROSSMOD_SCALE 100.0f
#define CROSSMOD_MIN_MELEE_REACH 220.0f
#define CROSSMOD_MAX_MELEE_REACH 520.0f
#define CROSSMOD_ATTACK_HALF_ANGLE_COS 0.35f
#define CROSSMOD_MAX_BLOCK_BOXES 4096
#define CROSSMOD_TERRAIN_RADIUS 8
#define CROSSMOD_TERRAIN_INTERVAL 3
#define CROSSMOD_OVERLAY_ORIGIN_Y 128

#define CROSSMOD_ENEMY_INTERACT_MASK ( \
    INTERACT_GRABBABLE | \
    INTERACT_DAMAGE | \
    INTERACT_KOOPA | \
    INTERACT_BREAKABLE | \
    INTERACT_BOUNCE_TOP | \
    INTERACT_BULLY | \
    INTERACT_BOUNCE_TOP2 | \
    INTERACT_MR_BLIZZARD | \
    INTERACT_HIT_FROM_BELOW | \
    INTERACT_CLAM_OR_BUBBA | \
    INTERACT_SHOCK | \
    INTERACT_UNKNOWN_08 \
)

struct CrossmodBlockBox {
    long long key;
    float min_x;
    float min_y;
    float min_z;
    float max_x;
    float max_y;
    float max_z;
    int active;
};

struct CrossmodSurfaceHit {
    int valid;
    float x;
    float y;
    float z;
    float nx;
    float ny;
    float nz;
};

struct CrossmodGuestState {
    unsigned long sequence;
    char held_item[96];
    int selected_slot;
    char weapon_kind[24];
    float reach_blocks;
    int power;
    int screen_open;
    float health;
    int food;
    float player_x;
    float player_y;
    float player_z;
    float velocity_x;
    float velocity_y;
    float velocity_z;
    float yaw;
    float pitch;
    float body_yaw;
    int on_ground;
    int sneaking;
    int sprinting;
};

static struct CrossmodBlockBox s_block_boxes[CROSSMOD_MAX_BLOCK_BOXES];

static int s_has_guest;
static struct CrossmodGuestState s_guest;

static unsigned int s_host_keys;
static unsigned long s_attack_serial;
static unsigned long s_use_serial;
static int s_attack_down;
static int s_use_down;
static int s_prev_attack_down;
static int s_prev_use_down;
static unsigned int s_prev_slot_mask;
static int s_prev_inventory_down;
static int s_prev_view_down;
static int s_prev_hud_down;
static int s_prev_drop_down;
static int s_prev_swap_down;
static int s_prev_escape_down;
static int s_prev_chat_down;
static int s_prev_command_down;
static unsigned char s_gui_prev_keys[256];
static int s_mouse_ready;
static int s_view_initialized;
static int s_view_mode = 0; /* 0=first, 1=third-back, 2=third-front */
static float s_view_yaw;
static float s_view_pitch;

static unsigned long s_last_processed_attack_serial;
static unsigned long s_last_processed_use_serial;
static unsigned long s_last_hit_attack_serial;
static int s_last_hit_count;
static unsigned long s_host_frame;
static struct CrossmodRenderPose s_render_pose;
static int s_render_pose_valid;
static unsigned int s_terrain_tick;
static unsigned long s_terrain_sequence;
static float s_pending_mc_health_delta;
static int s_proxy_armed;
static int s_proxy_level = -999;
static int s_proxy_area = -999;
static int s_proxy_course = -999;
static int s_proxy_act = -999;
static unsigned int s_proxy_wait_frames;
static int s_host_client_width = 1280;
static int s_host_client_height = 720;

void crossmod_bridge_init(void) {
    crossmod_ws_start();
}

void crossmod_bridge_shutdown(void) {
    crossmod_ws_stop();
}

bool crossmod_bridge_active(void) {
    return s_has_guest != 0 && crossmod_ws_connected();
}


void crossmod_bridge_mouse_wheel(int delta) {
    if (!s_has_guest
            || !crossmod_ws_connected()
            || s_guest.screen_open
            || delta == 0) {
        return;
    }

    char message[96];
    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"scroll\",\"delta\":%d}",
            delta
    );
    crossmod_ws_send(message);
}

bool crossmod_bridge_get_render_pose(
        struct CrossmodRenderPose *out_pose
) {
    if (!s_render_pose_valid || out_pose == NULL) {
        return false;
    }

    *out_pose = s_render_pose;
    return true;
}

bool crossmod_bridge_sync_minecraft_proxy(
        struct MarioState *m
) {
    if (!s_has_guest
            || m == NULL
            || m->marioObj == NULL) {
        return false;
    }

    int level = (int) gCurrLevelNum;
    int area = (int) gCurrAreaIndex;
    int course = (int) gCurrCourseNum;
    int act = (int) gCurrActNum;

    if (level != s_proxy_level
            || area != s_proxy_area
            || course != s_proxy_course
            || act != s_proxy_act) {
        s_proxy_level = level;
        s_proxy_area = area;
        s_proxy_course = course;
        s_proxy_act = act;
        s_proxy_armed = 0;
        s_proxy_wait_frames = 0;
    }

    float target_x = s_guest.player_x * CROSSMOD_SCALE;
    float target_y = s_guest.player_y * CROSSMOD_SCALE;
    float target_z = -s_guest.player_z * CROSSMOD_SCALE;

    if (!s_proxy_armed) {
        float dx = target_x - m->pos[0];
        float dy = target_y - m->pos[1];
        float dz = target_z - m->pos[2];
        float distance_sq = dx * dx + dy * dy + dz * dz;

        /*
         * On a fresh level/warp the host first publishes the original SM64
         * spawn. Minecraft snaps there once; only then does authority flip to
         * Minecraft. This avoids replacing a new course spawn with the hidden
         * overlay world's old coordinates.
         */
        if (distance_sq <= 500.0f * 500.0f
                || ++s_proxy_wait_frames > 120) {
            s_proxy_armed = 1;
        } else {
            return false;
        }
    }

    m->pos[0] = target_x;
    m->pos[1] = target_y;
    m->pos[2] = target_z;

    m->vel[0] = s_guest.velocity_x * CROSSMOD_SCALE;
    m->vel[1] = s_guest.velocity_y * CROSSMOD_SCALE;
    m->vel[2] = -s_guest.velocity_z * CROSSMOD_SCALE;

    m->slideVelX = m->vel[0];
    m->slideVelZ = m->vel[2];
    m->forwardVel = sqrtf(
            m->vel[0] * m->vel[0]
            + m->vel[2] * m->vel[2]
    );

    m->faceAngle[0] = 0;
    m->faceAngle[1] = (s16) lroundf(
            -s_guest.body_yaw * 65536.0f / 360.0f
    );
    m->faceAngle[2] = 0;

    m->marioObj->oPosX = m->pos[0];
    m->marioObj->oPosY = m->pos[1];
    m->marioObj->oPosZ = m->pos[2];
    m->marioObj->oFaceAngleYaw = m->faceAngle[1];
    m->marioObj->oMoveAngleYaw = m->faceAngle[1];
    vec3f_copy(m->marioObj->header.gfx.pos, m->pos);
    m->marioObj->header.gfx.angle[1] = m->faceAngle[1];

    m->wall = NULL;
    m->floorHeight = find_floor(
            m->pos[0],
            m->pos[1] + 80.0f,
            m->pos[2],
            &m->floor
    );

    if (m->floor != NULL) {
        m->floorAngle = atan2s(
                m->floor->normal.z,
                m->floor->normal.x
        );
    }

    m->ceilHeight = vec3f_find_ceil(
            &m->pos[0],
            m->floorHeight,
            &m->ceil
    );
    m->waterLevel = find_water_level(
            m->pos[0],
            m->pos[2]
    );

    /*
     * Keep only semantic inputs needed by original SM64 interactions. No
     * analog/intended movement is ever fed back into Mario locomotion.
     */
    m->input = 0;
    m->intendedMag = 0.0f;
    m->intendedYaw = m->faceAngle[1];

    if (!s_guest.on_ground
            || (m->floor != NULL
                && m->pos[1] > m->floorHeight + 100.0f)) {
        m->input |= INPUT_OFF_FLOOR;
    }
    if (m->pos[1] < m->waterLevel - 10) {
        m->input |= INPUT_IN_WATER;
    }

    if (m->controller != NULL) {
        if (m->controller->buttonPressed & A_BUTTON) {
            m->input |= INPUT_A_PRESSED;
        }
        if (m->controller->buttonDown & A_BUTTON) {
            m->input |= INPUT_A_DOWN;
        }
        if (m->controller->buttonPressed & B_BUTTON) {
            m->input |= INPUT_B_PRESSED;
        }
        if (m->controller->buttonDown & Z_TRIG) {
            m->input |= INPUT_Z_DOWN;
        }
        if (m->controller->buttonPressed & Z_TRIG) {
            m->input |= INPUT_Z_PRESSED;
        }
    }

    m->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;
    return true;
}

static struct CrossmodBlockBox *crossmod_find_block_box(
        long long key
) {
    for (int i = 0; i < CROSSMOD_MAX_BLOCK_BOXES; ++i) {
        if (s_block_boxes[i].active
                && s_block_boxes[i].key == key) {
            return &s_block_boxes[i];
        }
    }

    return NULL;
}

static void crossmod_update_block_box(const char *text) {
    long long key;
    struct CrossmodBlockBox next;
    memset(&next, 0, sizeof(next));

    int count = sscanf(
            text,
            "{\"t\":\"box\",\"key\":%lld,"
            "\"min\":[%f,%f,%f],"
            "\"max\":[%f,%f,%f]}",
            &key,
            &next.min_x,
            &next.min_y,
            &next.min_z,
            &next.max_x,
            &next.max_y,
            &next.max_z
    );

    if (count != 7) {
        return;
    }

    struct CrossmodBlockBox *box =
            crossmod_find_block_box(key);

    if (box == NULL) {
        for (int i = 0; i < CROSSMOD_MAX_BLOCK_BOXES; ++i) {
            if (!s_block_boxes[i].active) {
                box = &s_block_boxes[i];
                break;
            }
        }
    }

    if (box == NULL) {
        return;
    }

    *box = next;
    box->key = key;
    box->active = 1;
}

static void crossmod_remove_block_box(const char *text) {
    long long key;

    if (sscanf(
            text,
            "{\"t\":\"unbox\",\"key\":%lld}",
            &key
        ) != 1) {
        return;
    }

    struct CrossmodBlockBox *box =
            crossmod_find_block_box(key);
    if (box != NULL) {
        memset(box, 0, sizeof(*box));
    }
}

static void crossmod_receive_minecraft_health(
        const char *text
) {
    float delta = 0.0f;

    if (sscanf(
            text,
            "{\"t\":\"mc_health\",\"delta\":%f}",
            &delta
        ) != 1) {
        return;
    }

    if (delta > 20.0f) {
        delta = 20.0f;
    }
    if (delta < -20.0f) {
        delta = -20.0f;
    }

    s_pending_mc_health_delta += delta;

    if (s_pending_mc_health_delta > 20.0f) {
        s_pending_mc_health_delta = 20.0f;
    }
    if (s_pending_mc_health_delta < -20.0f) {
        s_pending_mc_health_delta = -20.0f;
    }
}

static int parse_guest_packet(
        const char *text,
        struct CrossmodGuestState *guest
) {
    if (text == NULL
            || strncmp(text, "{\"t\":\"guest\"", 12) != 0) {
        return 0;
    }

    int count = sscanf(
            text,
            "{\"t\":\"guest\",\"seq\":%lu,\"item\":\"%95[^\"]\","
            "\"slot\":%d,\"weapon\":\"%23[^\"]\","
            "\"reach\":%f,\"power\":%d,\"screen\":%d,"
            "\"health\":%f,\"food\":%d,"
            "\"pos\":[%f,%f,%f],"
            "\"vel\":[%f,%f,%f],"
            "\"yaw\":%f,\"pitch\":%f,\"body\":%f,"
            "\"ground\":%d,\"sneak\":%d,\"sprint\":%d}",
            &guest->sequence,
            guest->held_item,
            &guest->selected_slot,
            guest->weapon_kind,
            &guest->reach_blocks,
            &guest->power,
            &guest->screen_open,
            &guest->health,
            &guest->food,
            &guest->player_x,
            &guest->player_y,
            &guest->player_z,
            &guest->velocity_x,
            &guest->velocity_y,
            &guest->velocity_z,
            &guest->yaw,
            &guest->pitch,
            &guest->body_yaw,
            &guest->on_ground,
            &guest->sneaking,
            &guest->sprinting
    );

    return count == 21;
}

#ifdef _WIN32

static int crossmod_key_down(int virtual_key) {
    return (GetAsyncKeyState(virtual_key) & 0x8000) != 0;
}

static int crossmod_host_has_focus(void) {
    HWND window = GetForegroundWindow();
    if (window == NULL) {
        return 0;
    }

    DWORD process_id = 0;
    GetWindowThreadProcessId(window, &process_id);
    return process_id == GetCurrentProcessId();
}

static void crossmod_send_slot(int slot) {
    char message[96];
    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"slot\",\"slot\":%d}",
            slot
    );
    crossmod_ws_send(message);
}

static void crossmod_send_inventory_toggle(void) {
    crossmod_ws_send("{\"t\":\"inventory\"}");
}

static void crossmod_send_simple_command(const char *type) {
    char message[64];
    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"%s\"}",
            type
    );
    crossmod_ws_send(message);
}

static void crossmod_send_drop(int stack) {
    char message[64];
    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"drop\",\"stack\":%d}",
            stack
    );
    crossmod_ws_send(message);
}

static float crossmod_clamp01(float value) {
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 1.0f) {
        return 1.0f;
    }
    return value;
}

static int crossmod_gui_modifiers(void) {
    int modifiers = 0;

    if (crossmod_key_down(VK_SHIFT)
            || crossmod_key_down(VK_LSHIFT)
            || crossmod_key_down(VK_RSHIFT)) {
        modifiers |= 0x0001; /* GLFW_MOD_SHIFT */
    }

    if (crossmod_key_down(VK_CONTROL)
            || crossmod_key_down(VK_LCONTROL)
            || crossmod_key_down(VK_RCONTROL)) {
        modifiers |= 0x0002; /* GLFW_MOD_CONTROL */
    }

    if (crossmod_key_down(VK_MENU)
            || crossmod_key_down(VK_LMENU)
            || crossmod_key_down(VK_RMENU)) {
        modifiers |= 0x0004; /* GLFW_MOD_ALT */
    }

    if (crossmod_key_down(VK_LWIN)
            || crossmod_key_down(VK_RWIN)) {
        modifiers |= 0x0008; /* GLFW_MOD_SUPER */
    }

    return modifiers;
}

static int crossmod_unicode_for_key(int virtual_key) {
    BYTE keyboard[256];
    if (!GetKeyboardState(keyboard)) {
        return 0;
    }

    WCHAR chars[8];
    UINT scan = MapVirtualKeyW(
            (UINT) virtual_key,
            MAPVK_VK_TO_VSC
    );

    int count = ToUnicode(
            (UINT) virtual_key,
            scan,
            keyboard,
            chars,
            8,
            0
    );

    if (count <= 0) {
        return 0;
    }

    WCHAR first = chars[0];

    if (count >= 2
            && first >= 0xD800
            && first <= 0xDBFF
            && chars[1] >= 0xDC00
            && chars[1] <= 0xDFFF) {
        return 0x10000
                + (((int) first - 0xD800) << 10)
                + ((int) chars[1] - 0xDC00);
    }

    return (int) first;
}

static void crossmod_send_gui_keyboard(void) {
    int modifiers = crossmod_gui_modifiers();

    for (int key = 8; key < 256; ++key) {
        int down = crossmod_key_down(key);
        int old = s_gui_prev_keys[key] != 0;

        if (down == old) {
            continue;
        }

        s_gui_prev_keys[key] = down ? 1 : 0;

        /*
         * E and Escape are handled as cross-window screen controls so they
         * behave consistently even when Minecraft has no OS focus.
         */
        if (key == 'E' || key == VK_ESCAPE) {
            continue;
        }

        int code_point =
                down ? crossmod_unicode_for_key(key) : 0;

        char message[160];
        snprintf(
                message,
                sizeof(message),
                "{\"t\":\"key\",\"vk\":%d,\"down\":%d,"
                "\"mods\":%d,\"cp\":%d}",
                key,
                down ? 1 : 0,
                modifiers,
                code_point
        );
        crossmod_ws_send(message);
    }
}

static void crossmod_send_movement_input(void) {
    if (!crossmod_ws_connected() || !s_has_guest) {
        return;
    }

    int enabled = !s_guest.screen_open;
    int forward = enabled && (s_host_keys & 1u);
    int back = enabled && (s_host_keys & 2u);
    int left = enabled && (s_host_keys & 4u);
    int right = enabled && (s_host_keys & 8u);
    int jump = enabled && (s_host_keys & 16u);
    int sneak = enabled && (s_host_keys & 32u);
    int sprint = enabled && (s_host_keys & 64u);

    char message[256];
    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"move\","
            "\"f\":%d,\"b\":%d,\"l\":%d,\"r\":%d,"
            "\"jump\":%d,\"sneak\":%d,\"sprint\":%d}",
            forward ? 1 : 0,
            back ? 1 : 0,
            left ? 1 : 0,
            right ? 1 : 0,
            jump ? 1 : 0,
            sneak ? 1 : 0,
            sprint ? 1 : 0
    );

    crossmod_ws_send(message);
}

static void crossmod_send_pointer(void) {
    if (!s_guest.screen_open) {
        return;
    }

    HWND window = GetForegroundWindow();
    if (window == NULL) {
        return;
    }

    POINT point;
    RECT rect;

    if (!GetCursorPos(&point)
            || !ScreenToClient(window, &point)
            || !GetClientRect(window, &rect)) {
        return;
    }

    int width = rect.right - rect.left;
    int height = rect.bottom - rect.top;

    if (width <= 0 || height <= 0) {
        return;
    }

    float x = crossmod_clamp01(
            (float) point.x / (float) width
    );
    float y = crossmod_clamp01(
            (float) point.y / (float) height
    );

    char message[256];
    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"pointer\",\"x\":%.6f,\"y\":%.6f,"
            "\"left\":%lu,\"right\":%lu,\"ld\":%d,\"rd\":%d}",
            x,
            y,
            s_attack_serial,
            s_use_serial,
            s_attack_down,
            s_use_down
    );

    crossmod_ws_send(message);
}

static int crossmod_pick_sm64_surface(
        struct CrossmodSurfaceHit *hit
) {
    if (hit == NULL
            || gCurrentArea == NULL
            || gCurrentArea->camera == NULL) {
        return 0;
    }

    float ox = gLakituState.curPos[0];
    float oy = gLakituState.curPos[1];
    float oz = gLakituState.curPos[2];

    float dx = gLakituState.curFocus[0] - ox;
    float dy = gLakituState.curFocus[1] - oy;
    float dz = gLakituState.curFocus[2] - oz;

    float length = sqrtf(dx * dx + dy * dy + dz * dz);
    if (length < 0.001f) {
        return 0;
    }

    dx /= length;
    dy /= length;
    dz /= length;

    const float max_distance = 650.0f;
    const float step = 20.0f;

    for (float distance = 40.0f;
         distance <= max_distance;
         distance += step) {
        float x = ox + dx * distance;
        float y = oy + dy * distance;
        float z = oz + dz * distance;

        struct Surface *floor = NULL;
        float floor_y = find_floor(
                x,
                y + 80.0f,
                z,
                &floor
        );

        if (floor != NULL
                && fabsf(y - floor_y) <= 24.0f) {
            hit->valid = 1;
            hit->x = x;
            hit->y = floor_y;
            hit->z = z;
            hit->nx = floor->normal.x;
            hit->ny = floor->normal.y;
            hit->nz = floor->normal.z;
            return 1;
        }

        struct Surface *ceil = NULL;
        float ceil_y = find_ceil(
                x,
                y - 80.0f,
                z,
                &ceil
        );

        if (ceil != NULL
                && fabsf(ceil_y - y) <= 24.0f) {
            hit->valid = 1;
            hit->x = x;
            hit->y = ceil_y;
            hit->z = z;
            hit->nx = ceil->normal.x;
            hit->ny = ceil->normal.y;
            hit->nz = ceil->normal.z;
            return 1;
        }

        struct WallCollisionData wall;
        memset(&wall, 0, sizeof(wall));
        wall.x = x;
        wall.y = y;
        wall.z = z;
        wall.offsetY = 0.0f;
        wall.radius = 18.0f;

        if (find_wall_collisions(&wall) > 0
                && wall.numWalls > 0
                && wall.walls[0] != NULL) {
            struct Surface *surface = wall.walls[0];

            hit->valid = 1;
            hit->x = x;
            hit->y = y;
            hit->z = z;
            hit->nx = surface->normal.x;
            hit->ny = surface->normal.y;
            hit->nz = surface->normal.z;
            return 1;
        }
    }

    memset(hit, 0, sizeof(*hit));
    return 0;
}

static void crossmod_send_gameplay_action(void) {
    if (!crossmod_ws_connected()
            || s_guest.screen_open) {
        return;
    }

    struct CrossmodSurfaceHit hit;
    memset(&hit, 0, sizeof(hit));
    crossmod_pick_sm64_surface(&hit);

    char message[512];

    if (hit.valid) {
        snprintf(
                message,
                sizeof(message),
                "{\"t\":\"action\",\"attack\":%lu,\"use\":%lu,"
                "\"ad\":%d,\"ud\":%d,\"hit\":1,"
                "\"p\":[%.6f,%.6f,%.6f],"
                "\"n\":[%.6f,%.6f,%.6f]}",
                s_attack_serial,
                s_use_serial,
                s_attack_down,
                s_use_down,
                hit.x / CROSSMOD_SCALE,
                hit.y / CROSSMOD_SCALE,
                -hit.z / CROSSMOD_SCALE,
                hit.nx,
                hit.ny,
                -hit.nz
        );
    } else {
        snprintf(
                message,
                sizeof(message),
                "{\"t\":\"action\",\"attack\":%lu,\"use\":%lu,"
                "\"ad\":%d,\"ud\":%d,\"hit\":0}",
                s_attack_serial,
                s_use_serial,
                s_attack_down,
                s_use_down
        );
    }

    crossmod_ws_send(message);
}

static void crossmod_update_mouse_look(void) {
    if (s_guest.screen_open) {
        s_mouse_ready = 0;
        return;
    }

    HWND window = GetForegroundWindow();
    if (window == NULL) {
        s_mouse_ready = 0;
        return;
    }

    RECT rect;
    if (!GetClientRect(window, &rect)) {
        return;
    }

    POINT center;
    center.x = (rect.right - rect.left) / 2;
    center.y = (rect.bottom - rect.top) / 2;

    POINT screen_center = center;
    if (!ClientToScreen(window, &screen_center)) {
        return;
    }

    POINT cursor;
    if (!GetCursorPos(&cursor)) {
        return;
    }

    if (!s_mouse_ready) {
        SetCursorPos(screen_center.x, screen_center.y);
        s_mouse_ready = 1;
        return;
    }

    int dx = cursor.x - screen_center.x;
    int dy = cursor.y - screen_center.y;

    if (dx != 0 || dy != 0) {
        char message[128];
        snprintf(
                message,
                sizeof(message),
                "{\"t\":\"look\",\"dx\":%d,\"dy\":%d}",
                dx,
                dy
        );
        crossmod_ws_send(message);
    }

    SetCursorPos(screen_center.x, screen_center.y);
}

static void crossmod_capture_host_input(void) {
    if (!crossmod_host_has_focus()) {
        s_host_keys = 0;
        s_attack_down = 0;
        s_use_down = 0;
        s_prev_attack_down = 0;
        s_prev_use_down = 0;
        s_prev_slot_mask = 0;
        s_prev_inventory_down = 0;
        s_prev_view_down = 0;
        s_prev_hud_down = 0;
        s_prev_drop_down = 0;
        s_prev_swap_down = 0;
        s_prev_escape_down = 0;
        s_prev_chat_down = 0;
        s_prev_command_down = 0;
        memset(s_gui_prev_keys, 0, sizeof(s_gui_prev_keys));
        s_mouse_ready = 0;
        return;
    }

    RECT host_rect;
    HWND host_window = GetForegroundWindow();
    if (host_window != NULL
            && GetClientRect(host_window, &host_rect)) {
        int width = host_rect.right - host_rect.left;
        int height = host_rect.bottom - host_rect.top;
        if (width > 0 && height > 0) {
            s_host_client_width = width;
            s_host_client_height = height;
        }
    }

    unsigned int keys = 0;

    if (crossmod_key_down('W')) keys |= 1u;
    if (crossmod_key_down('S')) keys |= 2u;
    if (crossmod_key_down('A')) keys |= 4u;
    if (crossmod_key_down('D')) keys |= 8u;
    if (crossmod_key_down(VK_SPACE)) keys |= 16u;
    if (crossmod_key_down(VK_SHIFT)) keys |= 32u;
    if (crossmod_key_down(VK_CONTROL)) keys |= 64u;
    if (crossmod_key_down('P')) keys |= 128u;
    if (crossmod_key_down('I')) keys |= 256u;
    if (crossmod_key_down('K')) keys |= 512u;
    if (crossmod_key_down('J')) keys |= 1024u;
    if (crossmod_key_down('L')) keys |= 2048u;
    if (crossmod_key_down('O')) keys |= 4096u;
    if (crossmod_key_down('U')) keys |= 8192u;
    if (crossmod_key_down('V')) keys |= 16384u;

    s_host_keys = keys;

    int attack_down = crossmod_key_down(VK_LBUTTON);
    int use_down = crossmod_key_down(VK_RBUTTON);

    if (attack_down && !s_prev_attack_down) {
        s_attack_serial++;
    }
    if (use_down && !s_prev_use_down) {
        s_use_serial++;
    }

    s_attack_down = attack_down;
    s_use_down = use_down;
    s_prev_attack_down = attack_down;
    s_prev_use_down = use_down;

    int inventory_down = crossmod_key_down('E');
    if (inventory_down && !s_prev_inventory_down) {
        crossmod_send_inventory_toggle();
    }
    s_prev_inventory_down = inventory_down;

    int view_down = crossmod_key_down(VK_F5);
    if (view_down && !s_prev_view_down && !s_guest.screen_open) {
        s_view_mode = (s_view_mode + 1) % 3;
    }
    s_prev_view_down = view_down;

    int hud_down = crossmod_key_down(VK_F1);
    if (hud_down && !s_prev_hud_down && !s_guest.screen_open) {
        crossmod_send_simple_command("hud");
    }
    s_prev_hud_down = hud_down;

    int drop_down = crossmod_key_down('Q');
    if (drop_down && !s_prev_drop_down && !s_guest.screen_open) {
        crossmod_send_drop(
                crossmod_key_down(VK_CONTROL) ? 1 : 0
        );
    }
    s_prev_drop_down = drop_down;

    int swap_down = crossmod_key_down('F');
    if (swap_down && !s_prev_swap_down && !s_guest.screen_open) {
        crossmod_send_simple_command("swap");
    }
    s_prev_swap_down = swap_down;

    int escape_down = crossmod_key_down(VK_ESCAPE);
    if (escape_down && !s_prev_escape_down && s_guest.screen_open) {
        crossmod_send_simple_command("escape");
    }
    s_prev_escape_down = escape_down;

    int chat_down = crossmod_key_down('T');
    if (chat_down && !s_prev_chat_down && !s_guest.screen_open) {
        crossmod_send_simple_command("chat");
    }
    s_prev_chat_down = chat_down;

    int command_down = crossmod_key_down(VK_OEM_2);
    if (command_down
            && !s_prev_command_down
            && !s_guest.screen_open) {
        crossmod_send_simple_command("command");
    }
    s_prev_command_down = command_down;

    if (!s_guest.screen_open) {
        crossmod_update_mouse_look();

        unsigned int slot_mask = 0;

        for (int slot = 0; slot < 9; ++slot) {
            if (crossmod_key_down('1' + slot)) {
                unsigned int bit = 1u << slot;
                slot_mask |= bit;

                if ((s_prev_slot_mask & bit) == 0) {
                    crossmod_send_slot(slot);
                }
            }
        }

        s_prev_slot_mask = slot_mask;
    } else {
        s_prev_slot_mask = 0;
        crossmod_send_pointer();
        crossmod_send_gui_keyboard();
    }

    crossmod_send_movement_input();

    if (!s_guest.screen_open) {
        crossmod_send_gameplay_action();
    }
}

#else

static void crossmod_capture_host_input(void) {
    s_host_keys = 0;
    s_attack_down = 0;
    s_use_down = 0;
}

#endif

void crossmod_bridge_poll(void) {
    char buffer[4096];

    if (!crossmod_ws_connected()) {
        s_has_guest = 0;
        s_proxy_armed = 0;
        s_proxy_wait_frames = 0;
        crossmod_capture_host_input();
        return;
    }

    while (crossmod_ws_poll_message(buffer, sizeof(buffer))) {
        if (strncmp(buffer, "{\"t\":\"mc_health\"", 16) == 0) {
            crossmod_receive_minecraft_health(buffer);
            continue;
        }

        if (strncmp(buffer, "{\"t\":\"box\"", 10) == 0) {
            crossmod_update_block_box(buffer);
            continue;
        }

        if (strncmp(buffer, "{\"t\":\"unbox\"", 12) == 0) {
            crossmod_remove_block_box(buffer);
            continue;
        }

        struct CrossmodGuestState next;
        memset(&next, 0, sizeof(next));

        if (!parse_guest_packet(buffer, &next)) {
            continue;
        }

        s_guest = next;

        /*
         * Minecraft owns view rotation. The visible SM64 camera follows the
         * real vanilla player yaw/pitch reported by the guest.
         */
        s_view_yaw = next.yaw;
        s_view_pitch = next.pitch;
        s_view_initialized = 1;
        s_has_guest = 1;
    }

    if (s_has_guest) {
        crossmod_capture_host_input();
    }
}

static void crossmod_adjust_stick(struct Controller *controller) {
    controller->stickX = 0.0f;
    controller->stickY = 0.0f;

    if (controller->rawStickX <= -8) {
        controller->stickX = controller->rawStickX + 6;
    }
    if (controller->rawStickX >= 8) {
        controller->stickX = controller->rawStickX - 6;
    }
    if (controller->rawStickY <= -8) {
        controller->stickY = controller->rawStickY + 6;
    }
    if (controller->rawStickY >= 8) {
        controller->stickY = controller->rawStickY - 6;
    }

    controller->stickMag = sqrtf(
            controller->stickX * controller->stickX
            + controller->stickY * controller->stickY
    );

    if (controller->stickMag > 64.0f) {
        controller->stickX *= 64.0f / controller->stickMag;
        controller->stickY *= 64.0f / controller->stickMag;
        controller->stickMag = 64.0f;
    }
}

void crossmod_bridge_apply_controller(struct Controller *controller) {
    if (!s_has_guest || controller == NULL) {
        return;
    }

    /*
     * Mario locomotion is disabled. Keep only a tiny native-button channel
     * for original mission interactions/cutscenes; all walking, jumping,
     * sprinting, crouching and gravity are vanilla Minecraft.
     */
    controller->rawStickX = 0;
    controller->rawStickY = 0;
    controller->stickX = 0.0f;
    controller->stickY = 0.0f;
    controller->stickMag = 0.0f;

    u16 buttons = 0;

    if (!s_guest.screen_open) {
        if (s_host_keys & 128u) buttons |= START_BUTTON;

        /*
         * Right click is the natural "use" input. Feed it to native SM64
         * interactions as B as well, while the Minecraft guest independently
         * handles block/item use. V remains an explicit native fallback.
         */
        if (s_use_down || (s_host_keys & 16384u)) {
            buttons |= B_BUTTON;
        }

        if (s_host_keys & 32u) {
            buttons |= Z_TRIG;
        }
    }

    controller->buttonPressed =
            buttons & (buttons ^ controller->buttonDown);
    controller->buttonDown = buttons;
}

static int crossmod_is_attackable_object(const struct Object *obj) {
    if (obj == NULL || obj == gMarioObject) {
        return 0;
    }

    if ((obj->activeFlags & ACTIVE_FLAG_ACTIVE) == 0) {
        return 0;
    }

    if (obj->oInteractType == 0) {
        return 0;
    }

    return (obj->oInteractType & CROSSMOD_ENEMY_INTERACT_MASK) != 0;
}

static void crossmod_view_forward(
        float *x,
        float *y,
        float *z
) {
    const float d2r =
            3.14159265358979323846f / 180.0f;
    float yaw = s_view_yaw * d2r;
    float pitch = s_view_pitch * d2r;
    float cp = cosf(pitch);

    *x = -sinf(yaw) * cp;
    *y = -sinf(pitch);
    *z = cosf(yaw) * cp;
}

static float crossmod_clamp_melee_reach(float reach_blocks) {
    float reach = reach_blocks * CROSSMOD_SCALE;

    if (reach < CROSSMOD_MIN_MELEE_REACH) {
        reach = CROSSMOD_MIN_MELEE_REACH;
    }
    if (reach > CROSSMOD_MAX_MELEE_REACH) {
        reach = CROSSMOD_MAX_MELEE_REACH;
    }

    return reach;
}

static struct Object *crossmod_find_melee_target(
        struct MarioState *m,
        float reach
) {
    static const int combat_lists[] = {
        OBJ_LIST_PUSHABLE,
        OBJ_LIST_GENACTOR,
        OBJ_LIST_DESTRUCTIVE,
        OBJ_LIST_DEFAULT,
        OBJ_LIST_SURFACE
    };

    struct Object *best = NULL;
    float best_score = 1000000000.0f;
    float forward_x;
    float forward_y;
    float forward_z;
    crossmod_view_forward(
            &forward_x,
            &forward_y,
            &forward_z
    );

    int list_index;
    for (list_index = 0;
         list_index < (int) (sizeof(combat_lists) / sizeof(combat_lists[0]));
         list_index++) {
        struct ObjectNode *list = &gObjectLists[combat_lists[list_index]];
        struct ObjectNode *node = list->next;

        while (node != list) {
            struct Object *obj = (struct Object *) node;
            node = node->next;

            if (!crossmod_is_attackable_object(obj)) {
                continue;
            }

            float dx = obj->oPosX - m->pos[0];
            float dy = (obj->oPosY + obj->hurtboxHeight * 0.5f)
                    - (m->pos[1] + 100.0f);
            float dz = obj->oPosZ - m->pos[2];

            float distance_sq =
                    dx * dx + dy * dy + dz * dz;
            float distance = sqrtf(distance_sq);

            float target_radius = obj->hurtboxRadius;
            if (target_radius < 40.0f) {
                target_radius = 40.0f;
            }

            float allowed = reach + target_radius;
            if (distance > allowed || distance < 1.0f) {
                continue;
            }

            float facing =
                    (dx * forward_x
                    + dy * forward_y
                    + dz * forward_z)
                    / distance;

            if (facing < CROSSMOD_ATTACK_HALF_ANGLE_COS) {
                continue;
            }

            float score = distance - facing * 120.0f;
            if (score < best_score) {
                best_score = score;
                best = obj;
            }
        }
    }

    return best;
}

static void crossmod_attack_object(
        struct MarioState *m,
        struct Object *target,
        int attack_type
) {
    if (target == NULL) {
        return;
    }

    target->oInteractStatus =
            attack_type
            | INT_STATUS_INTERACTED
            | INT_STATUS_WAS_ATTACKED;

    m->interactObj = target;
}

static struct Object *crossmod_find_ranged_target(
        struct MarioState *m,
        float reach
) {
    static const int combat_lists[] = {
        OBJ_LIST_PUSHABLE,
        OBJ_LIST_GENACTOR,
        OBJ_LIST_DESTRUCTIVE,
        OBJ_LIST_DEFAULT,
        OBJ_LIST_SURFACE
    };

    float forward_x;
    float forward_y;
    float forward_z;
    crossmod_view_forward(
            &forward_x,
            &forward_y,
            &forward_z
    );

    struct Object *best = NULL;
    float best_t = reach + 1.0f;

    int list_index;
    for (list_index = 0;
         list_index < (int) (sizeof(combat_lists) / sizeof(combat_lists[0]));
         list_index++) {
        struct ObjectNode *list = &gObjectLists[combat_lists[list_index]];
        struct ObjectNode *node = list->next;

        while (node != list) {
            struct Object *obj = (struct Object *) node;
            node = node->next;

            if (!crossmod_is_attackable_object(obj)) {
                continue;
            }

            float dx = obj->oPosX - m->pos[0];
            float dy =
                    (obj->oPosY
                    + obj->hurtboxHeight * 0.5f)
                    - (m->pos[1] + 120.0f);
            float dz = obj->oPosZ - m->pos[2];

            float t =
                    dx * forward_x
                    + dy * forward_y
                    + dz * forward_z;

            if (t <= 0.0f || t > reach || t >= best_t) {
                continue;
            }

            float distance_sq =
                    dx * dx + dy * dy + dz * dz;
            float perpendicular_sq =
                    distance_sq - t * t;
            if (perpendicular_sq < 0.0f) {
                perpendicular_sq = 0.0f;
            }

            float radius =
                    obj->hurtboxRadius + 70.0f;
            if (radius < 90.0f) {
                radius = 90.0f;
            }

            if (perpendicular_sq <= radius * radius) {
                best = obj;
                best_t = t;
            }
        }
    }

    return best;
}

static int crossmod_explode_near_mario(
        struct MarioState *m,
        float radius
) {
    static const int combat_lists[] = {
        OBJ_LIST_PUSHABLE,
        OBJ_LIST_GENACTOR,
        OBJ_LIST_DESTRUCTIVE,
        OBJ_LIST_DEFAULT,
        OBJ_LIST_SURFACE
    };

    float radius_sq = radius * radius;
    int hits = 0;

    int list_index;
    for (list_index = 0;
         list_index < (int) (sizeof(combat_lists) / sizeof(combat_lists[0]));
         list_index++) {
        struct ObjectNode *list = &gObjectLists[combat_lists[list_index]];
        struct ObjectNode *node = list->next;

        while (node != list) {
            struct Object *obj = (struct Object *) node;
            node = node->next;

            if (!crossmod_is_attackable_object(obj)) {
                continue;
            }

            float dx = obj->oPosX - m->pos[0];
            float dy = obj->oPosY - m->pos[1];
            float dz = obj->oPosZ - m->pos[2];
            float distance_sq = dx * dx + dy * dy + dz * dz;

            if (distance_sq <= radius_sq) {
                crossmod_attack_object(
                    m,
                    obj,
                    ATTACK_KICK_OR_TRIP
                );
                hits++;
            }
        }
    }

    return hits;
}

static float crossmod_clamp_unit(float value) {
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 1.0f) {
        return 1.0f;
    }
    return value;
}

static void crossmod_send_terrain_box(
        int block_x,
        int block_y,
        int block_z,
        float min_x,
        float min_y,
        float min_z,
        float max_x,
        float max_y,
        float max_z
) {
    min_x = crossmod_clamp_unit(min_x);
    min_y = crossmod_clamp_unit(min_y);
    min_z = crossmod_clamp_unit(min_z);
    max_x = crossmod_clamp_unit(max_x);
    max_y = crossmod_clamp_unit(max_y);
    max_z = crossmod_clamp_unit(max_z);

    if (max_x - min_x < 0.001f
            || max_y - min_y < 0.001f
            || max_z - min_z < 0.001f) {
        return;
    }

    char message[256];
    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"terrain_box\","
            "\"x\":%d,\"y\":%d,\"z\":%d,"
            "\"min\":[%.5f,%.5f,%.5f],"
            "\"max\":[%.5f,%.5f,%.5f]}",
            block_x,
            block_y,
            block_z,
            min_x,
            min_y,
            min_z,
            max_x,
            max_y,
            max_z
    );
    crossmod_ws_send(message);
}

static void crossmod_send_floor_sample(
        int block_x,
        int block_z,
        int sub_x,
        int sub_z,
        float floor_y
) {
    const float subdivision = 2.0f;
    float minecraft_floor =
            floor_y / CROSSMOD_SCALE
            + (float) CROSSMOD_OVERLAY_ORIGIN_Y;

    /*
     * Put integer-height floors in the block below them so the collision top
     * remains exactly on the SM64 plane instead of moving one block upward.
     */
    int block_y = (int) floorf(minecraft_floor - 0.0001f);
    float top = minecraft_floor - (float) block_y;
    top = crossmod_clamp_unit(top);

    if (top < 0.01f) {
        top = 0.01f;
    }

    float min_x = (float) sub_x / subdivision;
    float max_x = (float) (sub_x + 1) / subdivision;
    float min_z = (float) sub_z / subdivision;
    float max_z = (float) (sub_z + 1) / subdivision;

    crossmod_send_terrain_box(
            block_x,
            block_y,
            block_z,
            min_x,
            0.0f,
            min_z,
            max_x,
            top,
            max_z
    );
}

static void crossmod_send_wall_sample(
        const struct Surface *surface,
        int block_x,
        int block_z,
        float sample_x,
        float wall_y,
        float sample_z
) {
    if (surface == NULL) {
        return;
    }

    float minecraft_y =
            wall_y / CROSSMOD_SCALE
            + (float) CROSSMOD_OVERLAY_ORIGIN_Y;
    int block_y = (int) floorf(minecraft_y);

    const float half_thickness = 0.055f;
    float normal_x = surface->normal.x;
    float normal_z = surface->normal.z;

    if (fabsf(normal_x) >= fabsf(normal_z)
            && fabsf(normal_x) > 0.001f) {
        float wall_x = -(
                surface->normal.y * wall_y
                + surface->normal.z * sample_z
                + surface->originOffset
        ) / normal_x;

        float local_x =
                wall_x / CROSSMOD_SCALE
                - (float) block_x;

        if (local_x < -0.20f || local_x > 1.20f) {
            return;
        }

        local_x = crossmod_clamp_unit(local_x);

        crossmod_send_terrain_box(
                block_x,
                block_y,
                block_z,
                local_x - half_thickness,
                0.0f,
                0.0f,
                local_x + half_thickness,
                1.0f,
                1.0f
        );
        return;
    }

    if (fabsf(normal_z) > 0.001f) {
        float wall_z = -(
                surface->normal.x * sample_x
                + surface->normal.y * wall_y
                + surface->originOffset
        ) / normal_z;

        float minecraft_z = -wall_z / CROSSMOD_SCALE;
        float local_z =
                minecraft_z - (float) block_z;

        if (local_z < -0.20f || local_z > 1.20f) {
            return;
        }

        local_z = crossmod_clamp_unit(local_z);

        crossmod_send_terrain_box(
                block_x,
                block_y,
                block_z,
                0.0f,
                0.0f,
                local_z - half_thickness,
                1.0f,
                1.0f,
                local_z + half_thickness
        );
    }
}

static void crossmod_send_ceiling_sample(
        int block_x,
        int block_z,
        float ceil_y
) {
    float minecraft_ceil =
            ceil_y / CROSSMOD_SCALE
            + (float) CROSSMOD_OVERLAY_ORIGIN_Y;
    int block_y = (int) floorf(minecraft_ceil);
    float bottom =
            crossmod_clamp_unit(
                    minecraft_ceil - (float) block_y
            );

    crossmod_send_terrain_box(
            block_x,
            block_y,
            block_z,
            0.0f,
            bottom,
            0.0f,
            1.0f,
            1.0f,
            1.0f
    );
}

static void crossmod_publish_terrain_proxy(
        const struct MarioState *m
) {
    if (m == NULL || !crossmod_ws_connected()) {
        return;
    }

    if (++s_terrain_tick < CROSSMOD_TERRAIN_INTERVAL) {
        return;
    }
    s_terrain_tick = 0;

    int center_x = (int) floorf(
            m->pos[0] / CROSSMOD_SCALE
    );
    int center_z = (int) floorf(
            -m->pos[2] / CROSSMOD_SCALE
    );

    char message[192];

    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"terrain_begin\",\"seq\":%lu}",
            ++s_terrain_sequence
    );
    crossmod_ws_send(message);

    for (int dz = -CROSSMOD_TERRAIN_RADIUS;
         dz <= CROSSMOD_TERRAIN_RADIUS;
         ++dz) {
        for (int dx = -CROSSMOD_TERRAIN_RADIUS;
             dx <= CROSSMOD_TERRAIN_RADIUS;
             ++dx) {
            int block_x = center_x + dx;
            int block_z = center_z + dz;

            /*
             * Four quarter-cell samples retain the exact floor height inside
             * a Minecraft block. Slopes therefore feel like the SM64 triangle
             * surface instead of one-block-tall staircase chunks.
             */
            for (int sub_z = 0; sub_z < 2; ++sub_z) {
                for (int sub_x = 0; sub_x < 2; ++sub_x) {
                    float sample_x =
                            ((float) block_x
                                + ((float) sub_x + 0.5f) / 2.0f)
                            * CROSSMOD_SCALE;
                    float sample_z =
                            -((float) block_z
                                + ((float) sub_z + 0.5f) / 2.0f)
                            * CROSSMOD_SCALE;

                    struct Surface *floor = NULL;
                    float floor_y = find_floor(
                            sample_x,
                            m->pos[1] + 500.0f,
                            sample_z,
                            &floor
                    );

                    if (floor == NULL
                            || (floor->flags & SURFACE_FLAG_DYNAMIC)
                            || fabsf(
                                floor_y - m->pos[1]
                            ) > 700.0f) {
                        continue;
                    }

                    crossmod_send_floor_sample(
                            block_x,
                            block_z,
                            sub_x,
                            sub_z,
                            floor_y
                    );
                }
            }

            float sample_x =
                    ((float) block_x + 0.5f)
                    * CROSSMOD_SCALE;
            float sample_z =
                    -((float) block_z + 0.5f)
                    * CROSSMOD_SCALE;

            struct Surface *center_floor = NULL;
            float floor_y = find_floor(
                    sample_x,
                    m->pos[1] + 500.0f,
                    sample_z,
                    &center_floor
            );

            if (center_floor == NULL
                    || (center_floor->flags
                        & SURFACE_FLAG_DYNAMIC)
                    || fabsf(floor_y - m->pos[1]) > 700.0f) {
                continue;
            }

            /*
             * Stream thin wall slices on the actual triangle plane rather
             * than marking the entire voxel as solid.
             */
            for (int layer = 0; layer < 4; ++layer) {
                float wall_y =
                        floor_y + 50.0f
                        + (float) layer * CROSSMOD_SCALE;

                struct WallCollisionData wall;
                memset(&wall, 0, sizeof(wall));
                wall.x = sample_x;
                wall.y = wall_y;
                wall.z = sample_z;
                wall.offsetY = 0.0f;
                wall.radius = 48.0f;

                if (find_wall_collisions(&wall) > 0
                        && wall.numWalls > 0
                        && wall.walls[0] != NULL
                        && !(wall.walls[0]->flags
                            & SURFACE_FLAG_DYNAMIC)) {
                    crossmod_send_wall_sample(
                            wall.walls[0],
                            block_x,
                            block_z,
                            sample_x,
                            wall_y,
                            sample_z
                    );
                }
            }

            struct Surface *ceil = NULL;
            float ceil_y = find_ceil(
                    sample_x,
                    floor_y + 50.0f,
                    sample_z,
                    &ceil
            );

            if (ceil != NULL
                    && !(ceil->flags & SURFACE_FLAG_DYNAMIC)
                    && ceil_y > floor_y + 80.0f
                    && ceil_y < floor_y + 650.0f) {
                crossmod_send_ceiling_sample(
                        block_x,
                        block_z,
                        ceil_y
                );
            }
        }
    }

    snprintf(
            message,
            sizeof(message),
            "{\"t\":\"terrain_end\",\"seq\":%lu}",
            s_terrain_sequence
    );
    crossmod_ws_send(message);
}

static void crossmod_apply_minecraft_health(
        struct MarioState *m
) {
    float delta = s_pending_mc_health_delta;
    s_pending_mc_health_delta = 0.0f;

    if (m == NULL || fabsf(delta) < 0.05f) {
        return;
    }

    /*
     * Live SM64 health spans about 0x800 units. update_mario_health changes
     * 0x40 per hurt/heal-counter tick, while Minecraft's default bar has 20
     * health points: 0x800 / 0x40 / 20 = 1.6 counter ticks per MC health.
     *
     * Minecraft has already applied armor, enchantments, effects and the
     * actual DamageSource before we receive the delta.
     */
    int counter =
            (int) ceilf(fabsf(delta) * 1.6f);
    if (counter < 1) {
        counter = 1;
    }

    if (delta < 0.0f) {
        int hurt = (int) m->hurtCounter + counter;
        m->hurtCounter = (u8) (hurt > 255 ? 255 : hurt);
    } else {
        int heal = (int) m->healCounter + counter;
        m->healCounter = (u8) (heal > 255 ? 255 : heal);
    }
}

static void crossmod_process_combat(struct MarioState *m) {
    if (s_guest.screen_open) {
        s_last_processed_attack_serial = s_attack_serial;
        s_last_processed_use_serial = s_use_serial;
        return;
    }

    if (s_attack_serial != 0
            && s_attack_serial != s_last_processed_attack_serial) {
        s_last_processed_attack_serial = s_attack_serial;
        s_last_hit_count = 0;

        if (strcmp(s_guest.weapon_kind, "ranged") != 0
                && strcmp(s_guest.weapon_kind, "explosive") != 0) {
            struct Object *target = crossmod_find_melee_target(
                    m,
                    crossmod_clamp_melee_reach(
                            s_guest.reach_blocks
                    )
            );

            if (target != NULL) {
                crossmod_attack_object(
                        m,
                        target,
                        ATTACK_KICK_OR_TRIP
                );
                s_last_hit_count =
                    s_guest.power > 0 ? s_guest.power : 1;
                s_last_hit_attack_serial =
                    s_attack_serial;
            }
        }
    }

    if (s_use_serial == 0
            || s_use_serial == s_last_processed_use_serial) {
        return;
    }

    s_last_processed_use_serial = s_use_serial;

    if (strcmp(s_guest.weapon_kind, "ranged") == 0
            || strcmp(s_guest.weapon_kind, "trident") == 0) {
        float reach = strcmp(s_guest.weapon_kind, "trident") == 0
            ? 2000.0f
            : 3000.0f;

        struct Object *target = crossmod_find_ranged_target(
                m,
                reach
        );

        if (target != NULL) {
            crossmod_attack_object(
                    m,
                    target,
                    ATTACK_KICK_OR_TRIP
            );
            s_last_hit_count =
                s_guest.power > 0 ? s_guest.power : 1;
            s_last_hit_attack_serial =
                s_use_serial;
        }
        return;
    }

    if (strcmp(s_guest.weapon_kind, "explosive") == 0) {
        int hits = crossmod_explode_near_mario(
                m,
                500.0f
        );
        s_last_hit_count = hits;
        s_last_hit_attack_serial = s_use_serial;
    }
}

static void crossmod_clip_third_person_camera(
        const Vec3f focus,
        Vec3f pos
) {
    Vec3f last_safe;
    vec3f_copy(last_safe, focus);

    float dx = pos[0] - focus[0];
    float dy = pos[1] - focus[1];
    float dz = pos[2] - focus[2];

    const int steps = 18;

    for (int i = 1; i <= steps; ++i) {
        float t = (float) i / (float) steps;
        Vec3f probe;

        probe[0] = focus[0] + dx * t;
        probe[1] = focus[1] + dy * t;
        probe[2] = focus[2] + dz * t;

        int blocked = 0;

        struct WallCollisionData wall;
        memset(&wall, 0, sizeof(wall));
        wall.x = probe[0];
        wall.y = probe[1];
        wall.z = probe[2];
        wall.offsetY = 0.0f;
        wall.radius = 28.0f;

        if (find_wall_collisions(&wall) > 0) {
            blocked = 1;
        }

        struct Surface *floor = NULL;
        float floor_y = find_floor(
                probe[0],
                probe[1] + 80.0f,
                probe[2],
                &floor
        );

        if (floor != NULL
                && probe[1] < floor_y + 24.0f) {
            blocked = 1;
        }

        struct Surface *ceil = NULL;
        float ceil_y = find_ceil(
                probe[0],
                probe[1] - 80.0f,
                probe[2],
                &ceil
        );

        if (ceil != NULL
                && probe[1] > ceil_y - 24.0f) {
            blocked = 1;
        }

        if (blocked) {
            vec3f_copy(pos, last_safe);
            return;
        }

        vec3f_copy(last_safe, probe);
    }
}

static void send_state(const struct MarioState *m);

void crossmod_bridge_override_camera(struct Camera *camera) {
    if (!s_has_guest
            || camera == NULL
            || gMarioState == NULL) {
        return;
    }

    if (!s_view_initialized) {
        float dx =
                gLakituState.curFocus[0]
                - gLakituState.curPos[0];
        float dy =
                gLakituState.curFocus[1]
                - gLakituState.curPos[1];
        float dz =
                gLakituState.curFocus[2]
                - gLakituState.curPos[2];
        float horizontal = sqrtf(dx * dx + dz * dz);

        s_view_yaw =
                atan2f(-dx, dz) * 57.295779513f;
        s_view_pitch =
                -atan2f(
                    dy,
                    horizontal > 0.0001f
                        ? horizontal
                        : 0.0001f
                ) * 57.295779513f;
        s_view_initialized = 1;
    }

    /*
     * Never replace authored SM64 cutscene cameras. Star grabs, doors,
     * Bowser scenes and course transitions stay 100% original.
     */
    if (camera->cutscene == 0 && !s_guest.screen_open) {
        const float d2r =
                3.14159265358979323846f / 180.0f;
        float yaw = s_view_yaw * d2r;
        float pitch = s_view_pitch * d2r;

        float cp = cosf(pitch);
        float forward_x = -sinf(yaw) * cp;
        float forward_y = -sinf(pitch);
        float forward_z = cosf(yaw) * cp;

        Vec3f focus;
        Vec3f pos;

        focus[0] = gMarioState->pos[0];
        focus[1] = gMarioState->pos[1] + 162.0f;
        focus[2] = gMarioState->pos[2];

        if (s_view_mode == 0) {
            /*
             * Minecraft-style first person: camera sits at Steve/Mario eye
             * height and the Minecraft hand/item is composited screen-space.
             */
            pos[0] = gMarioState->pos[0];
            pos[1] = gMarioState->pos[1] + 162.0f;
            pos[2] = gMarioState->pos[2];

            focus[0] = pos[0] + forward_x * 1000.0f;
            focus[1] = pos[1] + forward_y * 1000.0f;
            focus[2] = pos[2] + forward_z * 1000.0f;

            sFOVState.fov = 70.0f;
        } else if (s_view_mode == 2) {
            /* Minecraft third-person front. */
            pos[0] = focus[0] + forward_x * 400.0f;
            pos[1] = focus[1] + forward_y * 400.0f;
            pos[2] = focus[2] + forward_z * 400.0f;

            sFOVState.fov = 70.0f;
        } else {
            /* Minecraft third-person back. */
            pos[0] = focus[0] - forward_x * 400.0f;
            pos[1] = focus[1] - forward_y * 400.0f;
            pos[2] = focus[2] - forward_z * 400.0f;

            sFOVState.fov = 70.0f;
        }

        if (s_view_mode != 0) {
            crossmod_clip_third_person_camera(
                    focus,
                    pos
            );
        }

        vec3f_copy(camera->pos, pos);
        vec3f_copy(camera->focus, focus);
        vec3f_copy(gLakituState.goalPos, pos);
        vec3f_copy(gLakituState.curPos, pos);
        vec3f_copy(gLakituState.pos, pos);
        vec3f_copy(gLakituState.goalFocus, focus);
        vec3f_copy(gLakituState.curFocus, focus);
        vec3f_copy(gLakituState.focus, focus);
        gLakituState.roll = 0;
    }

    send_state(gMarioState);
}

static void send_state(const struct MarioState *m) {
    if (m == NULL) {
        return;
    }

    char response[2048];

    float camera_x = 0.0f;
    float camera_y = 0.0f;
    float camera_z = 0.0f;
    float focus_x = 0.0f;
    float focus_y = 0.0f;
    float focus_z = -1.0f;

    if (gCurrentArea != NULL && gCurrentArea->camera != NULL) {
        camera_x = gLakituState.curPos[0] / CROSSMOD_SCALE;
        camera_y = gLakituState.curPos[1] / CROSSMOD_SCALE;
        camera_z = -gLakituState.curPos[2] / CROSSMOD_SCALE;
        focus_x = gLakituState.curFocus[0] / CROSSMOD_SCALE;
        focus_y = gLakituState.curFocus[1] / CROSSMOD_SCALE;
        focus_z = -gLakituState.curFocus[2] / CROSSMOD_SCALE;
    }

    float dx = focus_x - camera_x;
    float dy = focus_y - camera_y;
    float dz = focus_z - camera_z;
    float horizontal = sqrtf(dx * dx + dz * dz);
    float yaw = atan2f(-dx, dz) * 57.295779513f;
    float pitch = -atan2f(
            dy,
            horizontal > 0.000001f ? horizontal : 0.000001f
    ) * 57.295779513f;

    float body_yaw =
            -(float) m->faceAngle[1] * 360.0f / 65536.0f;

    unsigned long host_frame = ++s_host_frame;

    s_render_pose.frame = host_frame;
    s_render_pose.camera_x = camera_x;
    s_render_pose.camera_y = camera_y;
    s_render_pose.camera_z = camera_z;
    s_render_pose.yaw = yaw;
    s_render_pose.pitch = pitch;
    s_render_pose.roll = 0.0f;
    s_render_pose.fov = sFOVState.fov;
    s_render_pose_valid = 1;

    if (!crossmod_ws_connected()) {
        return;
    }

    u32 save_flags = 0;
    u32 course_star_flags = 0;

    if (gCurrSaveFileNum > 0) {
        save_flags = save_file_get_flags();

        if (gCurrCourseNum > 0) {
            course_star_flags = save_file_get_star_flags(
                    gCurrSaveFileNum - 1,
                    gCurrCourseNum - 1
            );
        }
    }

    snprintf(
            response,
            sizeof(response),
            "{\"t\":\"cam\",\"f\":%lu,"
            "\"p\":[%.6f,%.6f,%.6f],"
            "\"r\":[%.4f,%.4f,0.0],"
            "\"fov\":%.3f,\"view\":%d,"
            "\"win\":[%d,%d],"
            "\"pl\":[%.6f,%.6f,%.6f],"
            "\"h\":%.4f,\"action\":%u,"
            "\"sneak\":%d,\"sprint\":%d,"
            "\"level\":%d,\"area\":%d,\"course\":%d,\"act\":%d,"
            "\"stars\":%d,\"health\":%d,"
            "\"save\":%lu,\"courseStars\":%lu,"
            "\"coins\":%d,\"lives\":%d,\"hud\":%d,\"timer\":%u,"
            "\"hitSerial\":%lu,\"hitCount\":%d}",
            host_frame,
            camera_x,
            camera_y,
            camera_z,
            yaw,
            pitch,
            (double) sFOVState.fov,
            s_view_mode,
            s_host_client_width,
            s_host_client_height,
            m->pos[0] / CROSSMOD_SCALE,
            m->pos[1] / CROSSMOD_SCALE,
            -m->pos[2] / CROSSMOD_SCALE,
            body_yaw,
            (unsigned int) m->action,
            (s_host_keys & 32u) ? 1 : 0,
            (s_host_keys & 64u) ? 1 : 0,
            (int) gCurrLevelNum,
            (int) gCurrAreaIndex,
            (int) gCurrCourseNum,
            (int) gCurrActNum,
            (int) m->numStars,
            (int) m->health,
            (unsigned long) save_flags,
            (unsigned long) course_star_flags,
            (int) m->numCoins,
            (int) m->numLives,
            (int) gHudDisplay.flags,
            (unsigned int) gHudDisplay.timer,
            s_last_hit_attack_serial,
            s_last_hit_count
    );

    crossmod_ws_send(response);
}

void crossmod_bridge_after_mario_update(struct MarioState *m) {
    if (!s_has_guest || m == NULL || m->marioObj == NULL) {
        return;
    }

    /*
     * Minecraft owns locomotion. Mario is only an invisible native
     * mission/interaction proxy at Minecraft's authoritative pose.
     */
    m->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;

    crossmod_apply_minecraft_health(m);
    crossmod_process_combat(m);
    crossmod_publish_terrain_proxy(m);
}


void crossmod_bridge_load_block_surfaces(void) {
    if (!s_has_guest) {
        return;
    }

    for (int i = 0; i < CROSSMOD_MAX_BLOCK_BOXES; ++i) {
        const struct CrossmodBlockBox *box =
                &s_block_boxes[i];

        if (!box->active) {
            continue;
        }

        /*
         * Minecraft X matches SM64 X. Minecraft Z is the negated SM64 Z.
         * Convert each collision AABB back to N64 units. Swapping Z min/max
         * after negation keeps the box ordered.
         */
        float min_x = box->min_x * CROSSMOD_SCALE;
        float max_x = box->max_x * CROSSMOD_SCALE;
        float min_y = box->min_y * CROSSMOD_SCALE;
        float max_y = box->max_y * CROSSMOD_SCALE;
        float min_z = -box->max_z * CROSSMOD_SCALE;
        float max_z = -box->min_z * CROSSMOD_SCALE;

        if (min_x <= -8190.0f || max_x >= 8190.0f
                || min_z <= -8190.0f || max_z >= 8190.0f) {
            continue;
        }

        crossmod_add_dynamic_box(
                (s16) lroundf(min_x),
                (s16) lroundf(min_y),
                (s16) lroundf(min_z),
                (s16) lroundf(max_x),
                (s16) lroundf(max_y),
                (s16) lroundf(max_z)
        );
    }
}
