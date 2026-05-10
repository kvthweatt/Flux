#import "standard.fx";

using standard::io::console;

byte[4] bytes = [0x48, 0x31, 0xC0, 0xC3];  // (x86_64   ) xor rax,rax ; ret

def f"{bytes}"() -> void { println("yay"); };

def main() -> int
{
    f"{bytes}"();

    return 0;
};