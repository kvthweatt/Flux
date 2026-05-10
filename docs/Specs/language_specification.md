<a id="flux"></a>
# Flux

Flux is a compiled, general purpose programming language.

It provides power with ease of writing.

If you like Flux, please consider contributing to the project or joining the [Flux Discord server](https://discord.gg/RAHjbYuNUc) where you can ask questions, provide feedback, and talk with other Flux enjoyers!

**Creator note** Everything in Flux is **stack allocated** unless specified.  
- This means you are likely to introduce stack overflows if you perform stack allocations inside loops such as declaring a new variable each time a loop passes.

---

## Table of Contents

- [Flux](#flux)
  - [Functions](#functions)
  - [Importing with `import`](#importing-with-import)
    - [Very simple preprocessor](#very-simple-preprocessor)
  - [Namespaces](#namespaces)
  - [Structs](#structs)
    - [You can template structs by using angle brackets `<`,`>`](#you-can-template-structs-by-using-angle-brackets)
  - [Objects](#objects)
    - [Required methods](#required-methods)
  - [Deferred object cleanup with `defer`](#deferred-object-cleanup-with-defer)
  - [Traits](#traits)
  - [Public/Private with Objects/Structs](#publicprivate-with-objectsstructs)
  - [i-Strings and f-Strings](#istrings-and-fstrings)
  - [Pointers](#pointers)
  - [You can also use in-line assembly directly](#you-can-also-use-inline-assembly-directly)
  - [Logic with if/elif/else](#logic-with-ifelifelse)
  - [The `data` keyword](#the-data-keyword)
    - [Mixing Signed/Unsigned in Expressions](#mixing-signedunsigned-in-expressions)
  - [Endianness Handling](#endianness-handling)
  - [Casting](#casting)
  - [Stringification with `$`](#stringification-with)
  - [Codification](#codification)
  - [Direct type conversion](#direct-type-conversion)
  - [The `typeof`, `sizeof`, `alignof`, and `endianof` built-ins](#the-typeof-sizeof-alignof-and-endianof-builtins)
  - [`void` as a literal](#void-as-a-literal)
  - [Arrays](#arrays)
  - [Loops](#loops)
  - [Single-initialized variables with `singinit`](#singleinitialized-variables-with-singinit)
  - [Recursion](#recursion)
  - [Strict Recursion with `<~`](#strict-recursion-with)
  - [Escaping strict recursion with `escape`](#escaping-strict-recursion-with-escape)
  - [Error handling with `try`/`throw`/`catch`](#error-handling-with-trythrowcatch)
  - [Enumerated Lists](#enumerated-lists)
  - [Unions](#unions)
  - [Tagged unions](#tagged-unions)
  - [Switching](#switching)
  - [Namespace elimination with `!using` or `not using`](#namespace-elimination-with-using-or-not-using)
  - [Deprecation with `deprecate`](#deprecation-with-deprecate)
  - [Assertion with `assert()`](#assertion-with-assert)
  - [Heap allocation](#heap-allocation)
  - [Freeing from the heap](#freeing-from-the-heap)
  - [Custom infix operators and overloading](#custom-infix-operators-and-overloading)
  - [Functions and `contract`](#functions-and-contract)
  - [Contracts on operators](#contracts-on-operators)
  - [Expression-based macros with `macro`](#expressionbased-macros-with-macro)
  - [Templates](#templates)
  - [Templating operators](#templating-operators)
  - [Combining templates, contracts, and operators](#combining-templates-contracts-and-operators)
  - [Variadic functions](#variadic-functions)
  - [Chaining Functions](#chaining-functions)
  - [External Functions (FFI)](#external-functions-ffi)
  - [Exporting Functions with `export`](#exporting-functions-with-export)
  - [Advanced pointer manipulation](#advanced-pointer-manipulation)
    - [Taking address of literals](#taking-address-of-literals)
    - [Pointer to integer conversions](#pointer-to-integer-conversions)
  - [Memory Layout and Alignment Tricks](#memory-layout-and-alignment-tricks)
    - [Bit-Field Manipulation](#bitfield-manipulation)
    - [Advanced data manipulation techniques](#advanced-data-manipulation-techniques)
    - [Reworking a loop](#reworking-a-loop)
    - [Bit slices](#bit-slices)
    - [Taking bit slices from structs](#taking-bit-slices-from-structs)
    - [Bit slices of bit slices](#bit-slices-of-bit-slices)
  - [Advanced Data Type Features](#advanced-data-type-features)
    - [Unusual Bit Widths](#unusual-bit-widths)
  - [Function Pointers](#function-pointers)
  - [Callbacks](#callbacks)
  - [Raw bytecode functions](#raw-bytecode-functions)
  - [Ownership with the tie operator `~`](#ownership-with-the-tie-operator)
  - [Control Flow Edge Cases](#control-flow-edge-cases)
    - [Nested Switches with Fallthrough](#nested-switches-with-fallthrough)
    - [Complex Try/Catch with Multiple Types](#complex-trycatch-with-multiple-types)
    - [Nested Loops with Break/Continue](#nested-loops-with-breakcontinue)
    - [Simple Packet Parser](#simple-packet-parser)
    - [Fixed-Point Math](#fixedpoint-math)
  - [Type System Edge Cases](#type-system-edge-cases)
    - [`void` semantics](#void-semantics)
- [Calling Conventions](#calling-conventions)
- [Keyword list](#keyword-list)
- [Operator list](#operator-list)
  - [Primitive types](#primitive-types)
  - [All types](#all-types)
  - [Preprocesor directives](#preprocesor-directives)


<a id="functions"></a>
## **Functions**

You cannot define a function within a function. They must be module, namespace, or object level.

Prototype:
```
// Single declaration
def name(parameters) -> void;

// Multi-declaration
def name(int) -> bool,
    name(float) -> void,
    name(char*) -> int;   // Can prototype multiple functions at once, comma separated signatures.
```
Prototype signatures do not need a variable name, only types like `def foo(int,int,void*)->bool;`

Signature:
```
def name (parameters) -> return_type
{
    return return_value;
};
```

Example:
```
def myAdd(int x, int y) -> int
{
    return x + y;
};
```
Definitions require a variable name.

Overloading example:
```
def myAdd(float x, float y) -> float
{
    return x + y;
};
```

---

<a id="importing-with-import"></a>
## **Importing with `import`**

Any file you import will take the place of the import statement.

```
#import "standard.fx";
#import "mylib.fx", "foobar.fx";  // Multi-line imports are processed from left to right in the order they appear.
```

Example:  
**`somefile.fx`**

```
int myVar = 10;
```

**`main.fx`**

```
#import "somefile.fx";  // int myVar = 10;

def main() -> int
{
    if (myVar < 20)
    {
        // Do something ...
    };
    return 0;
};
```

<a id="very-simple-preprocessor"></a>
### Very simple preprocessor
```
#import "standard.fx";

#ifdef __WINDOWS__
#def DEFAULT_CONFIG_FLAG 0x4000;
#else
#ifdef __LINUX__
#def DEFAULT_CONFIG_FLAG 0x8000;
#endif;
#endif;

#warn "This will show a warning message.";

#stop "This will hard-stop compilation.";

#dir "C:\\path\\to\\some\\lib";
// Adds a path to the preprocessor's search list
```

`#def` defines a preprocessor constant. This is not a functional macro, just a replacement.

---

<a id="namespaces"></a>
## **Namespaces**

Prototype: `namespace myNamespace;`
Definition: `namespace myNamespace {};`  
Scope access: `myNamespace::myMember;`

Example:

```
namespace myNamespace
{
    def myFoo() -> void; // Legal
};

namespace myNamespace
{
    def myBar() -> void;        // namespace myNamespace now has myFoo() and myBar()
};

namespace myNamespace
{
    namespace myNestedNamespace
    {
        def myFooBar() -> void;
    };
};
```

Duplicate namespace definitions do not redefine the namespace, the members of both combine as if they were one namespace. This is so the standard library or any library can have a core namespace across multiple files.  
Namespaces are the only container that have this functionality.

---

<a id="structs"></a>
## **Structs**

Prototype / forward declaration: `struct myStruct;`  
Definition: `struct myStruct {int x,y,z;};`  
Instance: `myStruct newStruct;`  
Instance with assignment: `myStruct newStruct {x = 10, y = 20, z = -5};`  
Member access: `newStruct.x;`

Structs are packed and have no padding naturally. There is no way to change this.  
You set up padding with alignment in your data types.  
Members of structs are aligned and tightly packed according to their width unless the types have specific alignment.  
Structs are non-executable, and therefore cannot contain functions or objects.  
Placing a for, do/while, if/elif/else, try/catch, or any executable statements other than variable declarations will result in a compilation error.

Example:

```
struct xyzStruct
{
    int x,y,z;
};

struct newStruct
{
    xyzStruct myStruct {x = 1, y = 1, z = 1};              // structs can contain structs
};
```

Structs are non-executable.  
Structs cannot contain functions, or objects. This includes prototypes and definitions. Pointers are ok, including function pointers.  

Structs support composition via prepending and appending other structs. Example:
```
struct Header
{
    data{16} sig;
    data{32} filesize, reserved, dataoffset;
};

struct InfoHeader
{
    data{32} size, width, height;
    data{16} planes, bitsperpixel;
    data{32} compression, imagesize, xpixelsperm, ypixelsperm, colorsused, importantcolors;
};

struct ExtraData
{
    byte[64] author;
};

struct BMP : Header, InfoHeader
{
    // More bitmap fields
} : ExtraData;
```

<a id="you-can-template-structs-by-using-angle-brackets"></a>
### You can template structs by using angle brackets `<`,`>`:
```
struct myStru<A,B>
{
    A ax, ay, az;
    B bx, by, bz;
};
```
Composition and templates can be combined, however they **will** shadow.
```
struct myStru1<A,B>
{
    A a1x, a1y;
    B b1x, b1y;
};

struct myStru2<A,B,C> : myStru1
{
    A a2x, a2y, a2z;
    B b2x, b2y, b2z;
};

// Becomes,

struct myStru2<A,B,C>
{
    A a1x, a1y;
    B b1x, b1y;
    A a2x, a2y, a2z;
    B b2x, b2y, b2z;
};
```
If you intended for `a1x` to be a different type than `a2x`, you must use different parameter names.

Structs cannot contain objects, but objects can contain structs. This means struct template parameters cannot be `object` type.

---

<a id="objects"></a>
## **Objects**

Prototype / forward declaration: `object myObj;`  
Definition: `object myObj {};`  
Instance: `myObj newObj();`  
Member access: `newObj.x`

Objects are functional with behavior and are "executable" as opposed to structs which are pure data-only.

**Object Methods**  
`this` never needs to be a parameter as it is always local to its object.

<a id="required-methods"></a>
### Required methods:
```
__init()       -> this               Example: thisObj newObj();            // Constructor
__exit()       -> void               Example: newObj.__exit();             // Destructor
__expr()       -> any
```

`__init` is always called on object instantiation.  
`__exit` called manually to destroy the object.
`__expr` is the instance's expression context method. This method cannot take arguments.

If an object's `__init` method takes **only one parameter**, you may instance it like sO:
```
#import "standard.fx";

using standard::io::console;

object SomeOBJ
{
    int val;

    def __init(int x) -> this { return this; };

    def __exit() -> void {};

    def __expr() -> int { return this.val; };
};

def main() -> int
{
    SomeOBJ sobj = 5;

    println(sobj.val);   // Direct access

    println(sobj);  // Compiler detects object instance, emits print(sobj.__expr());

    println(sobj + sobj); // 10

    return 0;
};
```
It is syntactic sugar for `SomeObj sobj(5);`

<a id="deferred-object-cleanup-with-defer"></a>
## Deferred object cleanup with `defer`:
Deferred statements execute in LIFO order.  
Deferred calls execute after post-contract code, immediately before the function returns.
```
#import "standard.fx";

using standard::io::console;

object SomeOBJ
{
    int val;
    def __init(int x) -> this
    {
        this.val = x;
        return this;
    };

    def __exit() -> void { print("Cleaning up!"); };

    def __expr() -> int { return this.val; };
};

def main() -> int
{
    SomeOBJ sobj = 5;
    defer sobj.__exit();

    print(sobj);
    // deferred statements injected here
    return 0;
};
```

### You can also defer in blocks:
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    println("Hello!");
    defer
    {
        println("Test1!");
        println("Test2!");
    };
    return 0;
};
```
Result:
```
Hello!
Test2!
Test1!
```

---

<a id="traits"></a>
## Traits
Traits are contracts imposed on objects dictating they __must__ implement the defined prototypes.
```
trait Drawable
{
    def draw() -> void;
};


// Implementation
Drawable object myObj
{
    // ... required methods ...

    def draw() -> void
    {
        // Implementation code, if the block is empty the compiler throws an error.
        return void;
    };

    // ... other methods ...
};
```

---


<a id="publicprivate-with-objectsstructs"></a>
## **Public/Private with Objects/Structs**  
Struct public and private works by only allowing access to private sections by the parent object/struct that "owns" the struct.  
The struct is still data where public members are visible anywhere, but its private members are only visible/modifiable by the object immediately containing it.

```
struct myStruct
{
    int x, y;
};

object Obj2
{
    private
    {
        myStruct objStru;
    };

    // ... required methods ...

    def get_y() -> int
    {
        return this.myStruct.y;             // Safe - Access is in the same scope (immediate `this` Obj2, not `super` Obj1)
    };
};

object Obj1
{

    Obj2 myObject;

    // ... required methods ...

    def foo() -> int
    {
        return this.myObject.myStruct.y;    // ERROR - Need to use a getter of Obj2
    };
};
```

---

<a id="istrings-and-fstrings"></a>
## **i-Strings and f-Strings**

The syntax in Flux would be: `i"{}{}{}":{x;y;z;};` for an i-string, and `f"{var1}{var2}\0";` for an f-string.

The brackets are replaced with the results of the statements in order respective to the statements' position in the statement array in i-strings.  
**i-string Example**

```
#import "standard.fx"; // imports types.fx

using standard::io::console;

def bar() -> noopstr { return "World"; };    // We get the non-OOP string type from the types library

def main() -> int
{
    println(i"Hello {} {}" : {bar() + "!"; "test";});

    x = i"Bar {}":{bar()};     // "Bar World!"

    noopstr a = "Hello", b = "World!",
            c = f"{a} {b}";    / "Hello World!"

    println(c);

    return 0;
};
```

This allows you to write clean interpolated strings without strange formatting.  
**f-string Example**
```
#import "standard.fx";

using standard::io::console,
      standard::strings;

def main() -> int
{
    string h = "Hello";
    string w = "World!";
    print(f"{h} {w}");
    return 0;
};
```
`Result: Hello World!`

---

<a id="pointers"></a>
## **Pointers**

```
string a = "Test\0";
string* pa = @a;
*pa += "ing!\0";
print(a);
// Result: "Testing!"


// Pointers to variables:
int idata = 0;
int* p_idata = @idata;

*p_idata += 3;
print(idata);  // 3

// Function pointer declarations
def{}* p_add(int,int)->int = @add;
def{}* p_sub(int,int)->int = @sub;

// Must dereference to call
print(p_add(0,3)); // 3
print(p_sub(5,2)); // 3

// Pointers to objects, structs, arrays:
object    myObj {};                 // Definition
object* p_myObj = @myObj;           // Pointer

struct    myStruct {};              // Definition
struct* p_myStruct = @myStruct;     // Pointer

int*[] pi_array = @i_array;         // Array of pointer

const int*  px; // Pointer to const value

const* int* px; // Constant pointer to int pointer
```

---

<a id="you-can-also-use-inline-assembly-directly"></a>
## You can also use in-line assembly directly:
Assembly in Flux is done AT&T style.  
The constraints follow the block in the pattern `outputs : inputs : clobbers`
Here's an example:
```
def _exchange64(i64* ptr, i64 value, i64* out) -> void
{
    #ifdef __ARCH_X86_64__
    volatile asm
    {
        movq $0, %rsi
        movq $2, %rdi
        movq $1, %rax
        xchgq %rax, (%rsi)
        movq %rax, (%rdi)
    } : : "r"(ptr), "r"(value), "r"(out) : "rax", "rsi", "rdi", "memory";
    #endif;
    #ifdef __ARCH_ARM64__
    volatile asm
    {
    .retry_xchg64:
        ldaxr x0, [$0]
        stlxr w3, x1, [$0]
        cbnz  w3, .retry_xchg64
        str   x0, [$2]
    } : : "r"(ptr), "r"(value), "r"(out) : "x0", "w3", "memory";
    #endif;
};
```
Here, the clobber list is `"r"(ptr), "r"(value), "r"(out) : "x0", "w3", "memory";`  
Using `volatile` tags the assembly block for the compiler, saying do not touch this for any reason.

---

<a id="logic-with-ifelifelse"></a>
## **Logic with if/elif/else**
```
if (condition1)
{
    doThis();
}
elif (condition2)      // You can also use `else if`
{
    doThat();
}
else if (condition 3)  // Equivalent to `elif`
{
    doAnythingElse();
}
else
{
    doThings();
};
```

You can also do `if` expressions:
```
int x = 0;
int y = x if (x > 5) else noinit;
```
Alternatively, you can use a ternary `?:`
`int y = x ?  (x > 5) :   noinit;`

You can also use `if` expressions in the following manner:
```
#import "standard.fx";

using standard::io::console;

def foo() -> int
{
    return 10;
};

def main() -> int
{
    int* px @= 5;

    print(foo()) if (px);

    return 0;
};
```
You may also use groups of statements in a block before an if:
```
#import "standard.fx";

using standard::io::console;

def foo() -> int
{
    print("Hello");
};
def bar() -> void
{
    print(" World!");
};

def main() -> int
{
    {
        foo(); bar();
    } if (true);

    return 0;
};
```

Ternary logic:
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int x = 0;
    int y = 5;

    int z = x < y ? y : 0;

    if (z is 5)
    {
        print("Success!\0");
    };
    return 0;
};
```

Ternary assignment:
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int x = 10,
        y;

    x ?= 50;
    y ?= x;

    if (x == y) { print("Success!\n\0"); };

    return 0;
};
```

Null coalesce operator:
```
#import "standard.fx";

def main() -> int
{
    int x = 0;
    int y = 5;

    int z = y ?? 0;

    if (z is 5)
    {
        print("Success!\0");
    };
    return 0;
};
```

---

<a id="the-data-keyword"></a>
## **The `data` keyword**

Data is a variable bit width, primitive binary data-type creation keyword.  
Anything can cast to it, and it can cast to any primitive like char, int, float.  
It is intended to allow Flux programmers to build any basic integer type to fit their needs.  
Data types use big-endian byte order by default. Manipulate bits as needed.  
Bit-width bust always be specified.

Syntax for declaring a datatype:

```
(const) (signed | unsigned) data {bit-width:alignment} (as) your_new_type

//    Example of a non-OOP string:

      unsigned data {8}[] as noopstr;    // Unsigned byte array, default alignment
```

This allows the creation of primitive, non-OOP types that can construct other types.  
`data` creates user-defined types.

For example, you can just keep type-punning:
`unsigned data{16} as dbyte;`  
`dbyte as xbyte;`  
`xbyte as ybyte;`  
You can pun and declare a variable as well:  
`ybyte as zbyte zbx = 0xFF;`

Data decays to an integer type under the hood. All data is binary, and is therefore an integer.

**Minimal specification**
`unsigned data{8} as byte;            // 8-bit`

**Full specification**
`data{width : alignment : endianness}`

**Example**
`unsigned data{16::0} as custom_le;   // 16-bit, 16-bit aligned, little endian`

---

<a id="mixing-signedunsigned-in-expressions"></a>
### Mixing Signed/Unsigned in Expressions
```
signed data{32} as i32;
unsigned data{32} as u32;

i32 a = -10;
u32 b = 20;

// Mixed arithmetic (result type determined by widest type)
i32 result1 = a + (i32)b;    // -10 + 20 = 10 (signed)
u32 result2 = (u32)a + b;    // 4294967286 + 20 (unsigned, wraps)

// Comparison with mixed signs
if (a < (i32)b)  // true: -10 < 20
{
    print("Signed comparison\0");
};

if ((u32)a < b)  // false: 4294967286 > 20
{
    print("Unsigned comparison\0");
};
```

---

<a id="endianness-handling"></a>
## **Endianness Handling**
```
data{16::0} as le16;  // Little-endian 16-bit
data{16}    as be16;  // Big-endian default 16-bit

def swap_endian_16(be value) -> data{16}
{
    data{16::0} v2 = value; // Explicit byte swap on assignment
    return v2;
};

// Network byte order (big-endian) to host (little-endian)
def network_to_host(be16 net_value) -> le16
{
    le16 x = net_value;     // Explicit byte swap on assignment
    return x;
};

// Reading from network buffer
data{8::0}[4] buf = [0x12, 0x34, 0x56, 0x78];
be16[2] net = buf; // autopack and convert endianness
```

1. Single-endian arithmetic model - All math is performed in one endianness (big).
2. Swapping on assignment means the compiler doesn't need to track mixed-endian states through complex expressions.

---

<a id="casting"></a>
## **Casting**

Casting in Flux is C-like

```
float x = 3.14;                  // 01000000010010001111010111000010b   binary representation of 3.14
i32 y = (i32)x;                  // 01000000010010001111010111000010b   but now treated as an integer  1078523330 == 0x4048F5C2
```
There are only two types. Integers, and floating point decimals. `float` and `double` are floating point types. All other types are integer types.

Casting anything to `void` is the functional equivalent of freeing the memory occupied by that thing.  
This is dangerous on purpose, it is equivalent to free(ptr) in C. This syntax is considered explicit in Flux once you understand the convention.  
It calls `ffree()` under the hood, which uses the standard heap allocator. You should not `void` cast free anything unless it was allocated with `fmalloc()`

**Void casting in relation to the stack and heap**
```
def example() -> void {
    int stackVar = 42; // Stack allocated

    (void)stackVar;    // What happens here?
}
```

In this case, `stackVar` is zeroed out and the reference invalidated.

---

<a id="stringification-with"></a>
## Stringification with `$`:
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int Hello = 5;

    println($Hello);
    return 0;
};
```
Result:
`Hello`

<a id="codification"></a>
## Codification:
Codification is the inverse of stringification, using the codify operator `~$`
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    byte* test = "int x = 5;";

    ~$test;

    println(x);
    
    return 0;
};
```
Result: `5`

---

<a id="direct-type-conversion"></a>
## Direct type conversion:
You can do function-like conversion only with built-in types like `int`, `long`, `double`, `bool`, etc.
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    double d = 3.1415925658;

    int i = int(d);

    print(i);

    return 0;
};
```
Result:
`3`

---

<a id="the-typeof-sizeof-alignof-and-endianof-builtins"></a>
## **The `typeof`, `sizeof`, `alignof`, and `endianof` built-ins**
```
data{8:8:0}* as lestr;
signed data{13:16} as strange;

sizeof(lestr);    // 8
alignof(lestr);   // 8
typeof(lestr);    // unsigned data{8:8}*
endianof(lestr);  // 1

sizeof(strange);   // 13
alignof(strange);  // 16
typeof(strange);   // signed data{13:16}
endianof(strange); // 1
```

---

<a id="void-as-a-literal"></a>
## **`void` as a literal**
```
if (x == void) {...code...};    // If it's nothing, do something
void x;
if (x == !void) {...code...};   // If it's not nothing, do something
```
In literal context, `void` is `0`. `false` is also `0`, which means `void == false;`. Therefore, anything can be `void`-checked. 

---

<a id="arrays"></a>
## **Arrays**

Array declarations have the syntax `type[n] var`. Never `type var[n]`.

A single dimension array: `int[] x = [1,2,3,4,5];`
A two dimensional array: `int[][] y = [[1,2,3,4],[5,6,7,8]];`
A three dimensional array:
```
int[][][] z = [
                [
                  [ 1,  2,  3], [ 4,  5,  6], [ 7,  8,  9]
                ],
                [
                  [10, 11, 12], [13, 14, 15], [16, 17, 18]
                ],
                [
                  [19, 20, 21], [22, 23, 24], [25, 26, 27]
                ]
              ];
```

**Static array comprehension**
```
// Python-style comprehension
int[10] squares = [x ^ 2 for (int x in 1..10)];

// With condition
int[20] evens = [x for (int x in 1..20) if (x % 2 == 0)];

// With type conversion
float[sizeof(int_array)] floats = [(float)x for (int x in int_array)];

// C++-style comprehension
int[10] squares = [x ^ 2 for (int x = 1; x <= 10; x++)];

// With condition
int[20] events = [x for (int x= 1; x <= 20; x++) if (x % 2 == 0)];
```

**Static array comprehension using a dynamic type**
```
#import "standard.fx";

using standard::collections; // For the dynamic array 'Array'

Array[] myArr = [x.name for (Array x in oldArr) if (x.name.len() > 5)];
```

---

<a id="loops"></a>
## **Loops**

Flux supports 2 styles of for loops:
```
for (x in y)                     // Array iteration
{
    // ... code ...
};

for (int c = 0; c < 10; c++)     // init ; cond ; expr
{
    // ... code ...
};
```

A `for`-ever loop:
`for (;;) {};`

A `do` loop:
```
do
{
    // some code;
};
```

You can also do comprehension on `while` conditions:
```
do
{
    y[i--] = void;     // Nulled out of array
}
while (x in y & i > 0);

while (condition)
{
    // ... code ...
};
```

An infinite `while` loop:
```
while (true)
{
    // ...
};
// or
while (1)
{
    // ...
};
```

---

<a id="singleinitialized-variables-with-singinit"></a>
## **Single-initialized variables with `singinit`**
```
#import "standard.fx";

using standard::io::console;

def foo() -> void
{
    singinit int x;
    x += 1;
    print(x); print();
};

def call(int y) -> void
{
    if (y == 0) { return; };
    foo();
    call(--y);
};

def main() -> int
{
    call(10);
    return 0;
};
```

---

<a id="recursion"></a>
## Recursion:
```
def rsub(int x, int y) -> int
{
    switch (x == 0 | y == 0)
    {
    };

    rsub(--x,--y);
};
```

---

<a id="strict-recursion-with"></a>
## Strict Recursion with `<~`:
Functions that have the recurse return operator will always return to themselves. Their stack frame never grows because they become tail calls, and get optimized as such.
```
#import "standard.fx";

using standard::io::console;

noopstr m1 = "[recurse \0",
        m2 = "]\0";

def recurse1(int x) <~ int
{
    singinit int y;
    print(m1); print(y); println(m2);
    return ++y;
};


def recurse2() <~ void
{
    singinit int z;
    print(m1); print(++z); println(m2);
};


def main() -> int
{
    recurse2(); // Step into tail function
    return 0;
};
```

<a id="escaping-strict-recursion-with-escape"></a>
## **Escaping strict recursion with `escape`**
`escape` can only be used inside a strictly-recursive function defined with a recurse arrow `<~`. Example:
```
def recurse2() <~ void
{
    if (!entered_flag) {entered_flag = true;};
    singinit int z;
    print(m1); print(++z); println(m2);
    if (z >= 10) { escape main(); }; // or any other function
};
```

---

<a id="error-handling-with-trythrowcatch"></a>
## **Error handling with `try`/`throw`/`catch`**
```
unsigned data{8}[] as string;  // Basic string implementation with no functionality (non-OOP string)

object ERR
{
    string e;

    def __init(string e) -> this
    {
        this.e = e;
        return this;
    };

    def __expr() -> string
    {
        return this.e;
    };
};

def myErr(int e) -> void
{
    switch (e)
    {
        case (0)
        {
            ERR myErrObj("Custom error from object myE\0");
            throw(myErrObj);
        }
        default
        {
            throw("Default error from function myErr()\0");
        };                                                  // Semicolons only follow the default case.
    };
};

def thisFails() -> bool
{
    return true;
};

def main() -> int
{
    string error = "\0";
    try
    {
        try
        {
            if(thisFails())
            {
                myErr(0);
            };
        }
        catch (ERR e)                                     // Specifically catch our ERR object
        {
            string err = e.e;
        }                                                 // No semicolon here because this is not the last catch in the try statement
        catch (string x)                                  // Only catch a primitive string (unsigned data{8}[]) thrown
        {
        }                                                 // No semicolon here because this is not the last catch in the try statement
        catch (auto x)
        {
        };                                                // Semicolon follows because it's the last catch in the try/catch sequence.
    }
    catch (string x)
    {
        error = x;  // "Thrown from nested try-catch block."
    };

    return 0;
};
```

---

<a id="enumerated-lists"></a>
## **Enumerated Lists**

Definition: `enum myEnum {val1, val2, val3, val4, ...};`  
Instance: `myEnum newEnum;`
Member access: `newEnum.val1;`

Enumerated lists are type `int`, this will be updated to support `type enum Ident {};` syntax.

---

<a id="unions"></a>
## **Unions**

Prototype: `union myUnion;`  
Definition: `union myUnion {int iVal; float fVal;};`  
Insance: `myUnion newUnion;`  
Instance with assignment: `myUnion newUnion {iVal = 10};`  
Member access: `newUnion.iVal;`

Unions are similar to structs, the difference is only one of its members can be initialized at any time.  
Initializing another member changes the actively initialized member.  
Attempting to access an uninitialized member results in garbage data for that member.

Example:

```
union myUnion
{
    int iVal;
    float fVal;
};

myUnion u {iVal = 10};

def main() -> int
{
    u.iVal = 10;   // iVal is the active member
    u.fVal = 3.14; // iVal overwritten by fVal in memory
};
```

---

<a id="tagged-unions"></a>
## **Tagged unions**
```
#import "standard.fx";

using standard::io::console;

enum ErrorUnionEnum
{
    INACTIVE,
    INT_ACTIVE,
    LONG_ACTIVE,
    BOOL_ACTIVE,
    CHAR_ACTIVE,
    FLOAT_ACTIVE,
    DOUBLE_ACTIVE   
};

union ErrorUnion
{
    int  iRval;
    long lRval;
    bool bRval;
    char cRval;
    float fRval;
    double dRval;
} ErrorUnionEnum;


def foo() -> ErrorUnion
{
    ErrorUnion err;

    err.bRval = false; // Set bool to active element
    err._ = ErrorUnionEnum.BOOL_ACTIVE;

    return err;
};


def main() -> int
{
    ErrorUnion e = foo();

    switch (e._)
    {
        case (ErrorUnionEnum.INT_ACTIVE)
        {
            print("Integer active in error union!\n\0");
        }
        case (ErrorUnionEnum.LONG_ACTIVE)
        {
            print("Long active in error union!\n\0");
        }
        case (ErrorUnionEnum.BOOL_ACTIVE)
        {
            print("Bool active in error union!\n\0");
        }
        case (ErrorUnionEnum.CHAR_ACTIVE)
        {
            print("Char active in error union!\n\0");
        }
        case (ErrorUnionEnum.FLOAT_ACTIVE)
        {
            print("Float active in error union!\n\0");
        }
        case (ErrorUnionEnum.DOUBLE_ACTIVE)
        {
            print("Double active in error union!\n\0");
        }

        default { print("No active tag set!\n\0"); };
    };

    return 0;
};
```

---

<a id="switching"></a>
## **Switching**
`switch` is static, value-based, and non-flexible. Switch statements are for speed.
```
switch (e)
{
    case (0)
    {
        // Do something
    }
    case (1)
    {
        // Another thing
    }
    default
    {
        // Something else
    };
};
```

---

<a id="namespace-elimination-with-using-or-not-using"></a>
## **Namespace elimination with `!using` or `not using`**
```
!using standard::io::file;
not using some::specific::namespace;
```

---

<a id="deprecation-with-deprecate"></a>
## **Deprecation with `deprecate`**
```
#import "standard.fx";

namespace test1
{
    namespace test2
    {
        def foo() -> void {};
    };
};

deprecate test1::test2;

def main() -> int
{
    test1::test2::foo();

    return 0;
};
```
Compiling gives this output:
```
✗ Compilation failed: Deprecated namespace 'test1::test2' is still referenced:
Function call test1__test2__foo()
```

---

<a id="assertion-with-assert"></a>
## **Assertion with `assert()`**
`assert` automatically performs `throw` if the condition is false if it's inside a try/catch block,
otherwise it automatically writes to standard error output.
```
def main() -> int
{
    int x;
    try
    {
        assert(x == 0, "Something is fatally wrong with your computer.");
    }
    catch (string e)
    {
        print(e);
        return -1;
    };
    return x;
};
```

---

<a id="heap-allocation"></a>
## **Heap allocation**
```
heap int x = 5;      // Allocate
(void)x;             // Deallocate
```

`(void)` casting works on both stack and heap allocated items.  
If you do this to a stack element, it is nulled, and all references invalidated. You will need to redeclare `x`.
Doing this to a heap element will call `ffree()` under the hood.

Allocating with `heap` calls `fmalloc(sizeof(T))` under the hood. `x` is a pointer.

<a id="freeing-from-the-heap"></a>
## **Freeing from the heap**
Flux's standard heap allocator is **incompatible** with C's `malloc` and `free`.

You **must** use `ffree` for anything allocated with `fmalloc`, including `heap` allocations.  
Alternatively you may void cast.

---

<a id="custom-infix-operators-and-overloading"></a>
## **Custom infix operators and overloading**
- Custom:
```
operator (int L, int R) [+++] -> int
{
    return ++L + ++R;
};
```
Usage: `a +++ b`

- Identifier-based:
```
operator (int L, int R) [NOPOR] -> bool
{
    return !L | !R;
};
```
Usage: `a NOPOR b`

- Overloading:
Overloading built-in operators is allowed, with rules.
1. One parameter must not be a built-in type.  
2. The precedence and associativity cannot be changed.
```
operator (int L, BigInt R) [+] -> bool
{
    // Implementation for adding an int and a BigInt
};
```

---

<a id="functions-and-contract"></a>
## **Functions and `contract`**
Contracts are compile time function modification.  
They prepend or append the code contained to a function's body.

Pre-contract form puts the contract's statements before the function's code.  
Post-contract form puts the contract's statements before the function's return.

Contracts are not specifically `assert`-only, they can contain any statement.
They are similar to macros and expand before type checking and semantic analysis.
```
#import "standard.fx";

using standard::io::console;

contract NonZero
{
    assert(x > 0, "x must be positive");
};

contract rValGT10
{
    assert(x > 10, "r must be greater than 10");
};

def foo(int x) -> int : NonZero
{
    x = x / 2;
    return x;
} : rValGT5;

def main() -> int
{
    int y = foo(18);

    return 0;
};
```
Turns into:
```
def foo(int x) -> int : NonZero
{
    assert(x > 0, "x must be positive");
    x = x / 2;
    assert(x > 10, "x must be greater than 10");
    return x;
};
```
The contracts disappear from the compilation unit after transformation.

---

<a id="contracts-on-operators"></a>
## Contracts on operators:
```
#import "standard.fx";

using standard::io::console;

contract NonZero(a,b)
{
    assert(a != 0, "a must be nonzero");
    assert(b != 0, "b must be nonzero");
};

operator(int x, i32 y)[+] -> int : NonZero(a,b)
{
    return x+y;
};


def main() -> int
{
    0 + 4;

    return 0;
};
```
Result at runtime:
`a must be nonzero`

---

<a id="expressionbased-macros-with-macro"></a>
## **Expression-based macros with `macro`**
```
#import "standard.fx";

using standard::io::console;

macro xyz(a,b,c)
{
    (a + b) ^ c
};

def main() -> int
{
    int x, y, z = 1, 2, 3;

    println(f"xyz(abc) = {xyz(x,y,z)}");

    return 0;
};
```
- The `println` string turns into:
```
println(f"xyz(abc) = {(1 + 2) ^ 3}");
```
Result:
`xyz(abc) = 27`

---

<a id="templates"></a>
## **Templates**

```
#import "standard.fx";


def foo<T>(T x) -> T
{
    return x;
};


def main() -> int
{
    float y = foo<float>(5.5f);
    int z = foo<int>(3);

    print(y); print();
    print(z); print();

    system("pause\0");
    return 0;
};
```

The compiler can also infer templates at call sites, so you don't end up with a mess of angle brackets:
```
#import "standard.fx";

using standard::io::console;

struct myStru<T>
{
    T a, b;
};

def foo<T, U>(T a, U b) -> U
{
    return a.a * b;
};

def bar(myStru<int> a, int b) -> int
{
    return foo(a, 3); // inferred from signature via 'a'
};

def main() -> int
{
    myStru<int> ms = {10,20};

    //int w = foo<myStru<int>, int>(ms, 3); // <brackets> at call site

    int x = foo(ms, 3); // inferred locally

    int y = bar(ms, 3);

    println(x == y);
    return 0;
};
```

<a id="templating-operators"></a>
## Templating operators:
```
operator<T, K>(T t, K k)[+] -> int
{
    return t + k;
};
```

<a id="combining-templates-contracts-and-operators"></a>
## Combining templates, contracts, and operators:
```
#import "standard.fx";

using standard::io::console;

struct myStru<T>
{
    T a, b;
};

def foo<T, U>(T a, U b) -> U
{
    return a.a * b;
};

def bar(myStru<int> a, int b) -> int
{
    return foo(a, 3); // Template inferred from parameter
};

macro macNZ(x)
{
    x != 0
};

contract ctNonZero(a,b)
{
    assert(macNZ(a), "a must be nonzero");
    assert(macNZ(b), "b must be nonzero");
};

contract ctGreaterThanZero
{
    assert(x > 0, "a must be greater than zero");
    assert(y > 0, "b must be greater than zero");
};

operator<T, K>(T t, K k)[+] -> int : ctNonZero(a,b)
{
    return t + k;
} : ctGreaterThanZero;

def main() -> int
{
    myStru<int> ms = {10,20};

    int x = foo(ms, 3); // Template inferred from myStru<int> above

    i32 y = bar(ms, 3);

    println(x + y);

    return 0;
};
```
Result: `60`

---

<a id="variadic-functions"></a>
## **Variadic functions**
Variadics in Flux are very straightforward, and use the `...` elipse operator.  
You can index the elipse operator to yield the arguments passed, example:
```
#import "standard.fx";

using standard::io::console;

def variadic(...) -> void
{
    print(...[0]); print();
    print(...[1]); print();
    print(...[2]); print();
    print(...[3]); print();
};



def main() -> int
{
    variadic(1,2,3,4);

    return 0;
};
```
Result:
```
1
2
3
4
```

---

<a id="chaining-functions"></a>
## **Chaining functions**
```
def foo(int x) -> int
{
    return x / 2;
};

def bar () -> int
{
    return 0xFF;
};

int z = foo() <- bar(); // == // int z = foo(bar());
```

---

<a id="external-functions-ffi"></a>
## **External Functions (FFI)**
Single-line:
```
extern def foo() -> void;
extern def !!foo() -> void;  // !! tells the compiler do not mangle this function name
```
Block-based:
```
extern
{
    def foo() -> void;
    def bar() -> void;
    def !!zed() -> void;
};
```
Or multiple prototypes at once:
```
extern
{
    // Memory allocation
    def !!
        malloc(size_t) -> void*,
        memcpy(void*, void*, size_t) -> void*,
        free(void*) -> void,
        calloc(size_t, size_t) -> void*,
        realloc(void*, size_t) -> void*,
        memcpy(void*, void*, size_t) -> void*,
        memmove(void*, void*, size_t) -> void*,
        memset(void*, int, size_t) -> void*,
        memcmp(void*, void*, size_t) -> int,
        abort() -> void,
        exit(int) -> void,
        atexit(void*) -> int;
};
```
String-literal based function name support to target any compiled library function:
```
def "??foo@"()->void;
```

<a id="exporting-functions-with-export"></a>
## **Exporting Functions with `export`**
Using `export` will cause a function to be marked as external for linkage.  
Use this when writing libraries, or to allow a function to be "seen".
```
#import "types.fx";

export
{
    def !!stub() -> void {};
};
```
This is a valid library and will compile if you do:
`python fxc.py tests\testlib.fx --library -o mylib.dll` on Windows,
and
`python3 fxc.py tests/testlib.fx --library -o testlib.so` on Linux.

---

<a id="advanced-pointer-manipulation"></a>
## **Advanced pointer manipulation**

<a id="taking-address-of-literals"></a>
### Taking address of literals
```
// You can take the address of a literal value
int* p = @42;
print(*p);  // 42

// The address can be manipulated as an integer
unsigned data{64}* as u64ptr;
u64ptr addr = (u64ptr)p;
addr += 8;  // Move 8 bytes forward in memory
int* p2 = (int*)addr;

// Pointer arithmetic on literal addresses
int* base = @100;
int* offset = base + 5;
*offset = 200;  // Writing to calculated memory location
```

<a id="pointer-to-integer-conversions"></a>
### Pointer to integer conversions
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    uint x, y = 10, 0;

    uint* px, py = @x, @y;

    // A pointer is simply a variable and its value is an address
    // An address is a number.
    // Therefore, we can store that address
    //
    u64 kx = px;

    // (@) is address-cast. It reinterprets the number as an address
    // When we treat a number as an address, we call that a pointer.
    // Therefore, we can assign this to another pointer.
    //
    py = (@)kx;

    // py now points to x

    // Dereference py to get the value at the address
    // Cast to make sure it's the proper type to print

    if (x == 10 & y == 0 & *py == x & px == py & px == (@)kx)
    {
        print("Success, y unchanged, py points to x.\n\0");
        print((uint)*py);
        return 0;
    };

        return 0;
};
```

---

<a id="memory-layout-and-alignment-tricks"></a>
## **Memory Layout and Alignment Tricks**

<a id="bitfield-manipulation"></a>
### Bit-Field Manipulation
```
// 13-bit signed value, 16-bit aligned
signed data{13:16} as strange13;

strange13 value = 0x1FFF;  // Max positive value for 13 bits
print(value);              // 8191

value = 0x1000;            // Sign bit set (bit 12)
print(value);              // -4096 (two's complement)

// Extract specific bit ranges
u32 packed = 0x12345678;

def extract_bits(uint32 value, int start, int length) -> uint32
{
    uint32 mask = ((1 << length) - 1) << start;
    return (value & mask) >> start;
};

uint32 nibble0 = extract_bits(packed, 0, 4);   // 0x80
uint32 nibble3 = extract_bits(packed, 12, 4);  // 0x50
uint32 byte1 = extract_bits(packed, 8, 8);     // 0x56
```

---

<a id="advanced-data-manipulation-techniques"></a>
### ***Advanced data manipulation techniques***
***C***:
```
len_block[0]  = (byte)((aad_bits    >> 56) & 0xFF);
len_block[1]  = (byte)((aad_bits    >> 48) & 0xFF);
len_block[2]  = (byte)((aad_bits    >> 40) & 0xFF);
len_block[3]  = (byte)((aad_bits    >> 32) & 0xFF);
len_block[4]  = (byte)((aad_bits    >> 24) & 0xFF);
len_block[5]  = (byte)((aad_bits    >> 16) & 0xFF);
len_block[6]  = (byte)((aad_bits    >>  8) & 0xFF);
len_block[7]  = (byte)( aad_bits           & 0xFF);
len_block[8]  = (byte)((cipher_bits >> 56) & 0xFF);
len_block[9]  = (byte)((cipher_bits >> 48) & 0xFF);
len_block[10] = (byte)((cipher_bits >> 40) & 0xFF);
len_block[11] = (byte)((cipher_bits >> 32) & 0xFF);
len_block[12] = (byte)((cipher_bits >> 24) & 0xFF);
len_block[13] = (byte)((cipher_bits >> 16) & 0xFF);
len_block[14] = (byte)((cipher_bits >>  8) & 0xFF);
len_block[15] = (byte)( cipher_bits        & 0xFF);
```

***Flux equivalent***
```
len_block[0..7]  = (byte[8])(u64)aad_bits;
len_block[8..15] = (byte[8])(u64)cipher_bits;
```

```
uint* pd = @p.digits[0];

// Proper Flux
pd = [0xFFFFFFEDu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu,
      0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu];

/// C-like
pd[0] = 0xFFFFFFED;
pd[1] = 0xFFFFFFFF;
pd[2] = 0xFFFFFFFF;
pd[3] = 0xFFFFFFFF;
pd[4] = 0xFFFFFFFF;
pd[5] = 0xFFFFFFFF;
pd[6] = 0xFFFFFFFF;
pd[7] = 0x7FFFFFFF;
///
```

<a id="reworking-a-loop"></a>
### **Reworking a loop**
```
for (i = 0; i < 4; i++)
{
    hash[i] = (byte)((ctx.state[0] >> (24 - i * 8)) & 0xFF);
    hash[i + 4] = (byte)((ctx.state[1] >> (24 - i * 8)) & 0xFF);
    hash[i + 8] = (byte)((ctx.state[2] >> (24 - i * 8)) & 0xFF);
    hash[i + 12] = (byte)((ctx.state[3] >> (24 - i * 8)) & 0xFF);
    hash[i + 16] = (byte)((ctx.state[4] >> (24 - i * 8)) & 0xFF);
    hash[i + 20] = (byte)((ctx.state[5] >> (24 - i * 8)) & 0xFF);
    hash[i + 24] = (byte)((ctx.state[6] >> (24 - i * 8)) & 0xFF);
    hash[i + 28] = (byte)((ctx.state[7] >> (24 - i * 8)) & 0xFF);
};
```
Turns into:
```
hash[0..3]   = (byte[4])(be32)ctx.state[0];
hash[4..7]   = (byte[4])(be32)ctx.state[1];
hash[8..11]  = (byte[4])(be32)ctx.state[2];
hash[12..15] = (byte[4])(be32)ctx.state[3];
hash[16..19] = (byte[4])(be32)ctx.state[4];
hash[20..23] = (byte[4])(be32)ctx.state[5];
hash[24..27] = (byte[4])(be32)ctx.state[6];
hash[28..31] = (byte[4])(be32)ctx.state[7];
```

<a id="bit-slices"></a>
### ***Bit slices***
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    byte x = 55;

    x[0``7] = x[7``0]; // Reverse the bits

    println(int(x)); // 236

    return 0;
};
```

<a id="taking-bit-slices-from-structs"></a>
### ***Taking bit slices from structs***
Bit slicing structs can cross member boundaries, because structs members are packed tightly in memory.
```
#import "standard.fx";

using standard::io::console;

struct xx { int a, b; };

def main() -> int
{
    data{4} as u4;
    xx yy = {5,10};
    u4 a = yy[60``63]; // 10 because 0b1010

    print((int)a);

    return 0;
};
```

<a id="bit-slices-of-bit-slices"></a>
### ***Bit slices of bit slices***
```
#import "standard.fx";

using standard::io::console;

struct xx { int a, b; };

def main() -> int
{
    data{4} as u4;
    data{2} as u2;
    xx yy = {5,10};
    u4 a = yy[60``63]; // 10 because 0b1010
    u2 b = a[0``1];

    print(int(b)); // 2, because 0b10

    return 0;
};
```

---

<a id="advanced-data-type-features"></a>
## **Advanced Data Type Features**

<a id="unusual-bit-widths"></a>
### Unusual Bit Widths
```
// 3-bit unsigned value (0-7)
unsigned data{3} as tiny = 5;

// 17-bit signed value
signed data{17} as weird17 = -1000;

// 7-bit with 8-bit alignment (1 bit padding)
unsigned data{7:8} as aligned7 = 127;

// Array of 5-bit values
unsigned data{5}[10] as nibble_array arr;
arr[0] = 0x1F;  // Max value for 5 bits

// Casting between weird widths
unsigned data{13} as u13 a = 8191;
unsigned data{17} as u17 b = (u17)a;  // Zero-extend
signed data{13} as s13 c = (s13)a;    // Truncate LTR, losing most significant bits
```

You may take arbitrary width slices as well, stored in your arbitrarily sized types.

---

<a id="function-pointers"></a>
## **Function Pointers**
```
#import "standard.fx";

using standard::io::console;

def foo(int x) -> int
{
    print("Inside foo!\n\0");
    return 0;   
};


def main() -> int
{
    def{}* pfoo(int)->int = @foo;
    print("Function pointer created.\n\0");
    print();

    pfoo(0); // Compiler auto dereferences

    return 0;
};
```


<a id="callbacks"></a>
## **Callbacks**
One of a few ways you can set up callbacks:
```
#import "standard.fx";

using standard::io::console;

def foo() -> void
{
    println("In foo()!");
};

def callback(long x) -> int
{
    def{}* cb()->void = x;
    cb();
    return 0;
};

def main() -> int
{
    callback(long(@foo));
    return 0;
};
```

<a id="raw-bytecode-functions"></a>
## **Raw bytecode functions**
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    byte[] some_bytecode = [0x48, 0x31, 0xC0, 0xC3];  // xor rax,rax ; ret
    def{}* fp()->void = @some_bytecode;
    fp();
    
    return 0;
};
```

---

<a id="ownership-with-the-tie-operator"></a>
## **Ownership with the tie operator `~`**

Ownership only occurs if you use `~` to tell the compiler to perform a very simple set of rules:
- A tied value requires it to be untied on-use
- A tied value can only move to a tied type
- One-time use, old reference invalidated on use

A function returning a tied type cannot return to a variable of non-tied type.  
Similarly, you cannot pass a non-tied variable to a tied parameter.

```
#import "standard.fx";

def foo(~int z) -> void  // accepts a tied parameter
{
    return;
};

def main() -> int
{
    ~int x;
    int  y;  // Non-tied var

    foo(~x); // Untie from main, tie to foo()

    foo(~x); // Compile error, use after untie

    foo(y);  // Compile error, foo expects tied param

    return 0;
};
```

---

<a id="control-flow-edge-cases"></a>
## **Control Flow Edge Cases**

<a id="nested-switches-with-fallthrough"></a>
### Nested Switches with Fallthrough
```
def classify_value(int x, int y) -> void
{
    switch (x)
    {
        case (0)
        {
            switch (y)
            {
                case (0)
                {
                    print("Both zero\0");
                }
                case (1)
                {
                    print("X zero, Y one\0");
                }
                default
                {
                    print("X zero, Y other\0");
                };
            };
        }
        case (1)
        {
            print("X is one\0");
        }
        default
        {
            print("X is other\0");
        };
    };
};
```

<a id="complex-trycatch-with-multiple-types"></a>
### Complex Try/Catch with Multiple Types
```
object ErrorA
{
    int code;
    def __init(int c) -> this { this.code = c; return this; };
    def __exit() -> void {return;};
};

object ErrorB
{
    string message;
    def __init(string m) -> this { this.message = m; return this; };
    def __exit() -> void {return;};
};

def risky_operation(int mode) -> void
{
    if (mode == 1)
    {
        throw(ErrorA(100));
    }
    elif (mode == 2)
    {
        throw(ErrorB("Something failed\0"));
    }
    else
    {
        throw("Generic error\0");
    };
};

def main() -> int
{
    try
    {
        risky_operation(1);
    }
    catch (ErrorA e)
    {
        print(f"ErrorA caught: code {e.code}\0");
    }
    catch (ErrorB e)
    {
        print(f"ErrorB caught: {e.message}\0");
    }
    catch (string s)
    {
        print(f"String error: {s}\0");
    }
    catch (auto x)
    {
        print("Unknown error type\0");
    };
    
    return 0;
};
```

<a id="nested-loops-with-breakcontinue"></a>
### Nested Loops with Break/Continue
```
def find_in_matrix(int[][] matrix, int target) -> bool
{
    for (int i = 0; i < 10; i++)
    {
        for (int j = 0; j < 10; j++)
        {
            if (matrix[i][j] == target)
            {
                print(f"Found at [{i}][{j}]\0");
                return true;  // Break out of both loops
            };
            
            if (matrix[i][j] < 0)
            {
                continue;  // Skip negative values
            };
        };
    };
    
    return false;
};

// Do-while with complex condition
def wait_for_ready(int* status_reg) -> void
{
    int timeout = 1000;
    do
    {
        if (*status_reg & 0x01)  // Ready bit
        {
            break;
        };
        timeout--;
    }
    while (timeout > 0 & !(*status_reg & 0x80));  // Not error bit
};
```

---

<a id="simple-packet-parser"></a>
### Simple Packet Parser
```

struct IPHeader
{
    nybble version, ihl;
    byte tos;
    be16 total_length, identification, flags_offset;
    byte ttl, protocol;
    be16 checksum;
    be32 src_addr, dst_addr;
};

def parse_ip_header(bytes* packet) -> IPHeader
{
    IPHeader* header = (IPHeader*)packet;
    return *header;
};

def format_ip(be32 addr) -> string
{
    bytes* bp = (bytes*)@addr;
    return f"{bp[0]}.{bp[1]}.{bp[2]}.{bp[3]}\0";
};

// Usage
bytes packet_data = [
    0x45, 0x00, 0x00, 0x3c,  // Version=4, IHL=5, ToS=0, Length=60
    0x1c, 0x46, 0x40, 0x00,  // ID, Flags
    0x40, 0x06, 0xb1, 0xe6,  // TTL=64, Protocol=TCP, Checksum
    0xc0, 0xa8, 0x01, 0x01,  // Source: 192.168.1.1
    0xc0, 0xa8, 0x01, 0x02   // Dest: 192.168.1.2
];

IPHeader hdr = parse_ip_header(@packet_data[0]);
print(f"Source: {format_ip(hdr.src_addr)}\0");
print(f"Dest: {format_ip(hdr.dst_addr)}\0");
```

<a id="fixedpoint-math"></a>
### Fixed-Point Math
```
// 16.16 fixed-point format
signed data{32} as fixed16_16;

def to_fixed(float value) -> fixed16_16
{
    return (fixed16_16)(value * 65536.0);
};

def from_fixed(fixed16_16 value) -> float
{
    return (float)value / 65536.0;
};

def fixed_mul(fixed16_16 a, fixed16_16 b) -> fixed16_16
{
    i64 temp = ((i64)a * (i64)b) >> 16;
    return (fixed16_16)temp;
};

def fixed_div(fixed16_16 a, fixed16_16 b) -> fixed16_16
{
    i64 temp = ((i64)a << 16) / (i64)b;
    return (fixed16_16)temp;
};

// Usage
fixed16_16 a = to_fixed(3.14159),
           b = to_fixed(2.0);
fixed16_16 result = fixed_mul(a, b);
print(from_fixed(result));  // approx 6.28318
```

---

<a id="type-system-edge-cases"></a>
## **Type System Edge Cases**

<a id="void-semantics"></a>
### `void` semantics
```
// Void as a value
void x = void;      // Cannot have void type, only void pointer
void* px = @0;      // Null void pointer. Allocates a 0 and takes its address
                    // Based on default pointer width (64)

if (px is void)
{
    print("px is null\0");
};

// Conditional void assignment
void y = condition ? void : some_value;

// Void in arrays (creates holes)
int[] sparse = [1, 2, void, 4, void, 6];
if (sparse[2] == void)
{
    sparse[2] = 3;  // Fill the hole
};

// Function returning void pointer
def get_nullable() -> int*
{
    if (error_condition)
    {
        return (int*)void;  // Return null
    };
    return @some_value;
};
```

---

<a id="calling-conventions"></a>
# **Calling Conventions**
Flux allows you to use different calling conventions at the language level.
```
stdcall foobar() -> void;
```
`def` is `fastcall` by default. You may change this in the configuration.
You may also create function pointers of different calling conventions:
```
vectorcall{}* someSIMDfunc() -> u64*;
```

---

---

<a id="keyword-list"></a>
# Keyword list:
```
alignof, and, as, asm, assert, auto, break, bool, byte, case,
catch, cdecl, const, continue, contract, data, def, default, defer,
deprecate, do, double, elif, else, enum, false, fastcall,
float, for, global, goto, heap, if, in, is, int, jump, label,
local, long, namespace, noinit, noreturn, not, object, or,
private, public, register, return, signed, singinit, sizeof,
stack, stdcall, struct, switch, this, thiscall, throw, true,
try, typeof, uint, ulong, union, unsigned, using,  vectorcall, void,
volatile, while, xor
```

<a id="operator-list"></a>
# Operator list:
```
ADD = "+"
SUB = "-"
INCREMENT = "++"
DECREMENT = "--"
MUL = "*"
DIV = "/"
MOD = "%"
NOT = "!"
POWER = "^"
# Logical
AND = "&"
OR = "|"
NAND = "!&"
NOR = "!|"
XOR = "^^"
# Comparison
EQUAL = "=="
NOT_EQUAL = "!="
LESS_THAN = "<"
LESS_EQUAL = "<="
GREATER_THAN = ">"
GREATER_EQUAL = ">="
# Assignment
ASSIGN = "="
PLUS_ASSIGN = "+="
MINUS_ASSIGN = "-="
MULTIPLY_ASSIGN = "*="
DIVIDE_ASSIGN = "/="
MODULO_ASSIGN = "%="
POWER_ASSIGN = "^="
# Bitwise operators
# Logical
BITNOT = "`!"
BITAND = "`&"
BITOR = "`|"
BITNAND = "`!&"
BITNOR = "`!|"
BITXOR = "`^^"
BITXNOT = "`^^!"
BITXNAND = "`^^!&"
BITXNOR = "`^^!|"
# Assignment
AND_ASSIGN = "&="
OR_ASSIGN = "|="
XOR_ASSIGN = "^^="
BITAND_ASSIGN = "`&="
BITOR_ASSIGN = "`|="
BITNAND_ASSIGN = "`!&="
BITNOR_ASSIGN = "`!|="
BITXOR_ASSIGN = "`^^="
BITXNOT_ASSIGN = "`^^!="
BITXNAND_ASSIGN = "`^^!&="
BITXNOR_ASSIGN = "`^^!|="

# Ternary assignment, assign if left side is null.
TERN_ASSIGN = "?="
NOT_NULL = "!?"     // unary boolean postfix operator, primary use for pointers `if (px!?) {...}`

# Shift
BITSHIFT_LEFT = "<<"
BITSHIFT_RIGHT = ">>"
BITSHIFT_LEFT_ASSIGN = "<<="
BITSHIFT_RIGHT_ASSIGN = ">>="

BITSLICE = "``"

ADDRESS_OF = "@"
ADDRESS_ASSIGN = "@="
RANGE = ".."
SCOPE = "::"
QUESTION = "?"
COLON = ":"
TIE = "~"
STRINGIFY = "$"
RETURN_ARROW = "->"
CHAIN_ARROW = "<-"
RECURSE_ARROW = "<~" // def foo() <~ void;  // Emits musttail, 0 stack growth
NULL_COALESCE = "??"
NO_MANGLE = "!!"
FUNCTION_POINTER = "{}*"
ADDRESS_CAST = "(@)"
```

---

<a id="primitive-types"></a>
## Primitive types:

bool `true`/`false`, byte `0xFF`, int `5`, uint `300u`, long `23492399393233`, ulong `983787283748727u`, float `3.14159`/`20f`, double `3.1415926585`/`360d`, char `"B"` == `66` - `65` == `'A'`, data

<a id="all-types"></a>
## All types:

bool, byte, int, uint, long, ulong, float, double, char, data, void, object, struct, union, enum

<a id="preprocesor-directives"></a>
## Preprocesor directives:
`#import`, `#dir`, `#def`, `#ifdef`, `#ifndef`, `#else`, `#warn`, `#stop`