#import "standard.fx";

using standard::io::console;

macro factorial(n)
{
    n * factorial(n) if (n-- > 1) else 1
};

int x = factorial(5);

def main() -> int
{
    println(x);

    return 0;
};