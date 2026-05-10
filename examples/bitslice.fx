#import "standard.fx";

using standard::io::console;

struct xx { int a, b; };

def main() -> int
{
    data{4} as u4;
    data{2} as u2;
    xx yy = {5,10};
    u4 a = yy[60``63]; // 10 because 0b1010
    u2 b = a[0``1];

    print(int(b)); // 2, because 0b10

    return 0;
};