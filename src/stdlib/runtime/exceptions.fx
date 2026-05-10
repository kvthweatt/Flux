// ============================================================
//  exceptions.fx  -  Flux exceptions library  (Windows x86-64)
//
//  Provides:
//    : __intrinsic_setjmp / setjmp / longjmp  (pure inline ASM)
//    : Vectored Exception Handler registration (Win32 FFI)
//    : __exc_push / __exc_pop  (jmp_buf guard helpers)
//
//  Hardware faults caught:
//    0xC0000005  EXCEPTION_ACCESS_VIOLATION
//    0xC0000094  EXCEPTION_INT_DIVIDE_BY_ZERO
//    0xC000001D  EXCEPTION_ILLEGAL_INSTRUCTION
//    0xC00000FD  EXCEPTION_STACK_OVERFLOW
//
//  Usage:
//    #import "exceptions.fx";
//    exceptions::init();           // once at program start
//
//    exceptions::jmp_buf buf;
//    long rc = exceptions::__exc_push(@buf);
//    switch (rc)
//    {
//        case (0)
//        {
//            int* bad = (int*)0;
//            int  x   = *bad;      // hardware fault -> longjmp -> rc=1
//            exceptions::__exc_pop();
//        }
//        default
//        {
//            exceptions::__exc_pop();
//            println(exceptions::__exc_fault_addr());
//        };
//    };
// ============================================================

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_EXCEPTIONS
#def FLUX_STANDARD_EXCEPTIONS 1;

        // ----------------------------------------------------------
        //  Win32 FFI
        // ----------------------------------------------------------
        extern
        {
            stdcall !! AddVectoredExceptionHandler(uint first, void* handler) -> void*;
            stdcall !! RemoveVectoredExceptionHandler(void* handle) -> uint;
        };

namespace standard
{
    namespace exceptions
    {
        // ----------------------------------------------------------
        //  jmp_buf  - 10 × 8-byte slots (80 bytes)
        //
        //  Slot  Offset  Register  Notes
        //  ----  ------  --------  --------------------------------
        //   0    0x00    RBX       non-volatile
        //   1    0x08    RBP       frame pointer
        //   2    0x10    RSI       non-volatile
        //   3    0x18    RDI       non-volatile
        //   4    0x20    RSP       caller's pre-call RSP (RSP+8 at point of call)
        //   5    0x28    R12       non-volatile
        //   6    0x30    R13       non-volatile
        //   7    0x38    R14       non-volatile
        //   8    0x40    R15       non-volatile
        //   9    0x48    RIP       return address sitting at [RSP] at point of call
        // ----------------------------------------------------------
        struct jmp_buf
        {
            long[10] regs;
        };


        // ----------------------------------------------------------
        //  Internal state
        // ----------------------------------------------------------
        jmp_buf*  _active_buf  = (jmp_buf*)0;
        long      _fault_addr  = 0;
        void*     _handler_ptr = (void*)0;

        // ----------------------------------------------------------
        //  _setjmp_impl
        //
        //  Snapshots all Windows x64 non-volatile registers into buf,
        //  then stores 0 into *out.
        //
        //  $0 = jmp_buf*   buf
        //  $1 = long*      out
        //
        //  We move both inputs into RSI/RDI first to free RCX/RDX,
        //  then save RSI's original call-time value (= buf ptr) into
        //  slot 2.  That stored value is used by longjmp purely to
        //  restore the ABI register state; the pointer arithmetic is
        //  done through R11 in longjmp, not through the restored RSI.
        // ----------------------------------------------------------
        def _setjmp_impl(jmp_buf* buf, long* out) -> void
        {
            #ifdef __ARCH_X86_64__
            volatile asm
            {
                movq  $0,    %rsi            // rsi  = buf
                movq  $1,    %rdi            // rdi  = out
                movq  %rbx,  0x00(%rsi)
                movq  %rbp,  0x08(%rsi)
                movq  %rsi,  0x10(%rsi)      // save RSI (its value here = buf ptr, but that's fine)
                movq  %rdi,  0x18(%rsi)      // save RDI (its value here = out ptr)
                leaq  0x08(%rsp), %rax       // caller's RSP before the call pushed ret addr
                movq  %rax,  0x20(%rsi)
                movq  %r12,  0x28(%rsi)
                movq  %r13,  0x30(%rsi)
                movq  %r14,  0x38(%rsi)
                movq  %r15,  0x40(%rsi)
                movq  (%rsp), %rax           // return address = saved RIP
                movq  %rax,  0x48(%rsi)
                movq  $$0,   (%rdi)          // *out = 0
            } : : "r"(buf), "r"(out) : "rax", "rsi", "rdi", "memory";
            #endif;
        };

        // ----------------------------------------------------------
        //  __intrinsic_setjmp
        // ----------------------------------------------------------
        def !! __intrinsic_setjmp(jmp_buf* buf) -> long
        {
            long result;
            _setjmp_impl(buf, @result);
            return result;
        };

        // ----------------------------------------------------------
        //  setjmp
        // ----------------------------------------------------------
        def !! setjmp(jmp_buf* buf) -> long
        {
            return __intrinsic_setjmp(buf);
        };

        // ----------------------------------------------------------
        //  longjmp
        //
        //  $0 = jmp_buf*   buf
        //  $1 = long       val   (clamped to 1 if 0)
        //
        //  Strategy:
        //    1. Move buf into R11 (volatile scratch in Windows x64).
        //       R11 survives the RSI/RDI restore because it is not
        //       one of the slots we are restoring.
        //    2. Clamp val to 1 if it is 0.
        //    3. Restore RBX, RBP, R12-R15.
        //    4. Stash saved RIP into RAX (we need it after RSP changes).
        //    5. Restore RDI then RSI from their saved slots.
        //    6. Restore RSP from slot 4 (R11 still valid here).
        //    7. Write saved RIP into the new [RSP] (ret address slot).
        //    8. Move val -> RAX and ret.  Execution resumes at the
        //       original setjmp call site with RAX = val.
        // ----------------------------------------------------------
        def !! longjmp(jmp_buf* buf, long val) -> void
        {
            #ifdef __ARCH_X86_64__
            volatile asm
            {
                movq  $0,    %r11            // r11 = buf  (volatile; safe scratch)
                movq  $1,    %rdx            // rdx = val

                // Clamp: val 0 -> 1
                testq %rdx,  %rdx
                jnz   .Ljmp_nonzero
                movq  $$1,   %rdx
            .Ljmp_nonzero:

                // Restore non-volatiles (all except RSI, RDI, RSP - those come later)
                movq  0x00(%r11), %rbx
                movq  0x08(%r11), %rbp
                movq  0x28(%r11), %r12
                movq  0x30(%r11), %r13
                movq  0x38(%r11), %r14
                movq  0x40(%r11), %r15

                // Stash saved RIP in RAX before RSP is restored
                movq  0x48(%r11), %rax

                // Restore RDI then RSI - R11 still holds buf after this
                movq  0x18(%r11), %rdi
                movq  0x10(%r11), %rsi

                // Restore RSP - R11 still valid (not a saved slot)
                movq  0x20(%r11), %rsp

                // Write saved RIP into the return-address slot and return
                movq  %rax,  (%rsp)
                movq  %rdx,  %rax            // RAX = return value
                ret
            } : : "r"(buf), "r"(val) : "rax", "rbx", "rbp", "rdx", "r11",
                                        "rsi", "rdi", "r12", "r13", "r14", "r15",
                                        "memory";
            #endif;
        };

        // ----------------------------------------------------------
        //  _veh_handler  (PVECTORED_EXCEPTION_HANDLER)
        //
        //  EXCEPTION_POINTERS (x64):
        //    +0x00  EXCEPTION_RECORD*
        //    +0x08  CONTEXT*            (ignored)
        //
        //  EXCEPTION_RECORD (relevant):
        //    +0x00  DWORD  ExceptionCode
        //    +0x14  DWORD  NumberParameters
        //    +0x18  ptr    ExceptionInformation[0]  (r/w flag, AV only)
        //    +0x20  ptr    ExceptionInformation[1]  (faulting VA, AV only)
        //
        //  Returns -1 (EXCEPTION_CONTINUE_EXECUTION) if handled,
        //           0 (EXCEPTION_CONTINUE_SEARCH) otherwise.
        // ----------------------------------------------------------
        stdcall !! _veh_handler(void* exc_ptrs) -> int
        {
            if (_active_buf == (jmp_buf*)0)
            {
                return 0;
            };

            long rec_ptr  = ((long*)exc_ptrs)[0];
            uint exc_code = ((uint*)rec_ptr)[0];

            switch (exc_code)
            {
                case (0xC0000005u)
                {
                    _fault_addr = ((long*)(rec_ptr + 0x20))[0];
                }
                case (0xC0000094u) { _fault_addr = 0; }
                case (0xC000001Du) { _fault_addr = 0; }
                case (0xC00000FDu) { _fault_addr = 0; }
                default
                {
                    return 0;
                };
            };

            // Disarm *before* longjmp so re-entrant faults pass through.
            jmp_buf* buf = _active_buf;
            _active_buf  = (jmp_buf*)0;
            longjmp(buf, 1);

            return -1;
        };

        // ----------------------------------------------------------
        //  __exc_push  -  arm guard, snapshot call site.
        //  Returns 0 initially; returns 1 after a hardware fault.
        // ----------------------------------------------------------
def !! __exc_push(jmp_buf* buf) -> long
{
    _active_buf = buf;
    _fault_addr = 0;

    long result;
    volatile asm
    {
        movq  $1,    %r11
        movq  %rbx,  0x00(%r11)
        movq  %rbp,  0x08(%r11)
        movq  %rsi,  0x10(%r11)
        movq  %rdi,  0x18(%r11)
        leaq  0x10(%rbp), %rax       // caller's RSP (rbp+16, ABI-stable)
        movq  %rax,  0x20(%r11)
        movq  %r12,  0x28(%r11)
        movq  %r13,  0x30(%r11)
        movq  %r14,  0x38(%r11)
        movq  %r15,  0x40(%r11)
        movq  0x08(%rbp), %rax       // return address to caller (rbp+8, ABI-stable)
        movq  %rax,  0x48(%r11)
        xorq  %rax,  %rax            // RAX = 0 on normal path
    } : "={rax}"(result) : "r"(buf) : "r11", "memory";

    return result;
};

        // ----------------------------------------------------------
        //  __exc_pop  -  disarm the guard.
        // ----------------------------------------------------------
        def !! __exc_pop() -> void
        {
            _active_buf = (jmp_buf*)0;
        };

        // ----------------------------------------------------------
        //  __exc_fault_addr  -  faulting VA from last AV; 0 for non-AV.
        // ----------------------------------------------------------
        def !! __exc_fault_addr() -> long
        {
            return _fault_addr;
        };

        // ----------------------------------------------------------
        //  init  -  register VEH handler; call once at program start.
        // ----------------------------------------------------------
        def seh_init() -> void
        {
            _handler_ptr = AddVectoredExceptionHandler(1u, (void*)@standard::exceptions::_veh_handler);
        };

        // ----------------------------------------------------------
        //  shutdown  -  deregister; optional.
        // ----------------------------------------------------------
        def seh_shutdown() -> void
        {
            if (_handler_ptr != (void*)0)
            {
                RemoveVectoredExceptionHandler(_handler_ptr);
                _handler_ptr = (void*)0;
            };
        };
    };
};

#endif;