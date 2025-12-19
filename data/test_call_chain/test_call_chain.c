// Test comprehensive call chain analysis with typedef struct and positional initialization

// ========== Target Functions ==========
void target_func1(void) {}
void target_func2(void) {}
void target_func3(void) {}

// ========== Test 1: Anonymous Typedef Struct ==========
typedef struct {
    void (*handler1)(void);
    void (*handler2)(void);
} AnonymousOps;

AnonymousOps anon_ops = {target_func1, target_func2};  // positional init

void anon_caller(void) {
    anon_ops.handler1();  // Should resolve to target_func1
}

// ========== Test 2: Named Typedef Struct ==========
typedef struct NamedOps {
    void (*handler1)(void);
    void (*handler2)(void);
} NamedOpsAlias;

NamedOpsAlias named_ops = {target_func2, target_func3};  // positional init

void named_caller(void) {
    named_ops.handler1();  // Should resolve to target_func2
}

// ========== Test 3: Multi-Level Call Chain ==========
// Chain: entry_point -> middle_caller -> anon_ops.handler2 -> target_func2

void middle_caller(void) {
    anon_ops.handler2();  // Indirect call to target_func2
}

void entry_point(void) {
    middle_caller();  // Direct call
}
