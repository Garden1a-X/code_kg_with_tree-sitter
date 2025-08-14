#ifndef TEST_2_H
#define TEST_2_H

// 结构体声明
struct Config {
    int level;
    int extra;
};

// 外部变量声明 (来自test_1.c)
extern int global_flag;
extern struct Config default_config;
extern int global_return;

// 来自test_1.c的宏定义
#define VERSION "v1.0"
#define default_alias default_config

// test_2.c中的宏定义
#define SCALE(x) ((x) * 2)
#define BUILD_NAME(name) config_##name

// 函数声明
int external_init(void);
int get_global(void);
int get_level(struct Config* conf);
void call_macros(void);

#endif // TEST_2_H