#import "standard.fx";

using standard::io::console;

def main() -> int
{
    i16 x = 0b1011010011110100;

    data{6} as u6;

    u6 y = x[0``5];

    if (y in x)
    {
        println("Success!");
    };
    return 0;
};