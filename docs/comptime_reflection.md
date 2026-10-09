# `compiler.symbol_table` — Compile-Time Reflection API

`compiler.symbol_table` is a compile-time intrinsic available inside `comptime` blocks. It exposes the compiler's symbol table as queryable Flux structs, allowing programs to inspect their own structure at compile time. All access is zero runtime cost — everything is erased before codegen.

Requires `#import <runtime.fx>` (or `compiler.import.stdlib("runtime.fx")` inside comptime) to bring the struct definitions into scope.

---

## Structs

Defined in `runtime.fx`. Must be in scope before use. Pulled in via `standard.fx`.

```
struct FXC_TYPESYS
{
    byte*  base_type;        // "int", "byte", "float", "struct", "void", etc.
    byte*  custom_typename;  // named type e.g. "MyStruct", empty if primitive
    bool   is_signed;
    bool   is_const;
    bool   is_volatile;
    bool   is_tied;
    bool   is_pointer;
    int    pointer_depth;
    bool   is_array;
    int    array_size;       // 0 if not array or dynamic
    int    bit_width;        // 0 if not explicitly set
    int    alignment;        // 0 if not explicitly set
    int    endianness;       // 1 = big-endian, 0 = little-endian
    byte*  storage_class;    // "stack", "heap", "global", "local", "register", "singinit", or ""
    bool   is_dict;
    byte*  dict_key_type;    // key type as string, empty if not dict
    byte*  dict_value_type;  // value type as string, empty if not dict
};

struct FXC_SYMENTRY
{
    byte*     name;   // unmangled bare name
    byte*     kind;   // "function", "struct", "object", "trait", "interface",
                      // "namespace", "variable", "enum", "union",
                      // "effect", "constraint", "contract"
    FXC_TYPESYS type; // type info: return type for functions, declared type for variables,
                      // zeroed for kinds with no single type (struct, trait, etc.)
    byte*     ns;     // fully qualified namespace path, empty if top-level
};

struct FXC_SYMTABLE
{
    int          entries;
    FXC_SYMENTRY* entry;
};

struct FXC_PARAM
{
    byte*      name;
    FXC_TYPESYS type;
};

struct FXC_FUNCINFO
{
    int         param_count;
    FXC_PARAM*  params;
    FXC_TYPESYS return_type;
    byte*       calling_conv;    // "fastcall", "cdecl", etc. Empty = default (fastcall)
    bool        is_variadic;
    bool        is_recursive;
    bool        is_inline;
    bool        no_mangle;
    bool        has_effect;      // true if any overload has a # effect {} annotation
    bool        has_attenuate;   // true if any overload has a # attenuate {} annotation
    int         pre_contracts;   // count of pre-contracts on first overload
    int         post_contracts;  // count of post-contracts on first overload
};
```

---

## Access forms

### `compiler.symbol_table`

Returns an `FXC_SYMTABLE` containing all entries in the symbol table at the point the `comptime` block executes.

```
FXC_SYMTABLE st = compiler.symbol_table;
```

### `compiler.symbol_table.<kind>`

Returns an `FXC_SYMTABLE` filtered to a specific kind. Valid filters:

| Access | Kind string in entries |
|---|---|
| `compiler.symbol_table.functions` | `"function"` |
| `compiler.symbol_table.structs` | `"struct"` |
| `compiler.symbol_table.objects` | `"object"` |
| `compiler.symbol_table.traits` | `"trait"` |
| `compiler.symbol_table.interfaces` | `"interface"` |
| `compiler.symbol_table.namespaces` | `"namespace"` |
| `compiler.symbol_table.variables` | `"variable"` |
| `compiler.symbol_table.enums` | `"enum"` |
| `compiler.symbol_table.unions` | `"union"` |
| `compiler.symbol_table.effects` | `"effect"` |
| `compiler.symbol_table.constraints` | `"constraint"` |
| `compiler.symbol_table.contracts` | `"contract"` |

```
FXC_SYMTABLE fns = compiler.symbol_table.functions;
```

### `compiler.symbol_table.lookup(name)`

Returns the first `FXC_SYMENTRY` matching the given name. Accepts a bare name or a fully qualified namespace path.

Returns a zeroed `FXC_SYMENTRY` (all fields empty strings, `kind == ""`) if not found.

```
FXC_SYMENTRY e = compiler.symbol_table.lookup("Point");
FXC_SYMENTRY e2 = compiler.symbol_table.lookup("standard::io::console::print");

if (e.kind == "")
{
    compiler.io.console.print("not found\n");
};
```

### `compiler.symbol_table.funcinfo(name)`

Returns an `FXC_FUNCINFO` for the named function. Accepts bare or qualified name. When a function has multiple overloads, boolean flags (`has_effect`, `has_attenuate`, `is_variadic`, etc.) are OR'd across all overloads. Parameter info comes from the first overload.

Returns a zeroed `FXC_FUNCINFO` (all zero/false/empty) if the name is not found or is not a function.

```
FXC_FUNCINFO fi = compiler.symbol_table.funcinfo("f");
FXC_FUNCINFO fi2 = compiler.symbol_table.funcinfo(e.name);
```

---

## Snapshot timing

The symbol table is snapshotted at the point the `comptime` block begins executing. It reflects the state of the program as parsed up to that point — including all `#import`ed files. Definitions that appear after the `comptime` block in source order are not visible to it.

---

## Examples

### Enumerate all functions

```
#import <standard.fx>;

using standard::io::console;

comptime
{
    FXC_SYMTABLE st = compiler.symbol_table.functions;
    int i;
    while (i < st.entries)
    {
        FXC_SYMENTRY e = st.entry[i];
        println(f"{e.name} -> {e.type.base_type}");
        i++;
    };
};
```

### Find all functions with effect annotations

```
comptime
{
    FXC_SYMTABLE st = compiler.symbol_table.functions;
    int i;
    while (i < st.entries)
    {
        FXC_SYMENTRY e = st.entry[i];
        FXC_FUNCINFO fi = compiler.symbol_table.funcinfo(e.name);
        compiler.io.console.print(f"{e.name} has effect: {fi.has_effect}\n") if (fi.has_effect);
        i++;
    };
};
```

### Look up a specific type

```
comptime
{
    FXC_SYMENTRY e = compiler.symbol_table.lookup("MyStruct");
    if (e.kind == "struct")
    {
        compiler.io.console.print(f"Found: {e.name} in {e.ns}\n");
    };
};
```

### Inspect function parameters

```
comptime
{
    FXC_FUNCINFO fi = compiler.symbol_table.funcinfo("f");
    compiler.io.console.print(f"f has {fi.param_count} params\n");
    int i;
    while (i < fi.param_count)
    {
        FXC_PARAM p = fi.params[i];
        compiler.io.console.print(f"  {p.name} : {p.type.base_type}\n");
        i++;
    };
};
```

### Qualified name lookup

```
comptime
{
    FXC_SYMENTRY e = compiler.symbol_table.lookup("standard::io::console::println");
    FXC_FUNCINFO fi = compiler.symbol_table.funcinfo("standard::io::console::println");
    compiler.io.console.print(f"println has_effect: {fi.has_effect}\n");
};
```

---

# `compiler.target` — Compile-Time Target Information

`compiler.target` exposes platform and hardware information at compile time inside `comptime` blocks. All properties are resolved when the comptime block executes. Zero runtime cost.

---

## Properties

### Platform

| Property | Type | Description |
|---|---|---|
| `compiler.target.arch` | `byte*` | CPU architecture: `"x86_64"`, `"arm64"`, `"x86"`, etc. |
| `compiler.target.os` | `byte*` | Operating system: `"windows"`, `"linux"`, `"macos"`, `"freestanding"` |
| `compiler.target.abi` | `byte*` | ABI: `"msvc"`, `"gnu"`, `"musl"` |
| `compiler.target.ptr_width` | `int` | Pointer width in bits: `64` or `32` |
| `compiler.target.endian` | `byte*` | Byte order: `"little"` or `"big"` |

### Memory

| Property | Type | Description |
|---|---|---|
| `compiler.target.cache_line` | `int` | CPU cache line size in bytes |
| `compiler.target.page_size` | `int` | Memory page size in bytes |

### x86/x86_64 instruction sets

| Property | Type | Description |
|---|---|---|
| `compiler.target.has_sse` | `bool` | SSE support |
| `compiler.target.has_sse2` | `bool` | SSE2 support |
| `compiler.target.has_sse4` | `bool` | SSE4.1 support |
| `compiler.target.has_avx` | `bool` | AVX support |
| `compiler.target.has_avx2` | `bool` | AVX2 support |
| `compiler.target.has_avx512` | `bool` | AVX-512 support |
| `compiler.target.has_aes` | `bool` | AES-NI support |
| `compiler.target.has_popcnt` | `bool` | POPCNT support |
| `compiler.target.has_bmi2` | `bool` | BMI2 support |

All `has_*` flags return `false` on non-x86 targets.

---

## Examples

### Basic platform detection

```
comptime
{
    compiler.io.console.print(f"arch:      {compiler.target.arch}\n");
    compiler.io.console.print(f"os:        {compiler.target.os}\n");
    compiler.io.console.print(f"ptr_width: {compiler.target.ptr_width}\n");
    compiler.io.console.print(f"endian:    {compiler.target.endian}\n");
};
```

### Generate target-specific code

```
comptime
{
    if (compiler.target.has_avx2)
    {
        emitflux
        {
            def dot_product(float* a, float* b, int n) -> float
            {
                // AVX2 vectorized implementation
            };
        };
    }
    else
    {
        emitflux
        {
            def dot_product(float* a, float* b, int n) -> float
            {
                // scalar fallback
            };
        };
    };
};
```

### Cache-aligned struct generation

```
comptime
{
    int cl = compiler.target.cache_line;
    compiler.io.console.print(f"Generating {cl}-byte aligned structs\n");
};
```

### Combined with symbol table

```
comptime
{
    compiler.io.console.print(f"Building for {compiler.target.arch} / {compiler.target.os}\n");
    FXC_SYMTABLE st = compiler.symbol_table.structs;
    compiler.io.console.print(f"{st.entries} structs defined\n");
};
```