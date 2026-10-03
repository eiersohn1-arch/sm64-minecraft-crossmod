#include "crossmod_bridge.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET crossmod_socket_t;
#define CROSSMOD_INVALID_SOCKET INVALID_SOCKET
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
typedef int crossmod_socket_t;
#define CROSSMOD_INVALID_SOCKET (-1)
#endif

#include "game/area.h"
#include "game/camera.h"
#include "game/game_init.h"
#include "game/interaction.h"
#include "game/mario.h"
#include "game/object_list_processor.h"
#include "game/save_file.h"
#include "engine/math_util.h"
#include "engine/graph_node.h"
#include "object_constants.h"
#include "object_fields.h"

#define CROSSMOD_PORT 6464
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

struct CrossmodPlayerPacket {
    unsigned long sequence;
    double minecraft_x;
    double minecraft_y;
    double minecraft_z;
    float yaw;
    float pitch;
    char held_item[96];
    unsigned long attack_serial;
    char weapon_kind[24];
    float reach_blocks;
    int power;
    int attack_down;
    int use;
    int forward;
    int back;
    int left;
    int right;
    int jump;
    int sneak;
    int sprint;
    int start;
    int camera_up;
    int camera_down;
    int camera_left;
    int camera_right;
    int r_trigger;
    int l_trigger;
    float health;
    int food;
};

static crossmod_socket_t s_socket = CROSSMOD_INVALID_SOCKET;
static struct sockaddr_in s_client_addr;
static socklen_t s_client_addr_len = sizeof(s_client_addr);
static int s_has_client;
static int s_has_player;
static struct CrossmodPlayerPacket s_player;

static unsigned long s_last_processed_attack_serial;
static unsigned long s_last_hit_attack_serial;
static int s_last_hit_count;

static void crossmod_close_socket(void) {
    if (s_socket == CROSSMOD_INVALID_SOCKET) {
        return;
    }
#ifdef _WIN32
    closesocket(s_socket);
#else
    close(s_socket);
#endif
    s_socket = CROSSMOD_INVALID_SOCKET;
}

static void crossmod_set_nonblocking(crossmod_socket_t socket_handle) {
#ifdef _WIN32
    u_long enabled = 1;
    ioctlsocket(socket_handle, FIONBIO, &enabled);
#else
    int flags = fcntl(socket_handle, F_GETFL, 0);
    if (flags >= 0) {
        fcntl(socket_handle, F_SETFL, flags | O_NONBLOCK);
    }
#endif
}

void crossmod_bridge_init(void) {
    struct sockaddr_in address;

    if (s_socket != CROSSMOD_INVALID_SOCKET) {
        return;
    }

#ifdef _WIN32
    WSADATA data;
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        return;
    }
#endif

    s_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s_socket == CROSSMOD_INVALID_SOCKET) {
        return;
    }

    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(CROSSMOD_PORT);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    if (bind(s_socket, (const struct sockaddr *)&address, sizeof(address)) != 0) {
        crossmod_close_socket();
        return;
    }

    crossmod_set_nonblocking(s_socket);
}

void crossmod_bridge_shutdown(void) {
    crossmod_close_socket();
#ifdef _WIN32
    WSACleanup();
#endif
}

bool crossmod_bridge_active(void) {
    return s_has_player != 0;
}

static int parse_player_packet(
        const char *text,
        struct CrossmodPlayerPacket *packet
) {
    int count = sscanf(
            text,
            "P|%lu|%lf|%lf|%lf|%f|%f|%95[^|]|%lu|%23[^|]|%f|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%f|%d",
            &packet->sequence,
            &packet->minecraft_x,
            &packet->minecraft_y,
            &packet->minecraft_z,
            &packet->yaw,
            &packet->pitch,
            packet->held_item,
            &packet->attack_serial,
            packet->weapon_kind,
            &packet->reach_blocks,
            &packet->power,
            &packet->attack_down,
            &packet->use,
            &packet->forward,
            &packet->back,
            &packet->left,
            &packet->right,
            &packet->jump,
            &packet->sneak,
            &packet->sprint,
            &packet->start,
            &packet->camera_up,
            &packet->camera_down,
            &packet->camera_left,
            &packet->camera_right,
            &packet->r_trigger,
            &packet->l_trigger,
            &packet->health,
            &packet->food
    );

    return count == 29;
}

void crossmod_bridge_poll(void) {
    char buffer[2048];

    if (s_socket == CROSSMOD_INVALID_SOCKET) {
        return;
    }

    for (;;) {
        struct sockaddr_in from;
        socklen_t from_len = sizeof(from);
        int received = (int) recvfrom(
                s_socket,
                buffer,
                sizeof(buffer) - 1,
                0,
                (struct sockaddr *)&from,
                &from_len
        );

        if (received <= 0) {
            break;
        }

        buffer[received] = '\0';

        struct CrossmodPlayerPacket next;
        memset(&next, 0, sizeof(next));

        if (!parse_player_packet(buffer, &next)) {
            continue;
        }

        s_player = next;
        s_client_addr = from;
        s_client_addr_len = from_len;
        s_has_client = 1;
        s_has_player = 1;
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
    if (!s_has_player || controller == NULL) {
        return;
    }

    int x = (s_player.right ? 1 : 0) - (s_player.left ? 1 : 0);
    int y = (s_player.forward ? 1 : 0) - (s_player.back ? 1 : 0);

    controller->rawStickX = (s8) (x * 127);
    controller->rawStickY = (s8) (y * 127);

    u16 buttons = 0;

    if (s_player.jump) {
        buttons |= A_BUTTON;
    }

    /*
     * B remains available for every original mission mechanic:
     * punching, grabbing, throwing Big Bob-omb/Bowser, signs and object use.
     * Left click is also B, while weapon metadata can add Minecraft damage.
     */
    if (s_player.attack_down || s_player.use) {
        buttons |= B_BUTTON;
    }

    if (s_player.sneak) {
        buttons |= Z_TRIG;
    }
    if (s_player.start) {
        buttons |= START_BUTTON;
    }
    if (s_player.camera_up) {
        buttons |= U_CBUTTONS;
    }
    if (s_player.camera_down) {
        buttons |= D_CBUTTONS;
    }
    if (s_player.camera_left) {
        buttons |= L_CBUTTONS;
    }
    if (s_player.camera_right) {
        buttons |= R_CBUTTONS;
    }
    if (s_player.r_trigger) {
        buttons |= R_TRIG;
    }
    if (s_player.l_trigger) {
        buttons |= L_TRIG;
    }

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

static void crossmod_process_combat(struct MarioState *m) {
    if (s_player.attack_serial == 0
            || s_player.attack_serial == s_last_processed_attack_serial) {
        return;
    }

    s_last_processed_attack_serial = s_player.attack_serial;
    s_last_hit_count = 0;

    if (strcmp(s_player.weapon_kind, "ranged") == 0) {
        return;
    }

    struct Object *target = crossmod_find_melee_target(
            m,
            crossmod_clamp_melee_reach(s_player.reach_blocks)
    );

    if (target == NULL) {
        return;
    }

    target->oInteractStatus =
            ATTACK_KICK_OR_TRIP
            | INT_STATUS_INTERACTED
            | INT_STATUS_WAS_ATTACKED;

    m->interactObj = target;
    s_last_hit_count = s_player.power > 0 ? s_player.power : 1;
    s_last_hit_attack_serial = s_player.attack_serial;
}

static void send_state(const struct MarioState *m) {
    if (!s_has_client || s_socket == CROSSMOD_INVALID_SOCKET || m == NULL) {
        return;
    }

    char response[1024];

    int camera_mode = 0;
    float camera_x = 0.0f;
    float camera_y = 0.0f;
    float camera_z = 0.0f;
    float focus_x = 0.0f;
    float focus_y = 0.0f;
    float focus_z = 0.0f;

    if (gCurrentArea != NULL && gCurrentArea->camera != NULL) {
        camera_mode = gLakituState.mode;
        camera_x = gLakituState.curPos[0];
        camera_y = gLakituState.curPos[1];
        camera_z = gLakituState.curPos[2];
        focus_x = gLakituState.curFocus[0];
        focus_y = gLakituState.curFocus[1];
        focus_z = gLakituState.curFocus[2];
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

    int length = snprintf(
            response,
            sizeof(response),
            "S|%lu|%d|%d|%d|%d|%d|%d|%lu|%lu|native|%.3f|%.3f|%.3f|%.3f|%.3f|%.3f|%.3f|%.3f|%.3f|%d|%lu|%d\n",
            s_player.sequence,
            (int) gCurrLevelNum,
            (int) gCurrAreaIndex,
            (int) gCurrCourseNum,
            (int) gCurrActNum,
            (int) m->numStars,
            (int) m->health,
            (unsigned long) save_flags,
            (unsigned long) course_star_flags,
            m->pos[0],
            m->pos[1],
            m->pos[2],
            camera_x,
            camera_y,
            camera_z,
            focus_x,
            focus_y,
            focus_z,
            camera_mode,
            s_last_hit_attack_serial,
            s_last_hit_count
    );

    if (length > 0) {
        sendto(
                s_socket,
                response,
                (size_t) length,
                0,
                (const struct sockaddr *)&s_client_addr,
                s_client_addr_len
        );
    }
}

void crossmod_bridge_after_mario_update(struct MarioState *m) {
    if (!s_has_player || m == NULL || m->marioObj == NULL) {
        return;
    }

    /*
     * SM64 keeps complete authority over Mario's native physics/actions.
     * We only hide the Mario model and use him as Steve's interaction body.
     */
    m->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;

    crossmod_process_combat(m);
    send_state(m);
}
