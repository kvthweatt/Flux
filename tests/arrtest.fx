#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int[] arr = [10, 20, 30, 40, 50, 0];

    arr[0..4] = arr[4..0];

    println(arr[1]);
    return 0;
};