#import "standard.fx";

using standard::io::console,
      standard::strings;

def main() -> int
{
    string str = "Testing!";

    print(str.val()[str.len()-1:0]);
    return 0;
};