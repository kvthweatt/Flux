#import "standard.fx";

using standard::io::console,
      standard::strings;

def main() -> int
{
    string h = "Hello";
    string w = "World!";

    println("ll" in h);

    println("le" in h[h.len()-1:0]);

    print(f"{h} {w}");
    return 0;
};