# 0 "/home/lyk/work/test_pro/test_1.c"
# 1 "/home/lyk//"
# 0 "<built-in>"
# 0 "<command-line>"
# 1 "/usr/include/stdc-predef.h" 1 3 4
# 0 "<command-line>" 2
# 1 "/home/lyk/work/test_pro/test_1.c"
# 1 "/home/lyk/work/test_pro/test_2.h" 1




struct Config {
    int level;
    int extra;
};


extern int global_flag;
extern struct Config default_config;
extern int global_return;
# 24 "/home/lyk/work/test_pro/test_2.h"
int external_init(void);
int get_global(void);
int get_level(struct Config* conf);
void call_macros(void);
# 2 "/home/lyk/work/test_pro/test_1.c" 2






void handler_usb() {}
void handler_eth() {}

struct Device {
    int id;
    void (*init)();
    struct Config* config;
    int mode;
};

int global_flag = 1;
struct Config default_config;
int global_return;

int get_id(struct Device* dev) {
    return dev->id;
}

int get_mode(struct Device* dev) {
    return dev->mode;
}

int get_const() {
    int temp = 100;
    return temp;
}

int get_buf_size_macro() {
    return 1024;
}

void call_init(struct Device* dev) {
    dev->init();
}

void assign_ptrs(struct Device* dev) {
    dev->init = handler_usb;
    dev->mode = 3;
}

void setup_device(struct Device* dev, int mode) {
    int local_mode = get_mode(dev);
    dev->mode = local_mode;
}

int compare_buf_sizes(int custom_size) {
    return ((custom_size) > (1024) ? (custom_size) : (1024));
}
