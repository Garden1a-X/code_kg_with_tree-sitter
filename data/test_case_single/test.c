#include <stdio.h>

// 全局变量（VARIABLE）
int global_var = 42;

// 定义结构体 Point（STRUCT）
struct Point {
    int x;  // 结构体字段（FIELD）
    int y;  // 结构体字段（FIELD）
};

// 定义结构体 Ops（STRUCT），含一个函数指针字段（FIELD）
struct Ops {
    void (*handler)();  // 函数指针字段（FIELD），可以指向某个函数
};

// 被赋值给函数指针的目标函数（FUNCTION）
void handler_fn() {
    printf("In handler_fn\\n");
}

// 普通函数（FUNCTION），含一个输入参数 param（VARIABLE, 参数）
void helper(int param) {
    printf("helper: %d\\n", param);
}

// 函数 set_handler（FUNCTION）
// 接收一个函数指针作为参数（VARIABLE, 参数）
// 内部定义了一个局部函数指针变量 fp（VARIABLE, 局部变量）
// 返回这个函数指针（RETURNS 关系）
void (*set_handler(void (*fn)()))() {
    void (*fp)() = fn;  // ASSIGNED_TO: fp ← fn
    return fp;          // RETURNS: 返回 fp
}

// 主函数（FUNCTION）
int main() {
    int local = global_var;  // 局部变量 local（VARIABLE）

    struct Point pt;     // 局部变量 pt，类型为 Point（TYPE_OF）
    pt.x = 10;           // 访问结构体字段
    pt.y = 20;

    struct Ops ops;      // 局部变量 ops，类型为 Ops（TYPE_OF）
    ops.handler = handler_fn;  // ASSIGNED_TO: handler ← handler_fn

    void (*fp)() = ops.handler;  // 局部函数指针变量（VARIABLE），ASSIGNED_TO: fp ← handler

    helper(local);  // 调用 helper 函数（CALLS）
    fp();           // 间接调用函数指针（CALLS → handler_fn）

    return 0;
}
