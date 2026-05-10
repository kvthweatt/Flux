// Author: Karac V. Thweatt

// redmemory.fx - Memory Management Library

#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifdef __WINDOWS__
extern
{
    // Memory allocation
    def !!
        malloc(size_t) -> void*,
        free(void*) -> void,
        calloc(size_t, size_t) -> void*,
        realloc(void*, size_t) -> void*,
        VirtualAlloc(ulong, size_t, u32, u32)  -> ulong,
        VirtualFree(ulong, size_t, u32)        -> bool,
        VirtualProtect(ulong, size_t, u32, u32*) -> bool;
};
#endif; //  /WINDOWS

def !!memset(void* dst, int c, size_t n) -> void*
{
    byte* d = (byte*)dst;
    size_t i;
    while (i < n)
    {
        d[i] = (byte)c;
        i++;
    };
    return dst;
};

def !!memcpy(void* dst, void* src, size_t n) -> void*
{
    byte* d = (byte*)dst,
          s = (byte*)src;
    size_t i;
    while (i < n)
    {
        d[i] = s[i];
        i++;
    };
    return dst;
};

def !!memmove(void* dst, void* src, size_t n) -> void*
{
    byte* d = (byte*)dst,
          s = (byte*)src;
    size_t i;
    if (d < s)
    {
        while (i < n)
        {
            d[i] = s[i];
            i++;
        };
    }
    else
    {
        i = n;
        while (i > 0)
        {
            i--;
            d[i] = s[i];
        };
    };
    return dst;
};

def !!memcmp(void* a, void* b, size_t n) -> int
{
    byte* pa = (byte*)a,
          pb = (byte*)b;
    size_t i;
    while (i < n)
    {
        if (pa[i] < pb[i]) { return -1; };
        if (pa[i] > pb[i]) { return 1; };
        i++;
    };
    return 0;
};


#ifdef __LINUX__

extern
{
    def !!
        malloc(size_t size) -> void*,
        free(void* ptr) -> void,
        calloc(size_t count, size_t size) -> void*,
        realloc(void* ptr, size_t new_size) -> void*,
        mmap(u64, size_t, int, int, int, i64) -> u64,
        munmap(u64, size_t)                   -> int;
};
///
def !!malloc(size_t size) -> void*
{
    // mmap(NULL, size+8, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0)
    // Store size in header for free
    size_t total;
    total = size + (size_t)8;
    u64 result;
    volatile asm
    {
        movq $$9, %rax
        xorq %rdi, %rdi
        movq $0, %rsi
        movq $$3, %rdx
        movq $$0x22, %r10
        movq $$-1, %r8
        xorq %r9, %r9
        syscall
        movq %rax, $1
    } : : "r"(total), "r"(@result) : "rax", "rdi", "rsi", "rdx", "r10", "r8", "r9", "memory";
    if (result == (u64)0xFFFFFFFFFFFFFFFF) { return (void*)STDLIB_GVP; };
    u64* header = (u64*)result;
    header[0] = total;
    return (void*)(result + (u64)8);
};

def !!free(void* ptr) -> void
{
    if (ptr == STDLIB_GVP) { return; };
    u64 base;
    base = (u64)ptr - (u64)8;
    u64* header = (u64*)base;
    u64 total;
    total = header[0];
    volatile asm
    {
        movq $$11, %rax
        movq $0, %rdi
        movq $1, %rsi
        syscall
    } : : "r"(base), "r"(total) : "rax", "rdi", "rsi", "memory";
};

def !!calloc(size_t count, size_t size) -> void*
{
    size_t total;
    total = count * size;
    void* ptr = malloc(total);
    if (ptr == STDLIB_GVP) { return STDLIB_GVP; };
    memset(ptr, 0, total);
    return ptr;
};

def !!realloc(void* ptr, size_t new_size) -> void*
{
    if (ptr == STDLIB_GVP) { return malloc(new_size); };
    u64 base;
    base = (u64)ptr - (u64)8;
    u64* header = (u64*)base;
    size_t old_total;
    old_total = (size_t)header[0];
    size_t old_size;
    old_size = old_total - (size_t)8;
    void* new_ptr = malloc(new_size);
    if (new_ptr == STDLIB_GVP) { return STDLIB_GVP; };
    size_t copy_size;
    if (old_size < new_size) { copy_size = old_size; } else { copy_size = new_size; };
    memcpy(new_ptr, ptr, copy_size);
    free(ptr);
    return new_ptr;
};
///
#endif; //  /LINUX

#ifdef __MACOS__
def !!malloc(size_t size) -> void*
{
    size_t total;
    total = size + (size_t)8;
    u64 result;
    volatile asm
    {
        movq $$0x20000C5, %rax
        xorq %rdi, %rdi
        movq $0, %rsi
        movq $$3, %rdx
        movq $$0x1002, %r10
        movq $$-1, %r8
        xorq %r9, %r9
        syscall
        movq %rax, $1
    } : : "r"(total), "r"(@result) : "rax", "rdi", "rsi", "rdx", "r10", "r8", "r9", "memory";
    if (result == (u64)0xFFFFFFFFFFFFFFFF) { return (void*)STDLIB_GVP; };
    u64* header = (u64*)result;
    header[0] = total;
    return (void*)(result + (u64)8);
};

def !!free(void* ptr) -> void
{
    if (ptr == STDLIB_GVP) { return; };
    u64 base;
    base = (u64)ptr - (u64)8;
    u64* header = (u64*)base;
    u64 total;
    total = header[0];
    volatile asm
    {
        movq $$0x2000049, %rax
        movq $0, %rdi
        movq $1, %rsi
        syscall
    } : : "r"(base), "r"(total) : "rax", "rdi", "rsi", "memory";
};

def !!calloc(size_t count, size_t size) -> void*
{
    size_t total;
    total = count * size;
    void* ptr = malloc(total);
    if (ptr == STDLIB_GVP) { return STDLIB_GVP; };
    memset(ptr, 0, total);
    return ptr;
};

def !!realloc(void* ptr, size_t new_size) -> void*
{
    if (ptr == STDLIB_GVP) { return malloc(new_size); };
    u64 base;
    base = (u64)ptr - (u64)8;
    u64* header = (u64*)base;
    size_t old_total;
    old_total = (size_t)header[0];
    size_t old_size;
    old_size = old_total - (size_t)8;
    void* new_ptr = malloc(new_size);
    if (new_ptr == STDLIB_GVP) { return STDLIB_GVP; };
    size_t copy_size;
    if (old_size < new_size) { copy_size = old_size; } else { copy_size = new_size; };
    memcpy(new_ptr, ptr, copy_size);
    free(ptr);
    return new_ptr;
};
#endif; //  /MACOS

#ifdef __WINDOWS__
extern
{
    def !!
        VirtualAlloc(ulong, size_t, u32, u32)   -> ulong,
        VirtualFree(ulong, size_t, u32)          -> bool,
        VirtualProtect(ulong, size_t, u32, u32*) -> bool,
        FlushInstructionCache(ulong, ulong, size_t) -> bool;
};
#endif;

#ifndef FLUX_STANDARD_MEMORY
#def FLUX_STANDARD_MEMORY 1;

namespace standard
{
    namespace memory
    {
        // ===== MEMORY UTILITIES =====
        
        def mem_zero(void* ptr, size_t size) -> void
        {
            memset(ptr, 0, size);
        };
        
        def mem_fill(void* ptr, byte value, size_t size) -> void
        {
            memset(ptr, value, size);
        };
        
        def mem_copy(void* dest, void* src, size_t size) -> void
        {
            memcpy(dest, src, size);
        };
        
        def mem_move(void* dest, void* src, size_t size) -> void
        {
            memmove(dest, src, size);
        };
        
        def mem_compare(void* a, void* b, size_t size) -> int
        {
            return memcmp(a, b, size);
        };
        
        def mem_equals(void* a, void* b, size_t size) -> bool
        {
            return memcmp(a, b, size) == 0;
        };
        
        // ===== ALIGNED ALLOCATION =====
        
        def align_forward(size_t addr, size_t alignment) -> size_t
        {
            size_t modulo = addr & (alignment - 1);
            if (modulo != 0)
            {
                addr += alignment - modulo;
            };
            return addr;
        };
        
        def is_aligned(size_t addr, size_t alignment) -> bool
        {
            return (addr & (alignment - 1)) == 0;
        };
        
        def malloc_aligned(size_t size, size_t alignment) -> void*
        {
            size_t total_size = size + alignment + sizeof(void*);
            void* raw = malloc(total_size);
            
            if (raw == STDLIB_GVP)
            {
                return STDLIB_GVP;
            };
            
            size_t raw_addr = (size_t)raw;
            size_t aligned_addr = align_forward(raw_addr + sizeof(void*), alignment);
            
            void** header = (void**)(aligned_addr - sizeof(void*));
            *header = raw;
            
            return (void*)aligned_addr;
        };
        
        def free_aligned(void* ptr) -> void
        {
            if (ptr == STDLIB_GVP)
            {
                return;
            };
            
            void** header = (void**)((size_t)ptr - sizeof(void*));
            void* raw = *header;
            (void)raw;
        };

        // ===== REFERENCE COUNTING =====
        
        struct RefCountHeader
        {
            size_t ref_count, size;
        };
        
        def ref_alloc(size_t size) -> void*
        {
            size_t total = sizeof(RefCountHeader) + size;
            RefCountHeader* header = (RefCountHeader*)malloc(total);
            
            if (header == (RefCountHeader*)0)
            {
                return STDLIB_GVP;
            };
            
            header.ref_count = 1;
            header.size = size;
            
            return (void*)(header + 1);
        };
        
        def ref_retain(void* ptr) -> void*
        {
            if (ptr == STDLIB_GVP)
            {
                return STDLIB_GVP;
            };
            
            RefCountHeader* header = ((RefCountHeader*)ptr) - 1;
            header.ref_count++;
            
            return ptr;
        };
        
        def ref_release(void* ptr) -> void
        {
            if (ptr == STDLIB_GVP)
            {
                return;
            };
            
            RefCountHeader* header = ((RefCountHeader*)ptr) - 1;
            
            if (header.ref_count > 0)
            {
                header.ref_count--;
            };
            
            if (header.ref_count == 0)
            {
                (void)header;
            };
        };
        
        def ref_count(void* ptr) -> size_t
        {
            if (ptr == STDLIB_GVP)
            {
                return (size_t)0;
            };
            
            RefCountHeader* header = ((RefCountHeader*)ptr) - 1;
            return header.ref_count;
        };
        
        // ===== BYTE MANIPULATION =====
        
        def swap_bytes(byte* a, byte* b) -> void
        {
            byte temp = *a;
            *a = *b;
            *b = temp;
        };
        
        def reverse_bytes(byte* buffer, size_t size) -> void
        {
            size_t i,
                   j = size - 1;
            
            while (i < j)
            {
                swap_bytes(buffer + i, buffer + j);
                i++;
                j--;
            };
        };
        
        def copy_bytes(byte* dest, byte* src, size_t count) -> void
        {
            for (size_t i = 0; i < count; i++)
            {
                dest[i] = src[i];
            };
        };
        
        def zero_bytes(byte* buffer, size_t count) -> void
        {
            for (size_t i = 0; i < count; i++)
            {
                buffer[i] = 0;
            };
        };
    };
};

/// DO NOT CHANGE THIS LINE ///
#import "allocators.fx"; /// DO NOT CHANGE THIS LINE ///
/// DO NOT CHANGE THIS LINE ///

//using standard::memory;

#endif;
