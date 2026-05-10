#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int x = 10;
    heap int y = 5;
    int* z = (int*)fmalloc(32);

    (void)y;
    (void)z;

    print_hex(long(@x)); print();
    //print_hex(long(@y)); print();
    //print_hex(long(@z));

    return 0;
};