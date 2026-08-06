<h1 align="center">Flux</h1>

<h2 align="center"><i>A compiled systems language that stays out of your way.</i></h2>

<p align="center">
    <img width="512" height="512" alt="Flux Logo" src="https://github.com/user-attachments/assets/58da57a7-1924-48a2-ba29-c2040d9343eb" />
</p>

<p align="center">
  <a href="https://discord.gg/wVAm2E6ymf">Discord</a> ·
  <a href="https://fluxspl.org/ide">Online Compiler</a> ·
  <a href="docs/Specs/language_specification.md">Language Specification</a> ·
  <a href="docs/learn_flux_intro.md">Getting Started</a>
</p>

---

Flux is a compiled, statically typed systems programming language. It has the performance of C and a type system that goes further than C in every direction that matters: arbitrary-width integers with alignment and endianness baked into the type, first-class bit manipulation, opt-in ownership and a totally optional borrow checker, compile-time code generation with `emitflux`, contracts, templates with type geometry constraints, and inline FVM assembly in comptime blocks.

It is not a C derivative. It is not a safe language in the Rust sense. It is a high-trust language that gives you sharp tools and expects you to use them correctly.

---

## What it looks like

### 16 lines of C becomes 2 lines of Flux

This is real cryptography code. The C version is a manual byte-by-byte extraction loop. The Flux version is a direct consequence of how the type system works.

**C:**
```c
len_block[0]  = (byte)((aad_bits >> 56) & 0xFF);
len_block[1]  = (byte)((aad_bits >> 48) & 0xFF);
len_block[2]  = (byte)((aad_bits >> 40) & 0xFF);
len_block[3]  = (byte)((aad_bits >> 32) & 0xFF);
len_block[4]  = (byte)((aad_bits >> 24) & 0xFF);
len_block[5]  = (byte)((aad_bits >> 16) & 0xFF);
len_block[6]  = (byte)((aad_bits >>  8) & 0xFF);
len_block[7]  = (byte)( aad_bits        & 0xFF);
len_block[8]  = (byte)((cipher_bits >> 56) & 0xFF);
// ... 8 more identical lines
```

**Flux:**
```
len_block[0..7]  = (byte[8])(u64)aad_bits;
len_block[8..15] = (byte[8])(u64)cipher_bits;
```

Casting an integer to a fixed-size byte array packs the bytes big-endian into the array. No masking. No shifting. No loop. The type system does the work.

---

### SHA-256 finalisation loop

**C:**
```c
for (i = 0; i < 4; i++) {
    hash[i]      = (byte)((ctx.state[0] >> (24 - i * 8)) & 0xFF);
    hash[i + 4]  = (byte)((ctx.state[1] >> (24 - i * 8)) & 0xFF);
    hash[i + 8]  = (byte)((ctx.state[2] >> (24 - i * 8)) & 0xFF);
    hash[i + 12] = (byte)((ctx.state[3] >> (24 - i * 8)) & 0xFF);
    // ... 4 more identical lines
}
```

**Flux:**
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

`be32` is a first-class big-endian 32-bit type. Casting to `byte[4]` unpacks it into four bytes in the correct order. No `htonl`. No manual shift arithmetic.

---

### Zero-copy packet parsing

```
struct Packet
{
    data{8}  type;
    data{16} length;
    data{32} timestamp;
    data{32} checksum;
};

def parse(byte* buf) -> void
{
    Packet pkt from buf;   // Reinterpret buf's bytes as a Packet in place. buf is consumed.

    println(f"Type:      {int(pkt.type)}");
    println(f"Length:    {pkt.length}");
    println(f"Timestamp: {pkt.timestamp}");
};
```

`from` recasts a byte buffer into a struct without copying. The layout is exact - struct fields are tightly packed with no hidden padding. What you declare is what you get in memory.

---

### Arbitrary-width integer types

```
signed   data{13:16} as strange13;   // 13-bit signed, 16-bit aligned
unsigned data{3}     as tiny;        // 3-bit unsigned (0-7)
unsigned data{7:8}   as aligned7;    // 7-bit with 8-bit alignment
unsigned data{5}[10] as 5b_array;    // Array of ten 5-bit values

data{16}    as be16;   // Big-endian 16-bit  (default)
data{16::0} as le16;   // Little-endian 16-bit

// Assigning between endian types emits a byte swap automatically
le16 host   = (be16)network_value;
```

Width, alignment, and endianness are part of the type. You are not masking bits out of a `uint32_t`. You are working with the type you actually have.

---

### Bit slices

```
u32 packed = 0x12345678;

u32 low_nibble  = packed[28``31];   // bits 28-31: 0x8
u32 high_byte   = packed[0``7];     // bits 0-7:   0x12

packed[24``31] = 0xFF;              // Replace bits 24-31 in place
// packed == 0x123456FF

// Reverse the bits of a byte
byte x = 55;
x[0``7] = x[7``0];
println(int(x));   // 236

// Bit slices cross struct field boundaries
struct Pair { int a, b; };
data{4} as u4;
Pair p   = {5, 10};
u4   val = p[60``63];   // 10, because 0b1010 - spans into the second field
```

Bit 0 is always the most significant bit. Slices that cross struct field boundaries work naturally because struct fields have no hidden padding. Reversing start and end indices reverses the bit order of the result.

---

### Compile-time code generation with `emitflux`

Flux has a compile-time executor - the FVM - that runs Flux code at compile time. `emitflux` blocks inject real Flux definitions into the compilation unit, in order, from within comptime logic. This is how you generate code programmatically without a macro preprocessor.

```
enum State { Idle, Running, Paused, Stopped };

comptime
{
    int[] trans_from = [0, 1, 2, 1];
    int[] trans_to   = [1, 2, 1, 3];
    int   tcount     = 4;

    emitflux
    {
        def state_name(int s) -> byte*
        {
            if (s == 0) { return "Idle"; };
            if (s == 1) { return "Running"; };
            if (s == 2) { return "Paused"; };
            if (s == 3) { return "Stopped"; };
            return "Unknown";
        };
    };

    for (int tidx = 0; tidx < tcount; tidx++)
    {
        emitflux
        {
            def ~$i"can_trans_{}_{}":{trans_from[tidx];trans_to[tidx];}() -> bool { return true; };
        };
    };

    emitflux
    {
        def transition(int fx, int to) -> int
        {
            if (fx == 0 & to == 1 & can_trans_0_1()) { return to; };
            if (fx == 1 & to == 2 & can_trans_1_2()) { return to; };
            if (fx == 2 & to == 1 & can_trans_2_1()) { return to; };
            if (fx == 1 & to == 3 & can_trans_1_3()) { return to; };
            println(f"Invalid: {fx}:{state_name(fx)} -> {to}:{state_name(to)}");
            return fx;
        };
    };
};
```

The comptime loop runs four times. Each iteration emits a `can_trans_X_Y()` function with a name built from the transition data using `~$` (codification) and i-strings. By the time `transition()` is emitted, all four predicates exist. Adding a new valid transition is one line in the data array.

You can also drop into raw FVM assembly inside a comptime block and modify comptime-scope variables directly:

```
comptime
{
    int x = 5;

    fluxvm
    {
        LOCAL_GET x
        PUSH 10
        ADD
        LOCAL_SET x
    };

    compiler.io.console.print(f"x is now {x}\n");   // Prints: x is now 15
};
```

Named comptime blocks are goto targets, letting you build arbitrary comptime control flow including loops:

```
comptime A
{
    // per-iteration setup
    goto B;
};

comptime B
{
    // more work
    if (condition) { goto A; };   // Loop back to A
};
```

---

### Contracts

```
contract NonZero(a, b)
{
    assert(a != 0, "a must be nonzero");
    assert(b != 0, "b must be nonzero");
};

def divide(int a, int b) -> int : NonZero(a, b)
{
    return a / b;
};

operator (int L, BigInt R) [+] -> BigInt : NonZero(L, R)
{
    // Contracts apply to operators too
};
```

Contracts are pre- and post-condition blocks attached to functions and operators as part of their specification, not their implementation. They are distinct from the function body and transform into assertions at the call boundary. Contracts can contain any statement that can go inside of a function definition, not just assertions.

---

### Templates with type geometry constraints

```
constraint NoNarrowing(A)
{
    A !`< A    // A must never be narrowed anywhere in this template body
};

def serialize<T: int, :{NoNarrowing}>(T x) -> byte
{
    return 5 + x;   // Compile error: narrowing T to byte violates NoNarrowing
};
```
The constraint operator:
```
!`<
```
is not a predicate on a concrete type. The compiler walks the instantiated function body and finds the actual narrowing. Template constraints express relationships between types, not just properties of a single type.

---

### Opt-in ownership

```
def consume(~int z) -> void {};   // Takes a tied parameter

def main() -> int
{
    ~int x;   // Tied variable

    consume(~x);   // Transfer ownership into consume
    consume(~x);   // Compile error: x has already been untied

    return 0;
};
```

Ownership in Flux is opt-in per type. Apply it where you need a move semantic. The rest of your program has no borrow checker.

---

### Inline assembly with architecture guards

```
def exchange64(i64* ptr, i64 value, i64* out) -> void
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
    .retry:
        ldaxr x0, [$0]
        stlxr w3, x1, [$0]
        cbnz  w3, .retry
        str   x0, [$2]
    } : : "r"(ptr), "r"(value), "r"(out) : "x0", "w3", "memory";
    #endif;
};
```

---

### Custom infix operators

```
// Define a new operator
operator (int L, int R) [+++] -> int
{
    return ++L + ++R;
};

int result = a +++ b;

// Identifier-based operators work too
operator (int L, int R) [NOPOR] -> bool
{
    return !L | !R;
};

bool check = a NOPOR b;
```

---

### Raw bytecode functions

```
byte[] some_bytecode = [0x48, 0x31, 0xC0, 0xC3];  // xor rax,rax ; ret
def{}* fp()->void = @some_bytecode;
fp();
```

---

## What Flux is not

- **Not a Rust alternative.** Rust's borrow checker is global and mandatory. Flux ownership is opt-in per type. If you want the compiler to enforce memory safety everywhere, use Rust.
- **Not a Python-syntax language.** The readme description "C performance with Python readability" means the language is clean, not that it looks like Python. It is a C-family language.
- **Not garbage collected.** Everything is stack allocated by default. Heap allocation is explicit with `heap`. Cleanup is explicit with `(void)ptr` or `defer`.
- **Not FluxCD.** Not the FLUX image generation models. Not the Flux application architecture pattern. This is a compiled systems programming language.

---

## Design principles

- Everything is stack allocated unless you write `heap`
- Everything is zero-initialized on declaration unless you specify otherwise
- Struct fields have no hidden padding - layout is exactly what you declare
- The compiler does not add safety overhead you did not ask for
- Endianness, alignment, and bit width are type properties, not runtime concerns
- Explicit is better than implicit

---

## Current status

The syntax and grammar are stable and will not change. The compiler works. Real programs run. The standard library is the current focus of development.

**What exists:**
- Full compiler (LLVM backend)
- Language Server Protocol (LSP)
- Package Manager (FPM)
- [Online Compiler / IDE](https://fluxspl.org/ide)
- [Language Specification](docs/Specs/language_specification.md)
- [Beginner Tutorial](docs/learn_flux_intro.md) and [Adept Tutorial](docs/learn_flux_adept.md)
- Style Guide, Keyword Reference
- Windows, Linux, and macOS setup guides
- C->Flux translation utility

**In progress:**
- Standard library expansion
- Build tooling
- IDE

---

## Requirements

- Python 3.12+
- LLVM 21+

---

## Get involved

- **Discord:** [discord.gg/wVAm2E6ymf](https://discord.gg/wVAm2E6ymf)
- **Online IDE:** [fluxspl.org/ide](https://fluxspl.org/ide)
- **GitHub:** [github.com/kvthweatt/FluxLang](https://github.com/kvthweatt/FluxLang)

---

## Star History

[![Star History Chart](https://star-history.dera.page/svg?repos=kvthweatt/Flux&type=date&legend=top-left)](https://star-history.dera.page/#kvthweatt/Flux&type=date&legend=top-left)

---

*Copyright (C) 2024 Karac Von Thweatt. All rights reserved.*
