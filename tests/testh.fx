#import "standard.fx";

using standard::io::console;

def !!__chkstk() -> void {};
int _fltused = 1;

object Test
{
    def __init() -> this
    {
        return this;
    };

    def __expr() -> Test* { return this; };

    def __exit() -> void { return; };
};

def main() -> int
{
    print(_fltused);
    return 0;
};