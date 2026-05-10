# Flux Standard Library Documentation

Version: 1.1
Date: March 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Library Structure](#library-structure)
3. [Core Modules](#core-modules)
   - [standard.fx](#standardfx)
   - [types.fx](#typesfx)
   - [sys.fx](#sysfx)
   - [io.fx](#iofx)
   - [math.fx](#mathfx)
4. [Runtime System](#runtime-system)
   - [runtime.fx](#runtimefx)
   - [memory.fx](#memoryfx)
   - [allocators.fx](#allocatorsfx)
   - [ffifio.fx](#ffifiofx)
5. [String Utilities](#string-utilities)
   - [string_utilities.fx](#string_utilitiesfx)
   - [string_object_raw.fx](#string_object_rawfx)
6. [Collections Library](#collections-library)
   - [collections.fx](#collectionsfx)
7. [Vectors Library](#vectors-library)
   - [vectors.fx](#vectorsfx)
8. [Extended Libraries](#extended-libraries)
   - [atomics.fx](#atomicsfx)
   - [threading.fx](#threadingfx)
   - [timing.fx](#timingfx)
   - [random.fx](#randomfx)
   - [cryptography.fx](#cryptographyfx)
   - [bigint.fx](#bigintfx)
   - [decimal.fx](#decimalfx)
   - [net_windows.fx](#net_windowsfx)
   - [uuid.fx](#uuidfx)
   - [sharedmemory.fx](#sharedmemoryfx)
   - [format.fx](#formatfx)
   - [console.fx](#consolefx)
   - [graphing.fx](#graphingfx)
   - [opengl.fx](#openglfx)
   - [windows.fx](#windowsfx)
   - [detour.fx](#detourfx)
   - [operators.fx](#operatorsfx)
9. [Import Guidelines](#import-guidelines)
10. [Platform Support](#platform-support)

---

## Overview

The Flux Standard Library provides a comprehensive set of tools and utilities for systems programming, designed to work across Windows, Linux, and macOS platforms.

### Design Philosophy

- **Cross-platform compatibility**: Supports Windows, Linux, and macOS through conditional compilation
- **Low-level control**: Direct access to system calls and memory management
- **Type safety**: Comprehensive type system with platform-specific definitions
- **Minimal dependencies**: Core functionality with optional FFI support
- **Performance-oriented**: Assembly-level optimizations where needed

---

## Library Structure

```
stdlib/
  `----/ standard.fx              # Main entry point
  `----/runtime/runtime.fx        # Runtime initialization and entry point
  `----/ types.fx                 # Type definitions and utilities
  `----/ sys.fx                   # OS detection
  `----/ io.fx                    # Input/output operations
  `----/ math.fx                  # Mathematical functions
  `----/runtime/memory.fx         # Memory management
  `----/runtime/allocators.fx     # Custom heap allocator (fmalloc/ffree)
  `----/runtime/ffifio.fx         # FFI-based file I/O (C runtime)
  `----/ string_utilities.fx      # String manipulation functions
  `----/ string_object_raw.fx     # String object implementation
  `----/ file_object_raw.fx       # File object implementation
  `----/ socket_object_raw.fx     # Socket object implementation
  `----/ collections.fx           # Dynamic data structures
  `----/ vectors.fx               # 3D/4D vector mathematics
  `----/runtime/atomics.fx        # Atomic operations
  `----/runtime/threading.fx      # Threads, mutexes, condition variables
  `----/runtime/timing.fx         # High-resolution timers
  `----/ random.fx                # Random number generation
  `----/ cryptography.fx          # SHA-256, MD5, AES
  `----/ bigint.fx                # Arbitrary-precision integers
  `----/ decimal.fx               # Arbitrary-precision decimals
  `----/ net_windows.fx           # TCP/UDP networking (Windows)
  `----/ uuid.fx                  # UUID generation (v1, v4, v7)
  `----/runtime/sharedmemory.fx   # Named shared memory regions
  `----/ format.fx                # ANSI color and text formatting
  `----/ console.fx               # TUI cursor and color control
  `----/ graphing.fx              # 2D/3D ASCII graphing
  `----/ opengl.fx                # OpenGL context and rendering helpers
  `----/ windows.fx               # Win32 window and GDI wrapper
  `----/ detour.fx                # x86-64 inline hook / detour
  `----/ operators.fx             # Extended operator utilities
```

---

## Core Modules

### standard.fx

**Purpose**: Main entry point for the Flux Standard Library

**Usage**:
```flux
#import "standard.fx";
```

**Description**:  
The `standard.fx` file serves as the primary import point for applications using the Flux Standard Library. It defines preprocessor guards and unconditionally imports `runtime.fx`, which pulls in the full runtime chain.

**Features**:
- Defines `FLUX_STANDARD` preprocessor constant
- Imports `runtime.fx` (which in turn imports `types.fx`, `memory.fx`, `allocators.fx`, `sys.fx`, `io.fx`, `ffifio.fx`, and the raw builtins)
- Provides the stable import surface for all Flux programs

---

### types.fx

**Purpose**: Comprehensive type system definitions and utilities

**Namespace**: `standard::types`

**Guard macro**: `FLUX_STANDARD_TYPES`

#### Type Definitions

##### Primitive Types

| Type Alias | Definition | Description |
|------------|------------|-------------|
| `nybble` | `unsigned data{4}` | 4-bit unsigned integer |
| `noopstr` | `byte[]` | Null-terminated byte string |
| `u16` | `unsigned data{16}` | 16-bit unsigned integer |
| `u32` | `unsigned data{32}` | 32-bit unsigned integer |
| `u64` | `unsigned data{64}` | 64-bit unsigned integer |
| `i8` | `signed data{8}` | 8-bit signed integer |
| `i16` | `signed data{16}` | 16-bit signed integer |
| `i32` | `signed data{32}` | 32-bit signed integer |
| `i64` | `signed data{64}` | 64-bit signed integer |

##### Pointer Types

| Type | Definition | Description |
|------|------------|-------------|
| `byte_ptr` | `byte*` | Pointer to byte |
| `i32_ptr` | `i32*` | Pointer to 32-bit signed integer |
| `i64_ptr` | `i64*` | Pointer to 64-bit signed integer |
| `void_ptr` | `void*` | Generic pointer |
| `noopstr_ptr` | `noopstr*` | Pointer to string |

##### Platform-Specific Types

**x86_64 and ARM64**:
```flux
intptr    // i64* - Pointer-sized signed integer
uintptr   // u64* - Pointer-sized unsigned integer
ssize_t   // i64  - Signed size type
size_t    // u64  - Unsigned size type
```

**x86 (32-bit)**:
```flux
intptr    // i32* - Pointer-sized signed integer
uintptr   // u32* - Pointer-sized unsigned integer
ssize_t   // i32  - Signed size type
size_t    // u32  - Unsigned size type
```

**Windows-Specific**:
```flux
wchar     // i16  - Wide character (UTF-16)
```

##### Network/Endian Types

**Big-Endian (Network Byte Order)**:
```flux
be16  // unsigned data{16::1}
be32  // unsigned data{32::1}
be64  // unsigned data{64::1}
```

**Little-Endian (Host Byte Order)**:
```flux
le16  // unsigned data{16::0}
le32  // unsigned data{32::0}
le64  // unsigned data{64::0}
```

#### Utility Functions

##### Byte Swapping

```flux
def bswap16(u16 value) -> u16
def bswap32(u32 value) -> u32
def bswap64(u64 value) -> u64
```

Swap byte order for endianness conversion.

**Example**:
```flux
u16 net_value = bswap16(0x1234);  // 0x3412
```

##### Network/Host Conversion

**Deprecated** - these wrappers remain present but are superseded by `net_windows.fx` helpers.

```flux
def ntoh16(be16 net_value) -> le16
def ntoh32(be32 net_value) -> le32
def hton16(le16 host_value) -> be16
def hton32(le32 host_value) -> be32
```

##### Bit Manipulation

```flux
def bit_test(u32 value, u32 bit) -> bool    // Test if bit is set
```

**Example**:
```flux
u32 flags = 0b00001000;
bool is_set = bit_test(flags, 3);  // true
```

##### Alignment Utilities

```flux
def align_up(u64 value, u64 alignment) -> u64
def align_down(u64 value, u64 alignment) -> u64
def is_aligned(u64 value, u64 alignment) -> bool
```

**Example**:
```flux
u64 aligned = align_up(137, 16);  // 144
bool check = is_aligned(144, 16);  // true
```

---

### sys.fx

**Purpose**: OS detection and platform constants

**Namespace**: `standard::system`

**Guard macro**: `FLUX_STANDARD_SYSTEM`

**Description**:  
Sets the `CURRENT_OS` preprocessor constant at compile time and provides Win32 FFI declarations needed by the runtime. Automatically imported by `runtime.fx`.

#### Platform Constants

```flux
CURRENT_OS  // Set at compile time
  1 = Windows
  2 = Linux
  3 = macOS
```

**Example**:
```flux
switch (CURRENT_OS)
{
    case (1) { print("Running on Windows\0"); }
    case (2) { print("Running on Linux\0"); }
    case (3) { print("Running on macOS\0"); }
};
```

---

### io.fx

**Purpose**: Cross-platform input/output operations

**Namespace**: `standard::io`

**Guard macro**: `FLUX_STANDARD_IO`

**Sub-namespaces**:
- `standard::io::console` - Console I/O operations
- `standard::io::file` - File I/O operations

#### Console I/O

##### Input Functions

```flux
def input(byte[] buffer, int max_len) -> int
```

Read user input from console. Platform-agnostic wrapper that calls the appropriate platform-specific implementation.

**Parameters**:
- `buffer`: Byte array to store input
- `max_len`: Maximum number of bytes to read

**Returns**: Number of bytes read (excluding null terminator)

**Platform Implementations**:
- Windows: `win_input()` - Uses Windows API (ReadFile)
- Linux: `nix_input()` - Uses Linux syscalls
- macOS: `mac_input()` - Uses macOS syscalls

##### Output Functions

```flux
def print(noopstr s, int len) -> void
def print(noopstr s) -> void
def print(byte s) -> void
```

Print to console output.

**Overloads**:
- `print(noopstr s, int len)`: Print string with explicit length
- `print(noopstr s)`: Print null-terminated string
- `print(byte s)`: Print single character

**Example**:
```flux
print("Hello, World!\0\0");
print('A');  // Print single character
```

**Platform Implementations**:
- Windows: `win_print()` - Uses Windows API (WriteFile)
- Linux: `nix_print()` - Uses Linux syscalls (write)
- macOS: `mac_print()` - Uses macOS syscalls

#### File I/O (Native Implementation)

The file I/O system provides both native syscall-based and FFI-based implementations.

##### Windows File I/O

**Constants**:
```flux
GENERIC_READ          = 0x80000000
GENERIC_WRITE         = 0x40000000
GENERIC_READ_WRITE    = 0xC0000000
FILE_SHARE_READ       = 0x00000001
FILE_SHARE_WRITE      = 0x00000002
CREATE_NEW            = 1
CREATE_ALWAYS         = 2
OPEN_EXISTING         = 3
OPEN_ALWAYS           = 4
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE  = -1
```

**Core Functions**:

```flux
def win_open(byte* path, i32 access, i32 share, i32 create, i32 flags) -> i64
def win_read(i64 handle, byte* buffer, u32 bytes_to_read, u32* bytes_read) -> i32
def win_write(i64 handle, byte* buffer, u32 bytes_to_write, u32* bytes_written) -> i32
def win_close(i64 handle) -> i32
```

**Helper Functions**:

```flux
def open_read(byte* path) -> i64
def open_write(byte* path) -> i64
def open_append(byte* path) -> i64
def open_read_write(byte* path) -> i64
```

##### Linux File I/O

**System Call Numbers**:
```flux
SYS_OPEN  = 2
SYS_READ  = 0
SYS_WRITE = 1
SYS_CLOSE = 3
SYS_EXIT  = 60
```

**Open Flags**:
```flux
O_RDONLY = 0x0000
O_WRONLY = 0x0001
O_RDWR   = 0x0002
O_CREAT  = 0x0040
O_TRUNC  = 0x0200
O_APPEND = 0x0400
```

**Permission Modes**:
```flux
S_IRUSR = 0x0400  // User read
S_IWUSR = 0x0200  // User write
S_IXUSR = 0x0100  // User execute
S_IRGRP = 0x0040  // Group read
S_IWGRP = 0x0020  // Group write
S_IXGRP = 0x0010  // Group execute
S_IROTH = 0x0004  // Others read
S_IWOTH = 0x0002  // Others write
S_IXOTH = 0x0001  // Others execute
DEFAULT_PERM = S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH
```

**Core Functions**:

```flux
open(byte* path, i32 flags, i32 mode) -> i64
read(i64 fd, byte* buffer, u64 count) -> i64
write(i64 fd, byte* buffer, u64 count) -> i64
close(i64 fd) -> i32
```

**Helper Functions**:

```flux
open_read(byte* path) -> i64
open_write(byte* path) -> i64
open_append(byte* path) -> i64
open_read_write(byte* path) -> i64
read32(i64 fd, byte* buffer, u32 count) -> i32
write32(i64 fd, byte* buffer, u32 count) -> i32
```

**Example Usage**:
```flux
#import "standard.fx";

def main() -> int
{
    i64 fd = open_write("output.txt\0");
    if (fd == INVALID_FD)
    {
        print("Failed to open file\0");
        return 1;
    };
    
    byte[] data = "Hello, File!\0";
    i64 written = write(fd, @data[0], 13);
    
    close(fd);
    return 0;
};
```

---

### math.fx

**Purpose**: Comprehensive mathematical functions with type overloading

**Namespace**: `standard::math`

**Guard macro**: `FLUX_STANDARD_MATH`

#### Mathematical Constants

```flux
// Integer approximations
PI8, PI16, PI32, PI64 = 3
E8, E16, E32, E64 = 2

// Floating-point constants
PIF = 3.14159265358979323846
EF  = 2.71828182845904523536
```

#### Core Mathematical Functions

All functions are overloaded for types: `i8`, `i16`, `i32`, `i64`, `float`

##### Absolute Value

```flux
def abs(T x) -> T  // T {i8, i16, i32, i64, float}
```

##### Minimum and Maximum

```flux
def min(T a, T b) -> T
def max(T a, T b) -> T
```

##### Clamp

```flux
def clamp(T value, T low, T high) -> T
```

Constrains `value` to be within [`low`, `high`].

##### Square Root

```flux
def sqrt(T x) -> T
```

Uses Newton's method. Integer versions use integer arithmetic; float version uses iterative refinement.

##### Factorial

```flux
def factorial(T n) -> T  // T {i8, i16, i32, i64}
```

##### GCD / LCM

```flux
def gcd(T a, T b) -> T
def lcm(T a, T b) -> T
```

##### Power

```flux
def pow(T base, T exp) -> T  // T {i8, i16, i32, i64, float}
```

Integer versions use repeated multiplication. Float version supports fractional exponents via exp/log.

#### Trigonometric Functions

```flux
def sin(float x) -> float
def cos(float x) -> float
def tan(float x) -> float
```

Input in radians. Implemented via Taylor series.

#### Logarithmic Functions

```flux
def log(float x) -> float    // Natural logarithm
def log10(float x) -> float  // Base-10 logarithm
```

#### Additional Utilities

```flux
def lerp(T a, T b, float t) -> T         // Linear interpolation
def sign(T x) -> T                        // -1, 0, or 1
def popcount(T x) -> T                    // Count set bits
def reverse_bits(T x) -> T               // Reverse bit order
```

---

## Runtime System

### runtime.fx

**Purpose**: Runtime initialization and program entry point management

**Description**:  
Manages the full startup chain for Flux programs. Imports `types.fx`, `memory.fx`, `sys.fx`, `io.fx`, `ffifio.fx`, and the raw builtins. Defines `STDLIB_GVP`, `NULL`, `U64MAXVAL`, and the `FRTStartup` entry point.

#### Global Constants

```flux
const void* STDLIB_GVP  // Standard global void pointer (null sentinel)
#def NULL STDLIB_GVP    // Alias for STDLIB_GVP
const data{64} U64MAXVAL = 0xFFFFFFFFFFFFFFFFu
```

`STDLIB_GVP` / `NULL` are provided so null checks do not momentarily allocate an integer zero on the stack.

#### Entry Points

**User-Defined Main Functions**:
```flux
def main() -> int
def main(int* argc, byte** argv) -> int
```

**Runtime Entry Point** (do not redefine):
```flux
def FRTStartup() -> int
```

`FRTStartup()` is the actual entry point called by the OS. It handles:
1. Platform detection
2. Standard heap allocator initialization (`stdheap::table_init()`)
3. Command-line argument extraction (Windows)
4. Calling the user's `main()` function
5. Process cleanup

**Linux Entry**:
```flux
def _start() -> void  // Calls FRTStartup()
```

#### Exit Functions

```flux
def exit(int code) -> void   // Platform-native process exit
def abort() -> void          // Abnormal process termination
def atexit(void* fn) -> int  // Register exit callback (stub on Linux/macOS)
```

**Example**:
```flux
#import "standard.fx";

def main(int* argc, byte** argv) -> int
{
    print("Arguments:\0");
    for (int i = 0; i < *argc; i++)
    {
        print(argv[i]);
        print("\n\0");
    };
    return 0;
};
```

---

### memory.fx

**Purpose**: Memory management - native implementations and C runtime FFI

**Namespace**: `standard::memory`

**Guard macro**: `FLUX_STANDARD_MEMORY`

**Description**:  
Provides both platform-native implementations of `malloc`/`free`/`calloc`/`realloc` (using `mmap`/`munmap` on Linux and macOS, C FFI on Windows) and a `standard::memory` namespace with higher-level utilities. Also exposes Win32 virtual memory functions.

#### Low-Level Allocation (C-compatible ABI)

```flux
def malloc(size_t size) -> void*
def free(void* ptr) -> void
def calloc(size_t count, size_t size) -> void*
def realloc(void* ptr, size_t new_size) -> void*
```

On Windows these are C runtime FFI declarations. On Linux and macOS they are native implementations backed by `mmap`/`munmap` with an 8-byte size header.

#### Memory Operations

```flux
def memset(void* ptr, int value, size_t n) -> void*
def memcpy(void* dst, void* src, size_t n) -> void*
def memmove(void* dst, void* src, size_t n) -> void*
def memcmp(void* a, void* b, size_t n) -> int
```

All four are native Flux implementations with no C runtime dependency.

#### Win32 Virtual Memory

Available on Windows only:

```flux
extern def VirtualAlloc(ulong, size_t, u32, u32) -> ulong
extern def VirtualFree(ulong, size_t, u32) -> bool
extern def VirtualProtect(ulong, size_t, u32, u32*) -> bool
extern def FlushInstructionCache(ulong, ulong, size_t) -> bool
```

#### standard::memory Utilities

```flux
def mem_zero(void* ptr, size_t size) -> void
def mem_fill(void* ptr, byte value, size_t size) -> void
def mem_copy(void* dest, void* src, size_t size) -> void
def mem_move(void* dest, void* src, size_t size) -> void
def mem_compare(void* a, void* b, size_t size) -> int
def mem_equals(void* a, void* b, size_t size) -> bool
```

#### Aligned Allocation

```flux
def align_forward(size_t addr, size_t alignment) -> size_t
def is_aligned(size_t addr, size_t alignment) -> bool
def malloc_aligned(size_t size, size_t alignment) -> void*
def free_aligned(void* ptr) -> void
```

#### Reference Counting

```flux
struct RefCountHeader { size_t ref_count, size; };

def ref_alloc(size_t size) -> void*
def ref_retain(void* ptr) -> void*
def ref_release(void* ptr) -> void
def ref_count(void* ptr) -> size_t
```

#### Byte Manipulation

```flux
def swap_bytes(byte* a, byte* b) -> void
def reverse_bytes(byte* buffer, size_t size) -> void
def copy_bytes(byte* dest, byte* src, size_t count) -> void
def zero_bytes(byte* buffer, size_t count) -> void
```

**Example**:
```flux
void* buffer = malloc(100);
if (buffer == NULL)
{
    print("Allocation failed\0");
    return 1;
};
// ... use buffer ...
free(buffer);
```

---

### allocators.fx

**Purpose**: Flux custom heap allocator (`fmalloc`/`ffree`/`frealloc`)

**Namespace**: `standard::memory::allocators::stdheap`

**Guard macro**: `FLUX_STANDARD_ALLOCATORS`

**Description**:  
Implements the Flux standard heap allocator, used internally by the runtime. Automatically initialized by `FRTStartup()` via `stdheap::table_init()`. Provides `fmalloc`/`ffree`/`frealloc` as the recommended allocation API for Flux programs.

**Design**:
- Segregated free lists by size class for O(1) small alloc/free
- Bump pointer fast path carves from a slab frontier
- Large allocations (>4096 bytes) get a dedicated OS slab, released on `ffree`
- Block metadata lives in a separate table slab (open-addressed hash map keyed by user pointer)
- No inline headers; user data blocks are completely clean
- No zeroing (Flux zero-initializes at the language level)
- Slabs acquired from OS: 4MB → 8MB → 16MB → 32MB → 64MB cap
- Zero OS memory consumed until the first `fmalloc` call

#### Public API

```flux
def fmalloc(size_t size) -> u64     // Allocate; returns integer address
def ffree(u64 ptr) -> void          // Free by integer address
def ffree(byte* ptr) -> void        // Free by pointer (overload)
def frealloc(u64 ptr, size_t new_size) -> u64  // Reallocate
```

**Note**: `fmalloc` returns a `u64` (raw address). Cast to the desired pointer type:

```flux
byte* buf = (byte*)fmalloc(256);
// ... use buf ...
ffree((u64)buf);
```

#### Internal API (do not call directly)

```flux
def stdheap::table_init() -> bool   // Called by FRTStartup()
```

---

### ffifio.fx

**Purpose**: File I/O through C standard library FFI

**Namespace**: `standard::io::file`

**Description**:  
Provides high-level file I/O operations using C's `stdio.h` through FFI. An alternative to the native syscall-based file I/O in `io.fx`.

#### C stdio FFI Declarations

```flux
extern def !!
    fopen(byte* filename, byte* mode) -> void*,
    fclose(void* stream) -> int,
    fread(void* ptr, int size, int count, void* stream) -> int,
    fwrite(void* ptr, int size, int count, void* stream) -> int,
    fseek(void* stream, int offset, int whence) -> int,
    ftell(void* stream) -> int,
    rewind(void* stream) -> void,
    feof(void* stream) -> int,
    ferror(void* stream) -> int;
```

#### File Modes

| Mode | Description |
|------|-------------|
| `"r"` | Read |
| `"w"` | Write (truncate) |
| `"a"` | Append |
| `"r+"` | Read/write |
| `"w+"` | Read/write (truncate) |
| `"rb"` | Read binary |
| `"wb"` | Write binary |
| `"ab"` | Append binary |

#### Seek Constants

```flux
SEEK_SET = 0  // Beginning of file
SEEK_CUR = 1  // Current position
SEEK_END = 2  // End of file
```

#### High-Level Helper Functions

```flux
def read_file(byte* filename, byte[] buffer, int buffer_size) -> int
def write_file(byte* filename, byte[] data, int data_size) -> int
def append_file(byte* filename, byte[] data, int data_size) -> int
def get_file_size(byte* filename) -> int
def file_exists(byte* filename) -> bool
```

**Example**:
```flux
#import "standard.fx";

def main() -> int
{
    byte[] data = "Hello, World!\0";
    int written = write_file("test.txt\0", data, 13);
    if (written < 0)
    {
        print("Failed to write file\0");
        return 1;
    };
    
    byte[1024] buffer;
    int read_bytes = read_file("test.txt\0", buffer, 1024);
    if (read_bytes > 0)
    {
        print(buffer);
    };
    return 0;
};
```

---

## String Utilities

### string_utilities.fx

**Purpose**: Comprehensive string manipulation functions

**Description**:  
Native Flux implementations of string operations without C runtime dependencies.

#### Core String Functions

```flux
def strlen(byte* ps) -> int
def strcpy(noopstr dest, noopstr src) -> noopstr
```

#### Integer to String Conversion

```flux
def i32str(i32 value, byte* buffer) -> i32
def i64str(i64 value, byte* buffer) -> i64
def u32str(u32 value, byte* buffer) -> u32
def u64str(u64 value, byte* buffer) -> u64
```

**Example**:
```flux
byte[32] buffer;
i32 len = i32str(-12345, @buffer[0]);
print(buffer);  // Prints "-12345"
```

#### String to Integer Conversion

```flux
def str2i32(byte* str) -> int
def str2u32(byte* str) -> uint
def str2i64(byte* str) -> i64
def str2u64(byte* str) -> u64
```

#### Float Conversion

```flux
def fstr(float value, byte* buffer, int precision) -> int
def str2f(byte* str) -> float
```

#### Character Classification

```flux
def is_digit(byte c) -> bool
def is_alpha(byte c) -> bool
def is_alnum(byte c) -> bool
def is_whitespace(byte c) -> bool
def is_upper(byte c) -> bool
def is_lower(byte c) -> bool
def is_hex_digit(byte c) -> bool
def is_identifier_start(byte c) -> bool
def is_identifier_char(byte c) -> bool
```

#### Character Conversion

```flux
def to_upper(byte c) -> byte
def to_lower(byte c) -> byte
def hex_to_int(byte c) -> int
```

#### String Comparison

```flux
def str_equals(byte* s1, byte* s2) -> bool
def str_equals_n(byte* s1, byte* s2, int n) -> bool
def starts_with(byte* str, byte* prefix) -> bool
def ends_with(byte* str, byte* suffix) -> bool
```

#### String Search

```flux
def find_char(byte* str, byte ch, int start_pos) -> int
def find_char_last(byte* str, byte ch) -> int
def find_substring(byte* haystack, byte* needle, int start_pos) -> int
def count_char(byte* str, byte ch) -> int
```

#### String Manipulation

```flux
def skip_whitespace(byte* str, int pos) -> int
def trim_start(byte* str) -> int
def trim_end(byte* str) -> int
```

**Memory-Allocating Functions** (caller must free):

```flux
def copy_string(byte* src) -> byte*
def copy_n(byte* src, int n) -> byte*
def substring(byte* str, int start, int length) -> byte*
def concat(byte* s1, byte* s2) -> byte*
```

#### Parsing Functions

```flux
def parse_int(byte* str, int start_pos, int* end_pos) -> int
def parse_hex(byte* str, int start_pos, int* end_pos) -> int
```

#### Line and Word Operations

```flux
def count_lines(byte* str) -> int
def get_line(byte* str, int line_num) -> byte*
def count_words(byte* str) -> int
```

#### String Replacement

```flux
def replace_first(byte* str, byte* find, byte* replace) -> byte*
```

#### Tokenization Helpers

```flux
def skip_until(byte* str, int pos, char ch) -> int
def skip_while_digit(byte* str, int pos) -> int
def skip_while_alnum(byte* str, int pos) -> int
def skip_while_identifier(byte* str, int pos) -> int
def match_at(byte* str, int pos, byte* pattern) -> bool
```

---

### string_object_raw.fx

**Purpose**: Object-oriented string wrapper

**Description**:  
Provides an object-oriented interface for string manipulation. Imported by `runtime.fx`; marked for deprecation from direct runtime use.

#### String Object

```flux
object string
{
    noopstr value;
    
    def val() -> byte*,
        len() -> int,
        set(byte*) -> bool,
        clear() -> void,
        isempty() -> bool,
        
        // Comparison
        equals(byte*) -> bool,
        compare(byte*) -> int,
        icompare(byte*) -> int,
        
        // Search
        contains(byte*) -> bool,
        startswith(byte*) -> bool,
        endswith(byte*) -> bool,
        indexof(byte*) -> int,
        lastindexof(byte*) -> int,
        indexof_char(char) -> int,
        lastindexof_char(char) -> int,
        count_occurrences(byte*) -> int,
        //count_spaces() -> int, // count_occurances(" \0")
        
        // Character access
        charat(int) -> char,
        setat(int, char) -> bool,
        
        // Substring & manipulation
        substring(int, int) -> byte*,
        left(int) -> byte*,
        right(int) -> byte*,
        
        // Concatenation
        concat(byte*) -> byte*,
        append(byte*) -> bool,
        prepend(byte*) -> bool,
        
        // Modification
        replace(byte*, byte*) -> byte*,
        replace_all(byte*, byte*) -> byte*,
        replace_char(char, char) -> bool,
        insert(int, byte*) -> bool,
        remove(int, int) -> bool,
        
        // Case conversion
        toupper() -> bool,
        tolower() -> bool,
        totitle() -> bool,
        
        // Trimming
        trim() -> bool,
        trimstart() -> bool,
        trimend() -> bool,
        trim_char(char) -> bool,
        
        // Splitting & joining
        split(char) -> byte**,
        split_lines() -> byte**,
        split_words() -> byte**,
        
        // Validation
        isalpha() -> bool,
        isdigit() -> bool,
        isalnum() -> bool,
        //isupper() -> bool,
        //islower() -> bool,
        
        // Conversion
        toint() -> int,
        toi32() -> i32,
        toi64() -> i64,
        tou32() -> u32,
        tou64() -> u64,
        fromint(int) -> bool,
        
        // Line operations
        count_lines() -> int,
        get_line(int) -> byte*,
        count_words() -> int,
        
        // Other
        reverse() -> bool,
        copy() -> byte*,
        hash() -> int,
        printval() -> void,
        println() -> void;
};
```

**Example**:
```flux
string myStr("Hello, World!\0");
print(myStr.val());
int length = myStr.len();
```

---

## Collections Library

### collections.fx

**Purpose**: Comprehensive data structure implementations for Flux

**Namespace**: `standard::collections`

**Dependencies**: `types.fx`, `memory.fx`

**Description**:  
Provides essential data structures for efficient data management. All collections are generic (using `void*` payloads) and manage their own allocation. Caller is responsible for freeing payloads.

#### Dynamic Array (Array)

**Definition**:
```flux
object Array
{
    void** items;
    size_t size;
    size_t capacity;
};
```

**Constructors**:
```flux
Array()                        // Default capacity: 16
Array(size_t initial_capacity) // Custom capacity
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get_size()` | `size_t` | Current number of elements |
| `get_capacity()` | `size_t` | Current allocated capacity |
| `is_empty()` | `bool` | Check if empty |
| `push(void* item)` | `bool` | Add to end (auto-resize) |
| `pop()` | `void*` | Remove and return last item |
| `get(size_t index)` | `void*` | Get item at index |
| `set(size_t index, void* item)` | `bool` | Set item at index |
| `clear()` | `void` | Remove all items (keeps capacity) |
| `remove_at(size_t index)` | `bool` | Remove at index (shift left) |
| `insert_at(size_t index, void* item)` | `bool` | Insert at index (shift right) |

**Example**:
```flux
Array myArray(32);
myArray.push((void*)42);
size_t count = myArray.get_size();  // 1
void* value = myArray.get(0);       // (void*)42
```

---

#### Doubly Linked List (LinkedList)

**Definition**:
```flux
struct LinkedListNode
{
    void* payload;
    LinkedListNode* next;
    LinkedListNode* prev;
};

object LinkedList
{
    LinkedListNode* head;
    LinkedListNode* tail;
    size_t size;
};
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get_size()` | `size_t` | Number of nodes |
| `is_empty()` | `bool` | Check if empty |
| `push_front(void*)` | `bool` | Add to front |
| `push_back(void*)` | `bool` | Add to back |
| `pop_front()` | `void*` | Remove and return first |
| `pop_back()` | `void*` | Remove and return last |
| `peek_front()` | `void*` | Get first without removing |
| `peek_back()` | `void*` | Get last without removing |
| `get(size_t index)` | `void*` | Get at index (O(n)) |
| `remove_at(size_t index)` | `bool` | Remove at index |
| `clear()` | `void` | Remove all nodes |

---

#### Stack

LIFO wrapper over `LinkedList`.

| Method | Returns | Description |
|--------|---------|-------------|
| `get_size()` | `size_t` | Number of items |
| `is_empty()` | `bool` | Check if empty |
| `push(void*)` | `bool` | Push onto stack |
| `pop()` | `void*` | Pop and return top |
| `peek()` | `void*` | Get top without removing |
| `clear()` | `void` | Remove all items |

---

#### Queue

FIFO wrapper over `LinkedList`.

| Method | Returns | Description |
|--------|---------|-------------|
| `get_size()` | `size_t` | Number of items |
| `is_empty()` | `bool` | Check if empty |
| `enqueue(void*)` | `bool` | Add to back |
| `dequeue()` | `void*` | Remove and return front |
| `peek()` | `void*` | Get front without removing |
| `clear()` | `void` | Remove all items |

---

#### Hash Map (HashMap)

**Definition**:
```flux
struct HashMapEntry { i64 key; void* value; HashMapEntry* next; };

object HashMap
{
    HashMapEntry** buckets;
    size_t bucket_count;
    size_t size;
};
```

**Constructors**:
```flux
HashMap()               // Default: 16 buckets
HashMap(size_t buckets) // Custom bucket count
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get_size()` | `size_t` | Number of pairs |
| `is_empty()` | `bool` | Check if empty |
| `put(i64 key, void* value)` | `bool` | Insert or update |
| `get(i64 key)` | `void*` | Get value (NULL if absent) |
| `contains(i64 key)` | `bool` | Check key exists |
| `remove(i64 key)` | `bool` | Remove pair |
| `clear()` | `void` | Remove all entries |

Uses chaining for collision resolution. Fixed bucket count (no auto-rehashing).

---

#### Binary Search Tree (BinarySearchTree)

**Definition**:
```flux
struct BinaryTreeNode
{
    void* payload;
    i64 key;
    BinaryTreeNode* left;
    BinaryTreeNode* right;
    BinaryTreeNode* parent;
};

object BinarySearchTree { BinaryTreeNode* root; size_t size; };
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get_size()` | `size_t` | Number of nodes |
| `is_empty()` | `bool` | Check if empty |
| `insert(i64 key, void* item)` | `bool` | Insert (updates if exists) |
| `find(i64 key)` | `void*` | Find payload by key |
| `contains(i64 key)` | `bool` | Check key exists |
| `remove(i64 key)` | `bool` | Remove node |
| `clear()` | `void` | Remove all nodes |

Maintains sorted order. Not self-balancing.

---

## Vectors Library

### vectors.fx

**Purpose**: 3D and 4D vector mathematics

**Namespace**: `standard::vectors`

**Dependencies**: `types.fx`, `math.fx`

#### Vector Structures

```flux
struct Vec3 { float x, y, z; };
struct Vec4 { float x, y, z, w; };
```

#### Vec3 Constructors

```flux
def vec3(float x, float y, float z) -> Vec3
def vec3_zero() -> Vec3    // (0, 0, 0)
def vec3_one() -> Vec3     // (1, 1, 1)
def vec3_up() -> Vec3      // (0, 1, 0)
def vec3_down() -> Vec3    // (0, -1, 0)
def vec3_left() -> Vec3    // (-1, 0, 0)
def vec3_right() -> Vec3   // (1, 0, 0)
def vec3_forward() -> Vec3 // (0, 0, 1)
def vec3_back() -> Vec3    // (0, 0, -1)
```

#### Vec4 Constructors

```flux
def vec4(float x, float y, float z, float w) -> Vec4
def vec4_zero() -> Vec4
def vec4_one() -> Vec4
def vec4_from_vec3(Vec3 v, float w) -> Vec4
```

#### Arithmetic Operations

```flux
def vec3_add(Vec3 a, Vec3 b) -> Vec3
def vec3_sub(Vec3 a, Vec3 b) -> Vec3
def vec3_mul(Vec3 v, float scalar) -> Vec3
def vec3_div(Vec3 v, float scalar) -> Vec3
def vec3_negate(Vec3 v) -> Vec3
def vec3_scale(Vec3 a, Vec3 b) -> Vec3  // Component-wise multiply

def vec4_add(Vec4 a, Vec4 b) -> Vec4
def vec4_sub(Vec4 a, Vec4 b) -> Vec4
def vec4_mul(Vec4 v, float scalar) -> Vec4
def vec4_div(Vec4 v, float scalar) -> Vec4
def vec4_negate(Vec4 v) -> Vec4
def vec4_scale(Vec4 a, Vec4 b) -> Vec4
```

#### Dot and Cross Products

```flux
def vec3_dot(Vec3 a, Vec3 b) -> float
def vec4_dot(Vec4 a, Vec4 b) -> float
def vec3_cross(Vec3 a, Vec3 b) -> Vec3  // Right-hand rule
```

#### Length and Normalization

```flux
def vec3_length_squared(Vec3 v) -> float
def vec3_length(Vec3 v) -> float
def vec3_normalize(Vec3 v) -> Vec3
def vec3_distance(Vec3 a, Vec3 b) -> float
def vec3_distance_squared(Vec3 a, Vec3 b) -> float

def vec4_length_squared(Vec4 v) -> float
def vec4_length(Vec4 v) -> float
def vec4_normalize(Vec4 v) -> Vec4
def vec4_distance(Vec4 a, Vec4 b) -> float
def vec4_distance_squared(Vec4 a, Vec4 b) -> float
```

#### Interpolation

```flux
def vec3_lerp(Vec3 a, Vec3 b, float t) -> Vec3
def vec4_lerp(Vec4 a, Vec4 b, float t) -> Vec4
def vec3_slerp(Vec3 a, Vec3 b, float t) -> Vec3
def vec4_slerp(Vec4 a, Vec4 b, float t) -> Vec4
```

#### Projection and Reflection

```flux
def vec3_project(Vec3 v, Vec3 onto) -> Vec3
def vec3_reject(Vec3 v, Vec3 from) -> Vec3
def vec3_reflect(Vec3 v, Vec3 normal) -> Vec3

def vec4_project(Vec4 v, Vec4 onto) -> Vec4
def vec4_reject(Vec4 v, Vec4 from) -> Vec4
def vec4_reflect(Vec4 v, Vec4 normal) -> Vec4
```

#### Angle, Min/Max/Clamp, Rotation, Advanced

```flux
def vec3_angle(Vec3 a, Vec3 b) -> float  // Radians, range [0, π]
def vec4_angle(Vec4 a, Vec4 b) -> float

def vec3_min(Vec3 a, Vec3 b) -> Vec3
def vec3_max(Vec3 a, Vec3 b) -> Vec3
def vec3_clamp(Vec3 v, Vec3 min_v, Vec3 max_v) -> Vec3

def vec3_rotate_x(Vec3 v, float angle) -> Vec3  // Angles in radians
def vec3_rotate_y(Vec3 v, float angle) -> Vec3
def vec3_rotate_z(Vec3 v, float angle) -> Vec3

def vec3_barycentric(Vec3 a, Vec3 b, Vec3 c, float u, float v) -> Vec3
def vec3_triple_product(Vec3 a, Vec3 b, Vec3 c) -> float  // a · (b × c)
def vec3_abs(Vec3 v) -> Vec3
def vec4_abs(Vec4 v) -> Vec4
```

---

## Extended Libraries

### atomics.fx

**Purpose**: Lock-free atomic primitives for multi-threaded access

**Namespace**: `standard::atomic`

**Guard macro**: `FLUX_STANDARD_ATOMICS`

**Description**:  
Provides hardware atomics via inline assembly for x86-64 and ARM64. Used internally by `threading.fx`.

#### Memory Barriers

```flux
def fence() -> void           // Full memory barrier
def compiler_barrier() -> void // Compiler-only barrier
def load_fence() -> void       // Acquire barrier
def store_fence() -> void      // Release barrier
```

#### Atomic Load / Store

```flux
def load32(i32* ptr) -> i32
def load64(i64* ptr) -> i64
def store32(i32* ptr, i32 value) -> void
def store64(i64* ptr, i64 value) -> void
```

#### Atomic Exchange

```flux
def exchange32(i32* ptr, i32 value) -> i32
def exchange64(i64* ptr, i64 value) -> i64
```

#### Compare-and-Swap

```flux
def cas32(i32* ptr, i32 expected, i32 desired) -> bool
def cas64(i64* ptr, i64 expected, i64 desired) -> bool
```

#### Atomic Arithmetic

```flux
def fetch_add32(i32* ptr, i32 delta) -> i32
def fetch_add64(i64* ptr, i64 delta) -> i64
def fetch_sub32(i32* ptr, i32 delta) -> i32
def fetch_sub64(i64* ptr, i64 delta) -> i64
def fetch_and32(i32* ptr, i32 mask) -> i32
def fetch_and64(i64* ptr, i64 mask) -> i64
def fetch_or32(i32* ptr, i32 mask) -> i32
def fetch_or64(i64* ptr, i64 mask) -> i64
def fetch_xor32(i32* ptr, i32 mask) -> i32
def fetch_xor64(i64* ptr, i64 mask) -> i64
def inc32(i32* ptr) -> i32
def inc64(i64* ptr) -> i64
def dec32(i32* ptr) -> i32
def dec64(i64* ptr) -> i64
```

#### Spin Lock

```flux
def spin_lock(i32* lock) -> void
def spin_unlock(i32* lock) -> void
def spin_trylock(i32* lock) -> bool
```

#### One-Time Initialization

```flux
def once_begin(i32* flag) -> bool  // Returns true if this caller wins the race
def once_end(i32* flag) -> void    // Signal initialization complete
```

#### Reference Counting / Flags

```flux
def ref_inc(i32* counter) -> void
def ref_dec_and_test(i32* counter) -> bool  // Returns true when count hits 0
def ref_get(i32* counter) -> i32

def flag_set(i32* flag) -> void
def flag_clear(i32* flag) -> void
def flag_test(i32* flag) -> bool
def flag_test_and_set(i32* flag) -> bool
```

---

### threading.fx

**Purpose**: Thread creation and synchronization primitives

**Namespace**: `standard::threading`

**Guard macro**: `FLUX_STANDARD_THREADING`

**Dependencies**: `types.fx`, `atomics.fx`

**Supported platforms**: Windows, Linux, macOS (x86-64 and ARM64)

#### Structures

```flux
struct Thread    { /* platform handle + id */ };
struct Mutex     { /* platform CS or pthread_mutex */ };
struct RWLock    { /* platform SRW or pthread_rwlock */ };
struct CondVar   { /* platform CV or pthread_cond */ };
struct Semaphore { /* platform handle + count */ };
struct Barrier   { /* atomic counter + CondVar */ };
struct TLSKey    { /* platform TLS slot */ };
```

#### Thread

```flux
def thread_create(void* fn, void* arg, Thread* out) -> int  // 0 on success
def thread_join(Thread* t) -> int
def thread_id() -> u64
def thread_yield() -> void
def thread_sleep_ms(u32 ms) -> void
```

#### Mutex

```flux
def mutex_init(Mutex* m) -> int
def mutex_destroy(Mutex* m) -> void
def mutex_lock(Mutex* m) -> void
def mutex_unlock(Mutex* m) -> void
def mutex_trylock(Mutex* m) -> bool
```

#### Reader/Writer Lock

```flux
def rwlock_init(RWLock* rw) -> int
def rwlock_destroy(RWLock* rw) -> void
def rwlock_read_lock(RWLock* rw) -> void
def rwlock_read_unlock(RWLock* rw) -> void
def rwlock_write_lock(RWLock* rw) -> void
def rwlock_write_unlock(RWLock* rw) -> void
def rwlock_try_read_lock(RWLock* rw) -> bool
def rwlock_try_write_lock(RWLock* rw) -> bool
```

#### Barrier

```flux
def barrier_init(Barrier* b, i32 n) -> void  // n = thread count
def barrier_wait(Barrier* b) -> bool          // Returns true for the last thread
```

#### Thread-Local Storage

```flux
def tls_key_create(TLSKey* k) -> int
def tls_key_destroy(TLSKey* k) -> void
def tls_set(TLSKey* k, void* value) -> int
def tls_get(TLSKey* k) -> void*
```

**Example**:
```flux
#import "threading.fx";
using standard::threading;

Thread t;
thread_create(my_worker_fn, (void*)@arg, @t);
thread_join(@t);
```

---

### timing.fx

**Purpose**: High-resolution timestamps, timers, and benchmarking utilities

**Namespace**: `standard::time`

**Description**:  
Provides nanosecond-resolution timing across all supported platforms.

#### Core Functions

```flux
def time_now() -> i64      // Current time in nanoseconds (platform-appropriate)
def sleep_ms(u32 ms) -> void
def sleep_us(u32 us) -> void
```

#### Unit Conversion

```flux
def ns_to_us(i64 ns) -> i64
def ns_to_ms(i64 ns) -> i64
def ns_to_sec(i64 ns) -> i64
def us_to_ns(i64 us) -> i64
def ms_to_ns(i64 ms) -> i64
def sec_to_ns(i64 s) -> i64
```

#### Timer Object

```flux
struct Timer { /* start/stop timestamps */ };

def timer_start(Timer* t) -> void
def timer_stop(Timer* t) -> i64   // Returns elapsed nanoseconds
```

**Example**:
```flux
#import "timing.fx";
using standard::time;

Timer t;
timer_start(@t);
// ... work ...
i64 elapsed_ns = timer_stop(@t);
```

---

### random.fx

**Purpose**: Random number generation

**Namespace**: `standard::random`

**Description**:  
Provides multiple RNG algorithms. Uses `rdtsc` or OS entropy for seeding. The recommended default is `PCG32` for general use.

#### RNG Structures

```flux
struct XorShift64  { /* 64-bit state */ };
struct XorShift128 { /* 128-bit state */ };
struct PCG32       { /* state + sequence */ };
struct LCG         { /* state */ };
```

#### Seeding

```flux
def xorshift64_seed(XorShift64* rng, u64 seed) -> void
def xorshift64_init(XorShift64* rng) -> void   // Auto-seed from entropy
def xorshift128_seed(XorShift128* rng, u64 seed1, u64 seed2) -> void
def xorshift128_init(XorShift128* rng) -> void
def pcg32_seed(PCG32* rng, u64 seed, u64 seq) -> void
def pcg32_init(PCG32* rng) -> void
def lcg_seed(LCG* rng, u64 seed) -> void
def lcg_init(LCG* rng) -> void
```

#### Generation

```flux
def xorshift64_next(XorShift64* rng) -> u64
def xorshift128_next(XorShift128* rng) -> u64
def pcg32_next(PCG32* rng) -> u32
def lcg_next(LCG* rng) -> u32
```

#### Utilities

```flux
def random_range_u64(XorShift128* rng, u64 max) -> u64
def random_range_u32(PCG32* rng, u32 max) -> u32
def random_range_int(PCG32* rng, int min, int max) -> int
def random_float(PCG32* rng) -> float           // [0.0, 1.0)
def random_range_float(PCG32* rng, float min, float max) -> float
def random_bool(PCG32* rng) -> bool
def random_bytes(PCG32* rng, byte* buffer, u64 length) -> void
def shuffle_u32_array(PCG32* rng, u32* array, u32 length) -> void
def roll_dice(PCG32* rng, int sides) -> int
def roll_dice_sum(PCG32* rng, int count, int sides) -> int
def flip_coin(PCG32* rng) -> bool
def random_string(PCG32* rng, byte* buffer, u32 length, byte* charset) -> void
def random_alphanum(PCG32* rng, byte* buffer, u32 length) -> void
def random_hex(PCG32* rng, byte* buffer, u32 length) -> void
```

#### Global Convenience Interface

```flux
def init_random() -> void  // Initialize global PCG32 state
def random() -> u32        // Draw from global state
```

---

### cryptography.fx

**Purpose**: Hashing and encryption primitives

**Namespaces**:
- `standard::crypto::hashing::SHA256`
- `standard::crypto::hashing::MD5`
- `standard::crypto::encryption::AES`

#### SHA-256

```flux
struct SHA256_CTX { /* 256-bit digest state */ };

def sha256_init(SHA256_CTX* ctx) -> void
def sha256_update(SHA256_CTX* ctx, byte* data, u64 len) -> void
def sha256_final(SHA256_CTX* ctx, byte* hash) -> void  // hash: 32-byte output buffer
```

#### MD5

```flux
struct MD5_CTX { /* 128-bit digest state */ };

def md5_init(MD5_CTX* ctx) -> void
def md5_update(MD5_CTX* ctx, byte* data, u64 len) -> void
def md5_final(MD5_CTX* ctx, byte* digest) -> void  // digest: 16-byte output buffer
```

#### AES

```flux
struct AES_CTX { /* round keys */ };

def aes_key_expansion(AES_CTX* ctx, byte* key) -> void          // 16-byte key
def aes_encrypt_block(AES_CTX* ctx, byte* plaintext, byte* ciphertext) -> void  // 16-byte blocks
def aes_decrypt_block(AES_CTX* ctx, byte* ciphertext, byte* plaintext) -> void
```

**Example** (SHA-256):
```flux
#import "cryptography.fx";
using standard::crypto::hashing::SHA256;

byte[32] hash;
SHA256_CTX ctx;
sha256_init(@ctx);
sha256_update(@ctx, data, data_len);
sha256_final(@ctx, @hash[0]);
```

---

### bigint.fx

**Purpose**: Arbitrary-precision integer arithmetic

**Namespace**: `math::bigint`

**Dependencies**: `math.fx`

#### BigInt Structure

```flux
struct BigInt { /* limb array, length, sign */ };
```

#### Construction

```flux
def bigint_zero(BigInt* num) -> void
def bigint_one(BigInt* num) -> void
def bigint_from_uint(BigInt* num, uint value) -> void
def bigint_from_u64(BigInt* num, u64 value) -> void
```

#### Predicates

```flux
def bigint_is_zero(BigInt* num) -> bool
def bigint_is_one(BigInt* num) -> bool
```

#### Arithmetic

```flux
def bigint_add(BigInt* result, BigInt* a, BigInt* b) -> void
def bigint_sub(BigInt* result, BigInt* a, BigInt* b) -> void
def bigint_mul(BigInt* result, BigInt* a, BigInt* b) -> void  // Karatsuba for large inputs
def bigint_divmod(BigInt* quotient, BigInt* remainder, BigInt* a, BigInt* b) -> void
def bigint_div(BigInt* result, BigInt* a, BigInt* b) -> void
def bigint_mod(BigInt* result, BigInt* a, BigInt* b) -> void
def bigint_pow_uint(BigInt* result, BigInt* base, uint exp) -> void
```

#### Bit Shifts

```flux
def bigint_shl(BigInt* result, BigInt* a, uint n) -> void
def bigint_shr(BigInt* result, BigInt* a, uint n) -> void
```

#### Comparison and Utilities

```flux
def bigint_cmp(BigInt* a, BigInt* b) -> int  // -1, 0, 1
def bigint_cmp_abs(BigInt* a, BigInt* b) -> int
def bigint_copy(BigInt* dest, BigInt* src) -> void
def bigint_normalize(BigInt* num) -> void
def bigint_print(BigInt* num) -> void
def bigint_print_hex(BigInt* num) -> void
def bigint_print_decimal(BigInt* num) -> void
```

---

### decimal.fx

**Purpose**: Arbitrary-precision decimal arithmetic

**Namespace**: `math::decimal`

**Dependencies**: `bigint.fx`

#### Decimal Structure

```flux
struct Decimal { BigInt coefficient; i32 exponent; bool negative; };
```

#### Precision Control

```flux
def decimal_set_precision(i32 prec) -> void
def decimal_get_precision() -> i32
```

#### Construction

```flux
def decimal_zero(Decimal* d) -> void
def decimal_one(Decimal* d) -> void
def decimal_from_i64(Decimal* d, i64 value) -> void
def decimal_from_u64(Decimal* d, u64 value) -> void
def decimal_from_string(Decimal* d, byte* s) -> void
def decimal_copy(Decimal* dest, Decimal* src) -> void
```

#### Arithmetic

```flux
def decimal_add(Decimal* result, Decimal* a, Decimal* b) -> void
def decimal_sub(Decimal* result, Decimal* a, Decimal* b) -> void
def decimal_mul(Decimal* result, Decimal* a, Decimal* b) -> void
def decimal_div(Decimal* result, Decimal* a, Decimal* b) -> void
def decimal_mod(Decimal* result, Decimal* a, Decimal* b) -> void
def decimal_pow_int(Decimal* result, Decimal* base, i32 exp) -> void
def decimal_neg(Decimal* result, Decimal* a) -> void
def decimal_abs(Decimal* result, Decimal* a) -> void
def decimal_sqrt(Decimal* result, Decimal* a) -> void
```

**Important**: Never pass the same pointer as both input and output (alias corruption). Always route through an intermediate variable:

```flux
Decimal tmp;
decimal_div(@tmp, @zoom, @two);  // Correct
decimal_copy(@zoom, @tmp);
// NOT: decimal_div(@zoom, @zoom, @two)  // Wrong - alias corruption
```

#### Rounding and Truncation

```flux
def decimal_round(Decimal* result, Decimal* a, i32 places) -> void
def decimal_truncate(Decimal* result, Decimal* a, i32 places) -> void
def decimal_floor(Decimal* result, Decimal* a) -> void
def decimal_ceil(Decimal* result, Decimal* a) -> void
```

#### Comparison and Predicates

```flux
def decimal_cmp(Decimal* a, Decimal* b) -> i32  // -1, 0, 1
def decimal_cmp_abs(Decimal* a, Decimal* b) -> i32
def decimal_is_zero(Decimal* d) -> bool
def decimal_is_negative(Decimal* d) -> bool
def decimal_is_positive(Decimal* d) -> bool
```

#### Output

```flux
def decimal_to_double(Decimal* d) -> double
def decimal_print(Decimal* d) -> void
def decimal_print_sci(Decimal* d) -> void  // Scientific notation
```

---

### net_windows.fx

**Purpose**: TCP/UDP networking (Windows Sockets API)

**Namespace**: `standard::net`

**Platform**: Windows only

#### Structures

```flux
struct sockaddr_in { /* family, port, addr */ };
struct sockaddr    { /* generic socket address */ };
struct timeval     { /* seconds, microseconds */ };
struct WSAData     { /* Winsock version info */ };
```

#### Initialization

```flux
def init() -> int      // Initialize Winsock (call before any socket ops)
def cleanup() -> int   // Cleanup Winsock
def get_last_error() -> int
```

#### Socket Creation

```flux
def tcp_socket() -> int
def udp_socket() -> int
```

#### Address Helpers

```flux
def init_sockaddr(sockaddr_in* addr, u32 ip_addr, u16 port) -> void
def init_sockaddr_str(sockaddr_in* addr, byte* ip_str, u16 port) -> void
def get_ip_string(sockaddr_in* addr) -> byte*
def get_port(sockaddr_in* addr) -> u16
def port_ntoh(u16 net_port) -> u16
def port_hton(u16 host_port) -> u16
```

#### Socket Options

```flux
def set_nonblocking(int sockfd) -> int
def set_blocking(int sockfd) -> int
def set_reuseaddr(int sockfd, bool enable) -> int
def set_recv_timeout(int sockfd, int milliseconds) -> int
def set_send_timeout(int sockfd, int milliseconds) -> int
def is_valid_socket(int sockfd) -> bool
```

#### TCP Server

```flux
def tcp_server_create(u16 port, int backlog) -> int
def tcp_server_accept(int server_sockfd, sockaddr_in* client_addr) -> int
```

#### TCP Client

```flux
def tcp_client_connect(byte* ip_addr, u16 port) -> int
def tcp_send(int sockfd, byte[] data, int length) -> int
def tcp_recv(int sockfd, byte[] buffer, int buffer_size) -> int
def tcp_send_all(int sockfd, byte[] data, int length) -> int
def tcp_recv_all(int sockfd, byte[] buffer, int length) -> int
def tcp_close(int sockfd) -> int
```

#### UDP

```flux
def udp_socket_bind(u16 port) -> int
def udp_send(int sockfd, byte[] data, int length, byte* dest_ip, u16 dest_port) -> int
def udp_recv(int sockfd, byte[] buffer, int buffer_size, sockaddr_in* src_addr) -> int
def udp_close(int sockfd) -> int
```

---

### uuid.fx

**Purpose**: UUID generation (versions 1, 4, and 7)

**Namespace**: `standard::uuid`

**Dependencies**: `random.fx`

#### UUID Structure

```flux
struct UUID { /* 16 bytes */ };
```

#### Generation

```flux
def uuid_v4(UUID* uuid, PCG32* rng) -> void       // Random UUID
def uuid_v4_quick(UUID* uuid) -> void              // Auto-seeded
def uuid_v7(UUID* uuid, PCG32* rng) -> void       // Time-ordered UUID
def uuid_v7_quick(UUID* uuid) -> void
def uuid_v1(UUID* uuid, PCG32* rng) -> void       // Time-based UUID
def uuid_v1_quick(UUID* uuid) -> void
def uuid_nil(UUID* uuid) -> void                   // All-zero UUID
def uuid_generate_batch_v4(UUID* uuids, int count, PCG32* rng) -> void
```

#### String Conversion

```flux
def uuid_to_string(UUID* uuid, byte* buffer) -> void        // Lowercase, 37-byte buffer
def uuid_to_string_upper(UUID* uuid, byte* buffer) -> void  // Uppercase
def uuid_to_hex(UUID* uuid, byte* buffer) -> void           // 32 hex chars, no dashes
```

#### Utilities

```flux
def uuid_equals(UUID* a, UUID* b) -> bool
def uuid_is_nil(UUID* uuid) -> bool
def uuid_version(UUID* uuid) -> int
def uuid_copy(UUID* dest, UUID* src) -> void
```

---

### sharedmemory.fx

**Purpose**: Named shared memory regions visible across processes

**Namespace**: `standard::sharedmemory`

#### SharedMem Structure

```flux
struct SharedMem { /* handle, mapping pointer, size, name */ };
```

#### Lifecycle

```flux
def shm_create(SharedMem* out, byte* name, size_t size) -> int      // Create new region
def shm_open_existing(SharedMem* out, byte* name, size_t size) -> int // Open existing
def shm_map(SharedMem* shm, u32 access) -> void*  // Map into address space
def shm_flush(SharedMem* shm) -> int
def shm_unmap(SharedMem* shm) -> int
def shm_close(SharedMem* shm) -> int
def shm_destroy(SharedMem* shm, byte* name) -> int  // Unmap + close + delete
```

---

### format.fx

**Purpose**: ANSI color codes, text formatting, borders, and separators

**Namespace**: `standard::format`

**Guard macro**: `FLUX_STANDARD_FORMAT`

#### Color Constants (`standard::format::colors`)

Pre-built ANSI escape strings as global `byte[]` constants:

```flux
RESET, BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE
BRIGHT_BLACK, BRIGHT_RED, BRIGHT_GREEN, BRIGHT_YELLOW
BRIGHT_BLUE, BRIGHT_MAGENTA, BRIGHT_CYAN, BRIGHT_WHITE
BG_BLACK, BG_RED, BG_GREEN, BG_YELLOW, BG_BLUE, BG_MAGENTA, BG_CYAN, BG_WHITE
BG_BRIGHT_BLACK ... BG_BRIGHT_WHITE
```

#### Printing Utilities

```flux
def print_charn(char c, int count) -> void          // Print char N times
def print_repeat(byte* str, int count) -> void
def print_separator(char c, int width) -> void
def hline(int width) -> void                        // Unicode box-drawing line
def hline_heavy(int width) -> void
def hline_light(int width) -> void
```

#### Colored Output

```flux
def print_colored(byte* text, byte* color) -> void
def println_colored(byte* text, byte* color) -> void
def print_red(byte* text) -> void
def print_green(byte* text) -> void
def print_blue(byte* text) -> void
def print_yellow(byte* text) -> void
def print_cyan(byte* text) -> void
def print_magenta(byte* text) -> void
```

#### Text Styling

```flux
def print_styled(byte* text, byte* style) -> void
def print_bold(byte* text) -> void
def print_italic(byte* text) -> void
def print_underline(byte* text) -> void
```

#### Borders and Boxes

```flux
def print_box_top(int width, bool double_line) -> void
def print_box_bottom(int width, bool double_line) -> void
```

---

### console.fx

**Purpose**: TUI cursor positioning, color control, and region management (Windows)

**Namespace**: `standard::io::console`

**Guard macro**: `FLUX_STANDARD_CONSOLE`

**Platform**: Windows only

**Usage**:
```flux
#import "console.fx";
using standard::io::console;

Console con;
con.cursor_set(0, 23);
con.set_attr(CON_FG_GREEN | CON_BG_BLACK);
con.write("Progress: [####      ] 40%\0");
con.reset_attr();
```

#### Coordinate Helpers

```flux
def make_coord(i16 x, i16 y) -> i32  // Pack (x, y) into COORD DWORD
def coord_x(i32 coord) -> i16
def coord_y(i32 coord) -> i16
```

#### Console Object

```flux
object Console
{
    def __init() -> this,
    
        refresh_size() -> void,
        get_width() -> i16,
        get_height() -> i16,
    
        cursor_set(i16 x, i16 y) -> void,
        cursor_get() -> i32,           // Packed COORD
        cursor_save() -> void,
        cursor_restore() -> void,
        cursor_visible(bool visible) -> void,
    
        set_attr(i16 attr) -> void,
        save_attr() -> void,
        restore_attr() -> void,
        reset_attr() -> void,
    
        write(byte* msg) -> void,
        write_at(i16 x, i16 y, byte* msg) -> void,
        write_at_colored(i16 x, i16 y, i16 attr, byte* msg) -> void,
    
        clear_line(i16 y) -> void,
        clear_line_attr(i16 y, i16 attr) -> void,
        clear_region(i16 x, i16 y, i16 w, i16 h) -> void,
        clear_screen() -> void,
        scroll_up(i16 top_row, i16 bottom_row, i16 lines) -> void,
    
        progress_bar(i16 row, byte* label, i32 done, i32 total) -> void,
        spinner(i16 x, i16 y, i32 tick) -> void;
};
```

---

### graphing.fx

**Purpose**: 2D line graphs, bar charts, scatter plots, and a full 3D graphing system

**Namespace**: `standard::graphing` / `standard::graphing::graph3d`

#### 2D Graphing

```flux
struct Graph { /* dimensions, axes, data series */ };
```

Provides terminal-based 2D rendering of line graphs, bar charts, and scatter plots with configurable axes and grid.

#### 3D Graphing

```flux
struct Graph3D { /* 3D axes, parametric data generators */ };
```

Full 3D graphing system with parametric surface and curve generators.

---

### opengl.fx

**Purpose**: OpenGL context setup and rendering helpers via Win32 WGL

**Namespace**: `standard::system::windows` (OpenGL section)

**Platform**: Windows only

#### Context Setup

```flux
def setup_opengl(HDC device_context) -> HGLRC
def swap_buffers(HDC device_context) -> void
def gl_load_extensions() -> void
```

#### Shader Utilities

```flux
def compile_shader(int shader_type, byte* src) -> int
def link_program(int vert, int frag) -> int
```

#### Matrix Math (for shaders)

```flux
struct Matrix4 { /* 4x4 float matrix */ };
struct GLVec3  { float x, y, z; };

def mat4_identity(Matrix4* out) -> void
def mat4_mul(Matrix4* a, Matrix4* b, Matrix4* out) -> void
def mat4_perspective(float fovy_rad, float aspect, float near_z, float far_z, Matrix4* out) -> void
def mat4_ortho(float left, float right, float bottom, float top, float near_z, float far_z, Matrix4* out) -> void
def mat4_translate(float tx, float ty, float tz, Matrix4* out) -> void
def mat4_scale(float sx, float sy, float sz, Matrix4* out) -> void
def mat4_rotate(float ax, float ay, float az, float angle_rad, Matrix4* out) -> void
def vec3_dot(GLVec3* a, GLVec3* b) -> float
```

---

### windows.fx

**Purpose**: Win32 window creation and GDI drawing

**Namespace**: `standard::system::windows`

**Platform**: Windows only

#### Structures

```flux
struct MSG          { /* Windows message */ };
struct WNDCLASSEXA  { /* Window class descriptor */ };
struct RECT         { left, top, right, bottom; };
struct PAINTSTRUCT  { /* Paint context */ };
```

#### Helpers

```flux
def DefaultWindowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) -> LRESULT
def RGB(byte r, byte g, byte b) -> DWORD
```

#### Window Object

```flux
object Window
{
    def __init(byte* title, int w, int h, int x, int y) -> this,
        __exit() -> void,
    
        show() -> void,
        hide() -> void,
        set_title(byte* title) -> void,
        process_messages() -> bool;  // Returns false on WM_QUIT
};
```

#### Canvas Object

```flux
object Canvas
{
    def __init(HWND hwnd, HDC hdc) -> this,
        __exit() -> void,
    
        clear(DWORD color) -> void,
        set_pen(DWORD color, int width) -> void,
        line(int x1, int y1, int x2, int y2) -> void,
        circle(int cx, int cy, int r) -> void;
};
```

---

### detour.fx

**Purpose**: x86-64 inline hook / detour (Windows)

**Platform**: Windows only (x86-64)

#### Detour Object

```flux
object Detour
{
    def __init() -> this,
        __exit() -> void,
    
        install(ulong target, ulong hook) -> bool,
        uninstall() -> bool,
        call_original(ulong arg) -> ulong;
};
```

**Description**: Patches a 14-byte absolute jump at `target` to redirect execution to `hook`. Saves the original bytes so the original function can be called via `call_original`. Uses `VirtualProtect` to temporarily make the target page writable and `FlushInstructionCache` after patching.

---

### operators.fx

**Purpose**: Extended operator utilities

**Namespace**: `standard::operators`

**Description**: Supplementary operator implementations and overloads not covered by the core language or other modules.

---

## Import Guidelines

### Basic Import

To use the standard library:

```flux
#import "standard.fx";
```

This automatically imports via `runtime.fx`:
- Type definitions (`types.fx`)
- OS detection (`sys.fx`)
- Memory management (`memory.fx`, `allocators.fx`)
- I/O operations (`io.fx`)
- File I/O via FFI (`ffifio.fx`)
- String utilities (`string_utilities.fx`)
- Raw builtins (`string_object_raw.fx`, `file_object_raw.fx`)

### Selective Imports

Extended libraries must be imported explicitly:

```flux
// Types only
#import "types.fx";

// Math
#import "math.fx";

// Collections
#import "collections.fx";

// Vectors
#import "vectors.fx";

// Threading (pulls in atomics.fx automatically)
#import "threading.fx";

// Timing
#import "timing.fx";

// Networking (Windows)
#import "net_windows.fx";

// Cryptography
#import "cryptography.fx";

// Arbitrary precision
#import "decimal.fx";  // also pulls in bigint.fx

// TUI console control
#import "console.fx";

// ANSI text formatting
#import "format.fx";

// OpenGL (Windows)
#import "opengl.fx";

// Win32 GUI
#import "windows.fx";

// Inline hooking (Windows x86-64)
#import "detour.fx";
```

### Namespace Usage

After importing, use namespaces explicitly or with `using`:

```flux
#import "standard.fx";

// Explicit namespace
int result = standard::math::abs(-42);

// Using directive
using standard::math;
int result = abs(-42);

// Collections
#import "collections.fx";
using standard::collections;
Array myArray;

// Vectors
#import "vectors.fx";
using standard::vectors;
Vec3 position = vec3(1.0, 2.0, 3.0);
```

### Conditional Compilation

```flux
// Disable runtime
#def FLUX_RUNTIME 0;
#import "standard.fx";

// Guard against double imports
#ifndef FLUX_STANDARD_MEMORY
#import "memory.fx";
#endif;
```

---

## Platform Support

### Supported Platforms

| Platform | Architecture | Status |
|----------|--------------|--------|
| Windows | x86_64 (64-bit) | Supported, primary target |
| Linux | x86_64 (64-bit) | Supported |
| macOS | x86_64 (64-bit) | Partial - needs improvement |
| - | ARM (64-bit) | Minimal - needs major improvement |

### Platform Detection

Preprocessor definitions set automatically at compile time:

```flux
#ifdef __WINDOWS__
    // Windows-specific code
#endif;

#ifdef __LINUX__
    // Linux-specific code
#endif;

#ifdef __MACOS__
    // macOS-specific code
#endif;

#ifdef __ARCH_X86_64__
    // 64-bit x86 code
#endif;

#ifdef __ARCH_ARM64__
    // ARM64 code
#endif;

#ifdef __WIN64__
    // Windows 64-bit
#endif;
```

### Platform-Specific Notes

#### Windows

- Uses Windows API for console I/O (`GetStdHandle`, `WriteFile`, `ReadFile`)
- File I/O through both Windows API and C FFI
- Supports wide character handling (`wchar`)
- Command-line arguments parsed from `GetCommandLineW()`
- Exclusive home of: `net_windows.fx`, `console.fx`, `opengl.fx`, `windows.fx`, `detour.fx`, `sharedmemory.fx`
- Entry point: `FRTStartup()`

#### Linux

- Direct syscall interface for all I/O operations
- No C runtime dependency for core operations
- Native `malloc`/`free` via `mmap`/`munmap`
- Entry point: `_start()` → `FRTStartup()`

#### macOS

- Similar to Linux with BSD syscalls
- Native `malloc`/`free` via macOS `mmap` syscall numbers
- Console I/O implementation pending full testing
- Entry point: `start()`

---

## Best Practices

### Memory Management

1. **Prefer `fmalloc`/`ffree` for Flux programs** — the standard heap allocator is more efficient than `malloc`/`free` in most cases:
   ```flux
   byte* buf = (byte*)fmalloc(256);
   // ... use buf ...
   ffree((u64)buf);
   ```

2. **Check allocation results**:
   ```flux
   void* buffer = malloc(1024);
   if (buffer == NULL)
   {
       return -1;
   };
   ```

3. **All locals are zero-initialized** — no need to manually zero freshly declared stack variables.

4. **All allocations are stack-allocated by default** — do not declare variables inside loops unless you intend a stack overflow. Hoist loop-invariant declarations to the function top.

### String Handling

1. **Always null-terminate strings** — the compiler does not do this automatically:
   ```flux
   print("Hello, World!\0");
   ```

2. **Use appropriate buffer sizes**:
   ```flux
   byte[32] buffer;
   i32str(value, @buffer[0]);
   ```

3. **Free dynamically allocated strings**:
   ```flux
   byte* result = concat(s1, s2);
   print(result);
   free(result);
   ```

### File I/O

1. **Always check file handles**:
   ```flux
   i64 fd = open_read("file.txt\0");
   if (fd == INVALID_FD)
   {
       return -1;
   };
   ```

2. **Close files when done**:
   ```flux
   close(fd);
   ```

### Error Handling

1. **Check return values**:
   ```flux
   int result = write_file("data.txt\0", buffer, size);
   if (result < 0)
   {
       print("Write failed\0");
       return 1;
   };
   ```

2. **Use try-catch for critical sections**:
   ```flux
   try
   {
       // Risky operation
   }
   catch()
   {
       return false;
   };
   ```

---

## Version History

**Version 2.0** (March 2026)
- `red` prefix removed from all library filenames
- `redstandard.fx` retired; `standard.fx` now directly imports `runtime.fx`
- `red_string_utilities.fx` renamed to `string_utilities.fx`
- `memory.fx` expanded: native Linux/macOS `malloc`/`free` via `mmap`; `standard::memory` namespace with utilities, aligned allocation, reference counting, and byte manipulation helpers
- `allocators.fx` promoted to primary heap allocator (`fmalloc`/`ffree`/`frealloc`); initialized by `FRTStartup()`
- `sys.fx` formalized with `standard::system` namespace and `CURRENT_OS` detection
- `ntoh`/`hton` helpers in `types.fx` marked deprecated
- New libraries added: `atomics.fx`, `threading.fx`, `timing.fx`, `random.fx`, `cryptography.fx`, `bigint.fx`, `decimal.fx`, `net_windows.fx`, `uuid.fx`, `sharedmemory.fx`, `format.fx`, `console.fx`, `graphing.fx`, `opengl.fx`, `windows.fx`, `detour.fx`, `operators.fx`

**Version 1.0** (February 2026)
- Initial reduced specification implementation
- Cross-platform support (Windows, Linux, macOS)
- Core I/O, math, and string utilities
- FFI integration with C runtime
- Collections library (Array, LinkedList, Stack, Queue, HashMap, BinarySearchTree)
- Vectors library (3D/4D vector mathematics)

---

## Contributing

The Flux Standard Library is part of the Flux language project. For contributions, bug reports, or questions, please visit the [Flux Discord server](https://discord.gg/RAHjbYuNUc).

---

## License

This documentation describes the Flux Standard Library as part of the Flux programming language project.

---

*This documentation reflects the Flux standard library as of v2.0, March 2026. For the most up-to-date information, refer to the official Flux language repository and Discord community.*