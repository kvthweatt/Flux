#import "standard.fx";

using standard::io::console;

def test_direct() -> int
{
    // Direct operations without function calls
    u64 x = (u64)5000000000;
    u64 y = x / (u64)10;
    
    byte[32] buf;
    u64str(y, buf);
    
    print("Direct: 5000000000 / 10 = \0");
    print(buf);
    print("\n\0");
    
    // Check what x actually contains
    if (x > (u64)4294967295) {
        print("x > 2^32-1 (good!)\n\0");
    } else {
        print("x <= 2^32-1 (BAD - truncated!)\n\0");
    };
    
    // Try manual 64-bit by combining two 32-bit parts
    u64 high = (u64)1;                  // High 32 bits
    u64 low  = (u64)1627584000;         // Low 32 bits
    u64 combined = (high << 32) | low;  // Should be 5922551296
    
    print("Manual combine: \0");
    u64str(combined, buf);
    print(buf);
    print(" (should be 5922551296)\n\0");
    if (combined == 5922551296)
    {
        print("Success! :: Manual combine\n\n\0");
    }
    else
    {
        print("Failure! :: Manual combine\n\n\0");
    };
    
    return 0;
};

#ifndef __FLUX_TEST__
def main() -> int
{
    return test_direct();
};
#endif;