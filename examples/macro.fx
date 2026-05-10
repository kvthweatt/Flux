#import "standard.fx";

using standard::io::console;

macro testMac(a,b,c)
{
    (a + b) ^ c
};

macro testMac2(a,b)
{
    testMac(1,2,a) * b
};

def main() -> int
{
    int x,y,z = 1,2,3;

    println(f"testMac(x,y,z) = {testMac(x,y,z)}"); // {(1 + 2) ^ 3}

    println(testMac(x,y,z) + 1);

    println(testMac2(3,4));

    return 0;
};