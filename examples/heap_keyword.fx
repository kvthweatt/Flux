#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int x = 10;
    heap int y = 5;
    int* z = (int*)fmalloc(sizeof(int));

    (void)y;
    (void)z;

    return 0;
};