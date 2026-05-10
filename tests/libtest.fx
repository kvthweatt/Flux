#import "standard.fx";

using standard::io::console;

extern def !!foo() -> int;

def main() -> int
{
	println(foo());

    return 0;
};