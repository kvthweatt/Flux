# Flux Programming Language - AGENTS.md

**Target Audience:** Autonomous AI coding agents (Claude Code, Codex CLI, Gemini CLI, Cursor, Aider, OpenHands, Roo Code, Continue, Warp AI, GitHub Copilot, etc.)

---

# Project Overview

Flux is a compiled, statically-typed systems programming language implemented in Python with an LLVM backend. It targets native x86-64, ARM64, and 16-bit DOS/bootloader.

**Key Characteristics:**
- **Compiler implemented in Python** — Not self-hosted. All compiler passes are Python modules in `src/compiler/`
- **Stack-allocated by default** — Everything lives on stack unless explicitly `heap` allocated
- **Arbitrary-width integers with alignment/endianness in type** — `data{13:16}` = 13-bit signed, 16-bit aligned
- **Bit slices as first-class** — `x[0``7]` extracts bits 0-7 (MSB=0), `x[7``0]` reverses
- **Compile-time execution via FVM** — `comptime { ... }` blocks run Flux code at compile time
- **emitflux code generation** — Inject Flux definitions from comptime loops via `emitflux { ... }`
- **Opt-in ownership/borrow checker** — `~int` tied variables, `~` operator for moves
- **Custom infix operators** — `operator (int, int)[+++] -> int`
- **Templates with type geometry constraints** — `constraint NoNarrowing(A) { A !`< A }`
- **Contracts** — Pre/post conditions attached to functions/operators via `: ContractName`
- **No GC** — Manual memory management; `(void)ptr` frees, `defer` for RAII-style cleanup
- **Raw bytecode functions** — `def{}* fp()->void = @bytecode;`

---

# Repository Structure

```
Flux/
├── fxc.py                  # Compiler entrypoint (CLI)
├── fbc.py                  # Borrow checker (standalone)
├── fbc_alias.py            # Alias map & violation detection
├── fbc_report.py           # Violation reporting
├── fpm.py                  # Flux Package Manager
├── fvm.py                  # Flux Virtual Machine (comptime & REPL)
├── fvm_test.py             # FVM self-tests
├── frepl.py                # REPL
├── tg.py                   # Type geometry visualizer
├── cft.py                  # C→Flux translator
├── config/
│   └── flux_configuration.cfg  # INI config: target, optimization, LLVM paths
├── src/
│   ├── compiler/           # Compiler core (all .py)
│   │   ├── fc.py           # FluxCompiler: orchestrates pipeline, LLVM IR gen
│   │   ├── fast.py         # AST node definitions (dataclasses)
│   │   ├── flexer.py       # Lexer (TokenType enum, FluxLexer class)
│   │   ├── fparser.py      # Recursive-descent parser → AST
│   │   ├── fpreprocess.py  # Preprocessor (#import, #def, #ifdef, #psub)
│   │   ├── ftypesys.py     # TypeSystem, TypeResolver, SymbolTable, mangling
│   │   ├── fcodegen.py     # LLVM IR CodegenVisitor (visit_<Node>)
│   │   ├── fvmcodegen.py   # FVM bytecode CodegenVisitor for comptime
│   │   ├── fmacros.py      # Built-in compiler macros
│   │   ├── fdce.py         # Dead code elimination
│   │   ├── ferrors.py      # Custom exceptions, diagnostic formatting
│   │   ├── flogger.py      # Structured logging (levels, components, colors)
│   │   └── fconfig.py      # Config loader
│   └── stdlib/             # Standard library (.fx files)
│       ├── standard.fx     # Core prelude (io, strings, math, etc.)
│       ├── runtime/        # Allocators, threading, atomics, exceptions
│       ├── builtins/       # Low-level object implementations
│       └── *.fx            # Domain modules: math, crypto, net, vulkan, opengl, tensors, neuralnet, etc.
├── docs/
│   ├── Specs/language_specification.md  # Complete language reference
│   ├── learn_flux_intro.md              # Beginner tutorial
│   ├── learn_flux_adept.md              # Advanced tutorial
│   ├── style_guide.md                   # Coding conventions
│   ├── keyword_reference.md
│   ├── operator_reference.md
│   ├── algebraic_types.md               # Type geometry constraints
│   ├── fbc.md                           # Borrow checker
│   ├── fpm.md                           # Package manager
│   ├── fvm.md                           # FVM / comptime
│   └── Compiler/                        # Architecture docs
├── examples/                # Example programs (.fx)
├── tests/                   # Test suite (.fx files + coreutils C tests)
├── editor-support/          # Editor plugins (vscode, sublime, notepad++)
├── tree-sitter-flux/        # Tree-sitter grammar (grammar.js)
├── build/                   # Build output (gitignored)
├── .fpm/                    # FPM package cache
└── LICENSE
```

---

# High-Level Architecture

## Compilation Pipeline

```
.fx source
    ↓
Preprocessor (fpreprocess.py) → build/tmp.fx
    ↓
Lexer (flexer.py) → Token stream
    ↓
Parser (fparser.py) → AST (fast.py nodes)
    ↓
[Optional] Borrow Checker (fbc.py) → errors/warnings
    ↓
[Optional] DCE (fdce.py) → pruned AST
    ↓
IR Generator (fcodegen.py: CodegenVisitor) → LLVM IR (llvmlite)
    ↓
Write build/<name>/<name>.ll
    ↓
llc (LLVM static compiler) → build/<name>/<name>.o
    ↓
clang / lld-link → executable
```

**Key modules:**
- `fc.py` — `FluxCompiler` class, orchestrates everything, platform/triple detection
- `fast.py` — All AST node classes (`@dataclass`), `ASTNode` base with `accept(visitor)`
- `flexer.py` — `FluxLexer`, `TokenType` enum (100+ tokens), keyword map
- `fparser.py` — `FluxParser`, recursive descent with precedence climbing
- `ftypesys.py` — `TypeSystem`, `TypeResolver`, `SymbolTable`, name mangling
- `fcodegen.py` — `CodegenVisitor`, per-node `visit_<Node>` methods
- `fvmcodegen.py` — `FVMCodegen`, compiles comptime blocks to FVM bytecode
- `fvm.py` — `FluxVM` stack VM, executes comptime bytecode, REPL backend
- `fpreprocess.py` — `FXPreprocessor`, handles `#import`, `#def`, `#ifdef`, `#psub`
- `fmacros.py` — `build_compiler_macros()` for predefined macros
- `fdce.py` — `eliminate(ast, entry)` marks unused functions
- `fbc.py` — `BorrowChecker`, flow-sensitive analysis on AST + call graph
- `flogger.py` — `FluxLogger`, `FluxLoggerConfig`, component filtering
- `fconfig.py` — `load_config()`, `config` dict, `get_byte_width()`

---

# Build System

## Requirements
- Python 3.12+
- LLVM 21+ (`llvmlite`)
- `clang` and `lld` (or `lld-link` on Windows) in PATH or config `llvm_path`

## Configuration (`config/flux_configuration.cfg`)
```ini
[compiler]
target = native           # native | dos | bootloader
optimize = true
debug_symbols = false
llvm_path =               # Optional: D:\LLVM\bin or /usr/lib/llvm-21/bin

[paths]
stdlib = src/stdlib
include =

[logging]
level = 3                 # 0=silent 1=error 2=warn 3=info 4=debug 5=trace
color = true
timestamp = false
```

## CLI (`python fxc.py`)
```bash
python fxc.py input.fx [options]

Basic:
  -o <name>              Output binary name
  -v <0-5>               Legacy verbosity
  --library              Emit static library (.a/.lib)
  -lib <lib1> <lib2>     Extra libraries to link

Targets:
  -dos                   16-bit DOS target
  -com                   DOS COM file (requires -dos)

Borrow checker:
  --borrowcheck          Enable (errors block compilation)
  --borrowcheck-warn     Warning-only mode

LLVM backend:
  --march <arch>         Target architecture (x86-64, aarch64, etc.)
  --mcpu <cpu>           Target CPU (native, skylake, apple-m1)
  --mattr <attrs>        Target attributes (+avx2,+sse4.2)

Logging:
  --log-level <0-5>
  --log-file <path>
  --log-timestamp
  --log-no-color
  --log-filter <comp>    Comma-separated: lexer,parser,compiler,build,preprocessor

Advanced:
  --entrypoint <name>    Override entry function (default: FRTStartup)
```

## Build Output
```
build/
  tmp.fx                 # Preprocessed source
  <program>/
    <program>.ll         # LLVM IR
    <program>.o          # Object file
    <program>            # Executable (or .exe on Windows)
```

---

# Development Environment

## Running Tests
- FVM self-tests: `python fvm_test.py`
- Compiler tests: compile and run `.fx` files in `tests/`
- Each test has `main() -> int` returning 0 on success

## Adding a Test
1. Create `tests/<feature>_test.fx` with `main() -> int` returning 0 on success
2. Use `assert(condition, "message")` for checks (throws if false in try/catch)
3. Ensure it compiles and runs cleanly

## Debugging the Compiler
- Verbose trace: `python fxc.py test.fx --log-level 5 --log-filter compiler,codegen`
- Dump LLVM IR: `python fxc.py test.fx -o build/test && cat build/test/test.ll`
- FVM trace: Inside comptime use `compiler.fvm.trace.begin()` / `.end()`

---

# How To Build

```bash
# Standard build (native executable)
python fxc.py examples/helloworld.fx -o build/hello

# With borrow checking
python fxc.py examples/ownership.fx --borrowcheck -o build/ownership

# DOS COM file
python fxc.py examples/boot.fx -dos -com -o build/boot.com

# Static library
python fxc.py src/mylib.fx --library -o build/mylib.a

# Cross-compile (requires LLVM target)
python fxc.py test.fx --march aarch64 --mcpu cortex-a72 --mattr +neon
```

---

# How To Test

## Test Categories
| Location | Purpose |
|----------|---------|
| `tests/*.fx` | Language feature tests (compile + run) |
| `tests/coreutils/*.c` | C programs for FFI/interop testing |
| `fvm_test.py` | FVM opcode-level unit tests |
| `examples/*.fx` | Larger integration tests |

## Running a Test File
```bash
python fxc.py tests/struct_test.fx -o build/struct_test && build/struct_test
# Exit code 0 = pass, non-zero = fail
```

---

# How To Debug

## Compiler Debug Logs
```bash
# Full trace to file
python fxc.py test.fx --log-level 5 --log-file build/debug.log

# Component-filtered
python fxc.py test.fx --log-level 4 --log-filter parser,lexer
```

## LLVM IR Inspection
```bash
python fxc.py test.fx -o build/test
cat build/test/test.ll
```

## FVM Bytecode Dump
```flux
comptime {
    compiler.fvm.dump("build/trace.fvm");  // Serializes VM state
}
```

## Source Location Mapping
- Preprocessor writes `build/tmp.fx` (merged source)
- Parser attaches `source_line`, `source_col` to every AST node
- `fc.py` stores `_flux_line_map` on module: global_line → (filename, local_line)
- Codegen uses `_src_loc_with_source(node, module)` for diagnostics

---

# Coding Standards

## Python Style (Compiler Code)
- **Formatter:** `black` (line-length=100, target py310)
- **Linter:** `flake8`
- **Types:** `mypy` strict (`disallow_untyped_defs = true`)
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants
- **Imports:** Group stdlib → third-party → local; absolute imports from `src.compiler`
- **Dataclasses:** Use `@dataclass` with `field(default_factory=list)` for mutable defaults
- **No `Any` unless unavoidable** — prefer `Union` or protocols

## AST Node Conventions (`fast.py`)
```python
@dataclass
class MyNode(ASTNode):
    field: Type
    optional_field: Optional[Type] = None
    list_field: List[Type] = field(default_factory=list)
    
    # Always call set_location(line, col) in parser before returning
    # Base ASTNode has accept(visitor) → visitor.visit(self)
```

## Visitor Pattern (Codegen)
- `fcodegen.py`: `CodegenVisitor.visit(node, builder, module)` dispatches to `visit_<ClassName>`
- `fvmcodegen.py`: `FVMCodegen._visit_<ClassName>` emits `Instr(op, operands)`
- Never put codegen logic in AST nodes (except legacy `codegen()` stubs being phased out)

## Error Reporting
- Use `FluxCodegenError(msg, node, module)` for codegen errors (includes source snippet)
- Use `FluxParseError(msg, token)` for parse errors
- Use `logger.error(msg, component)` for compiler-phase errors
- Format: `[ERROR] file.fx:line:col: message\n    source line\n    ^`

## Logging
```python
from flogger import FluxLogger, LogLevel, FluxLoggerConfig
logger = FluxLoggerConfig.create_logger(name="my_pass", level=LogLevel.DEBUG)
logger.step("Pass name", LogLevel.INFO, "component")
logger.debug("detail", "component")
```

---

# Documentation Standards

- **Language features:** Document in `docs/Specs/language_specification.md` with runnable examples
- **API docs:** Docstrings on public classes/functions (Google style)
- **Compiler internals:** `docs/Compiler/compiler_architecture.md`
- **Keywords/operators:** `docs/keyword_reference.md`, `docs/operator_reference.md`
- **Tutorials:** `docs/learn_flux_intro.md`, `docs/learn_flux_adept.md`
- **Style guide:** `docs/style_guide.md`

---

# Performance Philosophy

1. **Zero-cost abstractions** — Templates, operators, bit-slices compile to optimal IR
2. **Stack-first** — No hidden heap allocations; `heap` is explicit opt-in
3. **No mandatory runtime** — No GC, no heavy runtime; `FRTStartup` minimal
4. **Compile-time computation** — `comptime` + `emitflux` moves work to build
5. **LLVM optimization** — Default `-O3` equivalent via `llc` flags
6. **Avoid allocations in hot paths** — Reuse buffers, prefer `data{N}` over heap

---

# Safety Rules

- **Never commit to `main` directly** — Use feature branches + PR
- **Never disable borrow checker in CI** — `--borrowcheck` must pass
- **Never hardcode paths** — Use `FLUXC_SRCDIR` env var or `Path(__file__).parent`
- **Never change grammar without updating parser tests** — Tree-sitter + `fparser.py` must agree
- **Never change mangling without migration** — Breaks ABI compatibility
- **Never add heap allocation in compiler hot loops** — Use object pools or pre-allocation

---

# Repository Invariants

| Invariant | Enforced By |
|-----------|-------------|
| `build/` is gitignored | `.gitignore` |
| All `.fx` files parse without error | CI runs compiler on test suite |
| `fvm_test.py` passes | CI |
| `black --check src/` passes | CI |
| `mypy src/` passes | CI |
| No `print()` in compiler (use logger) | Code review |
| LLVM IR verifies (`llvm-as`) | `fc.py` calls `module.verify()` |

---

# Compiler Overview

## Lexer (`flexer.py`)
- **Single-pass**, character-by-character with `position`, `line`, `column` tracking
- **Token types:** 100+ in `TokenType` enum (keywords, literals, operators, delimiters)
- **Multi-char tokens:** Sorted by length (6-char → 1-char) for greedy matching
- **Special:** `#"` (DITTO), `~$` (CODIFY), `` `` `` (BITSLICE), `..` (RANGE), `::` (SCOPE)
- **String handling:** Escape sequences (`\n`, `\t`, `\xHH`, `\0`), f-strings, i-strings
- **Number literals:** Decimal, hex (`0x`), octal (`0o`), binary (`0b`), duotrigesimal (`0d`), with `u`/`l`/`b` suffixes

## Parser (`fparser.py`)
- **Recursive descent** with **precedence climbing** for expressions
- **Precedence levels** (loosest → tightest): assignment → ternary → null-coalesce → logical or/and/xor → bitwise or/nor/xor/nand → equality → relational → shift → range → additive → custom infix → multiplicative/power → cast → unary → postfix
- **Ambiguity resolution:** `conflicts` in grammar; parser uses context (e.g., `in` in `for` vs expression)
- **Template parsing:** `<T, U>` after identifier → `TemplateDef` with constraints
- **Comptime blocks:** Parsed as `ComptimeBlock(name?, body)` statements
- **Emitflux:** Parsed as `EmitFlux(body, terminator)` where terminator is `};` or `}#;`

## AST (`fast.py`)
Key node categories:
- **Declarations:** `FunctionDef`, `StructDef`, `ObjectDef`, `EnumDef`, `UnionDef`, `TraitDef`, `InterfaceDef`, `NamespaceDef`, `TypeDeclaration`, `VariableDeclaration`, `OperatorDef`, `ContractDef`, `ConstraintsDef`, `TemplateDef`
- **Statements:** `Block`, `IfStatement`, `WhileLoop`, `ForLoop`, `DoLoop`, `SwitchStatement`, `TryBlock`, `ReturnStatement`, `BreakStatement`, `ContinueStatement`, `DeferStatement`, `ThrowStatement`, `LabelStatement`, `GotoStatement`, `JumpStatement`, `ExpressionStatement`, `UsingStatement`, `NotUsingStatement`, `DeprecateStatement`, `AssertStatement`, `ComptimeBlock`, `EmitFlux`, `FluxVMBlock`, `ExternBlock`
- **Expressions:** `Literal`, `Identifier`, `BinaryOp`, `UnaryOp`, `CastExpression`, `TypeConvertExpression`, `FunctionCall`, `MethodCall`, `MemberAccess`, `ArrayAccess`, `ArraySlice`, `BitSlice`, `PointerDeref`, `AddressOf`, `StringLiteral`, `FStringLiteral`, `IStringLiteral`, `ArrayLiteral`, `StructLiteral`, `RangeExpression`, `ArrayComprehension`, `InExpression`, `HasExpression`, `TernaryOp`, `IfExpression`, `VariadicAccess`, `InlineAsm`, `LambdaExpression`, `ScopeAccess`, `Stringify`, `DittoExpression`
- **Types:** `TypeSystem` (in `ftypesys.py`), `DataType`, `StorageClass`, `Operator`

## Semantic Analysis / Type Checking (`ftypesys.py`)
- **TypeSystem** — Complete type descriptor: `base_type`, `bit_width`, `alignment`, `endianness`, `is_signed`, `is_const`, `is_volatile`, `is_pointer`, `pointer_depth`, `is_array`, `array_size`, `array_dimensions`, `custom_typename`, `storage_class`, `no_functions`
- **TypeResolver** — Resolves `data{13:16}` strings, handles `as` aliases, endianness, pointer/array decoration
- **SymbolTable** — Unified scope management (global + nested), namespace tracking, using/!using, overload registry, trait/interface registries
- **Name Mangling** — `<ns>__<name>__<argc>__<param_types>__ret_<ret_type>` with endianness suffix `E0`/`E1`
- **Constraint Checking** — Template relational constraints (`~=`, `!~=`, `!@`, `` !`< ``, `` !`<= ``, `` !`> ``, `` !`>= ``) evaluated during instantiation by walking instantiated body

## Intermediate Representation
- **LLVM IR via llvmlite** — `ir.Module`, `ir.IRBuilder`, `ir.Function`, `ir.BasicBlock`
- **Target triples/data layouts:** x86-64 Windows/Linux/macOS, ARM64 macOS/Linux, i386 DOS/bootloader
- **Calling conventions:** `fastcall` (default), `cdecl`, `stdcall`, `thiscall`, `vectorcall` via `FunctionDef.calling_conv`

## Optimizer
- **DCE only** (`fdce.py`) — Marks reachable from entrypoint (`FRTStartup`), removes unreferenced functions
- **LLVM passes** — Via `llc -O3` flags: misched, tail-merge, regalloc optimize, tailcallopt, disable-verify

## Code Generation (`fcodegen.py`)
- **Visitor pattern** — `visit_<NodeClass>(node, builder, module)`
- **Type lowering:** `DataType.SINT → i32/i64`, `DATA{N} → iN`, `BOOL → i1`, `BYTE → i8`, pointer → `ptr`
- **Struct layout:** Packed, no padding; fields at declared offsets; `STRUCT_NEW` + `STRUCT_STORE`/`STRUCT_LOAD`
- **Objects:** Struct with methods as functions taking implicit `this` (slot 0); vtables not used (static dispatch)
- **Contracts:** Pre-contract statements injected at function entry; post-contract before each `return`
- **Defer:** Statements pushed to `builder._flux_defer_stack`, emitted in LIFO order before function exit
- **Comptime:** `comptime` blocks compiled by `FVMCodegen` → bytecode → executed by `FluxVM` during Pass 3; `emitflux` fragments collected and re-parsed in Pass 4

## Runtime (`src/stdlib/runtime/`)
- `runtime.fx` — `FRTStartup`, `FRTShutdown`, panic handler
- `allocators.fx` — `fmalloc`, `ffree`, `falloc`, `heap` keyword implementation
- `memory.fx` — `memcpy`, `memset`, `memcmp`
- `threading.fx` — `thread_create`, `thread_join`, mutex
- `atomics.fx` — Atomic RMW ops
- `exceptions.fx` — `try`/`throw`/`catch` lowering
- `shadowstack.fx` — Shadow stack for borrow checker

## Standard Library (`src/stdlib/`)
| Module | Purpose |
|--------|---------|
| `standard.fx` | Prelude: io, strings, math, conversions |
| `io.fx` | File, console, stdin/stdout |
| `math.fx` | Transcendentals, constants |
| `collections.fx` | Dynamic arrays, hash maps |
| `sorting.fx` | Sort algorithms |
| `regex.fx` | PCRE-compatible regex |
| `json.fx` / `toml.fx` / `xml.fx` / `csv.fx` | Serialization |
| `net_linux.fx` / `net_windows.fx` | Sockets |
| `tls.fx` | TLS 1.3 client/server |
| `vulkan.fx` / `opengl.fx` / `directx.fx` | Graphics APIs |
| `tensors.fx` / `matrices.fx` / `vectors.fx` | Linear algebra |
| `neuralnet.fx` / `autograd.fx` | ML primitives |
| `cryptography.fx` | AES, SHA, HMAC, HKDF, x25519, Ed25519 |
| `fhf/*` | Hot-patching framework |

---

# Lexer

## Token Categories
- **Literals:** `SINT_LITERAL`, `UINT_LITERAL`, `SLONG_LITERAL`, `ULONG_LITERAL`, `FLOAT`, `DOUBLE`, `BYTE_LITERAL`, `CHAR`, `STRING_LITERAL`, `BOOL`, `I_STRING`, `F_STRING`, `G_STRING`
- **Keywords:** 80+ (see `docs/keyword_reference.md`)
- **Operators:** All symbols mapped to `TokenType` (see precedence table)
- **Delimiters:** `LEFT_PAREN`, `RIGHT_PAREN`, `LEFT_BRACKET`, `RIGHT_BRACKET`, `LEFT_BRACE`, `RIGHT_BRACE`, `SEMICOLON`, `COMMA`, `DOT`, `COLON`, `BACKSLASH`, `TAG`

## Lexing Rules
1. **Longest match** — 6-char → 1-char token tables consulted in order
2. **Keywords before identifiers** — `keywords` dict checked after identifier scan
3. **String modes:** `"` → `STRING_LITERAL`, `f"` → `F_STRING`, `i"` → `I_STRING`
4. **Number suffixes:** `u`=uint, `l`=long, `ul`=ulong, `b`=byte, `f`=float, `d`=double
5. **Line/column tracking:** Tabs expand to 4 columns; `\n` increments line, resets column

---

# Parser

## Grammar Highlights (from `fparser.py` + `tree-sitter-flux/grammar.js`)

### Top-Level Items
```flux
#import <std.fx>;
#def MACRO value;
namespace ns { def foo() -> void {}; }
struct Point { int x, y; }
object Counter { int v; def __init(int x)->this { this.v=x; return this; } ... }
trait Drawable { def draw() -> void; }
interface DB(Client: Conn, Server: Queryable) { Client : Server { connect() -> bool } ... }
def main() -> int { ... }
```

### Expressions (Precedence Order)
```
assignment (= += -= ... ?= @=)
ternary (?:)
null-coalesce (??)
logical or (| or)
logical and (& and)
logical xor (^^ xor)
bitwise or/nor (`| `!|)
bitwise xor/xnor (`^^ `^^!|)
bitwise and/nand (`& `!&)
equality (== != is is not in !in)
chain arrow (<-)
relational (< <= > >=)
shift (<< >>)
range (..)
additive (+ -)
custom infix (operator [sym])
multiplicative (* / % ^)
cast ((Type)expr)
unary (- + * @ ++ -- ~ `! `^^! `^^!& `^^!|)
postfix ([] [::] .field ++ -- as Type from expr if(...) )
primary (literals, identifiers, (expr), [array], {struct}, sizeof, typeof, etc.)
```

### Special Forms
- **Comptime:** `comptime { ... }` or `comptime Name { ... }` (named blocks are `goto` targets)
- **Emitflux:** `emitflux { def foo() -> int { return 42; }; }` with `}#;` to continue
- **FluxVM inline:** `fluxvm { LOCAL_GET x; PUSH 10; ADD; LOCAL_SET x; }`
- **Struct from:** `Header h from buffer;` (zero-copy reinterpret cast)
- **Bit slice:** `x[0``7] = x[7``0]` (reverse bits)
- **Ditto:** `x = 1, y = #", z = #";` (repeat last initializer)
- **Ternary assign:** `x ?= 5` (assign if x is zero/false)

---

# AST

## Base Class
```python
@dataclass
class ASTNode:
    source_line: int = field(default=0, init=False, repr=False, compare=False)
    source_col:  int = field(default=0, init=False, repr=False, compare=False)
    def set_location(self, line, col) -> 'ASTNode': ...
    def accept(self, visitor, builder, module): ...
```

## Representative Nodes
```python
@dataclass
class FunctionDef(ASTNode):
    name: str
    parameters: List[Parameter]
    return_type: TypeSystem
    body: Block
    contracts: List[str] = field(default_factory=list)  # pre-contract names
    post_contracts: List[str] = field(default_factory=list)
    calling_conv: str = 'fastcall'
    is_template: bool = False
    template_params: List[str] = field(default_factory=list)
    constraints: Dict = field(default_factory=dict)
    no_mangle: bool = False

@dataclass
class BinaryOp(Expression):
    left: Expression
    operator: Operator
    right: Expression

@dataclass
class BitSlice(Expression):
    value: Expression
    start: Expression
    end: Expression

@dataclass
class StructRecast(Expression):
    target_type: TypeSystem
    source: Expression
    consume_source: bool = True  # from buf vs from buf!

@dataclass
class ComptimeBlock(Statement):
    name: Optional[str]
    body: Block

@dataclass
class EmitFlux(Statement):
    body: Block
    terminator: str  # '};' or '}#;'
```

---

# Semantic Analysis

## Type Resolution (`TypeResolver.resolve`)
1. Parse base keyword (`int`, `uint`, `data`, `byte`, custom alias)
2. Read `{width:align:endian}` if present
3. Apply pointer `*`, array `[N]`, `[]` decorators
4. Apply `const`, `volatile`, `heap`, `stack`, `global`, `register`, `singinit`, `noinit`
5. Resolve `as` aliases recursively

## Overload Resolution
1. Filter by **arity** (parameter count)
2. **Exact type match** on all parameters (including endianness, bit-width)
3. **First declared** among count-matching candidates (no ranking)
4. **Coercion** at call site: `void*` universal pointer, array→pointer decay, integer widen/narrow

## Template Instantiation
- Triggered by explicit `<T, U>` or inference from call arguments
- Constraints checked by walking instantiated body for violations
- Mangled name includes concrete type tokens

## Contract Expansion
- Pre-contract: statements inserted at function entry
- Post-contract: statements inserted before each `return`
- Contracts can contain any statement (not just `assert`)

---

# Type Checking

## TypeSystem Fields
```python
@dataclass
class TypeSystem:
    base_type: DataType              # SINT, UINT, DATA, STRUCT, OBJECT, etc.
    bit_width: int = 0               # For DATA: 1-64
    alignment: int = 0               # Alignment in bits
    endianness: int = 1              # 1=big (default), 0=little
    is_signed: bool = True           # For DATA
    is_const: bool = False
    is_volatile: bool = False
    is_pointer: bool = False
    pointer_depth: int = 0
    is_array: bool = False
    array_size: int = 0
    array_dimensions: List[int] = field(default_factory=list)
    array_element_type: Optional[TypeSystem] = None
    custom_typename: str = ""        # For `as` aliases
    storage_class: StorageClass = StorageClass.AUTO
    no_functions: bool = False       # data!{N}
```

## Key Rules
- **Structs are packed** — no implicit padding; use `data{N:M}` for alignment
- **Endianness is part of type** — `be16` vs `le16` are distinct; assignment swaps bytes
- **Bit slices produce unsigned** — Width = `end - start + 1`
- **Array packing** — `(byte[8])u64` packs element 0 to MSB
- **Void cast frees** — `(void)ptr` calls `ffree` (heap) or zeros (stack)

---

# Intermediate Representation

Flux emits **LLVM IR** via `llvmlite`. Key mappings:

| Flux Type | LLVM Type |
|-----------|-----------|
| `int` / `sint` | `i32` or `i64` (config byte width) |
| `uint` | `i32`/`i64` |
| `long` / `slong` | `i64` |
| `ulong` | `i64` |
| `float` | `float` |
| `double` | `double` |
| `byte` / `char` | `i8` |
| `bool` | `i1` |
| `data{N}` | `iN` |
| `T*` | `ptr` (opaque) |
| `T[N]` | `[N x <elem>]` |
| `struct S` | `%S = type { <fields> }` (packed) |
| `object O` | `%O = type { <fields> }` + method functions |

**Function signature:** `(params...) -> ret` with `fastcc` by default.

---

# Optimizer

## Dead Code Elimination (`fdce.py`)
```python
def eliminate(ast, entry="FRTStartup", verbose=False):
    # 1. Build call graph from entry
    # 2. Mark all reachable FunctionDef nodes
    # 3. Remove unmarked from AST (and module globals)
```
- Runs **after parsing, before borrow check & codegen**
- Entrypoint configurable via `--entrypoint` or config `entrypoint`

## LLVM Passes (via `llc`)
```
-O3 -enable-misched -enable-tail-merge -optimize-regalloc
-relocation-model=static -tailcallopt -disable-verify
```
ARM64: adds `-mattr=+neon` etc. via `--mattr`.

---

# Runtime

## Memory Model
- **Stack:** Default; zero-init; frame popped on return
- **Heap:** `heap T x = init;` → `fmalloc`; `(void)x` → `ffree`
- **Defer:** `defer stmt;` pushes to frame-local stack; executed LIFO on exit
- **No GC, no ARC** — Ownership is manual or opt-in via `~`

## FRT (Flux Runtime)
- `FRTStartup(argc, argv)` → calls `main()` → `FRTShutdown()`
- Provides: `fmalloc`, `ffree`, `memcpy`, `memset`, `memcmp`, thread primitives
- Platform-specific: `linux.fx`, `windows.fx`, `doslib.fx`

## Exception Handling
- `throw(expr)` — Any type; caught by matching `catch (Type name)`
- `catch (auto name)` — Catch-all
- Implemented via LLVM `invoke` + landing pads + personality function

---

# Standard Library

## Core Modules (auto-available via `#import <standard.fx>`)
- `standard::io::console` — `print`, `println`, `input`
- `standard::strings` — `len`, `substr`, `split`, `join`, `find`
- `standard::math` — `sin`, `cos`, `sqrt`, `pow`, `abs`, `min`, `max`, `clamp`
- `standard::collections` — `Array`, `HashMap`
- `standard::sorting` — `qsort`, `msort`, `is_sorted`

## Optional Modules (explicit `#import` or `using`)
| Module | Imports |
|--------|---------|
| `vulkan.fx` | `using standard::graphics::vulkan;` |
| `opengl.fx` | `using standard::graphics::opengl;` |
| `tensors.fx` | `using standard::tensors;` |
| `neuralnet.fx` | `using standard::ml::neuralnet;` |
| `cryptography.fx` | `using standard::crypto;` |
| `tls.fx` | `using standard::net::tls;` |
| `fhf.fx` | `using standard::fhf;` (hot-patching) |

---

# Error Reporting

## Format
```
[ERROR] tests/test.fx:12:5: Expected ';' after statement
    int x = 5
    ----^
```

## Components
- **Lexer:** Invalid char, unterminated string, malformed number
- **Parser:** Unexpected token, mismatched braces, invalid syntax
- **Type System:** Type mismatch, unknown type, invalid cast, constraint violation
- **Codegen:** LLVM verification failure, undefined reference, invalid IR
- **Linker:** Missing symbol, duplicate definition, library not found

## Diagnostic Helpers
- `_src_loc_with_source(node, module)` → file:line:col + source line + caret
- `FluxCodegenError` captures node + module for rich context
- Logger component filters: `lexer`, `parser`, `compiler`, `build`, `preprocessor`, `codegen`, `dce`, `fbc`

---

# Diagnostics

## Logging Levels
| Level | Name | Use |
|-------|------|-----|
| 0 | SILENT | Nothing |
| 1 | ERROR | Failures only |
| 2 | WARNING | Warnings + errors |
| 3 | INFO | Progress (default) |
| 4 | DEBUG | Details |
| 5 | TRACE | Everything (IR dumps) |

## CLI Control
```bash
--log-level 4 --log-filter parser,compiler --log-timestamp --log-file build.log
```

## Environment Variables
- `FLUX_LOG_LEVEL`, `FLUX_LOG_FILE`, `FLUX_LOG_TIMESTAMP`, `FLUX_LOG_NO_COLOR`, `FLUX_LOG_COMPONENTS`

---

# CLI

See **Build System > CLI** above for full flag list.

## Entrypoint Override
```bash
python fxc.py test.fx --entrypoint my_main
```
Sets `compiler.entrypoint` used by DCE and codegen.

---

# Configuration

## `config/flux_configuration.cfg`
```ini
[compiler]
target = native          # native | dos | bootloader
optimize = true
debug_symbols = false
llvm_path =              # Optional absolute path to LLVM bin/

[paths]
stdlib = src/stdlib
include =                # Extra import search paths (semicolon-separated)

[logging]
level = 3
color = true
timestamp = false
```

## Environment Override Priority
CLI > Env vars > Config file > Defaults

---

# Examples

## Hello World
```flux
#import <standard.fx>;
using standard::io::console;

def main() -> int {
    println("Hello, Flux!");
    return 0;
}
```

## Bit Manipulation (SHA-256 Finalize)
```flux
hash[0..3]   = (byte[4])(be32)ctx.state[0];
hash[4..7]   = (byte[4])(be32)ctx.state[1];
hash[8..11]  = (byte[4])(be32)ctx.state[2];
hash[12..15] = (byte[4])(be32)ctx.state[3];
hash[16..19] = (byte[4])(be32)ctx.state[4];
hash[20..23] = (byte[4])(be32)ctx.state[5];
hash[24..27] = (byte[4])(be32)ctx.state[6];
hash[28..31] = (byte[4])(be32)ctx.state[7];
```

## Comptime Codegen
```flux
enum State { Idle, Running, Paused, Stopped };

comptime {
    int[] from = [0, 1, 2, 1];
    int[] to   = [1, 2, 1, 3];
    int n = 4;

    emitflux {
        def state_name(int s) -> byte* {
            if (s == 0) return "Idle";
            if (s == 1) return "Running";
            if (s == 2) return "Paused";
            if (s == 3) return "Stopped";
            return "Unknown";
        }
    }

    for (int i = 0; i < n; i++) {
        emitflux {
            def ~$i"can_trans_{}_{}"(from[i]; to[i])() -> bool { return true; }
        }
    }
}
```

## Custom Operator
```flux
operator (int L, int R) [+++] -> int {
    return ++L + ++R;
}
int z = a +++ b;  // Parses as custom infix, fixed precedence
```

## Ownership
```flux
def consume(~int z) -> void {}

def main() -> int {
    ~int x;
    consume(~x);  // Move
    consume(~x);  // ERROR: use after move
    return 0;
}
```

## Template with Constraint
```flux
constraint NoNarrowing(A) {
    A !`< A
}

def serialize<T: int, :{NoNarrowing}>(T x) -> byte {
    return 5 + x;  // ERROR if T wider than byte
}
```

---

# Benchmarks

Located in `examples/` (mandelbrot, fluid_sim, neuralnet, etc.).
Run with:
```bash
python fxc.py examples/mandelbrot.fx -o build/mandelbrot
time build/mandelbrot
```

---

# Testing

## Unit Tests
- `fvm_test.py` — 100+ opcode tests (stack, arithmetic, control flow, memory, structs, arrays, FFI, EMIT_*)

## Integration Tests
- `tests/*.fx` — Each has `main() -> int` returning 0 on success
- Run via script or manually: `python fxc.py tests/feature.fx -o build/feature && build/feature`

## Fuzzing
- Not yet implemented. Candidate: generate random valid `.fx` via grammar, compile+run.

---

# Fuzzing

**Repository does not currently define a fuzzing infrastructure.**

---

# VS Code Extension

Located in `editor-support/vscode/`.
- Syntax highlighting via TextMate grammar (derived from tree-sitter)
- LSP client connecting to `fxc.py --lsp` (if implemented)
- Debug adapter for LLVM DWARF (via `lldb-vscode` / `codelldb`)

---

# Tree-sitter

Grammar: `tree-sitter-flux/grammar.js`
- Generates `tree-sitter-flux.wasm` for GitHub linguist, editors
- Keep in sync with `fparser.py` precedence and keywords
- Run `npm install && npx tree-sitter generate` in `tree-sitter-flux/`

---

# LSP

**Repository does not currently define a Language Server Protocol implementation.**
The `fc.py` has hooks for future LSP (symbol table, diagnostics), but no server exists yet.

---

# Formatting

**No dedicated Flux formatter (`fluxfmt`) exists yet.**
- Use `black` on Python compiler code
- Flux source style per `docs/style_guide.md`:
  - 4-space indent, braces on same line for statements
  - Space after `,` `:` `=` in declarations
  - `def name(params) -> ret {` not `def name ( params ) -> ret {`
  - Semicolon after every statement including blocks

---

# Linting

**No dedicated Flux linter exists yet.**
- Borrow checker (`--borrowcheck`) serves as primary static analysis
- `fbc.py` reports: use-after-move, double-move, leak, alias violation

---

# CI/CD

**Repository does not currently define CI/CD pipelines (`.github/workflows/` missing).**
Recommended workflow:
1. `black --check src/`
2. `mypy src/`
3. `flake8 src/`
4. `python fvm_test.py`
5. `python fxc.py tests/*.fx` (compile + run subset)
6. Publish wheel to PyPI on tag

---

# Git Workflow

- **Main branch:** `main`
- **Feature branches:** `feature/<short-desc>`
- **Commit messages:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`)
- **PR required** for all changes to `main`
- **No force-push** to shared branches

---

# Pull Request Rules

1. All CI checks pass (formatter, typecheck, tests)
2. Borrow checker passes on modified files (`--borrowcheck`)
3. Language changes include spec update (`docs/Specs/language_specification.md`)
4. New keywords/operators added to `flexer.py`, `fparser.py`, `grammar.js`, `keyword_reference.md`
5. New stdlib modules have `#import` example in `examples/`
6. Breaking changes require version bump in `pyproject.toml` + migration note

---

# Commit Message Rules

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `build`
Scope: `lexer`, `parser`, `ast`, `typesys`, `codegen`, `fvm`, `stdlib`, `borrow`, `docs`

Example:
```
feat(codegen): add support for bit-slice assignment

Implements `x[a``b] = value` lowering to masked insert.
Updates fcodegen.py visit_BitSlice and ftypesys.py type checking.

Closes #123
```

---

# Code Review Rules

- **Reviewer runs** `python fxc.py <changed-test>.fx --borrowcheck` locally
- **No `print()` in compiler code** — use `logger.debug/info`
- **AST changes** require visitor updates in both `fcodegen.py` and `fvmcodegen.py`
- **Grammar changes** require `tree-sitter-flux` rebuild + test
- **Type system changes** require constraint/test updates

---

# Naming Conventions

| Entity | Convention | Example |
|--------|------------|---------|
| Python modules | `snake_case` | `fcodegen.py` |
| Python classes | `PascalCase` | `CodegenVisitor` |
| Python functions/vars | `snake_case` | `visit_FunctionDef` |
| Python constants | `UPPER_SNAKE` | `TokenType.PLUS` |
| Flux keywords | `lowercase` | `def`, `struct`, `comptime` |
| Flux types | `PascalCase` or `lowercase` | `MyStruct`, `int`, `data{16}` |
| Flux functions | `snake_case` | `my_function` |
| Flux constants | `UPPER_SNAKE` | `MAX_SIZE` |
| Flux namespaces | `lowercase` | `standard::io::console` |
| Template params | `PascalCase` | `<T, Alloc>` |
| LLVM IR values | `%snake_case` | `%my_var` |

---

# Folder Conventions

| Path | Purpose |
|------|---------|
| `src/compiler/` | Compiler passes (pure Python) |
| `src/stdlib/` | Standard library (`.fx` files) |
| `src/stdlib/runtime/` | Runtime support (allocators, threading) |
| `src/stdlib/builtins/` | Compiler-known intrinsics |
| `tests/` | `.fx` test programs |
| `examples/` | Runnable demo programs |
| `docs/Specs/` | Language specification |
| `docs/Compiler/` | Architecture docs |
| `editor-support/` | Editor plugins |
| `tree-sitter-flux/` | Tree-sitter grammar |
| `config/` | INI configuration |
| `build/` | Build artifacts (gitignored) |
| `.fpm/` | Package manager cache |

---

# File Naming

- Python: `snake_case.py`
- Flux source: `<feature>.fx` (lowercase, underscores)
- Test files: `<feature>_test.fx`
- Docs: `snake_case.md`
- Config: `flux_configuration.cfg`

---

# Memory Management

## Compiler (Python)
- **No manual management** — Python GC
- **Avoid large lists in hot loops** — Pre-allocate or use generators
- **AST nodes** — Short-lived; parsed → codegen → discarded
- **LLVM IR** — `llvmlite` manages via Python refs

## Runtime (Flux)
- **Stack** — Default; zero-init; frame popped on return
- **Heap** — `heap T x = init;` → `fmalloc`; `(void)x` → `ffree`
- **Defer** — `defer stmt;` pushes to frame-local stack; executed LIFO on exit
- **No GC, no ARC** — Ownership is manual or opt-in via `~`

---

# Thread Safety

- **Compiler** — Single-threaded; no concurrent compilation
- **Runtime** — `threading.fx` provides `thread_create`, `mutex`, `condvar`
- **Atomics** — `atomics.fx` maps to LLVM `atomicrmw`/`cmpxchg`
- **Borrow checker** — `check_threads=True` flag validates cross-thread moves

---

# Unsafe Code Rules

Flux has **no `unsafe` keyword**. Instead:
- **Inline asm** — `volatile asm { ... } : : : ;` — Programmer guarantees correctness
- **Raw bytecode** — `def{}* fp()->void = @bytes;` — Direct machine code execution
- **Pointer arithmetic** — `@expr`, `(@)addr`, `ptr + n` — No bounds checking
- **Void cast free** — `(void)ptr` — Can free invalid pointer if misused
- **Comptime FFI** — `compiler.fvm.loadlib`, `compiler.fvm.dump` — Host access at compile time

**Rule:** These features exist for systems programming; document assumptions in comments.

---

# Compiler Performance Rules

1. **No heap allocation in lexer/parser hot paths** — Reuse token objects, pre-allocate lists
2. **Single-pass lexer** — No backtracking
3. **Precedence climbing** — O(n) expression parsing
4. **Symbol table** — Dict lookups; avoid linear scans
5. **DCE before codegen** — Reduces IR size
6. **Lazy template instantiation** — Only instantiate used specializations
7. **Comptime caching** — FVM reuses `_comptime_functions`, `_comptime_locals` across blocks

---

# Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Forgetting `;` after block | `Expected ';' after statement` | All statements end with `;` including `};` |
| Shadowing in `comptime` | Variables not visible across blocks | Use `compiler.io.console.print` to debug; declare at top |
| `emitflux` terminator confusion | `}` ends block early | Use `}#;` to close inner brace, stay in emitflux |
| Template constraint violation | `Type relation T !`< T violated` | Check `return 5 + x` narrowing; widen return type |
| Borrow checker false positive | `use after move` on valid code | Ensure `~` only on tied vars; check `fbc_test.fx` patterns |
| Endianness mismatch | Network bytes swapped | Use `data{16::0}` for LE, default `data{16}` for BE |
| Array pack width mismatch | `element_count * bit_width == target` error | Pad array or use `data{N}` target |
| Missing `#import <standard.fx>` | `unknown identifier 'println'` | Always import stdlib first |

---

# Anti-patterns

1. **Using `heap` everywhere** — Defeats stack allocation; use only for dynamic lifetime
2. **C-style manual bit twiddling** — Use `data{N}` types and bit slices instead
3. **Deeply nested `if`/`else`** — Use `switch` or early `return`
4. **Ignoring contracts** — They're free runtime checks; use them
5. **Overloading built-in operators for primitives** — Rejected by compiler (Rule 1)
6. **Large stack arrays in loops** — Stack overflow; use `heap` or static

---

# Preferred Patterns

1. **Zero-copy parsing** — `Packet p from buf;` instead of field-by-field copy
2. **Bit-slice for protocols** — `flags[0``3] = 0b101;` instead of shifts/masks
3. **Comptime table generation** — `emitflux` in loop → optimal dispatch
4. **Contracts for invariants** — `: NonNull(ptr)` at function boundary
5. **Opt-in ownership** — `~T` only where move semantics matter
6. **Template constraints for geometry** — `{T !`< T}` prevents accidental truncation
7. **`defer` for cleanup** — RAII without destructors

---

# Flux Language Guide

## Variables & Constants
```flux
int x = 42;              // Stack, zero-init if no init
const int C = 10;        // Compile-time constant
singinit int y;          // Initialized once across calls
noinit int z;            // Uninitialized (dangerous)
heap int* p = 5;         // Heap allocation
~int owned;              // Tied (ownership-tracked)
```

## Functions
```flux
// Prototype
def add(int, int) -> int;

// Definition
def add(int a, int b) -> int {
    return a + b;
}

// Overload
def add(float a, float b) -> float { return a + b; }

// Variadic
def log(...) -> void {
    print(...[0]); print(...[1]);
}

// Chaining
int z = foo() <- bar();  // z = foo(bar())

// Recursion (tail-call optimized)
def fact(int n) <~ int {
    return n <= 1 ? 1 : n * fact(n - 1);
}

// Escape from strict recursion
def loop() <~ void {
    if (done) escape main();
}
```

## Closures / Lambdas
```flux
(int x, int y) <:- x + y;  // Expression lambda
```

## Modules & Imports
```flux
#import <standard.fx>;           // Stdlib
#import "local.fx";              // Relative file
#package mylib, otherlib;        // FPM packages

namespace mylib {
    def foo() -> void {}
}

using mylib;                     // Opens namespace
mylib::foo();                    // Qualified
```

## Structs
```flux
struct Packet {
    data{16}  type;
    data{32}  length;
    data{32}  timestamp;
    data{32}  checksum;
}

// Composition (flattened)
struct BMP : Header, InfoHeader { ... } : ExtraData;

// Zero-copy recast
Packet pkt from buffer;
```

## Enums
```flux
enum Color { Red, Green, Blue };
Color c = Color.Red;
```

## Unions / Tagged Unions
```flux
union Value { int i; float f; };
Value v { i = 42 };

enum Tag { INT, FLOAT };
union Tagged { int i; float f; } Tag;
Tagged t { f = 3.14; _ = Tag.FLOAT };
```

## Objects
```flux
object Counter {
    int value;
    
    def __init(int v) -> this { this.value = v; return this; }
    def __exit() -> void { print("drop"); }
    def __expr() -> int { return this.value; }
    
    def inc() -> void { this.value++; }
}

Counter c = 5;        // Sugar for Counter c(5);
c.inc();
defer c.__exit();     // RAII
```

## Traits
```flux
trait Drawable {
    def draw() -> void;
}

Drawable object Sprite {
    def draw() -> void { ... }
    // Must implement draw
}
```

## Interfaces
```flux
trait Queryable { def query(byte*) -> byte*; }
trait Connectable { def connect() -> bool; }

interface Database(Client: Connectable, Server: Queryable) {
    Client : Server { connect() -> bool, disconnect() -> void };
    Server(Client) { query(byte*) -> byte* };
    Client -> Server { result() -> byte* };
}

object Client : Database(this, Server) { ... }
object Server : Database(Client, this) { ... }
```

## Generics / Templates
```flux
def identity<T>(T x) -> T { return x; }
def foo<T, U>(T a, U b) -> U { return a.a * b; }  // Inference

struct Pair<T, U> { T first; U second; }

constraint NoNarrowing(T) { T !`< T; }
def safe<T: int, :{NoNarrowing}>(T x) -> byte { return x; }  // Error if T > byte
```

## Contracts
```flux
contract NonZero(a, b) {
    assert(a != 0, "a zero");
    assert(b != 0, "b zero");
}

def div(int a, int b) -> int : NonZero(a, b) {
    return a / b;
} : PostDiv;  // Post-contract

operator (int, BigInt)[+] -> BigInt : NonZero;
```

## Macros
```flux
#psub log(x) println("LOG: ", x); #

#def DEBUG 1;
#ifdef DEBUG
    log("debug");
#endif
```

## Comptime & Emitflux
```flux
comptime {
    int x = 42;
    emitflux { def get_x() -> int { return ~$i"{x}"; } }
    compiler.io.console.print("Comptime x: "); compiler.io.console.print(int(x));
}
```

## Inline Assembly
```flux
#ifdef __ARCH_X86_64__
volatile asm {
    movq $0, %rsi
    movq $2, %rdi
    movq $1, %rax
    xchgq %rax, (%rsi)
    movq %rax, (%rdi)
} : : "r"(ptr), "r"(val), "r"(out) : "rax", "rsi", "rdi", "memory";
#endif
```

## Pointers & Memory
```flux
int x = 10;
int* p = @x;           // Address of
*p = 20;               // Deref
heap int* h = 42;      // Heap alloc
(void)h;               // Free
int* q @= "hello";     // Anonymous allocation + assign
```

## Operators
See `docs/operator_reference.md` for complete table. Key differences from C:
- `^` = power (same precedence as `*`)
- `` `& ``, `` `| ``, `` `^^ `` = bitwise AND/OR/XOR (bind tighter than `==`)
- `^^` = logical XOR (with `and`/`or`)
- `!&` = NAND, `!|` = NOR
- `in` / `!in` / `not in` = membership test
- `??` = null coalesce
- `?=` = assign if zero/false
- `~` = tie (ownership move)
- `~$` = codify (splice comptime var into emitflux)
- `$` = stringify (identifier → string)
- `#"` = ditto (repeat last initializer)
- `<~` = strict recursion arrow

## Control Flow
```flux
if (cond) { ... } elif (cond) { ... } else { ... };
if (cond) expr else expr;              // Ternary expression
cond ? expr1 : expr2;                   // Classic ternary

for (int i = 0; i < 10; i++) { ... }
for (x in arr) { ... }
for (;;) { ... }                       // Infinite

while (cond) { ... }
do { ... } while (cond);

switch (val) {
    case (0) { ... }
    case (1) { ... }
    default { ... }
};
```

## Error Handling
```flux
try {
    risky();
} catch (MyError e) {
    handle(e);
} catch (string msg) {
    print(msg);
} catch (auto x) {
    print("unknown");
};
```

## Built-ins
```flux
typeof(expr)    // Type as string
sizeof(expr)    // Size in bits
alignof(expr)   // Alignment in bits
endianof(expr)  // 1=big, 0=little
assert(cond, "msg")
```

---

# AI Agent Rules (150+ Rules)

## General
1. **Never guess APIs** — Read the source file first (`read_file`).
2. **Never invent language features** — If not in `language_specification.md` or `fast.py`, it doesn't exist.
3. **Never modify `build/`** — It's gitignored; generated artifacts only.
4. **Run tests after changes** — `python fvm_test.py` + relevant `tests/*.fx`.
5. **Use `patch`/`write_file`** — Don't print code blocks; apply edits.
6. **Match existing style** — `black`, `mypy`, naming conventions.
7. **Update docs with code** — Spec, keyword ref, operator ref, tutorials.
8. **Preserve deterministic diagnostics** — Same input → same error message.
9. **Keep compiler passes pure** — No hidden global state; pass context explicitly.
10. **Batch independent tool calls** — Parallel `read_file`, `search_files`, `terminal`.

## Lexer
11. **Add tokens to all tables** — `single_char_tokens`, `double_char_tokens`, `triple_char_tokens`, `quadruple_binary_tokens`, `quintuple_binary_tokens`, `sextuple_binary_tokens`, `keywords`, `_TOKEN_TYPE_TO_STR`.
12. **Longest-match ordering** — New multi-char tokens must be in correct length bucket.
13. **Update tree-sitter grammar** — `grammar.js` must recognize new tokens.
14. **Test lexer in isolation** — `python flexer.py test.fx -v`.

## Parser
15. **Precedence climbing** — New binary operators go in correct precedence tier.
16. **Add AST node in `fast.py`** — Before parsing it.
17. **Update `conflicts` in grammar.js** — For ambiguities.
18. **Set `source_line`/`source_col`** — Call `node.set_location(line, col)` in parser.
19. **Handle template `<...>` vs `<` ambiguity** — Context-aware in `parse_expression`.
20. **Test parser** — `python fparser.py test.fx -a`.

## AST
21. **Inherit from `ASTNode`** — Get `accept()`, `set_location()`.
22. **Use `field(default_factory=list)`** for mutable defaults.
23. **Add `visit_<Node>` to both codegens** — `fcodegen.py` and `fvmcodegen.py`.
24. **Don't put logic in AST nodes** — Visitors own behavior.

## Type System
25. **Extend `TypeSystem` dataclass** — New fields for new type features.
26. **Update `TypeResolver.resolve()`** — Parse new syntax.
27. **Update mangling in `SymbolTable.mangle_function_name()`** — Include new discriminators.
28. **Add constraint operators to `ftypesys.py`** — If new type relations.
29. **Test with `typeof()`/`sizeof()`/`alignof()`/`endianof()`**.

## Semantic Analysis
30. **Symbol table scopes** — `enter_scope()`/`exit_scope()` around blocks.
31. **Namespace tracking** — `current_namespace`, `using_namespaces`.
32. **Overload registry** — Register after full `FunctionDef` parsed.
33. **Trait/interface registry** — Populate in pre-pass before object bodies.
34. **Template instantiation** — Lazy; cache by mangled name.

## Codegen (LLVM)
35. **Use `CodegenVisitor.visit_<Node>` pattern** — Don't add `codegen()` to AST.
36. **Lower types via `type_spec_to_llvm_type()`** — Centralized mapping.
37. **Emit debug loc** — `builder.debug_metadata = ...` from node location.
38. **Handle `defer`** — Push to `builder._flux_defer_stack`.
39. **Contracts** — Pre at entry, post before each `ret`.
40. **Verify module** — `module.verify()` before writing `.ll`.

## Codegen (FVM)
41. **Mirror LLVM visitor structure** — Same node coverage.
42. **Emit `Instr(Op, operands)`** — Use `_instr()` helper.
43. **Manage locals** — `_alloc_local(name)` → slot index.
44. **Loop patches** — `_break_stack`, `_continue_stack`.
45. **Struct layouts** — Build `_struct_layouts` from `StructDef` members in comptime.

## Borrow Checker
46. **Run after DCE** — `fc.py` order: parse → DCE → borrow → codegen.
47. **Tied vars only** — `~Type` parameters/variables.
48. **Move on `~var`** — Invalidate source, bind to dest.
49. **Leak check** — Tied vars must be moved or go out of scope.
50. **Thread check** — `check_threads=True` validates cross-thread moves.

## Runtime
51. **Stack allocation default** — `alloca` in entry block.
52. **Heap via `fmalloc`/`ffree`** — Never `malloc`/`free` directly.
53. **Zero-init all stack vars** — Unless `noinit`.
54. **Defer executes LIFO** — Before `ret`, after post-contracts.

## Stdlib
55. **Place in `src/stdlib/`** — `.fx` files only.
56. **Use `#import <standard.fx>`** for prelude.
57. **Export via `using standard::module::sub;`** at bottom of module.
58. **Platform-specific** — `net_linux.fx`, `net_windows.fx`, `linux.fx`, `windows.fx`.

## Testing
59. **Each test: `main() -> int` returning 0** — Non-zero = failure.
60. **Use `assert(cond, "msg")`** — Throws caught by test harness.
61. **Test borrow checker** — `--borrowcheck` flag on ownership tests.
62. **Test comptime** — `comptime { ... }` blocks with `emitflux`.
63. **Test FVM opcodes** — Add to `fvm_test.py`.

## CLI
64. **Add flags to `fxc.py` argument parser** — Follow existing pattern.
65. **Plumb through to `FluxCompiler`** — `__init__` params or setters.
66. **Document in `--help`** — User-facing consistency.

## Config
67. **Add to `config/flux_configuration.cfg`** — INI format.
68. **Read via `fconfig.py`** — `config.get('key', default)`.
69. **Env override** — `FLUX_<SECTION>_<KEY>`.

## Logging
70. **Use `logger.debug/info/warn/error`** — Not `print`.
71. **Component tag** — `lexer`, `parser`, `compiler`, `build`, `preprocessor`, `codegen`, `dce`, `fbc`.
72. **Rich errors** — `FluxCodegenError(node, module)` for source snippets.

## CI/Quality
73. **`black --check src/`** — Format compliance.
74. **`mypy src/`** — Type safety.
75. **`flake8 src/`** — Lint.
76. **No new `print()` in compiler** — Except CLI output in `fxc.py`.
77. **No `Any` without justification** — Use `Union`/`Optional`.

## Git/PR
78. **Branch per feature** — `feature/<short>`.
79. **Conventional commits** — `feat(scope): msg`.
80. **PR description** — What, why, test plan.
81. **No force-push** — Rebase instead.
82. **Update `pyproject.toml` version** on release.

## Language Design
83. **No breaking changes without migration** — Version bump + guide.
84. **Keywords are permanent** — Don't rename `def` → `fn`.
85. **Operators fixed precedence** — Custom infix always between additive/multiplicative.
86. **Structs always packed** — No hidden padding.
87. **Endianness in type** — Not runtime flag.
88. **Bit 0 = MSB** — Consistent bit numbering.
89. **Comptime = runtime semantics** — Same types, same behavior.
90. **Emitflux order = declaration order** — Pass 4 finalizes.

## Performance
91. **Avoid allocations in lexer/parser loops** — Reuse lists.
92. **Dict for symbol lookup** — Not linear scan.
93. **DCE before codegen** — Smaller IR.
94. **Lazy template instantiation** — Only instantiate used specializations.
95. **Comptime caching** — FVM reuses `_comptime_functions`, `_comptime_locals` across blocks.

## General Compiler Development
96. **Always check `fast.py` first** when adding a new language construct — the AST node must exist before parser and codegen.
97. **Both codegen visitors must be updated** — `fcodegen.py` for LLVM and `fvmcodegen.py` for FVM bytecode; never update only one.
98. **Use `FluxCodegenError` for all codegen failures** — it captures the AST node and module for proper source location rendering.
99. **Run `module.verify()` after IR generation** — catches invalid IR before writing `.ll`.
100. **When modifying the preprocessor, update `fpreprocess.py` AND the lexer** — new directives need token types.
101. **The `SymbolTable` is the single source of truth for name resolution** — don't create parallel lookup structures.
102. **Type aliases via `as` are resolved recursively** — handle cycles in `TypeResolver`.
103. **Constraint checking happens at template instantiation time** — not at template definition.
104. **`emitflux` fragments are order-sensitive** — they are finalized in Pass 4 in declaration order.
105. **Named comptime blocks are `goto` targets** — only valid from other comptime blocks.
106. **The borrow checker operates on the AST after DCE** — it sees the pruned call graph.
107. **Stack frames are fixed at function entry** — all `alloca` in the entry block.
108. **`defer` statements are collected per-function** — not global; they run on every return path.
109. **Contracts are inlined, not called** — pre-contract at entry, post-contract before each `ret`.
110. **Bit-slice indices are compile-time constants for assignment** — runtime indices only allowed for reading.
111. **Array packing is always big-endian at the array level** — element 0 goes to MSB regardless of element endianness.
112. **`void` cast is a free operation** — it calls `ffree` for heap, zeroes stack variables.
113. **`singinit` variables retain value across calls** — they are not re-zeroed on each function entry.
114. **`noinit` suppresses zero-initialization** — use only when you immediately overwrite.
115. **The `FVM` is a stack machine** — `PUSH`/`POP`/`LOCAL_GET`/`LOCAL_SET` are the primary operations.
116. **FVM functions have their own local slots** — slot 0 is `this` for methods.
117. **Struct layouts in FVM are computed from `StructDef` members** — field offsets match LLVM layout exactly.
118. **Interface whitelists are built during object definition** — they constrain method calls at compile time.
119. **The `compiler.` namespace is available only in `comptime` blocks** — it provides I/O, file, FPM, FVM introspection.
120. **Ditto operator (`#"`) in variable declarations repeats the last initializer** — each `#"` is an independent evaluation.
121. **Ditto in function calls repeats the argument at the same position from the previous call** — previous call must be same function with same arity.
122. **Standalone `#";` repeats the previous statement** — not the previous expression.
123. **`}#;` exits emitflux but stays in comptime** — allows interleaving comptime logic with emitted code.
124. **`#};` closes a brace inside emitflux without ending the emitflux block** — for nested braces in generated code.
125. **Template parameter defaults use `+` prefix** — `T: +int` means default to `int`; `!+` means no default.
126. **Contract syntax: `: Name` for pre, `} : Name` for post** — multiple contracts compose in declaration order.
127. **Operator overloading requires at least one non-builtin parameter** — prevents hijacking primitive arithmetic.
128. **Custom infix operators bind at fixed precedence (between `+` and `*`)** — parenthesize if different binding needed.
129. **`from` recast consumes source by default** — use `from buf!` to keep source alive.
130. **Bit-slice assignment `x[a``b] = val` requires `a`, `b` compile-time constant** — target must be a plain variable.
131. **Struct composition (`:` and `: ... :`) flattens members in declaration order** — no vtables, no padding.
132. **Object inheritance excludes `__init`, `__exit`, `__expr`** — child must define its own.
133. **Trait satisfaction is checked at object definition** — all prototype methods must have bodies.
134. **Interface attachment requires matching trait for each role** — checked at compile time.
135. **Preprocessor macros (`#def`) are text substitution only** — no parameters; use `#psub` for parameterized.
136. **`#psub` macros expand at preprocess time** — they see preprocessed source, not original.
137. **`#ifdef`/`#ifndef` control inclusion at preprocess level** — dead code removed before lexing.
138. **`#dir` adds import search paths** — affects `#import` resolution order.
139. **`#warn`/`#stop` emit diagnostics during preprocessing** — `#stop` halts compilation.
140. **LLVM target triple/data layout set in `FluxCompiler.__init__`** — platform detection is there.
141. **DCE entrypoint defaults to `FRTStartup`** — override with `--entrypoint` or config.
142. **Borrow checker runs after DCE, before codegen** — sees final call graph.
143. **Borrow checker violations: use-after-move, double-move, leak, alias** — reported with source locations.
144. **`--borrowcheck-warn` downgrades violations to warnings** — does not block compilation.
145. **Shadow stack in `shadowstack.fx` tracks heap allocations for borrow checker** — enables cross-function analysis.
146. **Inline asm uses AT&T syntax with GCC-style constraints** — `volatile` prevents optimization.
147. **Raw bytecode functions: `def{}* fp()->void = @bytes;`** — bytes are embedded directly in binary.
148. **Function pointers: `def{}* name(args)->ret = @func;`** — auto-dereferences on call.
150. **Variadic functions use `...` in params, `...[N]` to access args** — zero-indexed.
151. **Chaining arrow `<-` rewrites `foo() <- bar()` to `foo(bar())`** — syntactic sugar only.
152. **Recurse arrow `<~` emits `musttail` call** — guarantees zero stack growth.
153. **`escape` only valid inside `<~` function** — jumps to any callable, unwinds tail recursion.
154. **`noinit` on variables suppresses zero-init** — dangerous, use deliberately.
155. **`singinit` variables initialized once** — subsequent calls to same function see retained value.
156. **`data!{N}` creates non-functional type aliases** — cannot have type functions defined on them.
157. **`sizeof`/`alignof`/`typeof`/`endianof` work on types or expressions** — evaluated at compile time.
158. **`void` as literal equals `0`/`false`** — `void == false` is true.
159. **Arrays: `type[n] name` syntax** — not `type name[n]`.
160. **Array comprehensions: `[expr for (type var in iter)]`** — with optional `if` filter.
161. **C-style for: `for (int i = 0; i < n; i++)`** — init/cond/update separated by `;`.
162. **`for (x in y)` iterates arrays/pointers** — `in` also works as membership test in expressions.
163. **`switch` is static, value-based, no fallthrough** — `default` required.
164. **`try`/`catch`/`throw` catch by type** — `catch (auto x)` catches all.
165. **`assert(cond, msg)` throws if inside try, else writes stderr** — compile-time known false is error.
166. **`heap` keyword allocates via `fmalloc`** — `(void)ptr` frees via `ffree`.
167. **`defer expr;` or `defer { ... };` executes LIFO before function return** — after post-contracts.
168. **`using` opens namespace, `!using`/`not using` removes from search** — lexical scope.
169. **`deprecate namespace::name;` errors on any reference** — for API migration.
170. **`$identifier` stringifies to `"identifier"`** — compile-time.
171. **`~$string` codifies: splices string content as Flux code** — only in `emitflux`/`comptime`.
172. **`operator (L, R)[sym] -> Ret` defines custom infix** — `sym` can be identifier or punctuation sequence.
173. **Operator overloads of built-in symbols match exact operand types** — no coercion for overloads.
174. **Template constraints use `:{}` set syntax** — `T: int, :{T ~= U}`.
175. **Relational constraint operators: `~=`, `!~=`, `!@`, `` !`< ``, `` !`<= ``, `` !`> ``, `` !`>= ``** — pairwise, independent, or between.
176. **`constraint Name(P) { ... }` creates named constraint set** — reusable in `:{} `.
177. **Constraint merging: `constraint C = A + B;`** — parameter names remapped.
178. **Type geometry: bit-width, alignment, endianness are type properties** — not runtime values.
179. **Unusual bit widths (3-bit, 13-bit, etc.) fully supported** — stored in `data{N}` or `data{N:M}`.
178. **Bit slices cross struct field boundaries** — because structs are packed.
179. **Array packing into integer: element 0 = MSB** — convention for network serialization.
180. **Endian types (`be16`, `le32`) swap bytes on assignment** — compiler handles conversion.
181. **`cdecl`, `stdcall`, `fastcall`, `thiscall`, `vectorcall` calling conventions** — on function def and function pointer.
182. **`extern` blocks declare FFI functions** — `!!` prevents name mangling.
179. **Function pointer calling convention encoded in type** — `stdcall{}* fn()->int`.
180. **Exported functions visible to dynamic linker** — use `export` block.
181. **Static libraries via `--library` flag** — produces `.a` or `.lib`.
182. **DOS target: 16-bit real mode** — COM (flat binary) or EXE (MZ header).
183. **Bootloader target: 512-byte sector** — with 0x55 0xAA signature.
184. **Tree-sitter grammar in `tree-sitter-flux/grammar.js`** — must stay in sync with parser.
185. **VS Code extension in `editor-support/vscode/`** — TextMate grammar from tree-sitter.
186. **FPM package manager in `fpm.py`** — registry at `.fpm/packages/`.
187. **Examples in `examples/` are integration tests** — compile and run to verify.
188. **C coreutils in `tests/coreutils/`** — for FFI interop testing.
189. **LLVM C headers in `tests/llvm-c/`** — for FFI bindings.
190. **Never assume a feature exists without checking `language_specification.md`** — it is the source of truth.
