#def FLUX_SHADOW_STACK 1;
#import <standard.fx>;

using standard::io::console;

struct Point { int x, y; };
Point[4] pts = [{1,2},{3,4},{5,6},{7,8}];

def main() -> int : FSS_Protect_Frame
{
    for (auto {x, y} in pts)
    {
        println(x);
        println(y);
    };
    println("Hello World!");
    return 0;
} : FSS_Cleanup_Frame # effect {!IO.Console.Output};