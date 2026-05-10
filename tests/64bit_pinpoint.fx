#def __FLUX_TEST__ 1;
#import "standard.fx";
#import "tests\\64bit_arith.fx";
#import "tests\\64bit_arith2.fx";
#import "tests\\64bit_su_test.fx";
#import "tests\\64bit_direct_test.fx";
#import "tests\\64bit_direct_test2.fx";


using standard::io::console;

def pinpoint_llvm_bug() -> int
{
    byte[32] buf;
    
    // Test exact operations that should use 64-bit LLVM instructions
    u64 a = (u64)4294967295u;  // 0xFFFFFFFF
    
    print("Testing operation bit-widths:\n\0");
    
    // These should use i64 operations in LLVM IR:
    u64 div_result = a / (u64)256u;      // Should be: udiv i64
    u64 mod_result = a % (u64)257u;      // Should be: urem i64  
    u64 and_result = a & (u64)0xFFFFu;   // Should be: and i64
    u64 or_result  = a | (u64)0x100000000u; // Should be: or i64
    u64 add_result = a + (u64)1u;        // Should be: add i64
    
    print("0xFFFFFFFF / 256 = \0"); u64str(div_result, buf); print(buf); print(" (expected: 16777215)\n\0");
    if (div_result == 16777215)
    {
        print("Success! :: a / (u64)256u;\n\0");
    }
    else
    {
        print("Failure! :: a / (u64)256u;\n\0");
    };
    print("0xFFFFFFFF % 257 = \0"); u64str(mod_result, buf); print(buf); print(" (expected: 0)\n\0");
    if (mod_result == 0)
    {
        print("Success! :: a % (u64)257u;\n\0");
    }
    else
    {
        print("Failure! :: a % (u64)257u;\n\0");
    };
    print("0xFFFFFFFF & 0xFFFF = \0"); u64str(and_result, buf); print(buf); print(" (expected: 65535)\n\0");
    if (and_result == 65535)
    {
        print("Success! :: a & (u64)0xFFFFu;\n\0");
    }
    else
    {
        print("Failure! :: a & (u64)0xFFFFu;\n\0");
    };
    print("0xFFFFFFFF | 0x100000000 = \0"); u64str(or_result, buf); print(buf); print(" (expected: 8589934591)\n\0");
    if (or_result == 8589934591)
    {
        print("Success! :: a | (u64)0x100000000u;\n\0");
    }
    else
    {
        print("Failure! :: a | (u64)0x100000000u;\n\0");
    };
    print("0xFFFFFFFF + 1 = \0"); u64str(add_result, buf); print(buf); print(" (expected: 4294967296)\n\0");
    if (add_result == 4294967296)
    {
        print("Success! :: a + (u64)1u;\n\0");
    }
    else
    {
        print("Failure! :: a + (u64)1u;\n\0");
    };

    // Test if it's value-dependent
    u64 small = (u64)255u;
    u64 small_div = small / (u64)2u;
    print("Small value test (255/2): \0"); u64str(small_div, buf); print(buf); print(" (expected: 127)\n\0");
    if (small_div == 127)
    {
        print("Success! :: small / (u64)2u;\n\0");
    }
    else
    {
        print("Failure! :: small / (u64)2u;\n\0");
    };
    print();print();

    return 0;
};

def test_all_ops() -> int
{
    byte[32] buf;
    u64 large = (u64)0xFFFFFFFFu;
    
    print("Testing ALL operations on 0xFFFFFFFF:\n\0");
    
    // Multiplication (should overflow in 32-bit)
    u64 mul = large * (u64)2;
    print("0xFFFFFFFF * 2 = \0"); u64str(mul, buf); print(buf); print(" (expected: 8589934590)\n\0");
    
    // Subtraction
    u64 sub = large - (u64)1;
    print("0xFFFFFFFF - 1 = \0"); u64str(sub, buf); print(buf); print(" (expected: 4294967294)\n\0");
    
    // Bitwise XOR
    u64 xx = large xor (u64)0xFFFF0000u;
    print("0xFFFFFFFF ^ 0xFFFF0000 = \0"); u64str(xx, buf); print(buf); print(" (expected: 65535)\n\0");
    
    // Right shift (logical vs arithmetic matters for signed!)
    u64 shr = large >> (u64)8u;
    print("0xFFFFFFFF >> 8 = \0"); u64str(shr, buf); print(buf); print(" (expected: 16777215)\n\0");
    
    return 0;
};

def isolate_the_bug() -> int
{
    byte[32] buf;
    
    // Test 1: Explicit 64-bit constant division
    // (Should work if literals are correct)
    u64 result1 = (u64)0xFFFFFFFFu / (u64)256u;
    print("Literal 0xFFFFFFFF / 256 = \0");
    u64str(result1, buf); print(buf); print("\n\0");
    
    // Test 2: Variable division (might be different code path)
    u64 var = (u64)0xFFFFFFFFu;
    u64 result2 = var / (u64)256u;
    print("Variable 0xFFFFFFFF / 256 = \0");
    u64str(result2, buf); print(buf); print("\n\0");
    
    // Test 3: Force 64-bit with cast
    u64 result3 = (u64)((u64)0xFFFFFFFFu / (u64)256u);
    print("Double-cast 0xFFFFFFFF / 256 = \0");
    u64str(result3, buf); print(buf); print("\n\0");
    print();
    
    return 0;
};

def diagnose_variable_vs_literal() -> int
{
    byte[64] buffer;
    
    print("=== Variable vs Literal Diagnosis ===\n\0");
    
    // Case 1: Literal directly in operation
    u64 result1 = (u64)0xFFFFFFFF / (u64)256;
    print("Literal: 0xFFFFFFFF / 256 = \0"); 
    u64str(result1, buffer); print(buffer); print("\n\0");
    
    // Case 2: Store in variable first
    u64 val = (u64)0xFFFFFFFF;
    u64 result2 = val / (u64)256;
    print("Variable: val / 256 = \0");
    u64str(result2, buffer); print(buffer); print("\n\0");
    
    // Case 3: Check what's actually in the variable
    print("val (as hex should be 0xFFFFFFFF) = \0");
    u64str(val, buffer); print(buffer); print("\n\0");
    
    // Case 4: Test addition with variable
    u64 add_result = val + (u64)1;
    print("val + 1 = \0");
    u64str(add_result, buffer); print(buffer); print(" (expected: 0x100000000)\n\0");
    
    // Case 5: What type does 'val' think it is?
    // Let's test with explicit casts
    u64 casted = (u64)val;
    u64 casted_result = casted / (u64)256;
    print("(u64)val / 256 = \0");
    u64str(casted_result, buffer); print(buffer); print("\n\0");
    print();
    
    return 0;
};

def test_implicit_conversions() -> int
{
    byte[64] buffer;
    
    print("=== Implicit Conversion Tests ===\n\0");
    
    // Test: u32 literal assigned to u64
    u64 from_u32_literal = 0xFFFFFFFF;  // This is u32 max
    print("u64 from u32 literal (0xFFFFFFFF) = \0");
    u64str(from_u32_literal, buffer); print(buffer); print("\n\0");
    
    u64 div1 = from_u32_literal / 256;
    print("  / 256 = \0"); u64str(div1, buffer); print(buffer); print("\n\0");
    
    // Test: explicit u64 cast
    u64 explicit = (u64)0xFFFFFFFF;
    u64 div2 = explicit / 256;
    print("Explicit (u64)0xFFFFFFFF / 256 = \0");
    u64str(div2, buffer); print(buffer); print("\n\0");
    
    // Test: intermediate calculations
    u64 calc = (u64)(0xFFFFFFFF) / 256;
    print("(u64)(0xFFFFFFFF) / 256 = \0");
    u64str(calc, buffer); print(buffer); print("\n\0");
    print();
    
    return 0;
};

def main() -> int
{
    test_64bit_arithmetic();
    check_literal_types();
    test_direct();
    test_individual_operations();
    signed_vs_unsigned();
    pinpoint_llvm_bug();
    test_all_ops();
    isolate_the_bug();
    diagnose_variable_vs_literal();
    test_implicit_conversions();
    return 0;
};