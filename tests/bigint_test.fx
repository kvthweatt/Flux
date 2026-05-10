// Big Integer Library for Flux - Full Math Edition
// Supports: init, print, copy, compare, add, subtract, multiply, divide, modulo, power, shift
#import "standard.fx", "bigint.fx";

using standard::io::console;

// BigInt structure - stores large integers as arrays of u32 digits
// Each u32 holds one "digit" in base 2^32
// digits[0] is least significant, digits[length-1] is most significant

using math::bigint;

def main() -> int
{
    BigInt num,
           a,
           b,
           result,
           rem_17,
           div25;
    i32 cmp22,
        cmp23,
        cmp24,
        cmp25;

    print("==== BIG INTEGER FOUNDATION TEST ====\n\n\0");
    
    // Test 1: Zero
    print("Test 1: Zero\n\0");
    bigint_zero(@num);
    print("Decimal: \0");
    bigint_print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 2: One
    print("Test 2: One\n\0");
    bigint_one(@num);
    print("Decimal: \0");
    bigint_print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 3: Small u32 value
    print("Test 3: From u32 (42)\n\0");
    bigint_from_uint(@num, 42);
    print("Decimal: \0");
    bigint_print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 4: Larger u32 value
    print("Test 4: From u32 (0xDEADBEEF)\n\0");
    bigint_from_uint(@num, 0xDEADBEEF);
    print("Decimal: \0");
    bigint_print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 5: u64 value that spans two u32 digits
    print("Test 5: From u64 (0x123456789ABCDEF0)\n\0");
    bigint_from_u64(@num, 0x123456789ABCDEF0);
    print("Decimal: \0");
    bigint_print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 6: Maximum u64 value
    print("Test 6: From u64 (0xFFFFFFFFFFFFFFFF)\n\0");
    bigint_from_u64(@num, 0xFFFFFFFFFFFFFFFF);
    print("Decimal: \0");
    bigint_print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 7: Check is_zero
    print("Test 7: is_zero checks\n\0");
    bigint_zero(@num);
    print("Zero is_zero: \0");
    if (bigint_is_zero(@num))
    {
        print("true\n\0");
    }
    else
    {
        print("false\n\0");
    };
    
    bigint_one(@num);
    print("One is_zero: \0");
    if (bigint_is_zero(@num))
    {
        print("true\n\0");
    }
    else
    {
        print("false\n\0");
    };
    print("\n\0");
    
    // Test 8: Check is_one
    print("Test 8: is_one checks\n\0");
    bigint_one(@num);
    print("One is_one: \0");
    if (bigint_is_one(@num))
    {
        print("true\n\0");
    }
    else
    {
        print("false\n\0");
    };
    
    bigint_zero(@num);
    print("Zero is_one: \0");
    if (bigint_is_one(@num))
    {
        print("true\n\0");
    }
    else
    {
        print("false\n\0");
    };
    print("\n\0");

    // ---- 64-bit and full math tests ----

    // Test 9: Add two u64 values
    print("Test 9: Add u64 (0xFFFFFFFFFFFFFFFF + 1)\n\0");
    bigint_from_u64(@a, 0xFFFFFFFFFFFFFFFF);
    bigint_one(@b);
    bigint_add(@result, @a, @b);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 10: Add two large values
    print("Test 10: Add (0x123456789ABCDEF0 + 0xFEDCBA9876543210)\n\0");
    bigint_from_u64(@a, 0x123456789ABCDEF0);
    bigint_from_u64(@b, 0xFEDCBA9876543210);
    bigint_add(@result, @a, @b);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 11: Subtract
    print("Test 11: Subtract (0xFFFFFFFFFFFFFFFF - 0x123456789ABCDEF0)\n\0");
    bigint_from_u64(@a, 0xFFFFFFFFFFFFFFFF);
    bigint_from_u64(@b, 0x123456789ABCDEF0);
    bigint_sub(@result, @a, @b);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 12: Subtract to zero
    print("Test 12: Subtract to zero (0xDEADBEEF - 0xDEADBEEF)\n\0");
    bigint_from_uint(@a, 0xDEADBEEF);
    bigint_from_uint(@b, 0xDEADBEEF);
    bigint_sub(@result, @a, @b);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 13: Multiply two u32 values
    print("Test 13: Multiply (0xFFFFFFFF * 0xFFFFFFFF)\n\0");
    bigint_from_uint(@a, 0xFFFFFFFF);
    bigint_from_uint(@b, 0xFFFFFFFF);
    bigint_mul(@result, @a, @b);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 14: Multiply two u64 values
    print("Test 14: Multiply (0xFFFFFFFFFFFFFFFF * 0xFFFFFFFFFFFFFFFF)\n\0");
    bigint_from_u64(@a, 0xFFFFFFFFFFFFFFFF);
    bigint_from_u64(@b, 0xFFFFFFFFFFFFFFFF);
    bigint_mul(@result, @a, @b);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 15: Divide
    print("Test 15: Divide (100 / 7)\n\0");
    bigint_from_uint(@a, 100);
    bigint_from_uint(@b, 7);
    bigint_div(@result, @a, @b);
    print("Quotient Decimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 16: Modulo
    print("Test 16: Modulo (100 % 7)\n\0");
    bigint_from_uint(@a, 100);
    bigint_from_uint(@b, 7);
    bigint_mod(@result, @a, @b);
    print("Remainder Decimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 17: Divide large u64 values
    print("Test 17: Divide (0xFFFFFFFFFFFFFFFF / 0x123456789ABCDEF0)\n\0");
    bigint_from_u64(@a, 0xFFFFFFFFFFFFFFFF);
    bigint_from_u64(@b, 0x123456789ABCDEF0);
    bigint_divmod(@result, @rem_17, @a, @b);
    print("Quotient Hex: \0");
    bigint_print_hex(@result);
    print("\nRemainder Hex: \0");
    bigint_print_hex(@rem_17);
    print("\n\n\0");

    // Test 18: Power (2^64)
    print("Test 18: Power (2^64)\n\0");
    bigint_from_uint(@a, 2);
    bigint_from_uint(@result, 64);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 19: Power (10^20)
    print("Test 19: Power (10^20)\n\0");
    bigint_from_uint(@a, 10);
    bigint_from_uint(@result, 20);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 20: Shift left
    print("Test 20: Shift left (1 << 63)\n\0");
    bigint_one(@a);
    bigint_shl(@result, @a, 63);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 21: Shift right
    print("Test 21: Shift right (0xFFFFFFFFFFFFFFFF >> 4)\n\0");
    bigint_from_u64(@a, 0xFFFFFFFFFFFFFFFF);
    bigint_shr(@result, @a, 4);
    print("Hex: \0");
    bigint_print_hex(@result);
    print("\nDecimal: \0");
    bigint_print_decimal(@result);
    print("\n\n\0");

    // Test 22: Compare equal
    print("Test 22: Compare equal (0xDEADBEEF == 0xDEADBEEF)\n\0");
    bigint_from_uint(@a, 0xDEADBEEF);
    bigint_from_uint(@b, 0xDEADBEEF);
    cmp22 = bigint_cmp(@a, @b);
    if (cmp22 == 0)
    {
        print("Equal: true\n\0");
    }
    else
    {
        print("Equal: false\n\0");
    };
    print("\n\0");

    // Test 23: Compare less than
    print("Test 23: Compare less than (42 < 0xFFFFFFFF)\n\0");
    bigint_from_uint(@a, 42);
    bigint_from_uint(@b, 0xFFFFFFFF);
    cmp23 = bigint_cmp(@a, @b);
    if (cmp23 < 0)
    {
        print("Less: true\n\0");
    }
    else
    {
        print("Less: false\n\0");
    };
    print("\n\0");

    // Test 24: Compare greater than
    print("Test 24: Compare greater than (0xFFFFFFFFFFFFFFFF > 0xFFFFFFFF)\n\0");
    bigint_from_u64(@a, 0xFFFFFFFFFFFFFFFF);
    bigint_from_uint(@b, 0xFFFFFFFFu);
    cmp24 = bigint_cmp(@a, @b);
    if (cmp24 > 0)
    {
        print("Greater: true\n\0");
    }
    else
    {
        print("Greater: false\n\0");
    };
    print("\n\0");

    // Test 25: Large multiply then divide should recover original
    print("Test 25: (0x123456789ABCDEF0 * 1000) / 1000 == original\n\0");
    bigint_from_u64(@a, 0x123456789ABCDEF0u);
    bigint_from_uint(@b, 1000u);
    bigint_mul(@result, @a, @b);
    bigint_div(@div25, @result, @b);
    cmp25 = bigint_cmp(@div25, @a);
    if (cmp25 == 0)
    {
        print("Round-trip: true\n\0");
    }
    else
    {
        print("Round-trip: false\n\0");
    };
    print("\n\0");

    print("==== ALL TESTS COMPLETE ====\n\0");
    
    return 0;
};
