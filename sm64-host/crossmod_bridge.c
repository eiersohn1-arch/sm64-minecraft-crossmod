#include "crossmod_bridge.h"

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
#include "engine/graph_node.h"
#include "object_constants.h"
#include "object_fields.h"

extern struct CameraFOVStatus sFOVState;

#define CROSSMOD_SCALE 100.0f
#define CROSSMOD_MIN_MELEE_REACH 220.0f
#define CROSSMOD_MAX_MELEE_REACH 520.0f
#define CROSSMOD_ATTACK_HALF_ANGLE_COS 0.35f

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
};

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

static unsigned long s_last_processed_attack_serial;
static unsigned long s_last_processed_use_serial;
static unsigned long s_last_hit_attack_serial;
static int s_last_hit_count;
static unsigned long s_host_frame;
static struct CrossmodRenderPose s_render_pose;
static int s_render_pose_valid;

void crossmod_bridge_init(void) {
    crossmod_ws_start();
}

void crossmod_bridge_shutdown(void) {
    crossmod_ws_stop();
}

bool crossmod_bridge_active(void) {
    return s_has_guest != 0 && crossmod_ws_connected();
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
            "\"health\":%f,\"food\":%d}",
            &guest->sequence,
            guest->held_item,
            &guest->selected_slot,
            guest->weapon_kind,
            &guest->reach_blocks,
            &guest->power,
            &guest->screen_open,
            &guest->health,
            &guest->food
    );

    return count == 9;
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

static float crossmod_clamp01(float value) {
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 1.0f) {
        return 1.0f;
    }
    return value;
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

static void crossmod_capture_host_input(void) {
    if (!crossmod_host_has_focus()) {
        s_host_keys = 0;
        s_attack_down = 0;
        s_use_down = 0;
        s_prev_attack_down = 0;
        s_prev_use_down = 0;
        s_prev_slot_mask = 0;
        s_prev_inventory_down = 0;
        return;
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

    if (!s_guest.screen_open) {
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
        crossmod_capture_host_input();
        return;
    }

    while (crossmod_ws_poll_message(buffer, sizeof(buffer))) {
        struct CrossmodGuestState next;
        memset(&next, 0, sizeof(next));

        if (!parse_guest_packet(buffer, &next)) {
            continue;
        }

        s_guest = next;
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

    if (s_guest.screen_open) {
        controller->rawStickX = 0;
        controller->rawStickY = 0;
        controller->buttonPressed = 0;
        controller->buttonDown = 0;
        crossmod_adjust_stick(controller);
        return;
    }

    int x = ((s_host_keys & 8u) ? 1 : 0)
            - ((s_host_keys & 4u) ? 1 : 0);
    int y = ((s_host_keys & 1u) ? 1 : 0)
            - ((s_host_keys & 2u) ? 1 : 0);

    controller->rawStickX = (s8) (x * 127);
    controller->rawStickY = (s8) (y * 127);

    u16 buttons = 0;

    if (s_host_keys & 16u) buttons |= A_BUTTON;
    if (s_attack_down || s_use_down) buttons |= B_BUTTON;
    if (s_host_keys & 32u) buttons |= Z_TRIG;
    if (s_host_keys & 128u) buttons |= START_BUTTON;
    if (s_host_keys & 256u) buttons |= U_CBUTTONS;
    if (s_host_keys & 512u) buttons |= D_CBUTTONS;
    if (s_host_keys & 1024u) buttons |= L_CBUTTONS;
    if (s_host_keys & 2048u) buttons |= R_CBUTTONS;
    if (s_host_keys & 4096u) buttons |= R_TRIG;
    if (s_host_keys & 8192u) buttons |= L_TRIG;

    controller->buttonPressed =
            buttons & (buttons ^ controller->buttonDown);
    controller->buttonDown = buttons;

    crossmod_adjust_stick(controller);
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
    float forward_x = sins(m->faceAngle[1]);
    float forward_z = coss(m->faceAngle[1]);

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
                    - (m->pos[1] + 80.0f);
            float dz = obj->oPosZ - m->pos[2];

            float horizontal_sq = dx * dx + dz * dz;
            float distance_sq = horizontal_sq + dy * dy;

            float target_radius = obj->hurtboxRadius;
            if (target_radius < 40.0f) {
                target_radius = 40.0f;
            }

            float allowed = reach + target_radius;
            if (distance_sq > allowed * allowed) {
                continue;
            }

            float horizontal = sqrtf(horizontal_sq);
            float facing = 1.0f;

            if (horizontal > 1.0f) {
                facing = (dx * forward_x + dz * forward_z) / horizontal;
            }

            if (facing < CROSSMOD_ATTACK_HALF_ANGLE_COS) {
                continue;
            }

            float score = sqrtf(distance_sq) - facing * 120.0f;
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

    float forward_x = sins(m->faceAngle[1]);
    float forward_z = coss(m->faceAngle[1]);

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
            float dz = obj->oPosZ - m->pos[2];
            float t = dx * forward_x + dz * forward_z;

            if (t <= 0.0f || t > reach || t >= best_t) {
                continue;
            }

            float horizontal_sq = dx * dx + dz * dz;
            float perpendicular_sq = horizontal_sq - t * t;
            if (perpendicular_sq < 0.0f) {
                perpendicular_sq = 0.0f;
            }

            float radius = obj->hurtboxRadius + 80.0f;
            if (radius < 100.0f) {
                radius = 100.0f;
            }

            float center_y = obj->oPosY + obj->hurtboxHeight * 0.5f;
            float dy = center_y - (m->pos[1] + 100.0f);
            float vertical_limit = obj->hurtboxHeight * 0.5f + 160.0f;

            if (perpendicular_sq <= radius * radius
                    && fabsf(dy) <= vertical_limit) {
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
            "\"fov\":%.3f,"
            "\"pl\":[%.6f,%.6f,%.6f],"
            "\"h\":%.4f,"
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
            m->pos[0] / CROSSMOD_SCALE,
            m->pos[1] / CROSSMOD_SCALE,
            -m->pos[2] / CROSSMOD_SCALE,
            body_yaw,
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
     * SM64 remains the real game. Mario is its native collision/mission body,
     * while Minecraft renders Steve/skin/items at the authoritative pose.
     */
    m->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;

    crossmod_process_combat(m);
    send_state(m);
}
