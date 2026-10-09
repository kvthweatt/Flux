#!/usr/bin/env python3
"""
Flux Abstract Syntax Tree

Copyright (C) 2026 Karac Thweatt

Contributors:

    Piotr Bednarski
"""

from dataclasses import dataclass, field
from typing import List, Any, Optional, Union, Dict, Tuple, ClassVar
from enum import Enum
from pathlib import Path
import os, sys

from ftypesys import *


class ComptimeError(Exception):
    def __init__(self, msg):
        super().__init__(msg)
        

# Base classes first
@dataclass
class ASTNode:
    """Base class for all AST nodes"""
    source_line: int = field(default=0, init=False, repr=False, compare=False)
    source_col:  int = field(default=0, init=False, repr=False, compare=False)

    def set_location(self, line: int, col: int) -> 'ASTNode':
        """Stamp source location onto this node. Returns self for chaining."""
        self.source_line = line
        self.source_col  = col
        return self

    def accept(self, visitor, builder, module) -> Any:
        """Dispatch this node through a CodegenVisitor."""
        return visitor.visit(self, builder, module)

    def codegen(self, builder, module) -> Any:
        # Once a node's codegen is removed during migration, this base
        # implementation routes it through the module-level visitor singleton.
        # Nodes that still have their own codegen() override this and never
        # reach here, so there is no behaviour change during the transition.
        from fcodegen import visitor as _visitor
        return _visitor.visit(self, builder, module)

# Literal values (no dependencies)
@dataclass
class Literal(ASTNode):
    value: Any
    type: DataType

    def __repr__(self) -> str:
        return str(self.value)



# Expressions (built up from simple to complex)
@dataclass
class Expression(ASTNode):
    pass

@dataclass
class Identifier(Expression):
    name: str

    def __repr__(self) -> str:
        return self.name

@dataclass
class ArrayLiteral(Expression):
    """
    Centralized class for all array literal operations.
    
    Handles:
    - String literals (char arrays)
    - Array literals like [1, 2, 3]
    - Array concatenation
    - Array slicing
    - Memory operations (memcpy, memset)
    - Array information and type checking
    - Compile-time vs runtime array creation
    """
    elements: List[Expression] = field(default_factory=list)
    element_type: Optional[TypeSystem] = None
    is_string: bool = False
    string_value: Optional[str] = None
    storage_class: Optional[StorageClass] = None
    
    # Class-level counter for unique names
    _string_counter: ClassVar[int] = 0
    
    def __post_init__(self):
        """Initialize array literal properties."""
        # Handle string literal conversion
        if not self.is_string and self.elements:
            # Check if all elements are char literals
            all_chars = all(
                isinstance(elem, Literal) and elem.type == DataType.CHAR 
                for elem in self.elements
            )
            if all_chars:
                self.is_string = True
                # Build string from char literals
                chars = []
                for elem in self.elements:
                    if isinstance(elem.value, str):
                        chars.append(elem.value)
                    else:
                        chars.append(chr(elem.value))
                self.string_value = ''.join(chars)
    
    @staticmethod
    def from_string(string_value: str, storage_class: Optional[StorageClass] = None) -> 'ArrayLiteral':
        """
        Create an ArrayLiteral from a string value.
        
        This is a convenience factory method for creating array literals from strings.
        The actual code generation happens in the codegen() method.
        
        Args:
            string_value: The string content
            storage_class: Optional storage class (GLOBAL, STACK, etc.)
            
        Returns:
            ArrayLiteral configured as a string
        """
        # Convert string to list of char literals
        elements = []
        for char in string_value:
            elements.append(Literal(char, DataType.CHAR))
        
        return ArrayLiteral(
            elements=elements,
            is_string=True,
            string_value=string_value,
            storage_class=storage_class
        )
    
    def create_global_string(self, module, string_val: str, name_hint: str = ""):
        """Create a global string constant. Delegates to fcodegen."""
        from fcodegen import _create_global_string as _cgs
        return _cgs(module, string_val, name_hint, ArrayLiteral)
    


@dataclass
class StringLiteral(Expression):
    """
    Represents a string literal.
    
    Unlike CHAR literals (single characters stored as i8),
    string literals are arrays of i8.
    """
    value: str
    storage_class: Optional[StorageClass] = None

    def __repr__(self) -> str:
        return f"\"{self.value.replace(chr(10),'\\n').replace(chr(0),'\\0')}\""
    


_BUILTIN_OP_SYMBOL_MANGLE = {
    '%': 'pct',  '+': 'plus', '-': 'minus', '*': 'mul',
    '/': 'div',  '<': 'lt',   '>': 'gt',    '=': 'eq',
    '&': 'amp',  '|': 'pipe', '^|': 'xor',  '!': 'not',
    '?': 'qst',  '@': 'at',   '~': 'tilde', '^': 'exp',
}

def _mangle_builtin_op(symbol: str) -> str:
    """Reproduce the parser's _mangle_op_symbol logic for built-in operator names."""
    # This mirrors parser._symbol_to_parts (greedy longest-first) then _mangle_op_symbol.
    multi = sorted(['^|!&', '^|!|', '^|!', '^|', '!&', '!|', '<=', '>=', '==', '!=',
                    '++', '--', '<<', '>>', '`!&', '`!|', '`^|'],
                   key=len, reverse=True)
    parts = []
    i = 0
    while i < len(symbol):
        matched = False
        for m in multi:
            if symbol[i:i+len(m)] == m:
                parts.append(m)
                i += len(m)
                matched = True
                break
        if not matched:
            parts.append(symbol[i])
            i += 1
    # Mangle each part: char-by-char with underscore joining, then join parts with underscore
    mangled_parts = []
    for part in parts:
        mangled_parts.append('_'.join(_BUILTIN_OP_SYMBOL_MANGLE.get(c, hex(ord(c))) for c in part))
    return '_'.join(mangled_parts)

@dataclass
class BinaryOp(Expression):
    left: Expression
    operator: Operator
    right: Expression

    def __repr__(self):
        return f"{self.left} {self.operator} {self.right}"



@dataclass
class InExpression(Expression):
    """
    Represents the 'x in y', 'x !in y', and 'x not in y' membership-test expressions.
    Produces a boolean: true if needle is found inside haystack (negated=False),
    or false if found (negated=True).
    """
    needle: Expression
    haystack: Expression
    negated: bool = False

    def __repr__(self) -> str:
        op = "!in" if self.negated else "in"
        return f"({self.needle} {op} {self.haystack})"


@dataclass
class HasExpression(Expression):
    """
    Represents the 'expr has TraitName' trait-membership expression.
    Produces a boolean i1: true if the static type of 'subject' has the
    named trait in its traits list, false otherwise.
    The trait_name is always a plain identifier string resolved at compile time.
    """
    subject: Expression
    trait_name: str  # bare trait name, e.g. "Serializable"

    def __repr__(self) -> str:
        return f"({self.subject} has {self.trait_name})"


@dataclass
class UnaryOp(Expression):
    operator: Operator
    operand: Expression
    is_postfix: bool = False

    def __repr__(self) -> str:
        return f"{self.operator}{self.operand}" if self.is_postfix is False else f"{self.operand}{self.operator}"



@dataclass
class CastExpression(Expression):
    target_type: TypeSystem
    expression: Expression

    def __repr__(self) -> str:
        return f"({self.target_type.custom_typename if self.target_type.custom_typename else self.target_type.base_type}){self.expression}"



@dataclass
class TypeConvertExpression(Expression):
    """
    Represents a built-in type conversion expression: float(x), int(y), etc.
    This is a value-convert (not a bitcast) - e.g. float(intval) emits sitofp.
    Delegates codegen to CastExpression since the conversion semantics are identical.
    """
    target_type: TypeSystem
    expression: Expression

    def __repr__(self) -> str:
        name = self.target_type.custom_typename if self.target_type.custom_typename else self.target_type.base_type.value
        return f"{name}({self.expression})"




@dataclass
class RangeExpression(Expression):
    start: Expression
    end: Expression
    step: Optional[Expression] = None  # For future extension: start..end..step



@dataclass
class ArrayComprehension(Expression):
    expression: Expression  # The expression to evaluate for each element
    variable: str  # Loop variable name
    variable_type: Optional[TypeSystem]  # Type of loop variable
    iterable: Expression  # What to iterate over (e.g., range expression or ArrayLiteral)
    condition: Optional[Expression] = None  # Optional filter condition



@dataclass
class FStringLiteral(Expression):
    """Represents an f-string - evaluated at compile time when possible"""
    parts: List[Union[str, Expression]]
    


@dataclass
class FunctionCall(Expression):
    name: str
    arguments: List[Expression] = field(default_factory=list)
    
    # Class-level counter for globally unique string literals
    _string_counter = 0

    def __repr__(self) -> str:
        s = ", ".join([str(x) for x in self.arguments])
        return f"{self.name}({s})"




@dataclass
class MemberAccess(Expression):
    object: Expression
    member: str

    def __repr__(self) -> str:
        obj_repr = self.object.name if isinstance(self.object, Identifier) else repr(self.object)
        return f"{obj_repr}.{self.member}"

    def _get_member_ptr(self, builder, module):
        """Return the GEP pointer to the member without loading it. Used by ++ and --."""
        from fcodegen import _member_access_get_ptr as _mgp
        return _mgp(self, builder, module)


@dataclass
class MethodCall(Expression):
    object: Expression
    method_name: str
    arguments: List[Expression] = field(default_factory=list)

    def __repr__(self) -> str:
        s = ', '.join([str(x) for x in self.arguments])
        return f"{self.object}.{self.method_name}({s})"


def _emit_va_arg(builder, va_list_i8ptr, arg_type, name: str = ''):
    """Emit a va_arg instruction. Delegates to fcodegen."""
    from fcodegen import _emit_va_arg as _eva
    return _eva(builder, va_list_i8ptr, arg_type, name)


@dataclass
class VariadicAccess(Expression):
    """Represents ...[N] - access the Nth variadic argument."""
    index: Expression

    def __repr__(self) -> str:
        return f"...[{self.index}]"



@dataclass
class ArrayAccess(Expression):
    array: Expression
    index: Expression

    def __repr__(self) -> str:
        return f"{self.array}[{self.index}]"
    


@dataclass
class ArraySlice(Expression):
    """Slice expression using Flux syntax: base[start:end]

    NOTE: In Flux, `x..y` is a Range. This node is specifically for `[start:end]`.
    For now, codegen materializes a fixed-size array value (copy) when the slice
    length can be proven to be a compile-time constant from the AST.

    This matches existing call semantics where functions may take `T[N]` by value.
    """

    array: Expression
    start: Expression
    end: Expression

    def _try_const_len(self) -> Optional[int]:
        """Best-effort compile-time slice length inference.

        Supports common patterns like:
          - a:b where both are integer literals
          - i:i+K or i:(i+K)
          - i+K:i  (NOT supported; slice must be forward)
        """
        # Literal case
        if isinstance(self.start, Literal) and isinstance(self.end, Literal):
            if isinstance(self.start.value, int) and isinstance(self.end.value, int):
                return self.end.value - self.start.value + 1

        # i : i + K  or  i : K + i
        if isinstance(self.end, BinaryOp) and self.end.operator == Operator.ADD:
            lhs, rhs = self.end.left, self.end.right
            # start matches lhs
            if repr(lhs) == repr(self.start) and isinstance(rhs, Literal) and isinstance(rhs.value, int):
                return rhs.value + 1
            # start matches rhs
            if repr(rhs) == repr(self.start) and isinstance(lhs, Literal) and isinstance(lhs.value, int):
                return lhs.value + 1

        # 0 : K
        if isinstance(self.start, Literal) and isinstance(self.start.value, int) and self.start.value == 0:
            if isinstance(self.end, Literal) and isinstance(self.end.value, int):
                return self.end.value + 1

        return None


@dataclass
class BitSlice(Expression):
    """Bit-slice expression: value[start``end]
    
    Extracts bits [start, end] (inclusive) from an integer value.
    Returns an unsigned integer of width (end - start + 1).
    Equivalent to: (value >> start) & ((1 << (end - start + 1)) - 1)
    """
    value: Expression
    start: Expression
    end: Expression



@dataclass
class BitIndexAccess(Expression):
    """Single-bit index expression: value[`index]

    Reads one bit from an integer value using MSB-first addressing
    (bit 0 = MSB, bit N-1 = LSB for an N-bit integer).
    Returns 0 or 1 as i8.
    """
    value: Expression
    index: Expression

    def __repr__(self) -> str:
        return f"{self.value}[`{self.index}]"


@dataclass
class PointerDeref(Expression):
    pointer: Expression



@dataclass
class AddressOf(Expression):
    expression: Expression

    def __repr__(self) -> str:
        return f"@{self.expression}"



@dataclass
class Stringify(Expression):
    """$x or $x.member -- produce the name/value as a compile-time string literal (byte*)"""
    name: str
    member: Optional[str] = None

    def __repr__(self) -> str:
        if self.member:
            return f"${self.name}.{self.member}"
        return f"${self.name}"



@dataclass
class Codify(Expression):
    """~$x -- parse-time code injection operator.
    The byte* variable x must be initialised with a string literal.
    The parser re-lexes and re-parses that string, splicing the resulting
    statements in place of the ~$x; statement. This node never reaches codegen."""
    operand: Expression

    def __repr__(self) -> str:
        return f"~${self.operand!r}"



@dataclass
class AlignOf(Expression):
    target: Union[TypeSystem, Expression]



@dataclass
class TypeOf(Expression):
    expression: Expression
    # typeof() returns the Flux type name as a byte* string (e.g. "int",
    # "byte*", "myStru1"). Bare 'struct'/'object' keywords used as the
    # argument resolve to the literal strings "struct"/"object" via
    # DataType.STRUCT.value / DataType.OBJECT.value, so
    # typeof(x) == typeof(struct) is true for any struct-typed x while
    # typeof(x) == typeof(myStru1) is true only for that exact named type.



@dataclass
class SizeOf(Expression):
    target: Union[TypeSystem, Expression]




@dataclass
class EndianOf(Expression):
    target: Union[TypeSystem, Expression]




@dataclass
class NoInit(Expression):
    """
    Represents the noinit keyword for uninitialized variable declarations.
    This is a special marker expression that indicates a variable should not
    be automatically initialized to zero.
    
    Example:
        int x = noinit;  // x is declared but not initialized
    
    Note: This expression type should never generate code directly - it is
    handled specially in VariableDeclaration.codegen()
    """
    


# Variable declarations
@dataclass
class VariableDeclaration(ASTNode):
    name: str
    type_spec: TypeSystem
    initial_value: Optional[Expression] = None
    is_global: bool = False

    def __repr__(self) -> str:
        return f"{self.name}"

# Type declarations
@dataclass
class TypeDeclaration(Expression):
    """AST node for type declarations using AS keyword"""
    name: str
    type_spec: TypeSystem
    initial_value: Optional[Expression] = None
    
    def __repr__(self):
        init_str = f" = {self.initial_value}" if self.initial_value else ""
        return f"TypeDeclaration({self.type_spec} as {self.name}{init_str})"
    


# Statements
@dataclass
class Statement(ASTNode):
    pass

@dataclass
class ExpressionStatement(Statement):
    expression: Expression

    def __repr__(self) -> str:
        return f"{self.expression}"



@dataclass
class Assignment(Statement):
    target: Expression
    value: Expression

    def __repr__(self) -> str:
        return f"{self.target} = {self.value};"


@dataclass
class CompoundAssignment(Statement):
    target: Expression
    op_token: Any  # TokenType enum for the compound operator  
    value: Expression

    def __repr__(self) -> str:
        return f"{self.target} {self.op_token} {self.value}"


@dataclass
class RangeAssignment(Statement):
    """Set-notation range fill assignment: array[start..end] = {fill};

    Assigns the fill value to every element of 'array' from index 'start'
    to index 'end' (inclusive).

    Example:
        x[0..5] = {0};     // zero-fill indices 0 through 5
        x[2..4] = {255b};  // fill bytes 2-4 with 255
    """
    array: Expression
    start: Expression
    end: Expression
    fill: Expression

    def __repr__(self) -> str:
        return f"{self.array}[{self.start}..{self.end}] = {{{self.fill}}};"

@dataclass
class TernaryAssign(Statement):
    """x ?= value  -- assign value to x only if x == 0"""
    target: Expression
    value: Expression

    def __repr__(self) -> str:
        return f"{self.target} ?= {self.value};"

@dataclass
class Block(Statement):
    statements: List[Statement] = field(default_factory=list)

    def __repr__(self) -> str:
        if isinstance(self.statements, list):
            return f"{'\\n\\t'.join([str(x) for x in self.statements])}"


@dataclass
class IfStatement(Statement):
    condition: Expression
    then_block: Block
    elif_blocks: List[tuple] = field(default_factory=list)  # (condition, block) pairs
    else_block: Optional[Block] = None

    def __repr__(self) -> str:
        base_str = f"if ({self.condition})\n{{\n\t{self.then_block}\n}}"
        if self.elif_blocks is not None:
            for b in self.elif_blocks:
                base_str += f"\nelif\n{{\n\t{self.elif_blocks}\n}}"
        if self.else_block is not None:
            base_str += f"\nelse\n{{\n\t{self.else_block}\n}}"
        return base_str + ";\n"

@dataclass
class IfExpression(Expression):
    """
    If expression: value if (condition) [else alternative]
    
    Examples:
        int x = y if (y > 5);                    // x = y if y > 5, else x = 0 (default)
        int x = y if (y > 5) else z;             // x = y if y > 5, else x = z
        int x = y if (y > 5) else noinit;        // x = y if y > 5, else uninitialized
        int x = y if (y > 5) else noinit if (y < 5);  // Chained if-expressions
    """
    value_expr: Expression
    condition: Expression
    else_expr: Optional[Expression] = None  # Can be another IfExpression for chaining

    def __repr__(self) -> str:
        if else_expr:
            return f"{value_expr} if ({condition}) else {else_expr}"
        else:
            return f"{value_expr} if ({condition})"

@dataclass
class TernaryOp(Expression):
    """
    Ternary conditional operator: condition ? true_expr : false_expr
    
    Example:
        x > 0 ? x : -x  // Absolute value
        a == b ? 1 : 0  // Boolean to int
    """
    condition: Expression
    true_expr: Expression
    false_expr: Expression

    def __repr__(self) -> str:
        return f"{self.condition} ? {self.true_expr} : {self.false_expr}"
    


@dataclass
class NullCoalesce(Expression):
    """
    Null coalescing operator: value ?? default
    
    Returns the left operand if it's not null/zero, otherwise returns the right operand.
    
    Example:
        ptr ?? default_ptr     // Use ptr if non-null, else default_ptr
        x ?? 0                 // Use x if non-zero, else 0
    """
    left: Expression
    right: Expression


@dataclass
class NotNull(Expression):
    """
    Not-null operator: expr!?

    Postfix unary operator that evaluates to True (i8 1) when the operand is
    non-zero/non-null, and False (i8 0) when it is zero/null.

    Semantics:
        ptr!?          def   ptr != 0   (boolean i1, zero-extended to i8)
        x!?            def   x  != 0
        obj.field!?    def   obj.field != 0

    The operator sits in the postfix position because the subject is already
    in mind when the assertion is made - mirroring natural language:
        "The pointer isn't null!?"  ->  ptr!?

    Codegen produces an LLVM icmp ne ... 0 (or fcmp one for floats), then
    zext i1 to i8 so the result is a usable bool-width integer.

    Example:
        if (ptr!?) { use(ptr); };
        bool live = node.next!?;
    """
    operand: Expression

    def __repr__(self) -> str:
        return f"{self.operand}!?"
    


@dataclass
class WhileLoop(Statement):
    condition: Expression
    body: Block

    def __repr__(self) -> str:
        return f"while ({self.condition})\n{{\n\t{self.body}\n}};"

@dataclass
class DoLoop(Statement):
    """Plain do loop - executes body once"""
    body: Block

@dataclass
class DoWhileLoop(Statement):
    body: Block
    condition: Expression

@dataclass
class ForLoop(Statement):
    init: Optional[Statement]
    condition: Optional[Expression]
    update: Optional[Statement]
    body: Block

    def __repr__(self) -> str:
        return f"for ({self.init};{self.condition};{self.update})\n{{\n{self.body}}}"

@dataclass
class ForInLoop(Statement):
    variables: List[str]
    iterable: Expression
    body: Block
    is_destructure: bool = False

@dataclass
class ReturnStatement(Statement):
    value: Optional[Expression] = None

    def __repr__(self) -> str:
        return f"return {self.value};"

@dataclass
class ErrorReturnStatement(Statement):
    """
    Error return statement: error <expr>;
    
    Returns via the error channel of a dual-return function.
    The expression is returned as the error value (typed as the function's error_type).
    
    Syntax forms:
        error {"msg"};       // struct literal inferred from error_type context
        error arg;           // return existing value as error
        error -> arg;        // alternate arrow form
        error return arg;    // explicit 'return' keyword form
    """
    value: Optional[Expression] = None

    def __repr__(self) -> str:
        return f"error {self.value};"

@dataclass
class BreakStatement(Statement):
    pass

@dataclass
class BreakSwitchStatement(Statement):
    pass

@dataclass
class ContinueStatement(Statement):
    pass

@dataclass
class DeferStatement(Statement):
    expression: 'Optional[Expression]'
    body: 'Optional[List[Statement]]' = None  # block form: defer { ... };

    def __repr__(self) -> str:
        if self.body is not None:
            stmts = ' '.join(repr(s) for s in self.body)
            return f"defer {{ {stmts} }};"
        return f"defer {self.expression};"



@dataclass
class NoreturnStatement(Statement):
    def __repr__(self) -> str:
        return "noreturn;"



@dataclass
class EscapeStatement(Statement):
    call: 'Expression'

    def __repr__(self) -> str:
        return f"escape {self.call};"



@dataclass
class LabelStatement(Statement):
    name: str



@dataclass
class GotoStatement(Statement):
    target: str



# NOTE:
#
# Currently only supporting x86_64
# IT WILL GENERATE INCORRECT ASM FOR ANY OTHER ARCH (currently)
@dataclass
class JumpStatement(Statement):
    target: Expression  # Any expression yielding an address (AddressOf or integer)



@dataclass
class Case(ASTNode):
    value: Optional[Expression]  # None for default case
    body: Block

@dataclass
class SwitchStatement(Statement):
    expression: Expression
    cases: List[Case] = field(default_factory=list)

@dataclass
class TryBlock(Statement):
    try_body: Block
    catch_blocks: List[Tuple[Optional[TypeSystem], str, Block]]

@dataclass
class ThrowStatement(Statement):
    expression: Expression

@dataclass
class AssertStatement(Statement):
    condition: Expression
    message: Optional[Expression] = None

# Function parameter
@dataclass
class Parameter(ASTNode):
    name: Optional[str] # Can be none for unnamed prototype parameters
    type_spec: TypeSystem
    default_value: Optional['Expression'] = None  # e.g. the `5` in `int x = 5`

    def __repr__(self) -> str:
        if self.type_spec.custom_typename is not None:
            return f"{self.type_spec.custom_typename} {self.name}"
        else:
            return f"{self.type_spec.base_type} {self.name}"
    
    def __post_init__(self):
        # Store the original type name for debugging/metadata
        if self.type_spec.custom_typename:
            self.original_type_name = self.type_spec.custom_typename
        else:
            self.original_type_name = str(self.type_spec.base_type)

@dataclass
class FluxVMBlock(Statement):
    """Inline FVM bytecode block: fluxvm { OP [operands] ... }"""
    body: str          # raw text content of the block

    def __repr__(self) -> str:
        return f"fluxvm {{ {self.body} }}"


@dataclass
class InlineAsm(Expression):
    """Represents inline assembly block"""
    body: str
    is_volatile: bool = False
    constraints: str = ""

    def __repr__(self) -> str:
        return self.body


def _collect_label_names(stmts) -> list:
    """Recursively walk a statement list and collect all LabelStatement names."""
    names = []
    for stmt in stmts:
        if stmt is None:
            continue
        if isinstance(stmt, LabelStatement):
            names.append(stmt.name)
        # Recurse into blocks / compound statements
        if isinstance(stmt, Block):
            names.extend(_collect_label_names(stmt.statements))
        elif hasattr(stmt, 'body') and isinstance(getattr(stmt, 'body', None), Block):
            names.extend(_collect_label_names(stmt.body.statements))
        elif hasattr(stmt, 'then_block') and isinstance(getattr(stmt, 'then_block', None), Block):
            names.extend(_collect_label_names(stmt.then_block.statements))
        if hasattr(stmt, 'else_block') and isinstance(getattr(stmt, 'else_block', None), Block):
            names.extend(_collect_label_names(stmt.else_block.statements))
    return names

# Deprecate statement - compile-time check that no references to a namespace exist
@dataclass
class DeprecateStatement(Statement):
    namespace_path: str  # e.g., "standard::io::some::deprecated::namespace"



# Function definition
@dataclass
class FunctionDef(ASTNode):
    name: str
    parameters: List[Parameter]
    return_type: TypeSystem
    body: Block
    is_const: bool = False
    is_volatile: bool = False
    is_prototype: bool = False
    no_mangle: bool = False
    is_variadic: bool = False
    calling_conv: Optional[str] = None  # LLVM calling convention string, e.g. 'fastcc'
    is_recursive: bool = False
    is_inline: bool = False
    is_deprecated: bool = False
    effect_annotation: Optional['EffectAnnotation'] = None      # # effect { ... }
    attenuate_annotation: Optional['AttenuateAnnotation'] = None # # attenuate { ... }
    error_type: Optional[TypeSystem] = None  # error channel type: def f() -> int ^| ErrType

    # Map Flux calling-convention keywords to LLVM CC strings
    _CALLING_CONV_MAP: ClassVar[dict] = {
        'cdecl':      'ccc',
        'stdcall':    'x86_stdcallcc',
        'fastcall':   'fastcc',
        'thiscall':   'x86_thiscallcc',
        'vectorcall': 'x86_vectorcallcc',
    }

@dataclass
class FunctionPointerDeclaration(Statement):
    """
    Function pointer variable declaration.
    
    Syntax: def{}* fp() -> rtype = @foo;
            fastcall{}* fp() -> rtype = @foo;
    """
    name: str
    fp_type: FunctionPointerType
    initializer: Optional[Expression] = None

    def __repr__(self) -> str:
        cc = self.fp_type.calling_conv or 'def'
        return f"{cc}{{}}* {self.name}{self.fp_type}"

    @staticmethod
    def get_llvm_type(func_ptr, module):
        """Convert to LLVM function type. Delegates to fcodegen."""
        from fcodegen import _fp_decl_get_llvm_type as _fgt
        return _fgt(func_ptr, module)
def _get_fp_cconv(pointer_expr, module) -> Optional[str]:
    """Look up the LLVM calling convention for an indirect call through a named function pointer."""
    from fcodegen import _get_fp_cconv as _gfc
    return _gfc(pointer_expr, module)

@dataclass
class FunctionPointerCall(Expression):
    """Call through a function pointer"""
    pointer: Expression  # Expression that evaluates to function pointer
    arguments: List[Expression]
    


@dataclass
class FunctionPointerAssignment(Statement):
    """Assign a function to a function pointer"""
    pointer_name: str
    function_expr: Expression  # Usually AddressOf(Identifier("function_name"))
    


@dataclass
class DestructuringAssignment(Statement):
    """Destructuring assignment"""
    variables: List[Union[str, Tuple[str, TypeSystem]]]  # Can be simple names or (name, type) pairs
    source: Expression
    source_type: Optional[Identifier]  # For the "from" clause
    is_explicit: bool  # True if using "as" syntax

@dataclass
class DualAssignDeclaration(Statement):
    """
    Dual-assignment declaration for dual-return function calls.

    Syntax: success_type ^| error_type success_name, error_name = call();

    Declares two variables from one call: the success value and the error value.
    Either name may be '_' to discard that channel.
    """
    success_type: TypeSystem
    error_type: TypeSystem
    success_name: str
    error_name: str
    call_expr: Expression

    def __repr__(self) -> str:
        return f"{self.success_type} ^| {self.error_type} {self.success_name}, {self.error_name} = {self.call_expr};"

@dataclass
class EnumDef(ASTNode):
    name: str
    values: dict
    underlying_type: Optional['TypeSystem'] = None

@dataclass
class EnumDefStatement(Statement):
    enum_def: EnumDef

@dataclass
class UnionMember(ASTNode):
    name: str
    type_spec: TypeSystem
    initial_value: Optional[Expression] = None

@dataclass
class UnionDef(ASTNode):
    name: str
    members: List[UnionMember] = field(default_factory=list)
    tag_name: Optional[str] = None  # Name of the enum type used as tag
    
@dataclass
class TieExpression(Expression):
    """
    Tie operator: ~variable
    
    Transfers ownership and marks source as tied-from.
    Only creates tracking when explicitly used.
    """
    operand: Expression

    def __repr__(self) -> str:
        return f"~{self.operand}"


# Struct member
@dataclass
class StructMember(ASTNode):
    name: str
    type_spec: TypeSystem
    offset: Optional[int] = None  # Bit offset, calculated during vtable gen
    is_private: bool = False
    friend_of: Optional[str] = None  # If set, only this named object may access/inherit
    initial_value: Optional[Expression] = None

# Struct instance
@dataclass
class StructInstance(Expression):
    """
    Struct instance - actual data container.
    
    This represents an actual struct in memory with data packed inline.
    The data is already serialized according to the struct's vtable layout.
    
    Syntax:
        StructName instance_name;                    # Uninitialized
        StructName instance_name {field1 = val1};   # Initialized with literal
    
    Example:
        struct Data { 
            unsigned data{32} a; 
            unsigned data{32} b; 
        };
        
        Data d {a = 0x54534554, b = 0x21474E49};  # "TEST" "ING!"
        // Memory layout: [54 53 45 54 21 47 4E 49] = "TESTING!"
    """
    struct_name: str
    field_values: Dict[str, Expression] = field(default_factory=dict)
    

    
# Struct literal
@dataclass
class StructLiteral(Expression):
    """
    Struct literal - inline struct initialization.
    Can be either named fields {a=1, b=2} or positional {1, 2, 3}
    """
    field_values: Dict[str, Expression] = field(default_factory=dict)
    positional_values: List[Expression] = field(default_factory=list)
    struct_type: Optional[str] = None  # Can be inferred from context
    



# Struct pointer vtable
@dataclass
class StructVTable:
    struct_name: str
    total_bits: int
    total_bytes: int
    alignment: int
    fields: List[Tuple[str, int, int, int]]  # (name, bit_offset, bit_width, alignment)
    field_types: Dict[str, Any] = field(default_factory=dict)  # field_name -> LLVM type (managed by fcodegen)

    def to_llvm_constant(self, module):
        """Generate LLVM IR constant for vtable metadata. Delegates to fcodegen."""
        from fcodegen import _struct_vtable_to_llvm_constant as _svtc
        return _svtc(self, module)

# Struct definition
@dataclass
class StructDef(ASTNode):
    """
    Struct definition - creates a Table Layout Descriptor (TLD).
    Struct instances are pure data with no overhead.
    """
    name: str
    members: List[StructMember] = field(default_factory=list)
    base_structs: List[str] = field(default_factory=list)
    post_structs: List[str] = field(default_factory=list)
    nested_structs: List['StructDef'] = field(default_factory=list)
    storage_class: Optional[StorageClass] = None
    vtable: Optional[StructVTable] = None
    template_params: List[str] = field(default_factory=list)
    comptime_blocks: List = field(default_factory=list)  # (insert_index, ComptimeBlock) pairs
    
    def calculate_vtable(self, module) -> 'StructVTable':
            """Calculate struct layout and generate TLD."""
            vtable = StructTypeHandler.calculate_vtable(self.members, module)
            vtable.struct_name = self.name
            #print(f"DEBUG calculate_vtable: Created vtable for '{self.name}' with field_types={vtable.field_types}")
            return vtable
    
@dataclass
class StructFieldAccess(Expression):
    """
    Access a field from a struct/object instance.

    Syntax: instance.field_name
    """
    struct_instance: Expression
    field_name: str


@dataclass
class StructFieldAssign(Statement):
    struct_instance: Expression
    field_name: str
    value: Expression

@dataclass
class StructRecast(Expression):
    """
    Zero-cost struct reinterpretation cast.
    
    Syntax: (TargetStruct)source_data
    
    This performs:
    1. Runtime size check (can be optimized away if size is known)
    2. Bitcast pointer (zero cost)
    3. No data movement or copying
    """
    target_type: str  # Struct type name
    source_expr: Expression
    



# ============================================================================
# Helper Functions
# ============================================================================
def register_struct_type(module, type_name: str, bit_width: int, alignment: int):
    """Register a custom type in the module's type registry. Delegates to fcodegen."""
    from fcodegen import register_struct_type as _rst
    return _rst(module, type_name, bit_width, alignment)
def get_struct_vtable(module, struct_name: str) -> Optional['StructVTable']:
    """Get vtable for a struct type. Delegates to fcodegen."""
    from fcodegen import get_struct_vtable as _gsv
    return _gsv(module, struct_name)

# Trait definition (compile-time only, no IR output)
@dataclass
class TraitDef(ASTNode):
    name: str
    prototypes: List['FunctionDef'] = field(default_factory=list)


# Protocol relationship kinds for interface bodies.
# CALL_ON  : A : B   -- A may call these methods on B (existing behaviour)
# PASS_INTO: B(A)    -- return values of these A methods may be passed as args into B
# RETURN_TO: A -> B  -- these A methods may be called from inside a B method body
class ProtocolKind(Enum):
    CALL_ON   = "call_on"
    PASS_INTO = "pass_into"
    RETURN_TO = "return_to"


# Interface protocol: one directional block inside an interface body (A : B { ... })
@dataclass
class InterfaceProtocol(ASTNode):
    caller: str                    # role name that initiates / provides, e.g. "A"
    callee: str                    # role name that receives, e.g. "B"
    methods: List['FunctionDef'] = field(default_factory=list)  # prototypes only
    kind: ProtocolKind = ProtocolKind.CALL_ON  # relationship kind; defaults to existing behaviour


# Interface definition (compile-time only, no IR output)
@dataclass
class InterfaceDef(ASTNode):
    name: str
    params: List[Tuple[str, Optional[str]]] = field(default_factory=list)  # [("A", "Readable"), ...]
    protocols: List[InterfaceProtocol] = field(default_factory=list)
    attenuate_annotation: Optional['AttenuateAnnotation'] = None  # # attenuate { ... }
    effect_annotation: Optional['EffectAnnotation'] = None        # # effect { ... }


# Object method
@dataclass
class ObjectMethod(ASTNode):
    name: str
    parameters: List[Parameter]
    return_type: TypeSystem
    body: Block
    is_private: bool = False
    is_const: bool = False
    is_volatile: bool = False

# Object definition
@dataclass
class ObjectDef(ASTNode):
    name: str
    methods: List[ObjectMethod] = field(default_factory=list)
    members: List[StructMember] = field(default_factory=list)
    base_objects: List[str] = field(default_factory=list)
    nested_objects: List['ObjectDef'] = field(default_factory=list)
    nested_structs: List[StructDef] = field(default_factory=list)
    super_calls: List[Tuple[str, str, List[Expression]]] = field(default_factory=list)
    virtual_calls: List[Tuple[str, str, List[Expression]]] = field(default_factory=list)
    virtual_instances: List[Tuple[str, str, List[Expression]]] = field(default_factory=list)
    is_prototype: bool = False
    traits: List[str] = field(default_factory=list)
    template_params: List[str] = field(default_factory=list)
    interfaces: List[Tuple[str, List[str]]] = field(default_factory=list)

    def codegen_type_only(self, module):
        """Register the struct type and symbol table entry for this object without emitting method bodies.
        Called as a pre-pass so namespace-level functions can reference object types."""
        from fcodegen import _object_def_codegen_type_only as _oct
        return _oct(self, module)

@dataclass
class ExternBlock(Statement):
    """
    Extern block for FFI declarations.
    
    Syntax:
        extern {
            def function_name(params) -> return_type;
        };
    
    Or single declaration:
        extern ->function_name(params) -> return_type;
    """
    declarations: List['FunctionDef']  # List of function prototypes


class ExportBlock(ASTNode):
    """
    AST node for an 'export' block: functions made externally visible for linkage.
    Same stucture as extern, except definitions go here.
    """
    definitions: List['FunctionDef'] # Collection of function definitions

    def __init__(self, definitions):
        self.definitions = definitions  # List[FunctionDef]

# Namespace definition
@dataclass
class NamespaceDef(ASTNode):
    name: str
    functions: List[FunctionDef] = field(default_factory=list)
    structs: List[StructDef] = field(default_factory=list)
    objects: List[ObjectDef] = field(default_factory=list)
    enums: List[EnumDef] = field(default_factory=list)
    unions: List['UnionDef'] = field(default_factory=list)
    extern_blocks: List[ExternBlock] = field(default_factory=list)
    variables: List[VariableDeclaration] = field(default_factory=list)
    nested_namespaces: List['NamespaceDef'] = field(default_factory=list)
    base_namespaces: List[str] = field(default_factory=list)  # inheritance

    @staticmethod
    def _collect_all_ns_objects(ns: 'NamespaceDef', excluded: set, parent_path: str = '') -> list:
        """Return a flat list of (kind, namespace_name, item) tuples for the entire tree.
        kind is 'struct' or 'object'. namespace_name uses the fully-mangled path so that
        pre-registered types match the names produced by process_namespace_object/struct."""
        result = []
        # Build the full mangled namespace name for this level
        full_name = f"{parent_path}__{ns.name}" if parent_path else ns.name
        if full_name in excluded:
            return result
        for excl in excluded:
            if full_name.startswith(excl + "__"):
                return result
        for s in ns.structs:
            result.append(('struct', full_name, s))
        for obj in ns.objects:
            if not isinstance(obj, TraitDef):
                result.append(('object', full_name, obj))
        for nested in ns.nested_namespaces:
            result.extend(NamespaceDef._collect_all_ns_objects(nested, excluded, full_name))
        return result

    @staticmethod
    def preregister_all_types(ns: 'NamespaceDef', module, excluded: set = None) -> None:
        """Recursively walk the namespace tree and pre-register every object struct type
        before any method bodies are emitted. Delegates to fcodegen."""
        from fcodegen import _namespace_preregister_all_types as _npat
        return _npat(ns, module, excluded)

# Import statement
@dataclass
class UsingStatement(Statement):
    namespace_path: str  # e.g., "standard::io"
    



# Unusing statement (removes from using namespaces)
@dataclass
class NotUsingStatement(Statement):
    namespace_path: str  # e.g., "standard::io::file"
    



# Function definition statement
@dataclass
class FunctionDefStatement(Statement):
    function_def: FunctionDef



# Union definition statement
@dataclass
class UnionDefStatement(Statement):
    union_def: UnionDef



# Struct definition statement
@dataclass
class StructDefStatement(Statement):
    struct_def: StructDef



# Object definition statement
@dataclass
class ObjectDefStatement(Statement):
    object_def: ObjectDef



# Namespace definition statement
@dataclass
class NamespaceDefStatement(Statement):
    namespace_def: NamespaceDef



# ============================================================================
# Expression Macros (macro)
# ============================================================================

@dataclass
class macroDef(ASTNode):
    """
    Expression macro definition.

    Syntax:
        macro someMac(a, b, c)
        {
            (a + b) ^ c;
        };

    The body is a single expression. The trailing ';' inside the braces is a
    terminator only - it is consumed during parsing and is NOT injected into
    the expanded expression.

    macro->nodes are registered in the parser's macro table at parse time
    and never reach codegen directly. Invocation sites are replaced with
    macroCall, which expands by substituting caller arguments for params.
    """
    name: str
    params: List[str]          # parameter names, e.g. ['a', 'b', 'c']
    body: Expression           # parsed body expression (params appear as Identifier nodes)

    def __repr__(self) -> str:
        params_str = ', '.join(self.params)
        return f"macro {self.name}({params_str}) {{ {self.body} }}"


@dataclass
class macroCall(Expression):
    """
    Invocation of an expression macro.

    Syntax (call site):
        someMac(x, y + 1, z)

    Expansion substitutes each argument expression for the corresponding
    parameter Identifier inside the macro body. Expansion happens at
    codegen (or in a pre-codegen pass) via deep-copy + substitution so
    each call site gets an independent copy of the body.
    """
    name: str
    arguments: List[Expression] = field(default_factory=list)

    def __repr__(self) -> str:
        args_str = ', '.join(repr(a) for a in self.arguments)
        return f"{self.name}({args_str})  /* macro */"


@dataclass
class macroDefStatement(Statement):
    """Wraps an macro->so it can appear as a top-level statement."""
    macro_def: macroDef


# Contract definition
@dataclass
class ContractDef(Statement):
    """
    A named contract: a list of statements injected into a function body at compile time.

    Syntax:
        contract NonZero
        {
            assert(x > 0, "x must be positive");
        };

    Applied via colon syntax:
        def foo(int x) -> int : NonZero { ... };

    The parser expands the contract body statements into the top of the
    function body at parse time. Contract->nodes are stored in the
    parser's _contracts table and never reach codegen directly.

    Optional binding annotation (parsed after the semicolon):
        contract MyC(a,b)
        {
        } # binding { this : OtherContract };

    binding is None when not specified, otherwise a dict:
        {
            'pre':  list of str -- the pre-contract names that must appear (or ['!'] for none allowed)
            'post': list of ContractBindingRef -- post requirements (or [ContractBindingRef('!', None, False)])
        }
    Each ContractBindingRef is a 3-tuple: (name, arity_or_None, negated)
    The operator between post entries is stored in 'post_op': ',' (ordered-all), '|' (ordered-any/all), '&' (all required).
    """
    name: str
    body: Block  # statements to inject at the top of the function body
    params: List[str] = field(default_factory=list)  # param names for parameterized contracts
    binding: object = field(default=None)  # None or dict with 'pre', 'post', 'post_op'

    def __repr__(self) -> str:
        params_str = '(' + ', '.join(self.params) + ')' if self.params else ''
        return f"contract {self.name}{params_str} {{ {self.body} }}"


@dataclass
class ConstraDef(Statement):
    """
    A named relational constraint set.

    Syntax:
        constra MyCS(A, B)
        {
            A ~= B
        };

    Applied inside a template constraint set:
        <T, U, :{MyCS(T, U)}>
        <T, U, :{MyCS}>         // parameters mapped in declaration order

    Constra->nodes are stored in the parser's _constras table and never
    reach codegen directly.
    """
    name: str
    params: List[str]           # formal parameter names (A, B, ...)
    relations: list             # list of (lhs_names, op: str, rhs_names) using formal names

    def __repr__(self) -> str:
        params_str = '(' + ', '.join(self.params) + ')' if self.params else ''
        return f"constra {self.name}{params_str} {{ ... }}"


# Program root
@dataclass
class TypeFuncDef(ASTNode):
    """
    Type function definition.

    Defines a method on a built-in/literal type or a named struct type.

    Syntax:
        TYPE_OR_LITERAL.func_name(params) -> return_type { body };

    Within the body, ``this`` is an implicit first parameter that holds the
    receiver value (the left-hand side of the dot).

    ``type_name`` is the canonical string that identifies the receiver type,
    e.g. ``"byte"``, ``"int"``, ``"string"``, ``"MyStruct"``.
    ``func_name`` is the unqualified function name.
    ``parameters`` does NOT include the implicit ``this`` parameter; that is
    added automatically during lowering.
    ``return_type`` is the TypeSystem for the declared return type.
    ``body`` is the Block (may be empty for a prototype).
    ``receiver_type_spec`` is the TypeSystem of the receiver (used to build
    the implicit ``this`` parameter).
    ``is_prototype`` is True when the body is omitted (ends with ``;`` after
    the return type).
    """
    type_name: str
    func_name: str
    parameters: List['Parameter']
    return_type: 'TypeSystem'
    body: 'Block'
    receiver_type_spec: 'TypeSystem'
    is_prototype: bool = False
    calling_conv: Optional[str] = None
    is_const: bool = False
    is_volatile: bool = False
    is_inline: bool = False

    @staticmethod
    def mangle(type_name: str, func_name: str) -> str:
        """Return the internal mangled name for a type function."""
        return f"__typefunc__{type_name}__{func_name}"


@dataclass
class TypeFuncCall(Expression):
    """
    Call to a type function.

    Emitted by the parser when it sees ``expr.func_name(args)`` and the
    receiver ``expr`` resolves to a built-in / literal / named-struct type
    that has a matching type function registered.

    ``receiver`` is the expression whose value becomes ``this`` in the body.
    ``type_name`` is the canonical receiver type name (same key used in
    TypeFuncDef).
    ``func_name`` is the unqualified function name.
    ``arguments`` are the explicit arguments (NOT including the receiver).
    """
    receiver: 'Expression'
    type_name: str
    func_name: str
    arguments: List['Expression'] = field(default_factory=list)

    def __repr__(self) -> str:
        s = ', '.join(str(a) for a in self.arguments)
        return f"({self.receiver}).{self.func_name}({s})"


@dataclass
class EmitFlux(ASTNode):
    """
    emitflux { ... } -- raw Flux source text captured inside a comptime block.
    The source_text is substituted with comptime variable values and parsed
    into AST nodes that are spliced at the position of the enclosing comptime block.
    """
    source_text: str

    def __repr__(self) -> str:
        return f'EmitFlux({self.source_text!r})'


@dataclass
class ComptimeBlock(ASTNode):
    """
    comptime { ... } -- a block of statements executed at compile time via fvm.py.
    The body may contain regular Flux statements and EmitFlux nodes.
    An optional name allows the block to be targeted by goto inside other
    comptime blocks: `comptime MyBlock { ... };` / `goto MyBlock;`
    """
    body: List[ASTNode] = field(default_factory=list)
    name: str = None

    def __repr__(self) -> str:
        tag = f' {self.name}' if self.name else ''
        return f'ComptimeBlock{tag}({len(self.body)} statements)'


@dataclass
class DictLiteralExpr(Expression):
    """Inline dict literal: d{k1:v1, k2:v2, ...}[key]"""
    keys: List[Expression]
    values: List[Expression]

    def __repr__(self):
        pairs = ', '.join(f"{k}:{v}" for k, v in zip(self.keys, self.values))
        return f"d{{{pairs}}}"


@dataclass
class DictLiteral(Expression):
    """A dict literal: { k1, v1, k2, v2, ... } used in dict variable initialization."""
    entries: List[Expression] = field(default_factory=list)  # flat list: key, val, key, val, ...

    def __repr__(self) -> str:
        pairs = [f"{self.entries[i]}: {self.entries[i+1]}" for i in range(0, len(self.entries), 2)]
        return '{' + ', '.join(pairs) + '}'


@dataclass
class EffectName(Expression):
    """A single effect name, possibly namespaced: IO, IO.Socket, Hook.Detour, etc."""
    name: str

    def __repr__(self) -> str:
        return self.name


@dataclass
class EffectExpr(Expression):
    """
    An effect algebra expression node.
    operator is one of: *, ~, !, ?, @, !@, ->, ^, <->, .., ..., ^suppress, <*, &, |, >
    For unary operators: left holds the operand, right is None.
    For binary operators: left and right hold the operands.
    """
    operator: str
    left: Optional[Expression] = None
    right: Optional[Expression] = None

    def __repr__(self) -> str:
        if self.right is None:
            return f"({self.operator}{self.left})"
        return f"({self.left} {self.operator} {self.right})"


@dataclass
class EffectDef(Statement):
    """Top-level effect declaration: effect Name { expr };"""
    name: str
    body: Optional[Expression]  # effect algebra expression; None for opaque/builtin

    def __repr__(self) -> str:
        return f"effect {self.name} {{ {self.body} }}"


@dataclass
class EffectAnnotation(ASTNode):
    """# effect { expr } qualifier on a function."""
    effects: Expression

    def __repr__(self) -> str:
        return f"# effect {{ {self.effects} }}"


@dataclass
class AttenuateAnnotation(ASTNode):
    """# attenuate { expr } qualifier on an interface."""
    effects: Expression

    def __repr__(self) -> str:
        return f"# attenuate {{ {self.effects} }}"


@dataclass
class Program(ASTNode):
    symbol_table: 'SymbolTable'  # Forward reference since SymbolTable is in ftypesys
    statements: List[Statement] = field(default_factory=list)

    # DO NOT DO TRY/EXCEPT AROUND THE STATEMENT CODEGEN CALLS IN THIS CODEGEN
    # IT WILL CAPTURE EVERYTHING AND MAKE A VAGUE ERROR UNLOCATABLE
    # CAPTURE CODEGEN CALLS AT OTHER NODES TO IDENTIFY THE CALL SITE

# Example usage
if __name__ == "__main__":
    # Create a simple program AST
    main_func = FunctionDef(
        name="main",
        parameters=[],
        return_type=TypeSystem(base_type=DataType.SINT),
        body=Block([
            ReturnStatement(Literal(0, DataType.SINT))
        ])
    )
    
    program = Program(
        statements=[
            FunctionDefStatement(main_func)
        ]
    )
    
    print("AST created successfully!")
    print(f"Program has {len(program.statements)} statements")
    print(f"Main function has {len(main_func.body.statements)} statements")