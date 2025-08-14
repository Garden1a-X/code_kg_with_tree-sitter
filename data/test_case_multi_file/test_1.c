#include "test_2.c"
#define BUF_SIZE 1024
#define VERSION "v1.0"
#define default_alias default_config
#define DISPATCH(x) handler_##x
#define MAX(a, b) ((a) > (b) ? (a) : (b))

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
    return BUF_SIZE;
}

void call_init(struct Device* dev) {
    dev->init();
}

void assign_ptrs(struct Device* dev) {
    dev->init = DISPATCH(usb);   // should resolve to handler_usb
    dev->mode = 3;
}

void setup_device(struct Device* dev, int mode) {
    int local_mode = get_mode(dev);
    dev->mode = local_mode;
}
