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
from llvmlite import ir
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

    def accept(self, visitor, builder: ir.IRBuilder, module: ir.Module) -> Any:
        """Dispatch this node through a CodegenVisitor."""
        return visitor.visit(self, builder, module)

    def codegen(self, builder: ir.IRBuilder, module: ir.Module) -> Any:
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
    
    def create_global_string(self, module: ir.Module, string_val: str, name_hint: str = "") -> ir.Value:
        """Create a global string constant."""
        string_bytes = string_val.encode('ascii')
        str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
        str_val = ir.Constant(str_array_ty, bytearray(string_bytes))
        
        # Create unique name
        if not name_hint:
            name_hint = f"str_{ArrayLiteral._string_counter}"
            ArrayLiteral._string_counter += 1
        
        gname = f".str.{name_hint}"
        gv = ir.GlobalVariable(module, str_val.type, name=gname)
        gv.linkage = 'internal'
        gv.global_constant = True
        gv.initializer = str_val
        
        # Mark as array pointer for downstream logic
        gv.type._is_array_pointer = True
        
        return gv
    


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
        return f"\"{self.value.replace('\n','\\n').replace('\0','\\0')}\""
    


_BUILTIN_OP_SYMBOL_MANGLE = {
    '%': 'pct',  '+': 'plus', '-': 'minus', '*': 'mul',
    '/': 'div',  '<': 'lt',   '>': 'gt',    '=': 'eq',
    '&': 'amp',  '|': 'pipe', '^^': 'xor',  '!': 'not',
    '?': 'qst',  '@': 'at',   '~': 'tilde', '^': 'exp',
}

def _mangle_builtin_op(symbol: str) -> str:
    """Reproduce the parser's _mangle_op_symbol logic for built-in operator names."""
    # This mirrors parser._symbol_to_parts (greedy longest-first) then _mangle_op_symbol.
    multi = sorted(['^^!&', '^^!|', '^^!', '^^', '!&', '!|', '<=', '>=', '==', '!=',
                    '++', '--', '<<', '>>', '`!&', '`!|', '`^^'],
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
    Represents the 'x in y' membership-test expression.
    Produces a boolean: true if 'needle' is found inside 'haystack'.
    Used in if/while/ternary conditions and any other expression context.
    """
    needle: Expression
    haystack: Expression

    def __repr__(self) -> str:
        return f"({self.needle} in {self.haystack})"


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
    This is a value-convert (not a bitcast) — e.g. float(intval) emits sitofp.
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

    def _get_member_ptr(self, builder: ir.IRBuilder, module: ir.Module) -> ir.Value:
        """Return the GEP pointer to the member without loading it. Used by ++ and --."""
        if isinstance(self.object, Identifier):
            var_name = self.object.name
            if var_name == "this":
                obj_val = self.object.codegen(builder, module)
                if MemberAccessTypeHandler.is_this_double_pointer(obj_val):
                    obj_val = builder.load(obj_val, name="this_ptr")
            elif not module.symbol_table.is_global_scope() and module.symbol_table.get_llvm_value(var_name) is not None:
                obj_val = module.symbol_table.get_llvm_value(var_name)
            elif var_name in module.globals:
                obj_val = module.globals[var_name]
            else:
                obj_val = self.object.codegen(builder, module)
        else:
            obj_val = self.object.codegen(builder, module)
        # If obj_val is a pointer-to-pointer-to-struct (e.g. local var of pointer type),
        # load once to get the actual struct pointer before GEP-ing
        if (isinstance(obj_val.type, ir.PointerType) and
                isinstance(obj_val.type.pointee, ir.PointerType) and
                MemberAccessTypeHandler.is_struct_pointer(obj_val.type.pointee)):
            obj_val = builder.load(obj_val, name="struct_ptr")
        if isinstance(obj_val.type, ir.PointerType) and MemberAccessTypeHandler.is_struct_pointer(obj_val.type):
            struct_type = obj_val.type.pointee
            member_index = MemberAccessTypeHandler.get_member_index(struct_type, self.member)
            return builder.gep(
                obj_val,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), member_index)],
                inbounds=True
            )
        raise ValueError(f"Cannot get member pointer for: {obj_val.type} [{self.source_line}:{self.source_col}]")


@dataclass
class MethodCall(Expression):
    object: Expression
    method_name: str
    arguments: List[Expression] = field(default_factory=list)

    def __repr__(self) -> str:
        s = ', '.join([str(x) for x in self.arguments])
        return f"{self.object}.{self.method_name}({s})"



def _emit_va_arg(builder: ir.IRBuilder, va_list_i8ptr: ir.Value, arg_type: ir.Type, name: str = '') -> ir.Value:
    """
    Emit a va_arg instruction using llvmlite's low-level instruction API.
    llvmlite's IRBuilder does not expose va_arg directly, so we construct
    the instruction manually and insert it via builder._insert().
    The LLVM IR text produced is:  %name = va_arg i8* %ap, <type>
    """
    from llvmlite.ir import instructions as _insns

    class _VaArgInstr(_insns.Instruction):
        """Custom instruction that emits: %name = va_arg <ptr>, <type>"""
        def __init__(self, parent, typ, ptr, name=''):
            super().__init__(parent, typ, 'va_arg', [ptr], name)
            self._va_type = typ

        def descr(self, buf):
            # Emit:  va_arg <ptr_type> <ptr_value>, <result_type>
            buf.append(f'va_arg {self.operands[0].type} {self.operands[0].get_reference()}, {self._va_type}\n')

    instr = _VaArgInstr(builder.block, arg_type, va_list_i8ptr, name)
    builder._insert(instr)
    return instr


@dataclass
class VariadicAccess(Expression):
    """Represents ...[N] — access the Nth variadic argument."""
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

    # Type-kind constants used for comparison (typeof(x) == struct)
    KIND_UNKNOWN   = 0
    KIND_SINT      = 1
    KIND_UINT      = 2
    KIND_FLOAT     = 3
    KIND_DOUBLE    = 4
    KIND_BOOL      = 5
    KIND_CHAR      = 6
    KIND_BYTE      = 7
    KIND_SLONG     = 8
    KIND_ULONG     = 9
    KIND_POINTER   = 10
    KIND_ARRAY     = 11
    KIND_STRUCT    = 12
    KIND_OBJECT    = 13
    KIND_VOID      = 14
    KIND_FUNCTION  = 15



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
            return f"{'\n\t'.join([str(x) for x in self.statements])}"


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
        ptr!?          ->  ptr != 0   (boolean i1, zero-extended to i8)
        x!?            ->  x  != 0
        obj.field!?    ->  obj.field != 0

    The operator sits in the postfix position because the subject is already
    in mind when the assertion is made — mirroring natural language:
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

@dataclass
class ReturnStatement(Statement):
    value: Optional[Expression] = None

    def __repr__(self) -> str:
        return f"return {self.value};"

@dataclass
class BreakStatement(Statement):
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

# Deprecate statement — compile-time check that no references to a namespace exist
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
    def get_llvm_type(func_ptr, module: ir.Module) -> ir.FunctionType:
        """Convert to LLVM function type"""
        ret_type = func_ptr.return_type.get_llvm_type(func_ptr, module)
        param_types = [param.get_llvm_type(func_ptr, module) for param in func_ptr.parameter_types]
        return ir.FunctionType(ret_type, param_types)

def _get_fp_cconv(pointer_expr, module) -> Optional[str]:
    """Look up the LLVM calling convention for an indirect call through a named function pointer."""
    name = None
    if isinstance(pointer_expr, Identifier):
        name = pointer_expr.name
    if name and hasattr(module, '_flux_fp_calling_convs'):
        return module._flux_fp_calling_convs.get(name)
    return None

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
class EnumDef(ASTNode):
    name: str
    values: dict

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
    field_types: Dict[str, ir.Type] = field(default_factory=dict)  # field_name -> LLVM type
    
    def to_llvm_constant(self, module: ir.Module) -> ir.Constant:
        """
        Generate LLVM IR constant for vtable metadata.
        
        Format:
        {
            i32 total_bits,
            i32 field_count,
            [N x {i32 offset, i32 width, i32 alignment}] fields
        }
        """
        i32 = ir.IntType(32) # REPLACE WITH CODE TO EVALUATE INSTEAD OF HARD-CODE
        
        # Create field metadata array type
        field_type = ir.LiteralStructType([i32, i32, i32])
        field_array_type = ir.ArrayType(field_type, len(self.fields))
        
        # Build field array
        field_constants = []
        for name, offset, width, alignment in self.fields:
            field_constants.append(ir.Constant(field_type, [
                ir.Constant(i32, offset),
                ir.Constant(i32, width),
                ir.Constant(i32, alignment)
            ]))
        
        # Build vtable struct
        vtable_type = ir.LiteralStructType([
            i32,              # total_bits
            i32,              # field_count
            field_array_type  # fields
        ])
        
        return ir.Constant(vtable_type, [
            ir.Constant(i32, self.total_bits),
            ir.Constant(i32, len(self.fields)),
            ir.Constant(field_array_type, field_constants)
        ])

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
    
    def calculate_vtable(self, module: ir.Module) -> StructVTable:
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

def register_struct_type(module: ir.Module, type_name: str, bit_width: int, alignment: int):
    """
    Register a custom type in the module's type registry.
    
    Used for `unsigned data{N:M} as typename` declarations.
    """
    if not hasattr(module, '_custom_types'):
        module._custom_types = {}
    
    module._custom_types[type_name] = {
        'bit_width': bit_width,
        'alignment': alignment
        #'endianness': endianness
    }

def get_struct_vtable(module: ir.Module, struct_name: str) -> Optional[StructVTable]:
    """Get vtable for a struct type"""
    if not hasattr(module, '_struct_vtables'):
        return None
    return module._struct_vtables.get(struct_name)

# Trait definition (compile-time only, no IR output)
@dataclass
class TraitDef(ASTNode):
    name: str
    prototypes: List['FunctionDef'] = field(default_factory=list)



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
    #base_objects: List[str] = field(default_factory=list)
    nested_objects: List['ObjectDef'] = field(default_factory=list)
    nested_structs: List[StructDef] = field(default_factory=list)
    super_calls: List[Tuple[str, str, List[Expression]]] = field(default_factory=list)
    virtual_calls: List[Tuple[str, str, List[Expression]]] = field(default_factory=list)
    virtual_instances: List[Tuple[str, str, List[Expression]]] = field(default_factory=list)
    is_prototype: bool = False
    traits: List[str] = field(default_factory=list)

    def codegen_type_only(self, module: ir.Module) -> ir.Type:
        """Register the struct type and symbol table entry for this object without emitting method bodies.
        Called as a pre-pass so namespace-level functions can reference object types."""
        ObjectTypeHandler.initialize_object_storage(module)

        # Already registered (e.g. forward declaration processed earlier) - skip
        if hasattr(module, '_struct_types') and self.name in module._struct_types:
            existing_type = module._struct_types[self.name]
            if existing_type.elements:
                # Full definition already registered - nothing to do
                return existing_type
            # Opaque forward-decl exists; fill it in now if we have members
            if not self.members:
                return existing_type

        # Forward declaration with no members - create opaque type
        if not self.members and not self.methods:
            opaque_struct = ir.global_context.get_identified_type(self.name)
            opaque_struct.names = []
            if not hasattr(module, '_struct_types'):
                module._struct_types = {}
            module._struct_types[self.name] = opaque_struct
            if hasattr(module, 'symbol_table'):
                module.symbol_table.define(
                    self.name, SymbolKind.STRUCT,
                    type_spec=None, llvm_type=opaque_struct, llvm_value=None)
            return opaque_struct

        # Create member types and register struct
        member_types, member_names = ObjectTypeHandler.create_member_types(self.members, module)
        struct_type = ObjectTypeHandler.create_struct_type(self.name, member_types, member_names, module)
        fields = ObjectTypeHandler.calculate_field_layout(self.members, member_types)
        ObjectTypeHandler.create_vtable(self.name, fields, module)

        if hasattr(module, 'symbol_table'):
            module.symbol_table.define(
                self.name, SymbolKind.STRUCT,
                type_spec=None, llvm_type=struct_type, llvm_value=None)

        # Predeclare methods so they are in module.globals for cross-references
        for method in self.methods:
            func_type, func_name = ObjectTypeHandler.create_method_signature(
                self.name, method.name, method, struct_type, module)
            ObjectTypeHandler.predeclare_method(func_type, func_name, method, module)

        return struct_type

@dataclass
class ExternBlock(Statement):
    """
    Extern block for FFI declarations.
    
    Syntax:
        extern {
            def function_name(params) -> return_type;
        };
    
    Or single declaration:
        extern def function_name(params) -> return_type;
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
    def preregister_all_types(ns: 'NamespaceDef', module: ir.Module, excluded: set = None) -> None:
        """Recursively walk the namespace tree and pre-register every object struct type
        before any method bodies are emitted.  Uses a retry loop so forward references
        between objects (e.g. FreeNode* inside another object) resolve in dependency order."""
        from fcodegen import visitor as _visitor
        if excluded is None:
            excluded = getattr(module, '_excluded_namespaces', set())
        pending = NamespaceDef._collect_all_ns_objects(ns, excluded)
        max_passes = len(pending) + 1
        for _ in range(max_passes):
            if not pending:
                break
            still_pending = []
            for entry in pending:
                kind, ns_name, item = entry
                try:
                    if kind == 'struct':
                        _visitor._ns_struct(ns_name, item, None, module)
                    else:
                        _visitor._ns_object_type_only(ns_name, item, module)
                except Exception:
                    still_pending.append(entry)
            if len(still_pending) == len(pending):
                # No progress made - run once more without catching to surface the real error
                for entry in still_pending:
                    kind, ns_name, item = entry
                    if kind == 'struct':
                        _visitor._ns_struct(ns_name, item, None, module)
                    else:
                        _visitor._ns_object_type_only(ns_name, item, module)
                break
            pending = still_pending

        return None

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
    terminator only — it is consumed during parsing and is NOT injected into
    the expanded expression.

    macroDef nodes are registered in the parser's macro table at parse time
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
    """Wraps an macroDef so it can appear as a top-level statement."""
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
    function body at parse time. ContractDef nodes are stored in the
    parser's _contracts table and never reach codegen directly.
    """
    name: str
    body: Block  # statements to inject at the top of the function body
    params: List[str] = field(default_factory=list)  # param names for parameterized contracts

    def __repr__(self) -> str:
        params_str = f'({', '.join(self.params)})' if self.params else ''
        return f"contract {self.name}{params_str} {{ {self.body} }}"


# Program root
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