#define SCALE(x) ((x) * 2)
#define BUILD_NAME(name) config_##name

struct Config {
    int level;
    int extra;
};

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
}
