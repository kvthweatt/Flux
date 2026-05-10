// Big Integer Library for Flux - Foundation
// Phase 1: Structure, initialization, and printing
#import "standard.fx";

using standard::io::console;

// BigInt structure - stores large integers as arrays of u32 digits
// Each u32 holds one "digit" in base 2^32
// digits[0] is least significant, digits[length-1] is most significant
struct BigInt
{
    u32[128] digits;    // Can hold up to 4096 bits (128 * 32)
    u32 length;         // Number of u32 digits actually used
    bool negative;      // Sign: false = positive, true = negative
};

namespace math
{
    namespace bigint
    {
        // Initialize a BigInt to zero
        def bigint_zero(BigInt* num) -> void
        {
            u32 i;
            for (i = 0; i < 128; i++)
            {
                num.digits[i] = 0;
            };
            num.length = 1;
            num.negative = false;
            return;
        };
        
        // Initialize a BigInt to one
        def bigint_one(BigInt* num) -> void
        {
            u32 i;
            num.digits[0] = 1;
            for (i = 1; i < 128; i++)
            {
                num.digits[i] = 0;
            };
            num.length = 1;
            num.negative = false;
            return;
        };
        
        // Create a BigInt from a u32 value
        def bigint_from_u32(BigInt* num, u32 value) -> void
        {
            u32 i;
            num.digits[0] = value;
            for (i = 1; i < 128; i++)
            {
                num.digits[i] = 0;
            };
            
            if (value == 0)
            {
                num.length = 1;
            }
            else
            {
                num.length = 1;
            };
            
            num.negative = false;
            return;
        };
        
        // Create a BigInt from a u64 value
        def bigint_from_u64(BigInt* num, u64 value) -> void
        {
            u32 i;
            num.digits[0] = (u32)(value & 0xFFFFFFFF);
            num.digits[1] = (u32)(value >> 32);
            
            for (i = 2; i < 128; i++)
            {
                num.digits[i] = 0;
            };
            
            if (num.digits[1] != 0)
            {
                num.length = 2;
            }
            else
            {
                if (num.digits[0] != 0)
                {
                    num.length = 1;
                }
                else
                {
                    num.length = 1;
                };
            };
            
            num.negative = false;
            return;
        };
        
        // Check if BigInt is zero
        def bigint_is_zero(BigInt* num) -> bool
        {
            if (num.length == 1)
            {
                if (num.digits[0] == 0)
                {
                    return true;
                };
            };
            return false;
        };
        
        // Check if BigInt is one
        def bigint_is_one(BigInt* num) -> bool
        {
            if (num.negative)
            {
                return false;
            };
            
            if (num.length == 1)
            {
                if (num.digits[0] == 1)
                {
                    return true;
                };
            };
            
            return false;
        };
        
        // Print a single hex digit
        def print_hex_digit(u32 digit) -> void
        {
            if (digit < 10)
            {
                print((byte)('0' + digit));
            }
            else
            {
                print((byte)('a' + (digit - 10)));
            };
            return;
        };
        
        // Print BigInt in hexadecimal format (for debugging)
        def bigint_print_hex(BigInt* num) -> void
        {
            if (num.negative)
            {
                standard::io::console::print('-');
            };
            
            print("0x\0");
            
            // Print from most significant to least significant
            u32 i = num.length;
            while (i > 0)
            {
                i--;
                
                u32 digit = num.digits[i];
                
                // Print all 8 hex digits for this u32
                u32 j;
                for (j = 0; j < 8; j++)
                {
                    u32 nibble = (digit >> (28 - j * 4)) & 0xF;
                    print_hex_digit(nibble);
                };
                
                // Add separator between digits for readability
                if (i > 0)
                {
                    print("_\0");
                };
            };
            
            return;
        };
        
        // Copy one BigInt to another
        def bigint_copy(BigInt* dest, BigInt* src) -> void
        {
            u32 i;
            for (i = 0; i < 128; i++)
            {
                dest.digits[i] = src.digits[i];
            };
            dest.length = src.length;
            dest.negative = src.negative;
            return;
        };
        
        // Create a BigInt from an array of u64 values (least significant first)
        // This allows creating numbers larger than 64 bits
        def bigint_from_u64_array(BigInt* num, u64* values, u32 num_values) -> void
        {
            u32 i;
            u32 digit_index = 0;
            
            // Clear all digits first
            for (i = 0; i < 128; i++)
            {
                num.digits[i] = 0;
            };
            
            // Convert each u64 into two u32 digits
            for (i = 0; i < num_values; i++)
            {
                if (digit_index < 128)
                {
                    num.digits[digit_index] = (u32)(values[i] & 0xFFFFFFFF);
                    digit_index++;
                };
                
                if (digit_index < 128)
                {
                    num.digits[digit_index] = (u32)(values[i] >> 32);
                    digit_index++;
                };
            };
            
            // Calculate actual length (trim leading zeros)
            num.length = digit_index;
            while (num.length > 1)
            {
                if (num.digits[num.length - 1] == 0)
                {
                    //num.length--;
                    num.length -= 1;
                }
                else
                {
                    break;
                };
            };
            
            num.negative = false;
            return;
        };
        
        // Create a BigInt from an array of u32 values (least significant first)
        def bigint_from_u32_array(BigInt* num, u32* values, u32 num_values) -> void
        {
            u32 i;
            
            // Clear all digits first
            for (i = 0; i < 128; i++)
            {
                num.digits[i] = 0;
            };
            
            // Copy values
            for (i = 0; i < num_values; i++)
            {
                if (i < 128)
                {
                    num.digits[i] = values[i];
                };
            };
            
            // Calculate actual length (trim leading zeros)
            num.length = num_values;
            if (num.length > 128)
            {
                num.length = 128;
            };
            
            while (num.length > 1)
            {
                if (num.digits[num.length - 1] == 0)
                {
                    num.length -= 1;
                }
                else
                {
                    break;
                };
            };
            
            num.negative = false;
            return;
        };

        // Helper: Divide BigInt by u32, return remainder (modifies num in place)
        def bigint_div_u32_inplace(BigInt* num, u32 divisor) -> u32
        {
            u64 carry = 0;
            u32 i = num.length;
            
            while (i > 0)
            {
                i = i - 1;
                u64 temp = (carry << 32) | (u64)num.digits[i];
                num.digits[i] = (u32)(temp / (u64)divisor);
                carry = temp % (u64)divisor;
            };
            
            // Trim leading zeros
            while (num.length > 1)
            {
                if (num.digits[num.length - 1] == 0)
                {
                    num.length = num.length - 1;
                }
                else
                {
                    break;
                };
            };
            
            return (u32)carry;
        };

        // Print BigInt in decimal format (works for any size)
        def print(BigInt* num) -> void
        {
            // Handle negative
            if (num.negative)
            {
                standard::io::console::print('-');
            };
            
            // Handle zero
            if (bigint_is_zero(num))
            {
                standard::io::console::print("0\0");
                return;
            };
            
            // Make a copy so we don't modify original
            BigInt temp;
            bigint_copy(@temp, num);
            
            // Extract decimal digits by repeated division by 10
            byte[1024] digits;
            u32 digit_count = 0;
            
            while (bigint_is_zero(@temp) == false)
            {
                u32 remainder = bigint_div_u32_inplace(@temp, 10);
                digits[digit_count] = (byte)('0' + remainder);
                digit_count = digit_count + 1;
            };
            
            // Print digits in reverse order
            u32 i = digit_count;
            while (i > 0)
            {
                i = i - 1;
                standard::io::console::print((u32)digits[i]);
            };
            
            return;
        };
    };
};

using math::bigint;

def main() -> int
{
    print("==== BIG INTEGER FOUNDATION TEST ====\n\n\0");
    
    BigInt num;
    
    // Test 1: Zero
    print("Test 1: Zero\n\0");
    bigint_zero(@num);
    print("Decimal: \0");
    print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 2: One
    print("Test 2: One\n\0");
    bigint_one(@num);
    print("Decimal: \0");
    print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 3: Small u32 value
    print("Test 3: From u32 (42)\n\0");
    bigint_from_u32(@num, 42);
    print("Decimal: \0");
    print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 4: Larger u32 value
    print("Test 4: From u32 (0xDEADBEEF)\n\0");
    bigint_from_u32(@num, 0xDEADBEEF);
    print("Decimal: \0");
    print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 5: u64 value that spans two u32 digits
    print("Test 5: From u64 (0x123456789ABCDEF0)\n\0");
    bigint_from_u64(@num, 0x123456789ABCDEF0);
    print("Decimal: \0");
    print(@num);
    print("\nHex: \0");
    bigint_print_hex(@num);
    print("\n\n\0");
    
    // Test 6: Maximum u64 value
    print("Test 6: From u64 (0xFFFFFFFFFFFFFFFF)\n\0");
    bigint_from_u64(@num, 0xFFFFFFFFFFFFFFFF);
    print("Decimal: \0");
    print(@num);
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
    
    // Test 9: 96-bit number (using u64 array)
    print("Test 9: 96-bit number (3 u32 digits)\n\0");
    u64[2] vals96;
    vals96[0] = (u64)0x9876543210ABCDEFu;
    vals96[1] = (u64)0x0000000012345678u;
    bigint_from_u64_array(@num, @vals96[0], 2);
    print("Hex: \0");
    bigint_print_hex(@num);
    print("\nLength: \0");
    print((int)num.length);
    print(" u32 digits\n\n\0");
    
    // Test 10: 128-bit number (using u64 array)
    print("Test 10: 128-bit number (4 u32 digits)\n\0");
    u64[2] vals128;
    vals128[0] = 0xFEDCBA9876543210u;
    vals128[1] = 0x123456789ABCDEF0u;
    bigint_from_u64_array(@num, @vals128[0], 2);
    print("Hex: \0");
    bigint_print_hex(@num);
    print("\nLength: \0");
    print((int)num.length);
    print(" u32 digits\n\n\0");
    
    // Test 11: 256-bit number (using u32 array)
    print("Test 11: 256-bit number (8 u32 digits)\n\0");
    u32[8] vals256;
    vals256[0] = (u32)0x11111111u;
    vals256[1] = (u32)0x22222222u;
    vals256[2] = (u32)0x33333333u;
    vals256[3] = (u32)0x44444444u;
    vals256[4] = (u32)0x55555555u;
    vals256[5] = (u32)0x66666666u;
    vals256[6] = (u32)0x77777777u;
    vals256[7] = (u32)0x88888888u;
    bigint_from_u32_array(@num, @vals256[0], 8);
    print("Hex: \0");
    bigint_print_hex(@num);
    print("\nLength: \0");
    print((int)num.length);
    print(" u32 digits\n\n\0");
    
    // Test 12: 512-bit number (using u64 array)
    print("Test 12: 512-bit number (16 u32 digits)\n\0");
    u64[8] vals512;
    vals512[0] = (u64)0xAAAAAAAAAAAAAAAA;
    vals512[1] = (u64)0xBBBBBBBBBBBBBBBB;
    vals512[2] = (u64)0xCCCCCCCCCCCCCCCC;
    vals512[3] = (u64)0xDDDDDDDDDDDDDDDD;
    vals512[4] = (u64)0xEEEEEEEEEEEEEEEE;
    vals512[5] = (u64)0xFFFFFFFFFFFFFFFF;
    vals512[6] = (u64)0x0000000000000000;
    vals512[7] = (u64)0x1111111111111111;
    bigint_from_u64_array(@num, @vals512[0], 8);
    print("Hex: \0");
    bigint_print_hex(@num);
    print("\nLength: \0");
    print((int)num.length);
    print(" u32 digits\n\n\0");
    
    // Test 13: 1024-bit number (using u32 array)
    print("Test 13: 1024-bit number (32 u32 digits)\n\0");
    u32[32] vals1024;
    u32 j;
    for (j = 0; j < 32; j++)
    {
        vals1024[j] = (u32)0xDEADBEEF;
    };
    bigint_from_u32_array(@num, @vals1024[0], 32);
    print("Hex: \0");
    bigint_print_hex(@num);
    print("\nLength: \0");
    print((int)num.length);
    print(" u32 digits\n\n\0");
    
    // Test 14: Test with leading zeros (should trim)
    print("Test 14: Number with leading zeros (should trim)\n\0");
    u32[5] valsLeading;
    valsLeading[0] = (u32)0x12345678;
    valsLeading[1] = (u32)0xABCDEF00;
    valsLeading[2] = (u32)0x00000000;
    valsLeading[3] = (u32)0x00000000;
    valsLeading[4] = (u32)0x00000000;
    bigint_from_u32_array(@num, @valsLeading[0], 5);
    print("Hex: \0");
    bigint_print_hex(@num);
    print("\nLength: \0");
    print((int)num.length);
    print(" u32 digits (should be 2)\n\n\0");
    
    print("==== ALL FOUNDATION TESTS COMPLETE ====\n\0");
    
    return 0;
};
