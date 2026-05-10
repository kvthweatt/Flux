#import "standard.fx";

using standard::io::console;

def bar(~int y) -> ~int  // returns a tied type
{
    return ~y;
};

def main() -> int
{
    ~int x, y, z; // Tied vars
    int  w = 5;   // Non-tied var

    x = bar(~y);
    z = ~w;

    int w = 10;
    
    println(z);

    return 0;
};
