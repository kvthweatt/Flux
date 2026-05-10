#import "standard.fx";

using standard::io::console;

#def KEY byte(0x42);

def print_password() -> void
{
    int c = 9;
    byte[c] encrypted = [0x32, 0x76, 0x31, 0x31, 0x35, 0x72, 0x30, 0x26, 0x63];
    byte tmp;

    for (x in encrypted)
    {
        print(x ^^ KEY + '\x00');
    };
};

def main() -> int
{
    print_password();
    return 0;
};