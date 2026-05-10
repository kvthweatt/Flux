#import "standard.fx";

using standard::io::console;

def main() -> int
{
    byte[4] bytes = [0x30, 0x24, 0x22, 0x3C];

    byte[4] bytes2 = [101, 113, 119, 105];

    for (b in bytes)
    {
        println(int(b `^^ 0x55));
    };

    for (b in bytes2)
    {
        print_hex(int(b `^^ 0x55)); print();
    };

    return 0;
};