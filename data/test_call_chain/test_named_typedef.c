// Test named struct with typedef alias
// typedef struct OriginalName { ... } TypedefAlias;

void func1(void) {}
void func2(void) {}

// Named struct with typedef alias
typedef struct FuncOps {
    void (*callback1)(void);
    void (*callback2)(void);
} FunctionOps;

// Test 1: Use typedef alias name
FunctionOps ops1 = {func1, func2};

// Test 2: Use original struct name
struct FuncOps ops2 = {func1, func2};

// Test 3: Array with typedef alias
FunctionOps ops_array[] = {
    {func1, func2}
};

void caller1(void) {
    ops1.callback1();
}

void caller2(void) {
    ops2.callback1();
}

void caller3(void) {
    ops_array[0].callback1();
}
