#import "standard.fx";

using standard::io::console;

def main() -> int
{
    try
    {
        throw("Test throw...");
        for (int i; i < 1000000; i++)
        {
            int c = i;
            println(c);
        };
    }
    catch (byte* e)
    {
        println(e);
    };
    return 0;
};