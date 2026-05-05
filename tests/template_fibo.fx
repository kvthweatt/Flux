#import "standard.fx", "math.fx", "format.fx";

using standard::io::console,
      standard::format;

def fibonacci<T>(T n) -> T
{
    if (n <= (T)1)
    {
        return n;
    };

    int test;

    T a = (T)0,
      b = (T)1,
      c = (T)2,
      temp;
    
    while (c <= n)
    {
        temp = a + b;
        a = b;
        b = temp;
        c = c + (T)1;
    };
    
    return b;
};

def main() -> int
{
    println_colored("Fibonacci Calculator\0", colors::YELLOW);
    hline_heavy(30);
    u64 x;
    
    for (u64 i = 0; i <= 93; i++)
    {
        print_cyan("fib(\0");
        print(i);
        print_cyan(") = \0");
        x = fibonacci(i);
        print(x);
        print("\n\0");
    };
    
    return 0;
};