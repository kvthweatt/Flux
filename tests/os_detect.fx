#import "redstandard.fx";

using standard::io::console;

def main() -> int
{
    #ifdef __WINDOWS__
    print("Windows detected.",17);
    #endif;
    #ifdef __LINUX__
    print("Linux detected.\n",16);
    #endif;

    return 0;
};