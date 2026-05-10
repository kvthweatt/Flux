#import "standard.fx";
#import "sys.fx";

using standard::io::console;

// EXCEPTION_POINTERS layout (x64):
//   0  void*  ExceptionRecord
//   8  void*  ContextRecord
//
// EXCEPTION_RECORD layout (partial):
//   0  u32    ExceptionCode
//   4  u32    ExceptionFlags
//   8  void*  ExceptionRecord (chained)
//  16  void*  ExceptionAddress
//  24  u32    NumberParameters
//  28  u32    _pad
//  32  u64[2] ExceptionInformation  (for AV: [0]=read(0)/write(1), [1]=fault addr)

byte*[256] as jmp_buf;

extern
{
    def !!setjmp(byte*) -> int;
};

def !!longjmp(byte* env, int val) -> void
{
    volatile asm
    {
        movq   (%rcx), %rbx
        movq  8(%rcx), %rsp
        movq 16(%rcx), %rbp
        movq 24(%rcx), %rsi
        movq 32(%rcx), %rdi
        movq 40(%rcx), %r12
        movq 48(%rcx), %r13
        movq 56(%rcx), %r14
        movq 64(%rcx), %r15
        movl %edx, %eax
        testl %eax, %eax
        jnz  .Lret
        movl $1, %eax
    .Lret:
        jmpq *72(%rcx)
    } : : "r"(env), "r"(val) : "rax", "rbx", "rsp", "rbp", "rsi", "rdi",
                                "r12", "r13", "r14", "r15", "memory";
};

def !!__intrinsic_setjmp(byte* env, void* frame) -> int
{
    return setjmp(env);
};

struct EXCEPTION_RECORD_PARTIAL
{
    u32   ExceptionCode,
          ExceptionFlags;
    void* ChainedRecord,
          ExceptionAddress;
    u32   NumberParameters,
          _pad;
    u64   AccessType,
          FaultAddress;
};

struct EXCEPTION_POINTERS
{
    EXCEPTION_RECORD_PARTIAL* ExceptionRecord;
    void*                     ContextRecord;
};

// Return values for the handler
const long EXCEPTION_CONTINUE_EXECUTION = -1,
           EXCEPTION_CONTINUE_SEARCH    =  0,
           EXCEPTION_EXECUTE_HANDLER    =  1;

const u32 EXCEPTION_ACCESS_VIOLATION = 0xC0000005u;

// Our handler — fastcall, no-mangle so GetProcAddress/callback ABI matches
def !!segfault_handler(EXCEPTION_POINTERS* ep) -> long
{
    if (ep.ExceptionRecord.ExceptionCode == EXCEPTION_ACCESS_VIOLATION)
    {
        u64 resume = __flux_resume_addr;

        // If no try block is active, don't handle it
        if (resume == 0u) { return EXCEPTION_CONTINUE_SEARCH; };

        u64 fault_addr = ep.ExceptionRecord.FaultAddress;

        __flux_exc_value  = fault_addr;
        __flux_exc_active = 1;

        // Clear resume addr BEFORE patching Rip, so a fault inside the
        // landing block itself doesn't re-enter this handler recursively
        __flux_resume_addr = 0u;

        u64 ctx_base = (u64)ep.ContextRecord;
        u64* rip_ptr = (u64*)(ctx_base + 248u);
        *rip_ptr = resume;

        return EXCEPTION_CONTINUE_EXECUTION;
    };

    return EXCEPTION_CONTINUE_SEARCH;
};

// Load AddVectoredExceptionHandler via GetProcAddress at runtime
def register_segfault_handler() -> bool
{
    void* kernel32 = LoadLibraryA("kernel32.dll");
    if (kernel32 == void) { return false; };

    void* fn_ptr = GetProcAddress(kernel32, "AddVectoredExceptionHandler");
    if (fn_ptr == void) { return false; };

    // AddVectoredExceptionHandler(ULONG First, PVECTORED_EXCEPTION_HANDLER Handler) -> void*
    def{}* aveh(u32, void*) -> void* = @fn_ptr;
    aveh(1u, @segfault_handler);

    return true;
};

def main() -> int
{
    register_segfault_handler();

    try
    {
        int* bad = (int*)0;
        int  x   = *bad;    // will segfault
    }
    catch (auto e)
    {
        println("Caught fault at address:\0");
        println((long)e);
    };

    return 0;
};