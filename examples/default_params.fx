#import "standard.fx";
using standard::io::console;

def foo(int x = 5, int y = 2) -> int
{
    return x + y;
};

def main() -> int
{
    int x = foo();

    if (x == 6)
    {
        println("Success, x is 6!");
    }
    elif (x == 7)
    {
        println("Success, x is 7!");
    };
    return 0;
};