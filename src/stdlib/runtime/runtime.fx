// Author: Karac V. Thweatt

///
Flux Standard Runtime

Minimal runtime. Standard heap allocator is lazy initialized.
No allocation until first fmalloc().

The STDLIB_GVP is the standard library global void pointer.
It is provided so you do not need to allocate it during checks,
such as:
if (ptr == 0); // This allocates 0 on the stack momentarily.
Using this pointer solves this allocation.

NULL is an alternative which is easier to type.

By default, the standard types and memory libraries are pulled in.
This is simply for the heap allocator.

Also, standard input/output is pulled in, and is minimal.
///

const void* STDLIB_GVP = (void*)@void;
const data{64} U64MAXVAL = 0xFFFFFFFFFFFFFFFFu;

#def NULL STDLIB_GVP;

#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#ifndef FLUX_RUNTIME
#def FLUX_RUNTIME 1;
#endif;

#ifdef __WIN64__
#def __WIN32__ 0;
#else
#ifndef __WIN32__
#def __WIN32__ 1;
#endif;
#endif;

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifdef __WINDOWS__
global i64 WIN_STDOUT_HANDLE;
#endif;

#ifndef FLUX_STANDARD_MEMORY
#import "memory.fx";
#endif;

using standard::memory::allocators::stdheap;

// DO NOT MODIFY THIS LINE
#import "string_utilities.fx";
// DO NOT MODIFY THIS LINE

#ifndef FLUX_STANDARD_SYSTEM
#import "sys.fx";
#endif;

#ifndef FLUX_STANDARD_TIMING
#import "timing.fx";
#endif;

#ifndef FLUX_STANDARD_IO
#import "io.fx";
#endif;

// ---------------------------
//
// Import runtime helpers
#import "ffifio.fx";             // FFI-based File Input/Output (CRT)
//
// ---------------------------
//
// Import raw functions & builtins
#import "string_object_raw.fx";  // Deprecated from direct use in runtime
#import "file_object_raw.fx";    // "
//#import "socket_object_raw.fx";  // "
//

//#ifndef FLUX_STANDARD_COLLECTIONS
//#import "redcollections.fx";
//#endif;

extern
{
#ifdef __WINDOWS__
    def !!
        GetStdHandle(int nStdHandle) -> i64,
        GetCommandLineW() -> wchar*,
        LocalFree(void* x) -> void*;
#endif;
};

#ifdef __LINUX__
def !!exit(int code) -> void
{
    volatile asm
    {
        movl $0, %edi
        movq $$231, %rax
        syscall
    } : : "r"(code) : "edi", "rax", "memory";
    noreturn;
};

def !!abort() -> void
{
    volatile asm
    {
        movq $$231, %rax
        movq $$134, %rdi
        syscall
    } : : : "rax", "rdi", "memory";
    noreturn;
};

def !!atexit(void* fn) -> int
{
    int r;
    r = 0;
    return r;
};
#endif;

#ifdef __MACOS__
def !!exit(int code) -> void
{
    volatile asm
    {
        movl $0, %edi
        movq $$0x2000001, %rax
        syscall
    } : : "r"(code) : "edi", "rax", "memory";
    noreturn;
};

def !!abort() -> void
{
    volatile asm
    {
        movq $$0x2000001, %rax
        movq $$134, %rdi
        syscall
    } : : : "rax", "rdi", "memory";
    noreturn;
};

def !!atexit(void* fn) -> int
{
    return 0;
};
#endif;



// >Mains
def main() -> int;
def main(int, byte**) -> int;
// /Mains

  ///                                       ///
 ///DO NOT REDEFINE THIS FUNCTION SIGNATURE///
///                                       ///
def !!FRTStartup() -> int; // GO AWAY, SHOO
  ///                                       ///
 ///DO NOT REDEFINE THIS FUNCTION SIGNATURE///
///                                       ///

#ifdef __LINUX__
def !!_start() -> void;

def !!_start() -> void
{
    exit(FRTStartup());
    abort();
    noreturn;
};
#endif; // Linux

#ifdef FLUX_RUNTIME
#ifdef __WINDOWS__
def !!FRTStartup() -> int
{
    int return_code, argc, argi, pos, start, len, j, k;
    byte* arg;
    byte** argv;
    bool quoted;
    wchar* cmdLine;


    // Initialize stdout handle for win_print
    WIN_STDOUT_HANDLE = GetStdHandle(-11);
    //print("STDOUT: \0"); print(WIN_STDOUT_HANDLE); print();

    // Initialize the Flux standard heap allocator
    // For reference, see runtime/redallocators.fx
    standard::memory::allocators::stdheap::table_init();

    // Parse command line manually from GetCommandLineW
    cmdLine = GetCommandLineW();

    while (cmdLine[pos] != (wchar)0)
    {
        // Skip whitespace
        while (cmdLine[pos] == (wchar)32 | cmdLine[pos] == (wchar)9)
        {
            pos = pos + 1;
        };
        if (cmdLine[pos] == (wchar)0)
        {
            break;
        };
        // Skip quoted or unquoted token
        if (cmdLine[pos] == (wchar)34)
        {
            pos = pos + 1;
            while (cmdLine[pos] != (wchar)0 & cmdLine[pos] != (wchar)34)
            {
                pos = pos + 1;
            };
            if (cmdLine[pos] == (wchar)34)
            {
                pos = pos + 1;
            };
        }
        else
        {
            while (cmdLine[pos] != (wchar)0 & cmdLine[pos] != (wchar)32 & cmdLine[pos] != (wchar)9)
            {
                pos = pos + 1;
            };
        };
        argc = argc + 1;
    };

    // Allocate argv
    argv = (byte**)fmalloc((u64)argc * (u64)8);

    // Fill argv
    argi = 0;
    pos = 0;
    while (cmdLine[pos] != (wchar)0)
    {
        // Skip whitespace
        while (cmdLine[pos] == (wchar)32 | cmdLine[pos] == (wchar)9)
        {
            pos = pos + 1;
        };
        if (cmdLine[pos] == (wchar)0)
        {
            break;
        };

        // Measure token length
        start = pos;
        len = 0;
        if (cmdLine[pos] == (wchar)34)
        {
            quoted = true;
            pos = pos + 1;
            start = pos;
            while (cmdLine[pos] != (wchar)0 & cmdLine[pos] != (wchar)34)
            {
                len = len + 1;
                pos = pos + 1;
            };
            if (cmdLine[pos] == (wchar)34)
            {
                pos = pos + 1;
            };
        }
        else
        {
            while (cmdLine[pos] != (wchar)0 & cmdLine[pos] != (wchar)32 & cmdLine[pos] != (wchar)9)
            {
                len = len + 1;
                pos = pos + 1;
            };
        };

        // Copy low byte of each wchar into byte buffer
        arg = (byte*)fmalloc((u64)len + (u64)1);
        j = 0;
        while (j < len)
        {
            arg[j] = (byte)cmdLine[start + j];
            j = j + 1;
        };
        arg[len] = (byte)0;
        argv[argi] = arg;
        argi = argi + 1;
    };

    // Call the appropriate main overload
    if (argc > 1)
    {
        // Check 32-bit / 64-bit here, call appropriate main
        // 32 bit should call this one
        // #ifdef ...
        return_code = main__2__intE1__byteE1_ptr2__ret_intE1(argc, argv);
        // #else
        // 64 bit should call this one
        // return_code = main__2__intE1__byteE1_ptr2__ret_longE1(argc, argv);
    }
    else
    {
        return_code = main();
    };

    // Free converted argv
    while (k < argc)
    {
        ffree((u64)argv[k]);
        k = k + 1;
    };
    ffree(long(argv));

    if (return_code != 0)
    {
        // Handle error
        if (return_code == -1073741819)
        {
            standard::io::console::print("SEGFAULT\n\0");
        };
    };
    return return_code;
};
#endif; // __WINDOWS__

#ifdef __LINUX__
def !!FRTStartup() -> int
{
    // Initialize the Flux standard heap allocator
    // For reference, see runtime/redallocators.fx
    standard::memory::allocators::stdheap::table_init();
    int return_code = main__0__ret_intE1();
    if (return_code != 0)
    {
        // Handle error
        if (return_code == -1073741819)
        {
            standard::io::console::print("SEGFAULT\n\0");
        };
    };
    return return_code;
};
#endif; // __LINUX__

#ifdef __MACOS__
def !!FRTStartup() -> int
{
    int return_code = main__0__ret_intE1();
    if (return_code != 0)
    {
        // Handle error
        if (return_code == -1073741819)
        {
            standard::io::console::print("SEGFAULT\n\0");
        };
    };
    return return_code;
};
#endif; // __MACOS__
#endif; // FLUX_RUNTIME