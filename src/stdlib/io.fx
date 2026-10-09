// Author: Karac V. Thweatt

// Input/Output Operations
#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#import <sys.fx>;


#ifndef FLUX_STANDARD_IO
#def FLUX_STANDARD_IO;

#ifndef FLUX_STANDARD_TYPES
#import <types.fx>;
#endif;

/// MOVE TO SYS.FX BEGIN ///
#ifdef __WINDOWS__
extern
{
    def !!
        fgets(byte* str, int n, byte* stream) -> byte*,
        fopen(byte* filename, byte* mode) -> byte*,
        fclose(byte* stream) -> int;
};
#endif;
/// /MOVETOSYS/ END ///

namespace standard
{
    namespace io
    {
        // Console I/O
        namespace console
        {
    		// INPUT FORWARD DECLARATIONS
#ifdef __WINDOWS__
            def win_input(byte[] buffer, int max_len) -> int # effect {~IO.Console.Input};
#endif; // Windows
#ifdef __LINUX__
            def nix_input(byte[] buffer, int max_len) -> int # effect {~IO.Console.Input};
#endif; // Linux
#ifdef __MACOS__
            def mac_input(byte[] buffer, int max_len) -> int # effect {~IO.Console.Input};
#endif; // Mac
            // GENERIC
            def input(byte[] buffer, int max_len) -> int # effect {~IO.Console.Input};
            

            // OUTPUT FORWARD DECLARATIONS
#ifdef __WINDOWS__
            def win_print(byte* msg, int x) -> void # effect {~IO.Console.Output};
#endif;
#ifdef __LINUX__
            def nix_print(byte* msg, int x) -> void # effect {~IO.Console.Output};
#endif;
#ifdef __MACOS__
            def mac_print(byte* msg, int x) -> void # effect {~IO.Console.Output};
#endif;
            // GENERIC
            def print() -> void # effect {~IO.Console}, // no param = newline
                print(noopstr, int) -> void # effect {~IO.Console.Output},
                print(noopstr) -> void # effect {~IO.Console.Output},
                print(bool) -> void # effect {~IO.Console.Output},
                printchar(noopstr) -> void # effect {~IO.Console.Output},
                print(char) -> void # effect {~IO.Console.Output},
                print(byte) -> void # effect {~IO.Console.Output},
                print(i8) -> void # effect {~IO.Console.Output},
                print(i16) -> void # effect {~IO.Console.Output},
                print(u16) -> void # effect {~IO.Console.Output},
                print(int) -> void # effect {~IO.Console.Output},
                print(i32) -> void # effect {~IO.Console.Output}, // Holy shit ditto would be nice here
                print(uint) -> void # effect {~IO.Console.Output},
                print(u32) -> void # effect {~IO.Console.Output},
                print_hex_byte(byte) -> void # effect {~IO.Console.Output},
                print_hex_u32(u32) -> void # effect {~IO.Console.Output},
                print(i64) -> void # effect {~IO.Console.Output},
                print(u64) -> void # effect {~IO.Console.Output},
                print(long) -> void # effect {~IO.Console.Output},
                print(ulong) -> void # effect {~IO.Console.Output},
                print(float) -> void # effect {~IO.Console.Output},
                print(float,int) -> void # effect {~IO.Console.Output},
                print(double) -> void # effect {~IO.Console.Output},
                print(double,int) -> void # effect {~IO.Console.Output},
                println(noopstr) -> void # effect {~IO.Console.Output},   // newline print overloads
                println(byte) -> void # effect {~IO.Console.Output},
                println(char) -> void # effect {~IO.Console.Output},
                println(bool) -> void # effect {~IO.Console.Output},
                println(i8) -> void # effect {~IO.Console.Output},
                println(i16) -> void # effect {~IO.Console.Output},
                println(u16) -> void # effect {~IO.Console.Output},
                println(int) -> void # effect {~IO.Console.Output},
                println(uint) -> void # effect {~IO.Console.Output},
                printhbline(byte) -> void # effect {~IO.Console.Output},
                println(long) -> void # effect {~IO.Console.Output},
                println(ulong) -> void # effect {~IO.Console.Output},
                println(float) -> void # effect {~IO.Console.Output},
                println(float,int) -> void # effect {~IO.Console.Output},
                println(double) -> void # effect {~IO.Console.Output},
                println(double,int) -> void # effect {~IO.Console};

#ifdef __WINDOWS__
            // INPUT DEFINITIONS
            def win_input(byte[] buf, int max_len) -> int
            {
                i32 bytes_read, original_mode;
                i32* bytes_read_ptr = @bytes_read,
                     mode_ptr = @original_mode;
                
#ifdef __ARCH_X86_64__
                volatile asm
                {
                    // Get stdin handle
                    movq $$-10, %rcx
                    subq $$32, %rsp
                    call GetStdHandle
                    addq $$32, %rsp
                    movq %rax, %r12
                    
                    // Get current console mode
                    movq %rax, %rcx
                    movq $3, %rdx
                    subq $$32, %rsp
                    call GetConsoleMode
                    addq $$32, %rsp
                    
                    // Enable ENABLE_PROCESSED_INPUT (for Ctrl+C) and keep ENABLE_LINE_INPUT
                    // 0x001F = ENABLE_PROCESSED_INPUT | ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT | 
                    //          ENABLE_WINDOW_INPUT | ENABLE_MOUSE_INPUT
                    movq %r12, %rcx
                    movq $$0x001F, %rdx
                    subq $$32, %rsp
                    call SetConsoleMode
                    addq $$32, %rsp
                    
                    // Read input (will wait for Enter)
                    movq %r12, %rcx
                    movq $0, %rdx           // buf
                    movl $1, %r8d           // max_len
                    movq $2, %r9            // bytes_read_ptr
                    subq $$40, %rsp
                    movq $$0, 32(%rsp)
                    call ReadFile
                    addq $$40, %rsp
                    
                    // Restore original mode
                    movq %r12, %rcx
                    movl ($3), %edx
                    subq $$32, %rsp
                    call SetConsoleMode
                    addq $$32, %rsp
                    
                    // Return bytes_read
                    movl ($2), %eax
                } : : "r"(buf), "r"(max_len), "r"(bytes_read_ptr), "r"(mode_ptr)
                  : "rax","rcx","rdx","r8","r9","r10","r11","r12","memory";
#endif; // ARCH 86 64
#ifdef __ARCH_ARM64__
#endif; // ARCH ARM
                for (int i; i < bytes_read; i++)
                {
                    if (buf[i] == '\r' | buf[i] == '\n')
                    {
                        buf[i] = 0;
                    };
                };
                return bytes_read;
            };
#endif; // WINDOWS
/// --- --- --- --- --- ///
#ifdef __LINUX__
            def nix_input(byte[] buffer, int max_len) -> int
            {
                i64 count = max_len,
                    bytes_read = 0;

#ifdef __ARCH_X86_64__
                volatile asm
                {
                    // Linux syscall: read(int fd, void *buf, size_t count)
                    // syscall number: 0 (read)
                    // fd: 0 (STDIN_FILENO)
                    movq $$0, %rax
                    movq $$0, %rdi
                    movq $0, %rsi
                    movq $1, %rdx
                    syscall
                } : "r"(bytes_read) : "r"(buffer), "r"(count)
                  : "rax","rdi","rsi","rdx","rcx","r11","memory";
#endif; // ARCH X86_64
#ifdef __ARCH_ARM64__
                volatile asm
                {
                    // Linux ARM64 syscall: read(int fd, void *buf, size_t count)
                    // syscall number: 63 (read)
                    // fd: 0 (STDIN_FILENO)
                    mov x8, #63
                    mov x0, #0
                    ldr x1, [sp]
                    ldr x2, [sp, #8]
                    svc #0
                } : "r"(bytes_read) : "r"(buffer), "r"(count)
                  : "x0","x1","x2","x3","x4","x5",
                    "x6","x7","x8","x9","x10","x11",
                    "x12","x13","x14","x15","x16",
                    "x17","memory";
#endif; // ARCH ARM64

                if (bytes_read <= 0)
                {
                    return 0;
                };

                for (int i; i < max_len; i++)
                {
                    if (buffer[i] == '\n' | buffer[i] == '\r')
                    {
                        buffer[i] = '\0';
                    };
                };

                return bytes_read;
            };
#endif; // LINUX
#ifdef __MACOS__
            def mac_input(byte[] buffer, int max_len) -> int
            {
                i64 count = max_len,
                    bytes_read = 0;

#ifdef __ARCH_X86_64__
                volatile asm
                {
                    // macOS x86_64 (Darwin) syscall convention:
                    // Syscall number in rax
                    // Parameters: rdi, rsi, rdx, r10, r8, r9
                    // Use syscall instruction
                    // Syscall numbers: BSD base 0x2000000
                    
                    // macOS syscall: read(int fd, void *buf, size_t count)
                    // syscall number: 0x2000003 (BSD read = 3, + 0x2000000)
                    // fd: 0 (STDIN_FILENO)
                    movq $$0x2000003, %rax
                    movq $$0, %rdi
                    movq $0, %rsi
                    movq $1, %rdx
                    syscall
                } : "r"(bytes_read) : "r"(buffer), "r"(count)
                  : "rax","rdi","rsi","rdx","rcx","r11","memory";
#endif; // ARCH X86_64
#ifdef __ARCH_ARM64__
                volatile asm
                {
                    // macOS ARM64 (Darwin) syscall convention:
                    // x16: syscall number
                    // x0-x5: parameters
                    // svc #0x80 to invoke
                    // Return value in x0
                    
                    // macOS syscall: read(int fd, void *buf, size_t count)
                    // syscall number: 3 (BSD read)
                    // fd: 0 (STDIN_FILENO)
                    mov x16, #3
                    mov x0, #0
                    ldr x1, [sp]
                    ldr x2, [sp, #8]
                    svc #0x80
                } : "r"(bytes_read) : "r"(buffer), "r"(count)
                  : "x0","x1","x2","x3","x4","x5",
                    "x6","x7","x8","x9","x10","x11",
                    "x12","x13","x14","x15","x16",
                    "x17","memory";
#endif; // ARCH ARM64

                if (bytes_read <= 0)
                {
                    return 0;
                };

                for (int i; i < max_len; i++)
                {
                    if (buffer[i] == '\n' | buffer[i] == '\r')
                    {
                        buffer[i] = '\0';
                    };
                };

                return bytes_read;
            };
#endif; // MACOS

// INPUT WRAPPER
            def input(byte[] buffer, int max_len) -> int
            {
#ifdef __WINDOWS__
                return win_input(buffer, max_len);
#endif; // WINDOWS
#ifdef __LINUX__
                return nix_input(buffer, max_len);
#endif; // LINUX
#ifdef __MACOS__
                return mac_input(buffer, max_len);
#endif; // MACOS
            };
// INPUT WRAPPER END

// OUTPUT FUNCTIONS BEGIN
#ifdef __WINDOWS__
            def win_print(byte* msg, int x) -> void
            {
#ifdef __ARCH_X86_64__
                volatile asm
                {
                    // BOOL ok = WriteFile(WIN_STDOUT_HANDLE, msg, x, NULL, NULL)
                    movq $2, %rcx           // RCX = WIN_STDOUT_HANDLE (operand 2)
                    movq $0, %rdx           // RDX = lpBuffer (operand 0 = msg)
                    movl $1, %r8d           // R8D = nNumberOfBytesToWrite (operand 1 = x, DWORD)
                    xorq %r9, %r9           // R9 = lpNumberOfBytesWritten = NULL
                    subq $$40, %rsp         // 32 bytes shadow + 8 for 5th arg slot
                    movq %r9, 32(%rsp)      // *(rsp+32) = lpOverlapped = NULL
                    call WriteFile
                    addq $$40, %rsp
                } : : "r"(msg), "r"(x), "r"(WIN_STDOUT_HANDLE)
                    : "rax","rcx","rdx","r8","r9","r10","r11","memory";
#endif; // ARCH 86 64
#ifdef __ARCH_ARM64__
                volatile asm
                {
                    // Windows ARM64 calling convention:
                    // x0: Return value, also first parameter
                    // x1-x7: Parameters 2-8
                    // x8: Indirect result location / syscall number
                    // x9-x15: Temporary registers
                    // x16-x17: Intra-procedure-call scratch registers
                    // x18: Platform register (avoid)
                    // x19-x28: Callee-saved
                    // x29: Frame pointer
                    // x30: Link register
                    //chcp 65001
                    //utf8_test
                    
                    // GetStdHandle(STD_OUTPUT_HANDLE = -11)
                    mov x0, #-11             // STD_OUTPUT_HANDLE
                    bl GetStdHandle          // Call GetStdHandle
                    
                    mov x19, x0              // Save handle in callee-saved register
                    mov x0, x19              // hFile = handle
                    ldr x1, [sp]             // Get msg from stack (first parameter after x0)
                    ldr w2, [sp, #8]         // Get x from stack (32-bit)
                    mov x3, #0               // lpNumberOfBytesWritten = NULL
                    mov x4, #0               // lpOverlapped = NULL
                    
                    bl WriteFile             // Call WriteFile
                } : : "r"(msg), "r"(x) : "x0", "x1", "x2", "x3", "x4", "x5","x6","x7",
                                         "x8", "x9", "x10","x11","x12","x13",
                                         "x14","x15","x16","x17","x19","memory";
#endif; // ARCH ARM
                return;
            };

            def reset_from_input() -> void
            {
                char bs = 8;
                win_print(@bs,1);
                win_print(@bs,1);
                return;
            };
#endif; // WINDOWS

#ifdef __LINUX__
            def nix_print(byte* msg, int x) -> void
            {
                // Convert count to 64-bit for syscall
                i64 count = x;

#ifdef __ARCH_X86_64__
                volatile asm
                {
                    // Linux syscall: write(int fd, const void *buf, size_t count)
                    // syscall number: 1 (write)
                    // fd: 1 (STDOUT_FILENO)
                    // buf: msg
                    // count: count (64-bit)
                    
                    movq $$1, %rax
                    movq $$1, %rdi
                    movq $0, %rsi
                    movq $1, %rdx
                    syscall
                } : : "r"(msg), "r"(count) : "rax","rdi","rsi","rdx","rcx","r11","memory";
#endif; // ARCH 86 64
#ifdef __ARCH_ARM64__
                volatile asm
                {
                    // Linux ARM64 syscall convention:
                    // x8: syscall number
                    // x0-x5: parameters
                    // Return value in x0
                    
                    // Linux syscall: write(int fd, const void *buf, size_t count)
                    // syscall number: 64 (write)
                    // fd: 1 (STDOUT_FILENO)
                    // buf: msg
                    // count: count (64-bit)
                    
                    mov x8, #64
                    mov x0, #1
                    ldr x1, [sp]
                    ldr x2, [sp, #8]
                    svc #0
                } : : "r"(msg), "r"(count) : "x0","x1","x2","x3","x4","x5",
                                              "x6","x7","x8","x9","x10","x11",
                                              "x12","x13","x14","x15","x16",
                                              "x17","memory";
#endif; // ARCH ARM
                return;
            };
#endif; // LINUX

#ifdef __MACOS__
            def mac_print(byte* msg, int x) -> void
            {
                int count = x;

#ifdef __ARCH_X86_64__
                volatile asm
                {
                    // macOS x86_64 (Darwin) syscall convention:
                    // - Syscall number in rax
                    // - Parameters: rdi, rsi, rdx, r10, r8, r9 (similar to Linux)
                    // - Use syscall instruction (same as Linux)
                    // - Syscall numbers are different from Linux
                    
                    // macOS syscall: write(int fd, const void *buf, size_t count)
                    // syscall number: 0x2000004 (write)
                    // Note: macOS adds 0x2000000 to BSD syscall numbers
                    // BSD write syscall is 4, so macOS = 0x2000004
                    // fd: 1 (STDOUT_FILENO)
                    // buf: msg
                    // count: count (64-bit)
                    
                    movq $$0x2000004, %rax
                    movq $$1, %rdi
                    movq $0, %rsi
                    movq $1, %rdx
                    syscall
                } : : "r"(msg), "r"(count) : "rax","rdi","rsi","rdx","r10","r8","r9","rcx","r11","memory";
#endif; // ARCH 86 64
#ifdef __ARCH_ARM64__
                volatile asm
                {
                    mov x0, #1
                    mov x1, $0
                    mov x2, $1
                    movz x16, #0x4
                    svc #0x80
                } : : "r"(msg), "r"(count) : "x0","x1","x2","x16","memory";
#endif; // ARCH ARM
                return;
            };
#endif; // MACOS

            // GENERIC (noopstr)
    		def print(noopstr s, int len) -> void
    		{
#ifdef __WINDOWS__
                win_print(@s, len);
#endif;
#ifdef __LINUX__
                nix_print(@s, len);
#endif;
#ifdef __MACOS__
                mac_print(@s, len);
#endif;
    			(void)s;
    			return;
    		};

            def print(noopstr s) -> void
            {
                int len = standard::strings::strlen(@s);

#ifdef __WINDOWS__
                win_print(@s, len);
#endif;
#ifdef __LINUX__
                nix_print(@s, len);
#endif;
#ifdef __MACOS__
                mac_print(@s, len);
#endif;
                (void)s;
                return;
            };

            def print(bool b) -> void
            {
                if (b) { print("True\0"); } else { print("False\0"); };
            };
            def print(i8 s) -> void
            {
                print(byte(s));
            };
            def print(byte s) -> void
            {
                byte[2] x = [s, 0];
                print(x);
                return;
            };
            def print(char s) -> void
            {
                char[2] x = [s, 0];
                print(x);
                return;
            };
            def print(int x) -> void
            {
                byte[21] buf;
                standard::strings::i32str(x,buf);
                print(buf);
                return;
            };
            def print(i16 x) -> void
            {
                byte[21] buf;
                standard::strings::i16str(x,buf);
                print(buf);
                return;
            };
            def print(u16 x) -> void
            {
                byte[21] buf;
                standard::strings::u16str(x,buf);
                print(buf);
                return;
            };
            def print(i32 x) -> void
            {
                byte[21] buf;
                standard::strings::i32str(x,buf);
                print(buf);
                return;
            };
            def print(u32 x) -> void
            {
                byte[21] buf;
                standard::strings::u32str(x,buf);
                print(buf);
                return;
            };
            def print(i64 x) -> void
            {
                byte[21] buf;
                standard::strings::i64str(x,buf);
                print(buf);
                return;
            };
            def print(u64 x) -> void
            {
                byte[21] buf;
                standard::strings::u64str(x,buf);
                print(buf);
                return;
            };
            def print(long x) -> void
            {
                print((i64)x);
                return;
            };
            def print(ulong x) -> void
            {
                print((u64)x);
                return;
            };
            def print(float x) -> void
            {
                byte[256] buffer;
                standard::strings::float2str(x, @buffer, 5);
                print(buffer);
                return;
            };
            def print(float x, int y) -> void
            {
                byte[256] buffer;
                if (y > 5) { y = 5; };
                standard::strings::float2str(x, @buffer, y);
                print(buffer);
                return;
            };
            def print(double x) -> void
            {
                byte[256] buffer;
                standard::strings::dbl2str(x, @buffer, 14);
                print(buffer);
                return;
            };
            def print(double x, int y) -> void
            {
                byte[256] buffer;
                if (y > 14) { y = 14; };
                standard::strings::dbl2str(x, @buffer, y);
                print(buffer);
                return;
            };
            // Newline print versions
            def println(noopstr s) -> void
            {
                standard::io::console::print(s);
                standard::io::console::print();
            };
            def println(byte s) -> void
            {
                standard::io::console::print(s);
                standard::io::console::print();
            };
            def println(char s) -> void
            {
                standard::io::console::print(s);
                standard::io::console::print();
            };
            def println(bool x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(i8 x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(i16 x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(u16 x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(int x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(i32 x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(uint x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(u32 x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def printhbline(byte s) -> void
            {
                standard::io::console::print(s);
                standard::io::console::print();
            };
            def println(long x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(ulong x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(float x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(float x, int y) -> void
            {
                standard::io::console::print(x, y);
                standard::io::console::print();
            };
            def println(double x) -> void
            {
                standard::io::console::print(x);
                standard::io::console::print();
            };
            def println(double x, int y) -> void
            {
                standard::io::console::print(x, y);
                standard::io::console::print();
            };
            
            def print_hex_byte(byte b) -> void
            {
                byte high = (b >> 4) & 0x0F;
                if (high < 10)
                {
                    print((byte)('0' + high));
                }
                else
                {
                    print((byte)('a' + (high - 10)));
                };
                
                byte low = b & 0x0F;
                if (low < 10)
                {
                    print((byte)('0' + low));
                }
                else
                {
                    print((byte)('a' + (low - 10)));
                };
                return;
            };
            def print_hex(u32 value) -> void
            {
                // Print as 8 hex digits
                byte b;
                b = (byte)((value >> 24) & 0xFF);
                print_hex_byte(b);
                b = (byte)((value >> 16) & 0xFF);
                print_hex_byte(b);
                b = (byte)((value >> 8) & 0xFF);
                print_hex_byte(b);
                b = (byte)(value & 0xFF);
                print_hex_byte(b);
                return;
            };

            def print_hex(byte* buf, int len) -> void
            {
                int i;
                byte hi, lo;
                for (i = 0; i < len; i++)
                {
                    hi = (buf[i] >> 4) & (byte)0x0F;
                    lo = buf[i] & (byte)0x0F;
                    if (hi < (byte)10) { print('0' + hi); } else { print('A' + (hi - (byte)10)); };
                    if (lo < (byte)10) { print('0' + lo); } else { print('A' + (lo - (byte)10)); };
                };
            };

            // GENERIC (no param = newline)
            def print() -> void
            {
#ifdef __WINDOWS__
                win_print("\r\n", 2);
#endif;
#ifdef __LINUX__
                nix_print("\n", 1);
#endif;
#ifdef __MACOS__
                mac_print("\n", 1);
#endif;
                return;
            };
        };      // CONSOLE //

                // FILE //
                // NEEDS MAJOR UPGRADE //
        namespace file
        {
#ifdef __WINDOWS__
            // File access modes (dwDesiredAccess)
            #def GENERIC_READ 0x80000000;
            #def GENERIC_WRITE 0x40000000;
            #def GENERIC_READ_WRITE 0xC0000000;
            
            // File share modes (dwShareMode)
            #def FILE_SHARE_READ 0x00000001;
            #def FILE_SHARE_WRITE 0x00000002;
            #def FILE_SHARE_DELETE 0x00000004;
            
            // File creation disposition (dwCreationDisposition)
            #def CREATE_NEW 1;
            #def CREATE_ALWAYS 2;
            #def OPEN_EXISTING 3;
            #def OPEN_ALWAYS 4;
            #def TRUNCATE_EXISTING 5;
            
            // File attributes (dwFlagsAndAttributes)
            #def FILE_ATTRIBUTE_NORMAL 0x80;
            #def FILE_ATTRIBUTE_ARCHIVE 0x20;
            
            // Invalid handle value
            #def INVALID_HANDLE_VALUE -1;
       
            // FORWARD DECLARATIONS
            def win_open(byte* path, u32 access, u32 share, u32 disposition, u32 attributes) -> i64;
            def win_read(i64 handle, byte* buffer, u32 bytes_to_read) -> i32;
            def win_write(i64 handle, byte* buffer, u32 bytes_to_write) -> i32;
            def win_close(i64 handle) -> i32;
            
            // IMPLEMENTATIONS
            
            // CreateFileA - Opens or creates a file
            // Returns: File handle (i64), or INVALID_HANDLE_VALUE on failure
            def win_open(byte* path, u32 access, u32 share, u32 disposition, u32 attributes) -> i64
            {
                i64 handle = INVALID_HANDLE_VALUE;

                volatile asm
                {
                    // Save path to RCX (first parameter)
                    movq $0, %rcx           // lpFileName (path)
                    
                    // Save access to RDX (second parameter)
                    movl $1, %edx           // dwDesiredAccess (access) - 32-bit
                    
                    // Save share to R8 (third parameter)
                    movl $2, %r8d           // dwShareMode (share) - 32-bit
                    
                    // Set R9 to NULL for lpSecurityAttributes (fourth parameter)
                    xorq %r9, %r9           // lpSecurityAttributes = NULL
                    
                    // Allocate stack space: 32 bytes shadow + 24 bytes for 3 parameters
                    subq $$56, %rsp
                    
                    // Save disposition to stack (fifth parameter)
                    movl $3, %eax           // Get disposition
                    movl %eax, 32(%rsp)     // dwCreationDisposition
                    
                    // Save attributes to stack (sixth parameter)
                    movl $4, %eax           // Get attributes
                    movl %eax, 40(%rsp)     // dwFlagsAndAttributes
                    
                    // Set hTemplateFile to NULL (seventh parameter)
                    xorq %rax, %rax
                    movq %rax, 48(%rsp)     // hTemplateFile = NULL
                    
                    // Call CreateFileA
                    call CreateFileA
                    
                    // Store result
                    movq %rax, $5           // Store in 'handle' variable
                    
                    // Clean up stack
                    addq $$56, %rsp
                } : : "r"(path), "r"(access), "r"(share), "r"(disposition), "r"(attributes), "m"(handle)
                  : "rax","rcx","rdx","r8","r9","r10","r11","memory";
                
                return handle;
            };
            
            // ReadFile - Reads data from a file
            // Returns: Number of bytes actually read, or -1 on error
            def win_read(i64 handle, byte* buffer, u32 bytes_to_read) -> i32
            {
                u32 bytes_read = 0;
                u32* bytes_read_ptr = @bytes_read;
                i32 success = 0;
                
                volatile asm
                {
                    // Save handle to RCX (first parameter)
                    movq $0, %rcx           // hFile (handle)
                    
                    // Save buffer to RDX (second parameter)
                    movq $1, %rdx           // lpBuffer (buffer)
                    
                    // Save bytes_to_read to R8 (third parameter)
                    movl $2, %r8d           // nNumberOfBytesToRead
                    
                    // Save bytes_read_ptr to R9 (fourth parameter)
                    movq $3, %r9            // lpNumberOfBytesRead
                    
                    // Allocate stack space: 32 bytes shadow + 8 bytes for 5th parameter
                    subq $$40, %rsp
                    
                    // Set lpOverlapped to NULL (fifth parameter)
                    xorq %rax, %rax
                    movq %rax, 32(%rsp)     // lpOverlapped = NULL
                    
                    // Call ReadFile
                    call ReadFile
                    
                    // Store success flag
                    movl %eax, $4           // Store in 'success' variable
                    
                    // Clean up stack
                    addq $$40, %rsp
                } : : "r"(handle), "r"(buffer), "r"(bytes_to_read), "r"(bytes_read_ptr), "m"(success)
                  : "rax","rcx","rdx","r8","r9","r10","r11","memory";
                
                if (success == 0)
                {
                    return -1;
                };
                
                return (i32)bytes_read;
            };
            
            // WriteFile - Writes data to a file
            // Returns: Number of bytes actually written, or -1 on error
            def win_write(i64 handle, byte* buffer, u32 bytes_to_write) -> i32
            {
                u32 bytes_written = 0;
                u32* bytes_written_ptr = @bytes_written;
                i32 success = 0;
                
                volatile asm
                {
                    // Save handle to RCX (first parameter)
                    movq $0, %rcx           // hFile (handle)
                    
                    // Save buffer to RDX (second parameter)
                    movq $1, %rdx           // lpBuffer (buffer)
                    
                    // Save bytes_to_write to R8 (third parameter)
                    movl $2, %r8d           // nNumberOfBytesToWrite
                    
                    // Save bytes_written_ptr to R9 (fourth parameter)
                    movq $3, %r9            // lpNumberOfBytesWritten
                    
                    // Allocate stack space: 32 bytes shadow + 8 bytes for 5th parameter
                    subq $$40, %rsp
                    
                    // Set lpOverlapped to NULL (fifth parameter)
                    xorq %rax, %rax
                    movq %rax, 32(%rsp)     // lpOverlapped = NULL
                    
                    // Call WriteFile
                    call WriteFile
                    
                    // Store success flag
                    movl %eax, $4           // Store in 'success' variable
                    
                    // Clean up stack
                    addq $$40, %rsp
                } : : "r"(handle), "r"(buffer), "r"(bytes_to_write), "r"(bytes_written_ptr), "m"(success)
                  : "rax","rcx","rdx","r8","r9","r10","r11","memory";
                
                if (success == 0)
                {
                    return -1;
                };
                
                return (i32)bytes_written;
            };
            
            // CloseHandle - Closes a file handle
            // Returns: 1 on success, 0 on failure
            def win_close(i64 handle) -> i32
            {
                i32 result = 0;
                
                volatile asm
                {
                    // Save handle to RCX (first parameter)
                    movq $0, %rcx           // hObject (handle)
                    
                    // Allocate shadow space
                    subq $$32, %rsp
                    
                    // Call CloseHandle
                    call CloseHandle
                    
                    // Store result
                    movl %eax, $1           // Store in 'result' variable
                    
                    // Clean up stack
                    addq $$32, %rsp
                } : : "r"(handle), "m"(result)
                  : "rax","rcx","rdx","r8","r9","r10","r11","memory";
                
                return result;
            };
            
            // HELPER FUNCTIONS - Simplified wrappers
            //
            // Open file for reading
            def open_read(byte* path) -> i64
            {
                return win_open(path, (i32)GENERIC_READ, (i32)FILE_SHARE_READ, (i32)OPEN_EXISTING, (i32)FILE_ATTRIBUTE_NORMAL);
            };
            //
            // Open file for writing (creates if doesn't exist, truncates if exists)
            def open_write(byte* path) -> i64
            {
                return win_open(path, (i32)GENERIC_WRITE, (i32)0, (i32)CREATE_ALWAYS, (i32)FILE_ATTRIBUTE_NORMAL);
            };
            //
            // Open file for appending (creates if doesn't exist)
            def open_append(byte* path) -> i64
            {
                return win_open(path, (i32)GENERIC_WRITE, (i32)FILE_SHARE_READ, (i32)OPEN_ALWAYS, (i32)FILE_ATTRIBUTE_NORMAL);
            };
            //
            // Open file for reading and writing
            def open_read_write(byte* path) -> i64
            {
                return win_open(path, (i32)GENERIC_READ_WRITE, (i32)FILE_SHARE_READ, (i32)OPEN_ALWAYS, (i32)FILE_ATTRIBUTE_NORMAL);
            };
            //
#endif; // Windows

#ifdef __LINUX__
            extern
            {
                def !!
                    fseek(void* stream, long offset, int whence) -> int,
                    ftell(void* stream) -> long,
                    rewind(void* stream) -> void,
                    fread(void* ptr, ulong size, ulong count, void* stream) -> ulong,
                    fclose(void* stream) -> int;
            };
#endif;
        };
    };
};

#endif;