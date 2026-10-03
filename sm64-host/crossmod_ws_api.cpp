#include "crossmod_ws_api.h"
#include "ws.h"

#include <cstring>
#include <string>

static WsClient g_crossmod_ws;
static bool g_started = false;

extern "C" void crossmod_ws_start(void) {
    if (g_started) {
        return;
    }

    g_started = true;
    g_crossmod_ws.start("127.0.0.1", 25599);
}

extern "C" void crossmod_ws_stop(void) {
    if (!g_started) {
        return;
    }

    g_crossmod_ws.stop();
    g_started = false;
}

extern "C" int crossmod_ws_connected(void) {
    return g_started && g_crossmod_ws.connected() ? 1 : 0;
}

extern "C" int crossmod_ws_send(const char *text) {
    if (!g_started || text == nullptr) {
        return 0;
    }

    return g_crossmod_ws.send(text) ? 1 : 0;
}

extern "C" int crossmod_ws_poll_message(
        char *buffer,
        size_t capacity
) {
    if (!g_started || buffer == nullptr || capacity == 0) {
        return 0;
    }

    std::string message;
    if (!g_crossmod_ws.poll(message)) {
        return 0;
    }

    size_t length = message.size();
    if (length >= capacity) {
        length = capacity - 1;
    }

    std::memcpy(buffer, message.data(), length);
    buffer[length] = '\0';
    return 1;
}
