# Flux Keyword Reference

Flux keywords are reserved, and cnanot be used as identifiers.  
This means you cannot do `int data;`, this is illegal.

---

**`alignof`**
Returns the alignment requirement of a type in bits.
```
alignof(int)   // 32, dependent on target system, and configurable.
```

---

**`and`**
Logical AND operator. Equivalent to `&`.
```
if (x > 0 and y > 0) { ... };
```

---

**`as`**
Creates a type alias.
```
unsigned data{32} as u32;
```

---

**`asm`**
Inline assembly block.
```
asm { movq $$0, %rax };
```

---

**`assert`**
Halts compilation or execution if condition is false.
```
assert(x > 0);
```

---

**`auto`**
Infers the type of a variable from its initializer.
```
auto x = 5;   // x is a char, if greater than char it promotes to uint, if greater than int max value, it is a ulong. Not recommended.
```
`auto` will attempt within reason, to infer the integer or floating type, and will be a built-in dependent on its value.
- It will always attempt to coerce to the smallest width type.
The example `auto x = 5;` makes `x` a `char`.

---

**`bool`**
Boolean type. Values are `true` or `false`. Default is `false` due to zero initialization.  
Any integer type, bitwise respective, can be coerced to a bool in context so long as it the value is 1 or 0.  
`float` and `double` types that precisely equal `1.0` and `0.0` will evaluate as `true` and `false` respectively.
```
bool flag = true;
```

---

**`break`**
Exits the nearest enclosing loop or switch.
```
while (true) { break; };
```

---

**`byte`**
Single byte type. Width configurable via `__BYTE_WIDTH__`, default 8 bits.
```
byte b = 0xFF;
```

---

**`case`**
Defines a branch in a switch statement. Does not require semicolon block termination.
```
switch (x) { case (1) { ... } default {}; };
```

---

**`catch`**
Handles a thrown exception.
```
try { ... } catch (int e) { ... };
```

---

**`cdecl`**
Declares a function using the cdecl calling convention. Used in place of `def`.
```
cdecl foo(int x) -> int { return x; };
```

---

**`char`**
Character type. Guaranteed 8 bits.
```
char c = 'H';
```

---

**`const`**
Marks a variable as immutable after initialization.
```
const int x = 10;
```

---

**`continue`**
Skips to the next iteration of the nearest enclosing loop.
```
for (int i; i < 10; i++) { if (i == 5) { continue; }; };
```

---

**`data`**
Declares a raw bit-width type. Can be signed or unsigned.
```
unsigned data{32} as u32;
signed data{64} as i64;
```

---

**`def`**
Declares or defines a function. `fastcall` calling convention by default. Configurable.
```
def add(int x, int y) -> int { return x + y; };
```

---

**`default`**
Fallback branch in a switch statement. Requires semicolon block termination.
```
switch (x) { case (1) { ... } default { ... }; };
```

---

**`deprecate`**
Marks a namespace, object member, or function signature as deprecated. Emits an error on use.  
Applied to the declaration, not the definition.
```
deprecate oldFunc() -> void;
deprecate oldLib;    // Namespace will be identified
deprecate oldMember; // Type will be identified by definition
```

---

**`do`**
Enter a `do` loop.
```
do { x++; };
```
Adding `while`
```
do { x++; } while (x < 10);
```

---

**`double`**
64-bit floating point type.
```
double pi = 3.1415926585;
```

---

**`elif`**
Else-if branch in a conditional chain.
```
if (x == 1) { ... } elif (x == 2) { ... } else { ... };
```

---

**`else`**
Fallback branch of an `if` statement.
```
if (x > 0) { ... } else { ... };
```

---

**`enum`**
Declares an enumeration of named integer constants.
```
enum Color { RED, GREEN, BLUE };
```

---

**`export`:
Define a function as external for linkage. Used when creating libraries or to allow a function to be   
seen from outside the program's compilation unit.  
Only definitions are used with `export`.
```
export
{
    def !!foo() -> int
    {
        int a = 1, b = 10;
        int[10] x = [y for (int y in a..b)];
        return x[5];
    };
};
```

---

**`extern`**:
External FFI - reference a function from a library.
Only prototypes are used with `extern`.
```
extern
{
    def !!foo() -> int;
};
```

---

`extern` and `export` are mutually exclusive, you cannot do:
`extern export { ... };` or `export extern def ...;`

---

**`escape`**
Exits a strictly-recursive function and returns a value up the call chain. Every `return` in a strictly-recursive function re-enters itself; `escape` is the only true exit.  
A strictly-recursive function is defined with a recurse arrow `<~` in its signature instead of a return arrow `->`.
```
def factorial <~ int (int n, int acc)
{
    if (n <= 1) { escape acc; };
    return factorial(n - 1, acc * n);
};
```

---

**`false`**
Boolean literal false. Equivalent to `0`.
```
bool flag;
```

---

**`fastcall`**
Declares a function using the fastcall calling convention. Used in place of `def`.
```
fastcall foo(int x) -> int { return x; };
```

---

**`float`**
64-bit floating point type. Same as `double`.
```
float x = 3.14159;
```

---

**`for`**
Declares a for loop. Supports both C-style and for-in iteration.
```
for (int i; i < 10; i++) { ... };
for (int x in arr) { ... };
```

---

**`global`**
Declares a variable at global scope regardless of where it appears.
```
global int counter;
```

---

**`goto`**
Unconditional jump to a `label`.
```
goto myLabel;
```

---

**`heap`**
Allocates a variable on the heap explicitly.
```
heap int x = 10;
```
This calls `fmalloc(sizeof(T))` where `T` is the type. `x` is a pointer of type `T`.  
It is **not** the same as `int* x = @10;`, as this is a stack-allocated pointer & value.

---

**`if`**
Conditional branch. Single-statements must be wrapped in a block.
```
if (x > 0) { ... };
```

---

**`in`**
Used in for-in loops to specify the iterable.
```
for (int x in arr) { ... };
```

---

**`int`**
32-bit signed integer type.
```
int x = 42;
```

---

**`is`**
Equivalent to `==`.
```
if (x is 5) { ... };
```

---

**`jump`**
Jump to a target address. Any integer value will be treated as an address.

A jump to an address with no executable memory will cause a crash.
```
jump 0;

jump @func;
```

---

**`label`**
Declares a jump target for `goto`.
```
label myLabel:
```
Use like:
```
def foo() -> int
{
label j1:
    // code
    goto j3;
label j2:
    // code
    goto final;
label j3:
    // code
    goto j2;
label final:
    // return
};
```

---

**`local`**
Explicitly marks a variable as local scope. Cannot escape its scope via return or by being passed to a function.
```
local int x = 10;
```
Example:
```
def foo(int x) -> int { return x; };

def baz() -> int { local int z = 50; return z; }; // Compile error, z cannot leave function.

def bar() -> void
{
    local int x = 10;
    int y = foo(x); // Compile error, x cannot leave scope.
}
```

---

**`long`**
64-bit signed integer type.
```
long x = 1000000000000;
```

---

**`namespace`**
Declares a named scope for organizing code.
```
namespace math { def square(int x) -> int { return x * x; }; };
```

---

**`noinit`**
Suppresses zero-initialization of a variable.
```
int x = noinit;
```

---

**`noreturn`**
Marks a point in code as unreachable. Emits LLVM `unreachable`.
```
noreturn;
```

---

**`not`**
Logical NOT operator. Equivalent to `!`.
```
if (not flag) { ... };
```
Can also perform `not using`:
```
not using standard::math::calculus;
```

---

**`object`**
Declares an object type with methods and state.
```
object Point { int x, y; def __init(int x, int y) -> this { ... }; ...; };
```

---

**`operator`**:
Define a custom infix operator. Can use symbols or an identifier as the operator.  
To overload a built-in operator, one of the operands **must not** be a built-in type, ie `int`, `float`, `byte`, etc.
TODO

---

**`or`**
Logical OR operator. Equivalent to `|`.
```
if (x == 0 or y == 0) { ... };
```

---

**`private`**
Restricts member access to within the object. Members must be wrapped in a block.
```
object Foo { private { int secret; }; };
```

---

**`public`**
Explicitly marks a member as externally accessible. Members must be wrapped in a block. Object members are public by default.
```
object Foo { public { int value; }; };
```

---

**`register`**
Hints that a variable should be stored in a CPU register. Not enforced, but strongly hinted.
```
register int i;
```

---

**`return`**
Returns a value from a function. In strictly-recursive functions, re-enters the function.
```
return x + y;
```

---

**`signed`**
Declares a signed data type. Types are unsigned by default.
```
signed data{32} as i32;
```

---

**`singinit`**
Declares a singleton. Function-scoped variable that is initialized only once across all calls.
```
singinit int count;
```

---

**`sizeof`**
Returns the size of a type or value in bits, never bytes. Divide by `sizeof(byte)` to get accurate byte widths.
```
sizeof(int)   // 32
```

---

**`stack`**
Explicitly marks a variable as stack allocated. This is default behavior and implicit in any non-heap allocation.
```
stack int x = 10;
```
Identical to:
```
int x = 10;
```

---

**`stdcall`**
Declares a function using the stdcall calling convention. Used in place of `def`.
```
stdcall foo(int x) -> int { return x; };
```

---

**`struct`**
Declares a packed data structure. Padding dependent on the alignment of the types within.
```
struct Point { int x, y; }; // 64 bits wide. This can pack into a long or any 64 bit wide type.
```

---

**`switch`**
Multi-branch conditional on a value.
```
switch (x) { case (1) { ... } default {}; };
```

---

**`this`**
Refers to the current object instance's pointer inside an object method.
```
def __init(int x) -> this { this.x = x; return this; };
```

---

**`thiscall`**
Declares a function using the thiscall calling convention. Used in place of `def`.
```
thiscall foo(int x) -> int { return x; };
```

---

**`throw`**
Throws an exception value.
```
throw(42);
```

---

**`trait`**
Declares a contract that an object must implement.
```
trait Drawable { def draw() -> void; };
```

---

**`true`**
Boolean literal true. Equivalent to `1`.
```
bool flag = true;
```

---

**`try`**
Begins a block that can throw exceptions.
```
try { ... } catch (int e) { ... };
```

---

**`uint`**
32-bit unsigned integer type.
```
uint x = 4294967295;
```

---

**`ulong`**
64-bit unsigned integer type.
```
ulong x = 18446744073709551615;
```

---

**`union`**
Declares a type where all members share the same memory.
```
union Data { int i; float f; };
```

---

**`unsigned`**
Declares an unsigned data type.
```
unsigned data{32} as u32;
```

---

**`using`**
Brings a namespace into the current scope.
```
using standard::io::console;
```

---

**`vectorcall`**
Declares a function using the vectorcall calling convention. Used in place of `def`.
```
vectorcall foo(int x) -> int { return x; };
```

---

**`void`**
Represents the absence of a value. Also used as a null pointer literal.
```
def foo() -> void { return; };
void* p = (void*)void; // (void*)0;
```

---

**`volatile`**
Prevents the compiler from optimizing accesses to a variable or assembly block.
```
volatile int x = 0;
volatile asm { ... };
```

---

**`while`**
Declares a while loop.
```
while (x > 0) { x--; };
```

---

**`xor`**
Bitwise XOR operator. Note: `^` is exponentiation.
```
int result = a xor b;
```