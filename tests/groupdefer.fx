#import "standard.fx";

using standard::io::console;

def main() -> int
{
    println("Hello!");
    defer
    {
        println("Test1!");
        println("Test2!");
    };
    return 0;
};