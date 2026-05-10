#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int c = 5;
    ulong[5] addrs = [0,0,0,0,0];

    for (int i; i < c; i++)
    {
        int x = 5;
        addrs[i] = ulong(@x);
    };

    for (int i; i < c; i++)
    {
        print_hex(addrs[i]); print(f" = {*(@)addrs[i]}\n");
    };

    return 0;
};