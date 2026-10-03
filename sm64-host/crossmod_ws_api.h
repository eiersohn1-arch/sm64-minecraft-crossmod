#ifndef CROSSMOD_WS_API_H
#define CROSSMOD_WS_API_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void crossmod_ws_start(void);
void crossmod_ws_stop(void);
int crossmod_ws_connected(void);
int crossmod_ws_send(const char *text);
int crossmod_ws_poll_message(char *buffer, size_t capacity);

#ifdef __cplusplus
}
#endif

#endif
