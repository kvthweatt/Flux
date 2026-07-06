#!/usr/bin/env python3
"""
Flux Virtual Machine (fvm.py)
Experimental comptime execution backend.

Copyright (C) 2026 Karac V. Thweatt
"""

import struct
import ctypes
import ctypes.util
import os
import sys
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Opcodes
# ---------------------------------------------------------------------------

class Op(Enum):
    # Stack
    PUSH        = auto()
    POP         = auto()
    DUP         = auto()
    SWAP        = auto()
    ROT         = auto()   # ROT  - a b c -> b c a
    OVER        = auto()   # OVER - a b   -> a b a

    # Arithmetic
    ADD         = auto()
    SUB         = auto()
    MUL         = auto()
    DIV         = auto()
    MOD         = auto()
    NEG         = auto()
    POW         = auto()
    ABS         = auto()   # ABS  - absolute value
    MIN         = auto()   # MIN  - pop two, push min
    MAX         = auto()   # MAX  - pop two, push max
    CLAMP       = auto()   # CLAMP - pop (val, lo, hi), push clamped

    # Bitwise
    BAND        = auto()
    BOR         = auto()
    BXOR        = auto()
    BNOT        = auto()
    SHL         = auto()
    SHR         = auto()
    ROTL        = auto()   # ROTL <width>  - rotate left by width bits
    ROTR        = auto()   # ROTR <width>  - rotate right by width bits
    BITREV      = auto()   # BITREV <width> - reverse bits within width
    POPCOUNT    = auto()   # POPCOUNT      - count set bits
    CLZ         = auto()   # CLZ <width>   - count leading zeros within width
    CTZ         = auto()   # CTZ <width>   - count trailing zeros
    BITSLICE    = auto()   # BITSLICE - pop end, pop start, pop val, push extracted bits

    # Comparison
    CMP_EQ      = auto()
    CMP_NE      = auto()
    CMP_LT      = auto()
    CMP_LE      = auto()
    CMP_GT      = auto()
    CMP_GE      = auto()

    # Logic
    AND         = auto()
    OR          = auto()
    NOT         = auto()

    # Control flow
    JMP         = auto()   # JMP <addr>
    JIF         = auto()   # JIF <addr>  - jump if truthy
    JNF         = auto()   # JNF <addr>  - jump if falsy
    JTABLE      = auto()   # JTABLE <default_addr> [addr0, addr1, ...] - jump table dispatch
    CALL        = auto()   # CALL <name> <argc>
    CALL_PTR    = auto()   # CALL_PTR <argc> - pop BYTES(func_name), call it
    RET         = auto()
    TAIL_SELF   = auto()   # TAIL_SELF <argc> - reset ip=0, reload args into slots 0..N-1, reuse frame
    HALT        = auto()

    # Exceptions (comptime try/catch/throw)
    THROW       = auto()   # THROW       - pop value, raise FluxThrowSignal(value)
    TRY_BEGIN   = auto()   # TRY_BEGIN <catch_addr>  - push exception handler entry point
    TRY_END     = auto()   # TRY_END     - pop exception handler (normal exit from try body)

    # Locals
    LOCAL_GET      = auto()   # LOCAL_GET <slot>
    LOCAL_SET      = auto()   # LOCAL_SET <slot>
    LOCAL_DEREF    = auto()   # LOCAL_DEREF    - pop PTR(slot), push locals[slot]
    LOCAL_DEREF_SET = auto()  # LOCAL_DEREF_SET - pop val, pop PTR(slot), locals[slot]=val
    GLOBAL_GET      = auto()   # GLOBAL_GET <name>  - push vm._globals[name]
    GLOBAL_SET      = auto()   # GLOBAL_SET <name>  - pop val, vm._globals[name] = val

    # Memory
    ALLOC       = auto()   # ALLOC - pop size, push pointer
    FREE        = auto()   # FREE  - pop pointer
    LOAD        = auto()   # LOAD <type_tag> <byte_size>
    STORE       = auto()   # STORE <type_tag> <byte_size>
    OFFSET      = auto()   # OFFSET - pop (ptr, n), push ptr+n

    # Structs / arrays
    STRUCT_NEW   = auto()   # STRUCT_NEW <type_name>  - push zero struct value (TTag.STRUCT)
    STRUCT_LOAD  = auto()   # STRUCT_LOAD <field>     - pop struct, push field value
    STRUCT_STORE = auto()   # STRUCT_STORE <field>    - pop val, pop struct, push updated struct
    ENUM_NEW     = auto()   # ENUM_NEW <type_name>    - push zero enum value (TTag.ENUM)
    ENUM_LOAD    = auto()   # ENUM_LOAD               - pop enum, push integer value
    ENUM_STORE   = auto()   # ENUM_STORE              - pop int, pop enum, push updated enum
    ARRAY_NEW    = auto()   # ARRAY_NEW <type_name> <count>
    ARRAY_LEN    = auto()   # ARRAY_LEN  - pop array, push element count
    ARRAY_LOAD   = auto()   # ARRAY_LOAD  - pop array, pop idx, push element
    ARRAY_STORE  = auto()   # ARRAY_STORE - pop val, pop idx, pop array, push updated array

    # Type introspection
    SIZEOF      = auto()   # SIZEOF <type_name>  - pushes size in bits
    TYPEOF      = auto()   # TYPEOF              - pushes type tag of top
    ALIGNOF     = auto()   # ALIGNOF <type_name>
    ENDIANOF    = auto()   # ENDIANOF <type_name>

    # IO
    IO_OPEN     = auto()   # (path, mode) -> handle
    IO_READ     = auto()   # (handle, size) -> bytes ptr
    IO_WRITE    = auto()   # (handle, bytes ptr, size)
    IO_CLOSE    = auto()   # (handle)

    # FFI
    FFI_LOAD    = auto()   # FFI_LOAD <lib_path> -> lib handle
    FFI_SYM     = auto()   # FFI_SYM <sym_name>  -> callable
    FFI_CALL    = auto()   # FFI_CALL <argc> <ret_type_tag>
    FFI_FREE    = auto()   # FFI_FREE            - unload lib

    # compiler.io built-ins
    COMPILER_PRINT      = auto()   # compiler.io.console.print(byte*)
    COMPILER_INPUT      = auto()   # compiler.io.console.input() -> byte*
    COMPILER_READFILE   = auto()   # compiler.io.readfile(path: byte*) -> byte*
    COMPILER_WRITEFILE      = auto()   # compiler.io.writefile(path: byte*, content: byte*, flags: byte*)
    COMPILER_FVM_DUMP       = auto()   # compiler.fvm.dump(path: byte*) - serialise current comptime to .fvm
    COMPILER_FVM_TRACE_BEGIN = auto()  # compiler.fvm.trace.begin() - enable per-instruction VM tracing
    COMPILER_FVM_TRACE_END   = auto()  # compiler.fvm.trace.end() - disable per-instruction VM tracing
    COMPILER_FVM_SETBP       = auto()  # compiler.fvm.setbp() - comptime breakpoint: print stack and pause
    COMPILER_IMPORT_STDLIB  = auto()   # compiler.import.stdlib(path)
    COMPILER_LOADLIB        = auto()   # compiler.fvm.loadlib(name, ext) - load a native library for asm symbol resolution
    COMPILER_IMPORT_LOCAL   = auto()   # compiler.import.local(path)
    COMPILER_FPM_PACKAGE    = auto()   # compiler.fpm.package(path)
    EXTERN_DECL             = auto()   # EXTERN_DECL <name> <ret_ttag> - register extern proto

    # String ops
    STR_LEN     = auto()   # STR_LEN     - push length of top string
    STR_CAT     = auto()   # STR_CAT     - pop two strings, push concatenated
    STR_SLICE   = auto()   # STR_SLICE   - pop (str, start, len), push substring
    STR_EQ      = auto()   # STR_EQ      - pop two strings, push 1 if equal
    STR_FIND    = auto()   # STR_FIND    - pop (haystack, needle), push offset or -1
    INT_TO_STR  = auto()   # INT_TO_STR  - pop integer, push string representation
    STR_TO_INT  = auto()   # STR_TO_INT  - pop string, push integer

    # Type conversion
    CAST        = auto()   # CAST <ttag>    - convert top value to target type
    BITCAST     = auto()   # BITCAST <ttag> - reinterpret bytes as target type

    # Diagnostics
    ASSERT      = auto()   # ASSERT      - pop value; if falsy abort with message
    WARN        = auto()   # WARN        - pop string; emit compiler warning
    PANIC       = auto()   # PANIC       - pop string; unconditional abort

    # Boundary crossing
    EMIT_CONST  = auto()   # pop value  -> ir.Constant
    EMIT_GLOBAL = auto()   # pop ptr    -> ir.GlobalVariable (static data)
    EMIT_TYPE   = auto()   # pop type tag -> LLVM type reference
    EMITFLUX    = auto()   # EMITFLUX <source_text> <var_names>
                           # Substitutes comptime locals into source_text and appends
                           # ('flux', substituted_text) to emit_results.
    INLINE_ASM  = auto()   # INLINE_ASM <body> <constraints> <n_inputs> <n_outputs> <output_names>
                           # Assembles and executes x86-64 AT&T inline asm at comptime.


# ---------------------------------------------------------------------------
# Type tags
# ---------------------------------------------------------------------------

class TTag(Enum):
    INT      = 'int'
    UINT     = 'uint'
    LONG     = 'long'
    ULONG    = 'ulong'
    FLOAT    = 'float'
    DOUBLE   = 'double'
    BOOL     = 'bool'
    BYTE     = 'byte'
    CHAR     = 'char'
    DATA     = 'data'
    PTR      = 'ptr'
    VOID     = 'void'
    STRUCT   = 'struct'
    ENUM     = 'enum'
    ARRAY    = 'array'
    BYTES    = 'bytes'    # raw VM heap bytes (IO read results)
    FFI_LIB  = 'ffi_lib'
    FFI_SYM  = 'ffi_sym'
    FILE     = 'file'


# ---------------------------------------------------------------------------
# Stack value
# ---------------------------------------------------------------------------

@dataclass
class Val:
    """
    A value on the VM stack.
    tag  : TTag       - the Flux type of this value
    data : Any        - Python representation:
                        int/bool/float for primitives,
                        int for PTR (offset into VM heap),
                        str for type-name tags (STRUCT, ARRAY),
                        bytes for BYTES,
                        ctypes handle for FFI_LIB/FFI_SYM,
                        file object for FILE.
    meta : dict       - optional extra (e.g. struct type name, element type,
                        bit width for DATA, endianness for be/le types).
    """
    tag:  TTag
    data: Any
    meta: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        return f'Val({self.tag.value}, {self.data!r})'


# ---------------------------------------------------------------------------
# Instruction
# ---------------------------------------------------------------------------

@dataclass
class Instr:
    op:      Op
    operands: List[Any] = field(default_factory=list)
    src_line: int = field(default=0, compare=False, repr=False)

    def __repr__(self):
        if self.operands:
            return f'{self.op.name} {self.operands}'
        return self.op.name


# ---------------------------------------------------------------------------
# Call frame
# ---------------------------------------------------------------------------

@dataclass
class CallFrame:
    func_name: str
    instructions: List[Instr]
    ip:      int = 0                              # instruction pointer
    locals:  List[Optional[Val]] = field(default_factory=list)
    ret_val: Optional[Val] = None
    # Stack of (catch_addr, stack_depth) pushed by TRY_BEGIN, popped by TRY_END/throw
    exception_handlers: List[tuple] = field(default_factory=list)


# ---------------------------------------------------------------------------
# VM heap
# ---------------------------------------------------------------------------

class VMHeap:
    """
    Simple bump allocator backed by a bytearray.
    Keeps a type-tag map so TYPEOF and bounds checks work.
    Free list is maintained for reuse.
    """
    DEFAULT_SIZE = 16 * 1024 * 1024  # 16 MB default

    def __init__(self, size: int = DEFAULT_SIZE):
        self._mem   = bytearray(size)
        self._size  = size
        self._bump  = 8              # start at offset 8, 0 is the null pointer
        self._allocs: Dict[int, int] = {}   # ptr -> byte_size
        self._tags:   Dict[int, TTag] = {}  # ptr -> TTag
        self._free_list: List[Tuple[int, int]] = []  # (ptr, size) freed blocks

    def alloc(self, byte_size: int, tag: TTag = TTag.PTR) -> int:
        """Allocate byte_size bytes, return pointer (offset into heap)."""
        if byte_size <= 0:
            raise VMError(f'VMHeap.alloc: invalid size {byte_size}')
        # Try free list first (first-fit)
        for i, (ptr, sz) in enumerate(self._free_list):
            if sz >= byte_size:
                self._free_list.pop(i)
                self._allocs[ptr] = byte_size
                self._tags[ptr]   = tag
                self._mem[ptr:ptr + byte_size] = bytearray(byte_size)
                return ptr
        # Bump allocate
        ptr = self._bump
        if ptr + byte_size > self._size:
            raise VMError(f'VMHeap: out of memory (requested {byte_size}, available {self._size - self._bump})')
        self._bump += byte_size
        # Align next alloc to 8 bytes
        self._bump = (self._bump + 7) & ~7
        self._allocs[ptr] = byte_size
        self._tags[ptr]   = tag
        return ptr

    def free(self, ptr: int):
        """Return allocation to free list."""
        if ptr not in self._allocs:
            raise VMError(f'VMHeap.free: invalid pointer {ptr}')
        sz = self._allocs.pop(ptr)
        self._tags.pop(ptr, None)
        self._free_list.append((ptr, sz))

    def read(self, ptr: int, byte_size: int) -> bytes:
        """Read byte_size bytes from ptr."""
        self._check(ptr, byte_size)
        return bytes(self._mem[ptr:ptr + byte_size])

    def write(self, ptr: int, data: bytes):
        """Write bytes to ptr."""
        self._check(ptr, len(data))
        self._mem[ptr:ptr + len(data)] = data

    def type_of(self, ptr: int) -> Optional[TTag]:
        return self._tags.get(ptr)

    def _check(self, ptr: int, size: int):
        if ptr < 8 or ptr + size > self._size:
            raise VMError(f'VMHeap: out-of-bounds access at ptr={ptr} size={size}')

    def snapshot(self, ptr: int, byte_size: int) -> bytes:
        """Snapshot a region for EMIT_GLOBAL serialization."""
        return bytes(self._mem[ptr:ptr + byte_size])


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class VMError(Exception):
    pass

class FluxThrowSignal(Exception):
    """Raised by the THROW opcode; carries the thrown Val for catch handlers."""
    def __init__(self, value):
        self.value = value
        super().__init__(repr(value))


# ---------------------------------------------------------------------------
# Struct layout cache
# ---------------------------------------------------------------------------

@dataclass
class StructLayout:
    name:       str
    fields:     List[Tuple[str, TTag, int, int]]  # (name, tag, byte_offset, byte_size)
    total_size: int
    endian:     str = 'little'
    total_bits: int = 0  # True bit-packed size (sum of raw field bit widths, no padding)


# ---------------------------------------------------------------------------
# FluxVM
# ---------------------------------------------------------------------------

class FluxVM:
    """
    Flux comptime virtual machine.

    Usage:
        vm = FluxVM(struct_layouts, type_sizes)
        result = vm.execute(instructions, functions)
    """

    def __init__(
        self,
        struct_layouts: Dict[str, StructLayout] = None,
        type_sizes:     Dict[str, int]          = None,
        heap_size:      int                     = VMHeap.DEFAULT_SIZE,
        source_file:    str                     = None,
    ):
        self.heap            = VMHeap(heap_size)
        self.stack:  List[Val]       = []
        self.frames: List[CallFrame] = []
        self.struct_layouts  = struct_layouts or {}
        self.type_sizes      = type_sizes     or {}   # type name -> byte size
        self._ffi_libs:  Dict[str, ctypes.CDLL] = {}
        self._io_handles: Dict[int, Any]         = {}
        self._io_next_handle: int                = 1
        # Registered comptime functions: name -> List[Instr]
        self._functions: Dict[str, List[Instr]]  = {}
        self._function_overloads: Dict[str, list] = {}
        # Source file path - used by compiler.import.* for relative path resolution
        self.source_file: str = source_file
        # FVMCodegen class injected by the host compiler for use in compiler.import.*
        self._codegen_class = None
        # Compiler macros (#def constants) from the host preprocessor
        self._compiler_constants: dict = {}
        # Pending LLVM emission results accumulated during execute()
        self.emit_results: List[Any] = []
        # Per-instruction VM tracing, toggled via compiler.fvm.trace.begin()/end()
        self._trace_enabled: bool = False
        self._trace_remaining: int = 0
        # Locals snapshot from the most recently executed top-level block
        self.last_locals: List[Any] = []
        self._comptime_log: List[List[Instr]] = []
        self._comptime_log_locals: int   = 0
        # Comptime block-level variables accessible across function call frames
        self._globals: dict = {}
        # Extern function prototypes registered via ExternBlock: name -> ret TTag
        self._extern_protos: dict = {}
        # OS-allocated pointers (from extern malloc etc.) tracked separately from VM heap
        self._os_ptrs: set = set()
        # Last source line number seen during execution (for error reporting)
        self._last_src_line: int = 0
        self._imported_sources: list = []  # list of (source_lines, line_map, filename)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_function(self, name: str, instructions: List[Instr]):
        """Register a comptime function by name."""
        self._functions[name] = instructions

    def execute(self, instructions: List[Instr], local_count: int = 0) -> Optional[Val]:
        """
        Execute a flat instruction list as the top-level comptime block.
        Returns the top-of-stack value after HALT, or None.
        """
        if local_count > self._comptime_log_locals:
            self._comptime_log_locals = local_count
        frame = CallFrame(
            func_name='<comptime>',
            instructions=instructions,
            locals=[None] * local_count,
        )
        self.frames.append(frame)
        result = self._run()
        block = [instr for instr in instructions if instr.op != Op.HALT]
        self._comptime_log.append(block)
        return result

    # ------------------------------------------------------------------
    # Execution loop
    # ------------------------------------------------------------------

    def _run(self) -> Optional[Val]:
        import time as _time
        _watchdog_start = _time.monotonic()
        _watchdog_limit = 300.0  # seconds (5 minutes)
        _instr_count = 0
        while self.frames:
            frame = self.frames[-1]
            if frame.ip >= len(frame.instructions):
                # Implicit return from frame
                self.frames.pop()
                continue
            instr = frame.instructions[frame.ip]
            frame.ip += 1
            if instr.src_line:
                self._last_src_line = instr.src_line
            _instr_count += 1
            if self._trace_enabled and self._trace_remaining > 0:
                _locals_dump = ', '.join(
                    f'[{i}]={v!r}' for i, v in enumerate(frame.locals) if v is not None
                )
                _stack_dump = ', '.join(repr(v) for v in self.stack[-4:])
                print(f'[VMTRACE] func={frame.func_name} line={instr.src_line} '
                      f'op={instr.op.name} operands={instr.operands} '
                      f'locals=[{_locals_dump}] stack=[{_stack_dump}]', flush=True)
                self._trace_remaining -= 1
                if self._trace_remaining == 0:
                    self._trace_enabled = False
                    print('[VMTRACE] trace limit reached, auto-disabling', flush=True)
            if _instr_count % 50000 == 0:
                if _time.monotonic() - _watchdog_start > _watchdog_limit:
                    _locals_dump = ', '.join(
                        f'[{i}]={v!r}' for i, v in enumerate(frame.locals) if v is not None
                    )
                    _stack_dump = ', '.join(repr(v) for v in self.stack[-6:])
                    raise VMError(
                        f'comptime execution exceeded {_watchdog_limit:.0f}s '
                        f'({_instr_count} instructions executed) in function '
                        f'{frame.func_name!r} at ip={frame.ip} — likely an infinite loop.\n'
                        f'  locals: {_locals_dump}\n'
                        f'  stack (top 6): {_stack_dump}\n'
                        f'Last executed source line is shown below.'
                    )
            try:
                self._dispatch(instr)
            except FluxThrowSignal as _throw:
                # Walk the frame stack (innermost first) looking for a
                # TRY_BEGIN handler. If found, restore the stack to the
                # depth at TRY_BEGIN time, push the thrown value, and
                # jump to the catch address. If no handler found, re-raise.
                _handled = False
                while self.frames:
                    _frame = self.frames[-1]
                    if _frame.exception_handlers:
                        _catch_addr, _stack_depth = _frame.exception_handlers.pop()
                        # Restore stack to the depth recorded at TRY_BEGIN
                        del self.stack[_stack_depth:]
                        self._push(_throw.value)
                        _frame.ip = _catch_addr
                        _handled = True
                        break
                    self.frames.pop()
                if not _handled:
                    raise VMError(f'Unhandled comptime throw: {_throw.value!r}')
        return self.stack[-1] if self.stack else None

    def _dispatch(self, instr: Instr):
        op = instr.op
        o  = instr.operands

        # Stack
        if   op == Op.PUSH:       self._push(o[0])
        elif op == Op.POP:        self._pop()
        elif op == Op.DUP:        self.stack.append(self.stack[-1])
        elif op == Op.SWAP:       self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]
        elif op == Op.ROT:        self._op_rot()
        elif op == Op.OVER:       self._push(self.stack[-2])

        # Arithmetic
        elif op == Op.ADD:        self._binop(lambda a, b: a + b)
        elif op == Op.SUB:        self._binop(lambda a, b: a - b)
        elif op == Op.MUL:        self._binop(lambda a, b: a * b)
        elif op == Op.DIV:        self._binop_div()
        elif op == Op.MOD:        self._binop(lambda a, b: a % b)
        elif op == Op.NEG:        self._unop(lambda a: -a)
        elif op == Op.POW:        self._binop(lambda a, b: a ** b)
        elif op == Op.ABS:        self._unop(lambda a: abs(a))
        elif op == Op.MIN:        self._binop(lambda a, b: a if a < b else b)
        elif op == Op.MAX:        self._binop(lambda a, b: a if a > b else b)
        elif op == Op.CLAMP:      self._op_clamp()

        # Bitwise
        elif op == Op.BAND:       self._binop(lambda a, b: a & b)
        elif op == Op.BOR:        self._binop(lambda a, b: a | b)
        elif op == Op.BXOR:       self._binop(lambda a, b: a ^ b)
        elif op == Op.BNOT:       self._unop(lambda a: ~a)
        elif op == Op.SHL:        self._binop(lambda a, b: a << b)
        elif op == Op.SHR:        self._binop(lambda a, b: a >> b)
        elif op == Op.ROTL:       self._op_rotl(o[0])
        elif op == Op.ROTR:       self._op_rotr(o[0])
        elif op == Op.BITREV:     self._op_bitrev(o[0])
        elif op == Op.POPCOUNT:   self._unop(lambda a: bin(a & ((1 << 64) - 1)).count('1'))
        elif op == Op.CLZ:        self._op_clz(o[0])
        elif op == Op.CTZ:        self._op_ctz(o[0])
        elif op == Op.BITSLICE:   self._op_bitslice()

        # Comparison
        elif op == Op.CMP_EQ:     self._cmp(lambda a, b: a == b)
        elif op == Op.CMP_NE:     self._cmp(lambda a, b: a != b)
        elif op == Op.CMP_LT:     self._cmp(lambda a, b: a <  b)
        elif op == Op.CMP_LE:     self._cmp(lambda a, b: a <= b)
        elif op == Op.CMP_GT:     self._cmp(lambda a, b: a >  b)
        elif op == Op.CMP_GE:     self._cmp(lambda a, b: a >= b)

        # Logic
        elif op == Op.AND:        self._binop(lambda a, b: int(bool(a) and bool(b)))
        elif op == Op.OR:         self._binop(lambda a, b: int(bool(a) or  bool(b)))
        elif op == Op.NOT:        self._unop(lambda a: int(not bool(a)))

        # Control flow
        elif op == Op.JMP:        self.frames[-1].ip = o[0]
        elif op == Op.JIF:        self._jif(o[0], truthy=True)
        elif op == Op.JNF:        self._jif(o[0], truthy=False)
        elif op == Op.JTABLE:     self._op_jtable(o[0], o[1])
        elif op == Op.CALL:       self._call(o[0], o[1])
        elif op == Op.CALL_PTR:   self._call_ptr(o[0])
        elif op == Op.RET:        self._ret()
        elif op == Op.TAIL_SELF:  self._tail_self(o[0])
        elif op == Op.HALT:
            if self.frames:
                self.last_locals = list(self.frames[0].locals)
            self.frames.clear()

        # Exception handling
        elif op == Op.THROW:
            raise FluxThrowSignal(self._pop())
        elif op == Op.TRY_BEGIN:  self._op_try_begin(o[0])
        elif op == Op.TRY_END:    self._op_try_end()

        # Locals
        elif op == Op.LOCAL_GET:      self._push(self.frames[-1].locals[o[0]])
        elif op == Op.LOCAL_SET:      self.frames[-1].locals[o[0]] = self._pop()
        elif op == Op.LOCAL_DEREF:    self._op_local_deref()
        elif op == Op.LOCAL_DEREF_SET: self._op_local_deref_set()
        elif op == Op.GLOBAL_GET:
            _gval = self._globals.get(o[0], Val(TTag.INT, 0))
            self._push(_gval)
        elif op == Op.GLOBAL_SET:
            _sv = self._pop()
            self._globals[o[0]] = _sv

        # Memory
        elif op == Op.ALLOC:      self._op_alloc()
        elif op == Op.FREE:       self._op_free()
        elif op == Op.LOAD:       self._op_load(o[0], o[1], o[2] if len(o) > 2 else None)
        elif op == Op.STORE:      self._op_store(o[0], o[1], o[2] if len(o) > 2 else '')
        elif op == Op.OFFSET:     self._op_offset()

        # Structs / arrays
        elif op == Op.STRUCT_NEW:   self._op_struct_new(o[0])
        elif op == Op.STRUCT_LOAD:  self._op_struct_load(o[0])
        elif op == Op.STRUCT_STORE: self._op_struct_store(o[0])
        elif op == Op.ENUM_NEW:     self._op_enum_new(o[0])
        elif op == Op.ENUM_LOAD:    self._op_enum_load()
        elif op == Op.ENUM_STORE:   self._op_enum_store()
        elif op == Op.ARRAY_NEW:    self._op_array_new(o[0], o[1])
        elif op == Op.ARRAY_LEN:    self._op_array_len()
        elif op == Op.ARRAY_LOAD:   self._op_array_load()
        elif op == Op.ARRAY_STORE:  self._op_array_store()

        # Type introspection
        elif op == Op.SIZEOF:     self._op_sizeof(o[0])
        elif op == Op.TYPEOF:     self._op_typeof()
        elif op == Op.ALIGNOF:    self._op_alignof(o[0])
        elif op == Op.ENDIANOF:   self._op_endianof(o[0])

        # IO
        elif op == Op.IO_OPEN:    self._op_io_open()
        elif op == Op.IO_READ:    self._op_io_read()
        elif op == Op.IO_WRITE:   self._op_io_write()
        elif op == Op.IO_CLOSE:   self._op_io_close()

        # FFI
        elif op == Op.FFI_LOAD:   self._op_ffi_load(o[0])
        elif op == Op.FFI_SYM:    self._op_ffi_sym(o[0])
        elif op == Op.FFI_CALL:   self._op_ffi_call(o[0], o[1])
        elif op == Op.FFI_FREE:   self._op_ffi_free()

        # compiler.io built-ins
        elif op == Op.COMPILER_PRINT:     self._op_compiler_print()
        elif op == Op.COMPILER_INPUT:     self._op_compiler_input()
        elif op == Op.COMPILER_READFILE:  self._op_compiler_readfile()
        elif op == Op.COMPILER_WRITEFILE: self._op_compiler_writefile()

        # String ops
        elif op == Op.STR_LEN:    self._op_str_len()
        elif op == Op.STR_CAT:    self._op_str_cat()
        elif op == Op.STR_SLICE:  self._op_str_slice()
        elif op == Op.STR_EQ:     self._op_str_eq()
        elif op == Op.STR_FIND:   self._op_str_find()
        elif op == Op.INT_TO_STR: self._op_int_to_str()
        elif op == Op.STR_TO_INT: self._op_str_to_int()

        # Type conversion
        elif op == Op.CAST:       self._op_cast(o[0], o[1] if len(o) > 1 else None)
        elif op == Op.BITCAST:    self._op_bitcast(o[0])

        # Diagnostics
        elif op == Op.ASSERT:     self._op_assert()
        elif op == Op.WARN:       self._op_warn()
        elif op == Op.PANIC:      self._op_panic()

        # Boundary crossing
        elif op == Op.EMIT_CONST:  self._op_emit_const()
        elif op == Op.EMIT_GLOBAL: self._op_emit_global(o[0])
        elif op == Op.EMIT_TYPE:   self._op_emit_type()
        elif op == Op.EMITFLUX:             self._op_emitflux(o[0], o[1])
        elif op == Op.COMPILER_FVM_DUMP:    self._op_compiler_fvm_dump()
        elif op == Op.COMPILER_FVM_TRACE_BEGIN:
            self._trace_enabled = True
            self._trace_remaining = 2000
        elif op == Op.COMPILER_FVM_TRACE_END:
            self._trace_enabled = False
            self._trace_remaining = 0
        elif op == Op.COMPILER_FVM_SETBP:    self._op_compiler_fvm_setbp()
        elif op == Op.COMPILER_IMPORT_STDLIB: self._op_compiler_import_stdlib()
        elif op == Op.COMPILER_LOADLIB:       self._op_compiler_loadlib()
        elif op == Op.COMPILER_IMPORT_LOCAL:  self._op_compiler_import_local()
        elif op == Op.COMPILER_FPM_PACKAGE:   self._op_compiler_fpm_package()
        elif op == Op.EXTERN_DECL:            self._extern_protos[o[0]] = o[1]
        elif op == Op.INLINE_ASM:            self._op_inline_asm(o[0], o[1], o[2], o[3], o[4])

        else:
            raise VMError(f'Unknown opcode: {op}')

    # ------------------------------------------------------------------
    # Stack helpers
    # ------------------------------------------------------------------

    def _push(self, v: Val):
        self.stack.append(v)

    def _pop(self) -> Val:
        if not self.stack:
            raise VMError('Stack underflow')
        return self.stack.pop()

    def _peek(self) -> Val:
        if not self.stack:
            raise VMError('Stack underflow')
        return self.stack[-1]

    def _binop(self, fn):
        b = self._pop()
        a = self._pop()
        tag = a.tag
        # BYTES + int: pointer arithmetic -- pin bytes to native memory and return PTR
        if tag == TTag.BYTES and b.tag in (TTag.INT, TTag.UINT, TTag.LONG, TTag.ULONG):
            raw = a.data if isinstance(a.data, (bytes, bytearray)) else str(a.data).encode('utf-8')
            # Ensure null terminator so strlen-style loops terminate correctly
            if not raw or raw[-1] != 0:
                raw = raw + b'\x00'
            if not hasattr(self, '_pinned_bufs'):
                self._pinned_bufs = []
            buf = (ctypes.c_char * len(raw))(*raw)
            self._pinned_bufs.append(buf)
            base = ctypes.addressof(buf)
            self._os_ptrs.add(base)
            offset = int(b.data)
            self._push(Val(TTag.PTR, base + offset))
            return
        result = fn(a.data, b.data)
        result = self._wrap_int(tag, result)
        self._push(Val(tag, result))

    def _wrap_int(self, tag: 'TTag', value):
        """
        Wrap an arithmetic/bitwise result to the bit width implied by `tag`,
        matching Flux's fixed-width integer semantics (e.g. u64 multiply,
        shift, and XOR must wrap at 64 bits rather than growing as Python
        arbitrary-precision ints). Non-integer tags pass through unchanged.
        """
        if not isinstance(value, int) or isinstance(value, bool):
            return value
        _unsigned = (TTag.UINT, TTag.ULONG, TTag.BYTE, TTag.CHAR, TTag.BOOL, TTag.PTR, TTag.DATA)
        _signed   = (TTag.INT, TTag.LONG)
        if tag in _unsigned or tag in _signed:
            bits = self._ttag_byte_size(tag) * 8
            mask = (1 << bits) - 1
            value &= mask
            if tag in _signed and value >= (1 << (bits - 1)):
                value -= (1 << bits)
            return value
        return value

    def _binop_div(self):
        b = self._pop()
        a = self._pop()
        if b.data == 0:
            raise VMError('Division by zero in comptime')
        if a.tag in (TTag.FLOAT, TTag.DOUBLE):
            self._push(Val(a.tag, a.data / b.data))
        else:
            self._push(Val(a.tag, self._wrap_int(a.tag, int(a.data / b.data))))

    def _unop(self, fn):
        a = self._pop()
        self._push(Val(a.tag, self._wrap_int(a.tag, fn(a.data))))

    def _cmp(self, fn):
        b = self._pop()
        a = self._pop()
        self._push(Val(TTag.BOOL, int(fn(a.data, b.data))))

    def _jif(self, addr: int, truthy: bool):
        v = self._pop()
        if bool(v.data) == truthy:
            self.frames[-1].ip = addr

    # ------------------------------------------------------------------
    # Control flow
    # ------------------------------------------------------------------

    def _call(self, name: str, argc: int):
        self._call_depth = getattr(self, '_call_depth', 0) + 1
        # TEMP DIAGNOSTIC: auto-enable tracing on entry to table_raw_insert
        # (matches bare or namespace-qualified names like
        # standard__memory__allocators__stdheap__table_raw_insert).
        # if name == 'table_raw_insert' or name.endswith('__table_raw_insert'):
        #     self._trace_enabled = True
        #     self._trace_remaining = 400
        if name not in self._functions:
            # Suffix-match against namespace-qualified names registered at runtime
            # e.g. 'dt_from_unix_ms' matches 'standard__datetime__dt_from_unix_ms'
            suffix = '__' + name
            matches = [k for k in self._functions if k.endswith(suffix)]
            if len(matches) == 1:
                name = matches[0]
            elif len(matches) > 1:
                raise VMError(
                    f'Ambiguous comptime function: {name!r} matches {matches}')
            elif name in self._extern_protos:
                pass  # handled below via ctypes
            else:
                raise VMError(f'Unknown comptime function: {name!r}')
        if name in self._extern_protos:
            ret_tag = self._extern_protos[name]
            args = [self._pop() for _ in range(argc)]
            args.reverse()
            # Resolve symbol: check explicitly loaded libs first, then C runtime
            sym = None
            import sys as _sys
            for _lib in getattr(self, '_asm_libs', {}).values():
                try:
                    sym = getattr(_lib, name, None)
                    if sym is not None:
                        if ret_tag == TTag.PTR:
                            sym.restype = ctypes.c_void_p
                        break
                except (OSError, AttributeError):
                    continue
            if sym is None:
                _runtime_libs = (['msvcrt'] if _sys.platform == 'win32' else [None, 'c', 'libc.so.6'])
                for _lib in _runtime_libs:
                    try:
                        _dll = ctypes.CDLL(_lib)
                        sym = getattr(_dll, name, None)
                        if sym is not None:
                            if ret_tag == TTag.PTR:
                                sym.restype = ctypes.c_void_p
                            break
                    except OSError:
                        continue
            if sym is None:
                raise VMError(f'extern: symbol {name!r} not found in any loaded library')
            c_args = [self._val_to_ctype(a) for a in args]
            try:
                # Force c_void_p restype so ctypes returns full pointer-width value
                sym.restype = ctypes.c_void_p
                _raw = sym(*c_args)
                result = int(_raw) if _raw is not None else 0
                # Reinterpret as signed if needed
                if ret_tag in (TTag.INT, TTag.LONG) and result > 0x7FFFFFFFFFFFFFFF:
                    result = result - 0x10000000000000000
            except Exception as e:
                raise VMError(f'extern call {name!r}: {e}')
            if ret_tag == TTag.VOID:
                self._push(Val(TTag.VOID, 0))
            elif ret_tag == TTag.PTR:
                addr = int(result or 0) & 0xFFFFFFFFFFFFFFFF
                if addr:
                    self._os_ptrs.add(addr)
                    # Zero-initialize: Flux default behavior
                    # We track size from the call args if possible; use arg[0] as size hint
                    try:
                        _sz = int(args[0].data) if args else 0
                        if _sz > 0:
                            ctypes.memset(addr, 0, _sz)
                    except Exception:
                        pass
                self._push(Val(TTag.PTR, addr))
            else:
                # For integer return types, if the value looks like an OS address, track it
                val = int(result or 0)
                if ret_tag in (TTag.LONG, TTag.ULONG, TTag.INT, TTag.UINT) and val > 0xFFFF:
                    self._os_ptrs.add(val & 0xFFFFFFFFFFFFFFFF)
                self._push(Val(ret_tag, result))
            return
        args = [self._pop() for _ in range(argc)]
        args.reverse()
        # Arity-based overload resolution from __$-suffixed function names.
        # When calling e.g. 'print' with argc=1, prefer 'print__$byte' over
        # 'print__$byte_int' (argc=2). Collect all registered overload keys
        # matching this base name and pick the one whose suffix arg-count matches.
        _sig_prefix = name + '__$'
        _sig_suffix = '__' + name + '__$'
        _sig_matches = [k for k in self._functions if k.startswith(_sig_prefix)]
        if not _sig_matches:
            _sig_matches = [k for k in self._functions if '__$' in k and k[:k.index('__$')].endswith('__' + name)]
        if _sig_matches:
            def _sig_argc(key):
                sig = key[key.index('__$') + 3:]
                return len(sig.split('_')) if sig else 0
            _arity_matches = [k for k in _sig_matches if _sig_argc(k) == argc]
            if len(_arity_matches) == 1:
                name = _arity_matches[0]
            elif len(_arity_matches) > 1:
                # Tie-break by matching arg TTags against the sig tokens.
                # BYTES/PTR args prefer 'arr'/'ptr'-suffixed tokens; scalar args prefer plain tokens.
                def _sig_score(key):
                    sig = key[key.index('__$') + 3:]
                    tokens = sig.split('_') if sig else []
                    score = 0
                    for i, a in enumerate(args):
                        if i >= len(tokens):
                            break
                        tok = tokens[i]
                        if a.tag in (TTag.BYTES,) and tok.endswith('arr'):
                            score += 2
                        elif a.tag == TTag.PTR and tok.endswith('ptr'):
                            score += 2
                        elif a.tag not in (TTag.BYTES, TTag.PTR) and not tok.endswith(('arr', 'ptr')):
                            score += 1
                    return score
                best = max(_arity_matches, key=_sig_score)
                name = best
            # else: no arity matches, fall through to TTag dispatch below
        # Overload dispatch: if multiple overloads registered, pick best match by arg TTag.
        _overloads = self._function_overloads
        instrs = None
        if name in _overloads and len(_overloads[name]) > 1:
            _ttag_to_dt = {
                TTag.BOOL: 'bool', TTag.BYTE: 'byte', TTag.CHAR: 'char',
                TTag.INT: 'sint', TTag.UINT: 'uint',
                TTag.LONG: 'slong', TTag.ULONG: 'ulong',
                TTag.DATA: 'data', TTag.PTR: 'ptr', TTag.VOID: 'void',
            }
            arg_tags = [_ttag_to_dt.get(a.tag, '?') for a in args]
            best = None
            best_score = -1
            for _params, _instrs in _overloads[name]:
                if len(_params) != len(args):
                    continue
                score = 0
                for i, p in enumerate(_params):
                    pt = str(getattr(getattr(p, 'type_spec', None), 'base_type', '')).split('.')[-1].lower()
                    if arg_tags[i] == pt:
                        score += 2
                    elif arg_tags[i] in ('data', 'ulong', 'uint', 'sint', 'slong') and pt in ('data', 'ulong', 'uint', 'sint', 'slong'):
                        score += 1
                if score > best_score:
                    best_score = score
                    best = _instrs
            if best is not None:
                instrs = best
        if instrs is None:
            instrs = self._functions[name]
        # if name in ('strlen', 'win_print') or 'strlen' in name or 'win_print' in name or ('print' in name and 'console' in name):
        #     import sys as _sys; _sys.stderr.write(f'[DEBUG CALL] {name} argc={argc} args={args}\n'); _sys.stderr.flush()
        frame  = CallFrame(
            func_name=name,
            instructions=instrs,
            locals=list(args) + [None] * max(0, 32 - len(args)),
        )
        self.frames.append(frame)

    def _call_ptr(self, argc: int):
        """Pop BYTES(func_name) then call that function with argc args."""
        name_val = self._pop()
        name = (name_val.data.decode('utf-8')
                if isinstance(name_val.data, (bytes, bytearray))
                else str(name_val.data))
        self._call(name, argc)

    def _ret(self):
        frame = self.frames.pop()
        # Return value stays on the stack (already pushed by callee)
        # if 'strlen' in frame.func_name or ('print' in frame.func_name and 'console' in frame.func_name):
        #     import sys as _sys; _sys.stderr.write(f'[DEBUG RET] {frame.func_name} stack_top={self.stack[-1] if self.stack else None}\n'); _sys.stderr.flush()

    def _tail_self(self, argc: int):
        """TAIL_SELF <argc> - zero-stack-growth self tail-call.
        Pop argc args, reload them into slots 0..argc-1 of the current frame,
        then reset ip to 0. The current frame is reused entirely.
        """
        args = [self._pop() for _ in range(argc)]
        args.reverse()
        frame = self.frames[-1]
        for i, arg in enumerate(args):
            frame.locals[i] = arg
        frame.ip = 0

    # ------------------------------------------------------------------
    # Stack ops
    # ------------------------------------------------------------------

    def _op_local_deref(self):
        """Dereference a pointer: PTR(slot) -> local slot value, PTR(os_addr) -> byte at addr, BYTES -> byte at offset 0."""
        ptr_val = self._pop()
        if ptr_val.tag == TTag.BYTES:
            raw = ptr_val.data if isinstance(ptr_val.data, (bytes, bytearray)) else str(ptr_val.data).encode('utf-8')
            self._push(Val(TTag.BYTE, raw[0] if raw else 0))
            return
        addr = int(ptr_val.data)
        if self._ptr_is_os(addr):
            # OS pointer: read one byte
            try:
                byte_val = ctypes.string_at(ctypes.c_void_p(addr & 0xFFFFFFFFFFFFFFFF), 1)[0]
            except Exception:
                byte_val = 0
            self._push(Val(TTag.BYTE, byte_val))
            return
        # Slot-based deref (small integer = slot index)
        slot = addr
        val = self.frames[-1].locals[slot]
        if val is None:
            val = Val(TTag.INT, 0)
        self._push(val)

    def _op_local_deref_set(self):
        """Pop val and PTR(slot), store val into locals[slot]."""
        val     = self._pop()
        ptr_val = self._pop()
        slot    = int(ptr_val.data)
        self.frames[-1].locals[slot] = val

    def _op_rot(self):
        # a b c -> b c a
        if len(self.stack) < 3:
            raise VMError('ROT: stack underflow')
        c = self.stack.pop()
        b = self.stack.pop()
        a = self.stack.pop()
        self.stack.append(b)
        self.stack.append(c)
        self.stack.append(a)

    # ------------------------------------------------------------------
    # Arithmetic ops
    # ------------------------------------------------------------------

    def _op_clamp(self):
        hi  = self._pop()
        lo  = self._pop()
        val = self._pop()
        tag = val.tag
        v = val.data
        lo_v = lo.data
        hi_v = hi.data
        if v < lo_v:
            v = lo_v
        elif v > hi_v:
            v = hi_v
        self._push(Val(tag, v))

    # ------------------------------------------------------------------
    # Bitwise ops
    # ------------------------------------------------------------------

    def _op_rotl(self, width: int):
        shift_val = self._pop()
        val       = self._pop()
        n     = int(val.data)   & ((1 << width) - 1)
        shift = int(shift_val.data) % width
        result = ((n << shift) | (n >> (width - shift))) & ((1 << width) - 1)
        self._push(Val(val.tag, result))

    def _op_rotr(self, width: int):
        shift_val = self._pop()
        val       = self._pop()
        n     = int(val.data)   & ((1 << width) - 1)
        shift = int(shift_val.data) % width
        result = ((n >> shift) | (n << (width - shift))) & ((1 << width) - 1)
        self._push(Val(val.tag, result))

    def _op_bitrev(self, width: int):
        val    = self._pop()
        n      = int(val.data) & ((1 << width) - 1)
        result = 0
        for _ in range(width):
            result = (result << 1) | (n & 1)
            n >>= 1
        self._push(Val(val.tag, result))

    def _op_bitslice(self):
        # Stack order pushed by codegen: value, start, end (end on top)
        end_val   = self._pop()
        start_val = self._pop()
        arr_val   = self._pop()
        start = int(start_val.data)
        end   = int(end_val.data)
        num_bits = end - start + 1

        # Build a flat byte list from the source value, MSB-first (matching fcodegen).
        raw_bytes = []
        if arr_val.tag == TTag.ARRAY:
            elements = (arr_val.meta or {}).get('elements', [])
            for el in elements:
                raw_bytes.append(int(el.data) & 0xFF)
        elif arr_val.tag == TTag.BYTES and isinstance(arr_val.data, (bytes, bytearray)):
            raw_bytes = list(arr_val.data)
        elif arr_val.tag in (TTag.BYTE, TTag.INT, TTag.UINT, TTag.LONG, TTag.ULONG, TTag.DATA):
            # Integer: pack big-endian so bit 0 = MSB
            v = int(arr_val.data)
            bits_meta = (arr_val.meta or {}).get('bits')
            if bits_meta is not None:
                nbytes = (bits_meta + 7) // 8
            elif arr_val.tag == TTag.BYTE:
                nbytes = 1
            elif arr_val.tag in (TTag.INT, TTag.UINT):
                nbytes = 4
            elif arr_val.tag in (TTag.LONG, TTag.ULONG):
                nbytes = 8
            else:
                nbytes = (v.bit_length() + 7) // 8 or 1
            for i in range(nbytes):
                shift = (nbytes - 1 - i) * 8
                raw_bytes.append((v >> shift) & 0xFF)
        else:
            raise VMError(f'BITSLICE: unsupported value tag {arr_val.tag}')

        # Extract bits [start..end] from MSB-first flat byte layout.
        result = 0
        for bit_pos in range(start, end + 1):
            byte_idx   = bit_pos // 8
            bit_in_byte = bit_pos % 8
            if byte_idx < len(raw_bytes):
                # MSB of byte is bit 0 within that byte
                byte_val = raw_bytes[byte_idx]
                bit = (byte_val >> (7 - bit_in_byte)) & 1
            else:
                bit = 0
            result = (result << 1) | bit

        self._push(Val(TTag.DATA, result, {'bits': num_bits}))

    def _op_clz(self, width: int):
        val = self._pop()
        n   = int(val.data) & ((1 << width) - 1)
        if n == 0:
            self._push(Val(TTag.UINT, width))
            return
        count = 0
        mask  = 1 << (width - 1)
        while mask and not (n & mask):
            count += 1
            mask >>= 1
        self._push(Val(TTag.UINT, count))

    def _op_ctz(self, width: int):
        val = self._pop()
        n   = int(val.data) & ((1 << width) - 1)
        if n == 0:
            self._push(Val(TTag.UINT, width))
            return
        count = 0
        while not (n & 1):
            count += 1
            n >>= 1
        self._push(Val(TTag.UINT, count))

    # ------------------------------------------------------------------
    # Control flow ops
    # ------------------------------------------------------------------

    def _op_jtable(self, default_addr: int, table: list):
        idx_val = self._pop()
        idx     = int(idx_val.data)
        if 0 <= idx < len(table):
            self.frames[-1].ip = table[idx]
        else:
            self.frames[-1].ip = default_addr

    # ------------------------------------------------------------------
    # Memory ops
    # ------------------------------------------------------------------

    def _op_alloc(self):
        size_val = self._pop()
        ptr = self.heap.alloc(int(size_val.data), TTag.PTR)
        self._push(Val(TTag.PTR, ptr))

    def _op_free(self):
        ptr_val = self._pop()
        self.heap.free(int(ptr_val.data))

    def _op_load(self, tag: TTag, byte_size: int, type_name: str = None):
        ptr_val = self._pop()
        ptr     = int(ptr_val.data) & 0xFFFFFFFFFFFFFFFF
        if self._ptr_is_os(ptr):
            raw = ctypes.string_at(ctypes.c_void_p(ptr), byte_size)
        else:
            raw = self.heap.read(ptr, byte_size)
        if tag == TTag.STRUCT:
            # Reconstruct struct from raw bytes using layout
            if type_name is None:
                type_name = ptr_val.meta.get('struct_type') if ptr_val.meta else None
            if type_name is None:
                # Find layout by size
                type_name = next((n for n, l in self.struct_layouts.items()
                                  if l.total_size == byte_size), None)
            if type_name and type_name in self.struct_layouts:
                layout = self.struct_layouts[type_name]
                fields = {}
                for fname, ftag, foff, fsz in layout.fields:
                    fbytes = raw[foff:foff+fsz]
                    fields[fname] = Val(ftag, self._bytes_to_val(fbytes, ftag, fsz))
                self._push(Val(TTag.STRUCT, type_name, meta={'fields': fields}))
                return
            self._push(Val(TTag.STRUCT, raw))
            return
        data = self._bytes_to_val(raw, tag, byte_size)
        self._push(Val(tag, data))

    def _op_store(self, tag: TTag, byte_size: int, type_name: str = ''):
        val     = self._pop()
        ptr_val = self._pop()
        ptr     = int(ptr_val.data) & 0xFFFFFFFFFFFFFFFF
        raw     = self._val_to_bytes(val, byte_size, type_name=type_name)
        if self._ptr_is_os(ptr):
            ctypes.memmove(ctypes.c_void_p(ptr), raw, len(raw))
        else:
            self.heap.write(ptr, raw)

    def _op_offset(self):
        n       = self._pop()
        ptr_val = self._pop()
        self._push(Val(TTag.PTR, int(ptr_val.data) + int(n.data)))

    def _mem_read(self, addr: int, byte_size: int) -> bytes:
        """Read byte_size bytes from either OS memory or the VM heap."""
        addr = addr & 0xFFFFFFFFFFFFFFFF
        if self._ptr_is_os(addr):
            return ctypes.string_at(ctypes.c_void_p(addr), byte_size)
        return self.heap.read(addr, byte_size)

    def _mem_write(self, addr: int, raw: bytes):
        """Write raw bytes to either OS memory or the VM heap."""
        addr = addr & 0xFFFFFFFFFFFFFFFF
        if self._ptr_is_os(addr):
            ctypes.memmove(ctypes.c_void_p(addr), raw, len(raw))
        else:
            self.heap.write(addr, raw)

    # ------------------------------------------------------------------
    # Struct / array ops
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Struct ops
    # ------------------------------------------------------------------

    def _op_struct_new(self, type_name: str):
        layout = self._get_layout(type_name)
        _zero  = {TTag.BOOL: 0, TTag.BYTE: 0, TTag.CHAR: 0,
                  TTag.INT: 0, TTag.UINT: 0, TTag.LONG: 0, TTag.ULONG: 0,
                  TTag.FLOAT: 0.0, TTag.DOUBLE: 0.0, TTag.DATA: 0}
        fields = {f[0]: Val(f[1], _zero.get(f[1], 0)) for f in layout.fields}
        self._push(Val(TTag.STRUCT, type_name, meta={'fields': fields}))

    def _op_struct_load(self, field: str):
        sv = self._pop()
        if sv.tag == TTag.STRUCT:
            fields = sv.meta.get('fields', {})
            if field not in fields:
                raise VMError(f'STRUCT_LOAD: field {field!r} not found in struct {sv.data!r}')
            result = fields[field]
            # if field in ('frontier', 'base', 'capacity'):
            #     import sys as _sys; _sys.stderr.write(f'[DEBUG STRUCT_LOAD] {sv.data}.{field} = {result}\n'); _sys.stderr.flush()
            self._push(result)
        elif sv.tag == TTag.PTR and sv.meta and sv.meta.get('struct_type'):
            type_name = sv.meta['struct_type']
            layout = self._get_layout(type_name)
            fname, ftag, foff, fsz = self._find_field(layout, field)
            addr = int(sv.data) & 0xFFFFFFFFFFFFFFFF
            raw = self._mem_read(addr + foff, fsz)
            result = Val(ftag, self._bytes_to_val(raw, ftag, fsz))
            # if field in ('frontier', 'base', 'capacity'):
            #     import sys as _sys; _sys.stderr.write(f'[DEBUG STRUCT_LOAD PTR] {type_name}@{hex(addr)}.{field} = {result}\n'); _sys.stderr.flush()
            self._push(result)
        else:
            raise VMError(f'STRUCT_LOAD: expected STRUCT value, got {sv.tag}')

    def _op_struct_store(self, field: str):
        val = self._pop()
        sv  = self._pop()
        if sv.tag == TTag.STRUCT:
            new_fields = dict(sv.meta.get('fields', {}))
            new_fields[field] = val
            # if field in ('frontier', 'base', 'capacity'):
            #     import sys as _sys; _sys.stderr.write(f'[DEBUG STRUCT_STORE] {sv.data}.{field} = {val}\n'); _sys.stderr.flush()
            self._push(Val(TTag.STRUCT, sv.data, meta={'fields': new_fields}))
        elif sv.tag == TTag.PTR and sv.meta and sv.meta.get('struct_type'):
            type_name = sv.meta['struct_type']
            layout = self._get_layout(type_name)
            fname, ftag, foff, fsz = self._find_field(layout, field)
            addr = int(sv.data) & 0xFFFFFFFFFFFFFFFF
            raw = self._val_to_bytes(val, fsz)
            # if field in ('frontier', 'base', 'capacity'):
            #     import sys as _sys; _sys.stderr.write(f'[DEBUG STRUCT_STORE PTR] {type_name}@{hex(addr)}.{field} = {val} raw={raw.hex()}\n'); _sys.stderr.flush()
            self._mem_write(addr + foff, raw)
            # Push the pointer back unchanged so a subsequent LOCAL_SET
            # write-back of `sv` (the pointer itself) is a no-op.
            self._push(sv)
        else:
            raise VMError(f'STRUCT_STORE: expected STRUCT value, got {sv.tag}')

    # ------------------------------------------------------------------
    # Enum ops
    # ------------------------------------------------------------------

    def _op_enum_new(self, type_name: str):
        self._push(Val(TTag.ENUM, 0, meta={'enum_type': type_name}))

    def _op_enum_load(self):
        ev = self._pop()
        if ev.tag != TTag.ENUM:
            raise VMError(f'ENUM_LOAD: expected enum value, got {ev.tag}')
        self._push(Val(TTag.INT, int(ev.data)))

    def _op_enum_store(self):
        val = self._pop()
        ev  = self._pop()
        if ev.tag != TTag.ENUM:
            raise VMError(f'ENUM_STORE: expected enum value, got {ev.tag}')
        # val may be a type-name bytes tag (union discriminant) or an integer
        if isinstance(val.data, (bytes, bytearray)):
            stored = val.data.decode('utf-8', errors='replace')
        elif isinstance(val.data, str):
            stored = val.data
        else:
            stored = int(val.data)
        self._push(Val(TTag.ENUM, stored, meta=dict(ev.meta)))


    def _op_array_len(self):
        ptr_val = self._pop()
        count = ptr_val.meta.get('count', 0)
        self._push(Val(TTag.INT, count))

    def _op_array_new(self, type_name: str, count: int):
        elem_size = self._type_byte_size(type_name)
        etag      = _str_to_ttag(type_name)
        _zero     = {TTag.FLOAT: 0.0, TTag.DOUBLE: 0.0}
        elements  = [Val(etag, _zero.get(etag, 0)) for _ in range(count)]
        self._push(Val(TTag.ARRAY, count, meta={'elem_type': type_name, 'count': count,
                                                 'elem_size': elem_size, 'elements': elements}))

    def _ptr_is_os(self, addr: int) -> bool:
        """Return True if addr is an OS-allocated pointer (not a VM heap or slot address)."""
        return addr in self._os_ptrs or addr > self.heap._size

    def _os_read_byte(self, addr: int) -> int:
        return ctypes.string_at(ctypes.c_void_p(addr & 0xFFFFFFFFFFFFFFFF), 1)[0]

    def _os_write_byte(self, addr: int, byte_val: int):
        ctypes.memset(ctypes.c_void_p(addr), byte_val & 0xFF, 1)

    def _op_array_load(self):
        idx_val = self._pop()
        av      = self._pop()
        idx     = int(idx_val.data)
        if av.tag == TTag.PTR and isinstance(av.data, int):
            addr = int(av.data)
            # OS pointer (e.g. from malloc): use ctypes
            if self._ptr_is_os(addr):
                self._push(Val(TTag.BYTE, self._os_read_byte(addr + idx)))
                return
            # Slot-based PTR (from @var): deref slot then index
            frame = self.frames[-1] if self.frames else None
            if frame and addr < len(frame.locals):
                inner = frame.locals[addr]
                if inner is not None and inner.tag == TTag.PTR and self._ptr_is_os(int(inner.data)):
                    self._push(Val(TTag.BYTE, self._os_read_byte(int(inner.data) + idx)))
                    return
                if inner is not None and inner.tag == TTag.ARRAY:
                    av = inner
                elif inner is not None and inner.tag == TTag.PTR:
                    raw = self.heap.read(int(inner.data) + idx, 1)
                    self._push(Val(TTag.BYTE, raw[0]))
                    return
            else:
                raw = self.heap.read(addr + idx, 1)
                self._push(Val(TTag.BYTE, raw[0]))
                return
        # Handle native pointer stored with non-PTR tag (e.g. byte* from fmalloc)
        if isinstance(av.data, int) and av.data != 0:
            addr = av.data & 0xFFFFFFFFFFFFFFFF
            if addr > 0xFFFF:
                if self._ptr_is_os(addr):
                    self._push(Val(TTag.BYTE, self._os_read_byte(addr + idx)))
                    return
                raw = self.heap.read(addr + idx, 1)
                self._push(Val(TTag.BYTE, raw[0]))
                return
        # BYTES (byte* string literal): index directly into the Python bytes object
        if av.tag == TTag.BYTES and isinstance(av.data, (bytes, bytearray)):
            raw = av.data
            if idx < 0 or idx >= len(raw):
                self._push(Val(TTag.BYTE, 0))
                return
            self._push(Val(TTag.BYTE, raw[idx]))
            return
        elements = (av.meta or {}).get('elements')
        if elements is None:
            raise VMError('ARRAY_LOAD: array has no elements storage')
        if idx < 0 or idx >= len(elements):
            raise VMError(f'ARRAY_LOAD: index {idx} out of bounds (len={len(elements)})')
        self._push(elements[idx])

    def _op_array_store(self):
        val     = self._pop()
        idx_val = self._pop()
        av      = self._pop()
        idx     = int(idx_val.data)
        def _to_byte(v):
            if isinstance(v.data, int): return v.data & 0xFF
            if isinstance(v.data, (bytes, bytearray)): return v.data[0] & 0xFF
            if isinstance(v.data, str): return ord(v.data[0]) & 0xFF
            return 0
        if av.tag == TTag.PTR and isinstance(av.data, int):
            addr = int(av.data)
            # OS pointer (e.g. from malloc): use ctypes
            if self._ptr_is_os(addr):
                self._os_write_byte(addr + idx, _to_byte(val))
                self._push(av)
                return
            # Slot-based PTR: deref slot
            frame = self.frames[-1] if self.frames else None
            if frame and addr < len(frame.locals):
                inner = frame.locals[addr]
                if inner is not None and inner.tag == TTag.PTR:
                    inner_addr = int(inner.data)
                    if self._ptr_is_os(inner_addr):
                        self._os_write_byte(inner_addr + idx, _to_byte(val))
                    else:
                        self.heap.write(inner_addr + idx, bytes([_to_byte(val)]))
                    self._push(av)
                    return
                if inner is not None and inner.tag == TTag.ARRAY:
                    elements = list(inner.meta.get('elements', []))
                    if idx < 0 or idx >= len(elements):
                        raise VMError(f'ARRAY_STORE: index {idx} out of bounds (len={len(elements)})')
                    elements[idx] = val
                    new_meta = dict(inner.meta)
                    new_meta['elements'] = elements
                    frame.locals[addr] = Val(TTag.ARRAY, inner.data, meta=new_meta)
                    self._push(av)
                    return
            else:
                self.heap.write(addr + idx, bytes([_to_byte(val)]))
                self._push(av)
                return
        # Handle native pointer stored with non-PTR tag (e.g. byte* from fmalloc)
        if isinstance(av.data, int) and av.data != 0:
            addr = av.data & 0xFFFFFFFFFFFFFFFF
            if addr > 0xFFFF:
                if self._ptr_is_os(addr):
                    self._os_write_byte(addr + idx, _to_byte(val))
                    self._push(av)
                    return
                self.heap.write(addr + idx, bytes([_to_byte(val)]))
                self._push(av)
                return
        elements = list((av.meta or {}).get('elements', []))
        if idx < 0 or idx >= len(elements):
            raise VMError(f'ARRAY_STORE: index {idx} out of bounds (len={len(elements)}) av.tag={av.tag} av.data={av.data!r}')
        elements[idx] = val
        new_meta = dict(av.meta)
        new_meta['elements'] = elements
        self._push(Val(TTag.ARRAY, av.data, meta=new_meta))


    # ------------------------------------------------------------------
    # Type introspection
    # ------------------------------------------------------------------

    def _op_sizeof(self, type_name: str):
        bits = self._type_byte_size(type_name) * 8
        self._push(Val(TTag.UINT, bits))

    def _op_typeof(self):
        v = self._peek()
        self._push(Val(TTag.BYTES, v.tag.value.encode()))

    def _op_alignof(self, type_name: str):
        # Alignment mirrors byte size for primitives; use layout for structs
        if type_name in self.struct_layouts:
            layout = self.struct_layouts[type_name]
            # Alignment is the max field alignment (largest field size)
            align = max((f[3] for f in layout.fields), default=1)
        else:
            align = self._type_byte_size(type_name)
        self._push(Val(TTag.UINT, align))

    def _op_endianof(self, type_name: str):
        if type_name in self.struct_layouts:
            endian = self.struct_layouts[type_name].endian
        elif type_name.startswith('be'):
            endian = 'big'
        elif type_name.startswith('le'):
            endian = 'little'
        else:
            endian = 'little'   # Flux default
        self._push(Val(TTag.BYTES, endian.encode()))

    # ------------------------------------------------------------------
    # IO ops
    # ------------------------------------------------------------------

    def _op_io_open(self):
        mode_val = self._pop()
        path_val = self._pop()
        path     = self._read_vm_string(path_val)
        mode     = self._read_vm_string(mode_val)
        try:
            fh = open(path, mode)
        except OSError as e:
            raise VMError(f'IO_OPEN: {e}')
        handle = self._io_next_handle
        self._io_next_handle += 1
        self._io_handles[handle] = fh
        self._push(Val(TTag.FILE, handle))

    def _op_io_read(self):
        size_val   = self._pop()
        handle_val = self._pop()
        fh         = self._get_io_handle(int(handle_val.data))
        size       = int(size_val.data)
        raw        = fh.read(size) if size > 0 else fh.read()
        if isinstance(raw, str):
            raw = raw.encode()
        self._push(Val(TTag.BYTES, raw))

    def _op_io_write(self):
        size_val   = self._pop()
        ptr_val    = self._pop()
        handle_val = self._pop()
        fh         = self._get_io_handle(int(handle_val.data))
        size       = int(size_val.data)
        ptr        = int(ptr_val.data)
        raw        = self.heap.read(ptr, size)
        fh.write(raw)

    def _op_io_close(self):
        handle_val = self._pop()
        fh         = self._get_io_handle(int(handle_val.data))
        fh.close()
        del self._io_handles[int(handle_val.data)]

    def _get_io_handle(self, handle: int):
        if handle not in self._io_handles:
            raise VMError(f'IO: invalid file handle {handle}')
        return self._io_handles[handle]

    # ------------------------------------------------------------------
    # FFI ops
    # ------------------------------------------------------------------

    def _op_ffi_load(self, lib_path: str):
        try:
            lib = ctypes.CDLL(lib_path)
        except OSError as e:
            raise VMError(f'FFI_LOAD: {e}')
        self._ffi_libs[lib_path] = lib
        self._push(Val(TTag.FFI_LIB, lib_path))

    def _op_ffi_sym(self, sym_name: str):
        lib_val  = self._pop()
        lib_path = lib_val.data
        if lib_path not in self._ffi_libs:
            raise VMError(f'FFI_SYM: library {lib_path!r} not loaded')
        lib = self._ffi_libs[lib_path]
        try:
            sym = getattr(lib, sym_name)
        except AttributeError:
            raise VMError(f'FFI_SYM: symbol {sym_name!r} not found in {lib_path!r}')
        self._push(Val(TTag.FFI_SYM, sym, meta={'sym_name': sym_name}))

    def _op_ffi_call(self, argc: int, ret_tag: TTag):
        args    = [self._pop() for _ in range(argc)]
        args.reverse()
        sym_val = self._pop()
        sym     = sym_val.data
        # Marshal arguments to ctypes
        c_args  = [self._val_to_ctype(a) for a in args]
        result  = sym(*c_args)
        self._push(Val(ret_tag, result))

    def _op_ffi_free(self):
        lib_val  = self._pop()
        lib_path = lib_val.data
        if lib_path in self._ffi_libs:
            del self._ffi_libs[lib_path]

    # ------------------------------------------------------------------
    # Inline ASM execution
    # ------------------------------------------------------------------

    def _op_inline_asm(self, body: str, constraints: str, n_inputs: int, n_outputs: int, output_names: list):
        import platform as _platform, struct as _struct, re as _re
        # Platform / arch check
        machine = _platform.machine().lower()
        if machine not in ('x86_64', 'amd64'):
            raise VMError(f'INLINE_ASM: x86-64 required at comptime, got {machine!r}')

        try:
            import keystone as _ks
        except ImportError:
            raise VMError('INLINE_ASM: keystone-engine is not installed (pip install keystone-engine)')

        # Pop inputs in reverse order (last pushed = last input)
        input_vals = []
        for _ in range(n_inputs):
            input_vals.append(self._pop())
        input_vals.reverse()   # now input_vals[0] = first input operand ($N_out+0)

        # Windows vs Linux register assignments for integer args
        system = _platform.system()
        if system == 'Windows':
            arg_regs = ['%rcx', '%rdx', '%r8', '%r9']
        else:
            arg_regs = ['%rdi', '%rsi', '%rdx', '%rcx', '%r8', '%r9']

        # Build operand substitution table:
        # $0..$n_outputs-1  -> output operand registers (all %rax for now, one output)
        # $n_outputs..      -> input operand registers
        out_reg = '%rax'
        operand_map = {}
        for i in range(n_outputs):
            operand_map[i] = out_reg
        for i, val in enumerate(input_vals):
            reg_idx = i
            if reg_idx < len(arg_regs):
                operand_map[n_outputs + i] = arg_regs[reg_idx]
            else:
                raise VMError(f'INLINE_ASM: too many input operands (max {len(arg_regs)})')

        # Register name maps for different operand sizes
        _reg64 = {'%rcx': '%rcx', '%rdx': '%rdx', '%r8': '%r8',   '%r9': '%r9',
                  '%rdi': '%rdi', '%rsi': '%rsi', '%rax': '%rax',
                  '%r10': '%r10', '%r11': '%r11', '%r12': '%r12',
                  '%r13': '%r13', '%r14': '%r14', '%r15': '%r15'}
        _reg32 = {'%rcx': '%ecx', '%rdx': '%edx', '%r8': '%r8d',  '%r9': '%r9d',
                  '%rdi': '%edi', '%rsi': '%esi', '%rax': '%eax',
                  '%r10': '%r10d', '%r11': '%r11d', '%r12': '%r12d',
                  '%r13': '%r13d', '%r14': '%r14d', '%r15': '%r15d'}
        _reg16 = {'%rcx': '%cx',  '%rdx': '%dx',  '%r8': '%r8w',  '%r9': '%r9w',
                  '%rdi': '%di',  '%rsi': '%si',  '%rax': '%ax',
                  '%r10': '%r10w', '%r11': '%r11w', '%r12': '%r12w',
                  '%r13': '%r13w', '%r14': '%r14w', '%r15': '%r15w'}
        _reg8  = {'%rcx': '%cl',  '%rdx': '%dl',  '%r8': '%r8b',  '%r9': '%r9b',
                  '%rdi': '%dil', '%rsi': '%sil', '%rax': '%al',
                  '%r10': '%r10b', '%r11': '%r11b', '%r12': '%r12b',
                  '%r13': '%r13b', '%r14': '%r14b', '%r15': '%r15b'}

        # Substitute $N placeholders, choosing register size from instruction mnemonic
        def _sub_line(line):
            stripped = line.strip()
            # Detect size suffix from mnemonic (movl, movw, movb, etc.)
            mnemonic = stripped.split()[0] if stripped else ''
            if mnemonic.endswith('l') or mnemonic.endswith('l\t'):
                reg_map = _reg32
            elif mnemonic.endswith('w'):
                reg_map = _reg16
            elif mnemonic.endswith('b'):
                reg_map = _reg8
            else:
                reg_map = _reg64
            def _sub_operand(m):
                idx = int(m.group(1))
                if idx in operand_map:
                    r64 = operand_map[idx]
                    return reg_map.get(r64, r64)
                raise VMError(f'INLINE_ASM: operand ${idx} out of range')
            return _re.sub(r'(?<!\$)\$(\d+)', _sub_operand, line)

        # Remap input operands to scratch registers so we can embed values
        # as movabsq immediates without ABI register shuffling conflicts.
        # %rax is reserved for output. %r10-%r15 are caller-saved scratch.
        # %rax is used as call trampoline register.
        # r10, r11 are caller-saved (safe across calls without save/restore)
        # r12-r15 are callee-saved -- save/restore them in prologue/epilogue
        _scratch_regs = ['%r10', '%r11', '%r12', '%r13', '%r14', '%r15']
        _callee_saved_used = [r for r in _scratch_regs[2:2 + max(0, n_inputs - 2)] ]
        for i in range(n_inputs):
            if i < len(_scratch_regs):
                operand_map[n_outputs + i] = _scratch_regs[i]
            else:
                raise VMError(f'INLINE_ASM: too many input operands (max {len(_scratch_regs)})')

        # Single-pass: substitute operands then resolve external calls
        asm_body = '\n'.join(_sub_line(line) for line in body.splitlines())
        asm_body = asm_body.replace('$$', '$')

        _sym_addrs = {}
        _asm_libs = getattr(self, '_asm_libs', {})
        def _resolve_call(m):
            sym = m.group(1)
            if sym not in _sym_addrs:
                import ctypes as _ct
                addr = None
                # Check explicitly loaded libs first
                for lib in _asm_libs.values():
                    try:
                        _fn = getattr(lib, sym, None)
                        if _fn is not None:
                            addr = _ct.cast(_fn, _ct.c_void_p).value
                            break
                    except (OSError, AttributeError):
                        continue
                # Fall back to common system libs
                if addr is None:
                    _fallback = (['kernel32', 'msvcrt'] if system == 'Windows'
                                 else [None, 'c', 'libpthread.so.0'])
                    for _lib in _fallback:
                        try:
                            dll = _ct.CDLL(_lib)
                            _fn = getattr(dll, sym, None)
                            if _fn is not None:
                                addr = _ct.cast(_fn, _ct.c_void_p).value
                                break
                        except OSError:
                            continue
                if addr is None:
                    raise VMError(f'INLINE_ASM: cannot resolve symbol {sym!r}')
                _sym_addrs[sym] = addr
            addr = _sym_addrs[sym]
            return f'movabsq ${addr}, %rax\ncallq *%rax'
        _has_writefile = system == 'Windows' and bool(_re.search(r'\bcall\s+WriteFile\b', asm_body))
        asm_body = _re.sub(r'\bcall\s+(\w+)', _resolve_call, asm_body)

        # Pin BYTES values in native memory (need addresses for movabsq immediates)
        _pinned = []
        c_args = []

        # WriteFile on Windows requires lpNumberOfBytesWritten (r9) to be a valid
        # pointer when lpOverlapped (5th arg) is NULL. Replace xorq %r9,%r9 with
        # a movabsq to a pinned scratch DWORD so WriteFile can write the byte count.
        if _has_writefile:
            _written_buf = (ctypes.c_uint32 * 1)(0)
            _pinned.append(_written_buf)
            _written_addr = ctypes.addressof(_written_buf)
            asm_body = _re.sub(
                r'xorq\s+%r9,\s*%r9',
                f'movabsq ${_written_addr}, %r9',
                asm_body
            )
            # lpOverlapped (5th arg at rsp+32) must remain NULL -- replace
            # movq %r9, 32(%rsp) with a direct zero store now that r9 != 0.
            # Use xor+store via a scratch to avoid movq $imm,mem encoding issues.
            asm_body = asm_body.replace(
                'movq %r9, 32(%rsp)',
                'xorq %rax, %rax\nmovq %rax, 32(%rsp)'
            )
        for v in input_vals:
            tag = v.tag
            if tag in (TTag.INT, TTag.UINT, TTag.LONG, TTag.ULONG,
                       TTag.BYTE, TTag.BOOL, TTag.CHAR, TTag.PTR):
                c_args.append(int(v.data) & 0xFFFFFFFFFFFFFFFF)
            elif tag == TTag.BYTES:
                raw = v.data if isinstance(v.data, (bytes, bytearray)) else str(v.data).encode('utf-8')
                if not raw or raw[-1] != 0:
                    raw = raw + b'\x00'
                buf_pin = (ctypes.c_char * len(raw))(*raw)
                _pinned.append(buf_pin)
                c_args.append(ctypes.addressof(buf_pin))
            elif tag == TTag.FLOAT:
                c_args.append(int(_struct.unpack('<I', _struct.pack('<f', float(v.data)))[0]))
            elif tag == TTag.DOUBLE:
                c_args.append(int(_struct.unpack('<Q', _struct.pack('<d', float(v.data)))[0]))
            else:
                c_args.append(0)

        # Emit movabsq to load each input value into its scratch register
        setup_lines = []
        for i in range(len(input_vals)):
            reg = _scratch_regs[i]
            ival = c_args[i] if i < len(c_args) else 0
            setup_lines.append(f'movabsq ${ival}, {reg}')

        full_asm = 'pushq %rbp\n'
        full_asm += 'movq %rsp, %rbp\n'
        for reg in _callee_saved_used:
            full_asm += f'pushq {reg}\n'
        # Re-align stack to 16 bytes if we pushed an odd number of callee-saved regs
        extra_push = len(_callee_saved_used) % 2 != 0
        if extra_push:
            full_asm += 'subq $8, %rsp\n'
        for line in setup_lines:
            full_asm += line + '\n'
        asm_body_clean = '\n'.join(line.strip() for line in asm_body.splitlines() if line.strip())
        full_asm += asm_body_clean + '\n'
        if extra_push:
            full_asm += 'addq $8, %rsp\n'
        for reg in reversed(_callee_saved_used):
            full_asm += f'popq {reg}\n'
        full_asm += 'popq %rbp\n'
        full_asm += 'retq\n'

        # Assemble with keystone (AT&T syntax, x86-64)
        ks = _ks.Ks(_ks.KS_ARCH_X86, _ks.KS_MODE_64)
        ks.syntax = _ks.KS_OPT_SYNTAX_ATT
        try:
            encoding, count = ks.asm(full_asm)
        except _ks.KsError as e:
            raise VMError(f'INLINE_ASM: assembly failed: {e}\nASM:\n{full_asm}')
        if encoding is None or len(encoding) == 0:
            raise VMError(f'INLINE_ASM: assembler returned no bytes (count={count})\nASM:\n{full_asm}')

        machine_code = bytes(encoding)

        # Allocate executable memory and copy code in
        size = len(machine_code)
        if system == 'Windows':
            MEM_COMMIT   = 0x1000
            MEM_RESERVE  = 0x2000
            PAGE_EXEC_RW = 0x40
            kernel32 = ctypes.windll.kernel32
            kernel32.VirtualAlloc.restype = ctypes.c_void_p
            kernel32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
            buf = kernel32.VirtualAlloc(None, size, MEM_COMMIT | MEM_RESERVE, PAGE_EXEC_RW)
            if not buf:
                raise VMError('INLINE_ASM: VirtualAlloc failed')
            ctypes.memmove(buf, machine_code, size)
            kernel32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
            free_fn = lambda b: kernel32.VirtualFree(ctypes.c_void_p(b), 0, 0x8000)
        else:
            import mmap as _mmap
            mm = _mmap.mmap(-1, size,
                            prot=_mmap.PROT_READ | _mmap.PROT_WRITE | _mmap.PROT_EXEC)
            mm.write(machine_code)
            mm.seek(0)
            buf = ctypes.addressof((ctypes.c_char * size).from_buffer(mm))
            free_fn = lambda b: mm.close()

        # JIT function takes no arguments -- values are embedded as immediates
        fn_type = ctypes.CFUNCTYPE(ctypes.c_int64)
        fn = fn_type(buf)

        # import sys as _sys
        # _sys.stderr.write(f'[ASM]\n{full_asm}\n[ARGS] {c_args}\n')
        # _sys.stderr.flush()
        # If this is a WriteFile call, execute it directly via ctypes instead of JIT.
        # The JIT path crashes due to ABI subtleties; direct ctypes is reliable.
        if _has_writefile and system == 'Windows':
            _hnd = c_args[2] if len(c_args) > 2 else 0
            _msg_ptr = c_args[0] if c_args else 0
            _msg_len = c_args[1] if len(c_args) > 1 else 0
            _written2 = (ctypes.c_uint32 * 1)(0)
            _k32 = ctypes.windll.kernel32
            _k32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                        ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
            _k32.WriteFile.restype = ctypes.c_int32
            _k32.WriteFile(ctypes.c_void_p(_hnd), ctypes.c_void_p(_msg_ptr),
                           ctypes.c_uint32(_msg_len), _written2, None)
            return
        try:
            result = fn()
        except Exception as _e:
            free_fn(buf)
            raise VMError(f'INLINE_ASM: execution failed: {_e}\nASM:\n{full_asm}\nargs: {c_args}') from _e
        finally:
            free_fn(buf)

        # Store output: if there are output operands, push rax result
        if n_outputs > 0 and output_names:
            out_val = Val(TTag.LONG, int(result))
            for name in output_names:
                self._globals[name] = out_val
            self._push(out_val)

    # ------------------------------------------------------------------
    # compiler.fvm.loadlib
    # ------------------------------------------------------------------

    def _op_compiler_loadlib(self):
        ext_val  = self._pop()
        name_val = self._pop()
        name = self._read_vm_string(name_val)
        ext  = self._read_vm_string(ext_val).lstrip('.')
        import sys as _sys
        if _sys.platform == 'win32':
            lib_file = f'{name}.{ext}' if ext else name
            try:
                lib = ctypes.WinDLL(lib_file)
            except OSError:
                try:
                    lib = ctypes.CDLL(lib_file)
                except OSError as e:
                    raise VMError(f'compiler.fvm.loadlib: cannot load {lib_file!r}: {e}')
        else:
            candidates = []
            if ext:
                candidates.append(f'lib{name}.{ext}')
                candidates.append(f'{name}.{ext}')
            candidates += [f'lib{name}.so', f'lib{name}.dylib', name]
            lib = None
            for c in candidates:
                try:
                    lib = ctypes.CDLL(c)
                    break
                except OSError:
                    continue
            if lib is None:
                raise VMError(f'compiler.fvm.loadlib: cannot load {name!r}')
        if not hasattr(self, '_asm_libs'):
            self._asm_libs = {}
        self._asm_libs[name] = lib
        self._asm_libs[name.lower()] = lib

    # ------------------------------------------------------------------
    # compiler.io built-in ops
    # ------------------------------------------------------------------

    def _op_compiler_print(self):
        val = self._pop()
        if val.tag == TTag.BYTE:
            text = chr(int(val.data) & 0xFF)
        elif val.tag in (TTag.BYTES, TTag.PTR, TTag.CHAR) or isinstance(val.data, (str, bytes, bytearray)):
            text = self._read_vm_string(val)
        else:
            text = str(val.data)
        sys.stdout.write(text.replace('\x00', ''))
        sys.stdout.flush()

    def _op_compiler_input(self):
        line = sys.stdin.readline()
        raw  = line.encode('utf-8')
        self._push(Val(TTag.BYTES, raw))

    def _op_compiler_readfile(self):
        path_val = self._pop()
        path     = self._read_vm_string(path_val)
        try:
            with open(path, 'rb') as fh:
                raw = fh.read()
        except OSError as e:
            raise VMError(f'compiler.io.readfile: {e}')
        ptr = self.heap.alloc(len(raw) + 1, TTag.BYTES)
        self.heap.write(ptr, raw + b'\x00')
        self._push(Val(TTag.PTR, ptr, meta={'elem_type': 'byte', 'count': len(raw), 'elem_size': 1}))

    def _op_compiler_writefile(self):
        flags_val   = self._pop()
        content_val = self._pop()
        path_val    = self._pop()
        path    = self._read_vm_string(path_val)
        flags   = self._read_vm_string(flags_val)
        # Determine open mode from flags: r/w/a combined with t (text) or default binary
        mode_map = {
            'r':  'rb',  'rt': 'r',
            'w':  'wb',  'wt': 'w',
            'a':  'ab',  'at': 'a',
            'rw': 'r+b', 'rwt': 'r+',
        }
        mode = mode_map.get(flags.replace(' ', ''), 'wb')
        # Read content from VM heap
        if content_val.tag == TTag.PTR:
            ptr   = int(content_val.data)
            count = content_val.meta.get('count', 0)
            if count == 0:
                # Read until null terminator
                buf = bytearray()
                while True:
                    b = self.heap.read(ptr, 1)[0]
                    if b == 0:
                        break
                    buf.append(b)
                    ptr += 1
                raw = bytes(buf)
            else:
                raw = self.heap.read(ptr, count)
        elif content_val.tag == TTag.BYTES:
            raw = content_val.data if isinstance(content_val.data, bytes) else content_val.data.encode()
        else:
            raw = str(content_val.data).encode()
        try:
            with open(path, mode) as fh:
                fh.write(raw if 'b' in mode else raw.decode('utf-8', errors='replace'))
        except OSError as e:
            raise VMError(f'compiler.io.writefile: {e}')

    def _op_compiler_fvm_setbp(self):
        """compiler.fvm.setbp() -- comptime breakpoint.
        Prints the current stack and locals, then waits for a keypress."""
        import sys as _sys
        frame = self.frames[-1] if self.frames else None
        _sys.stderr.write('\n[COMPTIME BREAKPOINT]\n')
        if frame:
            _sys.stderr.write(f'  func : {frame.func_name}\n')
            _sys.stderr.write(f'  ip   : {frame.ip}\n')
            _sys.stderr.write('  locals:\n')
            for i, v in enumerate(frame.locals):
                if v is not None:
                    _sys.stderr.write(f'    [{i}] = {v}\n')
        _sys.stderr.write('  stack (top first):\n')
        for i, v in enumerate(reversed(self.stack)):
            _sys.stderr.write(f'    [{i}] {v}\n')
            if i >= 15:
                _sys.stderr.write(f'    ... ({len(self.stack) - 16} more)\n')
                break
        _sys.stderr.write('Press any key to continue execution ...')
        _sys.stderr.flush()
        try:
            import msvcrt as _msvcrt
            _msvcrt.getch()
        except ImportError:
            import tty as _tty, termios as _termios
            fd = _sys.stdin.fileno()
            old = _termios.tcgetattr(fd)
            try:
                _tty.setraw(fd)
                _sys.stdin.read(1)
            finally:
                _termios.tcsetattr(fd, _termios.TCSADRAIN, old)
        _sys.stderr.write('\n')
        _sys.stderr.flush()

    def _op_compiler_fvm_dump(self):
        path_val = self._pop()
        path     = self._read_vm_string(path_val)
        path     = path.replace('\\', '/')
        current_ip     = self.frames[0].ip if self.frames else 0
        current_instrs = self.frames[0].instructions if self.frames else []
        before_dump = [i for i in current_instrs[:current_ip - 2] if i.op != Op.HALT]
        all_instrs = []
        for block in self._comptime_log:
            all_instrs.extend(_rebase_block(block, len(all_instrs)))
        if before_dump:
            all_instrs.extend(_rebase_block(before_dump, len(all_instrs)))
        text = serialise_fvm(all_instrs, self._comptime_log_locals, self._functions, self.struct_layouts)
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(text)
        except OSError as e:
            raise VMError(f'compiler.fvm.dump: {e}')

    def _op_compiler_import_stdlib(self):
        path = self._read_vm_string(self._pop())
        try:
            processed, line_map = self._preprocess_import(path, 'stdlib')
            self._compile_imported_source(processed, path, line_map)
        except VMError as e:
            import re as _re, os as _os
            m = _re.search(r'\[([^\]]+\.fx):', str(e))
            real = _os.path.basename(m.group(1)) if m else path
            raise VMError(f'{e} (stdlib: {real})') from e
        self.emit_results.append(('import_stdlib', processed, path))

    def _op_compiler_import_local(self):
        path = self._read_vm_string(self._pop())
        try:
            processed, line_map = self._preprocess_import(path, 'local')
            self._compile_imported_source(processed, path, line_map)
        except VMError as e:
            raise VMError(f'{e} (local: {path})') from e
        self.emit_results.append(('import_local', processed, path))

    def _op_compiler_fpm_package(self):
        path = self._read_vm_string(self._pop())
        try:
            processed, line_map = self._preprocess_import(path, 'package')
            self._compile_imported_source(processed, path, line_map)
        except VMError as e:
            raise VMError(f'{e} (package: {path})') from e
        self.emit_results.append(('import_package', processed, path))

    def _compile_imported_source(self, source: str, filename: str = '<import>', line_map: list = None):
        """
        Lex, parse, and compile comptime-relevant declarations from preprocessed
        Flux source into self._functions so CALL instructions in the current block
        can find them immediately.

        Only comptime-compilable nodes are processed: function definitions,
        namespace definitions, struct/union/enum definitions.
        Everything else (extern blocks, LLVM IR declarations, etc.) is skipped.
        """
        import sys as _sys, types as _types
        if 'llvmlite' not in _sys.modules:
            class _IrStubMod(_types.ModuleType):
                class _S:
                    def __init__(self, *a, **kw): pass
                    def __call__(self, *a, **kw): return type(self)()
                    def __getattr__(self, n): return type(self)()
                    def __class_getitem__(cls, i): return cls
                def __getattr__(self, name): return self._S
            _ir_stub  = _IrStubMod('llvmlite.ir')
            _ll_stub  = _types.ModuleType('llvmlite')
            _ll_stub.ir = _ir_stub
            _sys.modules['llvmlite']                 = _ll_stub
            _sys.modules['llvmlite.ir']              = _ir_stub
            _sys.modules['llvmlite.ir.instructions'] = _types.ModuleType('llvmlite.ir.instructions')
        _CG = self._codegen_class
        if _CG is None:
            raise VMError('compiler.import: no codegen class registered on VM')
        try:
            from flexer import FluxLexer as _Lexer
            from fparser import FluxParser as _Parser
            from fast import (
                FunctionDef, FunctionDefStatement, NamespaceDef, NamespaceDefStatement,
                StructDef, StructDefStatement, UnionDef, UnionDefStatement,
                EnumDef, EnumDefStatement, TypeFuncDef, ExternBlock,
            )
        except ImportError as e:
            raise VMError(f'compiler.import: missing module: {e}')

        if not source or not source.strip():
            return
        source_lines = source.splitlines()
        tokens = _Lexer(source).tokenize()
        program = _Parser(tokens).parse()

        _decl_types = (
            FunctionDef, FunctionDefStatement, NamespaceDef, NamespaceDefStatement,
            StructDef, StructDefStatement, UnionDef, UnionDefStatement,
            EnumDef, EnumDefStatement, TypeFuncDef, ExternBlock,
        )

        # Pre-pass: register global const variables so function bodies can access
        # them as outer globals during compilation (e.g. TIME_NS_PER_SEC in timing.fx).
        from fast import VariableDeclaration as _VD, Literal as _Lit, NamespaceDef as _NS, NamespaceDefStatement as _NSS, CastExpression as _Cast, AddressOf as _AddrOf
        def _collect_global_consts(stmts):
            for s in stmts:
                if isinstance(s, (_NS, _NSS)):
                    ns = s.namespace_def if isinstance(s, _NSS) else s
                    _collect_global_consts(ns.variables)
                    _collect_global_consts(ns.nested_namespaces)
                elif isinstance(s, _VD):
                    if s.initial_value is None:
                        if s.name not in self._globals:
                            ts = getattr(s, 'type_spec', None)
                            if ts is not None and getattr(ts, 'is_array', False):
                                arr_size = getattr(ts, 'array_size', None)
                                # array_size may be a parsed Literal AST node rather
                                # than a plain int (e.g. `FreeNode*[9]`).
                                if isinstance(arr_size, _Lit):
                                    lit_val = arr_size.value
                                    if isinstance(lit_val, str):
                                        try: lit_val = int(lit_val, 0)
                                        except (ValueError, TypeError): lit_val = None
                                    arr_size = lit_val
                                if isinstance(arr_size, int) and arr_size > 0:
                                    elems = [Val(TTag.PTR, 0)] * arr_size
                                    self._globals[s.name] = Val(TTag.ARRAY, 0, meta={'elements': elems})
                                else:
                                    self._globals[s.name] = Val(TTag.PTR, 0)
                            else:
                                self._globals[s.name] = Val(TTag.PTR, 0)
                    elif isinstance(s.initial_value, _Lit):
                        if s.name not in self._globals:
                            try:
                                v = s.initial_value.value
                                if isinstance(v, str):
                                    try: v = int(v, 0)
                                    except (ValueError, TypeError):
                                        try: v = float(v)
                                        except (ValueError, TypeError): pass
                                if isinstance(v, bool):
                                    self._globals[s.name] = Val(TTag.BOOL, int(v))
                                elif isinstance(v, int):
                                    self._globals[s.name] = Val(TTag.LONG, v)
                                elif isinstance(v, float):
                                    self._globals[s.name] = Val(TTag.DOUBLE, v)
                            except Exception:
                                pass
                    elif isinstance(s.initial_value, _Cast) and isinstance(s.initial_value.expression, _AddrOf):
                        if s.name not in self._globals:
                            inner = s.initial_value.expression.expression
                            if isinstance(inner, _Lit) and inner.value in (0, 'void', False, None, '0'):
                                self._globals[s.name] = Val(TTag.PTR, 0)
                    else:
                        if s.name not in self._globals:
                            self._globals[s.name] = Val(TTag.PTR, 0)
        _collect_global_consts(program.statements)

        cg = _CG(known_functions=dict(self._functions),
                 known_struct_layouts=dict(self.struct_layouts))
        # Expose pre-registered globals to function bodies compiled inside this import
        cg._block_globals = set(self._globals.keys())
        for stmt in program.statements:
            if isinstance(stmt, _decl_types):
                try:
                    cg._visit_stmt(stmt)
                except Exception as e:
                    import re as _re, os as _os
                    line_no = col_no = None
                    m = _re.search(r'\[(\d+):(\d+)\]', str(e))
                    if m:
                        line_no = int(m.group(1))
                        col_no  = int(m.group(2))
                    real_file = filename
                    real_line_no = line_no
                    if line_map is not None and line_no is not None and 1 <= line_no <= len(line_map):
                        real_file, real_line_no = line_map[line_no - 1]
                        real_file = _os.path.basename(real_file)
                    override = getattr(e, 'override_src_text', None)
                    src_text = ''
                    if override is not None:
                        src_text = '\n' + '\n'.join('\t' + l for l in override.splitlines())
                    elif real_line_no is not None:
                        real_lines = source_lines
                        if line_map is not None and line_no is not None and 1 <= line_no <= len(line_map):
                            orig_file = line_map[line_no - 1][0]
                            try:
                                with open(orig_file, 'r', encoding='utf-8', errors='replace') as _fh:
                                    real_lines = _fh.read().splitlines()
                            except OSError:
                                real_lines = source_lines
                        if 1 <= real_line_no <= len(real_lines):
                            raw_line = real_lines[real_line_no - 1]
                            stripped = raw_line.strip()
                            indent = len(raw_line) - len(raw_line.lstrip())
                            caret_pos = max(0, (col_no - 1) - indent) if col_no is not None else 0
                            src_text = f'\n\t{stripped}\n\t{" " * caret_pos}^'
                    e_msg = _re.sub(r' \[\d+:\d+\]', '', str(e))
                    raise VMError(f'compiler.import (compiling imported declarations): {e_msg} [{real_file}:{real_line_no}:{col_no}]{src_text}') from e

        # Register all compiled functions with the VM immediately.
        # Do not overwrite functions already registered -- imported prototypes
        # (forward declarations with no body) must not clobber user definitions.
        for name, instrs in cg.compiled_functions.items():
            if name not in self._functions:
                self.register_function(name, instrs)

        # Register extern protos from EXTERN_DECL instructions emitted during import.
        # These appear in the top-level cg instruction stream and inside function bodies.
        def _collect_extern_decls(instrs):
            for instr in instrs:
                if instr.op == Op.EXTERN_DECL:
                    self._extern_protos[instr.operands[0]] = instr.operands[1]
        _collect_extern_decls(cg._instructions)
        for fn_instrs in cg.compiled_functions.values():
            _collect_extern_decls(fn_instrs)

        # Accumulate struct layouts so STRUCT_NEW / FIELD_GET work
        self.struct_layouts.update(cg._struct_layouts)

        # Store imported source for runtime error location lookup
        self._imported_sources.append((source_lines, line_map, filename))

    def _preprocess_import(self, path: str, kind: str):
        """
        Resolve, read, and preprocess a Flux source file for a compiler.import.*
        or compiler.fpm.package call. Returns (preprocessed_source, line_map).
        line_map is a list of (filename, local_line_number) for each output line.
        kind: 'stdlib' | 'local' | 'package'
        """
        try:
            from fpreprocess import FXPreprocessor
        except ImportError:
            raise VMError('compiler.import: fpreprocess module not available')
        import tempfile, os
        src_file = self.source_file or os.path.join(os.getcwd(), '__comptime__.fx')
        if kind == 'stdlib':
            wrapper = f'#import <{path}>;\n'
        elif kind == 'local':
            wrapper = f'#import "{path}";\n'
        else:
            wrapper = f'#package "{path}";\n'
        # For local imports the temp file must sit next to the user's source
        # so FXPreprocessor resolves relative #import paths correctly via its
        # _dir_stack.  For stdlib/package the temp file location doesn't
        # matter for resolution, so use cwd (/sandbox in the container) which
        # is always writable — this avoids a PermissionError when the line map
        # points to a stdlib file and src_dir resolves to the read-only
        # /opt/flux/src/stdlib/ directory.
        if kind == 'local':
            tmp_dir = os.path.dirname(os.path.abspath(src_file))
        else:
            tmp_dir = os.getcwd()
        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.fx', dir=tmp_dir,
            delete=False, encoding='utf-8'
        )
        try:
            tmp.write(wrapper)
            tmp.close()
            preprocessor = FXPreprocessor(tmp.name, compiler_constants=self._compiler_constants)
            result = preprocessor.process()
            line_map = preprocessor.line_map
        except FileNotFoundError as e:
            raise VMError(f'compiler.import: {e}')
        finally:
            os.unlink(tmp.name)
        return result, line_map

    # ------------------------------------------------------------------
    # String ops
    # ------------------------------------------------------------------

    def _op_str_len(self):
        val = self._pop()
        s   = self._read_vm_string(val)
        self._push(Val(TTag.UINT, len(s)))

    def _op_str_cat(self):
        b_val = self._pop()
        a_val = self._pop()
        a = self._read_vm_string(a_val)
        b = self._read_vm_string(b_val)
        self._push(Val(TTag.BYTES, (a + b).encode('utf-8')))

    def _op_str_slice(self):
        length_val = self._pop()
        start_val  = self._pop()
        str_val    = self._pop()
        s      = self._read_vm_string(str_val)
        start  = int(start_val.data)
        length = int(length_val.data)
        self._push(Val(TTag.BYTES, s[start:start + length].encode('utf-8')))

    def _op_str_eq(self):
        b_val = self._pop()
        a_val = self._pop()
        a = self._read_vm_string(a_val)
        b = self._read_vm_string(b_val)
        self._push(Val(TTag.BOOL, int(a == b)))

    def _op_str_find(self):
        needle_val   = self._pop()
        haystack_val = self._pop()
        haystack = self._read_vm_string(haystack_val)
        needle   = self._read_vm_string(needle_val)
        idx = haystack.find(needle)
        self._push(Val(TTag.INT, idx))

    def _op_int_to_str(self):
        val = self._pop()
        if val.tag in (TTag.BYTES,) or isinstance(val.data, (bytes, bytearray)):
            result = val.data if isinstance(val.data, (bytes, bytearray)) else val.data.encode('utf-8')
        elif val.tag == TTag.PTR:
            text = self._read_vm_string(val)
            result = text.encode('utf-8')
        elif isinstance(val.data, str):
            result = val.data.encode('utf-8')
        elif val.tag == TTag.CHAR:
            result = chr(int(val.data)).encode('utf-8')
        else:
            result = str(int(val.data)).encode('utf-8')
        self._push(Val(TTag.BYTES, result))

    def _op_str_to_int(self):
        val = self._pop()
        s   = self._read_vm_string(val)
        try:
            n = int(s.strip(), 0)
        except ValueError:
            raise VMError(f'STR_TO_INT: cannot convert {s!r} to integer')
        self._push(Val(TTag.INT, n))

    # ------------------------------------------------------------------
    # Type conversion ops
    # ------------------------------------------------------------------

    def _op_cast(self, target: TTag, struct_type: str = None):
        val = self._pop()
        src = val.tag
        d   = val.data
        # Coerce single-character strings to their ordinal for numeric casts
        if isinstance(d, str) and len(d) == 1:
            d = ord(d)
        if target in (TTag.INT, TTag.UINT, TTag.LONG, TTag.ULONG, TTag.BYTE, TTag.CHAR, TTag.DATA):
            self._push(Val(target, int(d)))
        elif target == TTag.FLOAT:
            self._push(Val(target, float(d)))
        elif target == TTag.DOUBLE:
            self._push(Val(target, float(d)))
        elif target == TTag.BOOL:
            self._push(Val(target, int(bool(d))))
        elif target == TTag.PTR and struct_type:
            self._push(Val(target, d, meta={'struct_type': struct_type}))
        else:
            self._push(Val(target, d))

    def _op_bitcast(self, target: TTag):
        val     = self._pop()
        raw     = self._val_to_bytes(val, self._ttag_byte_size(val.tag))
        result  = self._bytes_to_val(raw, target, self._ttag_byte_size(target))
        self._push(Val(target, result))

    def _ttag_byte_size(self, tag: TTag) -> int:
        _sizes = {
            TTag.BOOL: 1, TTag.BYTE: 1, TTag.CHAR: 1,
            TTag.INT: 4,  TTag.UINT: 4,
            TTag.LONG: 8, TTag.ULONG: 8,
            TTag.FLOAT: 4, TTag.DOUBLE: 8,
            TTag.PTR: 8,
        }
        return _sizes.get(tag, 4)

    # ------------------------------------------------------------------
    # Diagnostic ops
    # ------------------------------------------------------------------

    def _op_assert(self):
        msg_val  = self._pop()
        cond_val = self._pop()
        if not bool(cond_val.data):
            msg = self._read_vm_string(msg_val) if msg_val.tag in (TTag.BYTES, TTag.PTR) else str(msg_val.data)
            raise VMError(f'comptime assertion failed: {msg}')

    def _op_warn(self):
        val = self._pop()
        msg = self._read_vm_string(val) if val.tag in (TTag.BYTES, TTag.PTR) else str(val.data)
        sys.stderr.write(f'comptime warning: {msg}\n')
        sys.stderr.flush()

    def _op_panic(self):
        val = self._pop()
        msg = self._read_vm_string(val) if val.tag in (TTag.BYTES, TTag.PTR) else str(val.data)
        raise VMError(f'comptime panic: {msg}')

    def _op_try_begin(self, catch_addr: int):
        """Push a catch handler onto the current frame's exception_handlers stack."""
        frame = self.frames[-1]
        frame.exception_handlers.append((catch_addr, len(self.stack)))

    def _op_try_end(self):
        """Pop the innermost catch handler (normal exit from try body)."""
        frame = self.frames[-1]
        if frame.exception_handlers:
            frame.exception_handlers.pop()

    # ------------------------------------------------------------------
    # Boundary crossing ops
    # ------------------------------------------------------------------

    def _op_emit_const(self):
        val = self._pop()
        self.emit_results.append(('const', val))

    def _op_emit_global(self, byte_size: int):
        ptr_val = self._pop()
        ptr     = int(ptr_val.data)
        data    = self.heap.snapshot(ptr, byte_size)
        self.emit_results.append(('global', data, ptr_val.meta))

    def _op_emit_type(self):
        val = self._pop()
        self.emit_results.append(('type', val))

    def _op_emitflux(self, source_text: str, var_names: list):
        """
        Perform variable substitution on source_text using the current comptime
        locals (passed as a snapshot via var_names: list of (name, slot) pairs),
        then append ('flux', substituted_text) to emit_results.

        Substitution rules:
          - Plain identifiers: replace each occurrence of `name` that appears
            as a whole word with the string representation of its value.
          - ~$f"..." format strings in the text are expanded: the embedded
            {name} placeholders are replaced with the value, then the entire
            ~$f"..." expression is replaced with the resulting identifier text.
        """
        frame = self.frames[-1] if self.frames else None

        def val_to_str(v: Val) -> str:
            if v is None:
                return '0'
            if v.tag == TTag.BOOL:
                return 'true' if v.data else 'false'
            if v.tag in (TTag.FLOAT, TTag.DOUBLE):
                return repr(float(v.data))
            if v.tag == TTag.BYTES and isinstance(v.data, (bytes, bytearray)):
                return v.data.decode('utf-8', errors='replace')
            return str(v.data)

        # Build name -> Val mapping from the provided snapshot (for expression evaluation)
        local_vals: Dict[str, Val] = {}
        for name, slot in var_names:
            if frame is not None and slot < len(frame.locals):
                local_vals[name] = frame.locals[slot]
            else:
                local_vals[name] = Val(TTag.INT, 0)

        # Build name -> value-string mapping from the provided snapshot
        subst: Dict[str, str] = {}
        for name, v in local_vals.items():
            subst[name] = val_to_str(v)

        import re

        def _eval_istr_expr(expr_text: str) -> str:
            """
            Evaluate a single i-string positional expression against current locals.
            Supports: bare identifier, identifier[identifier], identifier[integer].
            Array subscripts are resolved directly against local_vals.
            """
            expr_text = expr_text.strip()
            # Try identifier[index]
            m = re.fullmatch(r'(\w+)\[(\w+)\]', expr_text)
            if m:
                arr_name = m.group(1)
                idx_name = m.group(2)
                arr_val  = local_vals.get(arr_name)
                # Resolve index: may be a local name or a bare integer literal
                if idx_name.lstrip('-').isdigit():
                    idx = int(idx_name)
                else:
                    idx_val = local_vals.get(idx_name)
                    idx = int(idx_val.data) if idx_val is not None else 0
                if arr_val is not None and arr_val.tag == TTag.ARRAY:
                    elements = (arr_val.meta or {}).get('elements', [])
                    if 0 <= idx < len(elements):
                        return val_to_str(elements[idx])
                return '0'
            # Bare identifier
            if re.fullmatch(r'\w+', expr_text):
                return subst.get(expr_text, expr_text)
            # Fallback: plain text substitute and return
            result = expr_text
            for nm, vs in subst.items():
                result = re.sub(r'\b' + re.escape(nm) + r'\b', vs, result)
            return result

        def expand_codify_istr(m):
            """Expand ~$i"template":{expr1;expr2;} into the resulting identifier."""
            template   = m.group(1)
            exprs_text = m.group(2)
            exprs = [e.strip() for e in exprs_text.split(';') if e.strip()]
            result = ''
            slot   = 0
            i      = 0
            while i < len(template):
                if template[i] == '{' and i + 1 < len(template) and template[i + 1] == '}':
                    if slot < len(exprs):
                        result += _eval_istr_expr(exprs[slot])
                        slot += 1
                    i += 2
                else:
                    result += template[i]
                    i += 1
            return result

        # Expand ~$i"...":{...} expressions first -- i-string codification.
        # These must be evaluated (array subscripts, locals) before any text substitution.
        text = re.sub(r'~\$i"([^"]*)":\{([^}]*)\}', expand_codify_istr, source_text)

        # Expand ~$f"..." expressions
        def expand_codify_fstr(m):
            fstr_body = m.group(1)
            # Replace {name} placeholders inside the f-string body
            def replace_placeholder(pm):
                pname = pm.group(1)
                return subst.get(pname, pname)
            expanded = re.sub(r'\{(\w+)\}', replace_placeholder, fstr_body)
            return expanded  # result is the bare identifier text

        text = re.sub(r'~\$f"([^"]*)"', expand_codify_fstr, text)

        # Replace whole-word variable names with their values
        for name, value_str in subst.items():
            text = re.sub(r'\b' + re.escape(name) + r'\b', value_str, text)

        self.emit_results.append(('flux', text))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_layout(self, type_name: str) -> StructLayout:
        if type_name not in self.struct_layouts:
            raise VMError(f'Unknown struct/object type: {type_name!r}')
        return self.struct_layouts[type_name]

    def _find_field(self, layout: StructLayout, name: str):
        for f in layout.fields:
            if f[0] == name:
                return f
        raise VMError(f'Field {name!r} not found in {layout.name!r}')

    def _type_byte_size(self, type_name: str) -> int:
        if type_name in self.type_sizes:
            return self.type_sizes[type_name]
        if type_name in self.struct_layouts:
            return self.struct_layouts[type_name].total_size
        _defaults = {
            'bool': 1, 'byte': 1, 'char': 1,
            'int': 4,  'uint': 4,
            'long': 8, 'ulong': 8,
            'float': 4, 'double': 8,
        }
        if type_name in _defaults:
            return _defaults[type_name]
        # data{N} / i8..i64 / u8..u64
        if type_name.startswith('i') or type_name.startswith('u'):
            try:
                bits = int(type_name[1:])
                return bits // 8
            except ValueError:
                pass
        if type_name.startswith('be') or type_name.startswith('le'):
            try:
                bits = int(type_name[2:])
                return bits // 8
            except ValueError:
                pass
        raise VMError(f'Unknown type size for: {type_name!r}')

    def _bytes_to_val(self, raw: bytes, tag: TTag, byte_size: int) -> Any:
        if tag in (TTag.INT, TTag.LONG):
            return int.from_bytes(raw[:byte_size], 'little', signed=True)
        if tag in (TTag.UINT, TTag.ULONG, TTag.BYTE, TTag.CHAR, TTag.BOOL, TTag.DATA):
            return int.from_bytes(raw[:byte_size], 'little', signed=False)
        if tag == TTag.FLOAT:
            return struct.unpack('<f', raw[:4])[0]
        if tag == TTag.DOUBLE:
            return struct.unpack('<d', raw[:8])[0]
        if tag == TTag.PTR:
            return int.from_bytes(raw[:byte_size], 'little', signed=False)
        return raw

    def _val_to_bytes(self, val: Val, byte_size: int, type_name: str = '') -> bytes:
        tag = val.tag
        d   = val.data
        if tag in (TTag.INT, TTag.LONG):
            return d.to_bytes(byte_size, 'little', signed=True)
        if tag in (TTag.UINT, TTag.ULONG, TTag.BYTE, TTag.CHAR, TTag.BOOL, TTag.DATA, TTag.PTR):
            return d.to_bytes(byte_size, 'little', signed=False)
        if tag == TTag.FLOAT:
            return struct.pack('<f', d)
        if tag == TTag.DOUBLE:
            return struct.pack('<d', d)
        if tag == TTag.STRUCT:
            layout = self.struct_layouts.get(val.data)
            fields = (val.meta or {}).get('fields', {})
            buf = bytearray(byte_size)
            if layout:
                for fname, ftag, foff, fsz in layout.fields:
                    fval = fields.get(fname)
                    if fval is None:
                        continue
                    try:
                        fbytes = self._val_to_bytes(fval, fsz)
                        buf[foff:foff+fsz] = fbytes
                    except Exception:
                        pass
            return bytes(buf)
        if isinstance(d, (bytes, bytearray)):
            return bytes(d)[:byte_size].ljust(byte_size, b'\x00')
        raise VMError(f'_val_to_bytes: unhandled tag {tag}')

    def _read_vm_string(self, val: Val) -> str:
        if isinstance(val.data, str):
            return val.data
        if val.tag == TTag.CHAR:
            return chr(int(val.data))
        if val.tag == TTag.BYTES and isinstance(val.data, (bytes, bytearray)):
            return val.data.decode('utf-8', errors='replace')
        if val.tag == TTag.PTR:
            ptr = int(val.data)
            result = bytearray()
            if self._ptr_is_os(ptr):
                # OS pointer: read via ctypes, cap at 4096 bytes to avoid runaway
                i = 0
                try:
                    while i < 4096:
                        b = self._os_read_byte(ptr + i)
                        if b == 0:
                            break
                        result.append(b)
                        i += 1
                except Exception:
                    pass
            else:
                # VM heap pointer: read null-terminated from heap
                while True:
                    b = self.heap.read(ptr, 1)[0]
                    if b == 0:
                        break
                    result.append(b)
                    ptr += 1
            return result.decode('utf-8', errors='replace')
        raise VMError(f'_read_vm_string: cannot read string from {val}')

    def _val_to_ctype(self, val: Val):
        tag = val.tag
        if tag in (TTag.INT,):            return ctypes.c_int32(int(val.data))
        if tag in (TTag.UINT,):           return ctypes.c_uint32(int(val.data))
        if tag in (TTag.LONG,):           return ctypes.c_int64(int(val.data))
        if tag in (TTag.ULONG,):          return ctypes.c_uint64(int(val.data))
        if tag == TTag.FLOAT:             return ctypes.c_float(float(val.data))
        if tag == TTag.DOUBLE:            return ctypes.c_double(float(val.data))
        if tag == TTag.BOOL:              return ctypes.c_bool(bool(val.data))
        if tag == TTag.BYTE:              return ctypes.c_uint8(int(val.data))
        if tag == TTag.PTR:               return ctypes.c_void_p(int(val.data) & 0xFFFFFFFFFFFFFFFF)
        if tag in (TTag.BYTES,):          return ctypes.c_void_p(0)
        raise VMError(f'_val_to_ctype: unhandled tag {tag}')


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _str_to_ttag(type_name: str) -> TTag:
    _map = {
        'int': TTag.INT, 'uint': TTag.UINT,
        'long': TTag.LONG, 'ulong': TTag.ULONG,
        'float': TTag.FLOAT, 'double': TTag.DOUBLE,
        'bool': TTag.BOOL, 'byte': TTag.BYTE, 'char': TTag.CHAR,
        'data': TTag.DATA, 'ptr': TTag.PTR, 'void': TTag.VOID,
    }
    return _map.get(type_name, TTag.PTR)

# ---------------------------------------------------------------------------
# .fvm serialiser
# ---------------------------------------------------------------------------

def _serialise_val(v) -> str:
    """Render a Val as a type:value token suitable for a PUSH operand.

    For PTR values carrying struct meta (stack_slot pointer), the meta is
    encoded as a bracketed suffix so it can be round-tripped through .fvm:

        ptr:29[struct_type=TB,stack_slot,a:0,b:1,c:2]

    Items in the bracket:
        struct_type=NAME      -- the Flux struct/type name
        stack_slot            -- flag: pointer addresses a frame local slot
        NAME:OFFSET           -- field_bit_offsets entries (name:bit_offset)
    """
    tag = v.tag
    d   = v.data
    if tag == TTag.BYTES:
        if isinstance(d, (bytes, bytearray)):
            text = d.decode('utf-8', errors='replace')
        else:
            text = str(d)
        escaped = (text.replace('\\', '\\\\')
                       .replace('"',  '\\"')
                       .replace('\n', '\\n')
                       .replace('\r', '\\r')
                       .replace('\t', '\\t')
                       .replace('\x00', '\\0'))
        return f'bytes:"{escaped}"'
    if tag == TTag.BOOL:
        return f'bool:{"true" if d else "false"}'
    if tag in (TTag.FLOAT, TTag.DOUBLE):
        return f'{tag.value}:{repr(float(d))}'
    if tag == TTag.VOID:
        return 'void:0'
    if tag == TTag.PTR and v.meta:
        parts = []
        if 'struct_type' in v.meta:
            parts.append(f'struct_type={v.meta["struct_type"]}')
        if v.meta.get('stack_slot'):
            parts.append('stack_slot')
        for fname, foffset in v.meta.get('field_bit_offsets', {}).items():
            parts.append(f'{fname}:{foffset}')
        # Struct with fields dict: inline each field value
        if 'fields' in v.meta:
            for fname, fval in v.meta['fields'].items():
                parts.append(f'f:{fname}={_serialise_val(fval)}')
        # Array with elements list: inline each element value
        if 'elements' in v.meta:
            elem_type = v.meta.get('elem_type', 'int')
            count     = v.meta.get('count', len(v.meta['elements']))
            parts.append(f'elem_type={elem_type}')
            parts.append(f'count={count}')
            for i, ev in enumerate(v.meta['elements']):
                parts.append(f'e:{i}={_serialise_val(ev)}')
        if parts:
            return 'ptr:' + str(d) + '[' + ','.join(parts) + ']'
    return f'{tag.value}:{d}'


def _serialise_instr(instr) -> str:
    """Render one Instr as a .fvm source line."""
    op = instr.op
    o  = instr.operands

    # Zero-operand
    _zero = {
        Op.POP, Op.DUP, Op.SWAP, Op.ROT, Op.OVER,
        Op.ADD, Op.SUB, Op.MUL, Op.DIV, Op.MOD, Op.NEG, Op.POW,
        Op.ABS, Op.MIN, Op.MAX, Op.CLAMP,
        Op.BAND, Op.BOR, Op.BXOR, Op.BNOT, Op.SHL, Op.SHR, Op.POPCOUNT,
        Op.CMP_EQ, Op.CMP_NE, Op.CMP_LT, Op.CMP_LE, Op.CMP_GT, Op.CMP_GE,
        Op.AND, Op.OR, Op.NOT,
        Op.RET, Op.HALT,
        Op.LOCAL_DEREF, Op.LOCAL_DEREF_SET,
        Op.ALLOC, Op.FREE, Op.OFFSET,
        Op.ARRAY_LEN, Op.ARRAY_LOAD, Op.ARRAY_STORE,
        Op.ENUM_LOAD, Op.ENUM_STORE,
        Op.BITSLICE,
        Op.TYPEOF,
        Op.IO_OPEN, Op.IO_READ, Op.IO_WRITE, Op.IO_CLOSE,
        Op.FFI_FREE,
        Op.COMPILER_PRINT, Op.COMPILER_INPUT,
        Op.COMPILER_READFILE, Op.COMPILER_WRITEFILE,
        Op.COMPILER_LOADLIB,
        Op.STR_LEN, Op.STR_CAT, Op.STR_SLICE, Op.STR_EQ, Op.STR_FIND,
        Op.INT_TO_STR, Op.STR_TO_INT,
        Op.ASSERT, Op.WARN, Op.PANIC,
        Op.EMIT_CONST, Op.EMIT_TYPE,
        Op.COMPILER_IMPORT_STDLIB, Op.COMPILER_IMPORT_LOCAL, Op.COMPILER_FPM_PACKAGE,
        Op.COMPILER_FVM_TRACE_BEGIN, Op.COMPILER_FVM_TRACE_END,
        Op.COMPILER_FVM_SETBP,
    }
    if op in _zero:
        return op.name

    if op in (Op.GLOBAL_GET, Op.GLOBAL_SET):
        return f'{op.name} {o[0]}'

    if op == Op.EXTERN_DECL:
        return f'EXTERN_DECL {o[0]} {o[1].name}'

    if op == Op.PUSH:
        return f'PUSH {_serialise_val(o[0])}'

    if op == Op.CALL_PTR:
        return f'CALL_PTR {o[0]}'

    if op in (Op.JMP, Op.JIF, Op.JNF):
        return f'{op.name} {o[0]}'

    if op == Op.JTABLE:
        table_str = ' '.join(str(a) for a in o[1])
        return f'JTABLE {o[0]} {table_str}'

    if op == Op.CALL:
        return f'CALL {o[0]} {o[1]}'

    if op == Op.TAIL_SELF:
        return f'TAIL_SELF {o[0]}'

    if op in (Op.LOCAL_GET, Op.LOCAL_SET):
        return f'{op.name} {o[0]}'

    if op in (Op.ROTL, Op.ROTR, Op.BITREV, Op.CLZ, Op.CTZ):
        return f'{op.name} {o[0]}'

    if op in (Op.SIZEOF, Op.ALIGNOF, Op.ENDIANOF,
              Op.STRUCT_NEW, Op.STRUCT_LOAD, Op.STRUCT_STORE,
              Op.ENUM_NEW):
        return f'{op.name} {o[0]}'

    if op in (Op.STRUCT_LOAD, Op.STRUCT_STORE):
        return f'{op.name} {o[0]}'

    if op == Op.ARRAY_NEW:
        return f'ARRAY_NEW {o[0]} {o[1]}'

    if op in (Op.LOAD, Op.STORE):
        return f'{op.name} {o[0].value} {o[1]}'

    if op in (Op.CAST, Op.BITCAST):
        if len(o) > 1 and o[1]:
            return f'{op.name} {o[0].value} {o[1]}'
        return f'{op.name} {o[0].value}'

    if op == Op.EMIT_GLOBAL:
        return f'EMIT_GLOBAL {o[0]}'

    if op == Op.FFI_LOAD:
        return f'FFI_LOAD {o[0]}'

    if op == Op.FFI_SYM:
        return f'FFI_SYM {o[0]}'

    if op == Op.FFI_CALL:
        return f'FFI_CALL {o[0]} {o[1].value}'

    if op == Op.INLINE_ASM:
        body        = o[0].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        constraints = o[1].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        n_inputs    = o[2]
        n_outputs   = o[3]
        out_names   = ' '.join(o[4]) if o[4] else ''
        return f'INLINE_ASM "{body}" "{constraints}" {n_inputs} {n_outputs} {out_names}'.rstrip()

    if op == Op.EMITFLUX:
        src_text = o[0].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        bindings = ' '.join(f'{n}:{s}' for n, s in o[1])
        return f'EMITFLUX "{src_text}" {bindings}'.rstrip()

    if op == Op.COMPILER_FVM_DUMP:
        return 'COMPILER_FVM_DUMP'

    # Fallback: emit op name only (unknown operand shape)
    return op.name


def _rebase_block(instrs, offset):
    """Return a copy of instrs with all jump targets shifted by offset."""
    result = []
    for instr in instrs:
        op = instr.op
        if op in (Op.JMP, Op.JIF, Op.JNF):
            result.append(Instr(op, [instr.operands[0] + offset]))
        elif op == Op.JTABLE:
            new_table = [t + offset for t in instr.operands[1]]
            result.append(Instr(op, [instr.operands[0] + offset, new_table]))
        else:
            result.append(instr)
    return result


def serialise_fvm(
    instructions:    'List[Instr]',
    local_count:     int,
    functions:       'Dict[str, List[Instr]]',
    struct_layouts:  'Dict[str, StructLayout]' = None,
) -> str:
    """
    Serialise a set of VM instructions and function definitions to .fvm text.
    This is the inverse of parse_fvm_source().
    """
    lines = ['# Generated by compiler.fvm.dump', '']

    # Struct layouts
    for layout in (struct_layouts or {}).values():
        lines.append(f'struct {layout.name} {layout.endian} {layout.total_size} {layout.total_bits}')
        for fname, fttag, foff, fsz in layout.fields:
            lines.append(f'    field {fname} {fttag.value} {foff} {fsz}')
        lines.append('endstruct')
        lines.append('')

    # Functions
    for name, instrs in functions.items():
        lines.append(f'func {name}')
        for instr in instrs:
            lines.append(f'    {_serialise_instr(instr)}')
        lines.append('endfunc')
        lines.append('')

    # Main block
    if local_count:
        lines.append(f'locals {local_count}')
    for instr in instructions:
        lines.append(_serialise_instr(instr))

    # Always terminate the main block with HALT so the file is self-contained
    if not lines or lines[-1].strip() != 'HALT':
        lines.append('HALT')
    return '\n'.join(lines) + '\n'




# ---------------------------------------------------------------------------
# .fvm source file parser
# ---------------------------------------------------------------------------

def _fvm_unescape(s: str) -> bytes:
    """Unescape a .fvm string literal body (between the quotes) to bytes."""
    result = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            if   n == 'n':  result.append(ord('\n')); i += 2
            elif n == 'r':  result.append(ord('\r')); i += 2
            elif n == 't':  result.append(ord('\t')); i += 2
            elif n == '0':  result.append(0);          i += 2
            elif n == '\\': result.append(ord('\\')); i += 2
            elif n == '"':  result.append(ord('"'));    i += 2
            else:           result.extend(c.encode('utf-8')); i += 1
        else:
            result.extend(c.encode('utf-8')); i += 1
    return bytes(result)


def _parse_fvm_val(token: str) -> Val:
    """
    Parse a typed literal token into a Val.

    Syntax:
        type:value        e.g.  int:42   float:3.14   bool:1   bytes:"hello"
        "string"          shorthand for bytes:"string"  (BYTES tag, UTF-8)
        ptr:N[meta]       PTR with meta dict encoded as a bracketed suffix

    PTR meta bracket format: [struct_type=NAME,stack_slot,field:offset,...]
    """
    # Bare quoted string -> BYTES
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        raw = _fvm_unescape(token[1:-1])
        return Val(TTag.BYTES, raw)

    if ':' not in token:
        raise VMError(f'.fvm: cannot parse value token {token!r} (expected type:value)')

    type_str, _, rest = token.partition(':')
    type_str = type_str.strip().lower()

    # Strip and parse optional [meta] bracket from the value portion.
    # Only look for '[' outside of a quoted string value.
    meta = {}
    raw  = rest
    if '[' in rest:
        # Find '[' that is not inside a quoted string
        _q = rest.find('"')
        _b = rest.find('[')
        if _b != -1 and (_q == -1 or _b < _q):
            bracket_start = _b
            raw = rest[:bracket_start]
        else:
            bracket_start = -1
    else:
        bracket_start = -1
    if bracket_start != -1:
        bracket_content = rest[bracket_start + 1:].rstrip(']')
        for item in bracket_content.split(','):
            item = item.strip()
            if not item:
                continue
            if item == 'stack_slot':
                meta['stack_slot'] = True
            elif item.startswith('struct_type='):
                meta['struct_type'] = item[len('struct_type='):]
            elif item.startswith('elem_type='):
                meta['elem_type'] = item[len('elem_type='):]
            elif item.startswith('count='):
                meta['count'] = int(item[len('count='):])
            elif item.startswith('f:'):
                # Struct field: f:fname=type:value
                rest = item[2:]
                fname, _, fval_str = rest.partition('=')
                if 'fields' not in meta:
                    meta['fields'] = {}
                meta['fields'][fname] = _parse_fvm_val(fval_str)
            elif item.startswith('e:') and '=' in item:
                # Array element: e:idx=type:value
                rest = item[2:]
                idx_str, _, eval_str = rest.partition('=')
                idx = int(idx_str)
                if 'elements' not in meta:
                    meta['elements'] = {}
                meta['elements'][idx] = _parse_fvm_val(eval_str)
            elif ':' in item:
                fname, _, foffset = item.partition(':')
                if 'field_bit_offsets' not in meta:
                    meta['field_bit_offsets'] = {}
                meta['field_bit_offsets'][fname] = int(foffset)

    if type_str == 'bytes':
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            raw = _fvm_unescape(raw[1:-1])
        else:
            raw = raw.encode('utf-8')
        return Val(TTag.BYTES, raw)

    tag_map = {
        'int':    TTag.INT,    'uint':   TTag.UINT,
        'long':   TTag.LONG,   'ulong':  TTag.ULONG,
        'float':  TTag.FLOAT,  'double': TTag.DOUBLE,
        'bool':   TTag.BOOL,   'byte':   TTag.BYTE,
        'char':   TTag.CHAR,   'ptr':    TTag.PTR,
        'void':   TTag.VOID,
    }
    if type_str not in tag_map:
        raise VMError(f'.fvm: unknown type tag {type_str!r} in {token!r}')

    tag = tag_map[type_str]
    if tag in (TTag.FLOAT, TTag.DOUBLE):
        return Val(tag, float(raw))
    elif tag == TTag.VOID:
        return Val(tag, 0)
    elif tag == TTag.BOOL:
        if raw.lower() in ('true', '1'):
            return Val(tag, 1)
        elif raw.lower() in ('false', '0'):
            return Val(tag, 0)
        raise VMError(f'.fvm: invalid bool value {raw!r}')
    else:
        # Convert elements sparse dict to ordered list
        if 'elements' in meta and isinstance(meta['elements'], dict):
            count = meta.get('count', max(meta['elements'].keys()) + 1 if meta['elements'] else 0)
            etag  = _str_to_ttag(meta.get('elem_type', 'int'))
            lst   = [meta['elements'].get(j, Val(etag, 0)) for j in range(count)]
            meta['elements'] = lst
        return Val(tag, int(raw, 0), meta)


def _parse_ttag(token: str) -> TTag:
    """Parse a bare type-tag name into a TTag."""
    _map = {t.value: t for t in TTag}
    if token not in _map:
        raise VMError(f'.fvm: unknown TTag {token!r}')
    return _map[token]


class FVMParseError(Exception):
    def __init__(self, message: str, lineno: int):
        super().__init__(f'line {lineno}: {message}')
        self.lineno = lineno


def _fvm_split(line: str) -> list:
    """
    Split a .fvm source line into tokens, keeping quoted strings and
    bracketed meta suffixes intact.

    Token forms:
      - bare word
      - "quoted string" (may contain spaces)
      - word:"quoted string"   (e.g. bytes:"hello world")
      - type:value[meta...]    (e.g. ptr:29[struct_type=TB,stack_slot,a:0])
        The [...] portion is part of the same token.
    """
    tokens = []
    i = 0
    n = len(line)
    while i < n:
        if line[i].isspace():
            i += 1
            continue
        j = i
        # Consume non-whitespace prefix up to a quote or end
        while j < n and not line[j].isspace() and line[j] != '"':
            j += 1
        prefix = line[i:j]
        if j < n and line[j] == '"':
            # Quoted section: absorb into current token
            j += 1
            while j < n:
                if line[j] == '\\':
                    j += 2
                    continue
                if line[j] == '"':
                    j += 1
                    break
                j += 1
            tokens.append(line[i:j])
        else:
            if prefix:
                tokens.append(prefix)
        i = j
    return tokens


def parse_fvm_source(source: str):
    """
    Parse a .fvm text file into (instructions, local_count, functions, struct_layouts).
    """
    instructions: List[Instr] = []
    functions:    Dict[str, List[Instr]] = {}
    struct_layouts: Dict[str, StructLayout] = {}
    local_count   = 0
    in_func       = False
    func_name     = ''
    func_instrs:  List[Instr] = []
    in_struct     = False
    struct_name   = ''
    struct_endian = 'little'
    struct_total_size = 0
    struct_total_bits = 0
    struct_fields: list = []

    op_by_name: Dict[str, Op] = {o.name: o for o in Op}
    lines_src = source.splitlines()

    for lineno, raw_line in enumerate(lines_src, start=1):
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue

        tokens = _fvm_split(line)
        if not tokens:
            continue
        directive = tokens[0].upper()

        if directive == 'LOCALS':
            if len(tokens) != 2:
                raise FVMParseError("'locals' requires exactly one argument", lineno)
            if not in_func:
                local_count = int(tokens[1], 0)
            continue

        if directive == 'STRUCT':
            if in_struct:
                raise FVMParseError("nested 'struct' is not allowed", lineno)
            if len(tokens) < 2:
                raise FVMParseError("'struct' requires a name", lineno)
            in_struct         = True
            struct_name       = tokens[1]
            struct_endian     = tokens[2] if len(tokens) > 2 else 'little'
            struct_total_size = int(tokens[3], 0) if len(tokens) > 3 else 0
            struct_total_bits = int(tokens[4], 0) if len(tokens) > 4 else 0
            struct_fields     = []
            continue

        if directive == 'FIELD':
            if not in_struct:
                raise FVMParseError("'field' outside 'struct' block", lineno)
            if len(tokens) < 5:
                raise FVMParseError("'field' requires fname ttag byte_offset byte_size", lineno)
            fname   = tokens[1]
            fttag   = _parse_ttag(tokens[2])
            foff    = int(tokens[3], 0)
            fsz     = int(tokens[4], 0)
            struct_fields.append((fname, fttag, foff, fsz))
            continue

        if directive == 'ENDSTRUCT':
            if not in_struct:
                raise FVMParseError("'endstruct' without matching 'struct'", lineno)
            layout = StructLayout(
                name=struct_name,
                fields=struct_fields,
                total_size=struct_total_size,
                endian=struct_endian,
                total_bits=struct_total_bits,
            )
            struct_layouts[struct_name] = layout
            in_struct = False
            continue

        if directive == 'FUNC':
            if in_func:
                raise FVMParseError("nested 'func' is not allowed", lineno)
            if len(tokens) < 2:
                raise FVMParseError("'func' requires a name", lineno)
            in_func     = True
            func_name   = tokens[1]
            func_instrs = []
            continue

        if directive == 'ENDFUNC':
            if not in_func:
                raise FVMParseError("'endfunc' without matching 'func'", lineno)
            functions[func_name] = func_instrs
            in_func   = False
            func_name = ''
            continue

        op_name = tokens[0].upper()
        if op_name not in op_by_name:
            raise FVMParseError(f'unknown opcode {tokens[0]!r}', lineno)
        op = op_by_name[op_name]

        try:
            operands = _parse_operands(op, tokens[1:], lineno)
        except FVMParseError:
            raise
        except Exception as e:
            raise FVMParseError(str(e), lineno)

        instr = Instr(op, operands)
        if in_func:
            func_instrs.append(instr)
        else:
            instructions.append(instr)

    if in_func:
        raise FVMParseError(f"unterminated 'func {func_name}' at end of file", len(lines_src))
    if in_struct:
        raise FVMParseError(f"unterminated 'struct {struct_name}' at end of file", len(lines_src))

    return instructions, local_count, functions, struct_layouts

def _parse_operand_token(token: str):
    if (token.startswith('"') and token.endswith('"')) or ':' in token:
        return _parse_fvm_val(token)
    try:
        return int(token, 0)
    except ValueError:
        return token


def _parse_operands(op: Op, raw_tokens: List[str], lineno: int) -> list:
    _zero_op = {
        Op.POP, Op.DUP, Op.SWAP, Op.ROT, Op.OVER,
        Op.ADD, Op.SUB, Op.MUL, Op.DIV, Op.MOD, Op.NEG, Op.POW,
        Op.ABS, Op.MIN, Op.MAX, Op.CLAMP,
        Op.BAND, Op.BOR, Op.BXOR, Op.BNOT, Op.SHL, Op.SHR,
        Op.POPCOUNT,
        Op.CMP_EQ, Op.CMP_NE, Op.CMP_LT, Op.CMP_LE, Op.CMP_GT, Op.CMP_GE,
        Op.AND, Op.OR, Op.NOT,
        Op.RET, Op.HALT,
        Op.LOCAL_DEREF, Op.LOCAL_DEREF_SET,
        Op.ALLOC, Op.FREE, Op.OFFSET,
        Op.ARRAY_LEN, Op.ARRAY_LOAD, Op.ARRAY_STORE,
        Op.ENUM_LOAD, Op.ENUM_STORE,
        Op.BITSLICE,
        Op.TYPEOF,
        Op.IO_OPEN, Op.IO_READ, Op.IO_WRITE, Op.IO_CLOSE,
        Op.FFI_FREE,
        Op.COMPILER_PRINT, Op.COMPILER_INPUT,
        Op.COMPILER_READFILE, Op.COMPILER_WRITEFILE,
        Op.COMPILER_FVM_DUMP,
        Op.COMPILER_LOADLIB,
        Op.COMPILER_IMPORT_STDLIB, Op.COMPILER_IMPORT_LOCAL, Op.COMPILER_FPM_PACKAGE,
        Op.COMPILER_FVM_TRACE_BEGIN, Op.COMPILER_FVM_TRACE_END,
        Op.COMPILER_FVM_SETBP,
        Op.STR_LEN, Op.STR_CAT, Op.STR_SLICE, Op.STR_EQ, Op.STR_FIND,
        Op.INT_TO_STR, Op.STR_TO_INT,
        Op.ASSERT, Op.WARN, Op.PANIC,
        Op.EMIT_CONST, Op.EMIT_TYPE,
        Op.THROW, Op.TRY_END,
    }
    if op in _zero_op:
        return []

    if op == Op.PUSH:
        if not raw_tokens:
            raise FVMParseError('PUSH requires a value operand', lineno)
        token = raw_tokens[0]
        # Tolerate a missing '[' before meta on PTR tokens:
        # 'ptr:N struct_type=...' -> fuse into 'ptr:N[struct_type=...]'
        if token.startswith('ptr:') and '[' not in token and len(raw_tokens) > 1:
            fused = token + '[' + ','.join(raw_tokens[1:])
            if not fused.endswith(']'):
                fused += ']'
            token = fused
        return [_parse_fvm_val(token)]

    if op == Op.CALL_PTR:
        if not raw_tokens:
            raise FVMParseError('CALL_PTR requires an argc operand', lineno)
        return [int(raw_tokens[0], 0)]

    _single_int_op = {
        Op.JMP, Op.JIF, Op.JNF,
        Op.LOCAL_GET, Op.LOCAL_SET,
        Op.TAIL_SELF,
        Op.EMIT_GLOBAL,
        Op.TRY_BEGIN,
    }
    if op in _single_int_op:
        if not raw_tokens:
            raise FVMParseError(f'{op.name} requires an integer operand', lineno)
        return [int(raw_tokens[0], 0)]

    _width_op = {Op.ROTL, Op.ROTR, Op.BITREV, Op.CLZ, Op.CTZ}
    if op in _width_op:
        if not raw_tokens:
            raise FVMParseError(f'{op.name} requires a width operand', lineno)
        return [int(raw_tokens[0], 0)]

    _type_name_op = {Op.SIZEOF, Op.ALIGNOF, Op.ENDIANOF,
                     Op.STRUCT_NEW, Op.STRUCT_LOAD, Op.STRUCT_STORE,
                     Op.ENUM_NEW,
                     Op.GLOBAL_GET, Op.GLOBAL_SET}

    if op == Op.EXTERN_DECL:
        if len(raw_tokens) < 2:
            raise FVMParseError('EXTERN_DECL requires name and ret_tag', lineno)
        ttag_map = {t.name: t for t in TTag}
        ret_tag = ttag_map.get(raw_tokens[1].upper(), TTag.VOID)
        return [raw_tokens[0], ret_tag]
    if op in _type_name_op:
        if not raw_tokens:
            raise FVMParseError(f'{op.name} requires a type name operand', lineno)
        return [raw_tokens[0]]

        if not raw_tokens:
            raise FVMParseError(f'{op.name} requires a field name operand', lineno)
        return [raw_tokens[0]]

    if op == Op.ARRAY_NEW:
        if len(raw_tokens) < 2:
            raise FVMParseError('ARRAY_NEW requires type_name and count', lineno)
        return [raw_tokens[0], int(raw_tokens[1], 0)]

    if op in (Op.LOAD, Op.STORE):
        if len(raw_tokens) < 2:
            raise FVMParseError(f'{op.name} requires ttag and byte_size', lineno)
        return [_parse_ttag(raw_tokens[0]), int(raw_tokens[1], 0)]

    if op in (Op.CAST, Op.BITCAST):
        if not raw_tokens:
            raise FVMParseError(f'{op.name} requires a type tag operand', lineno)
        if len(raw_tokens) > 1:
            return [_parse_ttag(raw_tokens[0]), raw_tokens[1]]
        return [_parse_ttag(raw_tokens[0])]

    if op == Op.CALL:
        if len(raw_tokens) < 2:
            raise FVMParseError('CALL requires name and argc', lineno)
        return [raw_tokens[0], int(raw_tokens[1], 0)]

    if op == Op.FFI_LOAD:
        if not raw_tokens:
            raise FVMParseError('FFI_LOAD requires a library path', lineno)
        return [raw_tokens[0].strip('"')]

    if op == Op.FFI_SYM:
        if not raw_tokens:
            raise FVMParseError('FFI_SYM requires a symbol name', lineno)
        return [raw_tokens[0]]

    if op == Op.FFI_CALL:
        if len(raw_tokens) < 2:
            raise FVMParseError('FFI_CALL requires argc and ret_type_tag', lineno)
        return [int(raw_tokens[0], 0), _parse_ttag(raw_tokens[1])]

    if op == Op.JTABLE:
        if len(raw_tokens) < 1:
            raise FVMParseError('JTABLE requires at least a default address', lineno)
        default = int(raw_tokens[0], 0)
        table   = [int(t, 0) for t in raw_tokens[1:]]
        return [default, table]

    if op == Op.EMITFLUX:
        if not raw_tokens:
            raise FVMParseError('EMITFLUX requires a source text operand', lineno)
        src_text = raw_tokens[0].strip('"').encode('utf-8').decode('unicode_escape')
        var_names = []
        for tok in raw_tokens[1:]:
            if ':' in tok:
                n, _, s = tok.partition(':')
                var_names.append((n, int(s, 0)))
        return [src_text, var_names]

    if op == Op.STR_SLICE:
        return []

    if op == Op.INLINE_ASM:
        if len(raw_tokens) < 4:
            raise FVMParseError('INLINE_ASM requires body, constraints, n_inputs, n_outputs', lineno)
        def _unescape(s: str) -> str:
            return s.strip('"').replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
        body        = _unescape(raw_tokens[0])
        constraints = _unescape(raw_tokens[1])
        n_inputs    = int(raw_tokens[2], 0)
        n_outputs   = int(raw_tokens[3], 0)
        out_names   = list(raw_tokens[4:])
        return [body, constraints, n_inputs, n_outputs, out_names]

    raise FVMParseError(f'unhandled operand encoding for {op.name}', lineno)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _fvm_main():
    import sys as _sys

    if len(_sys.argv) < 2:
        print('Flux VM')
        print('Usage: python fvm.py <program.fvm>')
        print()
        print('Runs a .fvm opcode file on the Flux Virtual Machine.')
        _sys.exit(0)

    path = _sys.argv[1]
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            source = fh.read()
    except OSError as e:
        print(f'fvm: cannot open {path!r}: {e}', file=_sys.stderr)
        _sys.exit(1)

    try:
        instructions, local_count, functions, struct_layouts = parse_fvm_source(source)
    except FVMParseError as e:
        print(f'fvm: parse error in {path}: {e}', file=_sys.stderr)
        _sys.exit(1)

    vm = FluxVM(struct_layouts=struct_layouts)
    try:
        from fvmcodegen import FVMCodegen as _FVMCodegen
        vm._codegen_class = _FVMCodegen
    except ImportError:
        pass
    try:
        from fmacros import build_compiler_macros as _build_macros
        vm._compiler_constants = _build_macros()
    except ImportError:
        pass
    for name, instrs in functions.items():
        vm.register_function(name, instrs)

    try:
        result = vm.execute(instructions, local_count)
    except VMError as e:
        print(f'fvm: runtime error: {e}', file=_sys.stderr)
        _sys.exit(1)

    for entry in vm.emit_results:
        kind = entry[0]
        if kind == 'const':
            print(f'[emit:const] {entry[1]}')
        elif kind == 'global':
            print(f'[emit:global] {entry[1].hex()}')
        elif kind == 'type':
            print(f'[emit:type] {entry[1]}')
        elif kind == 'flux':
            print(f'[emit:flux] {entry[1]}')


if __name__ == '__main__':
    import sys as _sys
    _sys.modules.setdefault('fvm', _sys.modules['__main__'])
    _fvm_main()