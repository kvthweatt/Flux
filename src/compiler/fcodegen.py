#!/usr/bin/env python3
"""
Flux Code Generator

Copyright (C) 2026 Karac Thweatt

Usage
-----
    from fcodegen import visitor
    ir_module = visitor.compile(program_node, module)
"""

import sys
import inspect
import traceback
from typing import Any, Optional

from llvmlite import ir

from ftypesys import *

# ---------------------------------------------------------------------------
# Calling-convention map
# ---------------------------------------------------------------------------

CALLING_CONV_MAP: dict = {
    'cdecl':      'ccc',
    'stdcall':    'x86_stdcallcc',
    'fastcall':   'fastcc',
    'thiscall':   'x86_thiscallcc',
    'vectorcall': 'x86_vectorcallcc',
}

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_BUILTIN_OP_SYMBOL_MANGLE: dict = {
    '+': 'plus', '-': 'minus', '*': 'mul', '/': 'div', '%': 'mod',
    '!': 'not', '^': 'pow', '&': 'and', '|': 'or',
    '<': 'lt', '>': 'gt', '=': 'eq', '~': 'tilde', '`': 'tick',
}


def _mangle_builtin_op(symbol: str) -> str:
    """Reproduce the parser's _mangle_op_symbol logic for built-in operator names."""
    multi = sorted(
        ['^^!&', '^^!|', '^^!', '^^', '!&', '!|', '<=', '>=', '==', '!=',
         '++', '--', '<<', '>>', '`!&', '`!|', '`^^'],
        key=len, reverse=True)
    parts = []
    i = 0
    while i < len(symbol):
        matched = False
        for m in multi:
            if symbol[i:i + len(m)] == m:
                parts.append(m)
                i += len(m)
                matched = True
                break
        if not matched:
            parts.append(symbol[i])
            i += 1
    mangled_parts = []
    for part in parts:
        mangled_parts.append(
            '_'.join(_BUILTIN_OP_SYMBOL_MANGLE.get(c, hex(ord(c))) for c in part))
    return '_'.join(mangled_parts)


def _collect_label_names(stmts) -> list:
    """Recursively walk a statement list and collect all LabelStatement names."""
    from fast import LabelStatement, Block
    names = []
    for stmt in stmts:
        if stmt is None:
            continue
        if isinstance(stmt, LabelStatement):
            names.append(stmt.name)
        if isinstance(stmt, Block):
            names.extend(_collect_label_names(stmt.statements))
        elif hasattr(stmt, 'body') and isinstance(getattr(stmt, 'body', None), Block):
            names.extend(_collect_label_names(stmt.body.statements))
        elif hasattr(stmt, 'then_block') and isinstance(getattr(stmt, 'then_block', None), Block):
            names.extend(_collect_label_names(stmt.then_block.statements))
        if hasattr(stmt, 'else_block') and isinstance(getattr(stmt, 'else_block', None), Block):
            names.extend(_collect_label_names(stmt.else_block.statements))
    return names


def _emit_va_arg(builder: ir.IRBuilder, va_list_i8ptr: ir.Value,
                 arg_type: ir.Type, name: str = '') -> ir.Value:
    """Emit a va_arg instruction using llvmlite's low-level instruction API."""
    from llvmlite.ir import instructions as _insns

    class _VaArgInstr(_insns.Instruction):
        def __init__(self, parent, typ, ptr, name=''):
            super().__init__(parent, typ, 'va_arg', [ptr], name)
            self._va_type = typ

        def descr(self, buf):
            buf.append(
                f'va_arg {self.operands[0].type} '
                f'{self.operands[0].get_reference()}, {self._va_type}\n')

    instr = _VaArgInstr(builder.block, arg_type, va_list_i8ptr, name)
    builder._insert(instr)
    return instr


def _get_fp_cconv(pointer_expr, module) -> Optional[str]:
    """Look up the LLVM calling convention for an indirect call through a named function pointer."""
    from fast import Identifier
    name = None
    if isinstance(pointer_expr, Identifier):
        name = pointer_expr.name
    if name and hasattr(module, '_flux_fp_calling_convs'):
        return module._flux_fp_calling_convs.get(name)
    return None


def _coerce_to_bool(builder: ir.IRBuilder, val: ir.Value) -> ir.Value:
    """Coerce *val* to an i1 suitable for use as a branch condition.

    Rules
    -----
    - Already i1 → return as-is.
    - Any other integer width → compare != 0.
    - Pointer type → compare != null  (supports ``if (ptr) { ... }``).
    - Floating-point → compare != 0.0.
    - Anything else → attempt != 0 comparison and let llvmlite surface the
      error if the type is truly incompatible.

    Note: string literals (array pointers flagged with _is_string_literal) are
    rejected here as a safety net.  The primary check happens earlier in
    _check_not_string_literal so that source location info can be included.
    """
    t = val.type
    # Safety-net: catch any string-literal array/pointer that slipped through.
    if getattr(t, '_is_string_literal', False):
        raise TypeError(
            "A string literal cannot be used as a boolean condition. "
            "Use a pointer variable instead (e.g. `byte* p = \"...\"; if (p) { ... };`).")
    if isinstance(t, ir.IntType):
        if t.width == 1:
            return val
        return builder.icmp_signed('!=', val, ir.Constant(t, 0), name='tobool')
    if isinstance(t, ir.PointerType):
        null = ir.Constant(t, None)          # null pointer constant
        return builder.icmp_unsigned('!=', val, null, name='ptrbool')
    if isinstance(t, (ir.FloatType, ir.DoubleType)):
        return builder.fcmp_ordered('!=', val, ir.Constant(t, 0.0), name='fpbool')
    # Fallback – try integer comparison; llvmlite will raise if unsupported.
    return builder.icmp_signed('!=', val, ir.Constant(t, 0), name='tobool')


def _check_not_string_literal(expr_node, context: str = 'condition', module: ir.Module = None) -> None:
    """Raise a compile-time TypeError if *expr_node* is a string or f-string literal.

    This enforces the Flux rule that string literals may not be used directly
    as boolean conditions (e.g. ``if ("x") { ... }``).  Pointer *variables*
    that happen to hold a string address are allowed; only the literal syntax
    itself is banned.

    Parameters
    ----------
    expr_node:
        The AST node for the condition expression.
    context:
        A short description of where the check is being applied, used in the
        error message (e.g. ``'if'``, ``'while'``, ``'elif'``).
    module:
        The ir.Module being compiled; used to resolve accurate source locations
        via the attached ``_flux_line_map``.
    """
    try:
        from fast import StringLiteral as _SL, FStringLiteral as _FSL
    except ImportError:
        return  # If fast module not available, skip (will be caught later)

    if isinstance(expr_node, (_SL, _FSL)):
        loc = _src_loc_with_source(expr_node, module)
        raise TypeError(
            f"String literal cannot be used as a boolean {context} {loc}. "
            f"A string literal is always a non-null pointer and its truthiness is "
            f"meaningless in Flux. Store it in a pointer variable first: "
            f"`byte* p = \"...\"; if (p) {{ ... }};`"
        )


def register_struct_type(module: ir.Module, type_name: str,
                         bit_width: int, alignment: int) -> None:
    """Register a custom data type in the module's type registry."""
    if not hasattr(module, '_custom_types'):
        module._custom_types = {}
    module._custom_types[type_name] = {
        'bit_width': bit_width,
        'alignment': alignment,
    }


def get_struct_vtable(module: ir.Module, struct_name: str):
    """Get vtable for a struct type."""
    if not hasattr(module, '_struct_vtables'):
        return None
    return module._struct_vtables.get(struct_name)


# ---------------------------------------------------------------------------
# Source location helper
# ---------------------------------------------------------------------------

def _src_loc(node, module: ir.Module) -> str:
    """
    Return a human-readable source location string for *node*.

    When a line map is attached to the module (``module._flux_line_map``),
    the global merged-source line number stored on the node is translated
    back to the original filename and its local line number so error messages
    point at the actual file the user wrote, not the preprocessed tmp.fx.

    Format when map is available:  ``filename.fx:6:1``
    Fallback (no map / out of range):  ``6:1``
    """
    line = getattr(node, 'source_line', '?')
    col  = getattr(node, 'source_col',  '?')

    line_map = getattr(module, '_flux_line_map', None) if module is not None else None
    if line_map and isinstance(line, int) and 1 <= line <= len(line_map):
        filename, local_line = line_map[line - 1]
        if filename:
            import os
            short_name = os.path.basename(filename)
            return f"[{short_name}:{local_line}:{col}]"

    return f"[{line}:{col}]"


def _src_loc_with_source(node, module: ir.Module, source_lines=None) -> str:
    """
    Like _src_loc but also appends the relevant source line text when available,
    to give the user the same context as a parser error.
    """
    loc = _src_loc(node, module)

    # Try to pull the actual source line text
    line = getattr(node, 'source_line', None)
    col  = getattr(node, 'source_col', 1) or 1
    src_text = None

    line_map = getattr(module, '_flux_line_map', None) if module is not None else None
    if line_map and isinstance(line, int) and 1 <= line <= len(line_map):
        filename, local_line = line_map[line - 1]
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as fh:
                    file_lines = fh.readlines()
                if 1 <= local_line <= len(file_lines):
                    src_text = file_lines[local_line - 1].rstrip('\n')
            except OSError:
                pass
    elif source_lines and isinstance(line, int) and 1 <= line <= len(source_lines):
        src_text = source_lines[line - 1].rstrip('\n')

    if src_text is not None:
        pointer = ' ' * (col - 1) + '^'
        return f"{loc}\n    {src_text}\n    {pointer}"
    return loc


# ---------------------------------------------------------------------------
# CodegenVisitor
# ---------------------------------------------------------------------------

class CodegenVisitor:
    """
    Visitor that drives LLVM IR generation for every Flux AST node.
    """

    # ------------------------------------------------------------------
    # Core dispatcher
    # ------------------------------------------------------------------

    def visit(self, node, builder: ir.IRBuilder, module: ir.Module) -> Any:
        """Dispatch to visit_<ClassName>(node, builder, module)."""
        if node is None:
            return None

        method_name = f'visit_{type(node).__name__}'
        method = getattr(self, method_name, None)

        if method is not None:
            return method(node, builder, module)

        if hasattr(node, 'codegen'):
            return node.codegen(builder, module)

        raise NotImplementedError(
            f"\nCodegenVisitor: no visit method for {type(node).__name__} "
            f"and node has no codegen() [{getattr(node, 'source_line', '?')}:"
            f"{getattr(node, 'source_col', '?')}]"
        )

    def compile(self, program, module: ir.Module = None) -> ir.Module:
        """Compile a Program node to an ir.Module."""
        return self.visit(program, None, module)

    def visit_NoInit(self, node, builder, module):
        raise RuntimeError(
            f"\nnoinit is a compile-time marker and should not generate code directly. "
            f"It should only be used as an initializer in variable declarations. "
            f"[{node.source_line}:{node.source_col}]"
        )

    def visit_ExpressionStatement(self, node, builder, module):
        return self.visit(node.expression, builder, module)

    # -- using / !using --------------------------------------------------

    def visit_UsingStatement(self, node, builder, module):
        if not hasattr(module, '_using_namespaces'):
            module._using_namespaces = []
        node.namespace_path = node.namespace_path.replace("::", "__")
        module._using_namespaces.append(node.namespace_path)
        if hasattr(module, 'symbol_table'):
            module.symbol_table.add_using_namespace(node.namespace_path)

    def visit_NotUsingStatement(self, node, builder, module):
        if not hasattr(module, '_excluded_namespaces'):
            module._excluded_namespaces = set()
        node.namespace_path = node.namespace_path.replace("::", "__")
        module._excluded_namespaces.add(node.namespace_path)

    # -- loop/switch control flow ----------------------------------------

    def visit_BreakStatement(self, node, builder, module):
        if not hasattr(builder, 'break_block'):
            raise SyntaxError(
                f"'break' outside of loop or switch [{node.source_line}:{node.source_col}]")
        if builder.block.is_terminated:
            return None
        builder.branch(builder.break_block)
        return None

    def visit_ContinueStatement(self, node, builder, module):
        if not hasattr(builder, 'continue_block'):
            raise SyntaxError(
                f"'continue' outside of loop [{node.source_line}:{node.source_col}]")
        if builder.block.is_terminated:
            return None
        builder.branch(builder.continue_block)
        return None

    def visit_DeferStatement(self, node, builder, module):
        if not hasattr(builder, '_flux_defer_stack'):
            builder._flux_defer_stack = []
        if node.body is not None:
            builder._flux_defer_stack.append(node.body)
        else:
            builder._flux_defer_stack.append(node.expression)
        return None

    def visit_NoreturnStatement(self, node, builder, module):
        if not builder.block.is_terminated:
            builder.unreachable()
        return None

    def visit_EscapeStatement(self, node, builder, module):
        if builder.block.is_terminated:
            return None
        if not getattr(builder, '_flux_is_recursive_func', False):
            raise SyntaxError(
                f"'escape' is only valid inside a <~ recursive function "
                f"[{node.source_line}:{node.source_col}]")
        result = self.visit(node.call, builder, module)
        func = builder.block.function
        ret_type = (func.type.return_type
                    if hasattr(func.type, 'return_type')
                    else func.type.pointee.return_type)
        if isinstance(ret_type, ir.VoidType):
            builder.ret_void()
        else:
            if result is None:
                builder.ret(ir.Constant(ret_type, 0))
            else:
                result = CoercionContext.coerce_return_value(builder, result, ret_type)
                builder.ret(result)
        return None

    # -- labels / goto / jump --------------------------------------------

    def visit_LabelStatement(self, node, builder, module):
        target_block = builder._flux_label_blocks[node.name]
        if not builder.block.is_terminated:
            builder.branch(target_block)
        builder.position_at_start(target_block)
        return None

    def visit_GotoStatement(self, node, builder, module):
        if node.target not in builder._flux_label_blocks:
            raise SyntaxError(
                f"'goto' to undefined label '{node.target}' "
                f"[{node.source_line}:{node.source_col}]")
        if builder.block.is_terminated:
            return None
        builder.branch(builder._flux_label_blocks[node.target])
        return None

    def visit_JumpStatement(self, node, builder, module):
        if builder.block.is_terminated:
            return None
        addr_val = self.visit(node.target, builder, module)
        i64 = ir.IntType(64)
        if isinstance(addr_val.type, ir.PointerType):
            addr_i64 = builder.ptrtoint(addr_val, i64, name="jump_addr")
        elif addr_val.type != i64:
            if addr_val.type.width < 64:
                addr_i64 = builder.zext(addr_val, i64, name="jump_addr")
            else:
                addr_i64 = builder.trunc(addr_val, i64, name="jump_addr")
        else:
            addr_i64 = addr_val
        ftype = ir.FunctionType(ir.VoidType(), [i64])
        asm = ir.InlineAsm(ftype, "addq $$8, %rsp\njmp *%rax", "{rax}", side_effect=True)
        builder.call(asm, [addr_i64])
        builder.unreachable()
        return None

    # -- compile-time declarations ---------------------------------------

    def visit_TraitDef(self, node, builder, module):
        if hasattr(module, 'symbol_table'):
            module.symbol_table.define(
                node.name,
                SymbolKind.TRAIT,
                type_spec=None,
                llvm_type=None,
                llvm_value=None,
            )
            module.symbol_table._trait_registry[node.name] = node.prototypes
        return None

    def visit_DeprecateStatement(self, node, builder, module):
        from fast import Identifier, FunctionCall, ASTNode
        mangled = node.namespace_path.replace("::", "__")
        statements = getattr(module, '_program_statements', [])
        references = []

        def walk(n, path="<top>"):
            if n is None:
                return
            if isinstance(n, Identifier):
                if n.name == mangled or n.name.startswith(mangled + "__"):
                    references.append(f"Identifier {n.name}")
            elif isinstance(n, FunctionCall):
                if n.name == mangled or n.name.startswith(mangled + "__"):
                    references.append(f"Function call {n.name}()")
                for i, arg in enumerate(n.arguments):
                    walk(arg, f"{path} -> call arg {i}")
            if hasattr(n, '__dataclass_fields__'):
                for field_name in n.__dataclass_fields__:
                    child = getattr(n, field_name, None)
                    child_path = f"{path}.{field_name}"
                    if isinstance(child, list):
                        for item in child:
                            walk(item, child_path)
                    elif isinstance(child, ASTNode):
                        walk(child, child_path)

        for stmt in statements:
            walk(stmt, type(stmt).__name__)

        if references:
            from fast import ComptimeError
            ref_list = "\n".join(references)
            raise ComptimeError(
                f"Deprecated namespace '{node.namespace_path}' is still referenced:\n"
                f"{ref_list} [{node.source_line}:{node.source_col}]"
            )

    # typeof() kind constants
    _TYPEOF_KIND_UNKNOWN  = 0
    _TYPEOF_KIND_SINT     = 1
    _TYPEOF_KIND_UINT     = 2
    _TYPEOF_KIND_FLOAT    = 3
    _TYPEOF_KIND_DOUBLE   = 4
    _TYPEOF_KIND_BOOL     = 5
    _TYPEOF_KIND_CHAR     = 6
    _TYPEOF_KIND_BYTE     = 7
    _TYPEOF_KIND_SLONG    = 8
    _TYPEOF_KIND_ULONG    = 9
    _TYPEOF_KIND_POINTER  = 10
    _TYPEOF_KIND_ARRAY    = 11
    _TYPEOF_KIND_STRUCT   = 12
    _TYPEOF_KIND_OBJECT   = 13
    _TYPEOF_KIND_VOID     = 14
    _TYPEOF_KIND_FUNCTION = 15

    def visit_Literal(self, node, builder, module):
        from fast import Literal
        if node.type in (DataType.SINT, DataType.UINT):
            llvm_type = TypeSystem.get_llvm_type(node.type, module, node.value)
            normalized_val = LiteralTypeHandler.normalize_int_value(node.value, node.type, llvm_type.width)
            llvm_val = ir.Constant(llvm_type, normalized_val)
            return TypeSystem.attach_type_metadata(llvm_val, node.type)
        elif node.type == DataType.FLOAT:
            llvm_type = TypeSystem.get_llvm_type(node.type, module, node.value)
            return ir.Constant(llvm_type, float(node.value))
        elif node.type == DataType.DOUBLE:
            llvm_type = TypeSystem.get_llvm_type(node.type, module, node.value)
            return ir.Constant(llvm_type, float(node.value))
        elif node.type in (DataType.SLONG, DataType.ULONG):
            llvm_type = ir.IntType(64)
            normalized_val = LiteralTypeHandler.normalize_int_value(node.value, node.type, 64)
            return TypeSystem.attach_type_metadata(ir.Constant(llvm_type, normalized_val), node.type)
        elif node.type == DataType.BOOL:
            llvm_type = TypeSystem.get_llvm_type(node.type, module, node.value)
            return ir.Constant(llvm_type, bool(node.value))
        elif node.type == DataType.CHAR:
            llvm_type = TypeSystem.get_llvm_type(node.type, module, node.value)
            char_val = LiteralTypeHandler.normalize_char_value(node.value)
            return ir.Constant(llvm_type, char_val)
        elif node.type == DataType.VOID:
            return ir.Constant(ir.IntType(1), 0)
        elif node.type == DataType.DATA:
            if isinstance(node.value, list):
                raise ValueError(
                    f"Array literal reached visit_Literal directly — must be handled by "
                    f"ArrayLiteral or VariableDeclaration [{node.source_line}:{node.source_col}]")
            elif isinstance(node.value, dict):
                return self._literal_handle_struct(node, builder, module)
            llvm_type = TypeSystem.get_llvm_type(node.type, module, node.value)
            if isinstance(llvm_type, ir.IntType):
                return ir.Constant(llvm_type, int(node.value) if isinstance(node.value, str) else node.value)
            elif isinstance(llvm_type, (ir.FloatType, ir.DoubleType)):
                return ir.Constant(llvm_type, float(node.value))
            raise ValueError(f"Unsupported DATA literal: {node.value} [{node.source_line}:{node.source_col}]")
        else:
            llvm_type = TypeSystem.get_llvm_type(node.type, module, node.value)
            if isinstance(llvm_type, ir.IntType):
                return ir.Constant(llvm_type, int(node.value) if isinstance(node.value, str) else node.value)
            elif isinstance(llvm_type, (ir.FloatType, ir.DoubleType)):
                return ir.Constant(llvm_type, float(node.value))
            raise ValueError(
                f"Unsupported literal type: {node.type} [{node.source_line}:{node.source_col}]")

    def _literal_handle_struct(self, node, builder, module):
        """Handle struct literal initialization."""
        from fast import Literal
        if not isinstance(node.value, dict):
            raise ValueError(
                f"Expected dictionary for struct literal [{node.source_line}:{node.source_col}]")
        struct_type = LiteralTypeHandler.resolve_struct_type(node.value, module)
        if module.symbol_table.is_global_scope():
            field_values = []
            for member_name in struct_type.names:
                if member_name in node.value:
                    field_expr = node.value[member_name]
                    field_index = struct_type.names.index(member_name)
                    expected_type = struct_type.elements[field_index]
                    if (isinstance(field_expr, Literal) and
                            field_expr.type == DataType.CHAR and
                            LiteralTypeHandler.is_string_pointer_field(expected_type)):
                        string_bytes = field_expr.value.encode('ascii')
                        str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
                        str_val = ir.Constant(str_array_ty, bytearray(string_bytes))
                        gv = ir.GlobalVariable(module, str_val.type,
                                               name=f".str.struct_init_{member_name}")
                        gv.linkage = 'internal'
                        gv.global_constant = True
                        gv.initializer = str_val
                        zero = ir.Constant(ir.IntType(32), 0)
                        field_values.append(gv.gep([zero, zero]))
                    else:
                        field_value = self.visit(field_expr, builder, module)
                        if (isinstance(field_value, ir.Constant) and
                                isinstance(field_value.type, ir.IntType) and
                                field_value.type.width > 8):
                            w = field_value.type.width
                            nbytes = w // 8
                            v = int(field_value.constant) & ((1 << w) - 1)
                            swapped = int.from_bytes(v.to_bytes(nbytes, "big"), "little")
                            field_value = ir.Constant(field_value.type, swapped)
                        field_values.append(field_value)
                else:
                    field_type = LiteralTypeHandler.get_struct_field_type(struct_type, member_name)
                    field_values.append(ir.Constant(field_type, 0))
            return ir.Constant(struct_type, field_values)
        else:
            struct_ptr = builder.alloca(struct_type, name="struct_literal")
            for field_name, field_value_expr in node.value.items():
                field_index = struct_type.names.index(field_name)
                field_ptr = builder.gep(
                    struct_ptr,
                    [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), field_index)],
                    inbounds=True)
                expected_type = struct_type.elements[field_index]
                if (isinstance(field_value_expr, Literal) and
                        field_value_expr.type == DataType.CHAR and
                        LiteralTypeHandler.is_string_pointer_field(expected_type)):
                    string_bytes = field_value_expr.value.encode('ascii')
                    str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
                    str_val = ir.Constant(str_array_ty, bytearray(string_bytes))
                    gv = ir.GlobalVariable(module, str_val.type,
                                           name=f".str.local_struct_init_{field_name}")
                    gv.linkage = 'internal'
                    gv.global_constant = True
                    gv.initializer = str_val
                    zero = ir.Constant(ir.IntType(32), 0)
                    field_value = builder.gep(gv, [zero, zero], name=f"{field_name}_str_ptr")
                else:
                    field_value = self.visit(field_value_expr, builder, module)
                    if field_value.type != expected_type:
                        if isinstance(field_value.type, ir.IntType) and isinstance(expected_type, ir.IntType):
                            if field_value.type.width > expected_type.width:
                                field_value = builder.trunc(field_value, expected_type)
                            elif field_value.type.width < expected_type.width:
                                field_value = builder.sext(field_value, expected_type)
                        elif isinstance(field_value.type, ir.IntType) and isinstance(expected_type, (ir.FloatType, ir.DoubleType)):
                            field_value = builder.sitofp(field_value, expected_type)
                        elif isinstance(field_value.type, (ir.FloatType, ir.DoubleType)) and isinstance(expected_type, ir.IntType):
                            field_value = builder.fptosi(field_value, expected_type)
                if isinstance(field_value.type, ir.IntType) and field_value.type.width > 8:
                    nbytes = field_value.type.width // 8
                    i8_ptr = builder.bitcast(field_ptr, ir.PointerType(ir.IntType(8)), name="be_ptr")
                    for byte_i in range(nbytes):
                        shift = (nbytes - 1 - byte_i) * 8
                        shifted = builder.lshr(field_value, ir.Constant(field_value.type, shift),
                                               name=f"be_shift_{byte_i}")
                        byte_val = builder.trunc(shifted, ir.IntType(8), name=f"be_byte_{byte_i}")
                        byte_ptr = builder.gep(i8_ptr, [ir.Constant(ir.IntType(32), byte_i)],
                                               inbounds=True, name=f"be_byteptr_{byte_i}")
                        builder.store(byte_val, byte_ptr)
                else:
                    builder.store(field_value, field_ptr)
            return builder.load(struct_ptr, name="struct_value")

    def visit_StringLiteral(self, node, builder, module):
        import fconfig as _fconfig
        _null_terminate = _fconfig.config.get('null_terminate_strings', '0').strip() == '1'
        value = node.value
        if _null_terminate and (not value or value[-1] != '\0'):
            value += '\0'
        string_bytes = value.encode('ascii')
        str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
        str_val = ir.Constant(str_array_ty, bytearray(string_bytes))
        use_global = (
            node.storage_class == StorageClass.GLOBAL or
            module.symbol_table.is_global_scope()
        )
        use_heap = node.storage_class == StorageClass.HEAP
        use_stack = (
            node.storage_class in (StorageClass.STACK, StorageClass.LOCAL) or
            (not module.symbol_table.is_global_scope() and not use_global and not use_heap)
        )
        if use_heap:
            from fast import string_heap_allocation
            return string_heap_allocation(builder, module, str_val)
        if use_global or not use_stack:
            str_name = f".str.{id(node)}"
            gv = ir.GlobalVariable(module, str_val.type, name=str_name)
            gv.linkage = 'internal'
            gv.global_constant = True
            gv.initializer = str_val
            gv.type._is_array_pointer = True
            return gv
        stack_alloca = builder.alloca(str_array_ty, name="str_stack")
        for i, byte_val in enumerate(string_bytes):
            zero = ir.Constant(ir.IntType(32), 0)
            index = ir.Constant(ir.IntType(32), i)
            elem_ptr = builder.gep(stack_alloca, [zero, index], name=f"str_char_{i}")
            builder.store(ir.Constant(ir.IntType(8), byte_val), elem_ptr)
        stack_alloca.type._is_array_pointer = True
        return stack_alloca

    def visit_RangeExpression(self, node, builder, module, element_type=None):
        start_val = self.visit(node.start, builder, module)
        end_val = self.visit(node.end, builder, module)
        range_type = element_type if element_type is not None else ir.IntType(32)
        range_struct_type = ir.LiteralStructType([range_type, range_type])
        range_struct_type.names = ['start', 'end']
        range_ptr = builder.alloca(range_struct_type, name="range")
        if isinstance(start_val.type, ir.IntType) and isinstance(range_type, ir.IntType) and start_val.type.width != range_type.width:
            start_val = builder.trunc(start_val, range_type) if start_val.type.width > range_type.width else builder.sext(start_val, range_type)
        if isinstance(end_val.type, ir.IntType) and isinstance(range_type, ir.IntType) and end_val.type.width != range_type.width:
            end_val = builder.trunc(end_val, range_type) if end_val.type.width > range_type.width else builder.sext(end_val, range_type)
        start_ptr = builder.gep(range_ptr, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)], inbounds=True)
        builder.store(start_val, start_ptr)
        end_ptr = builder.gep(range_ptr, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 1)], inbounds=True)
        builder.store(end_val, end_ptr)
        return range_ptr

    def visit_TypeConvertExpression(self, node, builder, module):
        from fast import CastExpression
        return self.visit(CastExpression(node.target_type, node.expression), builder, module)

    def visit_TypeDeclaration(self, node, builder, module):
        llvm_type = TypeSystem.get_llvm_type(node.type_spec, module, include_array=True)
        if not hasattr(module, '_type_aliases'):
            module._type_aliases = {}
        module._type_aliases[node.name] = llvm_type
        if not hasattr(module, '_type_alias_specs'):
            module._type_alias_specs = {}
        module._type_alias_specs[node.name] = node.type_spec
        if hasattr(module, 'symbol_table'):
            module.symbol_table.define(
                node.name, SymbolKind.TYPE,
                type_spec=node.type_spec, llvm_type=llvm_type, llvm_value=None)
        if node.initial_value:
            init_val = self.visit(node.initial_value, builder, module)
            gvar = ir.GlobalVariable(module, llvm_type, node.name)
            gvar.linkage = 'internal'
            gvar.global_constant = True
            gvar.initializer = init_val
            return gvar
        return None

    def visit_PointerDeref(self, node, builder, module):
        ptr_val = self.visit(node.pointer, builder, module)
        if not isinstance(ptr_val.type, ir.PointerType):
            raise ValueError(
                f"Cannot dereference non-pointer type [{node.source_line}:{node.source_col}]")
        return builder.load(ptr_val, name="deref")

    def visit_AddressOf(self, node, builder, module):
        from fast import (Literal, Identifier, PointerDeref, MemberAccess,
                          ArrayAccess, FunctionCall, NotNull, AddressOf,
                          StringLiteral, FStringLiteral, ArrayLiteral, StructLiteral)
        expr = node.expression
        # Parser bug workaround: `@x!?` is mis-parsed as AddressOf(NotNull(x))
        # instead of the correct NotNull(AddressOf(x)).  Detect and re-route.
        if isinstance(expr, NotNull):
            inner_addr = AddressOf(expr.operand)
            inner_addr.source_line = node.source_line
            inner_addr.source_col  = node.source_col
            addr_val = self.visit(inner_addr, builder, module)
            i8   = ir.IntType(8)
            null = ir.Constant(addr_val.type, None)
            cmp  = builder.icmp_unsigned('!=', addr_val, null, name='not_null')
            return builder.zext(cmp, i8, name='not_null_result')
        if isinstance(expr, Literal):
            literal_val = self.visit(expr, builder, module)
            temp = builder.alloca(literal_val.type)
            builder.store(literal_val, temp)
            return temp
        if isinstance(expr, Identifier):
            var_name = expr.name
            if (not module.symbol_table.is_global_scope() and
                    module.symbol_table.get_llvm_value(var_name) is not None):
                ptr = module.symbol_table.get_llvm_value(var_name)
                if (isinstance(ptr.type, ir.PointerType) and
                        isinstance(ptr.type.pointee, ir.PointerType)):
                    return builder.load(ptr, name=f"{var_name}_ptr")
                return ptr
            if var_name in module.globals:
                gvar = module.globals[var_name]
                if isinstance(gvar, ir.Function):
                    return gvar
                if (isinstance(gvar.type, ir.PointerType) and
                        isinstance(gvar.type.pointee, ir.PointerType) and
                        not isinstance(gvar.type.pointee, ir.ArrayType)):
                    return builder.load(gvar, name=f"{var_name}_ptr")
                return gvar
            if hasattr(module, '_function_overloads') and var_name in module._function_overloads:
                overloads = module._function_overloads[var_name]
                if len(overloads) == 1:
                    return overloads[0]['function']
                zero_arg = next((o for o in overloads if o['param_count'] == 0), None)
                if zero_arg:
                    return zero_arg['function']
                raise ValueError(
                    f"Ambiguous function reference '@{var_name}': multiple overloads exist. "
                    f"[{node.source_line}:{node.source_col}]")
            if hasattr(module, '_using_namespaces'):
                for namespace in module._using_namespaces:
                    mangled_name = namespace.replace('::', '__') + '__' + var_name
                    if mangled_name in module.globals:
                        gvar = module.globals[mangled_name]
                        if isinstance(gvar, ir.Function):
                            return gvar
                        if (isinstance(gvar.type, ir.PointerType) and
                                isinstance(gvar.type.pointee, ir.PointerType) and
                                not isinstance(gvar.type.pointee, ir.ArrayType)):
                            return builder.load(gvar, name=f"{var_name}_ptr")
                        return gvar
                    if (hasattr(module, '_function_overloads') and
                            mangled_name in module._function_overloads):
                        overloads = module._function_overloads[mangled_name]
                        if len(overloads) == 1:
                            return overloads[0]['function']
                        zero_arg = next((o for o in overloads if o['param_count'] == 0), None)
                        if zero_arg:
                            return zero_arg['function']
            raise NameError(
                f"Unknown identifier: {var_name} [{node.source_line}:{node.source_col}]")
        if isinstance(expr, PointerDeref):
            return self.visit(expr.pointer, builder, module)
        if isinstance(expr, MemberAccess):
            return expr._get_member_ptr(builder, module)
        if isinstance(expr, ArrayAccess):
            if isinstance(expr.array, Identifier):
                var_name = expr.array.name
                if (not module.symbol_table.is_global_scope() and
                        module.symbol_table.get_llvm_value(var_name) is not None):
                    array_ptr = module.symbol_table.get_llvm_value(var_name)
                elif var_name in module.globals:
                    array_ptr = module.globals[var_name]
                else:
                    mangled = IdentifierTypeHandler.resolve_namespace_mangled_name(var_name, module)
                    if mangled and module.symbol_table.get_llvm_value(mangled) is not None:
                        array_ptr = module.symbol_table.get_llvm_value(mangled)
                    elif mangled and mangled in module.globals:
                        array_ptr = module.globals[mangled]
                    else:
                        raise NameError(
                            f"Unknown array identifier: {var_name} "
                            f"[{node.source_line}:{node.source_col}]")
            elif isinstance(expr.array, MemberAccess):
                array_ptr = expr.array._get_member_ptr(builder, module)
            else:
                array_ptr = self.visit(expr.array, builder, module)
            index = self.visit(expr.index, builder, module)
            if (isinstance(array_ptr.type, ir.PointerType) and
                    isinstance(array_ptr.type.pointee, ir.PointerType)):
                array_ptr = builder.load(array_ptr, name="array_param_ptr")
            if isinstance(array_ptr.type, ir.PointerType):
                if isinstance(array_ptr.type.pointee, ir.ArrayType):
                    zero = ir.Constant(ir.IntType(32), 0)
                    return builder.gep(array_ptr, [zero, index], inbounds=True)
                return builder.gep(array_ptr, [index], inbounds=True)
        if isinstance(expr, FunctionCall):
            func_result = self.visit(expr, builder, module)
            temp_alloca = builder.alloca(func_result.type, name="func_result_temp")
            builder.store(func_result, temp_alloca)
            return temp_alloca
        if isinstance(expr, (StringLiteral, FStringLiteral, ArrayLiteral)):
            # All three visitors already return a pointer (global gvar, stack alloca, or gep),
            # so we can return it directly as the address of the data.
            return self.visit(expr, builder, module)
        if isinstance(expr, StructLiteral):
            # Allocate stack space for the struct literal, store the value into it,
            # and return a pointer -- consistent with @[...] and @"..." behaviour.
            struct_val = self.visit(expr, builder, module)
            if isinstance(struct_val.type, ir.PointerType):
                # visit_StructLiteral may already return a pointer (alloca) when
                # the literal contains non-constant fields; return it directly.
                return struct_val
            temp = builder.alloca(struct_val.type, name="struct_literal_tmp")
            builder.store(struct_val, temp)
            return temp
        raise ValueError(
            f"Cannot take address of {type(expr).__name__} [{node.source_line}:{node.source_col}]")

    def visit_Stringify(self, node, builder, module):
        from fast import ComptimeError
        current_ns = (getattr(module, '_current_namespace', '') or
                      module.symbol_table.current_namespace)
        if node.member is None:
            if (module.symbol_table.get_llvm_value(node.name) is None and
                    node.name not in module.globals and
                    module.symbol_table.lookup_variable(node.name, current_ns) is None and
                    module.symbol_table.lookup_function(node.name, current_ns) is None):
                raise ComptimeError(
                    f"Cannot stringify undefined identifier '{node.name}' "
                    f"[{node.source_line}:{node.source_col}]")
            return self._stringify_emit(builder, module, node.name, node)
        if node.member == '_':
            var_entry = module.symbol_table.lookup_variable(node.name, current_ns)
            if var_entry is None:
                raise ComptimeError(
                    f"Cannot stringify: '{node.name}' is not a defined variable "
                    f"[{node.source_line}:{node.source_col}]")
            union_name = var_entry.type_spec.custom_typename if var_entry.type_spec else None
            if (union_name is None or not hasattr(module, '_union_member_info') or
                    union_name not in module._union_member_info):
                raise ComptimeError(
                    f"Cannot stringify '._': '{node.name}' is not a tagged union variable "
                    f"[{node.source_line}:{node.source_col}]")
            union_info = module._union_member_info[union_name]
            if not union_info.get('is_tagged'):
                raise ComptimeError(
                    f"Cannot stringify '._': union '{union_name}' has no tag "
                    f"[{node.source_line}:{node.source_col}]")
            tag_enum_name = union_info['tag_name']
            if not hasattr(module, '_enum_types') or tag_enum_name not in module._enum_types:
                raise ComptimeError(
                    f"Cannot stringify '._': enum '{tag_enum_name}' not found "
                    f"[{node.source_line}:{node.source_col}]")
            enum_values = module._enum_types[tag_enum_name]
            var_llvm = module.symbol_table.get_llvm_value(node.name)
            if var_llvm is None:
                raise ComptimeError(
                    f"Cannot stringify '._': no LLVM value for '{node.name}' "
                    f"[{node.source_line}:{node.source_col}]")
            tag_ptr = builder.gep(
                var_llvm,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)],
                inbounds=True, name="tag_ptr")
            tag_val = builder.load(tag_ptr, name="tag_val")
            i8ptr = ir.PointerType(ir.IntType(8))
            result_slot = builder.alloca(i8ptr, name="stringify_result")
            after_bb = builder.append_basic_block("stringify_after")
            for enum_member, enum_int in sorted(enum_values.items(), key=lambda kv: kv[1]):
                match_bb = builder.append_basic_block(f"stringify_{enum_member}")
                next_bb = builder.append_basic_block(f"stringify_next_{enum_member}")
                cmp = builder.icmp_signed('==', tag_val, ir.Constant(ir.IntType(32), enum_int))
                builder.cbranch(cmp, match_bb, next_bb)
                builder.position_at_end(match_bb)
                str_ptr = self._stringify_emit(builder, module, f"{node.name}.{enum_member}", node)
                builder.store(str_ptr, result_slot)
                builder.branch(after_bb)
                builder.position_at_end(next_bb)
            unknown_ptr = self._stringify_emit(builder, module, f"{node.name}.<unknown>", node)
            builder.store(unknown_ptr, result_slot)
            builder.branch(after_bb)
            builder.position_at_end(after_bb)
            return builder.load(result_slot, name="stringify_tag")
        return self._stringify_emit(builder, module, f"{node.name}.{node.member}", node)

    def _stringify_emit(self, builder, module, text: str, node) -> ir.Value:
        """Emit a null-terminated string constant and return a pointer to it."""
        string_bytes = bytearray(text.encode('ascii')) + bytearray(1)
        str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
        str_val = ir.Constant(str_array_ty, string_bytes)
        gv = ir.GlobalVariable(module, str_val.type, name=f".stringify.{text}.{id(node)}")
        gv.linkage = 'internal'
        gv.global_constant = True
        gv.initializer = str_val
        zero = ir.Constant(ir.IntType(32), 0)
        return builder.gep(gv, [zero, zero], inbounds=True, name=f"str_{text}")

    def visit_AlignOf(self, node, builder, module):
        align = AlignOfTypeHandler.alignof_bytes_for_target(node.target, builder, module)
        if align is not None:
            return ir.Constant(ir.IntType(32), align)
        val = self.visit(node.target, builder, module)
        val_type = val.type.pointee if isinstance(val.type, ir.PointerType) else val.type
        align2 = AlignOfTypeHandler.alignment_from_llvm_type(val_type, module)
        if align2 is None:
            raise ValueError(
                f"Cannot determine alignment of type: {val_type} "
                f"[{node.source_line}:{node.source_col}]")
        return ir.Constant(ir.IntType(32), align2)

    def visit_SizeOf(self, node, builder, module):
        bits = SizeOfTypeHandler.sizeof_bits_for_target(node.target, builder, module)
        if bits is not None:
            return ir.Constant(ir.IntType(32), bits)
        value = self.visit(node.target, builder, module)
        bits = SizeOfTypeHandler.bits_from_llvm_type(value.type, module)
        if bits is None:
            raise ValueError(
                f"Cannot determine size of type: {value.type} "
                f"[{node.source_line}:{node.source_col}]")
        return ir.Constant(ir.IntType(32), bits)

    def visit_EndianOf(self, node, builder, module):
        endian = EndianOfTypeHandler.endianof_for_target(node.target, builder, module)
        if endian is not None:
            return ir.Constant(ir.IntType(32), endian)
        value = self.visit(node.target, builder, module)
        spec = getattr(value, '_flux_type_spec', None)
        if spec is not None:
            endian = EndianSwapHandler.get_endianness(spec)
            if endian is not None:
                return ir.Constant(ir.IntType(32), endian)
        return ir.Constant(ir.IntType(32), 0)

    def visit_TypeOf(self, node, builder, module):
        from fast import Identifier, Literal
        expr = node.expression
        if isinstance(expr, Identifier):
            kind = self._typeof_resolve_identifier_kind(expr.name, module)
            if kind is not None:
                return ir.Constant(ir.IntType(32), kind)
        if isinstance(expr, Literal):
            kind = self._typeof_kind_from_datatype(expr.type)
            return ir.Constant(ir.IntType(32), kind)
        val = self.visit(expr, builder, module)
        return ir.Constant(ir.IntType(32), self._typeof_kind_from_llvm_type(val.type))

    def _typeof_resolve_identifier_kind(self, name: str, module) -> Optional[int]:
        current_ns = (getattr(module, '_current_namespace', '') or
                      module.symbol_table.current_namespace)
        if module.symbol_table.lookup_type(name, current_ns) is not None:
            return self._TYPEOF_KIND_STRUCT
        if hasattr(module, '_struct_types'):
            if name in module._struct_types:
                return self._TYPEOF_KIND_STRUCT
            namespaces = (list(getattr(module, '_namespaces', [])) +
                          list(getattr(module.symbol_table, 'registered_namespaces', [])) +
                          list(getattr(module.symbol_table, 'using_namespaces', [])))
            for ns in namespaces:
                if ns.replace('::', '__') + '__' + name in module._struct_types:
                    return self._TYPEOF_KIND_STRUCT
            if current_ns and current_ns.replace('::', '__') + '__' + name in module._struct_types:
                return self._TYPEOF_KIND_STRUCT
        if hasattr(module, '_struct_vtables') and name in module._struct_vtables:
            return self._TYPEOF_KIND_STRUCT
        var_entry = module.symbol_table.lookup_variable(name, current_ns)
        if var_entry is not None and var_entry.type_spec is not None:
            return self._typeof_kind_from_datatype(var_entry.type_spec.base_type)
        try:
            if module.context.get_identified_type(name) is not None:
                return self._TYPEOF_KIND_STRUCT
        except Exception:
            pass
        if hasattr(module, '_struct_types'):
            for key in module._struct_types:
                if key == name or key.endswith('__' + name) or key.endswith('.' + name):
                    return self._TYPEOF_KIND_STRUCT
        return None

    def _typeof_kind_from_datatype(self, dt) -> int:
        mapping = {
            DataType.SINT:   self._TYPEOF_KIND_SINT,
            DataType.UINT:   self._TYPEOF_KIND_UINT,
            DataType.FLOAT:  self._TYPEOF_KIND_FLOAT,
            DataType.DOUBLE: self._TYPEOF_KIND_DOUBLE,
            DataType.BOOL:   self._TYPEOF_KIND_BOOL,
            DataType.CHAR:   self._TYPEOF_KIND_CHAR,
            DataType.DATA:   self._TYPEOF_KIND_BYTE,
            DataType.SLONG:  self._TYPEOF_KIND_SLONG,
            DataType.ULONG:  self._TYPEOF_KIND_ULONG,
            DataType.STRUCT: self._TYPEOF_KIND_STRUCT,
            DataType.OBJECT: self._TYPEOF_KIND_OBJECT,
            DataType.VOID:   self._TYPEOF_KIND_VOID,
        }
        return mapping.get(dt, self._TYPEOF_KIND_UNKNOWN)

    def _typeof_kind_from_llvm_type(self, llvm_type) -> int:
        if isinstance(llvm_type, ir.IntType):
            if llvm_type.width == 1:
                return self._TYPEOF_KIND_BOOL
            if llvm_type.width == 8:
                return self._TYPEOF_KIND_BYTE
            return self._TYPEOF_KIND_SINT
        if isinstance(llvm_type, ir.FloatType):
            return self._TYPEOF_KIND_FLOAT
        if isinstance(llvm_type, ir.DoubleType):
            return self._TYPEOF_KIND_DOUBLE
        if isinstance(llvm_type, ir.PointerType):
            return self._TYPEOF_KIND_POINTER
        if isinstance(llvm_type, ir.ArrayType):
            return self._TYPEOF_KIND_ARRAY
        if isinstance(llvm_type, (ir.LiteralStructType, ir.IdentifiedStructType)):
            return self._TYPEOF_KIND_STRUCT
        if isinstance(llvm_type, ir.VoidType):
            return self._TYPEOF_KIND_VOID
        return self._TYPEOF_KIND_UNKNOWN

    def visit_BinaryOp(self, node, builder, module):
        ctx = CoercionContext(builder)

        # Pointer-param overload check
        _ptr_overload_func = None
        if hasattr(module, '_function_overloads'):
            _op_sym = node.operator.value
            _op_fname = f"operator__{_mangle_builtin_op(_op_sym)}"
            if _op_fname in module._function_overloads:
                for _ov in module._function_overloads[_op_fname]:
                    if _ov['param_count'] != 2:
                        continue
                    _func = _ov['function']
                    _pts = [p.type for p in _func.args]
                    if len(_pts) != 2:
                        continue
                    if all(isinstance(pt, ir.PointerType) and
                           not isinstance(pt.pointee, (ir.ArrayType, ir.LiteralStructType, ir.IdentifiedStructType))
                           for pt in _pts):
                        _ptr_overload_func = _func
                        break

        # Suppress self-recursive dispatch: if we are currently inside the body
        # of the overload function itself, skip the overload and fall through to
        # the native LLVM instruction.
        _current_llvm_func = builder.block.function if builder.block else None

        if _ptr_overload_func is not None and _ptr_overload_func is not _current_llvm_func:
            from fast import Identifier
            def _get_alloca(n):
                if isinstance(n, Identifier) and not module.symbol_table.is_global_scope():
                    ptr = module.symbol_table.get_llvm_value(n.name)
                    if ptr is not None and isinstance(ptr.type, ir.PointerType):
                        return ptr
                return None
            _lhs_ptr = _get_alloca(node.left)
            _rhs_ptr = _get_alloca(node.right)
            _pts = [p.type for p in _ptr_overload_func.args]
            if (_lhs_ptr is not None and _rhs_ptr is not None and
                    _lhs_ptr.type == _pts[0] and _rhs_ptr.type == _pts[1]):
                return builder.call(_ptr_overload_func, [_lhs_ptr, _rhs_ptr],
                                    name="op_overload_result")

        lhs = self.visit(node.left, builder, module)
        rhs = self.visit(node.right, builder, module)

        # Built-in operator overload check
        if hasattr(module, '_function_overloads'):
            op_func_name = f"operator__{_mangle_builtin_op(node.operator.value)}"
            if op_func_name in module._function_overloads:
                overload_func = None
                for overload in module._function_overloads[op_func_name]:
                    if overload['param_count'] != 2:
                        continue
                    func = overload['function']
                    # Do not re-dispatch to the overload we are currently
                    # compiling — that produces infinite self-recursion.
                    if func is _current_llvm_func:
                        continue
                    param_types = [p.type for p in func.args]
                    if len(param_types) != 2:
                        continue
                    types_match = True
                    for raw, pt in zip([lhs, rhs], param_types):
                        rt = raw.type
                        if rt == pt:
                            continue
                        if (isinstance(rt, ir.PointerType) and
                                not isinstance(rt.pointee, (ir.ArrayType, ir.LiteralStructType, ir.IdentifiedStructType)) and
                                rt.pointee == pt):
                            continue
                        if (isinstance(rt, ir.PointerType) and
                                isinstance(rt.pointee, ir.ArrayType) and
                                isinstance(pt, ir.PointerType) and
                                rt.pointee.element == pt.pointee):
                            continue
                        types_match = False
                        break
                    if types_match:
                        overload_func = func
                        break
                if overload_func is not None:
                    adapted = []
                    for i, (av, pt) in enumerate(zip([lhs, rhs], [p.type for p in overload_func.args])):
                        rt = av.type
                        if (isinstance(rt, ir.PointerType) and
                                not isinstance(rt.pointee, (ir.ArrayType, ir.LiteralStructType, ir.IdentifiedStructType)) and
                                rt.pointee == pt):
                            av = builder.load(av, name=f"op_deref_{i}")
                        else:
                            av = FunctionTypeHandler.convert_argument_to_parameter_type(
                                builder, module, av, pt, i)
                        adapted.append(av)
                    return builder.call(overload_func, adapted, name="op_overload_result")

        lhs_is_ptr_to_ptr = (isinstance(lhs.type, ir.PointerType) and
                             isinstance(lhs.type.pointee, ir.PointerType))
        rhs_is_ptr_to_ptr = (isinstance(rhs.type, ir.PointerType) and
                             isinstance(rhs.type.pointee, ir.PointerType))

        might_be_ptr_arithmetic = (
            node.operator in (Operator.ADD, Operator.SUB) and
            (lhs_is_ptr_to_ptr or rhs_is_ptr_to_ptr or
             (isinstance(lhs.type, ir.PointerType) and isinstance(rhs.type, ir.IntType)) or
             (isinstance(rhs.type, ir.PointerType) and isinstance(lhs.type, ir.IntType)))
        )

        is_comparison = node.operator in (Operator.EQUAL, Operator.NOT_EQUAL, Operator.LESS_THAN,
                                          Operator.GREATER_THAN, Operator.LESS_EQUAL, Operator.GREATER_EQUAL)
        rhs_is_int_zero = isinstance(rhs, ir.Constant) and isinstance(rhs.type, ir.IntType) and rhs.constant == 0
        lhs_is_int_zero = isinstance(lhs, ir.Constant) and isinstance(lhs.type, ir.IntType) and lhs.constant == 0
        lhs_is_ptr = isinstance(lhs.type, ir.PointerType)
        rhs_is_ptr = isinstance(rhs.type, ir.PointerType)

        if is_comparison and lhs_is_ptr and rhs_is_int_zero:
            rhs = ir.Constant(lhs.type, None)
        elif is_comparison and rhs_is_ptr and lhs_is_int_zero:
            lhs = ir.Constant(rhs.type, None)
        elif is_comparison and lhs_is_ptr and rhs_is_ptr:
            pass
        elif not might_be_ptr_arithmetic:
            if isinstance(lhs.type, ir.PointerType):
                pointee = lhs.type.pointee
                if (not isinstance(pointee, (ir.ArrayType, ir.LiteralStructType, ir.IdentifiedStructType))
                        and not getattr(lhs, '_from_expr_method', False)):
                    lhs = builder.load(lhs, name="auto_deref_lhs")
            if isinstance(rhs.type, ir.PointerType):
                pointee = rhs.type.pointee
                if (not isinstance(pointee, (ir.ArrayType, ir.LiteralStructType, ir.IdentifiedStructType))
                        and not getattr(rhs, '_from_expr_method', False)):
                    rhs = builder.load(rhs, name="auto_deref_rhs")
        else:
            lhs_is_int_type = isinstance(lhs.type, ir.IntType)
            rhs_is_int_type = isinstance(rhs.type, ir.IntType)
            if lhs_is_ptr_to_ptr and isinstance(lhs.type.pointee.pointee, ir.IntType) and not rhs_is_int_type:
                lhs = builder.load(lhs, name="deref_ptr_for_arithmetic")
            if rhs_is_ptr_to_ptr and isinstance(rhs.type.pointee.pointee, ir.IntType) and not lhs_is_int_type:
                rhs = builder.load(rhs, name="deref_ptr_for_arithmetic")

        # Array concatenation
        if node.operator in (Operator.ADD, Operator.SUB):
            if (ArrayTypeHandler.is_array_or_array_pointer(lhs) and
                    ArrayTypeHandler.is_array_or_array_pointer(rhs)):
                return ArrayTypeHandler.concatenate(builder, module, lhs, rhs, node.operator)

        # i8* + i8* — both sides came from __expr() or are raw byte pointers.
        # auto_deref was suppressed above for __expr results, so the pointers
        # are still live here. Route to the standard string concat function.
        if (node.operator == Operator.ADD and
                getattr(lhs, '_from_expr_method', False) and
                getattr(rhs, '_from_expr_method', False)):
            concat_name = "standard__strings__manip__concat__2__byteE1_ptr1__byteE1_ptr1__ret_byteE1_ptr1"
            concat_func = module.globals.get(concat_name)
            if concat_func is not None:
                return builder.call(concat_func, [lhs, rhs], name="str_concat")

        # Pointer arithmetic
        lhs_ptr = isinstance(lhs.type, ir.PointerType)
        rhs_ptr = isinstance(rhs.type, ir.PointerType)
        lhs_int = isinstance(lhs.type, ir.IntType)
        rhs_int = isinstance(rhs.type, ir.IntType)

        if node.operator in (Operator.ADD, Operator.SUB):
            if lhs_ptr and rhs_int:
                offset = rhs
                if node.operator is Operator.SUB:
                    offset = builder.sub(ir.Constant(rhs.type, 0), rhs)
                base = lhs
                if isinstance(lhs.type.pointee, ir.ArrayType):
                    zero = ir.Constant(ir.IntType(32), 0)
                    base = builder.gep(lhs, [zero, zero], name="arr_base")
                result = builder.gep(base, [offset])
                if hasattr(lhs, '_flux_type_spec'):
                    result._flux_type_spec = lhs._flux_type_spec
                return result
            if rhs_ptr and lhs_int and node.operator is Operator.ADD:
                base = rhs
                if isinstance(rhs.type.pointee, ir.ArrayType):
                    zero = ir.Constant(ir.IntType(32), 0)
                    base = builder.gep(rhs, [zero, zero], name="arr_base")
                result = builder.gep(base, [lhs])
                if hasattr(rhs, '_flux_type_spec'):
                    result._flux_type_spec = rhs._flux_type_spec
                return result
            if lhs_ptr and rhs_ptr:
                a = builder.ptrtoint(lhs, ir.IntType(64))
                b = builder.ptrtoint(rhs, ir.IntType(64))
                return builder.sub(a, b)

        # Arithmetic
        if node.operator in (Operator.ADD, Operator.SUB, Operator.MUL, Operator.DIV,
                              Operator.MOD, Operator.POWER):
            if isinstance(lhs.type, ir.FloatType) and isinstance(rhs.type, ir.DoubleType):
                lhs = builder.fpext(lhs, ir.DoubleType(), name="float_to_double_lhs")
            elif isinstance(lhs.type, ir.DoubleType) and isinstance(rhs.type, ir.FloatType):
                rhs = builder.fpext(rhs, ir.DoubleType(), name="float_to_double_rhs")
            if isinstance(lhs.type, (ir.FloatType, ir.DoubleType)):
                if node.operator == Operator.POWER:
                    pow_name = "llvm.pow.f64" if lhs.type == ir.DoubleType() else "llvm.pow.f32"
                    pow_fn_type = ir.FunctionType(lhs.type, [lhs.type, lhs.type])
                    pow_fn = (module.globals[pow_name]
                              if pow_name in module.globals
                              else ir.Function(module, pow_fn_type, name=pow_name))
                    return builder.call(pow_fn, [lhs, rhs])
                return {
                    Operator.ADD: builder.fadd, Operator.SUB: builder.fsub,
                    Operator.MUL: builder.fmul, Operator.DIV: builder.fdiv,
                    Operator.MOD: builder.frem,
                }[node.operator](lhs, rhs)

            unsigned = ctx.is_unsigned(lhs) or ctx.is_unsigned(rhs)
            if isinstance(lhs.type, ir.IntType) and isinstance(rhs.type, ir.IntType):
                if lhs.type.width != rhs.type.width:
                    lhs, rhs = ctx.normalize_ints(lhs, rhs, unsigned=unsigned, promote=True)
            if node.operator == Operator.POWER:
                base_as_float = builder.sitofp(lhs, ir.DoubleType()) if not unsigned else builder.uitofp(lhs, ir.DoubleType())
                powi_fn_type = ir.FunctionType(ir.DoubleType(), [ir.DoubleType(), ir.IntType(32)])
                powi_fn = (module.globals["llvm.powi.f64.i32"]
                           if "llvm.powi.f64.i32" in module.globals
                           else ir.Function(module, powi_fn_type, name="llvm.powi.f64.i32"))
                if rhs.type.width > 32:
                    exp_i32 = builder.trunc(rhs, ir.IntType(32))
                elif rhs.type.width < 32:
                    exp_i32 = builder.sext(rhs, ir.IntType(32))
                else:
                    exp_i32 = rhs
                result_float = builder.call(powi_fn, [base_as_float, exp_i32])
                result = builder.fptoui(result_float, lhs.type) if unsigned else builder.fptosi(result_float, lhs.type)
            else:
                result = {
                    Operator.ADD: builder.add, Operator.SUB: builder.sub,
                    Operator.MUL: builder.mul,
                    Operator.DIV: builder.udiv if unsigned else builder.sdiv,
                    Operator.MOD: builder.urem if unsigned else builder.srem,
                }[node.operator](lhs, rhs)
            return TypeSystem.attach_type_metadata(result, DataType.UINT if unsigned else DataType.SINT)

        # Comparisons
        if node.operator in (Operator.EQUAL, Operator.NOT_EQUAL, Operator.LESS_THAN,
                              Operator.LESS_EQUAL, Operator.GREATER_THAN, Operator.GREATER_EQUAL):
            op_map = {
                Operator.EQUAL: "==", Operator.NOT_EQUAL: "!=",
                Operator.LESS_THAN: "<", Operator.LESS_EQUAL: "<=",
                Operator.GREATER_THAN: ">", Operator.GREATER_EQUAL: ">=",
            }
            op = op_map[node.operator]
            if isinstance(lhs.type, (ir.FloatType, ir.DoubleType)) and isinstance(rhs.type, (ir.FloatType, ir.DoubleType)):
                if isinstance(lhs.type, ir.FloatType) and isinstance(rhs.type, ir.DoubleType):
                    lhs = builder.fpext(lhs, ir.DoubleType(), name="float_to_double_lhs")
                elif isinstance(lhs.type, ir.DoubleType) and isinstance(rhs.type, ir.FloatType):
                    rhs = builder.fpext(rhs, ir.DoubleType(), name="float_to_double_rhs")
                return builder.fcmp_ordered(op, lhs, rhs)
            if isinstance(lhs.type, ir.PointerType) or isinstance(rhs.type, ir.PointerType):
                return ctx.emit_ptr_cmp(op, lhs, rhs)
            if isinstance(lhs.type, ir.IntType) and isinstance(rhs.type, ir.IntType):
                if lhs.type.width != rhs.type.width:
                    unsigned = ctx.is_unsigned(lhs) or ctx.is_unsigned(rhs)
                    lhs, rhs = ctx.normalize_ints(lhs, rhs, unsigned=unsigned, promote=True)
            return ctx.emit_int_cmp(op, lhs, rhs)

        # Bitwise
        if node.operator in (Operator.BITAND, Operator.BITOR, Operator.BITXOR):
            lhs, rhs = ctx.normalize_ints(lhs, rhs, unsigned=True, promote=True)
            result = {
                Operator.BITAND: builder.and_,
                Operator.BITOR:  builder.or_,
                Operator.BITXOR: builder.xor,
            }[node.operator](lhs, rhs)
            unsigned = ctx.is_unsigned(lhs) or ctx.is_unsigned(rhs)
            return TypeSystem.attach_type_metadata(result, DataType.UINT if unsigned else DataType.SINT)

        if node.operator in (Operator.AND, Operator.OR, Operator.XOR):
            if isinstance(lhs.type, ir.IntType) and isinstance(rhs.type, ir.IntType):
                if lhs.type.width != rhs.type.width:
                    lhs, rhs = ctx.normalize_ints(lhs, rhs, unsigned=True, promote=True)
            result = {
                Operator.AND: builder.and_,
                Operator.OR:  builder.or_,
                Operator.XOR: builder.xor,
            }[node.operator](lhs, rhs)
            unsigned = ctx.is_unsigned(lhs) or ctx.is_unsigned(rhs)
            return TypeSystem.attach_type_metadata(result, DataType.UINT if unsigned else DataType.SINT)

        # Shifts
        if node.operator in (Operator.BITSHIFT_LEFT, Operator.BITSHIFT_RIGHT):
            if lhs.type.width != rhs.type.width:
                if rhs.type.width < lhs.type.width:
                    rhs = builder.zext(rhs, lhs.type)
                else:
                    rhs = builder.trunc(rhs, lhs.type)
            if node.operator is Operator.BITSHIFT_LEFT:
                result = builder.shl(lhs, rhs)
                return TypeSystem.attach_type_metadata(result, DataType.UINT if ctx.is_unsigned(lhs) else DataType.SINT)
            result = (builder.lshr(lhs, rhs)
                      if ctx.is_unsigned(lhs) or not hasattr(lhs, '_flux_type_spec')
                      else builder.ashr(lhs, rhs))
            return TypeSystem.attach_type_metadata(result, DataType.UINT if ctx.is_unsigned(lhs) else DataType.SINT)

        # Boolean composites
        if node.operator is Operator.NOR:
            return builder.not_(builder.or_(lhs, rhs))
        if node.operator is Operator.NAND:
            return builder.not_(builder.and_(lhs, rhs))
        if node.operator is Operator.BITNAND:
            result = builder.not_(builder.and_(lhs, rhs))
            unsigned = ctx.is_unsigned(lhs) or ctx.is_unsigned(rhs)
            return TypeSystem.attach_type_metadata(result, DataType.UINT if unsigned else DataType.SINT)
        if node.operator is Operator.BITNOR:
            result = builder.not_(builder.or_(lhs, rhs))
            unsigned = ctx.is_unsigned(lhs) or ctx.is_unsigned(rhs)
            return TypeSystem.attach_type_metadata(result, DataType.UINT if unsigned else DataType.SINT)
        if node.operator is Operator.BITXNOR:
            result = builder.not_(builder.xor(lhs, rhs))
            unsigned = ctx.is_unsigned(lhs) or ctx.is_unsigned(rhs)
            return TypeSystem.attach_type_metadata(result, DataType.UINT if unsigned else DataType.SINT)

        raise ValueError(
            f"Unsupported operator: {node.operator} [{node.source_line}:{node.source_col}]")

    def visit_UnaryOp(self, node, builder, module):
        from fast import Identifier, AddressOf, MemberAccess
        if (node.operator in (Operator.INCREMENT, Operator.DECREMENT) and
                isinstance(node.operand, AddressOf)):
            return self._unary_increment_address_of(node, builder, module)

        operand_val = self.visit(node.operand, builder, module)

        if node.operator in (Operator.INCREMENT, Operator.DECREMENT):
            if isinstance(node.operand, Identifier):
                if (isinstance(operand_val.type, ir.PointerType) and
                        isinstance(operand_val.type.pointee, ir.PointerType)):
                    operand_val = builder.load(operand_val, name=f"{node.operand.name}_loaded")

        if node.operator == Operator.NOT:
            if isinstance(operand_val.type, ir.PointerType):
                null = ir.Constant(operand_val.type, None)
                return builder.icmp_unsigned('==', operand_val, null, name="is_null")
            if module.symbol_table.is_global_scope() and isinstance(operand_val, ir.Constant):
                if isinstance(operand_val.type, ir.IntType):
                    return ir.Constant(operand_val.type, ~operand_val.constant)
            return builder.not_(operand_val)

        elif node.operator == Operator.SUB:
            if module.symbol_table.is_global_scope() and isinstance(operand_val, ir.Constant):
                if isinstance(operand_val.type, ir.IntType):
                    return ir.Constant(operand_val.type, -operand_val.constant)
                elif isinstance(operand_val.type, (ir.FloatType, ir.DoubleType)):
                    return ir.Constant(operand_val.type, -operand_val.constant)
            if isinstance(operand_val.type, (ir.FloatType, ir.DoubleType)):
                return builder.fsub(ir.Constant(operand_val.type, 0.0), operand_val)
            return builder.neg(operand_val)

        elif node.operator == Operator.INCREMENT:
            if isinstance(operand_val.type, ir.PointerType):
                new_val = builder.gep(operand_val, [ir.Constant(ir.IntType(32), 1)], name="ptr_inc")
            else:
                new_val = builder.add(operand_val, ir.Constant(operand_val.type, 1))
            if isinstance(node.operand, Identifier):
                ptr = self._unary_get_var_ptr(node.operand.name, node, builder, module)
                st = builder.store(new_val, ptr)
                if hasattr(builder, 'volatile_vars') and node.operand.name in builder.volatile_vars:
                    st.volatile = True
            elif isinstance(node.operand, MemberAccess):
                builder.store(new_val, node.operand._get_member_ptr(builder, module))
            return new_val if not node.is_postfix else operand_val

        elif node.operator == Operator.DECREMENT:
            if isinstance(operand_val.type, ir.PointerType):
                new_val = builder.gep(operand_val, [ir.Constant(ir.IntType(32), -1)], name="ptr_dec")
            else:
                new_val = builder.sub(operand_val, ir.Constant(operand_val.type, 1))
            if isinstance(node.operand, Identifier):
                ptr = self._unary_get_var_ptr(node.operand.name, node, builder, module)
                st = builder.store(new_val, ptr)
                if hasattr(builder, 'volatile_vars') and node.operand.name in builder.volatile_vars:
                    st.volatile = True
            elif isinstance(node.operand, MemberAccess):
                builder.store(new_val, node.operand._get_member_ptr(builder, module))
            return new_val if not node.is_postfix else operand_val

        elif node.operator == Operator.BITNOT:
            if module.symbol_table.is_global_scope() and isinstance(operand_val, ir.Constant):
                if isinstance(operand_val.type, ir.IntType):
                    return ir.Constant(operand_val.type, ~operand_val.constant)
            return builder.not_(operand_val)

        raise ValueError(
            f"Unsupported unary operator: {node.operator} [{node.source_line}:{node.source_col}]")

    def _unary_get_var_ptr(self, name, node, builder, module):
        if (not module.symbol_table.is_global_scope() and
                module.symbol_table.get_llvm_value(name) is not None):
            return module.symbol_table.get_llvm_value(name)
        if name in module.globals:
            return module.globals[name]
        mangled = IdentifierTypeHandler.resolve_namespace_mangled_name(name, module)
        if mangled and module.symbol_table.get_llvm_value(mangled) is not None:
            return module.symbol_table.get_llvm_value(mangled)
        if mangled and mangled in module.globals:
            return module.globals[mangled]
        raise NameError(
            f"Variable '{name}' not found in any scope [{node.source_line}:{node.source_col}]")

    def _unary_increment_address_of(self, node, builder, module):
        base_address = self.visit(node.operand, builder, module)
        if isinstance(base_address.type, ir.PointerType):
            if isinstance(base_address.type.pointee, ir.ArrayType):
                zero = ir.Constant(ir.IntType(32), 0)
                array_start = builder.gep(base_address, [zero, zero], name="array_start")
                offset = ir.Constant(ir.IntType(32), 1 if node.operator == Operator.INCREMENT else -1)
                return builder.gep(array_start, [offset],
                                   name="inc_addr" if node.operator == Operator.INCREMENT else "dec_addr")
            else:
                offset = ir.Constant(ir.IntType(32), 1 if node.operator == Operator.INCREMENT else -1)
                return builder.gep(base_address, [offset],
                                   name="inc_addr" if node.operator == Operator.INCREMENT else "dec_addr")
        raise ValueError(
            f"Cannot increment/decrement address of non-pointer type: {base_address.type} "
            f"[{node.source_line}:{node.source_col}]")

    def visit_CastExpression(self, node, builder, module):
        from fast import Literal, Identifier
        target_llvm_type = TypeSystem.get_llvm_type(node.target_type, module, include_array=True)

        if isinstance(target_llvm_type, ir.VoidType):
            return self._cast_handle_void(node, builder, module)

        if isinstance(node.expression, Literal) and node.expression.type == DataType.VOID:
            if isinstance(target_llvm_type, ir.PointerType):
                return ir.Constant(target_llvm_type, None)
            if isinstance(target_llvm_type, ir.IntType):
                return ir.Constant(target_llvm_type, 0)
            if isinstance(target_llvm_type, (ir.HalfType, ir.FloatType, ir.DoubleType)):
                return ir.Constant(target_llvm_type, 0.0)
            raise TypeError(
                f"cannot cast void-literal to {target_llvm_type} "
                f"[{node.source_line}:{node.source_col}]")

        source_val = self.visit(node.expression, builder, module)
        if source_val.type == target_llvm_type:
            # Even though the LLVM types are identical (e.g. le32 and uint are
            # both i32), an explicit cast is a value-level reinterpretation: the
            # caller expressed `uint(y)` specifically to shed the endianness tag
            # on `y`.  Returning source_val unchanged would leave its
            # _flux_type_spec pointing at the source type (e.g. le32), which
            # causes a false endianness-mismatch error at the call site.
            # We must stamp the target type spec onto the result so that the
            # endianness check in visit_FunctionCall sees a neutral (non-endian)
            # type rather than the source's endian annotation.
            source_val._flux_type_spec = node.target_type
            return source_val

        void_ptr_type = ir.PointerType(ir.IntType(8))
        if target_llvm_type == void_ptr_type and isinstance(source_val.type, ir.PointerType):
            return builder.bitcast(source_val, void_ptr_type, name="to_void_ptr")
        if source_val.type == void_ptr_type and isinstance(target_llvm_type, ir.PointerType):
            return builder.bitcast(source_val, target_llvm_type, name="from_void_ptr")

        if (isinstance(source_val.type, ir.PointerType) and
                isinstance(source_val.type.pointee, ir.LiteralStructType) and
                isinstance(target_llvm_type, ir.LiteralStructType)):
            src_sz = sum(e.width for e in source_val.type.pointee.elements if hasattr(e, 'width'))
            tgt_sz = sum(e.width for e in target_llvm_type.elements if hasattr(e, 'width'))
            if src_sz != tgt_sz:
                raise ValueError(
                    f"Cannot cast struct of size {src_sz} to struct of size {tgt_sz} "
                    f"[{node.source_line}:{node.source_col}]")
            ptr = builder.bitcast(source_val, ir.PointerType(target_llvm_type), name="struct_reinterpret")
            return builder.load(ptr, name="reinterpreted_struct")

        elif (isinstance(source_val.type, ir.LiteralStructType) and
              isinstance(target_llvm_type, ir.LiteralStructType)):
            src_sz = sum(e.width for e in source_val.type.elements if hasattr(e, 'width'))
            tgt_sz = sum(e.width for e in target_llvm_type.elements if hasattr(e, 'width'))
            if src_sz != tgt_sz:
                raise ValueError(
                    f"Cannot cast struct of size {src_sz} to struct of size {tgt_sz} "
                    f"[{node.source_line}:{node.source_col}]")
            src_ptr = builder.alloca(source_val.type, name="temp_source")
            builder.store(source_val, src_ptr)
            ptr = builder.bitcast(src_ptr, ir.PointerType(target_llvm_type), name="struct_reinterpret")
            return builder.load(ptr, name="reinterpreted_struct")

        if isinstance(source_val.type, ir.IntType) and isinstance(target_llvm_type, ir.IntType):
            if source_val.type.width > target_llvm_type.width:
                result = builder.trunc(source_val, target_llvm_type)
            elif source_val.type.width < target_llvm_type.width:
                if isinstance(node.expression, Literal):
                    if node.expression.type == DataType.UINT:
                        result = builder.zext(source_val, target_llvm_type)
                    else:
                        result = builder.sext(source_val, target_llvm_type)
                else:
                    source_unsigned = CoercionContext.is_unsigned(source_val)
                    if not source_unsigned and isinstance(node.expression, Identifier):
                        expr_spec = TypeResolver.resolve_type_spec(node.expression.name, module)
                        if expr_spec is not None and hasattr(expr_spec, 'is_signed'):
                            source_unsigned = not expr_spec.is_signed
                    if source_unsigned or node.target_type.base_type == DataType.UINT or (
                            node.target_type.custom_typename and
                            node.target_type.custom_typename.startswith('u')):
                        result = builder.zext(source_val, target_llvm_type)
                    else:
                        result = builder.sext(source_val, target_llvm_type)
            else:
                result = source_val
            result._flux_type_spec = node.target_type
            return result

        elif isinstance(source_val.type, ir.IntType) and isinstance(target_llvm_type, (ir.FloatType, ir.DoubleType)):
            return builder.sitofp(source_val, target_llvm_type)
        elif isinstance(source_val.type, (ir.FloatType, ir.DoubleType)) and isinstance(target_llvm_type, ir.IntType):
            return builder.fptosi(source_val, target_llvm_type)
        elif isinstance(source_val.type, ir.FloatType) and isinstance(target_llvm_type, ir.DoubleType):
            return builder.fpext(source_val, target_llvm_type)
        elif isinstance(source_val.type, ir.DoubleType) and isinstance(target_llvm_type, ir.FloatType):
            return builder.fptrunc(source_val, target_llvm_type)
        elif (isinstance(source_val.type, ir.PointerType) and
              isinstance(target_llvm_type, ir.LiteralStructType)):
            ptr = builder.bitcast(source_val, ir.PointerType(target_llvm_type), name="ptr_to_struct")
            return builder.load(ptr, name="loaded_struct")
        elif (isinstance(source_val.type, ir.LiteralStructType) and
              isinstance(target_llvm_type, ir.PointerType)):
            if hasattr(source_val, 'name') and source_val.name and 'struct' in source_val.name:
                src_name = source_val.name.replace('_struct_load', '').replace('_load', '')
                if module.symbol_table.get_llvm_value(src_name) is not None:
                    return builder.bitcast(module.symbol_table.get_llvm_value(src_name),
                                           target_llvm_type, name="struct_to_ptr")
            src_ptr = builder.alloca(source_val.type, name="struct_for_cast")
            builder.store(source_val, src_ptr)
            return builder.bitcast(src_ptr, target_llvm_type, name="struct_to_ptr")
        elif isinstance(source_val.type, ir.PointerType) and isinstance(target_llvm_type, ir.PointerType):
            return builder.bitcast(source_val, target_llvm_type)
        elif isinstance(source_val.type, ir.IntType) and isinstance(target_llvm_type, ir.PointerType):
            if source_val.type.width < 64:
                source_val = builder.zext(source_val, ir.IntType(64), name="int_to_ptr_zext")
            return builder.inttoptr(source_val, target_llvm_type, name="int_to_ptr")
        elif isinstance(source_val.type, ir.PointerType) and isinstance(target_llvm_type, ir.IntType):
            if isinstance(source_val.type.pointee, ir.ArrayType):
                return ArrayTypeHandler.pack_array_pointer_to_integer(
                    builder, module, source_val, target_llvm_type)
            return builder.ptrtoint(source_val, target_llvm_type, name="ptr_to_int")
        elif (isinstance(source_val.type, ir.PointerType) and
              isinstance(target_llvm_type, (ir.FloatType, ir.DoubleType))):
            if isinstance(source_val.type.pointee, ir.ArrayType):
                return ArrayTypeHandler.pack_array_pointer_to_float(
                    builder, module, source_val, target_llvm_type)
        elif isinstance(target_llvm_type, ir.ArrayType):
            if (isinstance(source_val.type, ir.PointerType) and
                    isinstance(source_val.type.pointee, ir.ArrayType) and
                    source_val.type.pointee.element == target_llvm_type.element):
                count = target_llvm_type.count
                null_term_type = ir.ArrayType(target_llvm_type.element, count + 1)
                alloca = builder.alloca(null_term_type, name="arr_trunc")
                zero = ir.Constant(ir.IntType(32), 0)
                for i in range(count):
                    idx = ir.Constant(ir.IntType(32), i)
                    src_ptr = builder.gep(source_val, [zero, idx], inbounds=True, name=f"src_{i}")
                    src_val = builder.load(src_ptr, name=f"val_{i}")
                    dst_ptr = builder.gep(alloca, [zero, idx], inbounds=True, name=f"dst_{i}")
                    builder.store(src_val, dst_ptr)
                null_idx = ir.Constant(ir.IntType(32), count)
                null_ptr = builder.gep(alloca, [zero, null_idx], inbounds=True, name="null_term")
                builder.store(ir.Constant(target_llvm_type.element, 0), null_ptr)
                return alloca
            # Source is a bare pointer-to-element (e.g. i8* from an array slice or a
            # single-element address).  Copy 'count' elements directly — do NOT convert
            # the pointer value itself to an integer and unpack its bytes, which would
            # produce garbage stack-address bytes instead of the actual data.
            if (isinstance(source_val.type, ir.PointerType) and
                    source_val.type.pointee == target_llvm_type.element):
                count = target_llvm_type.count
                zero = ir.Constant(ir.IntType(32), 0)
                null_term_type = ir.ArrayType(target_llvm_type.element, count + 1)
                alloca = builder.alloca(null_term_type, name="arr_from_ptr")
                for i in range(count):
                    idx = ir.Constant(ir.IntType(32), i)
                    src_ptr = builder.gep(source_val, [idx], inbounds=True, name=f"src_{i}")
                    src_val_elem = builder.load(src_ptr, name=f"val_{i}")
                    dst_ptr = builder.gep(alloca, [zero, idx], inbounds=True, name=f"dst_{i}")
                    builder.store(src_val_elem, dst_ptr)
                null_idx = ir.Constant(ir.IntType(32), count)
                null_ptr = builder.gep(alloca, [zero, null_idx], inbounds=True, name="null_term")
                builder.store(ir.Constant(target_llvm_type.element, 0), null_ptr)
                return alloca
            # Source is a scalar integer — unpack its bytes into a null-terminated array.
            # For byte[N] / char[N] casts of a scalar value (e.g. `(byte[1])word[0]`)
            # we must allocate count+1 slots and write a null terminator so that the
            # result is usable as a C-string by println / %s.  Delegating to
            # unpack_integer_to_array produces a count-element array with NO null
            # terminator, so the consumer reads garbage bytes past the payload.
            if (isinstance(source_val.type, ir.IntType) and
                    isinstance(target_llvm_type.element, ir.IntType) and
                    target_llvm_type.element.width == 8):
                count = target_llvm_type.count
                zero = ir.Constant(ir.IntType(32), 0)
                null_term_type = ir.ArrayType(target_llvm_type.element, count + 1)
                alloca = builder.alloca(null_term_type, name="scalar_to_bytes")
                i8 = ir.IntType(8)
                # Widen the source to at least 32 bits so lshr is legal for multi-byte
                # casts; for a single byte we just truncate directly.
                src_width = source_val.type.width
                if src_width < 32:
                    wide = builder.zext(source_val, ir.IntType(32), name="scalar_widen")
                else:
                    wide = source_val
                # Big-endian byte layout: byte 0 = most-significant byte of the value,
                # matching the existing unpack_integer_to_array convention.
                for i in range(count):
                    shift = (count - 1 - i) * 8
                    if shift > 0:
                        shifted = builder.lshr(wide, ir.Constant(wide.type, shift),
                                               name=f"scalar_shift_{i}")
                    else:
                        shifted = wide
                    byte_val = builder.trunc(shifted, i8, name=f"scalar_byte_{i}")
                    dst_ptr = builder.gep(alloca, [zero, ir.Constant(ir.IntType(32), i)],
                                         inbounds=True, name=f"scalar_dst_{i}")
                    builder.store(byte_val, dst_ptr)
                # Null terminator
                null_idx = ir.Constant(ir.IntType(32), count)
                null_ptr = builder.gep(alloca, [zero, null_idx], inbounds=True,
                                       name="scalar_null_term")
                builder.store(ir.Constant(i8, 0), null_ptr)
                return alloca
            # General fallback — unpack scalar integer bytes (no null terminator).
            return ArrayTypeHandler.unpack_integer_to_array(builder, module, source_val, target_llvm_type)
        else:
            raise ValueError(
                f"Unsupported cast from {source_val.type} to {target_llvm_type} "
                f"[{node.source_line}:{node.source_col}]")

    def _cast_handle_void(self, node, builder, module):
        from fast import Identifier
        if isinstance(node.expression, Identifier):
            var_name = node.expression.name
            if (not module.symbol_table.is_global_scope() and
                    module.symbol_table.get_llvm_value(var_name) is not None):
                var_ptr = module.symbol_table.get_llvm_value(var_name)
                # heap variable: the alloca holds a T* pointing into the heap.
                # Call ffree(addr) where addr is the heap pointer cast to u64.
                if getattr(var_ptr, '_flux_is_heap', False):
                    # heap var: call ffree, then null the alloca
                    heap_ptr = builder.load(var_ptr, name=f"{var_name}_heapptr")
                    self._cast_ffree(builder, module, heap_ptr, var_name)
                    builder.store(ir.Constant(heap_ptr.type, None), var_ptr)
                else:
                    # Stack/pointer var: null the alloca to invalidate -- cannot free stack memory
                    if isinstance(var_ptr.type.pointee, ir.PointerType):
                        null = ir.Constant(var_ptr.type.pointee, None)
                    else:
                        null = ir.Constant(var_ptr.type.pointee, 0)
                    builder.store(null, var_ptr)
                module.symbol_table.delete_variable(var_name)
            elif var_name in module.globals:
                # Global pointer: null it out in place
                gvar = module.globals[var_name]
                if isinstance(gvar.type.pointee, ir.PointerType):
                    builder.store(ir.Constant(gvar.type.pointee, None), gvar)
                else:
                    builder.store(ir.Constant(gvar.type.pointee, 0), gvar)
            else:
                raise NameError(
                    f"Cannot void cast unknown variable: {var_name} "
                    f"[{node.source_line}:{node.source_col}]")
        else:
            expr_val = self.visit(node.expression, builder, module)
            if isinstance(expr_val.type, ir.PointerType):
                self._cast_runtime_free(builder, module, expr_val, "<expression>")
        return None

    def _cast_ffree(self, builder, module, heap_ptr, var_name):
        """Emit a call to ffree for a heap-allocated variable."""
        _FFREE_MANGLED = (
            'standard__memory__allocators__stdheap__ffree'
            '__1__dataE1_ubits64__ret_voidE1'
        )
        i64_ty = ir.IntType(64)
        ffree_fn = module.globals.get(_FFREE_MANGLED)
        if ffree_fn is None:
            for gname, gval in module.globals.items():
                if gname.endswith('ffree') and isinstance(gval, ir.Function):
                    ffree_fn = gval
                    break
        if ffree_fn is None:
            ffree_ty = ir.FunctionType(ir.VoidType(), [i64_ty])
            ffree_fn = ir.Function(module, ffree_ty, name=_FFREE_MANGLED)
        # ffree takes a u64 address
        addr = builder.ptrtoint(heap_ptr, i64_ty, name=f"{var_name}_freeaddr")
        builder.call(ffree_fn, [addr])

    def _cast_runtime_free(self, builder, module, ptr_value, var_name):
        i8_ptr = ir.PointerType(ir.IntType(8))
        void_ptr = builder.bitcast(ptr_value, i8_ptr, name=f"{var_name}_void_ptr") if ptr_value.type != i8_ptr else ptr_value
        is_windows = SymbolTable.is_macro_defined(module, '__WINDOWS__')
        is_linux   = SymbolTable.is_macro_defined(module, '__LINUX__')
        is_macos   = SymbolTable.is_macro_defined(module, '__MACOS__')
        if is_windows:
            asm_code = "\n                movq %rcx, %r10\n                movl $$0x1E, %eax\n                syscall\n            "
            constraints = "r,~{rax},~{r10},~{r11},~{memory}"
        elif is_linux:
            asm_code = "\n                movq $$11, %rax\n                syscall\n            "
            constraints = "r,~{rax},~{r11},~{memory}"
        elif is_macos:
            asm_code = "\n                movq $$0x2000049, %rax\n                syscall\n            "
            constraints = "r,~{rax},~{memory}"
        else:
            return
        asm_type = ir.FunctionType(ir.VoidType(), [i8_ptr])
        builder.call(ir.InlineAsm(asm_type, asm_code, constraints, side_effect=True), [void_ptr])

    def visit_TernaryOp(self, node, builder, module):
        _check_not_string_literal(node.condition, 'ternary condition', module)
        cond_val = self.visit(node.condition, builder, module)
        cond_val = _coerce_to_bool(builder, cond_val)
        func = builder.block.function
        true_block  = func.append_basic_block('ternary_true')
        false_block = func.append_basic_block('ternary_false')
        merge_block = func.append_basic_block('ternary_merge')
        builder.cbranch(cond_val, true_block, false_block)

        builder.position_at_start(true_block)
        true_val = self.visit(node.true_expr, builder, module)
        true_end_block = builder.block
        if not builder.block.is_terminated:
            builder.branch(merge_block)

        builder.position_at_start(false_block)
        false_val = self.visit(node.false_expr, builder, module)
        false_end_block = builder.block
        if not builder.block.is_terminated:
            builder.branch(merge_block)

        builder.position_at_start(merge_block)

        def _load_branch(val, end_block, target_type):
            """Re-open end_block, load val as target_type, re-emit branch to merge_block."""
            term = end_block.terminator
            if term is not None:
                end_block.instructions.remove(term)
                end_block.terminator = None
            builder.position_at_end(end_block)
            loaded = builder.load(val, name='ternary_load')
            builder.branch(merge_block)
            builder.position_at_start(merge_block)
            return loaded

        if true_val.type != false_val.type:
            true_is_ptr  = isinstance(true_val.type,  ir.PointerType)
            false_is_ptr = isinstance(false_val.type, ir.PointerType)

            # Case 1: one branch is a pointer to exactly the type the other branch
            # produced by value.  This covers struct member accesses (which the
            # identifier visitor returns as a pointer) mixed with by-value returns
            # such as `hit.front ? tri.normal : vec3_negate(tri.normal)`.
            if true_is_ptr and true_val.type.pointee == false_val.type:
                true_val = _load_branch(true_val, true_end_block, false_val.type)
            elif false_is_ptr and false_val.type.pointee == true_val.type:
                false_val = _load_branch(false_val, false_end_block, true_val.type)

            # Case 2: both are pointers — array decay and same-struct bitcast
            elif true_is_ptr and false_is_ptr:
                def _decay(val, end_block):
                    pt = val.type.pointee
                    if isinstance(pt, ir.ArrayType):
                        elem_ptr = ir.PointerType(pt.element)
                        term = end_block.terminator
                        builder.position_before(term) if term else builder.position_at_end(end_block)
                        return builder.bitcast(val, elem_ptr, name='ternary_decay')
                    return val
                true_val  = _decay(true_val,  true_end_block)
                false_val = _decay(false_val, false_end_block)
                if true_val.type != false_val.type:
                    same_struct = (
                        isinstance(true_val.type.pointee,  ir.IdentifiedStructType) and
                        isinstance(false_val.type.pointee, ir.IdentifiedStructType) and
                        str(true_val.type.pointee) == str(false_val.type.pointee)
                    )
                    if not same_struct:
                        term = false_end_block.terminator
                        builder.position_before(term) if term else builder.position_at_end(false_end_block)
                        false_val = builder.bitcast(false_val, true_val.type, name='ternary_cast')
                builder.position_at_start(merge_block)

            # Case 3: scalar pointer vs value (non-struct) — load the pointer side
            elif true_is_ptr and isinstance(true_val.type.pointee, (ir.IntType, ir.FloatType, ir.DoubleType)):
                true_val = _load_branch(true_val, true_end_block, true_val.type.pointee)
            elif false_is_ptr and isinstance(false_val.type.pointee, (ir.IntType, ir.FloatType, ir.DoubleType)):
                false_val = _load_branch(false_val, false_end_block, false_val.type.pointee)

            # Case 4: integer widening
            elif isinstance(true_val.type, ir.IntType) and isinstance(false_val.type, ir.IntType):
                if true_val.type.width < false_val.type.width:
                    builder.position_at_end(true_end_block)
                    term = true_end_block.terminator
                    if term is not None:
                        true_end_block.instructions.remove(term)
                        true_end_block.terminator = None
                    true_val = builder.sext(true_val, false_val.type)
                    builder.branch(merge_block)
                    builder.position_at_start(merge_block)
                elif false_val.type.width < true_val.type.width:
                    builder.position_at_end(false_end_block)
                    term = false_end_block.terminator
                    if term is not None:
                        false_end_block.instructions.remove(term)
                        false_end_block.terminator = None
                    false_val = builder.sext(false_val, true_val.type)
                    builder.branch(merge_block)
                    builder.position_at_start(merge_block)

            else:
                raise TypeError(
                    f"Ternary operator branches have incompatible types: "
                    f"{true_val.type} vs {false_val.type} [{node.source_line}:{node.source_col}]")

        phi = builder.phi(true_val.type, name='ternary_result')
        phi.add_incoming(true_val,  true_end_block)
        phi.add_incoming(false_val, false_end_block)
        return phi

    def visit_NullCoalesce(self, node, builder, module):
        left_val = self.visit(node.left, builder, module)
        if isinstance(left_val.type, ir.PointerType):
            is_null = builder.icmp_unsigned('==', left_val, ir.Constant(left_val.type, None), name='is_null')
        elif isinstance(left_val.type, ir.IntType):
            is_null = builder.icmp_signed('==', left_val, ir.Constant(left_val.type, 0), name='is_zero')
        else:
            raise TypeError(
                f"Null coalesce not supported for type: {left_val.type} "
                f"[{node.source_line}:{node.source_col}]")
        func = builder.block.function
        right_block = func.append_basic_block('coalesce_right')
        merge_block = func.append_basic_block('coalesce_merge')
        left_block  = builder.block
        builder.cbranch(is_null, right_block, merge_block)
        builder.position_at_start(right_block)
        right_val = self.visit(node.right, builder, module)
        right_end_block = builder.block
        builder.branch(merge_block)
        builder.position_at_start(merge_block)
        if left_val.type != right_val.type:
            if isinstance(left_val.type, ir.IntType) and isinstance(right_val.type, ir.IntType):
                if left_val.type.width < right_val.type.width:
                    builder.position_at_end(left_block)
                    left_val = builder.sext(left_val, right_val.type)
                    builder.branch(merge_block)
                    builder.position_at_start(merge_block)
                elif right_val.type.width < left_val.type.width:
                    builder.position_at_end(right_end_block)
                    right_val = builder.sext(right_val, left_val.type)
                    builder.branch(merge_block)
                    builder.position_at_start(merge_block)
            else:
                raise TypeError(
                    f"Null coalesce operands have incompatible types: "
                    f"{left_val.type} vs {right_val.type} [{node.source_line}:{node.source_col}]")
        phi = builder.phi(left_val.type, name='coalesce_result')
        phi.add_incoming(left_val,  left_block)
        phi.add_incoming(right_val, right_end_block)
        return phi

    def visit_NotNull(self, node, builder, module):
        # Evaluate the operand unconditionally — no branches needed, this is
        # a pure comparison that folds into a single LLVM instruction.
        val = self.visit(node.operand, builder, module)

        i8 = ir.IntType(8)

        if isinstance(val.type, ir.PointerType):
            # Pointer: icmp ne ptr, null  -> i1, then zext to i8
            null = ir.Constant(val.type, None)
            cmp  = builder.icmp_unsigned('!=', val, null, name='not_null')
        elif isinstance(val.type, ir.IntType):
            # Integer / bool / data-width value: icmp ne val, 0  -> i1, then zext to i8
            zero = ir.Constant(val.type, 0)
            cmp  = builder.icmp_signed('!=', val, zero, name='not_zero')
        elif isinstance(val.type, (ir.FloatType, ir.DoubleType)):
            # Float: fcmp one val, 0.0  (ordered, not-equal — false on NaN)  -> i1, zext to i8
            zero = ir.Constant(val.type, 0.0)
            cmp  = builder.fcmp_ordered('!=', val, zero, name='not_zero_f')
        else:
            raise TypeError(
                f"'!?' operator not supported for type {val.type} "
                f"[{node.source_line}:{node.source_col}]")

        # Widen i1 -> i8 so the result is a usable bool-width integer that
        # can be stored, compared, or passed without further extension.
        return builder.zext(cmp, i8, name='not_null_result')

    def visit_BitSlice(self, node, builder, module):
        val       = self.visit(node.value, builder, module)
        start_val = self.visit(node.start, builder, module)
        end_val   = self.visit(node.end,   builder, module)
        zero32 = ir.Constant(ir.IntType(32), 0)
        i8  = ir.IntType(8)
        i32 = ir.IntType(32)

        s_const      = int(start_val.constant) if hasattr(start_val, 'constant') else None
        e_const_rev  = int(end_val.constant)   if hasattr(end_val,   'constant') else None

        # Reverse bit slice
        if s_const is not None and e_const_rev is not None and s_const > e_const_rev:
            if isinstance(val.type, ir.PointerType) and isinstance(val.type.pointee, ir.ArrayType):
                rev_base = val
                def rev_gep(bidx): return builder.gep(rev_base, [zero32, ir.Constant(i32, bidx)], inbounds=True)
            elif isinstance(val.type, ir.PointerType) and isinstance(val.type.pointee, (ir.LiteralStructType, ir.IdentifiedStructType)):
                rev_base = builder.bitcast(val, ir.PointerType(i8), name="rev_struct_raw")
                def rev_gep(bidx): return builder.gep(rev_base, [ir.Constant(i32, bidx)], inbounds=True)
            elif isinstance(val.type, (ir.LiteralStructType, ir.IdentifiedStructType)):
                tmp = builder.alloca(val.type, name="rev_stmp"); builder.store(val, tmp)
                rev_base = builder.bitcast(tmp, ir.PointerType(i8), name="rev_struct_raw")
                def rev_gep(bidx): return builder.gep(rev_base, [ir.Constant(i32, bidx)], inbounds=True)
            elif isinstance(val.type, ir.IntType) and val.type.width >= 8:
                nbytes = val.type.width // 8
                tmp = builder.alloca(ir.ArrayType(i8, nbytes), name="rev_tmp")
                i8ptr = builder.bitcast(tmp, ir.PointerType(i8), name="rev_tmp_i8")
                wval = builder.zext(val, i32) if val.type.width < 32 else val
                for bi in range(nbytes):
                    sh = (nbytes - 1 - bi) * 8
                    bv = builder.trunc(builder.lshr(wval, ir.Constant(wval.type, sh)), i8)
                    builder.store(bv, builder.gep(i8ptr, [ir.Constant(i32, bi)], inbounds=True))
                rev_base = i8ptr
                def rev_gep(bidx): return builder.gep(rev_base, [ir.Constant(i32, bidx)], inbounds=True)
            else:
                tmp = builder.alloca(i8, name="rev_tmp")
                builder.store(val if val.type == i8 else builder.trunc(val, i8), tmp)
                rev_base = tmp
                def rev_gep(bidx): return builder.gep(rev_base, [ir.Constant(i32, bidx)], inbounds=True)
            num_bits = s_const - e_const_rev + 1
            result = ir.Constant(i8, 0)
            for i, bit_pos in enumerate(range(s_const, e_const_rev - 1, -1)):
                byte_i = bit_pos // 8; bit_in_byte = bit_pos % 8
                bval = builder.load(rev_gep(byte_i), name=f"rev_byte_{i}")
                extracted = builder.and_(
                    builder.lshr(bval, ir.Constant(i8, 7 - bit_in_byte), name=f"rev_ext_{i}"),
                    ir.Constant(i8, 1), name=f"rev_bit_{i}")
                placed = builder.shl(extracted, ir.Constant(i8, num_bits - 1 - i), name=f"rev_place_{i}")
                result = builder.or_(result, placed, name=f"rev_acc_{i}")
            if 1 <= num_bits < 8:
                return builder.trunc(result, ir.IntType(num_bits), name="rev_trunc")
            return result

        # Forward bit slice — build base_ptr.
        # Flux bit addressing is MSB-first (bit 0 = MSB of the whole value).
        # Fields are in declaration order (field 0 = most significant bits), but each
        # field's bytes are little-endian on x86. For struct types we build a flat staging
        # buffer where every field's bytes are written big-endian so that
        # byte_idx = bit_idx // 8 and shift = 7 - (bit_idx % 8) work correctly.
        def _build_msb_struct_buf(struct_type, struct_ptr):
            elements = getattr(struct_type, 'elements', None) or []
            field_sizes = []
            for el in elements:
                bits = SizeOfTypeHandler.bits_from_llvm_type(el, module)
                field_sizes.append((bits or 8) // 8)
            total = sum(field_sizes)
            buf   = builder.alloca(ir.ArrayType(i8, total), name="bs_msb_buf")
            i8buf = builder.bitcast(buf, ir.PointerType(i8), name="bs_msb_i8")
            offset = 0
            for fi, (el, nbytes) in enumerate(zip(elements, field_sizes)):
                fptr = builder.gep(struct_ptr, [ir.Constant(i32, 0), ir.Constant(i32, fi)],
                                   inbounds=True, name=f"bs_fptr_{fi}")
                if isinstance(el, ir.IntType) and el.width >= 8:
                    fval = builder.load(fptr, name=f"bs_fval_{fi}")
                    wty  = fval.type if fval.type.width >= 32 else ir.IntType(32)
                    wval = builder.zext(fval, wty) if fval.type.width < 32 else fval
                    for bi in range(nbytes):
                        sh   = (nbytes - 1 - bi) * 8
                        bval = builder.trunc(
                            builder.lshr(wval, ir.Constant(wty, sh), name=f"bs_fsh_{fi}_{bi}"),
                            i8, name=f"bs_fb_{fi}_{bi}")
                        bptr = builder.gep(i8buf, [ir.Constant(i32, offset + bi)],
                                           inbounds=True, name=f"bs_fbptr_{fi}_{bi}")
                        builder.store(bval, bptr)
                else:
                    fsrc = builder.bitcast(fptr, ir.PointerType(i8))
                    for bi in range(nbytes):
                        bval = builder.load(
                            builder.gep(fsrc, [ir.Constant(i32, bi)], inbounds=True))
                        builder.store(bval,
                            builder.gep(i8buf, [ir.Constant(i32, offset + bi)], inbounds=True))
                offset += nbytes
            return i8buf

        if isinstance(val.type, ir.PointerType) and isinstance(val.type.pointee, ir.ArrayType):
            base_ptr = val
        elif isinstance(val.type, ir.PointerType) and isinstance(val.type.pointee, (ir.LiteralStructType, ir.IdentifiedStructType)):
            base_ptr = _build_msb_struct_buf(val.type.pointee, val)
        elif isinstance(val.type, ir.PointerType):
            base_ptr = val
        elif isinstance(val.type, (ir.LiteralStructType, ir.IdentifiedStructType)):
            tmp = builder.alloca(val.type, name="bs_tmp"); builder.store(val, tmp)
            base_ptr = _build_msb_struct_buf(val.type, tmp)
        elif isinstance(val.type, ir.ArrayType):
            tmp = builder.alloca(val.type, name="bs_tmp"); builder.store(val, tmp); base_ptr = tmp
        elif isinstance(val.type, ir.IntType) and val.type.width >= 8:
            nbytes = val.type.width // 8
            tmp = builder.alloca(ir.ArrayType(i8, nbytes), name="bs_tmp")
            i8ptr = builder.bitcast(tmp, ir.PointerType(i8), name="bs_tmp_i8")
            wval = val
            if val.type.width < 32:   wval = builder.zext(val, i32, name="bs_widen")
            elif val.type.width > 64: wval = builder.trunc(val, ir.IntType(64), name="bs_widen")
            wty = wval.type
            for byte_i in range(nbytes):
                shift = (nbytes - 1 - byte_i) * 8
                shifted = builder.lshr(wval, ir.Constant(wty, shift), name=f"bs_byteshift_{byte_i}")
                bval = builder.trunc(shifted, i8, name=f"bs_byte_{byte_i}")
                bptr = builder.gep(i8ptr, [ir.Constant(i32, byte_i)], inbounds=True, name=f"bs_bptr_{byte_i}")
                builder.store(bval, bptr)
            base_ptr = i8ptr
        elif isinstance(val.type, ir.IntType):
            widened = builder.zext(val, i8, name="bs_widen")
            aligned = builder.shl(widened, ir.Constant(i8, 8 - val.type.width), name="bs_prealign")
            tmp = builder.alloca(i8, name="bs_tmp"); builder.store(aligned, tmp); base_ptr = tmp
        else:
            raise ValueError(
                f"Bit-slice operator `` requires array/pointer operand, got {val.type} "
                f"[{node.source_line}:{node.source_col}]")

        def to_i32(v, name):
            if isinstance(v.type, ir.IntType):
                if v.type.width < 32: return builder.zext(v, i32, name=name)
                if v.type.width > 32: return builder.trunc(v, i32, name=name)
                return v
            raise ValueError(
                f"Bit-slice indices must be integers [{node.source_line}:{node.source_col}]")



        start_i32 = to_i32(start_val, "bs_start")
        end_i32   = to_i32(end_val,   "bs_end")
        eight     = ir.Constant(i32, 8)
        byte_idx  = builder.udiv(start_i32, eight, name="bs_byte_idx")
        bit_start = builder.urem(start_i32, eight, name="bs_bit_start")
        bit_end   = builder.urem(end_i32,   eight, name="bs_bit_end")

        if isinstance(base_ptr.type.pointee, ir.ArrayType):
            byte_ptr = builder.gep(base_ptr, [zero32, byte_idx], inbounds=True, name="bs_byte_ptr")
        else:
            byte_ptr = builder.gep(base_ptr, [byte_idx], inbounds=True, name="bs_byte_ptr")
        byte_val     = builder.load(byte_ptr, name="bs_byte")
        bit_end_i8   = builder.trunc(bit_end,   i8, name="bs_bit_end_i8")
        bit_start_i8 = builder.trunc(bit_start, i8, name="bs_bit_start_i8")
        # MSB-first within each byte: bit N%8==0 is MSB, so shift right by (7 - bit_end)
        # to place the LSB of the slice at position 0, then mask.
        shift_amt    = builder.sub(ir.Constant(i8, 7), bit_end_i8, name="bs_shift_amt")
        shifted      = builder.lshr(byte_val, shift_amt, name="bs_shift")
        slice_w      = builder.add(builder.sub(bit_end_i8, bit_start_i8, name="bs_slen"),
                                   ir.Constant(i8, 1), name="bs_swidth")
        mask_raw     = builder.shl(ir.Constant(i8, 1), slice_w, name="bs_mask_raw")
        mask         = builder.sub(mask_raw, ir.Constant(i8, 1), name="bs_mask")
        masked       = builder.and_(shifted, mask, name="bs_result")
        try:
            sc = int(start_i32.constant) if hasattr(start_i32, 'constant') else None
            ec = int(end_i32.constant)   if hasattr(end_i32,   'constant') else None
            if sc is not None and ec is not None:
                width = (ec % 8) - (sc % 8) + 1
                if 1 <= width <= 8:
                    return builder.trunc(masked, ir.IntType(width), name="bs_trunc")
        except Exception:
            pass
        return masked

    def visit_VariadicAccess(self, node, builder, module):
        va_list_alloca = getattr(builder, '_flux_va_list', None)
        if va_list_alloca is None:
            raise RuntimeError(
                f"...[N] used outside of a variadic function "
                f"[{node.source_line}:{node.source_col}]")
        va_list_i8ptr = getattr(builder, '_flux_va_list_i8ptr')
        index_val = self.visit(node.index, builder, module)
        if isinstance(index_val.type, ir.IntType) and index_val.type.width != 32:
            index_val = (builder.trunc(index_val, ir.IntType(32), name="va_idx_trunc")
                         if index_val.type.width > 32
                         else builder.sext(index_val, ir.IntType(32), name="va_idx_ext"))
        va_list_type = ir.ArrayType(ir.IntType(8).as_pointer(), 1)
        va_copy_list = builder.alloca(va_list_type, name="va_copy")
        va_copy_i8ptr = builder.bitcast(va_copy_list, ir.IntType(8).as_pointer(), name="va_copy_ptr")
        va_copy_fn_type = ir.FunctionType(ir.VoidType(), [ir.IntType(8).as_pointer(), ir.IntType(8).as_pointer()])
        if 'llvm.va_copy' not in module.globals:
            va_copy_fn = ir.Function(module, va_copy_fn_type, 'llvm.va_copy')
        else:
            va_copy_fn = module.globals['llvm.va_copy']
        builder.call(va_copy_fn, [va_copy_i8ptr, va_list_i8ptr])
        va_end_fn_type = ir.FunctionType(ir.VoidType(), [ir.IntType(8).as_pointer()])
        if 'llvm.va_end' not in module.globals:
            va_end_fn = ir.Function(module, va_end_fn_type, 'llvm.va_end')
        else:
            va_end_fn = module.globals['llvm.va_end']
        arg_type = ir.IntType(64)
        result_alloca = builder.alloca(arg_type, name="va_result")
        current_fn = builder.block.parent
        loop_init_bb = current_fn.append_basic_block(name="va_loop_init")
        loop_cond_bb = current_fn.append_basic_block(name="va_loop_cond")
        loop_body_bb = current_fn.append_basic_block(name="va_loop_body")
        loop_end_bb  = current_fn.append_basic_block(name="va_loop_end")
        merge_bb     = current_fn.append_basic_block(name="va_merge")
        builder.branch(loop_init_bb)
        with builder.goto_block(loop_init_bb):
            counter_alloca = builder.alloca(ir.IntType(32), name="va_counter")
            builder.store(ir.Constant(ir.IntType(32), 0), counter_alloca)
            builder.branch(loop_cond_bb)
        with builder.goto_block(loop_cond_bb):
            counter_val = builder.load(counter_alloca, name="va_cnt_load")
            cond = builder.icmp_signed('<', counter_val, index_val, name="va_cond")
            builder.cbranch(cond, loop_body_bb, loop_end_bb)
        with builder.goto_block(loop_body_bb):
            _emit_va_arg(builder, va_copy_i8ptr, arg_type, name="va_discard")
            cnt = builder.load(counter_alloca, name="va_cnt_inc_load")
            builder.store(builder.add(cnt, ir.Constant(ir.IntType(32), 1), name="va_cnt_inc"), counter_alloca)
            builder.branch(loop_cond_bb)
        with builder.goto_block(loop_end_bb):
            result_val = _emit_va_arg(builder, va_copy_i8ptr, arg_type, name="va_result_val")
            builder.store(result_val, result_alloca)
            builder.call(va_end_fn, [va_copy_i8ptr])
            builder.branch(merge_bb)
        builder.position_at_end(merge_bb)
        return builder.load(result_alloca, name="va_arg_result")

    def visit_InlineAsm(self, node, builder, module):
        import re
        asm_lines = [l for l in node.body.split('\n')
                     if l.strip() and not l.strip().startswith('//')]
        asm = '\n'.join(asm_lines)
        output_operands, input_operands = [], []
        output_constraints, input_constraints, clobber_list = [], [], []
        if node.constraints:
            parts = node.constraints.split(':')
            while len(parts) < 3:
                parts.append('')
            output_part = parts[0].strip()
            if output_part:
                for constraint, var_name in re.findall(r'"([^"]+)"\s*\(([^)]+)\)', output_part):
                    if module.symbol_table.get_llvm_value(var_name) is not None:
                        output_operands.append(module.symbol_table.get_llvm_value(var_name))
                    elif var_name in module.globals:
                        output_operands.append(module.globals[var_name])
                    output_constraints.append(constraint)
            input_part = parts[1].strip()
            if input_part:
                for constraint, var_name in re.findall(r'"([^"]+)"\s*\(([^)]+)\)', input_part):
                    if module.symbol_table.get_llvm_value(var_name) is not None:
                        var_ptr = module.symbol_table.get_llvm_value(var_name)
                        if constraint == 'm' or (isinstance(var_ptr.type, ir.PointerType) and isinstance(var_ptr.type.pointee, ir.ArrayType)):
                            input_operands.append(var_ptr)
                        else:
                            input_operands.append(builder.load(var_ptr, name=f"{var_name}_load"))
                    elif var_name in module.globals:
                        var_ptr = module.globals[var_name]
                        if constraint == 'm' or isinstance(var_ptr.type.pointee, ir.ArrayType):
                            input_operands.append(var_ptr)
                        else:
                            input_operands.append(builder.load(var_ptr, name=f"{var_name}_load"))
                    input_constraints.append(constraint)
            clobber_part = parts[2].strip()
            if clobber_part:
                clobber_list = re.findall(r'"([^"]+)"', clobber_part)
        final_input_operands = input_operands[:]
        final_constraints    = input_constraints[:]
        for output_op, output_constraint in zip(output_operands, output_constraints):
            if output_constraint.startswith('=m'):
                final_input_operands.insert(0, output_op)
                final_constraints.insert(0, output_constraint.replace('=m', '+m'))
            else:
                final_constraints.insert(0, output_constraint)
        final_constraints.extend(f"~{{{c}}}" for c in clobber_list)
        constraint_str = ','.join(final_constraints)
        input_types = [op.type for op in final_input_operands]
        has_reg_out = any(c.startswith(('=r', '=a', '=b')) for c in output_constraints)
        if has_reg_out and output_operands:
            out_type = output_operands[0].type
            if isinstance(out_type, ir.PointerType):
                out_type = out_type.pointee
            fn_type = ir.FunctionType(out_type, input_types)
        else:
            fn_type = ir.FunctionType(ir.VoidType(), input_types)
        inline_asm = ir.InlineAsm(fn_type, asm, constraint_str, node.is_volatile)
        result = builder.call(inline_asm, final_input_operands)
        if has_reg_out and output_operands:
            builder.store(result, output_operands[0])
        return result

    def visit_ArrayLiteral(self, node, builder, module):
        if node.is_string:
            return self._array_literal_string(node, builder, module)
        return self._array_literal_array(node, builder, module)

    def _array_literal_string(self, node, builder, module):
        from fast import ArrayLiteral
        if node.string_value is None:
            return self._array_literal_array(node, builder, module)
        import fconfig as _fconfig
        _null_terminate = _fconfig.config.get('null_terminate_strings', '0').strip() == '1'
        string_value = node.string_value
        if _null_terminate and (not string_value or string_value[-1] != '\0'):
            string_value += '\0'
        string_bytes = string_value.encode('ascii')
        str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
        str_val = ir.Constant(str_array_ty, bytearray(string_bytes))
        use_global = (
            node.storage_class == StorageClass.GLOBAL or
            module.symbol_table.is_global_scope()
        )
        use_heap   = node.storage_class == StorageClass.HEAP
        use_stack  = (
            node.storage_class in (StorageClass.STACK, StorageClass.LOCAL) or
            (not module.symbol_table.is_global_scope() and not use_global and not use_heap)
        )
        if use_heap:
            return heap_array_allocation(builder, module, str_val)   # deliberately unresolved; mirrors original
        if use_global or not use_stack:
            str_name = f".str.{id(node)}"
            gv = ir.GlobalVariable(module, str_val.type, name=str_name)
            gv.linkage = 'internal'; gv.global_constant = True; gv.initializer = str_val
            zero = ir.Constant(ir.IntType(32), 0)
            return builder.gep(gv, [zero, zero], inbounds=True, name="str_ptr")
        stack_alloca = builder.alloca(str_array_ty, name="str_stack")
        for i, byte_val in enumerate(string_bytes):
            zero = ir.Constant(ir.IntType(32), 0)
            elem_ptr = builder.gep(stack_alloca, [zero, ir.Constant(ir.IntType(32), i)], name=f"str_char_{i}")
            builder.store(ir.Constant(ir.IntType(8), byte_val), elem_ptr)
        zero = ir.Constant(ir.IntType(32), 0)
        return builder.gep(stack_alloca, [zero, zero], inbounds=True, name="str_ptr")

    def _array_literal_array(self, node, builder, module):
        from fast import StringLiteral, ArrayLiteral
        from ftypesys import find_common_type, cast_to_type
        if not node.elements:
            if node.element_type:
                element_llvm_type = TypeSystem.get_llvm_type(node.element_type, module)
                array_type = ir.ArrayType(element_llvm_type, 0)
                if module.symbol_table.is_global_scope():
                    gvar = ir.GlobalVariable(module, array_type, name=f".empty_array.{id(node)}")
                    gvar.linkage = 'internal'; gvar.global_constant = True
                    gvar.initializer = ir.Constant(array_type, [])
                    return gvar
                return builder.alloca(array_type, name="empty_array")
            raise ValueError(
                f"Cannot create empty array without element type [{node.source_line}:{node.source_col}]")
        element_values = []
        element_types = set()
        for elem in node.elements:
            if isinstance(elem, StringLiteral):
                if node.element_type:
                    target_type = TypeSystem.get_llvm_type(node.element_type, module)
                else:
                    target_type = ir.IntType(32)
                if isinstance(target_type, ir.IntType):
                    string_val = elem.value
                    byte_count = min(len(string_val), target_type.width // 8)
                    packed_value = 0
                    for j in range(byte_count):
                        packed_value |= (ord(string_val[j]) << (j * 8))
                    elem_val = ir.Constant(target_type, packed_value)
                else:
                    elem_val = self.visit(elem, builder, module)
            else:
                # Propagate struct type context into StructLiteral elements so that
                # bare struct literals inside array initialisers (e.g. POINT[] v = [{1,2}])
                # have the required type context when visit_StructLiteral is called.
                from fast import StructLiteral as _StructLiteral
                if (isinstance(elem, _StructLiteral) and
                        getattr(elem, 'struct_type', None) is None and
                        node.element_type is not None):
                    ctn = getattr(node.element_type, 'custom_typename', None)
                    if ctn:
                        elem.struct_type = ctn
                elem_val = self.visit(elem, builder, module)
            if node.element_type is not None:
                target_elem_llvm = TypeSystem.get_llvm_type(node.element_type, module)
                if isinstance(target_elem_llvm, ir.IntType) and isinstance(elem_val.type, ir.IntType):
                    if elem_val.type.width > target_elem_llvm.width:
                        elem_val = (ir.Constant(target_elem_llvm, elem_val.constant & ((1 << target_elem_llvm.width) - 1))
                                    if isinstance(elem_val, ir.Constant)
                                    else builder.trunc(elem_val, target_elem_llvm, name="elem_trunc"))
                    elif elem_val.type.width < target_elem_llvm.width:
                        elem_val = (ir.Constant(target_elem_llvm, elem_val.constant)
                                    if isinstance(elem_val, ir.Constant)
                                    else builder.zext(elem_val, target_elem_llvm, name="elem_zext"))
            element_values.append(elem_val)
            element_types.add(elem_val.type)
        if len(element_types) == 1:
            element_type = next(iter(element_types))
        else:
            element_type = find_common_type(list(element_types))
            for i in range(len(element_values)):
                if element_values[i].type != element_type:
                    element_values[i] = cast_to_type(builder, element_values[i], element_type)
        array_type = ir.ArrayType(element_type, len(element_values))
        if module.symbol_table.is_global_scope() or all(isinstance(v, ir.Constant) for v in element_values):
            const_elements = [v if isinstance(v, ir.Constant) else ir.Constant(element_type, 0) for v in element_values]
            const_array = ir.Constant(array_type, const_elements)
            if module.symbol_table.is_global_scope():
                gvar = ir.GlobalVariable(module, array_type, name=f".array_literal.{id(node)}")
                gvar.linkage = 'internal'; gvar.global_constant = True; gvar.initializer = const_array
                gvar.type._is_array_pointer = True
                return gvar
            alloca = builder.alloca(array_type, name="array_literal_const")
            builder.store(const_array, alloca)
            alloca.type._is_array_pointer = True
            return alloca
        alloca = builder.alloca(array_type, name="array_literal")
        zero = ir.Constant(ir.IntType(32), 0)
        for i, elem_val in enumerate(element_values):
            elem_ptr = builder.gep(alloca, [zero, ir.Constant(ir.IntType(32), i)], inbounds=True, name=f"elem_{i}")
            builder.store(elem_val, elem_ptr)
        alloca.type._is_array_pointer = True
        return alloca

    def visit_ArrayComprehension(self, node, builder, module, expected_size=None):
        from fast import ArrayLiteral, RangeExpression, Literal
        element_type = LiteralTypeHandler.resolve_comprehension_element_type(node.variable_type, module)
        if isinstance(node.iterable, ArrayLiteral):
            iterable_elements = node.iterable.elements
            num_elements = len(iterable_elements)
            array_type = ir.ArrayType(element_type, num_elements)
            array_ptr = builder.alloca(array_type, name="comprehension_array")
            iterable_array_ptr = builder.alloca(array_type, name="iterable_array")
            for i, elem_expr in enumerate(iterable_elements):
                elem_val = self.visit(elem_expr, builder, module)
                elem_val = LiteralTypeHandler.cast_to_target_int_type(builder, elem_val, element_type)
                elem_ptr = builder.gep(iterable_array_ptr, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)])
                builder.store(elem_val, elem_ptr)
            var_ptr = builder.alloca(element_type, name=node.variable)
            module.symbol_table.define(node.variable, SymbolKind.VARIABLE, llvm_value=var_ptr)
            index_ptr = builder.alloca(ir.IntType(32), name="comp_index")
            builder.store(ir.Constant(ir.IntType(32), 0), index_ptr)
            func = builder.block.function
            loop_cond = func.append_basic_block('comp_loop_cond')
            loop_body = func.append_basic_block('comp_loop_body')
            loop_end  = func.append_basic_block('comp_loop_end')
            builder.branch(loop_cond)
            builder.position_at_start(loop_cond)
            current_index = builder.load(index_ptr)
            cond = builder.icmp_signed('<', current_index, ir.Constant(ir.IntType(32), num_elements))
            builder.cbranch(cond, loop_body, loop_end)
            builder.position_at_start(loop_body)
            elem_ptr = builder.gep(iterable_array_ptr, [ir.Constant(ir.IntType(32), 0), current_index])
            builder.store(builder.load(elem_ptr), var_ptr)
            expr_val = self.visit(node.expression, builder, module)
            expr_val = LiteralTypeHandler.cast_to_target_int_type(builder, expr_val, element_type)
            result_elem_ptr = builder.gep(array_ptr, [ir.Constant(ir.IntType(32), 0), current_index])
            builder.store(expr_val, result_elem_ptr)
            builder.store(builder.add(current_index, ir.Constant(ir.IntType(32), 1)), index_ptr)
            builder.branch(loop_cond)
            builder.position_at_start(loop_end)
            return array_ptr
        elif isinstance(node.iterable, RangeExpression):
            # Pass element_type through to visit_RangeExpression
            self.visit_RangeExpression(node.iterable, builder, module, element_type)
            start_val = self.visit(node.iterable.start, builder, module)
            end_val   = self.visit(node.iterable.end,   builder, module)
            start_val_sized = LiteralTypeHandler.cast_to_target_int_type(builder, start_val, element_type)
            end_val_sized   = LiteralTypeHandler.cast_to_target_int_type(builder, end_val,   element_type)
            if isinstance(node.iterable.start, Literal) and isinstance(node.iterable.end, Literal):
                actual_size = int(node.iterable.end.value) - int(node.iterable.start.value) + 1
                array_type = ir.ArrayType(element_type, actual_size)
                array_ptr  = builder.alloca(array_type, name="comprehension_array")
            elif expected_size is not None:
                array_type = ir.ArrayType(element_type, expected_size)
                array_ptr  = builder.alloca(array_type, name="comprehension_array")
            else:
                raise NotImplementedError(
                    f"Array comprehensions with runtime-determined ranges require an explicit array size "
                    f"[{node.source_line}:{node.source_col}]")
            index_ptr = builder.alloca(ir.IntType(32), name="comp_index")
            builder.store(ir.Constant(ir.IntType(32), 0), index_ptr)
            var_ptr = builder.alloca(element_type, name=node.variable)
            module.symbol_table.define(node.variable, SymbolKind.VARIABLE, llvm_value=var_ptr)
            start_val = LiteralTypeHandler.cast_to_target_int_type(builder, start_val, element_type)
            end_val   = LiteralTypeHandler.cast_to_target_int_type(builder, end_val,   element_type)
            func = builder.block.function
            loop_cond = func.append_basic_block('comp_loop_cond')
            loop_body = func.append_basic_block('comp_loop_body')
            loop_end  = func.append_basic_block('comp_loop_end')
            builder.store(start_val, var_ptr)
            builder.branch(loop_cond)
            builder.position_at_start(loop_cond)
            current_var = builder.load(var_ptr, name="current_var")
            builder.cbranch(builder.icmp_signed('<=', current_var, end_val, name="loop_cond"), loop_body, loop_end)
            builder.position_at_start(loop_body)
            expr_val = self.visit(node.expression, builder, module)
            expr_val = LiteralTypeHandler.cast_to_target_int_type(builder, expr_val, element_type)
            current_index = builder.load(index_ptr, name="current_index")
            array_elem_ptr = builder.gep(array_ptr, [ir.Constant(ir.IntType(32), 0), current_index], inbounds=True)
            builder.store(expr_val, array_elem_ptr)
            builder.store(builder.add(current_index, ir.Constant(ir.IntType(32), 1), name="next_index"), index_ptr)
            builder.store(builder.add(current_var, ir.Constant(element_type, 1), name="next_var"), var_ptr)
            builder.branch(loop_cond)
            builder.position_at_start(loop_end)
            return array_ptr
        raise NotImplementedError(
            f"Array comprehension only supports range expressions and array literals "
            f"[{node.source_line}:{node.source_col}]")

    def visit_FStringLiteral(self, node, builder, module):
        from fast import ArrayLiteral, Literal, BinaryOp, UnaryOp, Identifier, SizeOf
        try:
            full_string = ""
            for part in node.parts:
                if isinstance(part, str):
                    clean = part[2:] if part.startswith('f"') else part
                    clean = clean[:-1] if clean.endswith('"') else clean
                    full_string += clean
                else:
                    full_string += str(self._fstring_eval_ct(part, node, builder, module))
            return self.visit(ArrayLiteral.from_string(full_string), builder, module)
        except (ValueError, NotImplementedError):
            return self._fstring_runtime(node, builder, module)

    def _resolve_stringify_name(self, stringify_node, builder, module, parent_node) -> str:
        """Resolve a Stringify node used as a function name to a plain string.

        $X        -> compile-time value of X (if a global integer/bool constant),
                     otherwise the literal identifier name "X".
        $X.member -> "X.member" (same rules for X, dot-joined with member).
        """
        from fast import Identifier as _Identifier
        var_name = stringify_node.name
        resolved = var_name  # default: use the identifier name literally

        # Try to evaluate X as a compile-time constant (mirrors _fstring_eval_ct for Identifier)
        try:
            val = self._fstring_eval_ct(
                _Identifier(var_name), stringify_node, builder, module)
            resolved = str(val)
        except (ValueError, NotImplementedError):
            pass  # Not a known global constant — fall back to the identifier name itself

        if stringify_node.member is not None:
            resolved = f"{resolved}.{stringify_node.member}"

        return resolved

    def _fstring_eval_ct(self, expr, node, builder, module):
        from fast import Literal, BinaryOp, UnaryOp, Identifier, SizeOf, TypeConvertExpression
        if isinstance(expr, Literal):
            if expr.type == DataType.SINT:       return int(expr.value)
            if expr.type == DataType.FLOAT:      return float(expr.value)
            if expr.type == DataType.DOUBLE:     return float(expr.value)
            if expr.type in (DataType.SLONG, DataType.ULONG): return int(expr.value)
            if expr.type == DataType.BOOL:       return bool(expr.value)
            if expr.type == DataType.CHAR:
                return str(expr.value) if isinstance(expr.value, str) else chr(expr.value)
            raise ValueError(f"Cannot convert {expr.type} at compile time")
        if isinstance(expr, BinaryOp):
            l = self._fstring_eval_ct(expr.left,  node, builder, module)
            r = self._fstring_eval_ct(expr.right, node, builder, module)
            ops = {Operator.ADD:l+r, Operator.SUB:l-r, Operator.MUL:l*r, Operator.DIV:l/r,
                   Operator.MOD:l%r, Operator.EQUAL:l==r, Operator.NOT_EQUAL:l!=r,
                   Operator.LESS_THAN:l<r, Operator.LESS_EQUAL:l<=r,
                   Operator.GREATER_THAN:l>r, Operator.GREATER_EQUAL:l>=r}
            if expr.operator not in ops:
                raise NotImplementedError(f"Operator {expr.operator} not supported for compile-time f-string")
            return ops[expr.operator]
        if isinstance(expr, UnaryOp):
            o = self._fstring_eval_ct(expr.operand, node, builder, module)
            if expr.operator == Operator.NOT: return not o
            if expr.operator == Operator.SUB: return -o
            raise NotImplementedError
        if isinstance(expr, Identifier):
            # Try the bare name first, then common type-mangled suffixes used by
            # be32/le32/be64/le64 variables (e.g. "x__be32", "x__le32").
            _TYPED_SUFFIXES = ('__be32', '__le32', '__be64', '__le64',
                               '__be16', '__le16')
            gvar = module.globals.get(expr.name)
            if gvar is None:
                for _sfx in _TYPED_SUFFIXES:
                    gvar = module.globals.get(expr.name + _sfx)
                    if gvar is not None:
                        break
            if gvar is not None and hasattr(gvar, 'initializer') and gvar.initializer is not None:
                init = gvar.initializer
                if hasattr(init, 'constant'):
                    v = init.constant
                    if isinstance(v, (int, float, bool)):
                        return v
                    # byte[N] / char[N] array: constant is a bytearray or list of ints
                    if isinstance(v, (bytearray, bytes)):
                        # Decode as latin-1: every byte value 0x00-0xFF maps 1:1 to a
                        # Unicode code point, so this never raises and preserves raw
                        # byte identity (e.g. 0xC0 -> 'À', not a hex escape).
                        return v.rstrip(b'\x00').decode('latin-1')
                    if isinstance(v, list):
                        # List of ir.Constant elements (e.g. from ArrayType initialiser)
                        parts_ct = []
                        for elem in v:
                            ev = getattr(elem, 'constant', None)
                            if ev is None:
                                break
                            parts_ct.append(ev)
                        else:
                            # All elements resolved — treat as byte array
                            raw = bytes(int(b) & 0xFF for b in parts_ct)
                            # Decode as latin-1 for the same reason as the bytearray
                            # branch above: 1:1 byte→codepoint, never raises.
                            return raw.rstrip(b'\x00').decode('latin-1')
        if isinstance(expr, SizeOf) and isinstance(expr.target, TypeSystem):
            llvm_type = TypeSystem.get_llvm_type(expr.target, module, include_array=True)
            if isinstance(llvm_type, ir.IntType):
                return llvm_type.width // 8
            if isinstance(llvm_type, ir.ArrayType):
                return llvm_type.element.width * llvm_type.count // 8
        if isinstance(expr, TypeConvertExpression):
            inner = self._fstring_eval_ct(expr.expression, node, builder, module)
            # Map the target Flux type to the appropriate Python built-in so the
            # result stays a plain int/float/bool — exactly what the other branches
            # return.  Unknown target types just pass the value through unchanged.
            target = getattr(expr, 'target_type', None)
            if target is not None:
                _UINT_TYPES = {DataType.UINT}
                _SINT_TYPES = {DataType.SINT}
                _FLOAT_TYPES = {DataType.FLOAT, DataType.DOUBLE}
                _BOOL_TYPES  = {DataType.BOOL}
                if hasattr(target, 'base') and target.base in _FLOAT_TYPES:
                    return float(inner)
                if hasattr(target, 'base') and target.base in _BOOL_TYPES:
                    return bool(inner)
                if hasattr(target, 'base') and target.base in (_UINT_TYPES | _SINT_TYPES):
                    return int(inner)
                # Fallback: attempt coercion from the target's string representation
                type_name = str(target).lower()
                if any(k in type_name for k in ('int', 'uint', 'long', 'ulong', 'byte', 'be', 'le')):
                    return int(inner)
                if 'float' in type_name or 'double' in type_name:
                    return float(inner)
                if 'bool' in type_name:
                    return bool(inner)
            return inner  # no narrowing needed — pass value through unchanged
        raise NotImplementedError(f"Cannot evaluate {type(expr).__name__} at compile time for f-string")

    def _fstring_runtime(self, node, builder, module):
        from fast import ArrayLiteral, Literal
        from ftypesys import is_unsigned as _is_unsigned
        max_size = 256
        for part in node.parts:
            if isinstance(part, Literal) and part.type == DataType.CHAR:
                max_size += len(part.value)
            elif not isinstance(part, str):
                max_size += 32
        buffer_type = ir.ArrayType(ir.IntType(8), max_size)
        buffer = builder.alloca(buffer_type, name="fstring_buffer")
        pos_ptr = builder.alloca(ir.IntType(32), name="fstring_pos")
        builder.store(ir.Constant(ir.IntType(32), 0), pos_ptr)
        sprintf_fn = module.globals.get('sprintf')
        if sprintf_fn is None:
            sprintf_type = ir.FunctionType(ir.IntType(32),
                [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))], var_arg=True)
            sprintf_fn = ir.Function(module, sprintf_type, 'sprintf')
            sprintf_fn.linkage = 'external'
        for part in node.parts:
            pos = builder.load(pos_ptr, name="current_pos")
            dest_ptr = builder.gep(buffer, [ir.Constant(ir.IntType(32), 0), pos], name="dest")
            if isinstance(part, str):
                clean = part[2:] if part.startswith('f"') else part
                clean = clean[:-1] if clean.endswith('"') else clean
                src_val = self.visit(ArrayLiteral.from_string(clean), builder, module)
                for i in range(len(clean)):
                    char_ptr = builder.gep(src_val, [ir.Constant(ir.IntType(32), i)])
                    char_val = builder.load(char_ptr)
                    dest_char_ptr = builder.gep(dest_ptr, [ir.Constant(ir.IntType(32), i)])
                    builder.store(char_val, dest_char_ptr)
                builder.store(builder.add(pos, ir.Constant(ir.IntType(32), len(clean))), pos_ptr)
            elif isinstance(part, Literal) and part.type == DataType.CHAR:
                src_val = self.visit(part, builder, module)
                if isinstance(src_val.type, ir.PointerType):
                    str_len = len(part.value)
                    for i in range(str_len):
                        char_ptr = builder.gep(src_val, [ir.Constant(ir.IntType(32), i)])
                        char_val = builder.load(char_ptr)
                        dest_char_ptr = builder.gep(dest_ptr, [ir.Constant(ir.IntType(32), i)])
                        builder.store(char_val, dest_char_ptr)
                    builder.store(builder.add(pos, ir.Constant(ir.IntType(32), str_len)), pos_ptr)
            else:
                val = self.visit(part, builder, module)
                if isinstance(val.type, ir.IntType):
                    fmt_str = "%llu" if _is_unsigned(val) else "%lld"
                elif isinstance(val.type, (ir.FloatType, ir.DoubleType)):
                    fmt_str = "%f"
                elif (isinstance(val.type, ir.PointerType) and isinstance(val.type.pointee, ir.IntType) and val.type.pointee.width == 8):
                    fmt_str = "%s"
                elif (isinstance(val.type, ir.PointerType) and isinstance(val.type.pointee, ir.ArrayType) and
                      isinstance(val.type.pointee.element, ir.IntType) and val.type.pointee.element.width == 8):
                    fmt_str = "%s"
                    zero = ir.Constant(ir.IntType(32), 0)
                    val = builder.gep(val, [zero, zero], name="str_decay")
                else:
                    fmt_str = "%p"
                fmt_bytes = (fmt_str + "\x00").encode('ascii')
                fmt_array_ty = ir.ArrayType(ir.IntType(8), len(fmt_bytes))
                fmt_gv = ir.GlobalVariable(module, ir.Constant(fmt_array_ty, bytearray(fmt_bytes)).type,
                                           name=f".fstring_fmt_{id(part)}")
                fmt_gv.linkage = 'internal'; fmt_gv.global_constant = True
                fmt_gv.initializer = ir.Constant(fmt_array_ty, bytearray(fmt_bytes))
                zero = ir.Constant(ir.IntType(32), 0)
                fmt_ptr = builder.gep(fmt_gv, [zero, zero])
                if isinstance(val.type, ir.IntType) and val.type.width < 64:
                    val = builder.zext(val, ir.IntType(64)) if _is_unsigned(val) else builder.sext(val, ir.IntType(64))
                elif isinstance(val.type, ir.FloatType):
                    val = builder.fpext(val, ir.DoubleType())
                chars_written = builder.call(sprintf_fn, [dest_ptr, fmt_ptr, val])
                builder.store(builder.add(pos, chars_written), pos_ptr)
        final_pos = builder.load(pos_ptr)
        null_ptr = builder.gep(buffer, [ir.Constant(ir.IntType(32), 0), final_pos])
        builder.store(ir.Constant(ir.IntType(8), 0), null_ptr)
        zero = ir.Constant(ir.IntType(32), 0)
        return builder.gep(buffer, [zero, zero], name="fstring_result")

    def visit_FunctionCall(self, node, builder, module):
        from fast import FunctionPointerCall, Identifier, TieExpression

        # Resolve f-string function names at compile time, exactly as visit_FunctionDef does.
        # e.g. f"{x} {y}"() must be resolved to its string value before any lookup.
        from fast import FStringLiteral as _FStringLiteral, Stringify as _Stringify
        if isinstance(node.name, _FStringLiteral):
            parts = []
            for part in node.name.parts:
                if isinstance(part, str):
                    clean = part[2:] if part.startswith('f"') else part
                    clean = clean[:-1] if clean.endswith('"') else clean
                    parts.append(clean)
                else:
                    try:
                        parts.append(str(self._fstring_eval_ct(part, node.name, builder, module)))
                    except (ValueError, NotImplementedError) as e:
                        raise ValueError(
                            f"f-string function name contains a runtime-only expression "
                            f"that cannot be evaluated at compile time "
                            f"[{node.source_line}:{node.source_col}]: {e}"
                        ) from e
            node.name = "".join(parts)
        elif isinstance(node.name, _Stringify):
            node.name = self._resolve_stringify_name(node.name, builder, module, node)

        if self._funcall_is_fp_variable(node, builder, module):
            return self.visit(
                FunctionPointerCall(pointer=Identifier(node.name),
                                    arguments=node.arguments),
                builder, module)

        # ── Resolve the overload entry early so we can read param_types ──────
        # (arg_vals aren't built yet, but a count-based pre-check is enough
        #  for the tied/non-tied check which is purely structural.)
        current_ns = (module.symbol_table.current_namespace
                      if hasattr(module, 'symbol_table') else "")
        overload_entry = TypeResolver.resolve_overload_entry(
            module, node.name, current_ns, None)  # None → first count-match is fine

        for i, arg in enumerate(node.arguments):
            # Existing: block local vars from escaping their scope
            if isinstance(arg, Identifier):
                entry = module.symbol_table.lookup_variable(arg.name)
                if (entry is not None and entry.type_spec is not None
                        and entry.type_spec.is_local):
                    raise ValueError(
                        f"Compile error: local variable '{arg.name}' cannot "
                        f"leave its scope via function call "
                        f"[{node.source_line}:{node.source_col}]")

            # ── New: enforce tied-parameter contract ─────────────────────────
            if overload_entry and i < len(overload_entry['param_types']):
                param_spec = overload_entry['param_types'][i]
                arg_is_tie = isinstance(arg, TieExpression)
                if param_spec is not None:
                    if param_spec.is_tied and not arg_is_tie:
                        raise ValueError(
                            f"Compile error: parameter {i} of '{node.name}' "
                            f"requires a tied argument (~), but a non-tied "
                            f"expression was passed "
                            f"[{node.source_line}:{node.source_col}]")
                    if not param_spec.is_tied and arg_is_tie:
                        raise ValueError(
                            f"Compile error: parameter {i} of '{node.name}' "
                            f"is not a tied parameter, but a tie expression "
                            f"(~) was passed "
                            f"[{node.source_line}:{node.source_col}]")

        arg_vals = [self.visit(arg, builder, module) for arg in node.arguments]
        current_ns = module.symbol_table.current_namespace if hasattr(module, 'symbol_table') else ""

        # Inject default arguments for any trailing parameters not supplied by the caller.
        # We find the best matching overload by mangled name, then pad node.arguments and
        # arg_vals so the rest of the resolution pipeline sees a full argument list.
        if hasattr(module, '_func_defaults'):
            n_supplied = len(node.arguments)
            # Search all registered defaults for this function name to find a matching overload.
            for mangled, defaults in module._func_defaults.items():
                base = mangled.split('__')[0] if '__' in mangled else mangled
                if base != node.name and not mangled.endswith('__' + node.name) and node.name not in (base, mangled):
                    continue
                n_total = len(defaults)
                if n_supplied >= n_total:
                    continue  # Caller supplied all (or too many) args — nothing to fill.
                # Check that all missing args have defaults.
                missing = defaults[n_supplied:]
                if any(d is None for d in missing):
                    continue  # Some required params missing — let normal error path handle it.
                # Pad with default expressions.
                for default_expr in missing:
                    node.arguments.append(default_expr)
                    arg_vals.append(self.visit(default_expr, builder, module))
                break

        # ── Enforce endianness-parameter contract ─────────────────────────────
        # Passing a little-endian value to a big-endian parameter (or vice versa)
        # is a compile error.  Assignment auto-swaps, but parameter passing does not.
        if overload_entry:
            for i, (arg_val, param_spec) in enumerate(
                    zip(arg_vals, overload_entry['param_types'])):
                if param_spec is None:
                    continue
                tgt_endian = EndianSwapHandler.get_endianness(param_spec)
                if tgt_endian is None:
                    continue  # parameter has no explicit endianness requirement
                src_spec   = getattr(arg_val, '_flux_type_spec', None)
                src_endian = EndianSwapHandler.get_endianness(src_spec)
                if src_endian is None:
                    continue  # argument endianness unknown / native, let it pass
                if src_endian != tgt_endian:
                    endian_names = {0: "little-endian", 1: "big-endian"}
                    raise ValueError(
                        f"\nCompile error: Passing argument {i} of function {node.name} is "
                        f"{endian_names.get(src_endian, f'endian({src_endian})')}, "
                        f"but parameter {i} expects "
                        f"{endian_names.get(tgt_endian, f'endian({tgt_endian})')}.\n"
                        f"Endianness mismatch in function call disallowed "
                        f"(assignment auto-swaps, parameter passing does not). "
                        f"[{node.source_line}:{node.source_col}]")

        # Pointer-param overload
        if hasattr(module, '_function_overloads'):
            _op_key = None
            for _k in module._function_overloads:
                if _k == node.name or _k.endswith('__' + node.name):
                    _op_key = _k; break
            if _op_key is not None and len(node.arguments) == len(arg_vals):
                for _ov in module._function_overloads[_op_key]:
                    _func = _ov['function']
                    _pts = [p.type for p in _func.args]
                    if len(_pts) != len(arg_vals): continue
                    if not all(isinstance(pt, ir.PointerType) and
                               not isinstance(pt.pointee, (ir.ArrayType, ir.LiteralStructType, ir.IdentifiedStructType))
                               for pt in _pts): continue
                    _ptrs = []; _ok = True
                    for arg, pt in zip(node.arguments, _pts):
                        if not isinstance(arg, Identifier): _ok = False; break
                        _alloca = module.symbol_table.get_llvm_value(arg.name)
                        if _alloca is None or _alloca.type != pt: _ok = False; break
                        _ptrs.append(_alloca)
                    if _ok:
                        return builder.call(_func, _ptrs, name="op_overload_result")
        func = TypeResolver.resolve_function(module, node.name, current_ns, arg_vals)
        if func is None and hasattr(module, '_struct_types') and node.name in module._struct_types:
            struct_type = module._struct_types[node.name]
            tmp = builder.alloca(struct_type, name=f"{node.name}_tmp")
            init_name = f"{node.name}.__init"
            init_func = TypeResolver.resolve_function(module, init_name, current_ns, [tmp] + arg_vals)
            if init_func is None and hasattr(module, '_using_namespaces'):
                for ns in module._using_namespaces:
                    mangled = f"{ns.replace('::', '__')}__{init_name}"
                    init_func = TypeResolver.resolve_function(module, mangled, current_ns, [tmp] + arg_vals)
                    if init_func: break
            if init_func is not None:
                builder.call(init_func, [tmp] + arg_vals)
                return tmp
        if func is None:
            self._funcall_not_found(node, module)
        return self._funcall_generate(node, builder, module, func, arg_vals)

    def _funcall_is_fp_variable(self, node, builder, module):
        if module.symbol_table.get_llvm_value(node.name) is not None:
            var_ptr = module.symbol_table.get_llvm_value(node.name)
            if isinstance(var_ptr.type, ir.PointerType):
                pointee = var_ptr.type.pointee
                if isinstance(pointee, ir.FunctionType): return True
                if isinstance(pointee, ir.PointerType) and isinstance(pointee.pointee, ir.FunctionType): return True
        elif node.name in module.globals:
            gvar = module.globals[node.name]
            if not isinstance(gvar, ir.Function) and isinstance(gvar.type, ir.PointerType):
                if isinstance(gvar.type.pointee, (ir.FunctionType, ir.PointerType)):
                    return True
        return False

    def _funcall_not_found(self, node, module):
        if hasattr(module, '_function_overloads') and node.name in module._function_overloads:
            available_counts = [o['param_count'] for o in module._function_overloads[node.name]]
            if len(node.arguments) not in available_counts:
                raise ValueError(
                    f"Function {node.name} found but no overload accepts {len(node.arguments)} arguments. "
                    f"Available overloads accept: {available_counts} arguments. "
                    f"[{node.source_line}:{node.source_col}]")
        raise NameError(
            f"Function '{node.name}' not found in module or any imported namespaces "
            f"[{node.source_line}:{node.source_col}]")

    def _funcall_generate(self, node, builder, module, func, arg_vals):
        from fast import Literal, FunctionCall
        is_method_call = '.' in node.name
        parameter_offset = 1 if is_method_call else 0
        processed_args = []
        for i, (arg, arg_val) in enumerate(zip(node.arguments, arg_vals)):
            param_index = i + parameter_offset
            if (isinstance(arg, Literal) and arg.type == DataType.CHAR and
                    param_index < len(func.args) and
                    isinstance(func.args[param_index].type, ir.PointerType) and
                    isinstance(func.args[param_index].type.pointee, ir.IntType) and
                    func.args[param_index].type.pointee.width == 8):
                string_val = arg.value
                string_bytes = string_val.encode('ascii')
                str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
                str_val = ir.Constant(str_array_ty, bytearray(string_bytes))
                str_name = f".str.{FunctionCall._string_counter}"
                FunctionCall._string_counter += 1
                gv = ir.GlobalVariable(module, str_val.type, name=str_name)
                gv.linkage = 'internal'; gv.global_constant = True; gv.initializer = str_val
                zero = ir.Constant(ir.IntType(32), 0)
                arg_val = builder.gep(gv, [zero, zero], name=f"arg{i}_str_ptr")
            if param_index < len(func.args):
                expected = func.args[param_index].type
                # If the argument is a struct/object type and the parameter is not,
                # the user passed an object in expression context without defining __expr().
                # Give a clear error instead of the generic type-mismatch message.
                if (isinstance(arg_val.type, (ir.IdentifiedStructType, ir.LiteralStructType)) or
                        (isinstance(arg_val.type, ir.PointerType) and
                         isinstance(arg_val.type.pointee, (ir.IdentifiedStructType, ir.LiteralStructType)) and
                         not isinstance(expected, ir.PointerType))):
                    # Only raise if the struct type doesn't match what's expected.
                    # A matching type is a legitimate by-value struct pass — not an object misuse.
                    candidate = arg_val.type.pointee if isinstance(arg_val.type, ir.PointerType) else arg_val.type
                    if candidate == expected:
                        pass  # let convert_argument_to_parameter_type handle it
                    else:
                        obj_type_name = None
                        if hasattr(module, '_struct_types'):
                            for tname, stype in module._struct_types.items():
                                if stype == candidate:
                                    obj_type_name = tname
                                    break
                        if obj_type_name is not None:
                            raise TypeError(
                                f"Object of type '{obj_type_name}' used in expression context "
                                f"but has no __expr() method defined. "
                                f"Define 'def __expr() -> <type> {{ return @this.<member>; }};' "
                                f"inside the object to enable expression-context usage. "
                                f"[{node.source_line}:{node.source_col}]"
                            )
                arg_val = FunctionTypeHandler.convert_argument_to_parameter_type(
                    builder, module, arg_val, expected, i)
            processed_args.append(arg_val)
        call_instr = builder.call(func, processed_args)
        current_func = builder.function
        if current_func is not None and func.name == current_func.name:
            call_instr.tail = "musttail" if getattr(builder, '_flux_is_recursive_func', False) else "tail"
        return call_instr

    def visit_MemberAccess(self, node, builder, module):
        from fast import Identifier, StructFieldAccess
        if isinstance(node.object, Identifier):
            type_name = node.object.name
            if MemberAccessTypeHandler.is_enum_type(type_name, module):
                return ir.Constant(ir.IntType(32), MemberAccessTypeHandler.get_enum_value(type_name, node.member, module))
            mangled_type_name = IdentifierTypeHandler.resolve_namespace_mangled_name(type_name, module)
            if mangled_type_name and MemberAccessTypeHandler.is_enum_type(mangled_type_name, module):
                return ir.Constant(ir.IntType(32), MemberAccessTypeHandler.get_enum_value(mangled_type_name, node.member, module))
            if not mangled_type_name and hasattr(module, '_enum_types'):
                suffix = f"__{type_name}"
                for key in module._enum_types:
                    if key == type_name or key.endswith(suffix):
                        return ir.Constant(ir.IntType(32), MemberAccessTypeHandler.get_enum_value(key, node.member, module))
        # Suppress __expr promotion: visiting the LHS of a member access must yield
        # the raw struct pointer, not the promoted expression value.
        prev_in_member_access = getattr(self, '_in_member_access', False)
        self._in_member_access = True
        try:
            if hasattr(module, '_struct_types'):
                obj = self.visit(node.object, builder, module)
                if MemberAccessTypeHandler.is_struct_type(obj, module):
                    return self.visit(StructFieldAccess(node.object, node.member), builder, module)
            if isinstance(node.object, Identifier):
                type_name = node.object.name
                if MemberAccessTypeHandler.is_static_struct_member(type_name, module):
                    global_name = f"{type_name}.{node.member}"
                    for global_var in module.global_values:
                        if global_var.name == global_name:
                            return builder.load(global_var)
                    raise NameError(f"Static member '{node.member}' not found in struct '{type_name}' [{node.source_line}:{node.source_col}]")
                elif MemberAccessTypeHandler.is_static_union_member(type_name, module):
                    global_name = f"{type_name}.{node.member}"
                    for global_var in module.global_values:
                        if global_var.name == global_name:
                            return builder.load(global_var)
                    raise NameError(f"Static member '{node.member}' not found in union '{type_name}' [{node.source_line}:{node.source_col}]")
            obj_val = self.visit(node.object, builder, module)
        finally:
            self._in_member_access = prev_in_member_access
        if isinstance(node.object, Identifier) and node.object.name == "this" and MemberAccessTypeHandler.is_this_double_pointer(obj_val):
            obj_val = builder.load(obj_val, name="this_ptr")
        if (isinstance(obj_val.type, ir.PointerType) and isinstance(obj_val.type.pointee, ir.PointerType) and
                MemberAccessTypeHandler.is_struct_pointer(obj_val.type.pointee)):
            obj_val = builder.load(obj_val, name="deref_struct_ptr")
        if isinstance(obj_val.type, ir.PointerType) and MemberAccessTypeHandler.is_struct_pointer(obj_val.type):
            struct_type = obj_val.type.pointee
            if MemberAccessTypeHandler.is_union_type(struct_type, module):
                union_name = MemberAccessTypeHandler.get_union_name_from_type(struct_type, module)
                return self._member_access_union(node, builder, module, obj_val, union_name)
            member_index = MemberAccessTypeHandler.get_member_index(struct_type, node.member)
            member_ptr = builder.gep(obj_val,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), member_index)], inbounds=True)
            if isinstance(member_ptr.type, ir.PointerType):
                pointee = member_ptr.type.pointee
                if isinstance(pointee, ir.ArrayType):
                    struct_name = MemberAccessTypeHandler.get_struct_name_from_type(struct_type, module)
                    if struct_name:
                        type_spec = MemberAccessTypeHandler.get_member_type_spec(struct_name, node.member, module)
                        if type_spec:
                            MemberAccessTypeHandler.attach_array_element_type_spec(member_ptr, type_spec, module)
                    return member_ptr
                if MemberAccessTypeHandler.should_return_pointer_for_member(pointee):
                    return member_ptr
            loaded = builder.load(member_ptr)
            return MemberAccessTypeHandler.attach_member_type_metadata(loaded, struct_type, node.member, module)
        raise ValueError(f"Member access on unsupported type: {obj_val.type} [{node.source_line}:{node.source_col}]")

    def _member_access_union(self, node, builder, module, union_ptr, union_name):
        union_info = MemberAccessTypeHandler.get_union_member_info(union_name, module)
        member_names = union_info['member_names']
        member_types = union_info['member_types']
        is_tagged    = union_info['is_tagged']
        if node.member == '_':
            if not is_tagged:
                raise ValueError(f"Cannot access tag '._' on non-tagged union '{union_name}' [{node.source_line}:{node.source_col}]")
            tag_ptr = builder.gep(union_ptr, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)],
                                  inbounds=True, name="union_tag_ptr")
            return builder.load(tag_ptr, name="union_tag_value")
        MemberAccessTypeHandler.validate_union_member(union_name, node.member, module)
        member_type = MemberAccessTypeHandler.get_union_member_type(union_name, node.member, module)
        if is_tagged:
            data_ptr = builder.gep(union_ptr, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 1)],
                                   inbounds=True, name="union_data_ptr")
            casted_ptr = builder.bitcast(data_ptr, ir.PointerType(member_type), name=f"union_as_{node.member}")
            return builder.load(casted_ptr, name=f"union_{node.member}_value")
        casted_ptr = builder.bitcast(union_ptr, ir.PointerType(member_type), name=f"union_as_{node.member}")
        return builder.load(casted_ptr, name=f"union_{node.member}_value")

    def visit_MethodCall(self, node, builder, module):
        from fast import Identifier
        var_name = None
        if isinstance(node.object, Identifier):
            var_name = node.object.name
            if module.symbol_table.get_llvm_value(var_name) is not None:
                obj_ptr = module.symbol_table.get_llvm_value(var_name)
            else:
                raise NameError(f"Unknown variable: {var_name}")
        else:
            obj_ptr = self.visit(node.object, builder, module)
        if not isinstance(obj_ptr.type, ir.PointerType):
            raise ValueError(f"Method call internal error, expected alloca pointer, got: {obj_ptr.type}")
        slot_pointee = obj_ptr.type.pointee
        if isinstance(slot_pointee, ir.IdentifiedStructType):
            this_ptr = obj_ptr
        elif isinstance(slot_pointee, ir.PointerType) and isinstance(slot_pointee.pointee, ir.IdentifiedStructType):
            this_ptr = builder.load(obj_ptr, name=f"{var_name}_load" if var_name else "obj_load")
        else:
            raise ValueError(f"Cannot determine object type for method call: {obj_ptr.type}")
        struct_ty = this_ptr.type.pointee
        obj_type_name = None
        if hasattr(module, "_struct_types"):
            for type_name, struct_type in module._struct_types.items():
                if struct_type == struct_ty:
                    obj_type_name = type_name; break
        if obj_type_name is None:
            raise ValueError(f"Cannot determine object type for method call: {struct_ty}")
        method_func_name = f"{obj_type_name}.{node.method_name}"
        func = module.globals.get(method_func_name)
        if func is None and hasattr(module, '_function_overloads') and method_func_name in module._function_overloads:
            arg_vals = [self.visit(arg, builder, module) for arg in node.arguments]
            func = TypeResolver.resolve_function(module, method_func_name, "", arg_vals)
        if func is None:
            raise NameError(f"Unknown method: {method_func_name}")

        # Enforce private method access restriction
        if hasattr(module, '_private_methods'):
            current_object = getattr(module, '_current_object_name', None)
            for obj_type_name_key, priv_set in module._private_methods.items():
                if method_func_name in priv_set:
                    if current_object != obj_type_name_key:
                        raise AttributeError(
                            f"\nCannot call private method {node.method_name} on "
                            f"object instance of {obj_type_name_key} from outside its definition "
                            f"[{node.source_line}:{node.source_col}]"
                        )
                    break

        args = [this_ptr]
        for i, arg_expr in enumerate(node.arguments):
            if isinstance(arg_expr, Identifier):
                entry = module.symbol_table.lookup_variable(arg_expr.name)
                if entry is not None and entry.type_spec is not None and entry.type_spec.is_local:
                    raise ValueError(f"Compile error: local variable '{arg_expr.name}' cannot leave its scope via method call")
            arg_val = self.visit(arg_expr, builder, module)
            expected_type = func.args[i + 1].type
            if (isinstance(arg_val.type, ir.PointerType) and isinstance(arg_val.type.pointee, ir.ArrayType) and
                    isinstance(expected_type, ir.PointerType) and arg_val.type.pointee.element == expected_type.pointee):
                zero = ir.Constant(ir.IntType(32), 0)
                arg_val = builder.gep(arg_val, [zero, zero], name=f"marg{i}_decay")
            if arg_val.type != expected_type:
                arg_val = FunctionTypeHandler.convert_argument_to_parameter_type(builder, module, arg_val, expected_type, i)
            args.append(arg_val)
        return builder.call(func, args)

    def visit_FunctionPointerCall(self, node, builder, module):
        from fast import Literal, FunctionCall, FStringLiteral as _FStringLiteral, Stringify as _Stringify
        # If the callee is an f-string literal (e.g. f"{x} {y}"()), resolve its
        # name at compile time and redirect to a plain named FunctionCall —
        # exactly the same way StringLiteral names are already handled.
        if isinstance(node.pointer, _FStringLiteral):
            parts = []
            for part in node.pointer.parts:
                if isinstance(part, str):
                    clean = part[2:] if part.startswith('f"') else part
                    clean = clean[:-1] if clean.endswith('"') else clean
                    parts.append(clean)
                else:
                    try:
                        parts.append(str(self._fstring_eval_ct(part, node.pointer, builder, module)))
                    except (ValueError, NotImplementedError) as e:
                        raise ValueError(
                            f"f-string function name contains a runtime-only expression "
                            f"that cannot be evaluated at compile time "
                            f"[{node.source_line}:{node.source_col}]: {e}"
                        ) from e
            resolved_name = "".join(parts)
            synthetic = FunctionCall(name=resolved_name, arguments=node.arguments)
            synthetic.source_line = node.source_line
            synthetic.source_col  = node.source_col
        elif isinstance(node.pointer, _Stringify):
            resolved_name = self._resolve_stringify_name(node.pointer, builder, module, node)
            synthetic = FunctionCall(name=resolved_name, arguments=node.arguments)
            synthetic.source_line = node.source_line
            synthetic.source_col  = node.source_col
            return self.visit_FunctionCall(synthetic, builder, module)
            return self.visit(synthetic, builder, module)

        func_ptr = self.visit(node.pointer, builder, module)
        if isinstance(func_ptr.type, ir.PointerType) and isinstance(func_ptr.type.pointee, ir.PointerType):
            func_ptr = builder.load(func_ptr, name="func_ptr_load")
        args = [self.visit(arg, builder, module) for arg in node.arguments]
        if isinstance(func_ptr.type, ir.PointerType) and isinstance(func_ptr.type.pointee, ir.FunctionType):
            fn_type = func_ptr.type.pointee
            coerced = []
            for i, (arg_val, arg_expr) in enumerate(zip(args, node.arguments)):
                if i < len(fn_type.args):
                    expected_type = fn_type.args[i]
                    if (isinstance(arg_expr, Literal) and arg_expr.type == DataType.CHAR and
                            isinstance(expected_type, ir.PointerType) and
                            isinstance(expected_type.pointee, ir.IntType) and expected_type.pointee.width == 8):
                        string_bytes = arg_expr.value.encode('ascii')
                        str_array_ty = ir.ArrayType(ir.IntType(8), len(string_bytes))
                        str_const = ir.Constant(str_array_ty, bytearray(string_bytes))
                        str_name = f".str.fpc.{FunctionCall._string_counter}"
                        FunctionCall._string_counter += 1
                        gv = ir.GlobalVariable(module, str_const.type, name=str_name)
                        gv.linkage = 'internal'; gv.global_constant = True; gv.initializer = str_const
                        zero = ir.Constant(ir.IntType(32), 0)
                        arg_val = builder.gep(gv, [zero, zero], name=f"arg{i}_str_ptr")
                    arg_val = FunctionTypeHandler.convert_argument_to_parameter_type(builder, module, arg_val, expected_type, i)
                coerced.append(arg_val)
            args = coerced
        return builder.call(func_ptr, args, name="indirect_call", cconv=_get_fp_cconv(node.pointer, module))

    def visit_FunctionPointerAssignment(self, node, builder, module):
        if module.symbol_table.get_llvm_value(node.pointer_name) is not None:
            ptr_storage = module.symbol_table.get_llvm_value(node.pointer_name)
        elif node.pointer_name in module.globals:
            ptr_storage = module.globals[node.pointer_name]
        else:
            raise NameError(f"Function pointer '{node.pointer_name}' not found [{node.source_line}:{node.source_col}]")
        func_value = self.visit(node.function_expr, builder, module)
        builder.store(func_value, ptr_storage)
        return func_value

    def visit_ArrayAccess(self, node, builder, module):
        from fast import RangeExpression
        array_val = self.visit(node.array, builder, module)
        _ts    = getattr(array_val, '_flux_type_spec', None)
        _depth = getattr(_ts, 'pointer_depth', 1) if _ts else 1
        _is_arr = getattr(_ts, 'is_array', False) if _ts else False
        if (not _is_arr and _depth <= 1 and
                isinstance(array_val.type, ir.PointerType) and
                isinstance(array_val.type.pointee, ir.PointerType) and
                not isinstance(array_val.type.pointee.pointee, ir.ArrayType)):
            array_val = builder.load(array_val, name="ptr_loaded_for_access")
        if isinstance(node.index, RangeExpression):
            start_val = self.visit(node.index.start, builder, module)
            end_val   = self.visit(node.index.end,   builder, module)
            is_reverse = (isinstance(start_val, ir.Constant) and isinstance(end_val, ir.Constant) and
                          start_val.constant > end_val.constant)
            return ArrayTypeHandler.slice_array(builder, module, array_val, start_val, end_val, is_reverse)
        index_val = self.visit(node.index, builder, module)
        if index_val.type != ir.IntType(32):
            if isinstance(index_val.type, ir.IntType):
                index_val = (builder.trunc(index_val, ir.IntType(32), name="idx_trunc")
                             if index_val.type.width > 32
                             else builder.sext(index_val, ir.IntType(32), name="idx_ext"))
        zero = ir.Constant(ir.IntType(32), 0)
        def _load_and_preserve(gep_val, src):
            if isinstance(gep_val.type, ir.PointerType):
                pointee = gep_val.type.pointee
                if isinstance(pointee, ir.ArrayType): return gep_val
                if isinstance(pointee, (ir.LiteralStructType, ir.IdentifiedStructType)): return gep_val
                if hasattr(pointee, '_name') or hasattr(pointee, 'elements'): return gep_val
            loaded = builder.load(gep_val, name="array_load")
            return ArrayTypeHandler.preserve_array_element_type_metadata(loaded, src, module)
        if isinstance(array_val, ir.GlobalVariable):
            gep = builder.gep(array_val, [zero, index_val], inbounds=True, name="array_gep")
            return _load_and_preserve(gep, array_val)
        if isinstance(array_val.type, ir.PointerType) and isinstance(array_val.type.pointee, ir.ArrayType):
            gep = builder.gep(array_val, [zero, index_val], inbounds=True, name="array_gep")
            return _load_and_preserve(gep, array_val)
        if isinstance(array_val.type, ir.PointerType):
            gep = builder.gep(array_val, [index_val], inbounds=True, name="ptr_gep")
            if isinstance(gep.type, ir.PointerType):
                pointee = gep.type.pointee
                if (isinstance(pointee, (ir.LiteralStructType, ir.IdentifiedStructType)) or
                        hasattr(pointee, '_name') or hasattr(pointee, 'elements')):
                    return gep
            loaded = builder.load(gep, name="ptr_load")
            return ArrayTypeHandler.preserve_array_element_type_metadata(loaded, array_val, module)
        if isinstance(array_val.type, ir.IntType):
            index_i64 = builder.sext(index_val, ir.IntType(64), name="idx_i64") if index_val.type != ir.IntType(64) else index_val
            shift_amt = builder.mul(index_i64, ir.Constant(ir.IntType(64), 8), name="byte_shift")
            val_i64 = builder.zext(array_val, ir.IntType(64), name="val_i64") if array_val.type != ir.IntType(64) else array_val
            return builder.trunc(builder.lshr(val_i64, shift_amt, name="byte_shr"), ir.IntType(8), name="byte_extract")
        raise ValueError(f"Cannot access array element for type: {array_val.type} [{node.source_line}:{node.source_col}]")

    def visit_ArraySlice(self, node, builder, module):
        array_val = self.visit(node.array, builder, module)
        start_val = self.visit(node.start, builder, module)
        end_val   = self.visit(node.end,   builder, module)
        i32 = ir.IntType(32)
        def as_i32(v, name):
            if v.type == i32: return v
            if isinstance(v.type, ir.IntType):
                return builder.trunc(v, i32, name=f"{name}_trunc") if v.type.width > 32 else builder.sext(v, i32, name=f"{name}_ext")
            raise ValueError(f"Slice indices must be integers [{node.source_line}:{node.source_col}]")
        start_i32 = as_i32(start_val, "slice_start")
        end_i32   = as_i32(end_val,   "slice_end")
        zero = ir.Constant(i32, 0)
        # Support backwards ranges: [high:low] reverses the result.
        is_backward = builder.icmp_signed('>', start_i32, end_i32, name="slice_is_backward")
        gep_start   = builder.select(is_backward, end_i32,   start_i32, name="slice_gep_start")
        # [x:y] is inclusive on both ends: length = |start - end| + 1.
        # Compute abs(start - end) first, then add 1 — negating after +1 was wrong
        # for backward slices (e.g. [7:0] → 7-0=7, 7+1=8, not (0-7+1)=−6→6).
        fwd_len  = builder.sub(end_i32,   start_i32, name="slice_fwd_raw")  # negative when backward
        bwd_len  = builder.sub(start_i32, end_i32,   name="slice_bwd_raw")  # positive when backward
        abs_len  = builder.select(is_backward, bwd_len, fwd_len, name="slice_abs_len")
        dyn_len  = builder.add(abs_len, ir.Constant(i32, 1), name="slice_len")
        elem_ty = ArrayTypeHandler.get_element_type_from_array_value(array_val)
        if isinstance(array_val, ir.GlobalVariable) and isinstance(array_val.type.pointee, ir.ArrayType):
            src_ptr = builder.gep(array_val, [zero, gep_start], inbounds=True, name="slice_src")
        elif isinstance(array_val.type, ir.PointerType) and isinstance(array_val.type.pointee, ir.ArrayType):
            src_ptr = builder.gep(array_val, [zero, gep_start], inbounds=True, name="slice_src")
        elif isinstance(array_val.type, ir.PointerType):
            src_ptr = builder.gep(array_val, [gep_start], inbounds=True, name="slice_src")
        else:
            raise ValueError(f"Cannot slice type: {array_val.type} [{node.source_line}:{node.source_col}]")

        def _emit_inline_reverse(buf_ptr, byte_len_val):
            """Emit an inline two-pointer byte-swap loop over buf_ptr[0..byte_len_val-1]."""
            i8ptr = ir.PointerType(ir.IntType(8))
            i32t  = ir.IntType(32)
            i8t   = ir.IntType(8)
            lo_ptr = builder.alloca(i32t, name="rev_lo")
            hi_ptr = builder.alloca(i32t, name="rev_hi")
            builder.store(ir.Constant(i32t, 0), lo_ptr)
            hi_init = builder.sub(byte_len_val, ir.Constant(i32t, 1), name="rev_hi_init")
            builder.store(hi_init, hi_ptr)
            fn    = builder.function
            cond_bb = fn.append_basic_block("rev_cond")
            body_bb = fn.append_basic_block("rev_body")
            end_bb  = fn.append_basic_block("rev_end")
            builder.branch(cond_bb)
            builder.position_at_end(cond_bb)
            lo = builder.load(lo_ptr, name="rev_lo_v")
            hi = builder.load(hi_ptr, name="rev_hi_v")
            cond = builder.icmp_signed('<', lo, hi, name="rev_cond_v")
            builder.cbranch(cond, body_bb, end_bb)
            builder.position_at_end(body_bb)
            lo2 = builder.load(lo_ptr, name="rev_lo2")
            hi2 = builder.load(hi_ptr, name="rev_hi2")
            p_lo = builder.gep(buf_ptr, [lo2], name="rev_p_lo")
            p_hi = builder.gep(buf_ptr, [hi2], name="rev_p_hi")
            a = builder.load(p_lo, name="rev_a")
            b = builder.load(p_hi, name="rev_b")
            builder.store(b, p_lo)
            builder.store(a, p_hi)
            builder.store(builder.add(lo2, ir.Constant(i32t, 1), name="rev_lo_inc"), lo_ptr)
            builder.store(builder.sub(hi2, ir.Constant(i32t, 1), name="rev_hi_dec"), hi_ptr)
            builder.branch(cond_bb)
            builder.position_at_end(end_bb)

        # If the length happens to be statically known, use a fixed alloca (avoids VLA).
        const_len = node._try_const_len()
        alloca_len = abs(const_len) if const_len is not None else None
        i8_ptr_ty = ir.PointerType(ir.IntType(8))
        elem_bytes = ArrayTypeHandler.compute_element_size_bytes(elem_ty)
        i8 = ir.IntType(8)
        null = ir.Constant(i8, 0)
        if alloca_len is not None:
            dst_arr_ty = ir.ArrayType(elem_ty, alloca_len + 1)
            dst_alloca = builder.alloca(dst_arr_ty, name="slice_tmp")
            dst_ptr = builder.gep(dst_alloca, [zero, zero], inbounds=True, name="slice_dst")
            ArrayTypeHandler.emit_memcpy(builder, module, dst_ptr, src_ptr, alloca_len * elem_bytes)
            if const_len < 0:
                buf_i8 = builder.bitcast(dst_ptr, i8_ptr_ty, name="slice_rev_ptr")
                _emit_inline_reverse(buf_i8, ir.Constant(i32, alloca_len * elem_bytes))
            null_pos = builder.gep(dst_alloca, [zero, ir.Constant(i32, alloca_len)], inbounds=True, name="slice_null_pos")
            builder.store(null, null_pos)
            return builder.gep(dst_alloca, [zero, zero], inbounds=True, name="slice_ptr")
        else:
            elem_bytes_val = ir.Constant(i32, elem_bytes)
            byte_count = builder.mul(dyn_len, elem_bytes_val, name="slice_byte_count")
            byte_count_p1 = builder.add(byte_count, ir.Constant(i32, 1), name="slice_byte_count_p1")
            i8_alloca = builder.alloca(i8, size=byte_count_p1, name="slice_tmp")
            src_as_i8 = builder.bitcast(src_ptr, i8_ptr_ty, name="slice_src_i8")
            ArrayTypeHandler.emit_memcpy_dynamic(builder, module, i8_alloca, src_as_i8, byte_count)
            with builder.if_then(is_backward):
                _emit_inline_reverse(i8_alloca, byte_count)
            null_pos = builder.gep(i8_alloca, [byte_count], name="slice_null_pos")
            builder.store(null, null_pos)
            return builder.bitcast(i8_alloca, ir.PointerType(elem_ty), name="slice_ptr")

    def visit_TieExpression(self, node, builder, module):
        from fast import Identifier
        if not isinstance(node.operand, Identifier):
            raise ValueError(
                f"Tie operator ~ can only be applied to variables "
                f"[{node.source_line}:{node.source_col}]")
        var_name = node.operand.name

        # ── Use-after-untie check (must come before re-tie) ──────────────────
        IdentifierTypeHandler.check_validity(var_name, builder)

        # ── Resolve the pointer ───────────────────────────────────────────────
        if module.symbol_table.get_llvm_value(var_name) is not None:
            var_ptr = module.symbol_table.get_llvm_value(var_name)
        elif var_name in module.globals:
            var_ptr = module.globals[var_name]
        else:
            raise NameError(
                f"Unknown variable: {var_name} "
                f"[{node.source_line}:{node.source_col}]")

        tied_value = builder.load(var_ptr, name=f"{var_name}_tied")

        # ── Mark as untied (Python-side, compile-time tracking) ──────────────
        if not hasattr(builder, '_untied_vars'):
            builder._untied_vars = set()
        builder._untied_vars.add(var_name)

        # ── Zero out the source variable in LLVM IR (move-safety / crypto zeroing) ──
        # Every supported type is explicitly zeroed so no stale data remains
        # in the source location after ownership is transferred.
        pointee = var_ptr.type.pointee
        if isinstance(pointee, ir.PointerType):
            # Pointer: store a null pointer constant.
            builder.store(ir.Constant(pointee, None), var_ptr)
        elif isinstance(pointee, ir.IntType):
            # Integer (any width): store integer zero.
            builder.store(ir.Constant(pointee, 0), var_ptr)
        elif isinstance(pointee, (ir.FloatType, ir.DoubleType, ir.HalfType)):
            # Floating-point: store positive zero.
            builder.store(ir.Constant(pointee, 0.0), var_ptr)
        elif isinstance(pointee, (ir.LiteralStructType, ir.IdentifiedStructType)):
            # Struct: store an all-zeros aggregate constant.
            builder.store(ir.Constant(pointee, None), var_ptr)
        elif isinstance(pointee, ir.ArrayType):
            # Array: store an all-zeros aggregate constant.
            builder.store(ir.Constant(pointee, None), var_ptr)

        return tied_value

    def visit_StructLiteral(self, node, builder, module):
        if node.struct_type is None:
            raise ValueError(
                f"Struct literal must have type context. [{node.source_line}:{node.source_col}]")
        return StructTypeHandler.pack_struct_literal(
            builder, module, node.struct_type, node.field_values, node.positional_values)

    def visit_StructInstance(self, node, builder, module):
        if not hasattr(module, '_struct_vtables'):
            raise ValueError(f"Struct '{node.struct_name}' not defined [{node.source_line}:{node.source_col}]")
        vtable = module._struct_vtables.get(node.struct_name)
        if not vtable:
            raise ValueError(f"Struct '{node.struct_name}' not defined [{node.source_line}:{node.source_col}]")
        struct_type = module._struct_types[node.struct_name]
        instance = StructTypeHandler.create_zeroed_instance(struct_type, vtable)
        for field_name, field_value_expr in node.field_values.items():
            field_info = next((f for f in vtable.fields if f[0] == field_name), None)
            if not field_info:
                raise ValueError(f"Field '{field_name}' not found in struct '{node.struct_name}' [{node.source_line}:{node.source_col}]")
            _, bit_offset, bit_width, alignment = field_info
            field_value = self.visit(field_value_expr, builder, module)
            instance = StructTypeHandler.pack_field_value(builder, instance, field_value, bit_offset, bit_width, vtable.total_bits)
        return instance

    def visit_StructFieldAccess(self, node, builder, module):
        from fast import Identifier
        instance_val = self.visit(node.struct_instance, builder, module)
        struct_name = None
        if isinstance(node.struct_instance, Identifier):
            var_name = node.struct_instance.name
            entry = module.symbol_table.lookup_variable(var_name)
            if entry and entry.type_spec:
                type_spec = entry.type_spec
                if getattr(type_spec, "custom_typename", None):
                    struct_name = type_spec.custom_typename
            if (not isinstance(instance_val.type, ir.PointerType) and
                    isinstance(instance_val.type, (ir.LiteralStructType, ir.IdentifiedStructType))):
                alloca_ptr = module.symbol_table.get_llvm_value(var_name)
                if alloca_ptr is not None and isinstance(alloca_ptr.type, ir.PointerType):
                    if isinstance(alloca_ptr.type.pointee, (ir.LiteralStructType, ir.IdentifiedStructType)):
                        instance_val = alloca_ptr
        def _resolve_struct_name(name):
            if not name: return None
            if hasattr(module, "_struct_vtables") and name in module._struct_vtables: return name
            if hasattr(module, "_using_namespaces") and hasattr(module, "_struct_vtables"):
                for ns in module._using_namespaces:
                    mangled = ns.replace("::", "__") + "__" + name
                    if mangled in module._struct_vtables: return mangled
            if hasattr(module, "_struct_types") and name in module._struct_types: return name
            if hasattr(module, "_using_namespaces") and hasattr(module, "_struct_types"):
                for ns in module._using_namespaces:
                    mangled = ns.replace("::", "__") + "__" + name
                    if mangled in module._struct_types: return mangled
            return name
        struct_name = _resolve_struct_name(struct_name)
        if isinstance(instance_val.type, ir.PointerType):
            pointee = instance_val.type.pointee
            if isinstance(pointee, (ir.LiteralStructType, ir.IdentifiedStructType)):
                struct_type = pointee
                if not hasattr(struct_type, "names") or not struct_type.names:
                    raise ValueError(f"Struct type missing member names [{node.source_line}:{node.source_col}]")
                try:
                    field_index = struct_type.names.index(node.field_name)
                except ValueError:
                    raise ValueError(f"Field '{node.field_name}' not found in struct [{node.source_line}:{node.source_col}]")
                zero = ir.Constant(ir.IntType(32), 0)
                idx = ir.Constant(ir.IntType(32), field_index)
                field_ptr = builder.gep(instance_val, [zero, idx], inbounds=True, name=f"{node.field_name}_ptr")
                if isinstance(field_ptr.type, ir.PointerType):
                    fp = field_ptr.type.pointee
                    if isinstance(fp, (ir.ArrayType, ir.LiteralStructType, ir.IdentifiedStructType)):
                        return field_ptr
                return builder.load(field_ptr, name=node.field_name)
        if isinstance(instance_val.type, ir.PointerType):
            instance = builder.load(instance_val, name="struct_load")
        else:
            instance = instance_val
        if struct_name is None:
            struct_name = StructTypeHandler.infer_struct_name(instance, module)
            struct_name = _resolve_struct_name(struct_name)
        vtable = getattr(module, "_struct_vtables", {}).get(struct_name)
        if not vtable:
            raise ValueError(f"Cannot determine struct type for field access [{node.source_line}:{node.source_col}]")
        field_info = next((f for f in vtable.fields if f[0] == node.field_name), None)
        if not field_info:
            raise ValueError(f"Field '{node.field_name}' not found in struct '{struct_name}' [{node.source_line}:{node.source_col}]")
        _, bit_offset, bit_width, alignment = field_info
        if isinstance(instance.type, ir.IntType):
            instance_type = instance.type
            shifted = builder.lshr(instance, ir.Constant(instance_type, bit_offset)) if bit_offset > 0 else instance
            masked  = builder.and_(shifted, ir.Constant(instance_type, (1 << bit_width) - 1))
            field_type = ir.IntType(bit_width)
            return builder.trunc(masked, field_type, name=node.field_name) if instance_type.width != bit_width else masked
        if isinstance(instance.type, (ir.LiteralStructType, ir.IdentifiedStructType)):
            for i, f in enumerate(vtable.fields):
                if f[0] == node.field_name:
                    return builder.extract_value(instance, i, name=node.field_name)
            raise ValueError(f"Field '{node.field_name}' not found [{node.source_line}:{node.source_col}]")
        byte_offset = bit_offset // 8
        if bit_offset % 8 == 0 and bit_width % 8 == 0:
            field_bytes = bit_width // 8
            field_type  = ir.IntType(bit_width)
            result = ir.Constant(field_type, 0)
            for i in range(field_bytes):
                byte_val = builder.extract_value(instance, byte_offset + i)
                byte_ext = builder.zext(byte_val, field_type)
                byte_shifted = builder.shl(byte_ext, ir.Constant(field_type, (field_bytes - 1 - i) * 8))
                result = builder.or_(result, byte_shifted)
            if hasattr(vtable, "field_types") and node.field_name in vtable.field_types:
                target_type = vtable.field_types[node.field_name]
                if isinstance(target_type, (ir.FloatType, ir.DoubleType)) and isinstance(result.type, ir.IntType):
                    result = builder.bitcast(result, target_type)
            return result
        raise NotImplementedError(f"Unaligned field access not yet supported [{node.source_line}:{node.source_col}]")

    def visit_StructRecast(self, node, builder, module):
        from fast import ArraySlice as _ArraySlice
        # Zero-copy path: `T t from src[start:end]` — source_expr is an ArraySlice.
        # Do NOT call visit_ArraySlice which allocates a copy; instead emit a bare
        # GEP into the source buffer at the start offset and let perform_struct_recast
        # bitcast that pointer in-place, returning a Test* directly into src.
        if isinstance(node.source_expr, _ArraySlice):
            sl = node.source_expr
            array_val = self.visit(sl.array, builder, module)
            # Unwrap alloca-of-pointer (e.g. noopstr variable: [5xi8]** → [5xi8]*)
            if (isinstance(array_val.type, ir.PointerType) and
                    isinstance(array_val.type.pointee, ir.PointerType) and
                    not isinstance(array_val.type.pointee.pointee, ir.ArrayType)):
                array_val = builder.load(array_val, name="recast_arr_load")
            start_val = self.visit(sl.start, builder, module)
            i32 = ir.IntType(32)
            if start_val.type != i32:
                start_val = (builder.trunc(start_val, i32, name="recast_start_trunc")
                             if isinstance(start_val.type, ir.IntType) and start_val.type.width > 32
                             else builder.sext(start_val, i32, name="recast_start_ext"))
            zero = ir.Constant(i32, 0)
            # GEP to the first byte of the slice within the source — no copy
            if isinstance(array_val, ir.GlobalVariable) and isinstance(array_val.type.pointee, ir.ArrayType):
                src_ptr = builder.gep(array_val, [zero, start_val], inbounds=True, name="recast_src_ptr")
            elif isinstance(array_val.type, ir.PointerType) and isinstance(array_val.type.pointee, ir.ArrayType):
                src_ptr = builder.gep(array_val, [zero, start_val], inbounds=True, name="recast_src_ptr")
            else:
                src_ptr = builder.gep(array_val, [start_val], inbounds=True, name="recast_src_ptr")
            return StructTypeHandler.perform_struct_recast(builder, module, node.target_type, src_ptr)
        source_value = self.visit(node.source_expr, builder, module)
        return StructTypeHandler.perform_struct_recast(builder, module, node.target_type, source_value)

    def visit_Assignment(self, node, builder, module):
        from fast import (ArrayLiteral, StructLiteral, Identifier, MemberAccess, ArrayAccess,
                          PointerDeref, BitSlice, RangeExpression, Literal)
        # Seed element_type on ArrayLiteral from target's type_spec so large
        # unsigned literals aren't promoted to i64 when target is e.g. u32[N].
        if isinstance(node.value, ArrayLiteral) and node.value.element_type is None:
            target_name = node.target.name if isinstance(node.target, Identifier) else None
            if target_name is not None:
                entry = module.symbol_table.lookup_any(target_name)
                if entry and entry.type_spec is not None:
                    import dataclasses
                    ts = entry.type_spec
                    elem_ts = dataclasses.replace(ts, is_array=False, array_size=None, array_dimensions=None)
                    node.value.element_type = elem_ts

        # Seed struct_type on StructLiteral from target's type_spec so that bare
        # struct literals like `week[0] = {day = 1, celsius = 20.5}` have the
        # required type context when the target is an array element (ArrayAccess)
        # or a plain variable (Identifier).
        if isinstance(node.value, StructLiteral) and node.value.struct_type is None:
            target_name = node.target.name if isinstance(node.target, Identifier) else None
            if target_name is None and isinstance(node.target, ArrayAccess):
                inner = node.target.array
                target_name = inner.name if isinstance(inner, Identifier) else None
            if target_name is not None:
                entry = module.symbol_table.lookup_any(target_name)
                if entry and entry.type_spec is not None:
                    ctn = getattr(entry.type_spec, 'custom_typename', None)
                    if ctn:
                        node.value.struct_type = ctn

        val = self.visit(node.value, builder, module)

        # ── Tied return-type check ────────────────────────────────────────────
        # If the RHS is a function call whose return type is ~T, the LHS must
        # also be a ~T variable.  Assigning a tied return value to a non-tied
        # variable is a compile error.
        from fast import FunctionCall, TieExpression
        if isinstance(node.target, Identifier):
            target_entry = module.symbol_table.lookup_any(node.target.name)
            target_is_tied = (target_entry is not None
                              and target_entry.type_spec is not None
                              and getattr(target_entry.type_spec, 'is_tied', False))

            if target_is_tied:
                # Case 1: RHS is a function call — return type must be tied
                if isinstance(node.value, FunctionCall):
                    current_ns = (module.symbol_table.current_namespace
                                  if hasattr(module, 'symbol_table') else "")
                    ov = TypeResolver.resolve_overload_entry(
                        module, node.value.name, current_ns, None)
                    if ov is not None:
                        ret_spec = ov.get('return_type')
                        if ret_spec is not None and not getattr(ret_spec, 'is_tied', False):
                            raise ValueError(
                                f"Compile error: '{node.value.name}' does not return a tied type, "
                                f"cannot assign to tied variable '{node.target.name}' "
                                f"[{node.source_line}:{node.source_col}]")

                # Case 2: RHS is a plain identifier — must be a TieExpression (~w)
                elif isinstance(node.value, Identifier):
                    raise ValueError(
                        f"Compile error: cannot assign non-tied value to tied variable "
                        f"'{node.target.name}' — use '~{node.value.name}' to transfer ownership "
                        f"[{node.source_line}:{node.source_col}]")

            # Case 3: non-tied target, tied-return function (original check, flipped)
            elif isinstance(node.value, FunctionCall):
                current_ns = (module.symbol_table.current_namespace
                              if hasattr(module, 'symbol_table') else "")
                ov = TypeResolver.resolve_overload_entry(
                    module, node.value.name, current_ns, None)
                if ov is not None:
                    ret_spec = ov.get('return_type')
                    if ret_spec is not None and getattr(ret_spec, 'is_tied', False):
                        raise ValueError(
                            f"Compile error: Function {node.value.name} returns a tied type (~), "
                            f"but {node.target.name}'s type is not tied."
                            f"[{node.source_line}:{node.source_col}]")

        if isinstance(node.target, Identifier):
            return AssignmentTypeHandler.handle_identifier_assignment(
                builder, module, node.target.name, val, node.value)

        elif isinstance(node.target, MemberAccess):
            return AssignmentTypeHandler.handle_member_assignment(
                builder, module, node.target.object, node.target.member, val,
                value_expr=node.value)

        elif isinstance(node.target, ArrayAccess):
            if isinstance(node.target.array, MemberAccess):
                member_ptr = node.target.array._get_member_ptr(builder, module)
                if (isinstance(member_ptr.type, ir.PointerType) and
                        isinstance(member_ptr.type.pointee, ir.ArrayType)):
                    if isinstance(node.target.index, RangeExpression):
                        from ftypesys import emit_memcpy
                        rng = node.target.index
                        s = rng.start.value if isinstance(rng.start, Literal) else None
                        e = rng.end.value if isinstance(rng.end, Literal) else None
                        if s is None or e is None:
                            raise ValueError(f"Struct member slice assignment indices must be literals [{node.source_line}:{node.source_col}]")
                        const_len = e - s + 1
                        zero = ir.Constant(ir.IntType(32), 0)
                        start_i32 = ir.Constant(ir.IntType(32), s)
                        dst_ptr = builder.gep(member_ptr, [zero, start_i32], inbounds=True, name="slicewr_dst")
                        i8ptr = ir.IntType(8).as_pointer()
                        dst_i8 = builder.bitcast(dst_ptr, i8ptr, name="slicewr_dst_i8")
                        if isinstance(val.type, ir.PointerType):
                            src_i8 = builder.bitcast(val, i8ptr, name="slicewr_src_i8")
                        else:
                            src_alloca = builder.alloca(val.type, name="slicewr_src")
                            builder.store(val, src_alloca)
                            src_i8 = builder.bitcast(src_alloca, i8ptr, name="slicewr_src_i8")
                        emit_memcpy(builder, module, dst_i8, src_i8, const_len)
                        return val
                    index = self.visit(node.target.index, builder, module)
                    if index.type != ir.IntType(32):
                        if isinstance(index.type, ir.IntType):
                            if index.type.width > 32:
                                index = builder.trunc(index, ir.IntType(32), name="idx_trunc")
                            else:
                                index = builder.sext(index, ir.IntType(32), name="idx_ext")
                    zero = ir.Constant(ir.IntType(32), 0)
                    elem_ptr = builder.gep(member_ptr, [zero, index], inbounds=True)
                    element_type = member_ptr.type.pointee.element
                    if val.type != element_type:
                        if isinstance(val.type, ir.IntType) and isinstance(element_type, ir.IntType):
                            if val.type.width > element_type.width:
                                val = builder.trunc(val, element_type, name="val_trunc")
                            else:
                                val = builder.sext(val, element_type, name="val_ext")
                    builder.store(val, elem_ptr)
                    return val
            return AssignmentTypeHandler.handle_array_element_assignment(
                builder, module, node.target.array, node.target.index, node.value, val)

        elif isinstance(node.target, PointerDeref):
            ptr = self.visit(node.target.pointer, builder, module)
            if (isinstance(ptr.type, ir.PointerType) and
                isinstance(ptr.type.pointee, ir.PointerType) and
                isinstance(ptr.type.pointee.pointee, ir.PointerType)):
                ptr = builder.load(ptr, name="deref_ptr_loaded")
            return AssignmentTypeHandler.handle_pointer_deref_assignment(builder, ptr, val)

        elif isinstance(node.target, BitSlice):
            if not isinstance(node.target.value, Identifier):
                raise ValueError(f"Bit-slice assignment target must be a simple variable [{node.source_line}:{node.source_col}]")
            var_name = node.target.value.name
            ptr = module.symbol_table.get_llvm_value(var_name)
            if ptr is None:
                raise ValueError(f"Unknown variable '{var_name}' [{node.source_line}:{node.source_col}]")
            int_type = ptr.type.pointee
            if not isinstance(int_type, ir.IntType):
                raise ValueError(f"Bit-slice assignment requires an integer variable [{node.source_line}:{node.source_col}]")
            w = int_type.width
            s_val = self.visit(node.target.start, builder, module)
            e_val = self.visit(node.target.end, builder, module)
            if not (hasattr(s_val, 'constant') and hasattr(e_val, 'constant')):
                raise ValueError(f"Bit-slice assignment indices must be constants [{node.source_line}:{node.source_col}]")
            s_const = int(s_val.constant)
            e_const = int(e_val.constant)
            slice_width = e_const - s_const + 1
            lsb_shift = w - 1 - e_const
            mask = ((1 << slice_width) - 1) << lsb_shift
            inv_mask = ((1 << w) - 1) & ~mask
            cur = builder.load(ptr, name="bsa_cur")
            cleared = builder.and_(cur, ir.Constant(int_type, inv_mask), name="bsa_cleared")
            if isinstance(val.type, ir.IntType):
                if val.type.width < w:
                    val = builder.zext(val, int_type, name="bsa_widen")
                elif val.type.width > w:
                    val = builder.trunc(val, int_type, name="bsa_trunc")
            rhs_masked = builder.and_(val, ir.Constant(int_type, (1 << slice_width) - 1), name="bsa_rhs_mask")
            rhs_shifted = builder.shl(rhs_masked, ir.Constant(int_type, lsb_shift), name="bsa_rhs_shift")
            result = builder.or_(cleared, rhs_shifted, name="bsa_result")
            builder.store(result, ptr)
            return result

        else:
            raise ValueError(f"Cannot assign to {type(node.target).__name__} [{node.source_line}:{node.source_col}]")

    def visit_CompoundAssignment(self, node, builder, module):
        return AssignmentTypeHandler.handle_compound_assignment(
            builder, module, node.target, node.op_token, node.value)

    def visit_TernaryAssign(self, node, builder, module):
        from fast import Identifier
        if isinstance(node.target, Identifier):
            sym = module.symbol_table.lookup(node.target.name)
            if sym is None:
                raise ValueError(f"Undefined variable '{node.target.name}' [{node.source_line}:{node.source_col}]")
            ptr = module.symbol_table.get_llvm_value(node.target.name)
            current_val = builder.load(ptr, name="ternary_assign_cur")
        else:
            raise ValueError(f"TernaryAssign: unsupported target type {type(node.target).__name__} [{node.source_line}:{node.source_col}]")

        zero = ir.Constant(current_val.type, 0)
        is_zero = builder.icmp_unsigned('==', current_val, zero, name="ternary_assign_cmp")

        func = builder.block.function
        then_block = func.append_basic_block(name="ternary_assign_then")
        merge_block = func.append_basic_block(name="ternary_assign_merge")

        builder.cbranch(is_zero, then_block, merge_block)

        builder.position_at_start(then_block)
        new_val = self.visit(node.value, builder, module)
        if new_val.type != current_val.type:
            if isinstance(new_val.type, ir.IntType) and isinstance(current_val.type, ir.IntType):
                if new_val.type.width > current_val.type.width:
                    new_val = builder.trunc(new_val, current_val.type, name="ternary_assign_trunc")
                else:
                    new_val = builder.sext(new_val, current_val.type, name="ternary_assign_ext")
        builder.store(new_val, ptr)
        builder.branch(merge_block)

        builder.position_at_start(merge_block)
        return None

    def visit_Block(self, node, builder, module):
        import inspect as _inspect
        result = None
        #print(node.statements)
        #print(f"DEBUG Block: Processing {len(node.statements)} statements")

        outer_defer_stack = getattr(builder, '_flux_defer_stack', None)
        builder._flux_defer_stack = []

        try:
            for i, stmt in enumerate(node.statements):
                #print(f"DEBUG Block: Processing statement {i}: {type(stmt).__name__}")
                if builder.block.is_terminated:
                    break
                if stmt is not None:
                    try:
                        stmt_result = self.visit(stmt, builder, module)
                        if stmt_result is not None:
                            result = stmt_result
                    except Exception as e:
                        import traceback as _tb
                        current_frame = _inspect.currentframe()
                        caller_frame = current_frame.f_back
                        caller_name = caller_frame.f_code.co_name
                        stack = _inspect.stack()
                        stmt_i = i
                        #print("Full call stack (from current to outermost):")
                        #for i, frame_info in enumerate(reversed(stack)):
                            #print(f"  {i}: {frame_info.function}() in {frame_info.filename}:{frame_info.lineno}")
                        #print("--- REAL EXCEPTION ---")
                        #_tb.print_exc()
                        #print("--- END REAL EXCEPTION ---")
                        loc = ""
                        if hasattr(stmt, 'source_line') and stmt.source_line:
                            loc = f" {_src_loc(stmt, module)}"
                        raise ValueError(f"Block{{}} Debug: Error in statement {stmt_i} ({type(stmt).__name__}){loc}: {e}")

            if builder._flux_defer_stack and not builder.block.is_terminated:
                for deferred in reversed(builder._flux_defer_stack):
                    if isinstance(deferred, list):
                        for stmt in reversed(deferred):
                            self.visit(stmt, builder, module)
                    else:
                        self.visit(deferred, builder, module)
        finally:
            builder._flux_defer_stack = outer_defer_stack if outer_defer_stack is not None else []

        return result

    def visit_IfStatement(self, node, builder, module):
        if builder.block is None:
            return self._visit_IfStatement_global_scope(node, builder, module)

        _check_not_string_literal(node.condition, 'if', module)

        try:
            cond_val = self.visit(node.condition, builder, module)
        except Exception as e:
            from fast import ComptimeError
            raise ComptimeError(f"if statement condition: {e} [{node.source_line}:{node.source_col}]")

        func = builder.block.function
        then_block = func.append_basic_block('then')
        else_block = func.append_basic_block('else')
        merge_block = func.append_basic_block('ifcont')

        cond_val = _coerce_to_bool(builder, cond_val)
        builder.cbranch(cond_val, then_block, else_block)

        builder.position_at_start(then_block)
        self.visit(node.then_block, builder, module)
        if not builder.block.is_terminated:
            builder.branch(merge_block)

        builder.position_at_start(else_block)

        current_block = else_block
        for i, (elif_cond, elif_body) in enumerate(node.elif_blocks):
            _check_not_string_literal(elif_cond, 'elif', module)
            elif_cond_val = self.visit(elif_cond, builder, module)
            elif_cond_val = _coerce_to_bool(builder, elif_cond_val)
            elif_then = func.append_basic_block(f'elif_then_{i}')
            elif_else = func.append_basic_block(f'elif_else_{i}')
            builder.cbranch(elif_cond_val, elif_then, elif_else)
            builder.position_at_start(elif_then)
            self.visit(elif_body, builder, module)
            if not builder.block.is_terminated:
                builder.branch(merge_block)
            builder.position_at_start(elif_else)
            current_block = elif_else

        if node.else_block:
            self.visit(node.else_block, builder, module)

        if not builder.block.is_terminated:
            builder.branch(merge_block)

        builder.position_at_start(merge_block)
        return None

    def _visit_IfStatement_global_scope(self, node, builder, module):
        _check_not_string_literal(node.condition, 'if', module)
        try:
            cond_val = self.visit(node.condition, builder, module)
        except Exception as e:
            raise RuntimeError(f"Could not evaluate global if condition: {e} [{node.source_line}:{node.source_col}]")

        if isinstance(cond_val, ir.Constant):
            if cond_val.constant:
                self.visit(node.then_block, builder, module)
            else:
                executed = False
                for elif_cond, elif_block in node.elif_blocks:
                    elif_val = self.visit(elif_cond, builder, module)
                    if isinstance(elif_val, ir.Constant) and elif_val.constant:
                        self.visit(elif_block, builder, module)
                        executed = True
                        break
                if not executed and node.else_block:
                    self.visit(node.else_block, builder, module)
        else:
            raise RuntimeError(f"Cannot use runtime conditions in global scope if statements [{node.source_line}:{node.source_col}]")

        return None

    def visit_IfExpression(self, node, builder, module):
        from fast import NoInit

        def _coerce_ifexpr_operand(expr, ref_val, builder, module):
            """Visit an if-expression operand, handling raw Python scalars that the
            parser may emit directly (e.g. the ``0`` in ``x if (c) else 0``)."""
            if isinstance(expr, (int, float, bool)):
                # Raw scalar: emit as a constant matching ref_val's type when available.
                if ref_val is not None and isinstance(ref_val.type, ir.IntType):
                    return ir.Constant(ref_val.type, int(expr))
                if ref_val is not None and isinstance(ref_val.type, (ir.FloatType, ir.DoubleType)):
                    return ir.Constant(ref_val.type, float(expr))
                # No type hint available yet: default to i64 for ints, double for floats.
                if isinstance(expr, float):
                    return ir.Constant(ir.DoubleType(), expr)
                return ir.Constant(ir.IntType(64), int(expr))
            return self.visit(expr, builder, module)

        _check_not_string_literal(node.condition, 'if-expression condition', module)
        cond_val = self.visit(node.condition, builder, module)
        cond_val = _coerce_to_bool(builder, cond_val)

        func = builder.block.function
        value_block = func.append_basic_block('ifexpr_value')
        else_block  = func.append_basic_block('ifexpr_else')
        merge_block = func.append_basic_block('ifexpr_merge')

        builder.cbranch(cond_val, value_block, else_block)

        builder.position_at_start(value_block)
        value_val = _coerce_ifexpr_operand(node.value_expr, None, builder, module)
        value_end_block = builder.block
        if not builder.block.is_terminated:
            builder.branch(merge_block)

        # Statement-context if-expression with a void value and no else clause:
        # e.g. ``println("hi") if (cond);``
        # The else branch just falls through to merge — no phi needed.
        is_void_value = isinstance(value_val.type, ir.VoidType)
        if is_void_value and node.else_expr is None:
            builder.position_at_start(else_block)
            if not builder.block.is_terminated:
                builder.branch(merge_block)
            builder.position_at_start(merge_block)
            return None

        builder.position_at_start(else_block)
        if node.else_expr is not None:
            if isinstance(node.else_expr, NoInit):
                else_val = ir.Constant(value_val.type, ir.Undefined)
            else:
                else_val = _coerce_ifexpr_operand(node.else_expr, value_val, builder, module)
        else:
            # value is non-void but no else clause: default to zero of the same type
            else_val = ir.Constant(value_val.type, 0)

        else_end_block = builder.block
        if not builder.block.is_terminated:
            builder.branch(merge_block)

        builder.position_at_start(merge_block)

        if value_val.type != else_val.type:
            if isinstance(value_val.type, ir.IntType) and isinstance(else_val.type, ir.IntType):
                if value_val.type.width < else_val.type.width:
                    # Re-open value_end_block: remove its branch terminator,
                    # insert the sext, then re-emit the branch.
                    builder.position_at_end(value_end_block)
                    term = value_end_block.terminator
                    if term is not None:
                        value_end_block.instructions.remove(term)
                        value_end_block.terminator = None
                    value_val = builder.sext(value_val, else_val.type)
                    builder.branch(merge_block)
                    builder.position_at_start(merge_block)
                elif else_val.type.width < value_val.type.width:
                    # Re-open else_end_block: remove its branch terminator,
                    # insert the sext, then re-emit the branch.
                    builder.position_at_end(else_end_block)
                    term = else_end_block.terminator
                    if term is not None:
                        else_end_block.instructions.remove(term)
                        else_end_block.terminator = None
                    else_val = builder.sext(else_val, value_val.type)
                    builder.branch(merge_block)
                    builder.position_at_start(merge_block)
            else:
                raise TypeError(
                    f"If expression branches have incompatible types: "
                    f"{value_val.type} vs {else_val.type} [{node.source_line}:{node.source_col}]")

        phi = builder.phi(value_val.type, name='ifexpr_result')
        phi.add_incoming(value_val, value_end_block)
        phi.add_incoming(else_val, else_end_block)
        return phi

    def visit_WhileLoop(self, node, builder, module):
        func = builder.block.function
        cond_block = func.append_basic_block('while.cond')
        body_block = func.append_basic_block('while.body')
        end_block  = func.append_basic_block('while.end')

        old_break    = getattr(builder, 'break_block', None)
        old_continue = getattr(builder, 'continue_block', None)
        builder.break_block    = end_block
        builder.continue_block = cond_block

        builder.branch(cond_block)

        builder.position_at_start(cond_block)
        _check_not_string_literal(node.condition, 'while', module)
        cond_val = self.visit(node.condition, builder, module)
        cond_val = _coerce_to_bool(builder, cond_val)
        builder.cbranch(cond_val, body_block, end_block)

        builder.position_at_start(body_block)
        self.visit(node.body, builder, module)
        if not builder.block.is_terminated:
            builder.branch(cond_block)

        builder.break_block    = old_break
        builder.continue_block = old_continue

        builder.position_at_start(end_block)
        return None

    def visit_DoLoop(self, node, builder, module):
        if builder.block is None:
            func_type = ir.FunctionType(ir.VoidType(), [])
            temp_func = ir.Function(module, func_type, name="__do_temp")
            temp_block = temp_func.append_basic_block("entry")
            temp_builder = ir.IRBuilder(temp_block)
            self._do_loop_generate(node, temp_builder, module)
            temp_builder.ret_void()
            return None
        return self._do_loop_generate(node, builder, module)

    def _do_loop_generate(self, node, builder, module):
        func = builder.block.function
        body_block = func.append_basic_block('do.body')
        end_block  = func.append_basic_block('do.end')

        old_break    = getattr(builder, 'break_block', None)
        old_continue = getattr(builder, 'continue_block', None)
        builder.break_block    = end_block
        builder.continue_block = body_block

        builder.branch(body_block)

        builder.position_at_start(body_block)
        self.visit(node.body, builder, module)
        if not builder.block.is_terminated:
            builder.branch(body_block)

        builder.break_block    = old_break
        builder.continue_block = old_continue

        builder.position_at_start(end_block)
        return None

    def visit_DoWhileLoop(self, node, builder, module):
        if builder.block is None:
            func_type = ir.FunctionType(ir.VoidType(), [])
            temp_func = ir.Function(module, func_type, name="__dowhile_temp")
            temp_block = temp_func.append_basic_block("entry")
            temp_builder = ir.IRBuilder(temp_block)
            self._do_while_generate(node, temp_builder, module)
            temp_builder.ret_void()
            return None
        return self._do_while_generate(node, builder, module)

    def _do_while_generate(self, node, builder, module):
        func = builder.block.function
        body_block = func.append_basic_block('dowhile.body')
        cond_block = func.append_basic_block('dowhile.cond')
        end_block  = func.append_basic_block('dowhile.end')

        old_break    = getattr(builder, 'break_block', None)
        old_continue = getattr(builder, 'continue_block', None)
        builder.break_block    = end_block
        builder.continue_block = cond_block

        builder.branch(body_block)

        builder.position_at_start(body_block)
        self.visit(node.body, builder, module)
        if not builder.block.is_terminated:
            builder.branch(cond_block)

        builder.position_at_start(cond_block)
        _check_not_string_literal(node.condition, 'do-while', module)
        cond_val = self.visit(node.condition, builder, module)
        builder.cbranch(cond_val, body_block, end_block)

        builder.break_block    = old_break
        builder.continue_block = old_continue

        builder.position_at_start(end_block)
        return None

    def visit_ForLoop(self, node, builder, module):
        func = builder.block.function
        cond_block   = func.append_basic_block('for.cond')
        body_block   = func.append_basic_block('for.body')
        update_block = func.append_basic_block('for.update')
        end_block    = func.append_basic_block('for.end')

        if node.init:
            self.visit(node.init, builder, module)

        builder.branch(cond_block)

        builder.position_at_start(cond_block)
        if node.condition:
            _check_not_string_literal(node.condition, 'for', module)
            cond_val = self.visit(node.condition, builder, module)
            cond_val = _coerce_to_bool(builder, cond_val)
            builder.cbranch(cond_val, body_block, end_block)
        else:
            builder.branch(body_block)

        builder.position_at_start(body_block)
        old_break    = getattr(builder, 'break_block', None)
        old_continue = getattr(builder, 'continue_block', None)
        builder.break_block    = end_block
        builder.continue_block = update_block

        self.visit(node.body, builder, module)
        if not builder.block.is_terminated:
            builder.branch(update_block)

        builder.position_at_start(update_block)
        if node.update:
            self.visit(node.update, builder, module)
        builder.branch(cond_block)

        builder.break_block    = old_break
        builder.continue_block = old_continue

        builder.position_at_start(end_block)
        return None

    def visit_ForInLoop(self, node, builder, module):
        collection = self.visit(node.iterable, builder, module)
        coll_type = collection.type

        func = builder.block.function
        entry_block = builder.block
        cond_block  = func.append_basic_block('forin.cond')
        body_block  = func.append_basic_block('forin.body')
        end_block   = func.append_basic_block('forin.end')

        if isinstance(coll_type, ir.PointerType) and isinstance(coll_type.pointee, ir.ArrayType):
            arr_type  = coll_type.pointee
            size      = arr_type.count
            elem_type = arr_type.element

            index_ptr = builder.alloca(ir.IntType(32), name='forin.idx')
            builder.store(ir.Constant(ir.IntType(32), 0), index_ptr)
            builder.branch(cond_block)

            builder.position_at_start(cond_block)
            current_idx = builder.load(index_ptr, name='idx')
            cmp = builder.icmp_unsigned('<', current_idx,
                                        ir.Constant(ir.IntType(32), size),
                                        name='loop.cond')
            builder.cbranch(cmp, body_block, end_block)

            builder.position_at_start(body_block)
            elem_ptr = builder.gep(collection,
                                   [ir.Constant(ir.IntType(32), 0), current_idx],
                                   name='elem.ptr')
            elem_val = builder.load(elem_ptr, name='elem')
            var_ptr  = builder.alloca(elem_type, name=node.variables[0])
            builder.store(elem_val, var_ptr)
            module.symbol_table.define(node.variables[0], SymbolKind.VARIABLE, llvm_value=var_ptr)

        elif (isinstance(coll_type, ir.PointerType) and
              isinstance(coll_type.pointee, ir.PointerType)):
            elem_ptr_type = coll_type.pointee
            cursor_ptr = builder.alloca(coll_type, name='forin.cursor')
            builder.store(collection, cursor_ptr)
            builder.branch(cond_block)

            builder.position_at_start(cond_block)
            cursor_val = builder.load(cursor_ptr, name='cursor')
            slot_val   = builder.load(cursor_val, name='slot')
            slot_int   = builder.ptrtoint(slot_val, ir.IntType(64), name='slot.int')
            null_int   = ir.Constant(ir.IntType(64), 0)
            cmp = builder.icmp_unsigned('!=', slot_int, null_int, name='loop.cond')
            builder.cbranch(cmp, body_block, end_block)

            builder.position_at_start(body_block)
            var_ptr = builder.alloca(elem_ptr_type, name=node.variables[0])
            builder.store(slot_val, var_ptr)
            module.symbol_table.define(node.variables[0], SymbolKind.VARIABLE, llvm_value=var_ptr)

        elif (isinstance(coll_type, ir.PointerType) and
              isinstance(coll_type.pointee, ir.IntType) and
              coll_type.pointee.width == 8):
            current_ptr = builder.alloca(coll_type, name='char.ptr')
            builder.store(collection, current_ptr)
            builder.branch(cond_block)

            builder.position_at_start(cond_block)
            ptr_val  = builder.load(current_ptr, name='ptr')
            char_val = builder.load(ptr_val, name='char')
            cmp = builder.icmp_unsigned('!=', char_val,
                                        ir.Constant(ir.IntType(8), 0),
                                        name='loop.cond')
            builder.cbranch(cmp, body_block, end_block)

            builder.position_at_start(body_block)
            var_ptr = builder.alloca(ir.IntType(8), name=node.variables[0])
            builder.store(char_val, var_ptr)
            module.symbol_table.define(node.variables[0], SymbolKind.VARIABLE, llvm_value=var_ptr)

        elif (isinstance(coll_type, ir.PointerType) and
              isinstance(coll_type.pointee, ir.IntType) and
              coll_type.pointee.width != 8):
            # Decayed array pointer: int[] stored as i32* (VLA / inferred-size array).
            # Recover the element count from the symbol table type_spec.
            elem_type = coll_type.pointee
            size = None
            if hasattr(node, 'iterable'):
                from fast import Identifier as _Identifier
                if isinstance(node.iterable, _Identifier):
                    entry = module.symbol_table.lookup_any(node.iterable.name)
                    if entry and entry.type_spec is not None:
                        ts = entry.type_spec
                        if ts.array_size is not None:
                            raw = ts.array_size
                            size = raw if isinstance(raw, int) else (
                                raw.value if hasattr(raw, 'value') else int(raw))
                        elif ts.array_dimensions:
                            raw = ts.array_dimensions[0]
                            size = raw if isinstance(raw, int) else (
                                raw.value if hasattr(raw, 'value') else int(raw))
            if size is None:
                raise ValueError(
                    f"Cannot iterate over pointer type {coll_type} — "
                    f"array size not known at compile time [{node.source_line}:{node.source_col}]")

            index_ptr = builder.alloca(ir.IntType(32), name='forin.idx')
            builder.store(ir.Constant(ir.IntType(32), 0), index_ptr)
            builder.branch(cond_block)

            builder.position_at_start(cond_block)
            current_idx = builder.load(index_ptr, name='idx')
            cmp = builder.icmp_unsigned('<', current_idx,
                                        ir.Constant(ir.IntType(32), size),
                                        name='loop.cond')
            builder.cbranch(cmp, body_block, end_block)

            builder.position_at_start(body_block)
            elem_ptr = builder.gep(collection, [current_idx], name='elem.ptr')
            elem_val = builder.load(elem_ptr, name='elem')
            var_ptr  = builder.alloca(elem_type, name=node.variables[0])
            builder.store(elem_val, var_ptr)
            module.symbol_table.define(node.variables[0], SymbolKind.VARIABLE, llvm_value=var_ptr)

        else:
            raise ValueError(f"Cannot iterate over type {coll_type} [{node.source_line}:{node.source_col}]")

        old_break    = getattr(builder, 'break_block', None)
        old_continue = getattr(builder, 'continue_block', None)
        builder.break_block    = end_block
        builder.continue_block = cond_block

        self.visit(node.body, builder, module)

        if not builder.block.is_terminated:
            if isinstance(coll_type, ir.PointerType) and isinstance(coll_type.pointee, ir.ArrayType):
                current_idx = builder.load(index_ptr, name='idx')
                next_idx = builder.add(current_idx, ir.Constant(ir.IntType(32), 1), name='next.idx')
                builder.store(next_idx, index_ptr)
            elif (isinstance(coll_type, ir.PointerType) and
                  isinstance(coll_type.pointee, ir.PointerType)):
                cur = builder.load(cursor_ptr, name='cursor.latch')
                nxt = builder.gep(cur, [ir.Constant(ir.IntType(32), 1)], name='cursor.next')
                builder.store(nxt, cursor_ptr)
            elif (isinstance(coll_type, ir.PointerType) and
                  isinstance(coll_type.pointee, ir.IntType) and
                  coll_type.pointee.width == 8):
                pv  = builder.load(current_ptr, name='ptr.latch')
                nxt = builder.gep(pv, [ir.Constant(ir.IntType(32), 1)], name='ptr.next')
                builder.store(nxt, current_ptr)
            elif (isinstance(coll_type, ir.PointerType) and
                  isinstance(coll_type.pointee, ir.IntType) and
                  coll_type.pointee.width != 8):
                current_idx = builder.load(index_ptr, name='idx')
                next_idx = builder.add(current_idx, ir.Constant(ir.IntType(32), 1), name='next.idx')
                builder.store(next_idx, index_ptr)
            builder.branch(cond_block)

        builder.break_block    = old_break
        builder.continue_block = old_continue
        builder.position_at_start(end_block)
        return None

    def visit_InExpression(self, node, builder, module):
        """
        Codegen for 'needle in haystack' membership-test expressions.

        Returns an i1 (bool): 1 if needle is found in haystack, 0 otherwise.

        Needle shapes
        -------------
        - Scalar (iW)            : single-element membership test.
        - i8*                    : null-terminated string — full substring search.
        - [N x iW]* / iW* array  : contiguous sub-sequence search.

        Haystack shapes
        ---------------
        - i8*       : null-terminated byte string.
        - [N x iW]* : fixed-length array (element count known from type).
        - iW*       : decayed array (element count recovered from symbol table).

        Dispatch matrix
        ---------------
        scalar  needle + string   haystack -> single-char scan (stop at NUL)
        scalar  needle + array    haystack -> single-element scan (bounded)
        sequence needle + string  haystack -> NUL-terminated substring search
        sequence needle + array   haystack -> bounded sub-sequence search
        """
        i1  = ir.IntType(1)
        i8  = ir.IntType(8)
        i32 = ir.IntType(32)

        func = builder.block.function
        from fast import Identifier as _Ident

        # ── Helper: resolve array size from symbol-table entry ────────────────────
        def _array_size_from_sym(ast_node):
            if isinstance(ast_node, _Ident):
                entry = module.symbol_table.lookup_any(ast_node.name)
                if entry and entry.type_spec is not None:
                    ts = entry.type_spec
                    for dim in (ts.array_size,
                                ts.array_dimensions[0] if ts.array_dimensions else None):
                        if dim is not None:
                            return dim if isinstance(dim, int) else (
                                dim.value if hasattr(dim, 'value') else int(dim))
                # Fall back: symbol's llvm_value alloca may have [N x iW] allocated_type
                if entry and entry.llvm_value is not None:
                    lv = entry.llvm_value
                    if hasattr(lv, 'allocated_type') and isinstance(lv.allocated_type, ir.ArrayType):
                        return lv.allocated_type.count
            return None

        # ── Helper: decay [N x iW]* -> iW* via GEP [0,0] ─────────────────────
        def _decay(ptr_val, ast_node=None):
            """Return (decayed_iW_ptr, elem_type, count_or_None).

            Tries three sources for count, in order:
              1. LLVM array type on the pointer itself ([N x iW]*).
              2. The alloca's allocated_type (int[] with inferred literal size).
              3. Symbol-table type_spec (explicit array_size / array_dimensions).
            """
            t = ptr_val.type
            if isinstance(t, ir.PointerType) and isinstance(t.pointee, ir.ArrayType):
                arr  = t.pointee
                zero = ir.Constant(i32, 0)
                decayed = builder.gep(ptr_val, [zero, zero], name='decay.ptr')
                return decayed, arr.element, arr.count
            # Already a plain pointer (iW*) -- recover count from alloca or sym table
            if isinstance(t, ir.PointerType) and isinstance(t.pointee, ir.IntType):
                count = None
                if hasattr(ptr_val, 'allocated_type') and isinstance(ptr_val.allocated_type, ir.ArrayType):
                    count = ptr_val.allocated_type.count
                if count is None and ast_node is not None:
                    count = _array_size_from_sym(ast_node)
                return ptr_val, t.pointee, count
            return ptr_val, None, None

        # ══════════════════════════════════════════════════════════════════════
        # Emit and classify NEEDLE
        # ══════════════════════════════════════════════════════════════════════
        needle_raw  = self.visit(node.needle, builder, module)
        needle_type = needle_raw.type

        # needle_scalar : iW value (single element), OR
        # needle_seq    : (iW* ptr, elem_type, count_or_None)  (sequence)
        needle_scalar = None
        needle_seq    = None

        if isinstance(needle_type, ir.IntType):
            needle_scalar = needle_raw
        elif isinstance(needle_type, ir.PointerType):
            dec_ptr, elem_ty, count = _decay(needle_raw, node.needle)
            if elem_ty is None:
                raise ValueError(
                    f"'in' operator: unsupported needle type {needle_type} "
                    f"[{node.source_line}:{node.source_col}]")
            if count is None:
                # Plain pointer needle (e.g. i8* string variable): treat as
                # NUL-terminated sequence; count stays None (loop stops at NUL).
                count = _array_size_from_sym(node.needle)
            needle_seq = (dec_ptr, elem_ty, count)
        else:
            raise ValueError(
                f"'in' operator: unsupported needle type {needle_type} "
                f"[{node.source_line}:{node.source_col}]")

        # ══════════════════════════════════════════════════════════════════════
        # Emit and classify HAYSTACK
        # ══════════════════════════════════════════════════════════════════════
        haystack_raw  = self.visit(node.haystack, builder, module)
        haystack_type = haystack_raw.type

        # hay_ptr   : iW* (decayed)
        # hay_elem  : element ir.Type
        # hay_count : int (None = NUL-terminated)
        # hay_int   : iW scalar (set when haystack is an integer, for bit-window search)
        hay_int = None
        if isinstance(haystack_type, ir.IntType):
            # Integer haystack: needle must also be a scalar integer.
            # Emit a sliding bit-window: for pos in 0..(H-N) inclusive,
            # check (haystack >> pos) & mask == needle  (mask = (1<<N)-1).
            if needle_scalar is None:
                raise ValueError(
                    f"'in' operator: sequence needle not supported for integer haystack "
                    f"[{node.source_line}:{node.source_col}]")
            hay_w = haystack_type.width
            ndl_w = needle_scalar.type.width
            if ndl_w > hay_w:
                raise ValueError(
                    f"'in' operator: needle width {ndl_w} exceeds haystack width {hay_w} "
                    f"[{node.source_line}:{node.source_col}]")
            # Widen both to the haystack width for uniform arithmetic.
            iHW   = haystack_type
            hay_v = haystack_raw
            ndl_v = builder.zext(needle_scalar, iHW) if ndl_w < hay_w else needle_scalar
            mask  = ir.Constant(iHW, (1 << ndl_w) - 1)
            positions = hay_w - ndl_w + 1   # number of positions to check

            found_block  = func.append_basic_block('in.found')
            notfound_blk = func.append_basic_block('in.notfound')
            merge_block  = func.append_basic_block('in.merge')

            pos_ptr  = builder.alloca(i32, name='in.pos')
            builder.store(ir.Constant(i32, 0), pos_ptr)
            cond_bb  = func.append_basic_block('in.bit.cond')
            body_bb  = func.append_basic_block('in.bit.body')
            builder.branch(cond_bb)

            builder.position_at_start(cond_bb)
            pos  = builder.load(pos_ptr, name='in.pos.v')
            done = builder.icmp_unsigned('==', pos, ir.Constant(i32, positions), name='in.bit.done')
            builder.cbranch(done, notfound_blk, body_bb)

            builder.position_at_start(body_bb)
            pos2    = builder.load(pos_ptr, name='in.pos2')
            if hay_w < 32:
                pos_hw = builder.trunc(pos2, iHW, name='in.pos.hw')
            elif hay_w > 32:
                pos_hw = builder.zext(pos2, iHW, name='in.pos.hw')
            else:
                pos_hw = pos2
            shifted = builder.lshr(hay_v, pos_hw, name='in.shifted')
            window  = builder.and_(shifted, mask, name='in.window')
            hit     = builder.icmp_unsigned('==', window, ndl_v, name='in.hit')
            builder.store(builder.add(pos2, ir.Constant(i32, 1)), pos_ptr)
            builder.cbranch(hit, found_block, cond_bb)

            builder.position_at_start(found_block)
            builder.branch(merge_block)
            builder.position_at_start(notfound_blk)
            builder.branch(merge_block)
            builder.position_at_start(merge_block)
            phi = builder.phi(i1, name='in.result')
            phi.add_incoming(ir.Constant(i1, 1), found_block)
            phi.add_incoming(ir.Constant(i1, 0), notfound_blk)
            return phi

        if isinstance(haystack_type, ir.PointerType):
            hay_ptr, hay_elem, hay_count = _decay(haystack_raw, node.haystack)
            if hay_elem is None:
                raise ValueError(
                    f"'in' operator: unsupported haystack type {haystack_type} "
                    f"[{node.source_line}:{node.source_col}]")
            if hay_count is None:
                # Plain pointer — try symbol table
                hay_count = _array_size_from_sym(node.haystack)
                # If still None and element is i8, treat as NUL-terminated
        else:
            raise ValueError(
                f"'in' operator: unsupported haystack type {haystack_type} "
                f"[{node.source_line}:{node.source_col}]")

        is_nul_haystack = (hay_count is None and
                           isinstance(hay_elem, ir.IntType) and
                           hay_elem.width == 8)

        if hay_count is None and not is_nul_haystack:
            raise ValueError(
                f"'in' operator: cannot determine size of haystack "
                f"'{getattr(node.haystack, 'name', '?')}' "
                f"at compile time [{node.source_line}:{node.source_col}]")

        # ── Common result blocks ───────────────────────────────────────────────
        found_block  = func.append_basic_block('in.found')
        notfound_blk = func.append_basic_block('in.notfound')
        merge_block  = func.append_basic_block('in.merge')

        # ══════════════════════════════════════════════════════════════════════
        # SCALAR NEEDLE
        # ══════════════════════════════════════════════════════════════════════
        if needle_scalar is not None:
            cond_block = func.append_basic_block('in.cond')
            body_block = func.append_basic_block('in.body')

            nv = needle_scalar
            if isinstance(nv.type, ir.IntType) and nv.type != hay_elem:
                nv = builder.trunc(nv, hay_elem) if nv.type.width > hay_elem.width \
                    else builder.zext(nv, hay_elem)

            if is_nul_haystack:
                # Pointer-walk, stop at NUL
                cur_ptr = builder.alloca(hay_ptr.type, name='in.cur')
                builder.store(hay_ptr, cur_ptr)
                builder.branch(cond_block)

                builder.position_at_start(cond_block)
                cur = builder.load(cur_ptr, name='cur')
                ch  = builder.load(cur, name='ch')
                builder.cbranch(
                    builder.icmp_unsigned('==', ch, ir.Constant(hay_elem, 0), name='at.end'),
                    notfound_blk, body_block)

                builder.position_at_start(body_block)
                cur2 = builder.load(cur_ptr, name='cur2')
                ch2  = builder.load(cur2, name='ch2')
                hit  = builder.icmp_unsigned('==', ch2, nv, name='hit')
                builder.store(builder.gep(cur2, [ir.Constant(i32, 1)], name='nxt'), cur_ptr)
                builder.cbranch(hit, found_block, cond_block)
            else:
                # Index-walk, bounded by hay_count
                idx_ptr = builder.alloca(i32, name='in.idx')
                builder.store(ir.Constant(i32, 0), idx_ptr)
                builder.branch(cond_block)

                builder.position_at_start(cond_block)
                idx  = builder.load(idx_ptr, name='idx')
                done = builder.icmp_unsigned('==', idx, ir.Constant(i32, hay_count), name='done')
                builder.cbranch(done, notfound_blk, body_block)

                builder.position_at_start(body_block)
                idx2 = builder.load(idx_ptr, name='idx2')
                ep   = builder.gep(hay_ptr, [idx2], name='ep')
                elem = builder.load(ep, name='elem')
                hit  = builder.icmp_unsigned('==', elem, nv, name='hit')
                builder.store(builder.add(idx2, ir.Constant(i32, 1), name='nxt'), idx_ptr)
                builder.cbranch(hit, found_block, cond_block)

        # ══════════════════════════════════════════════════════════════════════
        # SEQUENCE NEEDLE
        # Two-level loop:
        #   Outer: slide a window over the haystack one element at a time.
        #   Inner: compare each needle element against the window.
        #   Match when all needle elements match (NUL-stop or count-bounded).
        # ══════════════════════════════════════════════════════════════════════
        else:
            ndl_ptr, ndl_elem, ndl_count = needle_seq
            # For i8* (byte-string) needles, always use NUL-termination regardless
            # of any compile-time count.  The stack alloca for a string literal
            # "[N x i8]" includes the NUL terminator in N, so using ndl_count
            # directly would require matching '\0' against a real haystack byte,
            # causing a false "not found" result (e.g. "ll" in str → False).
            if isinstance(ndl_elem, ir.IntType) and ndl_elem.width == 8:
                ndl_count = None
            is_nul_needle = (ndl_count is None and
                             isinstance(ndl_elem, ir.IntType) and
                             ndl_elem.width == 8)

            outer_cond = func.append_basic_block('in.outer.cond')
            outer_body = func.append_basic_block('in.outer.body')
            inner_cond = func.append_basic_block('in.inner.cond')
            inner_body = func.append_basic_block('in.inner.body')
            inner_fail = func.append_basic_block('in.inner.fail')

            # Outer state: current window start index into haystack
            outer_idx_ptr = builder.alloca(i32, name='in.outer.idx')
            builder.store(ir.Constant(i32, 0), outer_idx_ptr)
            builder.branch(outer_cond)

            # ── Outer cond ────────────────────────────────────────────────────
            builder.position_at_start(outer_cond)
            o_idx = builder.load(outer_idx_ptr, name='o.idx')
            if is_nul_haystack:
                # Stop when haystack[outer_idx] == NUL
                hay_ep  = builder.gep(hay_ptr, [o_idx], name='hay.ep')
                hay_ch  = builder.load(hay_ep, name='hay.ch')
                at_end  = builder.icmp_unsigned('==', hay_ch,
                                                ir.Constant(hay_elem, 0), name='hay.end')
                builder.cbranch(at_end, notfound_blk, outer_body)
            else:
                # Stop when outer_idx == hay_count
                done = builder.icmp_unsigned('==', o_idx,
                                             ir.Constant(i32, hay_count), name='hay.done')
                builder.cbranch(done, notfound_blk, outer_body)

            # ── Outer body: reset inner state and start inner loop ────────────
            builder.position_at_start(outer_body)
            inner_ndl_idx_ptr = builder.alloca(i32, name='in.ndl.idx')
            builder.store(ir.Constant(i32, 0), inner_ndl_idx_ptr)
            inner_hay_idx_ptr = builder.alloca(i32, name='in.hay.idx')
            o_idx2 = builder.load(outer_idx_ptr, name='o.idx2')
            builder.store(o_idx2, inner_hay_idx_ptr)
            builder.branch(inner_cond)

            # ── Inner cond: have we exhausted the needle? ─────────────────────
            builder.position_at_start(inner_cond)
            n_idx = builder.load(inner_ndl_idx_ptr, name='n.idx')
            if is_nul_needle:
                # Check needle[n_idx] == NUL  ->  matched
                ndl_ep  = builder.gep(ndl_ptr, [n_idx], name='ndl.ep')
                ndl_ch  = builder.load(ndl_ep, name='ndl.ch')
                ndl_end = builder.icmp_unsigned('==', ndl_ch,
                                                ir.Constant(ndl_elem, 0), name='ndl.end')
                builder.cbranch(ndl_end, found_block, inner_body)
            else:
                # Check n_idx == ndl_count  ->  matched
                ndl_done = builder.icmp_unsigned('==', n_idx,
                                                 ir.Constant(i32, ndl_count), name='ndl.done')
                builder.cbranch(ndl_done, found_block, inner_body)

            # ── Inner body: compare one element ───────────────────────────────
            builder.position_at_start(inner_body)
            n_idx2  = builder.load(inner_ndl_idx_ptr, name='n.idx2')
            h_idx2  = builder.load(inner_hay_idx_ptr, name='h.idx2')

            ndl_ep2 = builder.gep(ndl_ptr, [n_idx2], name='ndl.ep2')
            ndl_el  = builder.load(ndl_ep2, name='ndl.el')

            # Guard: if haystack index is out of bounds (or at NUL), fail
            if is_nul_haystack:
                hay_ep2  = builder.gep(hay_ptr, [h_idx2], name='hay.ep2')
                hay_el   = builder.load(hay_ep2, name='hay.el')
                hay_oob  = builder.icmp_unsigned('==', hay_el,
                                                 ir.Constant(hay_elem, 0), name='hay.oob')
            else:
                hay_oob  = builder.icmp_unsigned('==', h_idx2,
                                                 ir.Constant(i32, hay_count), name='hay.oob')
                hay_ep2  = builder.gep(hay_ptr, [h_idx2], name='hay.ep2')
                hay_el   = builder.load(hay_ep2, name='hay.el')

            # Coerce types if needed (e.g. i8 needle vs i32 haystack)
            if ndl_el.type != hay_el.type:
                if isinstance(ndl_el.type, ir.IntType) and isinstance(hay_el.type, ir.IntType):
                    if ndl_el.type.width < hay_el.type.width:
                        ndl_el = builder.zext(ndl_el, hay_el.type)
                    else:
                        ndl_el = builder.trunc(ndl_el, hay_el.type)

            mismatch = builder.or_(
                hay_oob,
                builder.icmp_unsigned('!=', hay_el, ndl_el, name='el.ne'),
                name='mismatch')

            # Advance both indices
            builder.store(builder.add(n_idx2, ir.Constant(i32, 1)), inner_ndl_idx_ptr)
            builder.store(builder.add(h_idx2, ir.Constant(i32, 1)), inner_hay_idx_ptr)
            builder.cbranch(mismatch, inner_fail, inner_cond)

            # ── Inner fail: advance outer window by 1 and retry ───────────────
            builder.position_at_start(inner_fail)
            o_idx3 = builder.load(outer_idx_ptr, name='o.idx3')
            builder.store(builder.add(o_idx3, ir.Constant(i32, 1)), outer_idx_ptr)
            builder.branch(outer_cond)

        # ── Merge: phi i1 ─────────────────────────────────────────────────────
        builder.position_at_start(found_block)
        builder.branch(merge_block)

        builder.position_at_start(notfound_blk)
        builder.branch(merge_block)

        builder.position_at_start(merge_block)
        phi = builder.phi(i1, name='in.result')
        phi.add_incoming(ir.Constant(i1, 1), found_block)
        phi.add_incoming(ir.Constant(i1, 0), notfound_blk)
        return phi

    def visit_ReturnStatement(self, node, builder, module):
        from fast import Identifier, IfExpression
        if builder.block.is_terminated:
            return None

        if node.value is None:
            if getattr(builder, '_flux_is_recursive_func', False):
                func = builder.block.function
                call_instr = builder.call(func, list(func.args))
                call_instr.tail = "musttail"
            builder.ret_void()
            return None

        if isinstance(node.value, Identifier):
            entry = module.symbol_table.lookup_variable(node.value.name)
            if entry is not None and entry.type_spec is not None and entry.type_spec.is_local:
                raise ValueError(f"Compile error: local variable '{node.value.name}' cannot leave its scope via return [{node.source_line}:{node.source_col}]")

        # Suppress __expr promotion when the function's return type is itself a struct.
        # Without this, "return str_var;" would call str_var.__expr() (yielding e.g. i8*)
        # before coercion can check that the function actually wants the struct back.
        func = builder.block.function
        _ret_type = (func.type.return_type
                     if hasattr(func.type, 'return_type')
                     else func.type.pointee.return_type)
        _suppress = isinstance(_ret_type, (ir.IdentifiedStructType, ir.LiteralStructType))
        if _suppress:
            self._in_member_access = True
        try:
            ret_val = self.visit(node.value, builder, module)
        finally:
            if _suppress:
                self._in_member_access = False

        if hasattr(builder, '_flux_defer_stack') and builder._flux_defer_stack:
            for deferred in reversed(builder._flux_defer_stack):
                if isinstance(deferred, list):
                    for stmt in reversed(deferred):
                        self.visit(stmt, builder, module)
                else:
                    self.visit(deferred, builder, module)

        if ret_val is None:
            builder.ret_void()
            return None

        # After visiting an IfExpression the builder is positioned at the
        # ifexpr_merge block. If that block is already terminated (e.g. a
        # nested return inside one of the arms already emitted a ret), bail.
        if builder.block.is_terminated:
            return None

        func = builder.block.function

        if hasattr(func.type, 'return_type'):
            expected = func.type.return_type
        elif hasattr(func.type, 'pointee') and hasattr(func.type.pointee, 'return_type'):
            expected = func.type.pointee.return_type
        else:
            raise RuntimeError(f"Cannot determine function return type [{node.source_line}:{node.source_col}]")

        if isinstance(expected, ir.VoidType):
            builder.ret_void()
            return None

        if (isinstance(ret_val.type, ir.PointerType) and
                isinstance(ret_val.type.pointee, ir.LiteralStructType) and
                ret_val.type.pointee == expected):
            ret_val = builder.load(ret_val, name="ret_load")

        ret_val = CoercionContext.coerce_return_value(builder, ret_val, expected)

        if getattr(builder, '_flux_is_recursive_func', False):
            func = builder.block.function
            call_instr = builder.call(func, [ret_val])
            call_instr.tail = "musttail"
            builder.ret(call_instr)
            return None

        builder.ret(ret_val)
        return None

    def visit_Case(self, node, builder, module):
        return self.visit(node.body, builder, module)

    def visit_SwitchStatement(self, node, builder, module):
        from fast import Literal, Identifier
        switch_val = self.visit(node.expression, builder, module)

        func = builder.block.function
        merge_block  = func.append_basic_block("switch_merge")
        default_block = None
        case_blocks  = []

        def _fold_case_const(val_expr, switch_val, builder, module):
            if isinstance(val_expr, Literal):
                c = self.visit(val_expr, builder, module)
                if isinstance(c, ir.Constant):
                    return ir.Constant(switch_val.type, c.constant)
            name = getattr(val_expr, 'name', None)
            if name:
                for gname, gval in module.globals.items():
                    if (gname == name or gname.endswith('__' + name)) and hasattr(gval, 'initializer'):
                        init = gval.initializer
                        if isinstance(init, ir.Constant) and isinstance(init.type, ir.IntType):
                            return ir.Constant(switch_val.type, init.constant)
            case_val = self.visit(val_expr, builder, module)
            if isinstance(case_val, ir.Constant):
                return ir.Constant(switch_val.type, case_val.constant)
            src = getattr(case_val, 'operands', [None])
            if src and len(src) > 0:
                init = getattr(src[0], 'initializer', None)
                if isinstance(init, ir.Constant) and isinstance(init.type, ir.IntType):
                    return ir.Constant(switch_val.type, init.constant)
            raise ValueError(f"Switch case value is not a constant integer: {val_expr} [{node.source_line}:{node.source_col}]")

        for i, case in enumerate(node.cases):
            if case.value is None:
                default_block = func.append_basic_block("switch_default")
                case_blocks.append((None, default_block))
            else:
                case_block  = func.append_basic_block(f"switch_case_{i}")
                case_const  = _fold_case_const(case.value, switch_val, builder, module)
                case_blocks.append((case_const, case_block))

        if default_block is None:
            default_block = merge_block

        switch = builder.switch(switch_val, default_block)
        for case_const, block in case_blocks:
            if case_const is not None:
                if isinstance(case_const.type, ir.IntType) and isinstance(switch_val.type, ir.IntType):
                    if case_const.type.width != switch_val.type.width:
                        case_const = ir.Constant(switch_val.type, case_const.constant)
                switch.add_case(case_const, block)

        for i, (value, case_block) in enumerate(case_blocks):
            builder.position_at_start(case_block)

            func_entry = builder.function.entry_basic_block
            saved_block = builder.block

            outer_alloca_block = getattr(builder, '_switch_case_alloca_block', None)
            builder._switch_case_alloca_block = func_entry

            self.visit(node.cases[i].body, builder, module)

            builder._switch_case_alloca_block = outer_alloca_block

            if not builder.block.is_terminated:
                builder.branch(merge_block)

        builder.position_at_start(merge_block)
        return None

    def visit_TryBlock(self, node, builder, module):
        exc_flag  = builder.alloca(ir.IntType(1),  name='exception_flag')
        exc_value = builder.alloca(ir.IntType(64), name='exception_value')

        old_exc_flag  = getattr(builder, 'flux_exception_flag',  None)
        old_exc_value = getattr(builder, 'flux_exception_value', None)

        builder.flux_exception_flag  = exc_flag
        builder.flux_exception_value = exc_value

        func = builder.block.function
        try_block        = func.append_basic_block('try.body')
        catch_check_block = func.append_basic_block('catch.check')
        catch_blocks_ir  = []
        end_block        = func.append_basic_block('try.end')

        for i, (exc_type, exc_name, catch_body) in enumerate(node.catch_blocks):
            catch_block = func.append_basic_block(f'catch.{i}')
            catch_blocks_ir.append(catch_block)

        builder.flux_exception_handler = catch_check_block

        builder.store(ir.Constant(ir.IntType(1), 0), exc_flag)
        builder.branch(try_block)

        builder.position_at_start(try_block)
        self.visit(node.try_body, builder, module)
        if not builder.block.is_terminated:
            builder.branch(catch_check_block)

        builder.position_at_start(catch_check_block)
        exc_flag_val  = builder.load(exc_flag, name='exc_flag')
        zero          = ir.Constant(ir.IntType(32), 0)
        has_exception = builder.icmp_signed('!=', exc_flag_val, zero, name='has_exception')

        if catch_blocks_ir:
            builder.cbranch(has_exception, catch_blocks_ir[0], end_block)
        else:
            builder.cbranch(has_exception, end_block, end_block)

        for i, (exc_type, exc_name, catch_body) in enumerate(node.catch_blocks):
            builder.position_at_start(catch_blocks_ir[i])

            builder.store(ir.Constant(ir.IntType(1), 0), exc_flag)

            if exc_name:
                exc_val_i64 = builder.load(exc_value, name='exc_val')

                if exc_type:
                    exc_type_llvm = TypeSystem.get_llvm_type(exc_type, module)
                else:
                    exc_type_llvm = ir.IntType(64)  # auto -> i64 (preserves pointer-width value)

                exc_var = builder.alloca(exc_type_llvm, name=exc_name)

                if isinstance(exc_type_llvm, ir.IntType):
                    if exc_type_llvm.width < 64:
                        exc_val = builder.trunc(exc_val_i64, exc_type_llvm, name='exc_trunc')
                    elif exc_type_llvm.width > 64:
                        exc_val = builder.zext(exc_val_i64, exc_type_llvm, name='exc_ext')
                    else:
                        exc_val = exc_val_i64
                elif isinstance(exc_type_llvm, ir.PointerType):
                    exc_val = builder.inttoptr(exc_val_i64, exc_type_llvm, name='exc_int_to_ptr')
                else:
                    exc_val = builder.bitcast(exc_val_i64, exc_type_llvm)

                builder.store(exc_val, exc_var)

                if not module.symbol_table.is_global_scope():
                    module.symbol_table.define(exc_name, SymbolKind.VARIABLE, llvm_value=exc_var)

            self.visit(catch_body, builder, module)

            if exc_name and not module.symbol_table.is_global_scope() and module.symbol_table.get_llvm_value(exc_name) is not None:
                module.symbol_table.delete_variable(exc_name)

            if not builder.block.is_terminated:
                builder.branch(end_block)

        builder.flux_exception_flag   = old_exc_flag
        builder.flux_exception_value  = old_exc_value
        builder.flux_exception_handler = None

        builder.position_at_start(end_block)
        return None

    def visit_ThrowStatement(self, node, builder, module):
        if not hasattr(builder, 'flux_exception_flag') or builder.flux_exception_flag is None:
            raise RuntimeError(f"throw statement used outside of try block [{node.source_line}:{node.source_col}]")

        exc_flag  = builder.flux_exception_flag
        exc_value = builder.flux_exception_value

        exc_val = self.visit(node.expression, builder, module)

        if isinstance(exc_val.type, ir.IntType):
            if exc_val.type.width < 64:
                exc_val_i64 = builder.zext(exc_val, ir.IntType(64), name='exc_zext')
            elif exc_val.type.width > 64:
                exc_val_i64 = builder.trunc(exc_val, ir.IntType(64), name='exc_trunc')
            else:
                exc_val_i64 = exc_val
        elif isinstance(exc_val.type, ir.PointerType):
            exc_val_i64 = builder.ptrtoint(exc_val, ir.IntType(64), name='exc_ptr_to_int')
        else:
            exc_val_i64 = builder.bitcast(exc_val, ir.IntType(64))

        builder.store(exc_val_i64, exc_value)
        builder.store(ir.Constant(ir.IntType(1), 1), exc_flag)

        if hasattr(builder, 'flux_exception_handler') and builder.flux_exception_handler is not None:
            builder.branch(builder.flux_exception_handler)
        else:
            builder.unreachable()

        return None

    def visit_AssertStatement(self, node, builder, module):
        from fast import Literal as _Lit
        cond_val = self.visit(node.condition, builder, module)
        cond_val = _coerce_to_bool(builder, cond_val)

        func = builder.block.function
        pass_block = func.append_basic_block('assert.pass')
        fail_block = func.append_basic_block('assert.fail')

        builder.cbranch(cond_val, pass_block, fail_block)

        builder.position_at_start(fail_block)

        if node.message:
            if isinstance(node.message, str):
                import fconfig as _fconfig
                _null_terminate = _fconfig.config.get('null_terminate_strings', '0').strip() == '1'
                msg_str = node.message
                if _null_terminate and (not msg_str or msg_str[-1] != '\0'):
                    msg_str += '\0'
                msg_bytes = msg_str.encode('ascii')
                msg_type  = ir.ArrayType(ir.IntType(8), len(msg_bytes))
                msg_const = ir.Constant(msg_type, bytearray(msg_bytes))
                msg_gv = ir.GlobalVariable(module, msg_type, name=f"assert_msg_{id(node)}")
                msg_gv.initializer    = msg_const
                msg_gv.linkage        = 'internal'
                msg_gv.global_constant = True
                zero    = ir.Constant(ir.IntType(32), 0)
                msg_ptr = builder.gep(msg_gv, [zero, zero], inbounds=True)
            else:
                msg_val = self.visit(node.message, builder, module)
                if isinstance(msg_val.type, ir.PointerType) and isinstance(msg_val.type.pointee, ir.ArrayType):
                    zero    = ir.Constant(ir.IntType(32), 0)
                    msg_ptr = builder.gep(msg_val, [zero, zero], inbounds=True, name="assert_msg_ptr")
                else:
                    msg_ptr = msg_val

            print_fn = module.globals.get('print')
            if print_fn is not None:
                builder.call(print_fn, [msg_ptr])
            else:
                puts_fn = module.globals.get('puts')
                if puts_fn is None:
                    puts_type = ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))])
                    puts_fn   = ir.Function(module, puts_type, 'puts')
                    puts_fn.linkage = 'external'
                builder.call(puts_fn, [msg_ptr])

        exit_proc = module.globals.get('ExitProcess')
        if exit_proc is None:
            exit_proc_type = ir.FunctionType(ir.VoidType(), [ir.IntType(32)])
            exit_proc = ir.Function(module, exit_proc_type, 'ExitProcess')
            exit_proc.linkage = 'external'
        builder.call(exit_proc, [ir.Constant(ir.IntType(32), 1)])
        builder.unreachable()

        builder.position_at_start(pass_block)
        return None

    def visit_FunctionDef(self, node, builder, module):
        # Resolve f-string function names at compile time.
        # A plain string literal name (e.g. def "foo"()) is already resolved to a
        # str by the parser.  An f-string name (e.g. def f"{x} {y}"()) arrives as a
        # FStringLiteral node; we evaluate it here using the same compile-time path
        # that visit_FStringLiteral uses, then replace node.name with the result so
        # the rest of this method sees a plain str, exactly like the string-literal case.
        from fast import FStringLiteral as _FStringLiteral, Stringify as _Stringify
        if isinstance(node.name, _FStringLiteral):
            parts = []
            for part in node.name.parts:
                if isinstance(part, str):
                    clean = part[2:] if part.startswith('f"') else part
                    clean = clean[:-1] if clean.endswith('"') else clean
                    parts.append(clean)
                else:
                    try:
                        parts.append(str(self._fstring_eval_ct(part, node.name, builder, module)))
                    except (ValueError, NotImplementedError) as e:
                        raise ValueError(
                            f"f-string function name contains a runtime-only expression "
                            f"that cannot be evaluated at compile time "
                            f"[{node.source_line}:{node.source_col}]: {e}"
                        ) from e
            node.name = "".join(parts)
        elif isinstance(node.name, _Stringify):
            node.name = self._resolve_stringify_name(node.name, builder, module, node)

        ret_type = FunctionTypeHandler.convert_type_spec_to_llvm(node.return_type, module)

        param_types = []
        param_metadata = FunctionTypeHandler.build_param_metadata(node.parameters, module)
        for param in node.parameters:
            param_type = FunctionTypeHandler.convert_type_spec_to_llvm(param.type_spec, module)
            param_types.append(param_type)

        func_type = ir.FunctionType(ret_type, param_types, var_arg=node.is_variadic)
        mangled_name = SymbolTable.mangle_function_name(node.name, node.parameters, node.return_type, node.no_mangle)

        if mangled_name in module.globals:
            existing_func = module.globals[mangled_name]
            if isinstance(existing_func, ir.Function):
                if node.is_prototype:
                    func = existing_func
                elif existing_func.is_declaration and len(existing_func.args) == len(node.parameters):
                    func = existing_func
                elif existing_func.is_declaration and len(existing_func.args) != len(node.parameters):
                    disambig_name = f"{mangled_name}__{len(node.parameters)}args"
                    if disambig_name in module.globals:
                        func = module.globals[disambig_name]
                    else:
                        func = ir.Function(module, func_type, disambig_name)
                    base_name = node.name.split('::')[-1] if '::' in node.name else node.name
                    SymbolTable.register_function_overload(module, base_name, disambig_name, node.parameters, node.return_type, func)
                else:
                    raise ValueError(f"Function '{node.name}' with signature '{mangled_name}' redefined [{node.source_line}:{node.source_col}]")
            else:
                raise ValueError(f"Name '{mangled_name}' already used for non-function [{node.source_line}:{node.source_col}]")
        else:
            func = ir.Function(module, func_type, mangled_name)
            if hasattr(module, 'symbol_table') and module.symbol_table.current_namespace:
                base_name = node.name
            else:
                base_name = node.name.split('::')[-1] if '::' in node.name else node.name
            #print(f"[FUNC REG] Registering {base_name} (mangled: {mangled_name})", file=sys.stdout)
            SymbolTable.register_function_overload(module, base_name, mangled_name, node.parameters, node.return_type, func)
            # Store default parameter values keyed by mangled name so call sites can inject them.
            defaults = [p.default_value for p in node.parameters]
            if any(d is not None for d in defaults):
                if not hasattr(module, '_func_defaults'):
                    module._func_defaults = {}
                module._func_defaults[mangled_name] = defaults
            #print(f"[FUNC REG] Registered! Overloads for {base_name}: {len(module._function_overloads.get(base_name, []))}", file=sys.stdout)
            if hasattr(module, 'symbol_table'):
                try:
                    #print(f"DEFINING FUNCTION: {base_name} -> {mangled_name}", file=sys.stdout)
                    module.symbol_table.define(
                        base_name,
                        SymbolKind.FUNCTION,
                        type_spec=node.return_type,
                        llvm_type=func_type,
                        llvm_value=func)
                    if base_name != node.name:
                        module.symbol_table.define(
                            node.name,
                            SymbolKind.FUNCTION,
                            type_spec=node.return_type,
                            llvm_type=func_type,
                            llvm_value=func)
                except Exception as e:
                    import traceback as _tb
                    print(f"[ERROR] Failed to register function in symbol table:", file=sys.stdout)
                    print(f"[ERROR]   base_name={base_name}", file=sys.stdout)
                    print(f"[ERROR]   self.name={node.name}", file=sys.stdout)
                    print(f"[ERROR]   mangled_name={mangled_name}", file=sys.stdout)
                    print(f"[ERROR]   symbol_table type: {type(module.symbol_table)}", file=sys.stdout)
                    print(f"[ERROR]   symbol_table.scope_level: {module.symbol_table.scope_level if hasattr(module, 'symbol_table') else 'N/A'}", file=sys.stdout)
                    print(f"[ERROR]   symbol_table.current_namespace: {module.symbol_table.current_namespace if hasattr(module, 'symbol_table') else 'N/A'}", file=sys.stdout)
                    print(f"[ERROR]   symbol_table.scopes: {module.symbol_table.scopes if hasattr(module, 'symbol_table') else 'N/A'}", file=sys.stdout)
                    print(f"[ERROR]   Exception type: {type(e).__name__}", file=sys.stdout)
                    print(f"[ERROR]   Exception: {e}", file=sys.stdout)
                    _tb.print_exc()
                    raise

        if node.is_prototype:
            if node.calling_conv:
                llvm_cc = CALLING_CONV_MAP.get(node.calling_conv, node.calling_conv)
                func.calling_convention = llvm_cc
            return func

        if node.calling_conv:
            llvm_cc = CALLING_CONV_MAP.get(node.calling_conv, node.calling_conv)
            func.calling_convention = llvm_cc

        for i, param in enumerate(func.args):
            if node.parameters[i].name is not None:
                param.name = node.parameters[i].name
            else:
                param.name = f"arg{i}"

        entry_block = func.append_basic_block('entry')
        builder.position_at_start(entry_block)

        # Reset per-function tracking state for tied vars
        builder._untied_vars = set()

        builder._flux_is_recursive_func = node.is_recursive

        builder._flux_label_blocks = {'entry': entry_block}
        for label_name in _collect_label_names(node.body.statements):
            if label_name not in builder._flux_label_blocks:
                builder._flux_label_blocks[label_name] = func.append_basic_block(label_name)

        module.symbol_table.enter_scope()
        if not hasattr(builder, 'initialized_unions'):
            builder.initialized_unions = set()

        for i, param in enumerate(func.args):
            param_name = node.parameters[i].name if node.parameters[i].name is not None else f"arg{i}"
            alloca = builder.alloca(param.type, name=f"{param_name}.addr")
            param_type_spec = node.parameters[i].type_spec
            if param_type_spec is not None:
                alloca._flux_type_spec = param_type_spec
            param_with_metadata = TypeSystem.attach_type_metadata(param, type_spec=param_type_spec)
            builder.store(param_with_metadata, alloca)
            module.symbol_table.define(
                param_name,
                SymbolKind.VARIABLE,
                type_spec=param_type_spec,
                llvm_value=alloca
            )

        if node.is_variadic:
            va_list_type = ir.ArrayType(ir.IntType(8).as_pointer(), 1)
            va_list_alloca = builder.alloca(va_list_type, name="va_list")
            va_list_i8ptr = builder.bitcast(va_list_alloca, ir.IntType(8).as_pointer(), name="va_list_ptr")
            va_start_type = ir.FunctionType(ir.VoidType(), [ir.IntType(8).as_pointer()])
            if 'llvm.va_start' not in module.globals:
                va_start_fn = ir.Function(module, va_start_type, 'llvm.va_start')
            else:
                va_start_fn = module.globals['llvm.va_start']
            builder.call(va_start_fn, [va_list_i8ptr])
            builder._flux_va_list = va_list_alloca
            builder._flux_va_list_i8ptr = va_list_i8ptr
            builder._flux_va_end_fn = None
            va_end_type = ir.FunctionType(ir.VoidType(), [ir.IntType(8).as_pointer()])
            if 'llvm.va_end' not in module.globals:
                va_end_fn = ir.Function(module, va_end_type, 'llvm.va_end')
            else:
                va_end_fn = module.globals['llvm.va_end']
            builder._flux_va_end_fn = va_end_fn

        try:
            self.visit(node.body, builder, module)
        finally:
            module.symbol_table.exit_scope()

        if not builder.block.is_terminated:
            if isinstance(ret_type, ir.VoidType):
                if node.is_recursive:
                    call_instr = builder.call(func, list(func.args))
                    call_instr.tail = "musttail"
                builder.ret_void()
            else:
                raise RuntimeError(f"Function '{node.name}' must end with return statement {_src_loc_with_source(node, module)}")

        return func

    def visit_FunctionPointerDeclaration(self, node, builder, module):
        ptr_type = FunctionPointerType.get_llvm_pointer_type(node.fp_type, module)
        resolved_type_spec = None

        _flux_cc = None
        if node.fp_type.calling_conv:
            _flux_cc = CALLING_CONV_MAP.get(node.fp_type.calling_conv, node.fp_type.calling_conv)

        if not hasattr(module, '_flux_fp_calling_convs'):
            module._flux_fp_calling_convs = {}

        if module.symbol_table.is_global_scope():
            gvar = ir.GlobalVariable(module, ptr_type, node.name)
            gvar.linkage = 'internal'
            if _flux_cc:
                module._flux_fp_calling_convs[node.name] = _flux_cc
            if node.initializer:
                init_val = self.visit(node.initializer, builder, module)
                if isinstance(init_val, ir.Function):
                    init_val = init_val.bitcast(ptr_type)
                elif isinstance(init_val, (ir.GlobalVariable, ir.Constant)) and isinstance(init_val.type, ir.PointerType) and init_val.type != ptr_type:
                    init_val = init_val.bitcast(ptr_type)
                gvar.initializer = init_val
            else:
                gvar.initializer = ir.Constant(ptr_type, None)
            return gvar
        else:
            alloca = builder.alloca(ptr_type, name=node.name)
            if _flux_cc:
                module._flux_fp_calling_convs[node.name] = _flux_cc
            module.symbol_table.define(node.name, SymbolKind.VARIABLE, type_spec=resolved_type_spec, llvm_value=alloca)
            if node.initializer:
                init_val = self.visit(node.initializer, builder, module)
                if isinstance(init_val, ir.Function):
                    func_as_int = builder.ptrtoint(init_val, ir.IntType(64))
                    init_val = builder.inttoptr(func_as_int, ptr_type)
                elif isinstance(init_val.type, ir.IntType):
                    if init_val.type.width != 64:
                        init_val = builder.zext(init_val, ir.IntType(64), name="fp_addr_ext")
                    init_val = builder.inttoptr(init_val, ptr_type, name="fp_from_int")
                elif isinstance(init_val.type, ir.PointerType) and init_val.type != ptr_type:
                    init_val = builder.bitcast(init_val, ptr_type)
                builder.store(init_val, alloca)
            return alloca

    def visit_FunctionPointerAssignment(self, node, builder, module):
        raise NotImplementedError(
            f"FunctionPointerAssignment has no codegen implementation [{node.source_line}:{node.source_col}]")

    def visit_EnumDef(self, node, builder, module):
        if not hasattr(module, '_enum_types'):
            module._enum_types = {}

        if node.name in module._enum_types:
            existing_values = module._enum_types[node.name]
            if not node.values:
                return
            if existing_values:
                raise ValueError(f"Enum '{node.name}' already defined [{node.source_line}:{node.source_col}]")

        module._enum_types[node.name] = node.values

        if not node.values:
            if hasattr(module, 'symbol_table'):
                module.symbol_table.define(
                    node.name, SymbolKind.ENUM,
                    type_spec=None, llvm_type=ir.IntType(32), llvm_value=None)
            return

        if hasattr(module, 'symbol_table'):
            #print(f"[ENUM] Registering enum '{node.name}' in symbol table", file=sys.stdout)
            module.symbol_table.define(
                node.name, SymbolKind.ENUM,
                type_spec=None, llvm_type=ir.IntType(32), llvm_value=None)

        for name, value in node.values.items():
            const_name = f"{node.name}.{name}"
            const_value = ir.Constant(ir.IntType(32), value)
            global_const = ir.GlobalVariable(module, ir.IntType(32), name=const_name)
            global_const.initializer = const_value
            global_const.global_constant = True
            if hasattr(module, 'symbol_table'):
                full_name = f"{node.name}.{name}"
                module.symbol_table.define(
                    full_name, SymbolKind.VARIABLE,
                    type_spec=None, llvm_type=ir.IntType(32), llvm_value=global_const)

    def visit_UnionDef(self, node, builder, module):
        member_types = []
        member_names = []
        max_size = 0
        max_type = None

        for member in node.members:
            member_type = TypeSystem.get_llvm_type(member.type_spec, module)
            if isinstance(member_type, str):
                if hasattr(module, '_type_aliases') and member_type in module._type_aliases:
                    member_type = module._type_aliases[member_type]
                else:
                    raise ValueError(f"Unknown type: {member_type} [{node.source_line}:{node.source_col}]")
            member_types.append(member_type)
            member_names.append(member.name)

            if hasattr(member_type, 'width'):
                size = (member_type.width + 7) // 8
            elif isinstance(member_type, ir.FloatType):
                size = 4
            elif isinstance(member_type, ir.DoubleType):
                size = 8
            elif isinstance(member_type, ir.PointerType):
                size = 8
            elif isinstance(member_type, ir.ArrayType):
                elem = member_type.element
                if hasattr(elem, 'width'):
                    elem_size = (elem.width + 7) // 8
                elif isinstance(elem, ir.FloatType):
                    elem_size = 4
                elif isinstance(elem, ir.DoubleType):
                    elem_size = 8
                else:
                    elem_size = 8
                size = elem_size * member_type.count
            elif isinstance(member_type, ir.LiteralStructType):
                total = 0
                for elem in member_type.elements:
                    if hasattr(elem, 'width'):
                        total += (elem.width + 7) // 8
                    elif isinstance(elem, ir.FloatType):
                        total += 4
                    elif isinstance(elem, ir.DoubleType):
                        total += 8
                    else:
                        total += 8
                size = total
            else:
                size = 8

            if size > max_size:
                max_size = size
                max_type = member_type

        if node.tag_name:
            if not hasattr(module, '_enum_types') or node.tag_name not in module._enum_types:
                raise ValueError(f"Tag '{node.tag_name}' is not a defined enum type [{node.source_line}:{node.source_col}]")
            tag_type = ir.IntType(32)
            data_type = ir.ArrayType(ir.IntType(8), max_size)
            union_type = ir.LiteralStructType([tag_type, data_type])
            union_type.names = [f"{node.name}_tagged"]
        else:
            union_type = ir.LiteralStructType([max_type])
            union_type.names = [node.name]

        if not hasattr(module, '_union_types'):
            module._union_types = {}
        module._union_types[node.name] = union_type

        if not hasattr(module, '_union_member_info'):
            module._union_member_info = {}
        module._union_member_info[node.name] = {
            'member_types': member_types,
            'member_names': member_names,
            'max_size': max_size,
            'tag_name': node.tag_name,
            'is_tagged': bool(node.tag_name)
        }

        if hasattr(module, 'symbol_table'):
            #print(f"[UNION] Registering union '{node.name}' in symbol table", file=sys.stdout)
            module.symbol_table.define(
                node.name, SymbolKind.UNION,
                type_spec=None, llvm_type=union_type, llvm_value=None)

        return union_type

    def visit_StructDef(self, node, builder, module):
        StructTypeHandler.initialize_struct_storage(module)

        if node.name in module._struct_types:
            existing_struct = module._struct_types[node.name]
            if not node.members:
                return existing_struct
            if existing_struct.elements:
                return existing_struct
            opaque_struct = existing_struct
        else:
            opaque_struct = ir.global_context.get_identified_type(node.name)
            opaque_struct.names = []
            module._struct_types[node.name] = opaque_struct

        from fast import StructMember as _StructMember
        # Composition: flatten members from all base structs in declaration order.
        # This handles:  struct BMP : Header, InfoHeader;
        # which is syntactic sugar for inlining all fields from the base structs.
        if not node.members and node.base_structs:
            for base_name in node.base_structs:
                base_specs = module._struct_member_type_specs.get(base_name)
                if base_specs is None:
                    raise RuntimeError(
                        f"Struct composition: base struct '{base_name}' has not been defined "
                        f"before '{node.name}' [{node.source_line}:{node.source_col}]"
                    )
                base_vtable = module._struct_vtables.get(base_name)
                ordered_names = [fname for fname, _, _, _ in base_vtable.fields] if base_vtable else list(base_specs.keys())
                for fname in ordered_names:
                    node.members.append(
                        _StructMember(name=fname, type_spec=base_specs[fname])
                    )

        # Post-composition: append members from post_structs after inline members.
        # struct BMP : Header, InfoHeader { int extra; } : PostData;
        # => fields: [Header fields] [InfoHeader fields] [extra] [PostData fields]
        for base_name in getattr(node, 'post_structs', []):
            base_specs = module._struct_member_type_specs.get(base_name)
            if base_specs is None:
                raise RuntimeError(
                    f"Struct post-composition: struct '{base_name}' has not been defined "
                    f"before '{node.name}' [{node.source_line}:{node.source_col}]"
                )
            base_vtable = module._struct_vtables.get(base_name)
            ordered_names = [fname for fname, _, _, _ in base_vtable.fields] if base_vtable else list(base_specs.keys())
            for fname in ordered_names:
                node.members.append(
                    _StructMember(name=fname, type_spec=base_specs[fname])
                )

        if not node.members:
            return opaque_struct

        node.vtable = node.calculate_vtable(module)

        field_types = [node.vtable.field_types[field_name] for field_name, _, _, _ in node.vtable.fields]
        opaque_struct.set_body(*field_types)
        opaque_struct.names = [field_name for field_name, _, _, _ in node.vtable.fields]

        vtable_constant = node.vtable.to_llvm_constant(module)
        vtable_global = ir.GlobalVariable(module, vtable_constant.type, name=f"{node.name}.TLD")
        vtable_global.initializer = vtable_constant
        vtable_global.linkage = 'internal'
        vtable_global.global_constant = True

        module._struct_vtables[node.name] = node.vtable

        if hasattr(module, 'symbol_table'):
            #print(f"[STRUCT] Registering struct '{node.name}' in symbol table", file=sys.stdout)
            module.symbol_table.define(
                node.name, SymbolKind.STRUCT,
                type_spec=None, llvm_type=opaque_struct, llvm_value=vtable_global)

        member_type_specs = {}
        for member in node.members:
            name = member.name
            type_spec = member.type_spec
            if isinstance(type_spec, TypeSystem) and type_spec.is_array:
                if isinstance(type_spec, DataType):
                    is_signed_value = type_spec in (DataType.SINT, DataType.CHAR, DataType.FLOAT, DataType.DOUBLE)
                elif hasattr(type_spec, 'is_signed'):
                    is_signed_value = type_spec.is_signed
                else:
                    is_signed_value = True
                if hasattr(type_spec, 'custom_typename') and type_spec.custom_typename and hasattr(module, '_type_alias_specs'):
                    if type_spec.custom_typename in module._type_alias_specs:
                        alias_spec = module._type_alias_specs[type_spec.custom_typename]
                        if hasattr(alias_spec, 'is_signed'):
                            is_signed_value = alias_spec.is_signed
                if isinstance(type_spec, TypeSystem):
                    element_type_spec = TypeSystem(
                        base_type=type_spec.base_type,
                        is_signed=is_signed_value,
                        bit_width=type_spec.bit_width if hasattr(type_spec, 'bit_width') else None,
                        custom_typename=type_spec.custom_typename if hasattr(type_spec, 'custom_typename') else None,
                        is_const=type_spec.is_const if hasattr(type_spec, 'is_const') else False,
                        is_volatile=type_spec.is_volatile if hasattr(type_spec, 'is_volatile') else False,
                        storage_class=type_spec.storage_class if hasattr(type_spec, 'storage_class') else None,
                        is_array=False, array_size=None, array_dimensions=None,
                        is_pointer=False, pointer_depth=0
                    )
                elif isinstance(type_spec, DataType):
                    element_type_spec = TypeSystem(
                        base_type=type_spec, is_signed=is_signed_value,
                        bit_width=None, custom_typename=None,
                        is_const=False, is_volatile=False, storage_class=None,
                        is_array=False, array_size=None, array_dimensions=None,
                        is_pointer=False, pointer_depth=0
                    )
                else:
                    raise TypeError(f"Expected TypeSystem or DataType, got {type(type_spec)} [{node.source_line}:{node.source_col}]")
                type_spec.array_element_type = element_type_spec
            member_type_specs[name] = type_spec
        # DEBUG: Print member type specs
        #print(f"[STRUCT] Storing member specs for {node.name}", file=sys.stdout)
        #for mem_name, mem_spec in member_type_specs.items():
        #    print(f"  {mem_name}: is_array={mem_spec.is_array}, array_element_type={mem_spec.array_element_type}", file=sys.stdout)
        #    if mem_spec.array_element_type:
        #        print(f"    element is_signed={mem_spec.array_element_type.is_signed}", file=sys.stdout)
        module._struct_member_type_specs[node.name] = member_type_specs

        if node.storage_class is not None:
            module._struct_storage_classes[node.name] = node.storage_class

        for member in node.members:
            if member.initial_value is not None:
                if not hasattr(module, '_struct_member_defaults'):
                    module._struct_member_defaults = {}
                member_key = f"{node.name}.{member.name}"
                module._struct_member_defaults[member_key] = member.initial_value

        for nested in node.nested_structs:
            self.visit(nested, builder, module)

        return opaque_struct

    def visit_StructFieldAssign(self, node, builder, module):
        instance_ptr = self.visit(node.struct_instance, builder, module)
        instance = builder.load(instance_ptr)
        struct_name = StructTypeHandler.infer_struct_name(instance, module)
        vtable = module._struct_vtables[struct_name]
        new_value = self.visit(node.value, builder, module)
        return StructTypeHandler.assign_field_value(
            builder, module, instance_ptr, struct_name, node.field_name, new_value, vtable)

    def visit_ObjectDef(self, node, builder, module):
        ObjectTypeHandler.initialize_object_storage(module)

        type_already_registered = False
        if hasattr(module, '_struct_types') and node.name in module._struct_types:
            existing_type = module._struct_types[node.name]
            if not node.members and not node.methods:
                return existing_type
            # Consider the type already registered if it has elements (data members),
            # OR if it has no data members but does have methods (methods-only object).
            # Previously only `existing_type.elements` was checked, which is falsy for
            # objects with no member variables — causing the struct and symbol to be
            # re-registered on retry passes, producing "X is already defined" errors
            # when a private method body caused the first visit to raise an exception.
            if existing_type.elements or not node.members:
                struct_type = existing_type
                type_already_registered = True

        if not type_already_registered:
            if not node.members and not node.methods:
                opaque_struct = ir.global_context.get_identified_type(node.name)
                opaque_struct.names = []
                if not hasattr(module, '_struct_types'):
                    module._struct_types = {}
                module._struct_types[node.name] = opaque_struct
                if hasattr(module, 'symbol_table'):
                    module.symbol_table.define(
                        node.name, SymbolKind.OBJECT,
                        type_spec=None, llvm_type=opaque_struct, llvm_value=None)
                return opaque_struct

            member_types, member_names = ObjectTypeHandler.create_member_types(node.members, module)
            struct_type = ObjectTypeHandler.create_struct_type(node.name, member_types, member_names, module)
            fields = ObjectTypeHandler.calculate_field_layout(node.members, member_types)
            ObjectTypeHandler.create_vtable(node.name, fields, module)

            if hasattr(module, 'symbol_table'):
                #print(f"[OBJECT] Registering object '{node.name}' in symbol table", file=sys.stdout)
                module.symbol_table.define(
                    node.name, SymbolKind.OBJECT,
                    type_spec=None, llvm_type=struct_type, llvm_value=None)

        method_funcs = {}
        for method in node.methods:
            func_type, func_name = ObjectTypeHandler.create_method_signature(
                node.name, method.name, method, struct_type, module)
            func = ObjectTypeHandler.predeclare_method(func_type, func_name, method, module)
            method_funcs[func_name] = func

        # Record private method names for access enforcement.
        # We store the fully-qualified "ObjName.method_name" key (plain, not mangled)
        # because visit_MethodCall builds its lookup key the same way:
        #   method_func_name = f"{obj_type_name}.{node.method_name}"
        if not hasattr(module, '_private_methods'):
            module._private_methods = {}
        private_set = set()
        for method in node.methods:
            if getattr(method, 'is_private', False):
                priv_func_name = f"{node.name}.{method.name}"
                private_set.add(priv_func_name)
        if private_set:
            module._private_methods.setdefault(node.name, set()).update(private_set)

        # Only emit method bodies when NOT in pre-pass mode.
        # During the pre-pass, using-namespace functions (e.g. println) are not yet
        # registered, so body emission would fail.  Pass 4 handles body emission after
        # all top-level symbols are available.
        if not getattr(module, '_prepass_only', False):
            for method in node.methods:
                from fast import FunctionDef as _FunctionDef
                if isinstance(method, _FunctionDef) and method.is_prototype:
                    continue
                _, func_name = ObjectTypeHandler.create_method_signature(
                    node.name, method.name, method, struct_type, module)
                func = method_funcs.get(func_name)
                if func is None:
                    raise RuntimeError(f"Internal error: missing function for method {method.name} [{node.source_line}:{node.source_col}]")
                self._emit_method_body(method, func, node.name, module)

        return struct_type

    def visit_ExternBlock(self, node, builder, module):
        for func_def in node.declarations:
            if not func_def.is_prototype:
                raise ValueError(f"Extern functions must be prototypes (no body): {func_def.name} [{node.source_line}:{node.source_col}]")
            ret_type = TypeSystem.get_llvm_type(func_def.return_type, module)
            param_types = [TypeSystem.get_llvm_type(param.type_spec, module) for param in func_def.parameters]
            func_type = ir.FunctionType(ret_type, param_types)
            func_name = func_def.name or ""
            base_name = func_name
            if "::" in base_name:
                base_name = base_name.split("::")[-1]
            if "__" in base_name:
                base_name = base_name.split("__")[-1]
            if func_def.no_mangle:
                final_name = base_name
            else:
                final_name = SymbolTable.mangle_function_name(base_name, func_def.parameters, func_def.return_type, False)
            if final_name in module.globals:
                func = module.globals[final_name]
                if not isinstance(func, ir.Function):
                    raise ValueError(f"Name '{final_name}' already used for non-function [{node.source_line}:{node.source_col}]")
            else:
                func = ir.Function(module, func_type, final_name)
            func.linkage = 'external'
            for i, param in enumerate(func.args):
                if i < len(func_def.parameters):
                    if func_def.parameters[i].name is not None:
                        param.name = func_def.parameters[i].name
                    else:
                        param.name = f"arg{i}"

    # ------------------------------------------------------------------
    # Export block codegen
    # ------------------------------------------------------------------

    def visit_ExportBlock(self, node, builder, module):
        """
        Generate code for an 'export' block.

        Each declaration is a full function definition (not a prototype).
        We delegate to visit_FunctionDef for body emission, then force
        'external' linkage so the symbol is visible to the linker /
        dynamic loader (equivalent to __declspec(dllexport) or
        __attribute__((visibility("default")))).
        """
        for func_def in node.definitions:
            if func_def.is_prototype:
                raise ValueError(
                    f"'export' requires a full definition, not a prototype: '{func_def.name}' "
                    f"[{node.source_line}:{node.source_col}]"
                )
            func = self.visit_FunctionDef(func_def, builder, module)
            # Override the default internal/private linkage set by visit_FunctionDef
            # so that this symbol is exported from the shared library.
            if func is not None:
                func.linkage = 'external'

    def _create_static_init_builder(self, module: ir.Module) -> ir.IRBuilder:
        init_func_name = "__static_init"
        if init_func_name not in module.globals:
            func_type = ir.FunctionType(ir.VoidType(), [])
            init_func = ir.Function(module, func_type, init_func_name)
            block = init_func.append_basic_block("entry")
        else:
            init_func = module.globals[init_func_name]
            if not init_func.blocks:
                block = init_func.append_basic_block("entry")
            else:
                block = init_func.blocks[-1]
                if block.is_terminated:
                    block = init_func.append_basic_block("cont")
        builder = ir.IRBuilder(block)
        builder.initialized_unions = set()
        return builder

    def _finalize_static_init(self, module: ir.Module) -> None:
        if "__static_init" in module.globals:
            init_func = module.globals["__static_init"]
            if init_func.blocks and not init_func.blocks[-1].is_terminated:
                final_builder = ir.IRBuilder(init_func.blocks[-1])
                final_builder.ret_void()

    def _run_in_namespace(self, namespace: str, item, builder, module: ir.Module,
                          codegen_attr: str = 'codegen') -> None:
        """Set namespace context, call item.<codegen_attr>(builder, module), restore."""
        original_name = item.name
        item.name = f"{namespace.replace('::', '__')}__{item.name}"
        orig_mod_ns = getattr(module, '_current_namespace', '')
        orig_st_ns = module.symbol_table.current_namespace if hasattr(module, 'symbol_table') else ''
        module._current_namespace = namespace
        if hasattr(module, 'symbol_table'):
            module.symbol_table.set_namespace(namespace)
        try:
            method = getattr(item, codegen_attr)
            if codegen_attr == 'codegen_type_only':
                method(module)
            else:
                method(builder, module)
        finally:
            item.name = original_name
            module._current_namespace = orig_mod_ns
            if hasattr(module, 'symbol_table'):
                module.symbol_table.set_namespace(orig_st_ns)

    def _ns_struct(self, namespace: str, struct_def, builder, module: ir.Module) -> None:
        self._run_in_namespace(namespace, struct_def, builder, module, 'codegen')

    def _ns_object_type_only(self, namespace: str, obj_def, module: ir.Module) -> None:
        self._run_in_namespace(namespace, obj_def, None, module, 'codegen_type_only')

    def _ns_object(self, namespace: str, obj_def, builder, module: ir.Module) -> None:
        self._run_in_namespace(namespace, obj_def, builder, module, 'codegen')

    def _ns_enum(self, namespace: str, enum_def, builder, module: ir.Module) -> None:
        self._run_in_namespace(namespace, enum_def, builder, module, 'codegen')

    def _ns_variable(self, namespace: str, var_def, module: ir.Module):
        original_name = var_def.name
        var_def.name = f"{namespace.replace('::', '__')}__{var_def.name}"
        orig_mod_ns = getattr(module, '_current_namespace', '')
        orig_st_ns = module.symbol_table.current_namespace if hasattr(module, 'symbol_table') else ''
        module._current_namespace = namespace
        if hasattr(module, 'symbol_table'):
            module.symbol_table.set_namespace(namespace)
        try:
            return var_def.codegen(None, module)
        finally:
            var_def.name = original_name
            module._current_namespace = orig_mod_ns
            if hasattr(module, 'symbol_table'):
                module.symbol_table.set_namespace(orig_st_ns)

    def _ns_function(self, namespace: str, func_def, builder, module: ir.Module) -> None:
        original_name = func_def.name
        func_def.name = f"{namespace}__{func_def.name}"
        orig_mod_ns = getattr(module, '_current_namespace', '')
        orig_st_ns = module.symbol_table.current_namespace if hasattr(module, 'symbol_table') else ''
        module._current_namespace = namespace
        if hasattr(module, 'symbol_table'):
            module.symbol_table.set_namespace(namespace)
        try:
            func_def.codegen(builder, module)
        finally:
            func_def.name = original_name
            module._current_namespace = orig_mod_ns
            if hasattr(module, 'symbol_table'):
                module.symbol_table.set_namespace(orig_st_ns)

    def _ns_nested(self, parent_namespace: str, nested_ns, builder, module: ir.Module) -> None:
        original_name = nested_ns.name
        full_nested_name = f"{parent_namespace}__{nested_ns.name}"
        nested_ns.name = full_nested_name
        orig_mod_ns = getattr(module, '_current_namespace', '')
        orig_st_ns = module.symbol_table.current_namespace if hasattr(module, 'symbol_table') else ''
        module._current_namespace = full_nested_name
        if hasattr(module, 'symbol_table'):
            module.symbol_table.set_namespace(full_nested_name)
        try:
            nested_ns.codegen(builder, module)
        finally:
            nested_ns.name = original_name
            if hasattr(module, 'symbol_table'):
                module.symbol_table.set_namespace(orig_st_ns)

    # ------------------------------------------------------------------
    # Object method body codegen (moved from ObjectTypeHandler)
    # ------------------------------------------------------------------

    def _emit_method_body(self, method, func: ir.Function, object_name: str, module: ir.Module) -> None:
        from fast import DataType as _DataType, TypeSystem as _TypeSystem, FunctionDef as _FunctionDef
        if isinstance(method, _FunctionDef) and method.is_prototype:
            return
        if len(func.blocks) != 0:
            # If the existing entry block is already properly terminated, the method
            # was fully emitted on a previous pass — skip it.
            # If it is *not* terminated, it was partially emitted during an earlier
            # failed attempt (e.g. a function-resolution error in the pre-pass retry
            # loop).  In that case we must wipe the stale block and re-emit the body
            # now that all symbols are available, otherwise the function is left with
            # an unterminated block and LLC rejects the IR.
            if func.blocks[0].is_terminated:
                return
            # Remove the stale partial block so we can start fresh.
            func.blocks.clear()
        entry_block = func.append_basic_block('entry')
        method_builder = ir.IRBuilder(entry_block)
        saved_namespace = module.symbol_table.current_namespace
        prev_object_name = getattr(module, '_current_object_name', None)
        module._current_object_name = object_name
        module.symbol_table.enter_scope()
        this_type_spec = _TypeSystem(base_type=_DataType.DATA, custom_typename=object_name, is_pointer=True)
        module.symbol_table.define(
            "this", SymbolKind.VARIABLE,
            llvm_value=func.args[0], type_spec=this_type_spec)
        for i, param in enumerate(func.args[1:], 1):
            param_name = method.parameters[i - 1].name if method.parameters[i - 1].name is not None else f"arg{i - 1}"
            alloca = method_builder.alloca(param.type, name=f"{param_name}.addr")
            param_type_spec = method.parameters[i - 1].type_spec
            if param_type_spec is not None:
                alloca._flux_type_spec = param_type_spec
            param_with_metadata = TypeSystem.attach_type_metadata(param, type_spec=param_type_spec)
            method_builder.store(param_with_metadata, alloca)
            module.symbol_table.define(param_name, SymbolKind.VARIABLE, type_spec=param_type_spec, llvm_value=alloca)
        try:
            self.visit(method.body, method_builder, module)
            if isinstance(method, _FunctionDef) and method.name == '__init' and not method_builder.block.is_terminated:
                method_builder.ret(func.args[0])
            if not method_builder.block.is_terminated:
                if isinstance(func.function_type.return_type, ir.VoidType):
                    method_builder.ret_void()
                else:
                    raise RuntimeError(f"CodegenVisitor._emit_method_body: Method {method.name} must end with return statement")
        finally:
            module.symbol_table.exit_scope()
            module.symbol_table.current_namespace = saved_namespace
            module._current_object_name = prev_object_name
        return

    def visit_NamespaceDef(self, node, builder, module):
        if hasattr(module, '_excluded_namespaces'):
            if node.name in module._excluded_namespaces:
                #print(f"[NAMESPACE] Skipping excluded namespace: {node.name}", file=sys.stdout)
                return
            for excluded_ns in module._excluded_namespaces:
                if node.name.startswith(excluded_ns + "__"):
                    #print(f"[NAMESPACE] Skipping namespace {node.name} (parent {excluded_ns} is excluded)", file=sys.stdout)
                    return

        #print(f"[NAMESPACE] Processing namespace: {node.name}", file=sys.stdout)
        #print(f"[NAMESPACE]   Functions: {len(node.functions)}", file=sys.stdout)
        #print(f"[NAMESPACE]   Nested namespaces: {len(node.nested_namespaces)}", file=sys.stdout)
        SymbolTable.register_namespace(module, node.name)

        for nested_ns in node.nested_namespaces:
            full_nested_name = f"{node.name}__{nested_ns.name}"
            #print("FULL NESTED NAME:", full_nested_name)
            SymbolTable.register_namespace(module, full_nested_name)
            SymbolTable.register_nested_namespaces(nested_ns, full_nested_name, module)

        #NamespaceTypeHandler.add_using_namespace(module, node.name)

        if not hasattr(module, 'symbol_table'):
            raise RuntimeError(f"Module must have symbol_table for namespace support [{node.source_line}:{node.source_col}]")

        original_namespace = module.symbol_table.current_namespace
        module.symbol_table.set_namespace(node.name)

        if builder is None or not hasattr(builder, 'block') or builder.block is None:
            work_builder = self._create_static_init_builder(module)
        else:
            work_builder = builder

        for nested_ns in node.nested_namespaces:
            self._ns_nested(node.name, nested_ns, work_builder, module)

        for var in node.variables:
            try:
                self._ns_variable(node.name, var, module)
            except Exception as e:
                var_name = getattr(var, 'name', '<unknown>')
                print(f"\nError processing variable '{var_name}' in namespace '{node.name}':")
                import traceback as _tb
                _tb.print_exc()
                raise

        for enum in node.enums:
            self._ns_enum(node.name, enum, work_builder, module)

        for struct in node.structs:
            self._ns_struct(node.name, struct, work_builder, module)

        for extern_block in node.extern_blocks:
            self.visit(extern_block, work_builder, module)

        for obj in node.objects:
            from fast import TraitDef as _TraitDef
            if not isinstance(obj, _TraitDef):
                self._ns_object_type_only(node.name, obj, module)

        for func in node.functions:
            self._ns_function(node.name, func, work_builder, module)

        for obj in node.objects:
            from fast import TraitDef as _TraitDef
            if isinstance(obj, _TraitDef):
                self.visit(obj, work_builder, module)
            else:
                self._ns_object(node.name, obj, work_builder, module)

        self._finalize_static_init(module)

        module._current_namespace = original_namespace
        module.symbol_table.set_namespace(original_namespace)
        return None

    def visit_FunctionDefStatement(self, node, builder, module):
        self.visit(node.function_def, builder, module)
        return None

    # ------------------------------------------------------------------
    # Expression macros (macro)
    # ------------------------------------------------------------------

    def visit_macroDefStatement(self, node, builder, module):
        """
        macroDef is a compile-time-only construct.
        The definition was already registered into the parser's _macros table
        during parsing; there is nothing to emit into LLVM IR here.
        """
        return None

    def visit_macroDef(self, node, builder, module):
        """Direct visit of the macroDef node — also a no-op at codegen time."""
        return None

    def visit_ContractDef(self, node, builder, module):
        """
        ContractDef is a compile-time-only construct.
        Contract body statements are inlined into the top of each annotated
        function body at parse time (by fparser.py's function_def()).
        There is nothing to emit into LLVM IR here.
        """
        return None

    def visit_macroCall(self, node, builder, module):
        """
        Expand an expression macro call inline.

        Steps:
          1. Look up the macroDef that was registered at parse time.
          2. Deep-copy the body expression so each call site gets an independent
             AST subtree (important for nested/recursive expansion and for
             location stamping).
          3. Walk the copy, substituting every Identifier whose name matches a
             macro parameter with the corresponding caller argument expression
             (also deep-copied so the same argument can appear multiple times).
          4. Codegen the substituted body — it's a plain Expression at this point
             and goes through the normal visitor dispatch.

        Arity is checked eagerly so the error message points at the call site.
        """
        import copy

        # ── 1. Locate the definition ──────────────────────────────────────────
        macro_def = None
        if hasattr(module, '_macros'):
            macro_def = module._macros.get(node.name)
        # Fall back to the parser-side table carried on the module (if wired up)
        if macro_def is None and hasattr(module, '_parser_macros'):
            macro_def = module._parser_macros.get(node.name)

        if macro_def is None:
            raise NameError(
                f"Unknown expression macro '{node.name}' "
                f"[{node.source_line}:{node.source_col}]"
            )

        # ── 2. Arity check ────────────────────────────────────────────────────
        if len(node.arguments) != len(macro_def.params):
            raise TypeError(
                f"Expression macro '{node.name}' expects {len(macro_def.params)} "
                f"argument(s), got {len(node.arguments)} "
                f"[{node.source_line}:{node.source_col}]"
            )

        # ── 3. Build substitution map: param_name -> deep-copied arg expression
        subst = {
            param: copy.deepcopy(arg)
            for param, arg in zip(macro_def.params, node.arguments)
        }

        # ── 4. Deep-copy the body and substitute ─────────────────────────────
        body_copy = copy.deepcopy(macro_def.body)
        expanded  = self._macro_substitute(body_copy, subst)

        # ── 5. Codegen the expanded expression ───────────────────────────────
        return self.visit(expanded, builder, module)

    @staticmethod
    def _macro_substitute(node, subst: dict):
        """
        Recursively walk an AST subtree and replace every Identifier whose
        name is a key in `subst` with the corresponding argument node.

        Returns the (possibly replaced) node.  All mutations happen on the
        already-deep-copied tree so the original macroDef body is untouched.
        """
        from fast import (Identifier, BinaryOp, UnaryOp, FunctionCall,
                          ArrayAccess, MemberAccess, MethodCall, CastExpression,
                          TypeConvertExpression, TernaryOp, NullCoalesce,
                          NotNull, AddressOf, PointerDeref, ArrayLiteral,
                          ArrayComprehension, RangeExpression, IfExpression,
                          macroCall)
        import copy

        if isinstance(node, Identifier):
            if node.name in subst:
                return copy.deepcopy(subst[node.name])
            return node

        if isinstance(node, BinaryOp):
            node.left  = CodegenVisitor._macro_substitute(node.left,  subst)
            node.right = CodegenVisitor._macro_substitute(node.right, subst)
            return node

        if isinstance(node, UnaryOp):
            node.operand = CodegenVisitor._macro_substitute(node.operand, subst)
            return node

        if isinstance(node, TernaryOp):
            node.condition  = CodegenVisitor._macro_substitute(node.condition,  subst)
            node.true_expr  = CodegenVisitor._macro_substitute(node.true_expr,  subst)
            node.false_expr = CodegenVisitor._macro_substitute(node.false_expr, subst)
            return node

        if isinstance(node, NullCoalesce):
            node.left  = CodegenVisitor._macro_substitute(node.left,  subst)
            node.right = CodegenVisitor._macro_substitute(node.right, subst)
            return node

        if isinstance(node, NotNull):
            node.operand = CodegenVisitor._macro_substitute(node.operand, subst)
            return node

        if isinstance(node, (CastExpression, TypeConvertExpression)):
            node.expression = CodegenVisitor._macro_substitute(node.expression, subst)
            return node

        if isinstance(node, FunctionCall):
            node.arguments = [
                CodegenVisitor._macro_substitute(a, subst) for a in node.arguments
            ]
            return node

        if isinstance(node, macroCall):
            # Nested macro call — substitute into its arguments too
            node.arguments = [
                CodegenVisitor._macro_substitute(a, subst) for a in node.arguments
            ]
            return node

        if isinstance(node, ArrayAccess):
            node.array = CodegenVisitor._macro_substitute(node.array, subst)
            node.index = CodegenVisitor._macro_substitute(node.index, subst)
            return node

        if isinstance(node, MemberAccess):
            node.object = CodegenVisitor._macro_substitute(node.object, subst)
            return node

        if isinstance(node, MethodCall):
            node.object    = CodegenVisitor._macro_substitute(node.object, subst)
            node.arguments = [
                CodegenVisitor._macro_substitute(a, subst) for a in node.arguments
            ]
            return node

        if isinstance(node, AddressOf):
            node.expression = CodegenVisitor._macro_substitute(node.expression, subst)
            return node

        if isinstance(node, PointerDeref):
            node.pointer = CodegenVisitor._macro_substitute(node.pointer, subst)
            return node

        if isinstance(node, ArrayLiteral):
            node.elements = [
                CodegenVisitor._macro_substitute(e, subst) for e in node.elements
            ]
            return node

        if isinstance(node, RangeExpression):
            node.start = CodegenVisitor._macro_substitute(node.start, subst)
            node.end   = CodegenVisitor._macro_substitute(node.end,   subst)
            if node.step is not None:
                node.step = CodegenVisitor._macro_substitute(node.step, subst)
            return node

        if isinstance(node, ArrayComprehension):
            node.expression = CodegenVisitor._macro_substitute(node.expression, subst)
            node.iterable   = CodegenVisitor._macro_substitute(node.iterable,   subst)
            if node.condition is not None:
                node.condition = CodegenVisitor._macro_substitute(node.condition, subst)
            return node

        if isinstance(node, IfExpression):
            node.value_expr = CodegenVisitor._macro_substitute(node.value_expr, subst)
            node.condition  = CodegenVisitor._macro_substitute(node.condition,  subst)
            if node.else_expr is not None:
                node.else_expr = CodegenVisitor._macro_substitute(node.else_expr, subst)
            return node

        # Literals, SizeOf, AlignOf, Stringify, etc. — nothing to substitute
        return node

    def visit_EnumDefStatement(self, node, builder, module):
        self.visit(node.enum_def, builder, module)
        return None

    def visit_UnionDefStatement(self, node, builder, module):
        self.visit(node.union_def, builder, module)
        return None

    def visit_StructDefStatement(self, node, builder, module):
        self.visit(node.struct_def, builder, module)
        return None

    def visit_ObjectDefStatement(self, node, builder, module):
        self.visit(node.object_def, builder, module)
        return None

    def visit_NamespaceDefStatement(self, node, builder, module):
        if (hasattr(module, '_excluded_namespaces') and
                node.namespace_def.name in module._excluded_namespaces):
            return None
        self.visit(node.namespace_def, builder, module)
        return None

    def _try_expr_method(self, ptr, builder, module):
        """
        If the LLVM value `ptr` is a pointer to an object type that has a
        __expr() method, call that method with `this = ptr` and return the
        result.  Returns None if the object has no __expr, so the caller can
        fall through to its normal behaviour.

        This implements expression-context promotion:
            print(str);   // calls str.__expr() transparently

        NOT called when visiting the object of a member access (str.val) or
        method call (str.foo()) — those need the raw struct pointer.

        Handles two common alloca shapes:
          1. alloca of struct:            ptr.type == %ObjName*   (this_ptr = ptr)
          2. alloca of pointer to struct: ptr.type == %ObjName**  (this_ptr = load ptr)
        """
        # Suppressed when we're resolving the LHS of a member access or method call
        if getattr(self, '_in_member_access', False):
            return None

        if not isinstance(ptr.type, ir.PointerType):
            return None

        pointee = ptr.type.pointee

        # Shape 2: alloca holding a pointer to struct (e.g. heap-allocated object)
        if isinstance(pointee, ir.PointerType) and isinstance(pointee.pointee, ir.IdentifiedStructType):
            struct_type = pointee.pointee
            this_ptr = builder.load(ptr, name="obj_this")
        # Shape 1: alloca IS the struct (stack-allocated object, most common case)
        elif isinstance(pointee, ir.IdentifiedStructType):
            struct_type = pointee
            this_ptr = ptr
        else:
            return None

        # Use the struct's own LLVM name directly — it's always the canonical mangled
        # key (e.g. "standard__strings__string") matching what predeclare_method
        # registered.  Iterating _struct_types risks hitting a short alias (e.g.
        # "string") before the fully-qualified name, producing the wrong lookup key.
        obj_type_name = struct_type.name
        if not obj_type_name:
            return None

        # __expr takes no user arguments (this is implicit and not counted in param_count).
        # Pass [] for overload resolution so param_count==0 matches correctly.
        expr_base_name = f"{obj_type_name}.__expr"
        expr_func = TypeResolver.resolve_function(module, expr_base_name, "", [])

        # Also try using-namespace mangled names
        if expr_func is None and hasattr(module, '_using_namespaces'):
            current_ns = TypeResolver.get_current_namespace(module)
            for ns in module._using_namespaces:
                mangled = f"{ns.replace('::', '__')}__{expr_base_name}"
                expr_func = TypeResolver.resolve_function(module, mangled, current_ns, [])
                if expr_func:
                    break

        if expr_func is None:
            return None

        result = builder.call(expr_func, [this_ptr], name=f"{obj_type_name}_expr")
        result._from_expr_method = True
        return result

    def visit_Identifier(self, node, builder, module):
        #print(f"[IDENTIFIER] Looking up '{node.name}'", file=sys.stdout)
        #print(f"[IDENTIFIER]   Scope level: {module.symbol_table.scope_level}", file=sys.stdout)
        #print(f"[IDENTIFIER]   Scopes count: {len(module.symbol_table.scopes)}", file=sys.stdout)

        # Look up the name in the current scope
        if not module.symbol_table.is_global_scope() and module.symbol_table.get_llvm_value(node.name) is not None:
            ptr = module.symbol_table.get_llvm_value(node.name)

            # Get type information if available
            type_spec = TypeResolver.resolve_type_spec(node.name, module)
            #print("TYPE SPEC FROM TYPE RESOLVER:",type_spec)

            # Check validity (use after untie)
            IdentifierTypeHandler.check_validity(node.name, builder)

            # Handle special case for 'this' pointer
            if node.name == "this":
                return TypeSystem.attach_type_metadata(ptr, type_spec)

            # Expression-context promotion: if this is an object variable with
            # __expr() defined, call it and return its result transparently.
            # We check here, before the load/pointer branching, so it fires
            # regardless of how should_return_pointer classifies the variable.
            expr_result = self._try_expr_method(ptr, builder, module)
            if expr_result is not None:
                return expr_result

            # For arrays and structs, return the pointer directly (don't load)
            if IdentifierTypeHandler.should_return_pointer(ptr, type_spec):
                return TypeSystem.attach_type_metadata(ptr, type_spec)

            # Load the value if it's a non-array, non-struct pointer type
            elif isinstance(ptr.type, ir.PointerType):
                ret_val = builder.load(ptr, name=node.name)
                if hasattr(ptr, '_flux_type_spec'):
                    ret_val._flux_type_spec = ptr._flux_type_spec
                if IdentifierTypeHandler.is_volatile(node.name, builder):
                    ret_val.volatile = True
                # Attach type metadata to loaded value from multiple sources
                if not hasattr(ret_val, '_flux_type_spec'):
                    # Priority 1: Check scope_type_info
                    if type_spec:
                        ret_val._flux_type_spec = type_spec
                    # Priority 2: Check if alloca itself has metadata
                    elif hasattr(ptr, '_flux_type_spec'):
                        ret_val._flux_type_spec = ptr._flux_type_spec
                return ret_val

            # For non-pointer types, attach metadata and return
            return TypeSystem.attach_type_metadata(ptr, type_spec)

        # Check for global variables
        if node.name in module.globals:
            gvar = module.globals[node.name]
            type_spec = module.symbol_table.get_type_spec(node.name)

            # Expression-context promotion for global object variables
            expr_result = self._try_expr_method(gvar, builder, module)
            if expr_result is not None:
                return expr_result

            # For arrays and structs, return the pointer directly (don't load)
            if IdentifierTypeHandler.should_return_pointer(gvar, type_spec):
                return TypeSystem.attach_type_metadata(gvar, type_spec)

            # Load the value if it's a non-array, non-struct pointer type
            elif isinstance(gvar.type, ir.PointerType):
                ret_val = builder.load(gvar, name=node.name)
                if IdentifierTypeHandler.is_volatile(node.name, builder):
                    ret_val.volatile = True
                return TypeSystem.attach_type_metadata(ret_val, type_spec)
            return TypeSystem.attach_type_metadata(gvar, type_spec)

        # Check if this is a custom type
        if IdentifierTypeHandler.is_type_alias(node.name, module):
            return module._type_aliases[node.name]

        # Check for namespace-qualified names using 'using' statements
        mangled_name = IdentifierTypeHandler.resolve_namespace_mangled_name(node.name, module)
        if mangled_name:
            # Check in global variables with mangled name
            if mangled_name in module.globals:
                gvar = module.globals[mangled_name]
                type_spec = module.symbol_table.get_type_spec(mangled_name)

                # Expression-context promotion for namespace-mangled global object variables
                expr_result = self._try_expr_method(gvar, builder, module)
                if expr_result is not None:
                    return expr_result

                # For arrays and structs, return the pointer directly (don't load)
                if IdentifierTypeHandler.should_return_pointer(gvar, type_spec):
                    return TypeSystem.attach_type_metadata(gvar, type_spec)
                # Load the value if it's a non-array, non-struct pointer type
                elif isinstance(gvar.type, ir.PointerType):
                    ret_val = builder.load(gvar, name=node.name)
                    if IdentifierTypeHandler.is_volatile(node.name, builder):
                        ret_val.volatile = True
                    return TypeSystem.attach_type_metadata(ret_val, type_spec)

                return TypeSystem.attach_type_metadata(gvar, type_spec)

            # Check in type aliases with mangled name
            if IdentifierTypeHandler.is_type_alias(mangled_name, module):
                return module._type_aliases[mangled_name]

        raise NameError(f"Unknown identifier: {node.name} [{node.source_line}:{node.source_col}]")

    def visit_VariableDeclaration(self, node, builder, module):
        # Resolve type (with automatic array size inference if needed)
        resolved_type_spec = VariableTypeHandler.infer_array_size(node.type_spec, node.initial_value, module)
        llvm_type = TypeSystem.get_llvm_type(resolved_type_spec, module, include_array=True, node=node)
        #print(f"[VAR DECL] name={node.name}, type_spec={resolved_type_spec}, llvm_type={llvm_type}", file=sys.stdout)

        # Check if this is global scope
        is_global_scope = (
            builder is None or
            node.is_global or
            module.symbol_table.is_global_scope()
        )

        # Handle global variables
        if is_global_scope:
            return self._vardecl_global(node, module, llvm_type, resolved_type_spec)

        # Handle local variables
        return self._vardecl_local(node, builder, module, llvm_type, resolved_type_spec)

    def _vardecl_global(self, node, module, llvm_type, resolved_type_spec):
        """Generate code for global variable."""
        from fast import NoInit as _NoInit
        # Check if global already exists
        if node.name in module.globals:
            return module.globals[node.name]

        # Check for namespaced duplicates
        base_name = node.name.split('__')[-1]
        for existing_name in list(module.globals.keys()):
            existing_base_name = existing_name.split('__')[-1]
            if existing_base_name == base_name and existing_name != node.name:
                return module.globals[existing_name]
            elif existing_name == node.name:
                return module.globals[existing_name]

        # Create new global
        gvar = ir.GlobalVariable(module, llvm_type, node.name)

        # Handle noinit for global variables
        if isinstance(node.initial_value, _NoInit):
            gvar.initializer = ir.Undefined(llvm_type)
        # Set initializer if value provided
        elif node.initial_value:
            init_const = self._vardecl_create_global_initializer(node, module, llvm_type)
            if init_const is not None:
                gvar.initializer = init_const
            else:
                gvar.initializer = TypeSystem.get_default_initializer(llvm_type)
        else:
            # Default behavior: zero-initialize
            gvar.initializer = TypeSystem.get_default_initializer(llvm_type)

        gvar.linkage = 'internal'

        # Register global variable in symbol table
        if hasattr(module, 'symbol_table'):
            #print(f"[GLOBAL VAR] Registering global variable '{node.name}' in symbol table", file=sys.stdout)
            module.symbol_table.define(
                node.name,
                SymbolKind.VARIABLE,
                type_spec=resolved_type_spec,
                llvm_type=llvm_type,
                llvm_value=gvar
            )

        return gvar

    def _vardecl_create_global_initializer(self, node, module, llvm_type):
        """Create compile-time constant initializer for global variable."""
        return VariableTypeHandler.create_global_initializer(node.initial_value, llvm_type, module)

    def _vardecl_singinit(self, node, builder, module, llvm_type, resolved_type_spec):
        """Generate code for a singinit (single-init, program-lifetime) local variable."""
        from fast import NoInit as _NoInit, ArrayLiteral as _ArrayLiteral
        func_name = builder.function.name
        global_name = f"__singinit__{func_name}__{node.name}"
        guard_name  = f"__singinit_guard__{func_name}__{node.name}"

        # Create (or reuse) the backing global for the variable value
        if global_name not in module.globals:
            gvar = ir.GlobalVariable(module, llvm_type, global_name)
            gvar.initializer = TypeSystem.get_default_initializer(llvm_type)
            gvar.linkage = 'internal'
        else:
            gvar = module.globals[global_name]

        # Create (or reuse) the init-guard (i1, false)
        guard_type = ir.IntType(1)
        if guard_name not in module.globals:
            gguard = ir.GlobalVariable(module, guard_type, guard_name)
            gguard.initializer = ir.Constant(guard_type, 0)
            gguard.linkage = 'internal'
        else:
            gguard = module.globals[guard_name]

        # Build the init-guard branch inline
        cur_func   = builder.function
        init_block = cur_func.append_basic_block(f"singinit_{node.name}_init")
        done_block = cur_func.append_basic_block(f"singinit_{node.name}_done")

        guard_val = builder.load(gguard, name=f"{node.name}_guard")
        builder.cbranch(guard_val, done_block, init_block)

        # init_block: initialize the global and set the guard
        builder.position_at_end(init_block)
        if node.initial_value and not isinstance(node.initial_value, _NoInit):
            self._vardecl_initialize_singinit(node, builder, module, gvar, llvm_type, resolved_type_spec)
        else:
            if isinstance(llvm_type, ir.ArrayType) and llvm_type.count > 64:
                i8_ptr_ty  = ir.PointerType(ir.IntType(8))
                i8_ty      = ir.IntType(8)
                i64_ty     = ir.IntType(64)
                i1_ty      = ir.IntType(1)
                elem = llvm_type.element
                elem_bytes = (elem.width // 8) if isinstance(elem, ir.IntType) else 1
                byte_count = llvm_type.count * elem_bytes
                fnty    = ir.FunctionType(ir.VoidType(), [i8_ptr_ty, i8_ty, i64_ty, i1_ty])
                ms_name = 'llvm.memset.p0i8.i64'
                if ms_name not in module.globals:
                    ir.Function(module, fnty, name=ms_name)
                memset_fn = module.globals[ms_name]
                cast_ptr  = builder.bitcast(gvar, i8_ptr_ty, name='memset_ptr')
                builder.call(memset_fn, [
                    cast_ptr,
                    ir.Constant(i8_ty,  0),
                    ir.Constant(i64_ty, byte_count),
                    ir.Constant(i1_ty,  0),
                ])
            else:
                zero = TypeSystem.get_default_initializer(llvm_type)
                builder.store(zero, gvar)
        builder.store(ir.Constant(guard_type, 1), gguard)
        builder.branch(done_block)

        # done_block: resume normal execution
        builder.position_at_end(done_block)

        # Register the global pointer in the symbol table so the rest of the
        # function body can load/store it transparently
        if resolved_type_spec:
            gvar._flux_type_spec = resolved_type_spec
        module.symbol_table.define(node.name, SymbolKind.VARIABLE,
                                   type_spec=resolved_type_spec, llvm_value=gvar)
        return gvar

    def _vardecl_initialize_singinit(self, node, builder, module, gvar, llvm_type, resolved_type_spec):
        """Initialize the backing global of a singinit variable."""
        from fast import ArrayLiteral as _ArrayLiteral
        if isinstance(node.initial_value, _ArrayLiteral):
            if isinstance(llvm_type, ir.IntType):
                packed_val = ArrayTypeHandler.pack_array_to_integer(builder, module, node.initial_value, llvm_type)
                builder.store(packed_val, gvar)
            else:
                ArrayTypeHandler.initialize_local_array(builder, module, gvar, llvm_type, node.initial_value)
            return
        init_val = self.visit(node.initial_value, builder, module)
        if hasattr(init_val, 'type') and init_val.type != llvm_type:
            init_val = TypeSystem.cast_value(builder, module, init_val, llvm_type, resolved_type_spec)
        builder.store(init_val, gvar)

    def _vardecl_local(self, node, builder, module, llvm_type, resolved_type_spec):
        """Generate code for local variable."""
        from fast import NoInit as _NoInit, FunctionCall as _FunctionCall, ArrayLiteral as _ArrayLiteral, ArrayComprehension as _ArrayComprehension, StringLiteral as _StringLiteral, Identifier as _Identifier

        # Zero-copy struct recast: `T t from src[start:end]` or `T t from arr`
        # visit_StructRecast returns a T* pointer directly into the source buffer
        # whenever the source is a pointer (slice GEP, array alloca, etc.).
        # Register that pointer as the variable — no alloca, no load, no store.
        from fast import StructRecast as _StructRecast, ArraySlice as _ArraySlice, Identifier as _Identifier
        if isinstance(node.initial_value, _StructRecast):
            recast_ptr = self.visit(node.initial_value, builder, module)
            # perform_struct_recast returns a pointer when it can alias in-place.
            # If it returned a non-pointer (e.g. byte-extraction path), fall
            # through to the normal alloca+store path below.
            if isinstance(recast_ptr.type, ir.PointerType):
                if resolved_type_spec:
                    recast_ptr._flux_type_spec = resolved_type_spec
                module.symbol_table.define(
                    node.name, SymbolKind.VARIABLE,
                    type_spec=resolved_type_spec,
                    llvm_value=recast_ptr,
                )
                # Invalidate the source identifier, mirroring void cast:
                # delete it from scope so any further use is a compile-time error.
                # Suppressed when the `from` declaration used a trailing `!`.
                if not getattr(node.initial_value, 'suppress_invalidate', False):
                    src = node.initial_value.source_expr
                    if isinstance(src, _ArraySlice) and isinstance(src.array, _Identifier):
                        module.symbol_table.delete_variable(src.array.name)
                    elif isinstance(src, _Identifier):
                        module.symbol_table.delete_variable(src.name)
                return recast_ptr

        # Handle singinit: single-init, program-lifetime, function-scoped variable
        if (resolved_type_spec is not None and
                resolved_type_spec.storage_class == StorageClass.SINGINIT):
            return self._vardecl_singinit(node, builder, module, llvm_type, resolved_type_spec)

        # Handle heap: allocate via fmalloc, variable becomes a T* pointer
        if (resolved_type_spec is not None and
                resolved_type_spec.storage_class == StorageClass.HEAP):
            return self._vardecl_heap(node, builder, module, llvm_type, resolved_type_spec)

        # If this is a constructor call and llvm_type resolved to i8* (void pointer),
        # the type was polluted by a local variable named the same as the object type.
        # Recover the correct struct type from the constructor's this parameter.
        if (isinstance(node.initial_value, _FunctionCall) and
                node.initial_value.name.endswith('.__init') and
                isinstance(llvm_type, ir.PointerType) and
                isinstance(llvm_type.pointee, ir.IntType) and
                llvm_type.pointee.width == 8):
            func = TypeResolver.resolve_function(module, node.initial_value.name)
            if func is None and hasattr(module, '_using_namespaces'):
                for namespace in module._using_namespaces:
                    mangled = f"{namespace}__{node.initial_value.name}"
                    func = TypeResolver.resolve_function(module, mangled)
                    if func:
                        break
            if func and func.args and isinstance(func.args[0].type, ir.PointerType):
                llvm_type = func.args[0].type.pointee

        # Check for VLA: type_spec says is_array with a runtime expression dimension,
        # so get_llvm_type returned PointerType(element) instead of ArrayType.
        # Use alloca with a dynamic count so the result is element* not element**.
        if (isinstance(llvm_type, ir.PointerType) and
                resolved_type_spec is not None and
                resolved_type_spec.is_array):
            dim_expr = None
            if resolved_type_spec.array_dimensions:
                dim_expr = resolved_type_spec.array_dimensions[0]
            elif resolved_type_spec.array_size is not None:
                dim_expr = resolved_type_spec.array_size
            if dim_expr is not None and not isinstance(dim_expr, int) and not (hasattr(dim_expr, 'value') and isinstance(dim_expr.value, int)):
                count_val = self.visit(dim_expr, builder, module)
                element_type = llvm_type.pointee
                alloca = builder.alloca(element_type, size=count_val, name=node.name)
                if resolved_type_spec:
                    alloca._flux_type_spec = resolved_type_spec
                module.symbol_table.define(node.name, SymbolKind.VARIABLE, type_spec=resolved_type_spec, llvm_value=alloca)
                # VLA: cannot store an aggregate initializer into an element pointer — skip init
                return alloca
            else:
                alloca = builder.alloca(llvm_type, name=node.name)
        else:
            # If inside a switch case body, hoist the alloca to the function entry
            # block so it doesn't land mid-CFG (LLVM requires allocas in entry block)
            alloca_block = getattr(builder, '_switch_case_alloca_block', None)
            if alloca_block is not None:
                current_block = builder.block
                entry_term = alloca_block.terminator
                if entry_term is not None:
                    builder.position_before(entry_term)
                else:
                    builder.position_at_end(alloca_block)
                alloca = builder.alloca(llvm_type, name=node.name)
                builder.position_at_end(current_block)
            else:
                alloca = builder.alloca(llvm_type, name=node.name)

        if resolved_type_spec:
            alloca._flux_type_spec = resolved_type_spec

        # Register in scope BEFORE initialization so endianness checking works
        #print(f"[LOCAL VAR] Registering local variable '{node.name}' in scope level {module.symbol_table.scope_level}", file=sys.stdout)
        #print(f"[LOCAL VAR]   Scopes count: {len(module.symbol_table.scopes)}", file=sys.stdout)
        module.symbol_table.define(node.name, SymbolKind.VARIABLE, type_spec=resolved_type_spec, llvm_value=alloca)
        #print(f"[LOCAL VAR]   Variable '{node.name}' registered successfully", file=sys.stdout)
        if resolved_type_spec.is_volatile:
            if not hasattr(builder, 'volatile_vars'):
                builder.volatile_vars = set()
            builder.volatile_vars.add(node.name)

        # Handle noinit keyword - skip initialization entirely
        if isinstance(node.initial_value, _NoInit):
            # Mark variable as explicitly uninitialized for tracking
            if not hasattr(builder, 'uninitialized_vars'):
                builder.uninitialized_vars = set()
            builder.uninitialized_vars.add(node.name)
            # Do NOT initialize the alloca - it will contain undefined value
        # Initialize variable if value is provided (and it's not noinit)
        elif node.initial_value:
            self._vardecl_initialize_local(node, builder, module, alloca, llvm_type, resolved_type_spec)
        else:
            # No initial value: zero-initialize per Flux spec.
            # For large arrays use llvm.memset to avoid emitting a massive
            # constant aggregate literal that crashes the LLVM instruction selector.
            if isinstance(llvm_type, ir.ArrayType) and llvm_type.count > 64:
                i8_ptr_ty  = ir.PointerType(ir.IntType(8))
                i8_ty      = ir.IntType(8)
                i64_ty     = ir.IntType(64)
                i1_ty      = ir.IntType(1)
                elem = llvm_type.element
                elem_bytes = (elem.width // 8) if isinstance(elem, ir.IntType) else 1
                byte_count = llvm_type.count * elem_bytes
                fnty    = ir.FunctionType(ir.VoidType(), [i8_ptr_ty, i8_ty, i64_ty, i1_ty])
                ms_name = 'llvm.memset.p0i8.i64'
                if ms_name not in module.globals:
                    ir.Function(module, fnty, name=ms_name)
                memset_fn = module.globals[ms_name]
                cast_ptr  = builder.bitcast(alloca, i8_ptr_ty, name='memset_ptr')
                builder.call(memset_fn, [
                    cast_ptr,
                    ir.Constant(i8_ty,  0),
                    ir.Constant(i64_ty, byte_count),
                    ir.Constant(i1_ty,  0),
                ])
            else:
                zero = TypeSystem.get_default_initializer(llvm_type)
                builder.store(zero, alloca)

        return alloca

    def _vardecl_heap(self, node, builder, module, llvm_type, resolved_type_spec):
        """Generate code for a heap-allocated variable (``heap T name = val;``).

        Translates to:
            T* name = (T*)fmalloc(sizeof(T));
            *name = val;                       // if an initializer was given

        The symbol is registered as a pointer-to-T so that subsequent reads,
        writes, and address-of operations work exactly like a manually declared
        ``T* ptr = (T*)fmalloc(...);``.
        """
        from fast import NoInit as _NoInit

        i8_ptr_ty = ir.PointerType(ir.IntType(8))
        i64_ty    = ir.IntType(64)
        ptr_ty    = ir.PointerType(llvm_type)

        # --- resolve / declare fmalloc -----------------------------------
        # The canonical mangled name emitted by the standard library.
        # Signature: u64 fmalloc(u64 size)  — takes and returns a raw address (u64).
        _FMALLOC_MANGLED = (
            'standard__memory__allocators__stdheap__fmalloc'
            '__1__dataE1_ubits64__ret_dataE1_ubits64'
        )
        fmalloc_fn = module.globals.get(_FMALLOC_MANGLED)
        if fmalloc_fn is None:
            # Try any variant ending in 'fmalloc' (handles using-namespace aliases)
            for gname, gval in module.globals.items():
                if gname.endswith('fmalloc') and isinstance(gval, ir.Function):
                    fmalloc_fn = gval
                    break
        if fmalloc_fn is None:
            # Forward-declare using the canonical mangled name so the linker can
            # resolve it against the standard library object.
            fmalloc_ty = ir.FunctionType(i64_ty, [i64_ty])
            fmalloc_fn = ir.Function(module, fmalloc_ty, name=_FMALLOC_MANGLED)

        # --- compute sizeof(T) -------------------------------------------
        # Use the standard GEP-from-null trick: sizeof(T) = (T*)null + 1 as int
        null_ptr  = ir.Constant(ptr_ty, None)
        size_ptr  = builder.gep(null_ptr, [ir.Constant(ir.IntType(32), 1)], name='sizeof_gep')
        sizeof_val = builder.ptrtoint(size_ptr, i64_ty, name='sizeof_val')

        # --- call fmalloc ------------------------------------------------
        # fmalloc takes and returns a u64 raw address, so convert via inttoptr.
        raw_addr  = builder.call(fmalloc_fn, [sizeof_val], name=f'{node.name}_raw')
        typed_ptr = builder.inttoptr(raw_addr, ptr_ty, name=f'{node.name}_ptr')

        # --- alloca to hold the pointer (so the symbol has an address) ---
        # Hoist to entry block if inside a switch case body
        alloca_block = getattr(builder, '_switch_case_alloca_block', None)
        if alloca_block is not None:
            current_block = builder.block
            entry_term = alloca_block.terminator
            if entry_term is not None:
                builder.position_before(entry_term)
            else:
                builder.position_at_end(alloca_block)
            ptr_alloca = builder.alloca(ptr_ty, name=node.name)
            builder.position_at_end(current_block)
        else:
            ptr_alloca = builder.alloca(ptr_ty, name=node.name)

        builder.store(typed_ptr, ptr_alloca)

        # Annotate so callers know this alloca holds a heap pointer
        ptr_alloca._flux_is_heap = True
        if resolved_type_spec:
            ptr_alloca._flux_type_spec = resolved_type_spec

        # --- register *pointer* type in symbol table ---------------------
        # Build a synthetic pointer type-spec so that loads of this symbol
        # produce T* (not T), matching behaviour of ``T* p = fmalloc(...);``.
        ptr_type_spec = None
        if resolved_type_spec is not None:
            try:
                ptr_type_spec = resolved_type_spec.__class__(
                    base_type=resolved_type_spec.base_type,
                    pointer_depth=(getattr(resolved_type_spec, 'pointer_depth', 0) or 0) + 1,
                    bit_width=getattr(resolved_type_spec, 'bit_width', None),
                    custom_typename=getattr(resolved_type_spec, 'custom_typename', None),
                    is_const=getattr(resolved_type_spec, 'is_const', False),
                    is_volatile=getattr(resolved_type_spec, 'is_volatile', False),
                    storage_class=None,   # strip heap modifier from the pointer itself
                )
            except TypeError:
                ptr_type_spec = resolved_type_spec  # fallback: use original spec

        module.symbol_table.define(
            node.name, SymbolKind.VARIABLE,
            type_spec=ptr_type_spec,
            llvm_type=ptr_ty,
            llvm_value=ptr_alloca,
        )

        # --- store initial value through the pointer ---------------------
        if node.initial_value and not isinstance(node.initial_value, _NoInit):
            init_val = self.visit(node.initial_value, builder, module)
            if init_val is not None:
                if hasattr(init_val, 'type') and init_val.type != llvm_type:
                    init_val = TypeSystem.cast_value(builder, module, init_val, llvm_type, resolved_type_spec)
                builder.store(init_val, typed_ptr)
        else:
            # Zero-initialise the heap allocation (mirrors stack zero-init)
            zero = TypeSystem.get_default_initializer(llvm_type)
            builder.store(zero, typed_ptr)

        return ptr_alloca

    def _vardecl_initialize_local(self, node, builder, module, alloca, llvm_type, resolved_type_spec):
        """Initialize local variable with initial value."""
        from fast import ArrayLiteral as _ArrayLiteral, ArrayComprehension as _ArrayComprehension, StringLiteral as _StringLiteral, FunctionCall as _FunctionCall, Identifier as _Identifier, AddressOf as _AddressOf, StructLiteral as _StructLiteral
        # When the RHS is @[...] and the LHS is a pointer (e.g. byte*), propagate the
        # pointee type as the array element_type so elements are not defaulted to i32.
        if (isinstance(node.initial_value, _AddressOf) and
                isinstance(node.initial_value.expression, _ArrayLiteral) and
                node.initial_value.expression.element_type is None and
                resolved_type_spec is not None and
                getattr(resolved_type_spec, 'pointer_depth', 0) > 0):
            node.initial_value.expression.element_type = resolved_type_spec.__class__(
                base_type=resolved_type_spec.base_type,
                pointer_depth=resolved_type_spec.pointer_depth - 1,
                bit_width=getattr(resolved_type_spec, 'bit_width', None),
                custom_typename=getattr(resolved_type_spec, 'custom_typename', None),
            )
        # When the RHS is @{...} (AddressOf a StructLiteral) and the LHS is a struct
        # pointer (e.g. test*), seed struct_type onto the StructLiteral from the LHS
        # type spec so that visit_StructLiteral has the required type context.
        if (isinstance(node.initial_value, _AddressOf) and
                isinstance(node.initial_value.expression, _StructLiteral) and
                node.initial_value.expression.struct_type is None and
                resolved_type_spec is not None):
            ctn = getattr(resolved_type_spec, 'custom_typename', None)
            if ctn:
                node.initial_value.expression.struct_type = ctn
        # Handle array instance initialization
        if isinstance(node.initial_value, _ArrayLiteral):
            # If target is an integer, pack the array into it
            if isinstance(llvm_type, ir.IntType):
                packed_val = ArrayTypeHandler.pack_array_to_integer(builder, module, node.initial_value, llvm_type)
                builder.store(packed_val, alloca)
            # Otherwise, initialize as array
            else:
                ArrayTypeHandler.initialize_local_array(builder, module, alloca, llvm_type, node.initial_value)
            return

        if isinstance(node.initial_value, _ArrayComprehension):
            # Extract expected size from the type_spec if it's an array type
            expected_size = None
            if resolved_type_spec and resolved_type_spec.array_size is not None:
                raw_size = resolved_type_spec.array_size
                if isinstance(raw_size, int):
                    expected_size = raw_size
                elif hasattr(raw_size, 'value') and isinstance(raw_size.value, int):
                    expected_size = raw_size.value
                else:
                    expected_size = int(raw_size)

            comp_result = self.visit_ArrayComprehension(node.initial_value, builder, module, expected_size=expected_size)
            # comp_result is [5 x i32]*, alloca is [5 x i32]*
            # Load from comp_result and store into alloca
            loaded_array = builder.load(comp_result, name="comp_array_load")
            builder.store(loaded_array, alloca)
            return

        # Delegate string literal initialization to ArrayLiteral
        if isinstance(node.initial_value, _StringLiteral):
            ArrayTypeHandler.initialize_local_string(
                builder, module, alloca, llvm_type, node.initial_value)
            return

        # Handle constructor calls
        if isinstance(node.initial_value, _FunctionCall) and node.initial_value.name.endswith('.__init'):
            # Zero-initialize the alloca before calling the constructor so that embedded
            # sub-object fields (e.g. arr.len, arr.cap inside JSONNode) start at zero per
            # Flux semantics. Constructors that are empty (just return this) rely on this.
            if isinstance(alloca.type.pointee, (ir.LiteralStructType, ir.IdentifiedStructType)):
                zero = TypeSystem.get_default_initializer(alloca.type.pointee)
                builder.store(zero, alloca)
            self._vardecl_call_constructor(node, builder, module, alloca)
            return

        # Handle array-to-array copy
        if isinstance(llvm_type, ir.ArrayType) and isinstance(node.initial_value, _Identifier):
            ArrayTypeHandler.copy_array_to_local(
                builder, module, alloca, llvm_type, node.initial_value
            )
            return

        # Handle regular initialization
        init_val = self.visit(node.initial_value, builder, module)
        if init_val is not None:
            self._vardecl_store_with_type_conversion(node, builder, alloca, llvm_type, init_val, module)

    def _vardecl_call_constructor(self, node, builder, module, alloca):
        """Call constructor for object initialization using proper overload resolution."""
        # Use the FunctionCall's existing resolution logic to find the constructor
        # This handles namespace resolution, overloading, and name mangling properly
        func_call = node.initial_value  # This is a FunctionCall with name like "string.__init"

        #print(f"[CONSTRUCTOR] Looking for constructor: {func_call.name}", file=sys.stdout)
        #print(f"[CONSTRUCTOR] current_namespace={getattr(module, '_current_namespace', '<none>')}", file=sys.stdout)
        #print(f"[CONSTRUCTOR] Globals with __init:", file=sys.stdout)
        #for name in module.globals:
        #    if '__init' in name:
        #        print(f"  - {name}", file=sys.stdout)
        #if hasattr(module, '_function_overloads'):
        #    print(f"[CONSTRUCTOR] Overload keys with __init:", file=sys.stdout)
        #    for base_name in module._function_overloads:
        #        if '__init' in base_name:
        #            print(f"  - {base_name}: {len(module._function_overloads[base_name])} overload(s)", file=sys.stdout)

        # Try to resolve the constructor using the same multi-step resolution as regular calls
        func = None

        # Step 1: Try direct lookup
        func = module.globals.get(func_call.name, None)
        if func and isinstance(func, ir.Function):
            #print(f"[CONSTRUCTOR] Found via direct lookup: {func_call.name}", file=sys.stdout)
            pass  # Found it
        else:
            #print("[CONSTRUCTOR] ATTEMPTING OVERLOAD RESOLUTION", file=sys.stdout)
            # Step 2: Try overload resolution
            if hasattr(module, '_function_overloads') and func_call.name in module._function_overloads:
                func = TypeResolver.resolve_function(module, func_call.name)
                #if func:
                #    print(f"[CONSTRUCTOR] Found via overload resolution: {func_call.name}", file=sys.stdout)

        # Step 3: Try namespace resolution if still not found
        if func is None and hasattr(module, '_using_namespaces'):
            #print("[CONSTRUCTOR] NOT FOUND, USING NAMESPACE RESOLUTION", file=sys.stdout)
            for namespace in module._using_namespaces:
                #print(f"[CONSTRUCTOR]   Trying namespace: {namespace}", file=sys.stdout)
                mangled_prefix = namespace.replace("::", "__") + "__"
                mangled_name = mangled_prefix + func_call.name
                #print(f"[CONSTRUCTOR]   Mangled name: {mangled_name}", file=sys.stdout)

                # Try direct lookup with namespace prefix
                func = module.globals.get(mangled_name, None)
                if func and isinstance(func, ir.Function):
                    #print(f"[CONSTRUCTOR] Found via namespace direct lookup: {mangled_name}", file=sys.stdout)
                    break

                # Try overload resolution with namespace prefix
                if hasattr(module, '_function_overloads'):
                    #print(f"[CONSTRUCTOR]   Checking overloads for: {mangled_name}", file=sys.stdout)
                    if mangled_name in module._function_overloads:
                        #print(f"[CONSTRUCTOR]   FOUND in overloads!", file=sys.stdout)
                        func = TypeResolver.resolve_function(module, mangled_name)
                        if func:
                            #print(f"[CONSTRUCTOR] Found via namespace overload resolution: {mangled_name}", file=sys.stdout)
                            break

        # Step 4: Try all registered namespaces (catches types in non-using namespaces)
        if func is None and hasattr(module, '_namespaces'):
            for namespace in module._namespaces:
                mangled_prefix = namespace.replace("::", "__") + "__"
                mangled_name = mangled_prefix + func_call.name

                func = module.globals.get(mangled_name, None)
                if func and isinstance(func, ir.Function):
                    break

                if hasattr(module, '_function_overloads') and mangled_name in module._function_overloads:
                    func = TypeResolver.resolve_function(module, mangled_name)
                    if func:
                        break

        # Step 5: Scan all overload keys for a suffix match (handles cross-namespace constructor calls
        # where the target namespace was registered after the caller's namespace was first processed)
        if func is None and hasattr(module, '_function_overloads'):
            suffix = "__" + func_call.name
            for key, overloads in module._function_overloads.items():
                if key.endswith(suffix) or key == func_call.name:
                    func = TypeResolver.resolve_function(module, key)
                    if func:
                        break

        # Step 6: Scan module.globals directly for a function whose name ends with the constructor pattern
        if func is None:
            # func_call.name is e.g. "JSONNode.__init"; look for "*__JSONNode.__init*" in globals
            base = func_call.name  # e.g. "JSONNode.__init"
            dot = base.find(".")
            if dot != -1:
                obj_part = base[:dot]   # e.g. "JSONNode"
                meth_part = base[dot:]  # e.g. ".__init"
                needle = "__" + obj_part + meth_part  # e.g. "__JSONNode.__init"
                for gname, gval in module.globals.items():
                    if isinstance(gval, ir.Function) and needle in gname:
                        func = gval
                        break

        if func is None:
            raise NameError(f"Constructor not found: {func_call.name} [{node.source_line}:{node.source_col}]")
        # Build arguments: 'this' pointer first, then constructor arguments
        args = [alloca]

        for i, arg_expr in enumerate(func_call.arguments):
            param_index = i + 1
            from fast import StringLiteral as _StringLiteral
            if (isinstance(arg_expr, _StringLiteral) and
                param_index < len(func.args) and
                isinstance(func.args[param_index].type, ir.PointerType) and
                isinstance(func.args[param_index].type.pointee, ir.IntType) and
                func.args[param_index].type.pointee.width == 8):

                arg_val = ArrayTypeHandler.create_local_string_for_arg(
                    builder, module, arg_expr.value, f"ctor_arg{i}"
                )
            else:
                arg_val = self.visit(arg_expr, builder, module)

            if param_index < len(func.args):
                expected_type = func.args[param_index].type
                arg_val = FunctionTypeHandler.convert_argument_to_parameter_type(builder, module, arg_val, expected_type, i)

            args.append(arg_val)

        builder.call(func, args)

    def _vardecl_store_with_type_conversion(self, node, builder, alloca, llvm_type, init_val, module):
        """Store value with automatic type conversion if needed."""
        VariableTypeHandler.store_with_type_conversion(builder, alloca, llvm_type, init_val, node.initial_value, module)

    def visit_Program(self, node, builder, module):
        from fast import (UsingStatement, NotUsingStatement, NamespaceDef,
                          StructDef, StructDefStatement, ObjectDef, ObjectDefStatement,
                          ExternBlock, ExportBlock, NamespaceDefStatement)
        print("[AST] Begining codegen for Flux program ...")
        print(f"[AST] Total statements in AST: {len(node.statements)}", file=sys.stdout)
        namespace_count = sum(1 for s in node.statements if isinstance(s, NamespaceDef))
        print(f"[AST] Namespace definitions: {namespace_count}", file=sys.stdout)
        #for s in node.statements:
        #    if isinstance(s, NamespaceDef):
        #        print(f"[AST]   - namespace {s.name} (funcs: {len(s.functions)}, nested: {len(s.nested_namespaces)})", file=sys.stdout)
        if module is None:
            module = ir.Module(name='flux_module') # Update to support module system.

        # Validate and attach symbol table to module
        if not isinstance(node.symbol_table, SymbolTable):
            print(f"[ERROR] Program.symbol_table is {type(node.symbol_table)}, not SymbolTable!", file=sys.stdout)
            print(f"[ERROR] Creating new SymbolTable to replace it", file=sys.stdout)
            node.symbol_table = SymbolTable()

        module.symbol_table = node.symbol_table
        module._program_statements = node.statements

        # Collect macro definitions onto the module so visit_macroCall can
        # find them without needing a reference back to the parser.
        from fast import macroDefStatement as _macroDefStatement
        if not hasattr(module, '_macros'):
            module._macros = {}
        for _stmt in node.statements:
            if isinstance(_stmt, _macroDefStatement):
                module._macros[_stmt.macro_def.name] = _stmt.macro_def

        # Create global builder with no function context
        builder = ir.IRBuilder()
        # Symbol table already at global scope (level 0)
        # Track initialized unions for immutability enforcement
        builder.initialized_unions = set()

        # 4-pass compilation
        print("[AST] Pass 1: Processing using statements...")
        for stmt in node.statements:
            if isinstance(stmt, UsingStatement):
                self.visit(stmt, builder, module)

        print("[AST] Pass 2: Processing not using statements...")
        for stmt in node.statements:
            if isinstance(stmt, NotUsingStatement):
                self.visit(stmt, builder, module)

        # Pre-pass: register all object struct types across the entire namespace tree before
        # any method bodies are emitted, so cross-namespace type references always resolve.
        # Extern blocks are included in this retry loop so that extern param types that
        # reference namespace-defined structs (e.g. RECT*) are resolved after those types
        # are registered, rather than eagerly before them.
        print("[AST] Pre-pass: Registering all object types and extern blocks...")
        pending_toplevel = [stmt for stmt in node.statements
                            if isinstance(stmt, (StructDef, StructDefStatement, ObjectDef, ObjectDefStatement))]
        pending_ns = []
        for stmt in node.statements:
            ns = None
            if isinstance(stmt, NamespaceDef):
                ns = stmt
            elif isinstance(stmt, NamespaceDefStatement):
                ns = stmt.namespace_def
            if ns is not None:
                pending_ns.append(ns)

        # Collect extern blocks for deferred processing.
        pending_extern = [stmt for stmt in node.statements if isinstance(stmt, ExternBlock)]

        # Pre-register namespace types using the existing retry helper first (best-effort).
        for ns in pending_ns:
            try:
                NamespaceDef.preregister_all_types(ns, module)
            except Exception:
                pass  # will be retried in the unified loop below

        # Now retry top-level structs/objects, namespace registrations, and extern blocks
        # together until no further progress is possible.
        # _prepass_only=True tells visit_ObjectDef to skip method body emission so that
        # unresolvable using-namespace functions (e.g. println) don't cause spurious
        # failures here.  Pass 4 emits all method bodies after Pass 3 has registered
        # every top-level symbol.
        module._prepass_only = True
        max_passes = len(pending_toplevel) + len(pending_ns) + len(pending_extern) + 1
        pending_tl = list(pending_toplevel)
        pending_ns_retry = list(pending_ns)
        pending_ex = list(pending_extern)
        for _ in range(max_passes):
            if not pending_tl and not pending_ns_retry and not pending_ex:
                break
            still_tl, still_ns, still_ex = [], [], []
            for stmt in pending_tl:
                try:
                    self.visit(stmt, builder, module)
                except Exception:
                    still_tl.append(stmt)
            for ns in pending_ns_retry:
                try:
                    NamespaceDef.preregister_all_types(ns, module)
                except Exception:
                    still_ns.append(ns)
            for ex in pending_ex:
                try:
                    self.visit(ex, builder, module)
                except Exception:
                    still_ex.append(ex)
            if (len(still_tl) == len(pending_tl) and
                    len(still_ns) == len(pending_ns_retry) and
                    len(still_ex) == len(pending_ex)):
                # No progress — surface the real errors
                for stmt in still_tl:
                    self.visit(stmt, builder, module)
                for ns in still_ns:
                    NamespaceDef.preregister_all_types(ns, module)
                for ex in still_ex:
                    self.visit(ex, builder, module)
                break
            pending_tl, pending_ns_retry, pending_ex = still_tl, still_ns, still_ex
        module._prepass_only = False

        # Pass 3: Process all other statements
        print("[AST] Pass 3: Processing all other statements...")
        from fast import ContractDef as _ContractDef
        for stmt in node.statements:
            if not isinstance(stmt, (UsingStatement, NotUsingStatement, ExternBlock, StructDef, StructDefStatement, ObjectDef, ObjectDefStatement, _ContractDef)):
                self.visit(stmt, builder, module)

        # Pass 3.5: Verify trait compliance now that all TraitDefs are registered.
        from fast import ObjectDef as _ObjectDef, ObjectDefStatement as _ObjectDefStatement
        for stmt in node.statements:
            obj_def = None
            if isinstance(stmt, _ObjectDef):
                obj_def = stmt
            elif isinstance(stmt, _ObjectDefStatement):
                obj_def = stmt.object_def
            if obj_def is None or not obj_def.traits:
                continue
            implemented_names = {m.name for m in obj_def.methods}
            for trait_name in obj_def.traits:
                required = module.symbol_table._trait_registry.get(trait_name)
                if required is None:
                    raise ValueError(
                        f"Trait '{trait_name}' used by object '{obj_def.name}' is not defined "
                        f"[{obj_def.source_line}:{obj_def.source_col}]")
                for proto in required:
                    if proto.name not in implemented_names:
                        raise ValueError(
                            f"Object '{obj_def.name}' does not implement required function "
                            f"'{proto.name}' from '{trait_name}' trait "
                            f"[{obj_def.source_line}:{obj_def.source_col}]")

        # Pass 4: Re-emit object method bodies that were skipped or partially emitted
        # during the pre-pass (e.g. because using-namespace functions such as println()
        # were not yet registered at that point).  _emit_method_body is idempotent for
        # fully-terminated functions and will re-attempt any that were left without a
        # terminator.
        print("[AST] Pass 4: Re-emitting pending bodies...")
        for stmt in node.statements:
            obj_def = None
            if isinstance(stmt, ObjectDef):
                obj_def = stmt
            elif isinstance(stmt, ObjectDefStatement):
                obj_def = stmt.object_def
            if obj_def is None:
                continue
            if not hasattr(module, '_struct_types') or obj_def.name not in module._struct_types:
                continue
            struct_type = module._struct_types[obj_def.name]
            for method in obj_def.methods:
                from fast import FunctionDef as _FunctionDef
                if isinstance(method, _FunctionDef) and method.is_prototype:
                    continue
                from ftypesys import ObjectTypeHandler as _OTH
                _, func_name = _OTH.create_method_signature(
                    obj_def.name, method.name, method, struct_type, module)
                func = module.globals.get(func_name)
                if func is None or not isinstance(func, ir.Function):
                    continue
                self._emit_method_body(method, func, obj_def.name, module)

        main_args_name = "main__2__intE1__byteE1_ptr2__ret_intE1"
        main_no_args_name = "main__0__ret_intE1"

        main_func      = module.globals.get(main_no_args_name)
        main_args_func = module.globals.get(main_args_name)

        # Emit a stub main() if the user only defined main(argc, argv).
        # The stub calls main(argc, argv) with argc=0 and argv=null so that
        # FRTStartup's no-arg path still reaches the user's real entry point.
        if (main_func is not None and
                isinstance(main_func, ir.Function) and
                main_func.is_declaration and
                main_args_func is not None and
                isinstance(main_args_func, ir.Function)):
            stub_block = main_func.append_basic_block("entry")
            stub_builder = ir.IRBuilder(stub_block)
            argc_val = ir.Constant(ir.IntType(32), 0)
            argv_type = ir.PointerType(ir.PointerType(ir.IntType(8)))
            argv_val = ir.Constant(argv_type, None)
            ret_val = stub_builder.call(main_args_func, [argc_val, argv_val])
            stub_builder.ret(ret_val)

        # Emit a stub main(argc, argv) if the user only defined main().
        # The stub ignores its arguments and calls the no-arg main() directly,
        # returning its result, so FRTStartup's args path still works.
        if (main_args_func is not None and
                isinstance(main_args_func, ir.Function) and
                main_args_func.is_declaration and
                main_func is not None and
                isinstance(main_func, ir.Function)):
            stub_block = main_args_func.append_basic_block("entry")
            stub_builder = ir.IRBuilder(stub_block)
            ret_val = stub_builder.call(main_func, [])
            stub_builder.ret(ret_val)

        return module

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

visitor = CodegenVisitor()