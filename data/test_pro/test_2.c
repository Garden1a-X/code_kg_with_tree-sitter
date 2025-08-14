#include "test_2.h"

int external_init() {
    return 1;
}

int get_global() {
    return global_flag;  // use global from test_1
}

int get_level(struct Config* conf) {
    return conf->level;
}

void call_macros() {
    int val = SCALE(5);
    char* buf = VERSION;
    struct Config* conf_ptr = &default_alias;
    
    // 避免未使用变量的警告
    (void)val;
    (void)buf;
    (void)conf_ptr;
}