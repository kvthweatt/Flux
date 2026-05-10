#import "standard.fx";


using standard::io::console;

def test_individual_operations() -> int
{
    byte[32] buf;
    
    // Test 1: Pure literal comparison (no arithmetic)
    u64 literal = (u64)5000000000;
    
    print("Test 1 - Literal storage:\n\0");
    print("literal == 5000000000: \0");
    if (literal == (u64)5000000000) {
        print("TRUE\n\0");
    } else {
        print("FALSE\n\0");
    };
    
    print("literal > 4294967295: \0");
    if (literal > (u64)4294967295) {
        print("TRUE\n\0");
    } else {
        print("FALSE\n\0");
    };
    
    // Test 2: Division/Modulo with small numbers (should work)
    u64 small = (u64)100;
    u64 div_small = small / (u64)10;
    u64 mod_small = small % (u64)3;
    
    print("\nTest 2 - Small value arithmetic:\n\0");
    print("100 / 10 = \0"); u64str(div_small, buf); print(buf); print(" (expected: 10)\n\0");
    print("100 % 3 = \0"); u64str(mod_small, buf); print(buf); print(" (expected: 1)\n\0");
    
    // Test 3: Division/Modulo with exact 32-bit max
    u64 max32 = (u64)4294967295;  // 2^32 - 1
    u64 div_max = max32 / (u64)10;
    u64 mod_max = max32 % (u64)10;
    
    print("\nTest 3 - 32-bit max arithmetic:\n\0");
    print("4294967295 / 10 = \0"); u64str(div_max, buf); print(buf); print(" (expected: 429496729)\n\0");
    print("4294967295 % 10 = \0"); u64str(mod_max, buf); print(buf); print(" (expected: 5)\n\0");
    
    // Test 4: Bit shift operations
    u64 one = (u64)1;
    u64 shifted = one << (u64)32;
    
    print("\nTest 4 - Bit shifting:\n\0");
    print("1 << 32 = \0"); u64str(shifted, buf); print(buf); print(" (expected: 4294967296)\n\0");
    
    // Test 5: Manual combine with verification
    u64 high = (u64)1;
    u64 low = (u64)1627584000;
    u64 shift_result = high << (u64)32;
    u64 or_result = shift_result | low;
    
    print("\nTest 5 - Manual combine step by step:\n\0");
    print("high = 1: \0"); u64str(high, buf); print(buf); print("\n\0");
    print("low = 1627584000: \0"); u64str(low, buf); print(buf); print("\n\0");
    print("high << 32 = \0"); u64str(shift_result, buf); print(buf); print("\n\0");
    print("(high << 32) | low = \0"); u64str(or_result, buf); print(buf); print("\n\0");

    print();print();
    
    return 0;
};

#ifndef __FLUX_TEST__
def main() -> int
{
    return test_individual_operations();
};
#endif;