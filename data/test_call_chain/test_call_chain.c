// Test comprehensive call chain analysis with typedef anonymous struct and positional initialization
// This test verifies:
// 1. ASSIGNED_TO relations for positional initialization in typedef anonymous struct arrays
// 2. Indirect CALLS relations through struct field pointers
// 3. Call chain traversal: func_a -> func_b -> struct_array[idx].field -> target_func

// Target functions that will be called indirectly
void target_func1(void) {
    // Implementation
}

void target_func2(void) {
    // Implementation
}

void target_func3(void) {
    // Implementation
}

void target_func4(void) {
    // Implementation
}

// Define typedef anonymous struct with function pointer fields
typedef struct {
    void (*callback1)(void);
    void (*callback2)(void);
} FunctionOps;

// Positional array initialization - should create ASSIGNED_TO relations:
// struct_array[0].callback1 -> target_func1
// struct_array[0].callback2 -> target_func2
// struct_array[1].callback1 -> target_func3
// struct_array[1].callback2 -> target_func4
FunctionOps struct_array[] = {
    {target_func1, target_func2},  // positional: field order matters
    {target_func3, target_func4}
};

// Single struct with partial initialization
FunctionOps single_ops = {target_func1};  // Only callback1 assigned

// Call chain level 3: Called by intermediate_caller
void intermediate_caller(void) {
    // Indirect call through struct field pointer
    // This should create: intermediate_caller --CALLS--> struct_array[0].callback1
    // Combined with ASSIGNED_TO: struct_array[0].callback1 -> target_func1
    // Call chain: intermediate_caller -> target_func1
    struct_array[0].callback1();
}

// Call chain level 2: Called by top_level_caller
void level2_caller(void) {
    // Direct call
    intermediate_caller();

    // Another indirect call
    struct_array[1].callback2();  // Should resolve to target_func4
}

// Call chain level 1: Entry point
void top_level_caller(void) {
    // Direct call to level2_caller
    level2_caller();

    // Indirect call through single_ops
    single_ops.callback1();  // Should resolve to target_func1
}

// Additional test: Pointer-based access
void pointer_based_caller(void) {
    FunctionOps *ops_ptr = &struct_array[0];

    // Call through pointer dereference
    // This tests: pointer->field() pattern
    ops_ptr->callback1();  // Should resolve to target_func1
    ops_ptr->callback2();  // Should resolve to target_func2
}

// Test: Array element via variable index
void variable_index_caller(int idx) {
    // Dynamic array access
    struct_array[idx].callback1();
}

// Expected call chain paths:
// 1. top_level_caller -> level2_caller -> intermediate_caller -> struct_array[0].callback1 -> target_func1
// 2. top_level_caller -> level2_caller -> struct_array[1].callback2 -> target_func4
// 3. top_level_caller -> single_ops.callback1 -> target_func1
// 4. pointer_based_caller -> ops_ptr->callback1 -> target_func1
// 5. pointer_based_caller -> ops_ptr->callback2 -> target_func2

// Expected ASSIGNED_TO relations (positional initialization):
// 1. struct_array[0].callback1 -> target_func1
// 2. struct_array[0].callback2 -> target_func2
// 3. struct_array[1].callback1 -> target_func3
// 4. struct_array[1].callback2 -> target_func4
// 5. single_ops.callback1 -> target_func1
