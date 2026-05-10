#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int[] y = [10, 20, 30, 40, 0];

    int[] x = [20, 30, 0];

    if (x in y)
    {
    	print(f"Found x in y!");
    };
    return 0;
};