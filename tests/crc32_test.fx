// crc32_test.fx — tests for crc32.fx

#import "standard.fx";
#import "crc32.fx";

using standard::io::console;

def main() -> int
{
    int passed = 0,
        failed = 0;
    uint result;

    // "123456789" → 0xCBF43926 (canonical CRC32 check value)
    byte[] msg1 = "123456789";
    result = crc32::of_string(@msg1[0]);
    if (result == 0xCBF43926u)
    {
        println("PASS: CRC32(\"123456789\") = 0xCBF43926\0");
        passed++;
    }
    else
    {
        println(f"FAIL: CRC32(\"123456789\") = 0x{result:X}, expected 0xCBF43926\0");
        failed++;
    };

    // Empty input → 0x00000000
    result = crc32::compute("", 0u);
    if (result == 0x00000000u)
    {
        println("PASS: CRC32(\"\") = 0x00000000\0");
        passed++;
    }
    else
    {
        println(f"FAIL: CRC32(\"\") = 0x{result:X}, expected 0x00000000\0");
        failed++;
    };

    // Single zero byte → 0xD202EF8D
    byte[1] zero_byte;
    zero_byte[0] = 0x00;
    result = crc32::compute(@zero_byte, 1u);
    if (result == 0xD202EF8Du)
    {
        println("PASS: CRC32([0x00]) = 0xD202EF8D\0");
        passed++;
    }
    else
    {
        println(f"FAIL: CRC32([0x00]) = 0x{result:X}, expected 0xD202EF8D\0");
        failed++;
    };

    // Single 0xFF byte → 0xFF000000
    byte[] ff_byte = [0xFF];
    result = crc32::compute(@ff_byte, 1u);
    if (result == 0xFF000000u)
    {
        println("PASS: CRC32([0xFF]) = 0xFF000000\0");
        passed++;
    }
    else
    {
        println(f"FAIL: CRC32([0xFF]) = 0x{result:X}, expected 0xFF000000\0");
        failed++;
    };

    // "The quick brown fox jumps over the lazy dog" → 0x414FA339
    byte[] msg2 = "The quick brown fox jumps over the lazy dog";
    result = crc32::of_string(@msg2[0]);
    if (result == 0x414FA339u)
    {
        println("PASS: CRC32(\"The quick brown fox...\") = 0x414FA339\0");
        passed++;
    }
    else
    {
        println(f"FAIL: CRC32(\"The quick brown fox...\") = 0x{result:X}, expected 0x414FA339\0");
        failed++;
    };

    println(f"\n{passed} passed, {failed} failed.\0");

    return failed;
};
