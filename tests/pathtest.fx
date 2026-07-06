#import <standard.fx>;

using standard::io::console;

object Path
{
    byte* raw;

    def __init(byte* filepath) -> this
    {
        this.raw = filepath;
        return this;
    };

    def __expr() -> Path* { return this; };

    def __exit() -> void { (void)this; };
};

operator (Path L, Path R)[\] -> byte*
{
    return f"{L.raw}\\{R.raw}\0";
};

def main() -> int
{
    Path p1("C:\\Users\\kvthw\\Flux\\tests");
    Path p2("pathtest.fx");

    byte* t = p1 \ p2;

    println(t);

    //Path p3(p1 \ p2);

    //println(p3.raw);

    return 0;
};