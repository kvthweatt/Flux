#import "standard.fx";

using standard::io::console;

struct Test
{
    int x;
};

def main() -> int
{
    noopstr str = "ABCD";
    byte[4] bytes = [0x65, 0x66, 0x67, 0x68];
    

    Test t from str[0:4]!;   // ! at the end means do not invalidate str
    Test v from bytes;       // bytes invalidated

    println(long((@)str));
    println(long(@t.x));

    println(long((@)bytes)); // unknown identifier bytes, must redeclare here
    println(long(@v.x));

    return 0;
};