#import "standard.fx";

~$"int x = 10;";

byte* = "int y = 5;";

~$i"{}":{t;};

byte* str = "using standard::io::console;

def main() -> int
{
    println(f\"Hello World! {y}\");

    return 0;
};";

~$str;