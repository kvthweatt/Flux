#import "standard.fx";

#import "math.fx";


using standard::io::console;

#def MAX_32 (i32)0xFFFFFFFF;
#def MAX_64 (u64)0xFFFFFFFFFFFFFFFF;

def main() -> int
{
    // Set to all 1s
    u32 max32  = MAX_32;
    u64 max64  = MAX_64;

    u32 maxu32 = MAX_32;
    u64 maxu64 = MAX_64;

    print("Start...\n\0");

    u32 ux32 = popcount(max32);
    if (ux32 == 32)
    {
        print("Signed 32-bit popcount() success!\n\0");
    }
    else
    {
        print("Signed 32-bit popcount() failed.\n\0");
    };

    u64 ux64 = popcount(max64);
    if (ux64 == 64)
    {
        print("Signed 64-bit popcount() success!\n\0");
    }
    else
    {
        print("Signed 64-bit popcount() failed.\n\0");
    };

    print("End.\n\0");
	return 0;
};