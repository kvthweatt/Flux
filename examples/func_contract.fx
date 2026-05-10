#import "standard.fx";

using standard::io::console;

contract NonZero
{
    assert(x > 0, "x must be positive");
};

contract rValGT10
{
    assert(x > 10, "r must be greater than 10");
};

def foo(int x) -> int : NonZero
{
    x = x / 2;
    return x;
} : rValGT10;

def main() -> int
{
    int y = foo(18);

    return 0;
};