// 测试位置初始化（positional initializer）对函数指针的赋值关系提取
// Test case for positional initialization of function pointers

// 函数定义
void func1() {}
void func2() {}
void func3() {}
void func4() {}
void func5() {}
void func6() {}

// 测试场景1: 简单的结构体位置初始化
struct simple_ops {
    void (*handler1)();
    void (*handler2)();
};

struct simple_ops ops1 = {func1, func2};  // 位置初始化

// 测试场景2: 结构体数组的位置初始化
struct simple_ops ops_array[] = {
    {func1, func2},
    {func3, func4}
};

// 测试场景3: 混合位置初始化和 designated initializer
struct mixed_ops {
    void (*field1)();
    void (*field2)();
    void (*field3)();
};

struct mixed_ops ops2 = {func1, func2, func3};  // 全部位置初始化
struct mixed_ops ops3 = {.field1 = func4, .field3 = func5};  // designated initializer
struct mixed_ops ops4 = {func1, .field3 = func5};  // 混合（C99+）

// 测试场景4: 嵌套结构体的位置初始化
struct inner_ops {
    void (*inner_handler1)();
    void (*inner_handler2)();
};

struct outer_ops {
    struct inner_ops inner;
    void (*outer_handler)();
};

struct outer_ops nested = {{func1, func2}, func3};

// 测试场景5: 包含其他类型字段的混合结构体
struct complex_ops {
    int id;
    void (*handler)();
    char *name;
};

struct complex_ops complex1 = {1, func1, "test"};

// 期望提取的关系：
// ops1.handler1 --ASSIGNED_TO--> func1
// ops1.handler2 --ASSIGNED_TO--> func2
// ops_array[0].handler1 --ASSIGNED_TO--> func1
// ops_array[0].handler2 --ASSIGNED_TO--> func2
// ops_array[1].handler1 --ASSIGNED_TO--> func3
// ops_array[1].handler2 --ASSIGNED_TO--> func4
// ops2.field1 --ASSIGNED_TO--> func1
// ops2.field2 --ASSIGNED_TO--> func2
// ops2.field3 --ASSIGNED_TO--> func3
// ops3.field1 --ASSIGNED_TO--> func4
// ops3.field3 --ASSIGNED_TO--> func5
// ops4.field1 --ASSIGNED_TO--> func1
// ops4.field3 --ASSIGNED_TO--> func5
// nested.inner.inner_handler1 --ASSIGNED_TO--> func1
// nested.inner.inner_handler2 --ASSIGNED_TO--> func2
// nested.outer_handler --ASSIGNED_TO--> func3
// complex1.handler --ASSIGNED_TO--> func1
