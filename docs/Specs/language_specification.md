<a id="flux"></a>
# Flux

Flux is a compiled, general purpose programming language.

It provides power with ease of writing.

If you like Flux, please consider contributing to the language or joining the [Flux Discord server](https://discord.gg/RAHjbYuNUc) where you can ask questions, provide feedback, and talk with other Flux enjoyers!

**Creator note** Everything in Flux is **stack allocated** unless specified.  
- This means you are likely to introduce stack overflows if you perform stack allocations inside loops such as declaring a new variable each time a loop passes.

---

## Table of Contents

- [Flux](#flux)
  - [Functions](#functions)
  - [Variadic functions](#variadic-functions)
  - [Chaining Functions](#chaining-functions)
  - [External Functions (FFI)](#external-functions-ffi)
  - [Exporting Functions with `export`](#exporting-functions-with-export)
  - [Importing with `#import`](#importing-with-import)
  - [Importing with `#package`](#importing-with-package)
    - [Very simple preprocessor](#the-preprocessor)
  - [Namespaces](#namespaces)
  - [Structs](#structs)
  - [Struct recast with `from`](#struct-recast-with-from)
  - [Objects](#objects)
    - [Required methods](#required-methods)
  - [Deferred object cleanup with `defer`](#deferred-object-cleanup-with-defer)
  - [Traits](#traits)
  - [Interfaces](#interfaces)
    - [Protocol relationship operators](#protocol-relationship-operators)
    - [Attachment rules](#attachment-rules)
  - [Public/Private with Objects/Structs](#publicprivate-with-objects)
  - [i-Strings and f-Strings](#istrings-and-fstrings)
  - [Pointers](#pointers)
  - [You can also use in-line assembly directly](#you-can-also-use-inline-assembly-directly)
  - [Logic with if/elif/else](#logic-with-ifelifelse)
  - [The `data` keyword](#the-data-keyword)
    - [Mixing Signed/Unsigned in Expressions](#mixing-signedunsigned-in-expressions)
  - [Endianness Handling](#endianness-handling)
  - [Casting](#casting)
  - [Direct type conversion](#direct-type-conversion)
  - [The `typeof`, `sizeof`, `alignof`, and `endianof` built-ins](#the-typeof-sizeof-alignof-and-endianof-builtins)
  - [`void` as a literal](#void-as-a-literal)
  - [Arrays](#arrays)
  - [Loops](#loops)
  - [Membership testing with `in`](#membership-testing-with-in)
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
  - [Contract `# binding`](#contract-binding)
  - [Contracts on operators](#contracts-on-operators)
  - [Type Functions](#defining-type-functions)
  - [Functionless Types](#functionless-types)
  - [Expression-based macros with `macro`](#expressionbased-macros-with-macro)
  - [Templates](#templates)
  - [Templating operators](#templating-operators)
  - [Combining templates, contracts, and operators](#combining-templates-contracts-and-operators)
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
- [Stringification with `$`](#stringification-with)
- [Codification](#codification)
- [The Ditto Operator](#the-ditto-operator)
- [Compile Time Execution with `comptime`](#compile-time-execution-with-comptime)
- [Emitting code back into your source file with `emitflux`](#emitflux)
- [The Effect System - Algebraic Effect Tracking](#flux-effect-system)
- [Keyword list](#keyword-list)
- [Operator list](#operator-list)
- [Operator Precedence and Associativity](#operator-precedence-and-associativity)
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

**How an overload is chosen at a call site:**
1. **Filter by argument count.** Only overloads whose parameter count matches the call's
   argument count are considered.
2. **Prefer an exact type match.** Among the count-matching candidates, the compiler looks for
   one whose parameter types are an exact match to the arguments' actual types, in declaration
   order.
3. **Otherwise, fall back to the first count-matching overload declared**, and adapt the
   arguments to fit its parameter types rather than treating the mismatch as an error.

This means overload selection is driven by argument count first and exact type match second; it
does not attempt the kind of best-match ranking among multiple inexact candidates that C++ does.
If none of the overloads for a given arity match exactly, you get whichever one was declared
first, with its arguments coerced to fit - so when overloading on type for the same arity
actually matters, declaration order matters too.

**Argument coercion at call sites.** Once an overload is selected, arguments that don't already
match the parameter types exactly are adapted automatically:
- **`void*` is a universal pointer type at call boundaries.** Passing any pointer where a `void*`
  parameter is expected bitcasts automatically (decaying through an array-to-pointer step first
  if needed), and passing a `void*` argument where a concrete pointer type is expected does the
  reverse. Neither direction requires an explicit cast at the call site.
- **Arrays decay to pointers automatically** when passed to a parameter declared as a pointer to
  the array's element type - you can pass an `int[8]` directly where an `int*` parameter is
  expected.
- **Integer width mismatches are adjusted, not rejected.** Passing a narrower or wider integer
  than the parameter declares truncates or extends it to fit (sign- or zero-extending based on
  the argument's known signedness). Unlike the array/integer packing casts described under
  "Casting", there is no "sizes must match exactly or it's an error" rule for ordinary function
  arguments - a call site adapts silently, because passing a value into a parameter is about
  *conveying* a value, not *reinterpreting* a fixed memory layout the way an explicit pack/unpack
  cast is.

Built-in *operator* overloads (see "Custom infix operators and overloading") follow a stricter
rule than ordinary functions: an operator overload is only used when its parameter types are an
exact match for the operands. There is no fall-back-and-coerce step for operators - if nothing
matches exactly, the native operation runs instead, since silently falling back to the wrong
user-defined overload for a built-in symbol would be far more surprising than just doing the
default thing.


<a id="variadic-functions"></a>
## **Variadic functions**
Variadics in Flux are very straightforward, and use the `...` elipse operator.  
You can index the elipse operator to yield the arguments passed, example:
```
#import <standard.fx>;

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

<a id="importing-with-import"></a>
## **Importing with `#import`**

Any file you import will take the place of the import statement.

```
#import <standard.fx>;  // <> means stdlib, "" means local to source file
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

<a id="importing-with-package"></a>
## **Importing with `#package`**

Packages are imported from the compiler's local FPM registry located inside `.fpm\packages`.

To import a package, use the package name directly:
```
#import <standard.fx">

#package super-types, flux-boost;  // these don't exist, yet..
```

You still need to perform `using` statements unless the package self-uses, meaning it has the `using` statements inside of it near the end of entrypoint file.

---

<a id="the-preprocessor"></a>
### The Preprocessor
```
#import <standard.fx>;

#ifdef __WINDOWS__
#def DEFAULT_CONFIG_FLAG 0x4000;
#elif __LINUX__
#def DEFAULT_CONFIG_FLAG 0x8000;
#endif;

#warn "This will show a warning message.";

#stop "This will hard-stop compilation.";

#dir "C:\\path\\to\\some\\lib";
// Adds a path to the preprocessor's search list
```

`#def` defines a preprocessor text substitution constant. This is not a macro, just a "dumb" replacement. It is not parameterized, meaning you cannot pass anything in to it.

### Parameterized Substitution:
To achieve C macro-like behavior, you can use `#psub`.  

Example:
```
#import <standard.fx>;

using standard::io::console;

#psub test(x,y) println(x); #
                println(y);

def main() -> int
{
    test("Hello", "world!");

    return 0;
};
```

You can also perform conditional logic with `#ifpsub` and `#ifnpsub`:
```
#import <standard.fx>;

using standard::io::console;

#psub test(x,y) println(x); #
                println(y);

#ifnpsub test2(a)
#warn "[Warning] #psub test2(a) not defined!";
#endif;

def main() -> int
{
    test("Hello", "world!");

    return 0;
};
```

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

## Block assignment
Below is an example snippet from the standard library in `runtime\allocators.fx` around line 415. If the object[at this index] is a struct, you can do block assignment instead of writing `new_tbl[rm_hole]` 4 times.
```
new_tbl[rm_hole]
{
    .key  = new_tbl[rm_next].key;
    .size = new_tbl[rm_next].size;
    .kind = new_tbl[rm_next].kind;
    .slab = new_tbl[rm_next].slab;
};
```

---

<a id="struct-recast-with-from"></a>
## **Struct recast with `from`**
`from` reinterprets an existing value's bytes as a struct, without copying. It's the
struct-typed counterpart to casting a byte array into an integer - useful for parsing a buffer
into a structured view in place rather than building the struct field by field.

```
struct Header
{
    data{16} sig;
    data{32} filesize;
};

byte[6] buf = [0x42, 0x4D, 0x00, 0x01, 0x02, 0x03];

Header h from buf;
// h.sig == 0x424D, h.filesize == 0x00010203
// `buf` is no longer usable after this point.
```

The right-hand side of `from` may be a plain identifier (an array or other addressable variable)
or an array slice (`buf[a:b]`). When the source is a slice, the compiler builds the struct view
directly over the original buffer starting at the slice's offset - there is no intermediate copy
of the sliced range.

The total size of the source must match the struct's total byte size; a mismatch is a
compile-time error, the same as casting one struct type to another of a different size.

**By default, `from` consumes its source.** After the recast, the original identifier is removed
from scope - referencing it again is a compile-time error. This mirrors the ownership-transfer
behavior of the `~` tie operator: once the bytes are viewed as the new struct type, the old name
for them is gone, so there's exactly one live name pointing at that memory.

To keep the source usable after the recast, append `!` to the source expression:

```
Header h from buf!;   // buf is still valid and usable after this line
```

```
// Recasting directly from a slice - no copy, h aliases buf[2:6]
Header h from buf[2:6];
```

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
#import <standard.fx>;

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
#import <standard.fx>;

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

### You can also `defer` in blocks:
```
#import <standard.fx>;

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

## **Inheritance**  
Object inheritance follows simple rules which eliminate the diamond problem. It will not permit the diamond problem to exist.  

Inheritance syntax is: `object B : A`, which means B inherits from A.

- A child object will not inherit mandatory methods (`__init`, `__expr`, `__exit`)
- If two parents have a function, and signatures match but implementation doesn't, the compiler will error
- The child will inherit all structure and members, excluding private members, unless the parent has `private : your_child, other_child`
- The child will not inherit member symbols that already exist in the child

**Multiple inheritance** is: `object C : A, B`

Here's an example:
```
#import <standard.fx>;

using standard::io::console;

object A
{
    int a1, a2, a3;
    def __init() -> this { return this; };
    def __expr() -> A*   { return this; };
    def __exit() -> void { (void)this;  };
};

object B
{
    int b1, b2, b3;
    def __init() -> this { return this; };
    def __expr() -> A*   { return this; };
    def __exit() -> void { (void)this;  };
};

object C : A, B
{
    int c1, c2, c3;
    def __init() -> this { return this; };
    def __expr() -> A*   { return this; };
    def __exit() -> void { (void)this;  };
};
```

You may use `!+` before `def` to indicate no override, like so:
```
object B
{
    int b1, b2, b3;
    def __init() -> this { return this; };
    def __expr() -> A*   { return this; };
    def __exit() -> void { (void)this;  };

    !+ def foo() -> void {};
};

object C : B
{
    +  def foo() -> void {}; // compiler will error, child must inherit foo from parent
}
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

You may have multiple traits to apply such as:
```
Drawable Deletable Resizable object Square
{
    /// ... ///
};
```

This can get hard to read fast, so you can compose traits together:
```
trait GeomT1 = Drawable & Deletable & Resizable;

GeomT1 object Square
{
    /// ... ///
};
```

<a id="interfaces"></a>
## **Interfaces**
Interfaces define how two or more objects interact. Every interface parameter must declare a trait constraint — bare role names without a trait are a compile error.

Attaching an interface to an object implicitly requires both the attached object and any named partner objects to satisfy their respective trait constraints. This is checked at compile time.

### Protocol relationship operators

Three operators may appear inside an interface body, each expressing a different kind of relationship between the two roles:

| Syntax | Meaning |
|---|---|
| `A : B { methods }` | A may call these methods on a B instance |
| `B(A) { methods }` | Return values of these A methods may be passed as arguments into B |
| `A -> B { methods }` | These A methods may be called from inside a B method body |

All three can coexist in a single interface for the same pair of roles. Each is enforced independently at compile time.

### `A : B` — call permission

The original and most common form. Restricts which methods A may call on B. Once a governed pair exists, calling any unlisted method — even a public one — is a compile-time error.

### `B(A)` — pass-into permission

Controls data flow at call sites. When a return value of an A method is passed directly as an argument to a B method, the compiler checks that the A method is listed in the `B(A)` block. This enforces that only sanctioned values flow across the boundary.

```
// OK -- query is listed in the B(A) block
b.some_func(a.query());

// Error -- secret is not listed
b.some_func(a.secret());
```

### `A -> B` — return-to permission

Controls call context. An A method listed in `A -> B` may be called from inside a B method body. Methods not listed cannot be called from inside B, even if they are otherwise public.

```
// Inside a B method body:
int val = a.result();   // OK -- result is listed in A -> B
int val = a.secret();   // Error -- secret is not listed
```

### Full example

```
trait Queryable  { def query(byte* sql) -> byte*; };
trait Connectable { def connect() -> bool, disconnect() -> bool; };

interface Database(A: Connectable, B: Queryable)
{
    A : B
    {
        connect()    -> bool,
        disconnect() -> void
    };

    B(A)
    {
        query(byte* sql) -> byte*
    };

    A -> B
    {
        result() -> byte*
    };
};

object Client, Store;

object Store
{
    def __init() -> this { return this; };
    def __exit() -> void {};
    def __expr() -> int { return 0; };
    def query(byte* sql) -> byte* { return sql; };
    def disconnect() -> void {};

    def fetch(Client* c) -> byte*
    {
        // Allowed: result() is listed in A -> B
        byte* r = c.result();
        return r;
    };
} : Database(Client, this);

object Client
{
    def __init() -> this { return this; };
    def __exit() -> void {};
    def __expr() -> int { return 0; };
    def connect() -> bool { return true; };
    def disconnect() -> bool { return true; };
    def result() -> byte* { return "data\0"; };
} : Database(this, Store);

def main() -> int
{
    Client c();
    Store  s();

    // Allowed: query() is listed in B(A), result() is the A method being passed
    byte* out = s.query(c.result());

    // Allowed: connect() is listed in A : B
    c.connect();

    return 0;
};
```

### Attachment rules

- An interface may be attached to either or both participants. A single attachment is sufficient to register all protocol rules for the pair.
- Argument order must match the interface parameter declaration: `Database(Client, this)` binds the first param role to `Client` and the second to `this`.
- Attaching with the wrong argument order is a compile error if the resulting role bindings violate trait constraints.
- A partner type named in an attachment (e.g. `Store` in `Database(this, Store)`) is checked against its role's required trait even if it never attaches the interface itself.

---


<a id="publicprivate-with-objects"></a>
## **Public/Private with Objects**  
Struct public and private works by only allowing access to private sections by the parent object that "owns" the struct.  
The struct is still data where public members are visible anywhere, but its private members are only visible/modifiable by the object immediately containing it.

```
struct myStruct
{
    int x, y;
};

object Obj2;

object Obj1
{

    Obj2 myObject();

    // ... required methods ...

    private : Obj2    // Obj2 is a friend class and can inherit Obj1's private members
    {
        // code
    };

    def foo() -> int
    {
        return this.myObject.myStruct.y;    // ERROR - Need to use a getter of Obj2
    };
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
        return this.myStruct.y;
    };
};
```

---

<a id="istrings-and-fstrings"></a>
## **i-Strings and f-Strings**

The syntax in Flux would be: `i"{}{}{}":{x;y;z;};` for an i-string, and `f"{var1}{var2}\0";` for an f-string.

This allows you to write clean interpolated strings without strange formatting.  
**f-string Example**
```
#import <standard.fx>;

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

**i-string Example**  
The brackets are replaced with the results of the statements in order respective to the statements' position in the statement array in i-strings.  
```
#import <standard.fx>; // imports types.fx

using standard::io::console;

def bar() -> noopstr { return "World"; };    // We get the non-OOP string type from the types library

def main() -> int
{
    println(i"Hello {} {}" : {bar() + "!"; "test";});

    x = i"Bar {}":{bar()};     // "Bar World!"

    noopstr a = "Hello", b = "World!",
            c = f"{a} {b}";    // "Hello World!"

    println(c);

    return 0;
};
```

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
#import <standard.fx>;

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
#import <standard.fx>;

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
#import <standard.fx>;

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
#import <standard.fx>;

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
#import <standard.fx>;

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

To prevent a custom type from having functions, use `data!`. See [functionless types](#functionless-types)

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

**The general casting rules.** Every cast falls into one of the following cases, determined by
the source and target type pair:

- **Same underlying representation, different Flux type.** If the source and target type happen
  to share the same underlying machine representation (for example, `le32` and `uint` are both
  a plain 32-bit integer), the cast performs no bit-level work. Instead, the compiler re-tags the
  value with the target type's metadata. This is the mechanism behind clearing an endianness tag
  explicitly:
  ```
  le32 netValue = ...;
  uint plain = uint(netValue);   // same bits, but now untagged as native/no endianness
  ```
- **Integer to integer.** Narrowing truncates to the target width. Widening extends to the
  target width, sign-extending for signed sources and zero-extending for unsigned sources.
- **Integer and floating point.** `(float)`/`(double)` casts from an integer, and
  `(int)`/`(long)`-style casts from a float or double, convert the numeric value (not the bit
  pattern) using standard signed conversion. `(float)x` and `(double)x` between each other
  extend or truncate the floating-point value as expected. To convert *bits* rather than *value*
  between an integer and a float of the same width, route through a same-size array (see
  "Arrays" below).
- **Pointers.** Pointer to pointer is a plain reinterpretation - any pointer type converts to
  any other pointer type directly. Pointer to integer normally takes the pointer's address and
  stores it as an integer value. **The one exception is a pointer whose pointee is an array
  type** - casting an array pointer to an integer does not produce the array's address as a
  number; it packs the array's *contents* into the integer, following the array-packing rules
  below. To get the numeric address of an array instead of its packed contents, take the
  address of the array variable itself and cast through a non-array pointer type first (see
  "Pointer to integer conversions"). Integer to pointer zero-extends the integer to a full
  machine address width if it's narrower, then reinterprets it as the target pointer type.
- **Structs.** Casting between two struct types reinterprets the same bits as the new layout,
  provided both structs have the same total bit width. A size mismatch is a compile-time error -
  there is no implicit padding or truncation when reinterpreting one struct as another. Casting
  a struct value to a pointer type takes its address (allocating a temporary stack slot first if
  the value doesn't already live in memory); casting a struct pointer to another pointer type is
  a plain reinterpretation.

---

<a id="direct-type-conversion"></a>
## Direct type conversion:
You can do function-like conversion only with built-in types like `int`, `long`, `double`, `bool`, etc.
```
#import <standard.fx>;

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
#import <standard.fx>;

using standard::collections; // For the dynamic array 'Array'

Array[] myArr = [x.name for (Array x in oldArr) if (x.name.len() > 5)];
```

**Casting between arrays, integers, and floating-point values**

Casting a fixed-size array to an integer or floating-point type (and back) packs or unpacks the
array element by element, following one fixed convention:

> **Element 0 occupies the most significant bits of the integer; the last element occupies the
> least significant bits.** This holds regardless of array length, element width, or any
> endianness tag on the element type - array packing is always big-endian at the array level.

```
u64 packed = (u64)[0x12u, 0x34u, 0x56u, 0x78u, 0x9Au, 0xBCu, 0xDEu, 0xF0u];
// packed == 0x123456789ABCDEF0 - element 0 is the highest byte.

byte[8] bytes = (byte[8])packed;
// bytes == [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0]
```

Floats and doubles participate in the same packing rule by having their raw bit pattern treated
as the integer payload for that slot - packing four bytes into a `float` reinterprets those four
bytes' bits as the float's bit pattern (not as a numeric conversion of the bytes' values).

**The total bit width must match exactly.** Packing an array into an integer (or unpacking an
integer into an array) requires `element_count * element_bit_width == target_bit_width`. There
is no implicit zero-padding or truncation to make a mismatched size fit - a three-element
`byte[3]` cannot be packed directly into a 32-bit integer; pack into a 24-bit `data{24}` instead,
or pad the array to four elements first.

**Unpacking into a byte or char array adds one extra, null element.** `(byte[8])someValue`
allocates and returns nine bytes: the eight packed bytes followed by a `0` terminator, so the
result can be used immediately as a C-style string. This applies specifically to 8-bit element
arrays; arrays of wider elements (`u16[4]`, for example) are not null-padded.

This packing convention is also what powers the rewrites shown under "Advanced data manipulation
techniques" - `hash[0..3] = (byte[4])(be32)ctx.state[0];` relies on exactly this
element-0-is-high-bits ordering to place the most significant byte of `ctx.state[0]` at
`hash[0]`.

## Block initialization with `{}`
```
noopstr[3] test =
[
    "String 1", // this is a list of items, not assignment statements
    "string 2",
    "string 3!"
];

test
{
    [0] = "New string!";    // these desugar to individual assignments
    [1] = "Another one!";   // like test[0] = "New string!"; <- would be required here, so sugar requires it
    [2] = "Changed again?"; //
};
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

<a id="membership-testing-with-in"></a>
## **Membership testing with `in`**
Beyond `for (x in y)`, `in` is also a general binary operator usable in any expression context -
`if`, ternaries, `return`, assignments, anywhere a boolean is expected:

```
int x = 5;
int[5] arr = [1, 2, 3, 4, 5];

if (x in arr) { ... };          // true: 5 is an element of arr
bool found = 3 in arr;
```

It resolves differently depending on what the needle and haystack look like:

| Needle | Haystack | Behavior |
|---|---|---|
| single value | string (`byte*`/`char*`) | true if that single byte/char occurs anywhere in the string |
| single value | fixed-size or decayed array | true if any element of the array equals the value |
| array / sub-sequence | string | true if the sequence occurs as a substring |
| array / sub-sequence | array | true if the sequence occurs as a contiguous sub-sequence anywhere in the array |

```
byte* greeting = "Hello, World!";
if ('W' in greeting) { ... };          // true
if ("World" in greeting) { ... };      // true - substring search

int[6] nums = [1, 2, 3, 4, 5, 6];
int[2] pair = [3, 4];
if (pair in nums) { ... };             // true - contiguous sub-sequence
```

---

<a id="singleinitialized-variables-with-singinit"></a>
## **Single-initialized variables with `singinit`**
```
#import <standard.fx>;

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
#import <standard.fx>;

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

Enumerated lists are type `int` by default. Each item in an enumerated list has an associated ordinality if no value is set. Imagine we want to name index values so we don't have to remember the indexes themselves.

```
enum Skills
{
    FIREBOLT,    // 0
    ICE_SHARD,   // 1
    THUNDERSTORM // 2
    //...
    // 999
};
```

Now say we need something more specific, like named pointers. We can't use `int` on a 64 bit system to store a 64 bit address, so we use a typed enum by putting a type before the `enum` keyword:
```
u64 enum PointerMap
{
    DedupSchedule   = 0xDEADBEEFCAFEFOOD,
    ReallocEntities = 0xFFFF00000037EADC,
    _Function3      = 0xF000000000000001,
    //...
    //
};
```

Then we can create a function pointer to that function:
```
PointerMap pm;

def foo() -> void = (@)pm.DedupSchedule; // (@) treats the value as an address

foo();
```

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
#import <standard.fx>;

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
} # ErrorUnionEnum; // # is the 'tag' operator


def foo() -> ErrorUnion
{
    ErrorUnion err;

    err.bRval = false; // Set bool to active element
    err.# = ErrorUnionEnum.BOOL_ACTIVE;

    return err;
};


def main() -> int
{
    ErrorUnion e = foo();

    switch (e.#)
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

<a id="dict"></a>
## **Dictionaries**

Definition: `dict{KeyType:ValueType} myDict`  
Instance with initializer:
```
dict{"":""} myDict
{
    "Hello": "World!",
    "hey": "you"
};
```

Access: `myDict["Hello"]`  
Merge: `dict{"":""} merged = myDict + myDict2;`

Dictionaries are key-value stores with a homogeneous key type and homogeneous value type declared in the `dict{K:V}` type specifier.
```
dict{"":""} greetings
{
    "en": "Hello",
    "es": "Hola",
    "jp": "Konnichiwa"
};

println(greetings["en"]); // Hello
```

Dictionaries can be passed to and returned from functions using the templated `dict{T:U}` type:
```
def foo<T,U>(dict{T:U} d) -> dict{T:U}
{
   -> d;
};
```

Dictionaries can be merged with `+`:
```
dict{"":""} a { "x": "1" };
dict{"":""} b { "y": "2" };
dict{"":""} c = a + b;
```


### Inline dict literals with `d{}`

A `d{}` expression creates an anonymous dict inline without declaring a named variable. The result can be immediately accessed with `[key]`:

byte* status = d{(a.logged_in):"Logged In", (!a.logged_in):"Guest"}[true];


When all keys and values are compile-time constants, the entire expression folds at compile time and is baked directly into the binary with no runtime cost.

// Compile-time constant -- no runtime dict lookup
byte* msg = d{true:"yes", false:"no"}[true];


The `[key]` access on a `d{}` expression is handled by the existing array access postfix, so the inline dict participates naturally in any expression context.

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
#import <standard.fx>;

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

<a id="the-ditto-operator"></a>
## **The Ditto Operator `#"`**
The ditto operator repeats the previous initializer expression in a multi-declarator variable declaration. It is shorthand for writing the same expression again.
```
ulong p0 = alloc_stub_page(),
      p1 = #",
      p2 = #",
      p3 = #",
      p4 = #",
      p5 = #";
```
Is identical to:
```
ulong p0 = alloc_stub_page(),
      p1 = alloc_stub_page(),
      p2 = alloc_stub_page(),
      p3 = alloc_stub_page(),
      p4 = alloc_stub_page(),
      p5 = alloc_stub_page();
```
This works for any initializer expression, including those with side effects:
```
int i;
int x = ++i,   // 1
    y = #",    // 2
    z = #";    // 3
```
Each `#"` produces an independent evaluation of the repeated expression — it is not a reference to the prior variable's value.

`#"` must be followed immediately by `,` or `;` in variable declarations. It is not valid as part of a larger expression (for now).

---

### **Repeating Statements With Ditto**  
Using `#"` on its own line will repeat the statement previous to it.  
Here's a simple example that should be straightforward enough to understand in all applications. Try not to invent edge cases, they don't exist. If the parser would error, it's not an edge case, it's an error.
```
#import <standard.fx>;

using standard::io::console;

def main() -> int
{
    println("Hello!");
    #";
    return 0;
};
```

---

### **Parameterized Ditto in Function Calls**

`#"` may also appear as a function call argument, where it repeats the argument at the same position from the immediately preceding statement, provided that statement was a call to the same function with the same arity.

```
foo(x, y, z);
foo(y, #", z);   // identical to foo(y, y, z)
```

Each `#"` is replaced by a copy of the corresponding positional argument from the previous call — independently evaluated, not a reference.

```
foo(x, y, z);
foo(#", #", #");  // identical to foo(x, y, z)
```

The previous statement must satisfy all of the following, or it is a compiler error:

- It must be a function call statement (not an expression like `a + b`, a variable declaration, a control statement, etc.)
- It must be a call to the same function name
- It must have the same number of arguments

```
foo(x, y, z);
bar();
foo(x, #", #");   // error: previous statement was bar, not foo

foo(x, y);
foo(x, #", #");   // error: arity mismatch (2 vs 3)

foo(x, y, z);
a + b;
foo(x, #", #");   // error: previous statement is not a function call
```

Ditto in argument lists always refers to the **previous statement**, not the previous argument. Chaining across multiple calls works naturally:

```
foo(x, y, z);   // prints "1 2 3"
foo(#", #", #"); // prints "1 2 3"
foo(#", #", #"); // prints "1 2 3"
```

Example program:
```
#import <standard.fx>;

using standard::io::console;


def foo(int a, int b, int c) -> void
{
    println(f"{a} {b} {c}");
};

def main() -> int
{
    int i;
    int x = ++i,
        y = #",
        z = #";

    foo(x, y, z);
    foo(y, #", #");
    foo(z, #", #");

    return 0;
};
```
Output:
```
1 2 3
2 2 3
3 2 3
```

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

**How this actually works under the hood:**

A symbol that isn't already one of Flux's built-in operators (anything not found in the
"Operator list") is registered as a **new piece of grammar**. From that point on, the parser
recognizes that exact token sequence anywhere an expression is expected and rewrites it directly
into a call to the operator's generated function. This rewrite happens at one single, fixed
precedence tier - between `+`/`-` and `*`/`/`/`%`/`^`, always left-associative - no matter what
the symbol looks like or what a programmer might expect a symbol like `<=>` or `**` to bind like
in another language. If you want a custom operator to behave as though it binds tighter or
looser than that tier, parenthesize at the call site.

A custom symbol can be either a single bare identifier (`NOPOR`, used like a word-operator) or a
sequence of the language's existing punctuation tokens glued together (`+++`, `<=>`, `??=` are
all legal, since `+`, `<`, `=`, `>`, `?` are each already meaningful punctuation on their own).

When the bracketed symbol *is* one of the language's built-in operators, nothing changes about
how that symbol parses - `+` still parses as ordinary addition, at its normal precedence,
because the parser never rewrites built-in symbols into function calls the way it does for new
ones. **This is the actual mechanism behind rule 2 above**: there is no separate code path for
an overloaded `+` to take at parse time. Resolution happens later, during code generation: for
every `+` expression, the compiler checks whether a registered overload exists whose two
parameter types exactly match the operands' types, and calls that function instead of emitting
the native add instruction if so. If no overload matches the operand types, the built-in
behavior runs as normal.

Rule 1 above ("one parameter must not be a built-in type") is enforced as a compile error, not
just a convention: an attempt to overload `+` for two plain primitives (`int` and `int`, `float`
and `double`, etc.) is rejected, specifically so that user overloads can never silently hijack
ordinary primitive arithmetic everywhere it's used. A non-built-in parameter is a struct, an
object, a custom `data` type alias, or a pointer.

**Templated operators** declare their concrete instantiation lazily:
```
operator<T> (T L, T R) [+] -> T
{
    // ...
};
```
Each time that operator symbol is used in an expression with operand types the compiler can
determine, it automatically generates a concrete overload for that specific pair of types (if
one hasn't already been generated). The same non-built-in-parameter restriction still applies
once concrete types are known: a templated `+` is never instantiated for an expression where
both operands turn out to be plain primitives.

Custom operators accept the exact same pre- and post-contract syntax as ordinary functions (see
"Functions and `contract`" and "Contracts on operators" below) - the contract's assertions are
spliced into the operator's generated function body at compile time, so they run on every call
that dispatches to that specific overload, whether the call arrived through the
rewritten-call-site path (new symbols) or the type-matched-dispatch path (built-in overloads).

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
#import <standard.fx>;

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

<a id="contract-binding"></a>
## Contract `# binding`

A contract may declare a **binding** that the compiler enforces at every function that attaches it.
The binding specifies which other contracts must (or must not) appear as pre- or post-contracts on
the same function, and in what order. This lets a contract author express relationships between
contracts and catch misuse at compile time rather than at runtime.

### Syntax

```
contract Name(params)
{
    // body
} # binding { pre_side : post_side };
```

The binding block is written after the contract body, before the terminating `;`.

**`pre_side`** describes what must or must not appear as a pre-contract on any function that
attaches `Name`:

| Form | Meaning |
|---|---|
| `!` | No pre-contracts are allowed on that function. |
| `this` | `Name` itself must be used as a pre-contract (not post). |
| `OtherContract` | `OtherContract` must also be a pre-contract on the function. |
| `this, OtherContract` | Both requirements apply, in that order. |

**`post_side`** describes what must or must not appear as a post-contract:

| Form | Meaning |
|---|---|
| `!` | No post-contracts are allowed on that function. |
| `this` | `Name` itself must be used as a post-contract (not pre). |
| `A, B` | Both `A` and `B` must be post-contracts, in that order (`,`). |
| `A \| B` | Any subset of `A`, `B` that is present must appear in that order (`\|`). |
| `A & B` | Both `A` and `B` must be post-contracts, in any order (`&`). |
| `!A` | `A` must **not** be a post-contract on the function. |
| `A(2)` | Specifically the two-parameter overload of `A` is required. |

The pre and post sides are separated by `:`.

### Examples

**Require the contract itself to be a pre-contract only (never post):**
```
contract Validated(x)
{
    assert(x != 0, "x must not be zero");
} # binding { this : ! };

// OK -- Validated is pre
def foo(int x) -> int : Validated(x) { return x * 2; };

// ERROR -- Validated is post, binding requires it to be pre
def bar(int x) -> int { return x; } : Validated(x);
```

**Require a companion post-contract whenever this contract is used as pre:**
```
contract CheckInput(x)
{
    assert(x > 0, "input must be positive");
} # binding { this : CheckOutput };

contract CheckOutput
{
    assert(rval > 0, "output must be positive");
};

// OK
def process(int x) -> int : CheckInput(x) { return x + 1; } : CheckOutput;

// ERROR -- CheckOutput is missing
def process2(int x) -> int : CheckInput(x) { return x + 1; };
```

**Forbid any pre-contracts when this contract is used as post:**
```
contract Finalize
{
    cleanup();
} # binding { ! : this };

// OK -- no pre-contracts, Finalize is post
def shutdown() -> void { do_work(); } : Finalize;

// ERROR -- SomeSetup is a pre-contract, binding forbids pre-contracts
def shutdown2() -> void : SomeSetup { do_work(); } : Finalize;
```

**Require two post-contracts in order:**
```
contract Stage1
{
    log("stage 1");
} # binding { this : Stage2, Stage3 };

contract Stage2 { log("stage 2"); };
contract Stage3 { log("stage 3"); };

// OK
def pipeline() -> void : Stage1 { work(); } : Stage2 : Stage3;

// ERROR -- wrong order
def pipeline2() -> void : Stage1 { work(); } : Stage3 : Stage2;
```

### Forward declarations

Contracts may be forward-declared before their body is defined, including in comma-separated lists:

```
contract A, B(x, y), C;
```

A binding may only be placed on the definition, not the forward declaration.

### Compiler errors

When a function violates a binding, the compiler emits an error at the function definition naming
the contract whose binding was violated, which side (`pre` or `post`) was violated, and what was
required vs. what was found.

---

<a id="contracts-on-operators"></a>
## Contracts on operators:
```
#import <standard.fx>;

using standard::io::console;

contract NonZero(a,b)
{
    assert(a != 0, "a must be nonzero");
    assert(b != 0, "b must be nonzero");
};

operator(int x, i32 y)[+] -> int : NonZero(x,y)
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
#import <standard.fx>;

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

<a id="defining-type-functions"></a>
## **Defining Type Functions**:
Flux has the ability to define functions for a given type, allowing `.` call notation on a value or variable of that type.
Inside of a type function `_` is reserved, and acts as the `this` parameter.
```
// noopstr is alias for byte*
noopstr.add_world() -> noopstr
{
    return _ + ", World!";  //  "Hello".add_world() == return "Hello" + ", World!"
};

/// Alternatively, you may use "" - Note this is special for type functions ///
"".add_world() -> ""
{
    return _ + ", World!";
};
```

You can use plain types or pointer types, and named struct types, like so:
```
struct MyStru
{
    // .. members ..
};

MyStru.mystru_func1() -> MyStru
{
    // impl
};
```

You may also use tied ~types:
```
~byte*.sub11() -> ~byte*
{
    return _[0] - 11; // set first char - 11, _ is tied type, no need for explicit move
};
```

You can make literal modifiers as well by using `0` with an appropriate suffix:
```
0.my_int_func() -> int   // 55.my_int_func()
{
    return _;
};

0l.my_long_func() -> long
{
    return _;
};

0d.my_double_func() -> double
{
    return _;
};

struct.my_struct_func() -> struct
{
    // impl for your arbitrary struct func
};
```

<a id="functionless-types"></a>
## Functionless Types

To forbid a type from having functions, you can declare it with `data!` like so:
```
#import <standard.fx>;

using standard::io::console;

data!{32} as u32i;

u32i.foo() -> u32i { return 0u; };

def main() -> int
{
    return 0;
};
```

The compiler will error with:  
`✗ Compilation failed: Type u32i is non-functional (declared with data!) and cannot have type functions defined on it at x:y`

---

<a id="templates"></a>
## <**Templates**>  
Templates in Flux are extremely simple.

There are no keywords for templates, only syntax, and involve only type substitution.  
There is no SFINAE, so templates are not subject to the pitfalls SFINAE allows.  

Templates can be applied to functions, structs, objects, and custom operator definitions.

Here's an example of using a template:
```
#import <standard.fx>;


def foo<T>(T x) -> T
{
    return x;
};


def main() -> int
{
    float y = foo<float>(5.5f);
    int z = foo<int>(3);

    println(y);
    println(z);

    system("pause\0");
    return 0;
};
```

The compiler can also infer templates at call sites, so you don't end up with a mess of angle brackets:
```
#import <standard.fx>;

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

## Template Constraints:
You can add constraints to template parameters on their allowed types like so:
```
<T: int | i32, U: long | i64>
```
The syntax is `Param: type (| type)*` comma separated.

Here's an example:
```
#import <standard.fx>;
 
using standard::io::console;

"".fx<T: "", U: "">(T x, U y) -> ""
{
    return _ + f"{x} {y}";
};

def main() -> int
{
    byte* new = "Hello".fx(",", "World!");
    println(new);
    return 0;
};
```
"new" isn't a keyword in Flux, so this is fine.

To set a default type constraint, use `+` before the type like so:
```
<T: +float | int>
```
To enforce no default constraint, use `!+` before your parameter like so:
```
<!+T: float | int>
```
Using `+` on any constraint type when the parameter has no default set with `!+` will throw a compiler error.

## Templates and Type Relationships
Flux allows ways to describe how a type - or pair of types - can behave.

There is a dedicated type relationships operator set specifically to describe relations between types.  
Since all operators are binary, to perform a unary operation, you do `A <op> A`, which is type self-referential.  
All template type relationships operators are distinct and not related to regular operators and cannot be overloaded.

See the [Algebraic Types](https://github.com/kvthweatt/Flux/blob/main/docs/algebraic_types.md) documentation for more details on the operators.

To use type relationships expressions, they must be constrained in a set.

Here's the same example using `~=`, the "must be compatible" operator, and the `:{}` set constraint.
```
#import <standard.fx>;
 
using standard::io::console;

"".fx<T: "", U: "", :{T ~= U}>(T x, U y) -> ""
{
    return _ + f"{x} {y}";
};

def main() -> int
{
    byte* new = "Hello".fx(",", "World!");
    println(new);
    return 0;
};
```

You can separate expressions with a comma like:
```
#import <standard.fx>;
 
using standard::io::console;

"".fx<T: "", U: "", :{T ~= U, T !`< U}>(T x, U y) -> ""
{
    return _ + f"{x} {y}";
};

def main() -> int
{
    byte* new = "Hello".fx(",", "World!");
    println(new);
    return 0;
};
```

However, you do not have to comma separate, and can instead write them circularly.  
Circular expressions can be very long, terse, and carry a lot of meaning.  
Example:
```
D !~= B & [A !@ A] !~= C !`< D !-= A
```
This reads as (inner most []):  
- Values of type A cannot have an address taken of them  
- D must be incompatible with B and A  
- B and A must be incompatible with C  
- C and D independently cannot be used in an expression where bit lowering would occur  
- D cannot be used in signed operations with A

There is a similar relationship here, `D !~= A & B !~= C`. This means `D ~= C` by relation, and doesn't need to be explicitly defined.  
This is the type geometry of Flux.

This can be hard to see if you do not write your expression with care, because you may intend `D !~= C`. See the following:
```
C !~= D !~= B & [A !@ A] !~= C !`< D !-= A
```

Just place the relationship in an open position.

No one wants to see that long expression in their template definition, that's why `constraint` exists.  
`constraint` creates named, generic and parameterized relational expression sets that can be used with a template like so:
```
#import <standard.fx>;
 
using standard::io::console;

constraint MyCS(A)
{
    A !`< A    // This is a unary expression, read as the relation !`< "between A types"
};

def foo<T: int, :{MyCS}>(T x) -> byte
{
    return 5 + x; // lowering would occur here, violating MyCS
};

def main() -> int
{
    foo(10);
    return 0;
};
```
Compiler will output:
```
✗ Compilation failed: Type relation T !`< T violated: illegal truncation on int at 12:5
    return 5 + x;
----^ // 5 + x will lower to byte
```

**The complete type-relationship operator set** and what each one enforces once a template is
instantiated with concrete types:

| Operator | Meaning | Scope |
|---|---|---|
| `~=` | The two types must be **compatible** | pairwise |
| `!~=` | The two types must be **incompatible** | pairwise |
| `!@` | A variable of this type must never have its address taken (`@`) anywhere in the template body | independent |
| `` !`< `` | This type must never appear as either side of a narrowing (truncating) conversion in the body | independent |
| `` !`<= `` | A narrowing conversion specifically **between these two named types** is forbidden | between |
| `` !`> `` | This type must never appear as either side of a widening conversion in the body | independent |
| `` !`>= `` | A widening conversion specifically **between these two named types** is forbidden | between |

"Compatible" (for `~=`/`!~=`) means: both types are pointers or both are non-pointers; if both
are pointers, their pointer depth matches; and if both have a known bit width, the widths are
equal.

The **independent** vs **between** distinction matters once more than two parameters are in
play. `` T !`< T `` (independent, self-referential, as in the `MyCS` example above) forbids `T`
from ever being narrowed by *anything* - any cast or implicit arithmetic narrowing involving
`T`'s width is a violation, regardless of what the other side of that conversion is.
`` T !`<= U `` (between) only forbids narrowing conversions where *both* the source and
destination widths belong to `{T, U}` specifically - narrowing `T` to some unrelated third type
is still allowed.

These checks aren't purely static type comparisons - for the truncation/widening operators, the
compiler walks the instantiated function body looking for the actual operations that would
violate the constraint: explicit casts (`(Type)expr`), `return` statements whose expression is
wider or narrower than the declared return type, and ordinary arithmetic where an implicit
narrowing happens because one operand is wider than the other. This is exactly how the `MyCS`
example above produces a violation from `return 5 + x;` with no explicit cast in sight - the `+`
between an `int` literal and a `byte`-constrained `x` implicitly narrows the result, and that
narrowing context is what gets flagged.

**Joining multiple names with `&`** lets one relation apply to a whole group of parameters at
once: `T & U ~= V` requires *both* `T` and `U` to individually satisfy `~= V`. This reuses the
ordinary `&` (logical AND) token, but inside a constraint set it's a list-joiner for the
relation's operands, not a boolean evaluation of two relation results.

You can comma separate named constraints in your template definition like so:  
`<T: int, :{MyCS1, MyCS2, MyCS3}>`

Template constraints can be used in any template, including operator, struct, and object templates.

**Named constraint sets can be merged**, combining the relations of two or more existing sets
into a new one:
```
constraint MyCS3 = MyCS1 + MyCS2;
```
All sources must declare the same number of parameters. The merged set adopts the first
source's parameter names unless you supply your own rename list before the `=`:
```
constraint MyCS3(M, N) = MyCS1 + MyCS2;
```
Relations from every source are carried over into the merged set, with each source's own
parameter names remapped to the merged set's names.

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
#import <standard.fx>;

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
#import <standard.fx>;

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
The bit-slice operator `` x[a``b] `` addresses individual bits of a value using one consistent
numbering scheme: **bit 0 is the most significant bit of the entire value, and bit numbers
increase moving toward the least significant bit.** This numbering runs across the whole
source - for a struct, it continues across field boundaries in declaration order, exactly as if
the struct's fields had been concatenated into one big-endian buffer. Because struct members
are packed tightly with no padding between them (see "Structs"), bit numbering never has to skip
over hidden padding bits when it crosses from one member into the next - member N's last bit is
immediately followed by member N+1's first bit.

A slice written with the start index greater than the end index (as in the example below) reads
the same bit range but reverses the order of the bits in the result. Bit slices may span up to
the full width of a native integer type (8 through 64 bits).
```
#import <standard.fx>;

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
#import <standard.fx>;

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
#import <standard.fx>;

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
Bit-slice results are ordinary integer values of the slice's width, so a bit slice can itself be
the source of another bit slice - there's no special chaining logic, it falls out naturally.

Assigning into a bit slice (` x[a``b] = value;`) replaces just that bit range in place,
leaving every other bit of the target untouched:
```
u32 packed = 0x12345678;
packed[24``31] = 0xFF;   // replace just the lowest byte
// packed == 0x123456FF
```
The assignment target must be a plain variable, and the start/end indices must be compile-time
constants.

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
unsigned data{5}[10] as 5b_array arr;
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
#import <standard.fx>;

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
#import <standard.fx>;

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
#import <standard.fx>;

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
#import <standard.fx>;

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


<a id="stringification-with"></a>
## Stringification with `$`:
```
#import <standard.fx>;

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
#import <standard.fx>;

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

<a id="compile-time-execution-with-comptime"></a>
# Compile-Time Execution with `comptime`
Flux can execute itself at compile time. It is capable of performing I/O as well.  
For now Flux will be limited to standard I/O and file I/O. Networking will come in a future update.

A dedicated VM was created to handle compile time execution, and is what powers the REPL (coming soon).

To perform compile time code execution in Flux, wrap code in a `comptime` block.

Compile-time code has no main function, the start of execution is at the first statement.  
Here's an example of programming at compile time:
```
#import <standard.fx>;

comptime
{
    def foo() -> void
    {
        compiler.io.console.print("Hello from compile time!\n");
    };
};

def main() -> int
{
    return 0;
};
```

This program will do nothing, because `foo()` was not called.  
The compiler will not automatically call a function that it sees, simply call it afterwards.

```
#import <standard.fx>;

comptime
{
    def foo() -> void
    {
        compiler.io.console.print("Hello from compile time!\n");
    };

    foo();
};

def main() -> int
{
    return 0;
};
```
Result:
```
[INFO] [lexer] ► Lexical analysis
[INFO] [parser] ► Parsing
[INFO] [parser] ► AST generated.
[INFO] [codegen] ► LLVM IR code generation
[AST] Begining codegen for Flux program ...
[AST] Total statements in AST: 45
[AST] Namespace definitions: 10
[AST] Pass 1: Processing using statements...
[AST] Pass 2: Processing not using statements...
[AST] Pre-pass: Registering all object types and extern blocks...
[AST] Pass 3: Processing all other statements...
Hello from compile time!
[AST] Pass 4: Re-emitting pending bodies...
[INFO] [compiler] ► Compiling to object file (Windows)
[INFO] [llc] opt IR optimization pass complete
[INFO] [linker] ► Linking executable: ./test.exe
✓ Compilation completed: ./test.exe
```

You can spread functions across `comptime` blocks like so:
```
#import <standard.fx>;
 
using standard::io::console;

comptime
{
    def foo() -> void
    {
        compiler.io.console.print("comptime foo!!!\n");
    };
};

comptime
{
    foo();

    int x;
    int* px = @x;

    compiler.io.console.print(f"Hello from comptime! {ulong(px)}\n");
};

def main() -> int
{
    return 0;
};
```
Result:
```
[INFO] [lexer] ► Lexical analysis
[INFO] [parser] ► Parsing
[INFO] [parser] ► AST generated.
[INFO] [codegen] ► LLVM IR code generation
[AST] Begining codegen for Flux program ...
[AST] Total statements in AST: 47
[AST] Namespace definitions: 10
[AST] Pass 1: Processing using statements...
[AST] Pass 2: Processing not using statements...
[AST] Pre-pass: Registering all object types and extern blocks...
[AST] Pass 3: Processing all other statements...
comptime foo!!!
Hello from comptime! 17
[AST] Pass 4: Re-emitting pending bodies...
```

You may use any keyword inside `comptime` blocks except for `comptime` itself.  
Yes, you may write an infinite loop at compile time.  

---

<a id="emitflux"></a>
# `emitflux` — Compile-Time Code Generation

`emitflux` is used inside a `comptime` block to inject Flux source code into the surrounding scope. The emitted definitions are deferred and finalized during **Pass 4** ("Re-emitting pending bodies"), so they do not need to be written contiguously — you can build up a single logical definition across multiple `emitflux` calls within one or more `comptime` blocks.

Basic usage:
```
comptime
{
    int x = 42;

    emitflux
    {
        def get_x() -> int { return ~$f"{x}"; };
    };
};

// get_x() is now available at runtime
def main() -> int
{
    return get_x();   // returns 42
};
```

`~$f"..."` and `~$i"..."` expand comptime variables into identifiers or expressions inside an `emitflux` block.

---

## Splice terminators

By default the closing `};` of an `emitflux` block ends emission and returns control to the surrounding `comptime` context. Two special terminators allow you to interleave comptime logic with emitted code — splicing a single logical construct across multiple `emitflux` calls:

### `}#;` — exit emitflux, stay in comptime

`}#;` terminates the current `emitflux` block and returns to the surrounding `comptime` context, leaving the emitted construct open. This lets you run arbitrary comptime code (loops, conditionals, I/O) between emitted chunks.

### `#};` — close a brace inside emitflux without ending it

`#};` emits a closing brace into the generated Flux source without being interpreted as the closing brace of the `emitflux` block itself. Use this to close `switch`, `if`, function bodies, or any other braced construct inside emitted code when the bare `}` would prematurely end the `emitflux`.

---

## Spliced code generation example

The following generates a `dispatch` function whose `switch` body is built case-by-case in a comptime loop:

```
#def NUM_OPS 4;

comptime
{
    byte*[NUM_OPS] op_names = ["add", "sub", "mul", "div"];

    // Step 1: open the function and switch, then exit emitflux with }#;
    emitflux
    {
        def dispatch(int id, int a, int b) -> int
        {
            switch (id)
            {
    }#;

    // Step 2: comptime loop emits one case per op
    int i = 0;
    while (i < NUM_OPS)
    {
        byte* nm = op_names[i];
        int   iv = i;

        emitflux
        {
                case (~$i"{}":{iv;}) { return ~$i"op_{}":{nm;} (a, b); }
        };

        i++;
    };

    // Step 3: close switch and function using #}; to avoid ending emitflux
    emitflux
    {
                default { return -1; };
           #};   // closes switch body
       #};       // closes function body
    };
};
```

Pass 4 collects all of the emitted fragments in order and finalizes `dispatch` as a single coherent function. The comptime loop runs during Pass 3 and is never present in the output binary.

---

## Execution order

| Pass | What happens |
|---|---|
| Pass 3 | `comptime` blocks execute; `emitflux` fragments are collected |
| Pass 4 | All collected `emitflux` fragments are finalized into the surrounding scope |

This means emitted definitions are always available to runtime code, but are not visible to other `comptime` blocks that execute before Pass 4.

---

<a id="flux-effect-system">
# The Effect System - Algebraic Effect Tracking

See [Flux Effect System](https://github.com/kvthweatt/FluxLang/blob/main/docs/effects_system.md) for a more thorough explanation of effects.

Effects are compile-time properties of computation. They describe what a function
does beyond its return value -- whether it allocates, touches IO, modifies memory,
hooks into running code, or any other observable behavior. The compiler tracks these
properties statically, enforces constraints across call chains, and erases them
entirely before codegen. Zero runtime cost.

---

## Overview

An effect is not a label. A label is metadata the compiler carries. An effect is a
membership in a relationship algebra the compiler reasons from. The algebra is what
makes it programming the compiler rather than annotating for it.

There are two annotation sites: origin and boundary.

**Origin** (`# effect {}`) declares what effects a function introduces.

**Boundary** (`# attenuate {}`) declares what effects are contained and cannot
escape a function's interface.

Everything in between is inferred. Effects propagate transitively up the call chain
without annotation. If `a` calls `b` calls `c`, and `c` introduces `Alloc.Heap`,
then `a`'s transitive effect set includes `Alloc.Heap` even if `b` has no annotation.
The compiler computes this through fixed-point propagation over the full call graph.

---

## Syntax

### Effect declaration

```
effect Name { expr };
effect Name.Sub { expr };
```

Declares a user-defined named effect. The body is an effect algebra expression.
Effect names may be dot-separated to express namespacing. User-defined effects
compose on top of built-in effects.

```
effect ShadowStack { *Hook & !@Unsafe & !Alloc };
effect RealTime    { !Alloc & !IO & !Throw };
effect NetworkIO   { *IO.Socket & [Mem.Write | Mem.Read] };
```

### Origin annotation

```
def foo() -> void # effect { expr };
def foo() -> void { ... };
```

Declares that `foo` introduces the effects described by `expr`. The annotation goes
on the prototype. Definitions inherit it -- you do not repeat the tag on the
definition site.

Tags may be chained in any order after contracts:

```
def foo() -> void : SomeContract # effect {*Alloc.Heap} # attenuate {IO};
def foo() -> void { ... };
```

Tags may also appear after the closing brace of a definition body:

```
def foo() -> void
{
    ...
} # effect {*IO.Console};
```

### Boundary annotation

```
def foo() -> void # attenuate { expr };
```

Declares that the effects described by `expr` are contained within `foo` and do not
propagate to callers. A caller with `!IO` can call a function annotated
`# attenuate {IO}` without violation -- the effect exists internally but cannot
cross the boundary.

Interfaces may also carry attenuation:

```
interface Sandbox { ... } # attenuate {IO & Alloc};
```

---

## Compiler Flags

| Flag | Behavior |
|------|----------|
| *(default)* | Transparent -- annotations stored, no enforcement |
| `--effects-warn` | Violations reported as warnings, compilation continues |
| `--effects` | Violations are errors, compilation aborted |

---

## Operator Set

All operators are only valid inside `effect {}` and `# attenuate {}` blocks.

### Unary operators

| Operator | Meaning |
|----------|---------|
| `*X` | Implies X -- X propagates upward through the call chain |
| `!X` | Excludes X -- X must not be present |
| `~X` | Requires X -- X must already be present |
| `?X` | Weak propagation -- X propagates but can be suppressed |
| `@X` | Explicitly marks X as attenuatable at a boundary |
| `!@X` | Permanently non-attenuatable -- X can never be stripped |
| `^X` | Suppresses X even if something else implies it |
| `..X` | Propagates exactly one level up, then stops |
| `...X` | Propagates indefinitely (this is the default behavior) |
| `<*X` | Propagates to the caller only, not further up the chain |

### Binary operators

| Operator | Meaning |
|----------|---------|
| `X & Y` | Both X and Y must hold |
| `X \| Y` | At least one of X or Y must hold |
| `X > Y` | X takes priority over Y at conflict boundaries |
| `X -> Y` | If X is present then Y must also be present |
| `X ^| Y` | Exactly one of X or Y -- exclusive or |
| `X <-> Y` | Mutual implication -- both present or neither |
| `X <-> !Y` | If X present then Y must be absent, and vice versa |

### Grouping

Parentheses `()` and brackets `[]` both group subexpressions and are interchangeable.

---

## Propagation Rules

1. Effects propagate implicitly up the call chain through fixed-point analysis.
   No annotation is needed at intermediate functions.

2. Only two annotation sites exist: origin (`# effect {}`) and boundary
   (`# attenuate {}`).

3. `*X` in an effect definition means introducing that effect also introduces X.

4. `!@X` means X cannot be stripped at any boundary. The compiler rejects any
   `# attenuate {X}` attempt on a `!@` effect.

5. `?X` propagates unless explicitly suppressed with `^X` somewhere in the chain.

6. `..X` stops propagating after one level up from the annotated function.

7. `...X` propagates indefinitely. This is the default for unannotated effects.

8. `<*X` propagates to the immediate caller only, not further up.

9. Parent effects imply all children. `IO` implies `IO.Console`, `IO.File`, etc.

10. Attenuating a parent blocks all children. `# attenuate {IO}` blocks all `IO.*`.

11. Attenuating a child is precise. `# attenuate {IO.Socket}` only blocks network IO,
    leaving `IO.File` and all other `IO.*` to propagate normally.

12. Attenuation applies to transitive effects too. If `foo` calls `bar` which
    introduces `IO.Console`, and `foo` declares `# attenuate {IO}`, then callers
    of `foo` see no IO effect regardless of what `bar` does internally.

---

## Conflict Detection

When a function's transitive effect set violates a constraint declared by a
user-defined effect it references, the compiler reports a conflict.

### Exclusive or (`^|`)

`X ^| Y` means exactly one of X or Y may be present in the function's transitive
set. If both are found, it is a conflict.

```
effect ExclusiveIO { IO.Console ^| IO.File };

// Conflict: introduces both sides of the exclusive-or.
def bad() -> void # effect {ExclusiveIO};
def bad() -> void
{
    write_console("x\0");
    read_file("y\0");
};

// OK: introduces only one side.
def good() -> void # effect {ExclusiveIO};
def good() -> void
{
    write_console("x\0");
};
```

### Mutual implication (`<->`)

`X <-> Y` means both or neither must be present. `X <-> !Y` means if X is present
then Y must be absent.

```
effect ReadOnly { *Mem.Read <-> !Mem.Write };

// Conflict: both Mem.Read and Mem.Write present, violating <-> !Mem.Write.
def bad() -> void # effect {ReadOnly};
def bad() -> void
{
    read_process_memory(addr);
    write_exec_memory(addr, 0);
};

// OK: only Mem.Read present.
def good() -> void # effect {ReadOnly};
def good() -> void
{
    read_process_memory(addr);
};
```

---

## Pure Enforcement

`Pure` is a special anchor effect. A function declaring `Pure` must not
transitively introduce any of: `IO`, `Alloc`, `Mem.Write`, `Throw`. The compiler
verifies this against the full transitive call graph.

```
// OK: only calls other Pure functions.
def add(int a, int b) -> int # effect {Pure};
def add(int a, int b) -> int { -> a + b; };

// Violation: calls heap allocator, which introduces Alloc.Heap.
def bad() -> int # effect {Pure};
def bad() -> int
{
    void* p = allocate_something();
    -> 0;
};
```

---

## Built-in Effects

Built-in effects are defined by the compiler and cannot be redefined or made
self-referential. They are namespaced with `.` -- capital letter distinguishes
effect namespaces from code namespaces (`IO.Socket` vs `standard::io::socket`).

### IO family

| Effect | Description |
|--------|-------------|
| `IO` | Any external communication |
| `IO.Console` | stdin / stdout / stderr |
| `IO.File` | Filesystem read or write |
| `IO.Socket` | Network communication |
| `IO.Pipe` | IPC and named pipes |
| `IO.Device` | Hardware device communication |
| `IO.Serial` | Serial port |
| `IO.USB` | USB device IO |
| `IO.GPU` | GPU command submission |

### Alloc family

| Effect | Description |
|--------|-------------|
| `Alloc` | Any allocation |
| `Alloc.Heap` | Standard heap allocation |
| `Alloc.Pool` | Pool or arena allocator |
| `Alloc.Stack` | Stack allocation (VLAs etc.) |
| `Alloc.Virtual` | VirtualAlloc / mmap -- page-level |
| `Alloc.Shared` | Shared memory allocation |

### Unsafe family

All `Unsafe.*` effects carry `!@` -- they are permanently non-attenuatable.

| Effect | Description |
|--------|-------------|
| `Unsafe` | Any unsafe operation |
| `Unsafe.Ptr` | Raw pointer dereference |
| `Unsafe.Cast` | Unsafe type cast |
| `Unsafe.ASM` | Inline assembly |
| `Unsafe.FFI` | Calling foreign functions |
| `Unsafe.Uninit` | Reading uninitialized memory |

### Mem family

| Effect | Description |
|--------|-------------|
| `Mem` | Any memory operation |
| `Mem.Read` | Any memory read |
| `Mem.Read.Process` | Reading another process |
| `Mem.Read.Kernel` | Kernel memory read |
| `Mem.Read.Mapped` | Mapped file or shared memory read |
| `Mem.Write` | Any memory write |
| `Mem.Write.Process` | Writing another process |
| `Mem.Write.Kernel` | Kernel memory write |
| `Mem.Write.Exec` | Writing executable memory |
| `Mem.Write.Mapped` | Mapped file or shared memory write |
| `Mem.Exec` | Executing memory directly |
| `Mem.Exec.JIT` | JIT-compiled execution |
| `Mem.Exec.Shellcode` | Raw shellcode execution |

### Sync family

| Effect | Description |
|--------|-------------|
| `Sync` | Any synchronization operation |
| `Sync.Lock` | Mutex or critical section |
| `Sync.Atomic` | Atomic operations |
| `Sync.Signal` | Signals or events |
| `Sync.Wait` | Blocking wait |

### Crypto family

| Effect | Description |
|--------|-------------|
| `Crypto` | Any cryptographic operation |
| `Crypto.Hash` | Hashing |
| `Crypto.Encrypt` | Encryption |
| `Crypto.Decrypt` | Decryption |
| `Crypto.Random` | Random number generation |
| `Crypto.Key` | Key generation or management |

### Process family

| Effect | Description |
|--------|-------------|
| `Process` | Any process operation |
| `Process.Spawn` | Creating processes |
| `Process.Kill` | Terminating processes |
| `Process.Inject` | Code injection |
| `Process.Suspend` | Suspending or resuming threads |
| `Process.Token` | Token or privilege manipulation |

### Hook family

| Effect | Description |
|--------|-------------|
| `Hook` | Any hooking operation |
| `Hook.Detour` | Inline detour or trampoline |
| `Hook.IAT` | Import address table hook |
| `Hook.SSDT` | SSDT hook (kernel) |
| `Hook.Vtable` | Vtable hook |
| `Hook.Exception` | Exception handler hook |

### Privilege family

| Effect | Description |
|--------|-------------|
| `Privilege` | Any privilege operation |
| `Privilege.Elevate` | Privilege escalation |
| `Privilege.Drop` | Privilege dropping |
| `Privilege.Check` | Privilege checking |

### Time family

| Effect | Description |
|--------|-------------|
| `Time` | Any time-sensitive operation |
| `Time.RealTime` | Hard real-time constraint |
| `Time.Sleep` | Thread sleep or delay |
| `Time.Timer` | Timer creation or management |

### Anchor effects

| Effect | Description |
|--------|-------------|
| `Pure` | No side effects -- implies `!IO & !Alloc & !Mem.Write & !Throw` |
| `Throw` | Can raise exceptions |

---

## Built-in Implication Rules

Some effects automatically imply others when introduced. These implications are
applied transitively by the compiler without requiring explicit annotation.

| Effect | Implies |
|--------|---------|
| `Hook.Detour` | `Hook`, `Unsafe`, `Mem.Write.Exec` |
| `Hook.IAT` | `Hook`, `Mem.Write` |
| `Hook.SSDT` | `Hook`, `Privilege`, `Mem.Write.Kernel`, `Unsafe` |
| `Hook.Vtable` | `Hook`, `Mem.Write` |
| `Process.Inject` | `Process`, `Alloc.Virtual`, `Mem.Write.Exec`, `Hook`, `Unsafe` |
| `Crypto.Key` | `Crypto` |

---

## Primitive Effect Sources

Certain language constructs introduce effects implicitly without requiring
annotation. The compiler seeds these into the call graph automatically.

| Source | Effect introduced |
|--------|------------------|
| `heap` allocation | `Alloc.Heap` |
| Inline `asm` block | `Unsafe.ASM` |
| Raw pointer dereference | `Unsafe.Ptr` |
| `throw` statement | `Throw` |
| Unsafe cast | `Unsafe.Cast` |
| FFI call | `Unsafe.FFI` |

---

## Complete Example

```
// Real-time constraint: no allocation, no IO, no exceptions.
effect RealTime { !Alloc & !IO & !Throw };

// Shadow stack: uses hooks, permanent Unsafe, no allocation.
effect ShadowStack { *Hook & !@Unsafe & !Alloc };

// Pure math -- no side effects.
def dot_product(float* a, float* b, uint n) -> float # effect {Pure};
def dot_product(float* a, float* b, uint n) -> float
{
    float acc;
    uint  i;
    while (i < n) { acc += a[i] * b[i]; i++; };
    -> acc;
};

// Real-time safe: only calls Pure functions.
def rt_update(float* state, float* input, uint n) -> void # effect {RealTime};
def rt_update(float* state, float* input, uint n) -> void
{
    float v = dot_product(state, input, n);
    state[0] = v;
};

// Attenuates its own IO -- callers see no IO effect from this function.
def log_event(byte* msg) -> void # attenuate {IO};
def log_event(byte* msg) -> void
{
    write_to_ring_buffer(msg);
};

// Shadow stack install: uses detour hook, permanent Unsafe, zero allocation.
def install_shadow_stack(void* target) -> void # effect {ShadowStack};
def install_shadow_stack(void* target) -> void
{
    hook_detour(target, (@)void);
};
```

---

## Notes

Effect annotations on prototypes are inherited by definitions. You do not repeat
the tag at the definition site.

User-defined effects compose freely on top of built-ins. An effect body is
evaluated by the same algebra engine as all other effect expressions -- there is no
separate language for defining effects.

The `>` priority operator inside an effect definition resolves conflicts at
boundaries deterministically. Without it, two conflicting effects at a boundary
produce a conflict diagnostic. With it, the compiler applies the declared ordering
and proceeds.

The effect system is purely compile-time. Nothing is emitted. Effects disappear
before codegen. The binary is affected only indirectly -- through what the effect
system proves, which feeds optimizer signals like `Pure` and `!Alloc`.

---

<a id="keyword-list"></a>
# Keyword list:
```
and, as, asm, assert, auto, bool, break, byte, case, catch,
cdecl, char, comptime, const, constraint, continue, contract, data, def, default, defer,
deprecate, dict, do, double, effect, elif, else, emitflux, enum, error, escape, export, extern,
false, fastcall, float, for, from, global, goto, has, heap, if, in, inline, int, interface, is,  
jump, label, local, long, macro, namespace, noinit, noreturn, not, object,
operator, or, private, public, register, return, signed, singinit,
stack, stdcall, struct, switch, this, thiscall, throw, trait, true,
try, uint, ulong, union, unsigned, using, vectorcall, void,
volatile, while, xor
```

<a id="compiler-builtins"></a>
# Compiler Built-Ins:
- `typeof()`  
- `sizeof()`  
- `alignof()`  
- `endianof()`  


## The `compiler.` namespace:
- `compiler.io.console.print(byte*)`  
- `compiler.io.console.input()->byte*`  

- `compiler.io.file.readall(path)->byte*`  
- `compiler.io.file.write(path,content,flags)`  

- `compiler.import.stdlib(filename)`
- `compiler.import.local(filename)`
- `compiler.fpm.package(package-name)`

- `compiler.fvm.trace.begin()`
- `compiler.fvm.trace.end()`

- `compiler.fvm.loadlib(lib_name, type)` - `// "kernel32", "dll"`
- `compiler.fvm.dump(path)`


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
XOR = "^|"
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
BITXOR = "`^|"
BITXNOT = "`^|!"
BITXNAND = "`^|!&"
BITXNOR = "`^|!|"
# Assignment
AND_ASSIGN = "&="
OR_ASSIGN = "|="
XOR_ASSIGN = "^|="
BITAND_ASSIGN = "`&="
BITOR_ASSIGN = "`|="
BITNAND_ASSIGN = "`!&="
BITNOR_ASSIGN = "`!|="
BITXOR_ASSIGN = "`^|="
BITXNOT_ASSIGN = "`^|!="
BITXNAND_ASSIGN = "`^|!&="
BITXNOR_ASSIGN = "`^|!|="

# Ternary operators / Null-oriented operators
TERN_ASSIGN = "?="  // Assign if LHS is null
NOT_NULL = "!?"     // unary boolean postfix operator, primary use for pointers `if (px!?) {...};`
NULL_COALESCE = "??"

# Shift
BITSHIFT_LEFT = "<<"
BITSHIFT_RIGHT = ">>"
BITSHIFT_LEFT_ASSIGN = "<<="
BITSHIFT_RIGHT_ASSIGN = ">>="

BITSLICE = "``"

ADDRESS_OF = "@"
ADDRESS_ASSIGN = "@="
ADDRESS_CAST = "(@)"
RANGE = ".."
SCOPE = "::"
QUESTION = "?"
COLON = ":"
TIE = "~"
STRINGIFY = "$"
RETURN_ARROW = "->"
CHAIN_ARROW = "<-"
RECURSE_ARROW = "<~"      // def foo() <~ void;  // Emits musttail, 0 stack growth
NO_MANGLE = "!!"          // prevent the compiler from mangling the function name
FUNCTION_POINTER = "{}*"
DITTO =  #"
```

---

<a id="operator-precedence-and-associativity"></a>
# Operator Precedence and Associativity

Flux's operators bind in the following order, from **loosest** (evaluated last) to **tightest**
(evaluated first):

| Level | Operators | Associativity |
|---|---|---|
| 1 | `=` `+=` `-=` `*=` `/=` `%=` `^=` `&=` `\|=` `^|=` `` `&= `` `` `\|= `` `` `!&= `` `` `!\|= `` `` `^|!= `` `<<=` `>>=` `@=` `?=` | right |
| 2 | `?:` (ternary) | right |
| 3 | `??` (null-coalesce) | right |
| 4 | `or` / `\|\|` | left |
| 5 | `and` / `&&` | left |
| 6 | `xor` / `^|` (logical xor) | left |
| 7 | `` `\| `` `` `!\| `` (bitwise or / nor) | left |
| 8 | `` `^| `` `` `^|!\| `` (bitwise xor / xnor) | left |
| 9 | `` `& `` `` `!& `` (bitwise and / nand) | left |
| 10 | `==` `!=` `is` `in` | left |
| 11 | `<-` (chain arrow) | right |
| 12 | `<` `<=` `>` `>=` | left |
| 13 | `<<` `>>` (shift) | left |
| 14 | `..` (range) | n/a |
| 15 | `+` `-` (additive) | left |
| 16 | user-defined infix operators (`operator`) | left |
| 17 | `*` `/` `%` `^` (multiplicative, **including power**) | left |
| 18 | `(Type)expr` (cast) | right (prefix) |
| 19 | unary `-` `+` `*` (deref) `@` (address-of) `++` `--` `` `! `` `not` `is not` `` `^|! `` `` `^|!& `` `` `^|!\| `` | right (prefix) |
| 20 | postfix `[i]` `[a:b]` `` [a``b] `` `(...)` `.field` `->field` postfix `++`/`--` | left |

A few rules worth calling out individually, since they differ from the C-family languages Flux
otherwise resembles:

- **`^` is the power operator, and it binds at the same precedence as `*`, `/`, and `%`,
  evaluated left to right.** `2 * 3 ^ 2` is `(2 * 3) ^ 2`, not `2 * (3 ^ 2)`. If you want
  exponentiation to bind tighter than multiplication, parenthesize explicitly.
- **Bitwise `` `& ``, `` `\| ``, and `` `^| `` bind tighter than the comparison operators**
  (`==`, `!=`, `<`, `<=`, `>`, `>=`). `a == b `&` c` means `a == (b `&` c)`. This is the opposite
  of C, where bitwise operators are notoriously looser than comparisons - in Flux you do not
  need extra parentheses to get the intuitive reading.
- `xor`/`^|` is a **logical** connective, sitting with `and`/`or` above the bitwise tier. It is
  a different operator from the bitwise `` `^| ``, which lives down with the other bitwise
  operators.
- The range operator `..` wraps an arithmetic expression on each side, so `1 + 2 .. 3 + 4` is
  valid and means `(1+2)..(3+4)`. A range cannot directly be the left or right operand of a
  shift or relational operator without parentheses, since those sit at a looser level than `..`.
- User-defined infix operators (declared with `operator`) always bind tighter than `+`/`-` and
  looser than `*`/`/`/`%`/`^`, and are always left-associative, regardless of what the operator
  symbol "looks like" it should do mathematically. See "Custom infix operators and overloading"
  for how this is enforced and how it differs for overloads of *built-in* operator symbols.
- Casts (`(Type)expr`) bind tighter than every binary operator, including multiplication, and
  chain right to left: `(byte[8])(u64)x` first casts `x` to `u64`, then casts that result to
  `byte[8]`. Each cast in a chain applies to everything written after it.

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