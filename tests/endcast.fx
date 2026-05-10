#import "standard.fx";

using standard::io::console;

def main() -> int
{
    be32 x = 0xAABBCCDD;
    le32 y = x;

    print_hex(uint(y));
    return 0;
};