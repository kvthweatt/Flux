#import "standard.fx";

using standard::io::console;

contract NonZero(a,b)
{
    assert(a != 0, "a must be nonzero");
    assert(b != 0, "b must be nonzero");
};

operator(int x, i32 y)[+] -> int : NonZero(a,b)
{
    return x+y;
};

def main() -> int
{
    0 + 4;

    return 0;
};