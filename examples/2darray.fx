#import "standard.fx";

using standard::io::console;

struct Test
{
    int[3][3] a;
};

def main() -> int
{
    Test t;

    t.a = [[1,2,3],[4,5,6],[7,8,9]];

    print(t.a[0][1]);
    print(t.a[1][1]);
    print(t.a[2][1]);
    return 0;
};