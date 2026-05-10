#import "standard.fx";

using standard::io::console;

def test_64bit_arithmetic() -> int
{
    byte[32] buffer;
    
    // Test basic 64-bit operations
    u64 large_val = (u64)5000000000;
    
    // Direct division test
    u64 divided = large_val / (u64)10;
    u64 modded = large_val % (u64)10;
    
    print("5000000000 / 10 = \0");
    u64str(divided, buffer);
    print(buffer);
    print(" (expected: 500000000)\n\0");
    
    print("5000000000 % 10 = \0");
    u64str(modded, buffer);
    print(buffer);
    print(" (expected: 0)\n\0");
    
    // Test with smaller values that fit in 32 bits
    u64 small_val = (u64)12345;
    u64 small_div = small_val / (u64)10;
    u64 small_mod = small_val % (u64)10;
    
    print("12345 / 10 = \0");
    u64str(small_div, buffer);
    print(buffer);
    print(" (expected: 1234)\n\0");
    
    print("12345 % 10 = \0");
    u64str(small_mod, buffer);
    print(buffer);
    print(" (expected: 5)\n\0");
    
    // Test with values just above 32-bit range
    u64 above_32bit = (u64)4294967296;  // 2^32
    u64 above_div = above_32bit / (u64)10;
    u64 above_mod = above_32bit % (u64)10;
    
    print("4294967296 / 10 = \0");
    u64str(above_div, buffer);
    print(buffer);
    print(" (expected: 429496729)\n\0");
    
    print("4294967296 % 10 = \0");
    u64str(above_mod, buffer);
    print(buffer);
    print(" (expected: 6)\n\0");

    print();print();
    
    return 0;
};

#ifndef __FLUX_TEST__
def main() -> int
{
    print("Testing 64-bit arithmetic operations:\n\0");
    return test_64bit_arithmetic();
};
#endif;