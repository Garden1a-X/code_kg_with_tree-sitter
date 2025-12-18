// 测试 typedef 和类型别名对关系提取的影响
// Test case for typedef and type aliases in relationship extraction

// 函数定义
void handler_a() {}
void handler_b() {}
void handler_c() {}
void handler_d() {}

// 测试场景1: typedef 函数指针类型
typedef void (*HandlerFunc)();

struct ops_with_typedef {
    HandlerFunc handler1;
    HandlerFunc handler2;
};

// 使用 typedef 的结构体初始化
struct ops_with_typedef ops1 = {handler_a, handler_b};  // 位置初始化
struct ops_with_typedef ops2 = {.handler1 = handler_c, .handler2 = handler_d};  // designated initializer

// 测试场景2: typedef 结构体类型
typedef struct {
    void (*callback1)();
    void (*callback2)();
} CallbackOps;

CallbackOps cb_ops1 = {handler_a, handler_b};
CallbackOps cb_ops2 = {.callback1 = handler_c};

// 测试场景3: typedef 结构体名称
struct original_ops {
    void (*op1)();
    void (*op2)();
};

typedef struct original_ops AliasedOps;

AliasedOps aliased1 = {handler_a, handler_b};
AliasedOps aliased2 = {.op1 = handler_c, .op2 = handler_d};

// 测试场景4: 多级 typedef
typedef HandlerFunc HandlerAlias;

struct multi_typedef_ops {
    HandlerAlias handler;
};

struct multi_typedef_ops mt_ops = {handler_a};

// 测试场景5: 匿名结构体 + typedef
typedef struct {
    void (*anon_handler1)();
    void (*anon_handler2)();
} AnonOps;

AnonOps anon1 = {handler_a, handler_b};
AnonOps anon2 = {.anon_handler1 = handler_c, .anon_handler2 = handler_d};

// 测试场景6: typedef 在数组中
typedef struct {
    void (*arr_handler)();
} ArrayOps;

ArrayOps arr_ops[] = {
    {handler_a},
    {handler_b},
    {handler_c}
};

// 测试场景7: 混合原始结构体名和 typedef 名
struct named_ops {
    void (*named_handler)();
};

typedef struct named_ops NamedOpsAlias;

struct named_ops n_ops1 = {handler_a};  // 使用原始名称
NamedOpsAlias n_ops2 = {handler_b};     // 使用 typedef 名称

// 期望提取的关系：
// ops1.handler1 --ASSIGNED_TO--> handler_a
// ops1.handler2 --ASSIGNED_TO--> handler_b
// ops2.handler1 --ASSIGNED_TO--> handler_c
// ops2.handler2 --ASSIGNED_TO--> handler_d
// cb_ops1.callback1 --ASSIGNED_TO--> handler_a
// cb_ops1.callback2 --ASSIGNED_TO--> handler_b
// cb_ops2.callback1 --ASSIGNED_TO--> handler_c
// aliased1.op1 --ASSIGNED_TO--> handler_a
// aliased1.op2 --ASSIGNED_TO--> handler_b
// aliased2.op1 --ASSIGNED_TO--> handler_c
// aliased2.op2 --ASSIGNED_TO--> handler_d
// mt_ops.handler --ASSIGNED_TO--> handler_a
// anon1.anon_handler1 --ASSIGNED_TO--> handler_a
// anon1.anon_handler2 --ASSIGNED_TO--> handler_b
// anon2.anon_handler1 --ASSIGNED_TO--> handler_c
// anon2.anon_handler2 --ASSIGNED_TO--> handler_d
// arr_ops[0].arr_handler --ASSIGNED_TO--> handler_a
// arr_ops[1].arr_handler --ASSIGNED_TO--> handler_b
// arr_ops[2].arr_handler --ASSIGNED_TO--> handler_c
// n_ops1.named_handler --ASSIGNED_TO--> handler_a
// n_ops2.named_handler --ASSIGNED_TO--> handler_b
