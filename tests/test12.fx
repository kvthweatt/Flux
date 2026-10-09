#def FLUX_SHADOW_STACK 1;
#import <standard.fx>;

using standard::io::console,
      standard::random;

def grade(int score) -> byte*
{
    if   (score >= 90) -> "A"
    elif (score >= 80) -> "B"
    elif (score >= 70) -> "C"
    elif (score >= 60) -> "D"
    else               -> "F";
};

comptime
{

    operator (i32 a) [&] -> int
    {
        // something involving a
        return ++a;
    } # binding {:this};

    operator (int a, int b, byte c) [$%][%$] -> int
    {
        return a + b * c;
    };

    float k = 10.0;
    int j from k;
    compiler.io.console.println(j);

    compiler.io.console.println("True" if (5 < 10 < 20) else "False");

    def add(int,i32) -> int as operator[\];

    def add(int a, i32 b) -> int
    {
        return a+b;
    };

    FXC_SYMTABLE st = compiler.symbol_table;
    FXC_SYMENTRY e;
    int i;
    while (i < st.entries)
    {
        e = st.entry[i];
        //compiler.io.console.println(f"{e.name} : {e.kind} : -> {e.type.base_type}\n{compiler.symbol_table.funcinfo(e.name).has_effect}\n") if (e.kind == "function");
        i++;
    };

    int x = 1 $% 2 %$ 3;

    compiler.io.console.println(x);   // 7

    compiler.io.console.println(5\2); // 7

    compiler.io.console.println(9&);  // 10

    FXC_FUNCINFO fi = compiler.symbol_table.funcinfo("standard::io::console::println");
    compiler.io.console.println(f"println has_effect: {fi.has_effect}\n");
};

comptime
{
    compiler.io.console.print(f"arch: {compiler.target.arch}\n");
    compiler.io.console.print(f"os: {compiler.target.os}\n");
    compiler.io.console.print(f"ptr_width: {compiler.target.ptr_width}\n");
    compiler.io.console.print(f"has_avx: {compiler.target.has_avx}\n");
    compiler.io.console.print(f"cache_line: {compiler.target.cache_line}\n");
};

struct Point { int x, y; };
Point[4] pts = [{1,2},{3,4},{5,6},{7,8}];

struct ErrType
{
    byte* msg;
};

f() -> int -> 42;

operator (int x) [|][|] -> int -> x < void ? -x : x;

main() -> int : FSS_Protect_Frame
{
    int result = f();

    int a = -1;

    println(5 * |a|);

    for (auto {x, y} in pts)
    {
        println(x);
        println(y);
    };
    println("Hello World!");
    println(f"Grade: {grade(100)}");
    return 0;
} : FSS_Cleanup_Frame # effect {!IO.Console.Output};