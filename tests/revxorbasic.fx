#import "standard.fx";

using standard::io::console;

def main() -> int
{
    byte[9] enc = [0x32, 0x76, 0x31, 0x31, 0x35, 0x72, 0x30, 0x26, 0x63];

    for (x in enc)
    {
        println(int(x `^^ byte(0x42)));
    };
    return 0;
};