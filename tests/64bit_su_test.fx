#import "standard.fx";


using standard::io::console;

def signed_vs_unsigned() -> int
{
    byte[32] buf;
    
    print("Signed vs Unsigned Test:\n\0");
    
    // These should be identical for unsigned, different for signed
    u64 unsigned_val = (u64)4294967295;  // 0xFFFFFFFF
    i64 signed_val = (i64)4294967295;    // Also 0xFFFFFFFF but signed
    
    u64 u_div = unsigned_val / (u64)256;
    i64 s_div = signed_val / (i64)256;
    
    print("Unsigned 0xFFFFFFFF / 256 = \0"); u64str(u_div, buf); print(buf); print("\n\0");
    print("Signed 0xFFFFFFFF / 256 = \0"); i64str(s_div, buf); print(buf); print("\n\0");
    
    // Test with clearly negative signed value
    i64 negative = (i64)-1;
    i64 neg_div = negative / (i64)256;
    
    print("Signed -1 / 256 = \0"); i64str(neg_div, buf); print(buf); print(" (expected: 0)\n\0");
    
    // Test modulo too
    u64 u_mod = unsigned_val % (u64)257;
    i64 s_mod = signed_val % (i64)257;
    
    print("\nUnsigned 0xFFFFFFFF % 257 = \0"); u64str(u_mod, buf); print(buf); print("\n\0");
    print("Signed 0xFFFFFFFF % 257 = \0"); i64str(s_mod, buf); print(buf); print("\n\0");

    print();print();
    
    return 0;
};

#ifndef __FLUX_TEST__
def main() -> int
{
    return signed_vs_unsigned();
};
#endif;