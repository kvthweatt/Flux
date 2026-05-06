#import "standard.fx";

using standard::io::console;

def main() -> int
{
    for (int i; i < 1000000; i++)
    {
        int c = i;
        println(c);
    };
    return 0;
};