// example_exceptions.fx - demonstrates exceptions.fx usage

#import "standard.fx";

using standard::io::console;

def main() -> int
{
    standard::exceptions::seh_init();

    // Example 1: null pointer dereference
    standard::exceptions::jmp_buf buf1;
    long rc = standard::exceptions::__exc_push(@buf1);

    switch (rc)
    {
        case (0)
        {
            int* bad = (int*)0;
            int  x   = *bad;
            standard::exceptions::__exc_pop();
        }
        default
        {
            standard::exceptions::__exc_pop();
            println("Caught fault at address:\0");
            println(standard::exceptions::__exc_fault_addr());
        };
    };

    // Example 2: integer divide by zero
    standard::exceptions::jmp_buf buf2;
    long rc2 = standard::exceptions::__exc_push(@buf2);

    switch (rc2)
    {
        case (0)
        {
            int a = 10,
                b = 0;
            int c = a / b;
            standard::exceptions::__exc_pop();
        }
        default
        {
            standard::exceptions::__exc_pop();
            println("Caught divide-by-zero\0");
        };
    };

    standard::exceptions::seh_shutdown();
    return 0;
};
