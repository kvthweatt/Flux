#!/usr/bin/env python3
"""
Flux VM Codegen (fvmcodegen.py)
Compiles Flux AST nodes inside comptime blocks to fvm.py bytecode.

This mirrors fcodegen.py's visitor pattern but targets the FluxVM
instead of LLVM IR. It does not use llvmlite, ir.IRBuilder, or
ir.Module in any way.

Copyright (C) 2026 Karac V. Thweatt
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fvm import Op, TTag, Val, Instr
from fast import (
    ASTNode, Expression, NoInit,
    ComptimeBlock, EmitFlux,
    VariableDeclaration,
    TypeDeclaration,
    Assignment, CompoundAssignment,
    BinaryOp, UnaryOp,
    Literal, Identifier, StringLiteral, FStringLiteral,
    FunctionCall, MethodCall, MemberAccess,
    ArrayLiteral,
    AddressOf, CastExpression, TypeConvertExpression,
    PointerDeref, BitSlice,
    InExpression,
    HasExpression,
    SizeOf,
    AlignOf,
    TypeOf,
    EndianOf,
    IfStatement,
    WhileLoop, DoLoop, DoWhileLoop,
    ForLoop, ForInLoop,
    ReturnStatement,
    BreakStatement, ContinueStatement, EscapeStatement,
    DeferStatement,
    NoreturnStatement,
    TryBlock, ThrowStatement,
    LabelStatement, GotoStatement, JumpStatement,
    ExpressionStatement,
    Block,
    ArrayAccess,
    SwitchStatement, Case,
    FunctionDef, FunctionDefStatement,
    FunctionPointerDeclaration,
    TypeFuncDef, TypeFuncCall,
    NamespaceDef, NamespaceDefStatement,
    StructDef, StructDefStatement, StructMember, StructInstance, StructLiteral,
    StructFieldAccess, StructFieldAssign, StructRecast,
    UnionDef, UnionDefStatement,
    ConstraDef,
    ContractDef,
    ObjectDef, ObjectDefStatement,
    TraitDef, InterfaceDef,
    DeprecateStatement,
    AssertStatement,
    EnumDef, EnumDefStatement,
    macroDefStatement, macroCall,
    ExternBlock,
    FluxVMBlock,
    UsingStatement, NotUsingStatement,
    InlineAsm,
    TernaryOp,
)
from ftypesys import DataType, Operator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _datatype_to_ttag(dt: DataType) -> TTag:
    """Map a Flux DataType to the closest VM TTag."""
    _map = {
        DataType.SINT:    TTag.INT,
        DataType.UINT:   TTag.UINT,
        DataType.SLONG:   TTag.LONG,
        DataType.ULONG:  TTag.ULONG,
        DataType.FLOAT:  TTag.FLOAT,
        DataType.DOUBLE: TTag.DOUBLE,
        DataType.BOOL:   TTag.BOOL,
        DataType.BYTE:   TTag.BYTE,
        DataType.CHAR:   TTag.CHAR,
    }
    return _map.get(dt, TTag.INT)


# Integer/float type aliases defined via `as` that must not be treated as structs.
_PRIM_ALIAS_TTAG: dict = {
    'i8':  TTag.INT,  'i16': TTag.INT,  'i32': TTag.INT,  'i64': TTag.LONG,
    'u8':  TTag.UINT, 'u16': TTag.UINT, 'u32': TTag.UINT, 'u64': TTag.ULONG,
    'f32': TTag.FLOAT, 'f64': TTag.DOUBLE,
    'size_t': TTag.ULONG, 'ssize_t': TTag.LONG,
    'uintptr_t': TTag.ULONG, 'intptr_t': TTag.LONG,
    'ptrdiff_t': TTag.LONG,
}

def _prim_alias_ttag(name: str):
    """Return TTag for a known integer/float alias, or None if it is a real struct type."""
    t = _PRIM_ALIAS_TTAG.get(name)
    if t is not None:
        return t
    # data{N} aliases: i<bits> / u<bits> patterns
    if name and name[0] in ('i', 'u') and name[1:].isdigit():
        return TTag.LONG if name[0] == 'i' else TTag.ULONG
    return None


def _instr(op: Op, *operands) -> Instr:
    return Instr(op, list(operands))


# ---------------------------------------------------------------------------
# Codegen result
# ---------------------------------------------------------------------------

class ComptimeBytecode:
    """Holds the flat instruction list and local count produced for a comptime block."""
    def __init__(self, instructions: List[Instr], local_count: int):
        self.instructions = instructions
        self.local_count   = local_count


# ---------------------------------------------------------------------------
# FVMCodegen visitor
# ---------------------------------------------------------------------------

class FVMCodegenError(Exception):
    """Carries both a message and the AST node that caused the failure."""
    def __init__(self, message: str, node=None):
        self.override_src_text = None
        if node is not None:
            # For InlineAsm, build a rich display from the node's own body/constraints
            from fast import InlineAsm as _IA
            if isinstance(node, _IA):
                prefix = 'volatile asm' if node.is_volatile else 'asm'
                body_indented = '\n'.join('    ' + l for l in node.body.splitlines())
                constraints = f' : {node.constraints}' if node.constraints else ''
                self.override_src_text = f'{prefix}\n{{\n{body_indented}\n}}{constraints};'
        # Deliberately do not append a "[line:col]" suffix here: the raw
        # source_col doesn't account for tab expansion, and the outer
        # FluxCodegenError (fcodegen.py) already renders a correctly
        # tab-aware "[file:line:col]" header plus caret via source_node.
        # Embedding a second, raw-column location here produced confusing
        # duplicate/mismatched locations like "... [18:2]\n[test2.fx:18:5]".
        super().__init__(message)
        self.source_node = node


class FVMCodegen:
    """
    Visits a ComptimeBlock AST node and emits FluxVM bytecode.

    Usage:
        cg = FVMCodegen()
        bc = cg.compile(node, captured_scope)
        vm.execute(bc.instructions, bc.local_count)
    """

    def __init__(self, known_functions: Dict[str, list] = None,
                 known_struct_layouts: Dict[str, Any] = None,
                 program_statements: list = None):
        self._instructions: List[Instr] = []
        # Full top-level program statement list (module._program_statements),
        # used by _visit_deprecate to scan for lingering references to a
        # namespace marked with `deprecate`, mirroring fcodegen.py's
        # visit_DeprecateStatement.
        self._program_statements: list = program_statements or []
        # Maps variable name -> local slot index
        self._locals: Dict[str, int] = {}
        self._local_count: int = 0
        # Loop-level break/continue patch lists (list of instruction indices)
        self._loop_patches: List[Tuple[int, str]] = []
        # Stack of (break_patches, continue_patches) lists for nested loops.
        # _visit_break/_visit_continue append to the top entry.
        # Loop visitors push on entry and pop+resolve on exit.
        self._break_stack: List[List[int]] = []
        self._continue_stack: List[List[int]] = []
        # Compiled comptime functions: name -> List[Instr]
        self.compiled_functions: Dict[str, List[Instr]] = {}
        self.compiled_overloads: Dict[str, list] = {}
        # Previously accumulated comptime functions (from prior blocks) for lookup
        self._known_functions: Dict[str, list] = known_functions or {}
        # Maps local variable name -> declared type name (for type function resolution)
        self._local_types: Dict[str, str] = {}
        # Struct layouts computed from StructDef nodes: name -> StructLayout
        self._struct_layouts: Dict[str, Any] = dict(known_struct_layouts or {})
        # Label name -> instruction index (for goto resolution)
        self._labels: Dict[str, int] = {}
        # Goto patches: list of (instr_idx, label_name) to resolve after body
        self._goto_patches: List[Tuple[int, str]] = []
        # Name of the enclosing <~ strict-recursive function, or None.
        # When set, self-calls and returns emit TAIL_SELF instead of CALL/RET.
        self._tail_call_self: Optional[str] = None
        self._tail_call_argc: int = 0
        # Active using-namespaces (:: replaced with __) for name resolution
        self._using_namespaces: List[str] = []
        self._excluded_namespaces: set = set()
        # Known enum type names (must not be treated as structs)
        self._enum_names: set = set()
        # Current source line being compiled, stamped onto emitted instructions
        self._current_src_line: int = 0
        # Expression macro definitions registered at comptime codegen time
        self._macro_table: dict = {}
        # Names declared with `local` storage class - cannot escape scope
        self._local_vars: set = set()
        # Full TypeSystem for declared locals, for sizeof/typeof resolution
        self._local_typespecs: dict = {}
        # Heap-allocated variables: name -> (TTag, byte_size) for auto-deref on read
        self._heap_vars: dict = {}
        # Interface registry: name -> InterfaceDef node (mirrors module.symbol_table._interface_registry)
        self._interface_registry: dict = {}
        # Interface whitelist: (caller_type, callee_type) -> set of allowed method names
        # Built in _visit_object_def when processing interface annotations on objects.
        # Enforced in _visit_method_call, mirroring fcodegen's pass 3.6 + visit_MethodCall check.
        self._interface_whitelist: dict = {}
        # PASS_INTO whitelist: (provider_type, receiver_type) -> set of method names
        # whose return values may be passed as arguments into receiver_type methods.
        # Mirrors fcodegen._passinto_whitelist built in pass 3.6.
        self._passinto_whitelist: dict = {}
        # RETURN_TO whitelist: (provider_type, consumer_type) -> set of method names
        # that may be called from inside consumer_type method bodies.
        # Mirrors fcodegen._returnto_whitelist built in pass 3.6.
        self._returnto_whitelist: dict = {}
        # Trait registry: trait name -> list of prototype FunctionDef nodes.
        # Mirrors module.symbol_table._trait_registry populated by visit_TraitDef.
        self._trait_registry: dict = {}
        # Object traits map: object type name -> list of trait name strings.
        # Mirrors module._object_traits populated by visit_ObjectDef.
        self._object_traits: dict = {}
        # Name of the object type whose method body is currently being compiled.
        # Set/cleared in _visit_object_def per method, used by _visit_method_call to
        # identify the caller type for whitelist checks (mirrors module._current_object_name).
        self._current_object_name: str = None
        # Stack of per-block defer lists. Each entry is a list of deferred
        # statements (DeferStatement.body or [DeferStatement.expression]) for
        # the body currently being compiled by _visit_body. Mirrors
        # fcodegen.py's builder._flux_defer_stack but as an explicit stack
        # since fvmcodegen has no enclosing builder object.
        self._defer_stack: List[List] = []
        # Names declared at the top level of the comptime block (accessible to
        # nested function definitions via GLOBAL_GET / GLOBAL_SET).
        self._block_globals: set = set()
        # When True, this codegen is compiling a nested function body and should
        # use GLOBAL_GET/SET for names listed in _outer_globals.
        self._outer_globals: set = set()
        # True when this codegen instance is compiling a nested function
        # body (created via _visit_function_def / _visit_namespace_def).
        # Ordinary assignments to local variables in a function body must
        # stay local — they must NOT be mirrored into the VM's global
        # namespace, since that namespace is shared across every function
        # call and would let same-named locals in different functions (or
        # different invocations of the same function) alias each other.
        self._is_function_body: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile(
        self,
        node: ComptimeBlock,
        captured_scope: Dict[str, Val] = None,
    ) -> ComptimeBytecode:
        """
        Compile a ComptimeBlock to VM bytecode.

        captured_scope: variables from the enclosing Flux scope, captured by
        value (read-only).  Each entry is pre-allocated as a local slot and
        initialised with a PUSH / LOCAL_SET pair.
        """
        captured_scope = captured_scope or {}

        # Pre-allocate captured scope variables as read-only locals
        for name, val in captured_scope.items():
            slot = self._alloc_local(name)
            self._emit(_instr(Op.PUSH, val))
            self._emit(_instr(Op.LOCAL_SET, slot))

        # Compile the body
        self._visit_body(node.body)

        # Resolve any remaining forward goto patches
        self._resolve_goto_patches()

        # Terminate with HALT
        self._emit(_instr(Op.HALT))

        return ComptimeBytecode(self._instructions, self._local_count)

    # ------------------------------------------------------------------
    # Emit helpers
    # ------------------------------------------------------------------

    def _emit(self, instr: Instr) -> int:
        """Append an instruction, return its index."""
        if self._current_src_line and not instr.src_line:
            instr.src_line = self._current_src_line
        idx = len(self._instructions)
        self._instructions.append(instr)
        return idx

    def _current_ip(self) -> int:
        return len(self._instructions)

    def _alloc_local(self, name: str) -> int:
        if name not in self._locals:
            self._locals[name] = self._local_count
            self._local_count += 1
        return self._locals[name]

    def _check_const_assign(self, name: str, node, op_label: str = 'assignment'):
        """
        Raise a compile error if `name` was declared `const` and is now
        being reassigned. Mirrors the const-reassignment check performed
        for the main LLVM codegen path in
        AssignmentTypeHandler.handle_identifier_assignment /
        handle_compound_assignment (ftypesys.py), which the comptime VM
        codegen does not otherwise go through.
        """
        ts = self._local_typespecs.get(name)
        if ts is not None and getattr(ts, 'is_const', False):
            raise FVMCodegenError(
                f"Cannot modify const variable '{name}' with {op_label}",
                node
            )

    def _visit_deprecate(self, node: DeprecateStatement):
        """
        `deprecate NS;` is a compile-time-only static check: scan the whole
        program for any remaining Identifier/FunctionCall references to the
        deprecated (mangled) namespace and raise a ComptimeError if found.
        Emits nothing to bytecode. Mirrors fcodegen.py's
        visit_DeprecateStatement exactly, operating on
        self._program_statements (module._program_statements) instead of
        builder/module.
        """
        from fast import Identifier as _Identifier, FunctionCall as _FunctionCall, ASTNode as _ASTNode
        mangled = node.namespace_path.replace("::", "__")
        references = []

        def walk(n, path="<top>"):
            if n is None:
                return
            if isinstance(n, _Identifier):
                if n.name == mangled or n.name.startswith(mangled + "__"):
                    references.append(f"Identifier {n.name}")
            elif isinstance(n, _FunctionCall):
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
                    elif isinstance(child, _ASTNode):
                        walk(child, child_path)

        for stmt in self._program_statements:
            walk(stmt, type(stmt).__name__)

        if references:
            from fast import ComptimeError
            ref_list = "\n".join(references)
            raise ComptimeError(
                f"Deprecated namespace '{node.namespace_path}' is still referenced:\n"
                f"{ref_list}"
            )

    def _fresh_tmp(self) -> str:
        """Return a unique temp-variable name that cannot collide with user identifiers."""
        n = self._local_count
        return f'__tmp_{n}__'

    def _patch_at(self, idx: int, new_op: Op, addr: int):
        """Replace the instruction at idx with new_op targeting addr."""
        self._instructions[idx] = _instr(new_op, addr)

    def _visit_object_def(self, node: ObjectDef):
        """
        Compile each object method into self.compiled_functions under the key
        'ObjectName.method_name', mirroring fcodegen.py's _emit_method_body.

        Slot layout (matches _vardecl_call_constructor passing alloca as args[0]):
          slot 0 : this  (the STRUCT value, by value in the VM)
          slot 1+: explicit parameters (from method.parameters)

        Special cases matching fcodegen._emit_method_body:
          __init  -- implicit 'return this' (LOCAL_GET 0 / RET) if body doesn't terminate
          __exit  -- returns void; implicit PUSH void / RET if not terminated
          __expr  -- returns a pointer; body must explicitly return

        The object name is recorded in self._object_type_names so that
        _visit_var_decl can detect constructor calls (FunctionCall ending in .__init).
        """
        if not hasattr(self, '_object_type_names'):
            self._object_type_names = set()
        self._object_type_names.add(node.name)

        # Record the traits list for this object so that _visit_has_expression
        # can resolve 'expr has TraitName' at compile time.
        # Mirrors fcodegen.py's visit_ObjectDef storing into module._object_traits.
        self._object_traits[node.name] = list(node.traits)

        # Register a StructLayout for this object so STRUCT_NEW can find it.
        # Members map directly to layout fields; objects with no data members
        # get an empty layout (total_size=0). This mirrors how visit_ComptimeBlock
        # builds struct_layouts from module._struct_types for structs defined
        # outside the comptime block -- but those paths use LLVM ABI sizes.
        # Here we compute field sizes directly from the member TypeSpec.
        from fvm import StructLayout as _SL
        fields = []
        offset = 0
        for member in node.members:
            ts = getattr(member, 'type_spec', None)
            if ts is None:
                continue
            fsz = max(1, self._type_bit_width(ts) // 8)
            ftag = self._type_ttag_from_ts(ts)
            fields.append((member.name, ftag, offset, fsz))
            offset += fsz
        self._struct_layouts[node.name] = _SL(
            name=node.name, fields=fields, total_size=offset)

        # Build interface whitelists BEFORE compiling method bodies so that
        # _visit_method_call can enforce them during codegen of those bodies.
        # (If built after, the whitelists are empty when fn_cg runs.)
        for (iface_name, iface_args) in getattr(node, 'interfaces', None) or []:
            iface_node = self._interface_registry.get(iface_name)
            if iface_node is None:
                continue
            if len(iface_args) != len(iface_node.params):
                continue
            role_map = {}
            for role_arg, (role_name, _trait) in zip(iface_args, iface_node.params):
                role_map[role_name] = node.name if role_arg == 'this' else role_arg
            # Enforce trait constraints for both this object's own role and any
            # partner roles, mirroring fcodegen.py's pass 3.6 / pass 3.7 split but
            # collapsed into one step since the VM compiles objects as encountered
            # rather than in discrete whole-program passes. Look up partner ObjectDef
            # nodes from self._program_statements so their actual method lists can
            # be checked regardless of source order.
            from fast import ObjectDef as _ObjectDef, ObjectDefStatement as _ObjectDefStatement
            _all_obj_defs = {}
            for _stmt in self._program_statements:
                _od = None
                if isinstance(_stmt, _ObjectDef):
                    _od = _stmt
                elif isinstance(_stmt, _ObjectDefStatement):
                    _od = _stmt.object_def
                if _od is not None:
                    _all_obj_defs[_od.name] = _od
            for role_name, trait_name in iface_node.params:
                if trait_name is None:
                    raise FVMCodegenError(
                        f"Interface {iface_name}: parameter {role_name} has no trait "
                        f"constraint -- all interface parameters must declare a trait",
                        node)
                concrete = role_map.get(role_name)
                if concrete is None:
                    continue
                required = self._trait_registry.get(trait_name)
                if required is None:
                    raise FVMCodegenError(
                        f"Trait {trait_name} required by interface {iface_name} "
                        f"for role {role_name} is not defined",
                        node)
                if concrete == node.name:
                    _implemented_names = {m.name for m in node.methods}
                    _target_def = node
                else:
                    _target_def = _all_obj_defs.get(concrete)
                    if _target_def is None:
                        raise FVMCodegenError(
                            f"Interface {iface_name}: role {role_name} is bound to "
                            f"{concrete}, which is not a known object",
                            node)
                    _implemented_names = {m.name for m in _target_def.methods}
                for proto in required:
                    if getattr(proto, '_is_trait_template_proto', False):
                        continue
                    if proto.name not in _implemented_names:
                        raise FVMCodegenError(
                            f"Object {concrete} does not implement required function "
                            f"{proto.name} from {trait_name} trait "
                            f"(required by interface {iface_name} for role {role_name})",
                            node)
                # Keep _object_traits in sync for whichever concrete type this is.
                self._object_traits.setdefault(concrete, [])
                if trait_name not in self._object_traits[concrete]:
                    self._object_traits[concrete].append(trait_name)
            # Pre-register governed pairs as empty sets per kind. Only register a
            # pair in a given whitelist if the interface has a protocol of that kind
            # for that pair -- pre-registering all pairs in all whitelists would cause
            # directions governed only by RETURN_TO to be blocked by the CALL_ON check.
            from fast import ProtocolKind as _ProtocolKind
            for protocol in iface_node.protocols:
                _pc = role_map.get(protocol.caller)
                _pe = role_map.get(protocol.callee)
                if _pc is None or _pe is None:
                    continue
                _ppair = (_pc, _pe)
                _kind = getattr(protocol, 'kind', _ProtocolKind.CALL_ON)
                if _kind == _ProtocolKind.CALL_ON:
                    if _ppair not in self._interface_whitelist:
                        self._interface_whitelist[_ppair] = set()
                elif _kind == _ProtocolKind.PASS_INTO:
                    if _ppair not in self._passinto_whitelist:
                        self._passinto_whitelist[_ppair] = set()
                elif _kind == _ProtocolKind.RETURN_TO:
                    if _ppair not in self._returnto_whitelist:
                        self._returnto_whitelist[_ppair] = set()
            for protocol in iface_node.protocols:
                caller_concrete = role_map.get(protocol.caller)
                callee_concrete = role_map.get(protocol.callee)
                if caller_concrete is None or callee_concrete is None:
                    continue
                key = (caller_concrete, callee_concrete)
                _kind = getattr(protocol, 'kind', _ProtocolKind.CALL_ON)
                if _kind == _ProtocolKind.CALL_ON:
                    if key not in self._interface_whitelist:
                        self._interface_whitelist[key] = set()
                    for proto in protocol.methods:
                        self._interface_whitelist[key].add(proto.name)
                elif _kind == _ProtocolKind.PASS_INTO:
                    if key not in self._passinto_whitelist:
                        self._passinto_whitelist[key] = set()
                    for proto in protocol.methods:
                        self._passinto_whitelist[key].add(proto.name)
                elif _kind == _ProtocolKind.RETURN_TO:
                    if key not in self._returnto_whitelist:
                        self._returnto_whitelist[key] = set()
                    for proto in protocol.methods:
                        self._returnto_whitelist[key].add(proto.name)

        for method in node.methods:
            # Skip forward declarations (no body)
            if method.body is None:
                continue

            fn_cg = FVMCodegen(known_functions=dict(self._known_functions),
                               program_statements=self._program_statements)
            fn_cg._outer_globals    = set(self._block_globals)
            fn_cg._is_function_body = True
            fn_cg._using_namespaces = list(self._using_namespaces)
            fn_cg._struct_layouts   = dict(self._struct_layouts)
            fn_cg._enum_names       = set(self._enum_names)
            fn_cg._macro_table      = dict(self._macro_table)
            fn_cg._local_types      = dict(self._local_types)
            fn_cg._local_typespecs  = dict(self._local_typespecs)
            fn_cg.compiled_functions = dict(self.compiled_functions)
            # Propagate interface state so _visit_method_call can enforce
            # whitelists for calls made from inside this method body.
            fn_cg._interface_registry  = self._interface_registry
            fn_cg._interface_whitelist = self._interface_whitelist
            fn_cg._passinto_whitelist  = self._passinto_whitelist
            fn_cg._returnto_whitelist  = self._returnto_whitelist
            fn_cg._current_object_name = node.name  # mirrors module._current_object_name
            # Propagate trait/object-trait data so _visit_has_expression works
            # inside method bodies. Mirrors fcodegen's module._object_traits.
            fn_cg._trait_registry  = self._trait_registry
            fn_cg._object_traits   = dict(self._object_traits)

            # slot 0: 'this' -- the struct value, same as fcodegen's func.args[0]
            fn_cg._alloc_local('this')
            fn_cg._local_types['this'] = node.name

            # slots 1+: explicit parameters
            for param in method.parameters:
                fn_cg._alloc_local(param.name)
                if param.type_spec is not None:
                    fn_cg._local_typespecs[param.name] = param.type_spec
                    _ctn = getattr(param.type_spec, 'custom_typename', None)
                    if _ctn:
                        fn_cg._local_types[param.name] = _ctn
                    elif param.type_spec.base_type is not None:
                        _bt = param.type_spec.base_type
                        fn_cg._local_types[param.name] = (
                            str(_bt.value) if hasattr(_bt, 'value') else str(_bt))

            body_stmts = (method.body.statements
                          if isinstance(method.body, Block) else [method.body])
            fn_cg._visit_body(body_stmts)

            last_op = fn_cg._instructions[-1].op if fn_cg._instructions else None
            if last_op not in (Op.RET, Op.TAIL_SELF):
                # All methods implicitly return this (slot 0) so the call site
                # can write the mutated struct back into the receiver variable.
                # fcodegen achieves this transparently via pointer; the VM passes
                # structs by value so every method must return the (possibly
                # mutated) this so the caller can store it back. Matches
                # fcodegen's implicit method_builder.ret(func.args[0]) for __init.
                fn_cg._emit(_instr(Op.LOCAL_GET, 0))
                fn_cg._emit(_instr(Op.RET))

            func_key = f"{node.name}.{method.name}"
            self.compiled_functions[func_key] = fn_cg._instructions
            # propagate any nested definitions
            for _k, _v in fn_cg.compiled_functions.items():
                if _k not in self.compiled_functions:
                    self.compiled_functions[_k] = _v


    def _visit_assert(self, node: AssertStatement):
        """
        assert(cond, msg) at comptime: evaluate the condition; if false,
        print the message via COMPILER_PRINT and PANIC to abort the
        comptime block. Per Karac's direction, the message is printed
        using the compiler's own console print path (Op.COMPILER_PRINT).

        Bytecode emitted:
            <condition>
            JIF  -> skip_fail
            <message | default string>
            COMPILER_PRINT
            PANIC
          skip_fail:
        """
        # Evaluate condition; JIF skips the failure block if truthy
        self._visit_expr(node.condition)
        skip_idx = self._emit(_instr(Op.JIF, 0))

        # Build the assertion failure message.
        # The parser stores plain string literals as raw Python str
        # (STRING_LITERAL -> .value); f-string/i-string nodes are AST
        # Expression nodes. Handle both cases.
        if node.message is not None:
            if isinstance(node.message, str):
                self._emit(_instr(Op.PUSH, Val(TTag.BYTES, node.message.encode())))
            else:
                self._visit_expr(node.message)
        else:
            line = getattr(node, 'source_line', '?')
            col  = getattr(node, 'source_col',  '?')
            self._emit(_instr(Op.PUSH, Val(TTag.BYTES,
                f"Assertion failed at [{line}:{col}]\n".encode())))

        self._emit(_instr(Op.PANIC))

        # Patch the JIF to jump here (past the failure block)
        self._patch_at(skip_idx, Op.JIF, self._current_ip())

    def _visit_throw(self, node: ThrowStatement):
        """
        throw expr; -- pushes the expression value and raises FluxThrowSignal.
        Mirrors fcodegen's visit_ThrowStatement which stores into flux_exception_value
        and branches to the catch handler. Here the VM catches FluxThrowSignal in _run.
        """
        self._visit_expr(node.expression)
        self._emit(_instr(Op.THROW))

    def _visit_try(self, node: TryBlock):
        """
        try { ... } catch (T e) { ... }

        Bytecode layout (mirrors fcodegen's try_block/catch_block basic-block structure):
            TRY_BEGIN <catch_addr>
              <try body>
            TRY_END
            JMP <after_all_catches>
          catch_0_addr:
            [LOCAL_SET <slot>  if catch var named]
            <catch_0 body>
            JMP <after_all_catches>
          catch_1_addr:
            ...
          after_all_catches:

        THROW pops a value and raises FluxThrowSignal; _run catches it,
        finds the nearest TRY_BEGIN handler on the frame stack, restores
        the stack to the TRY_BEGIN depth, pushes the thrown value, and
        jumps to catch_addr.
        """
        # Emit TRY_BEGIN with a placeholder catch address
        try_begin_idx = self._emit(_instr(Op.TRY_BEGIN, 0))

        # Emit try body
        try_stmts = (node.try_body.statements
                     if isinstance(node.try_body, Block) else [node.try_body])
        self._visit_body(try_stmts)

        # Normal exit from try: pop the handler and jump past all catches
        self._emit(_instr(Op.TRY_END))
        jmp_past_idx = self._emit(_instr(Op.JMP, 0))

        # Patch TRY_BEGIN to point here (start of first catch)
        first_catch_addr = self._current_ip()
        self._patch_at(try_begin_idx, Op.TRY_BEGIN, first_catch_addr)

        after_patches = []
        for i, (exc_type, exc_name, catch_body) in enumerate(node.catch_blocks):
            catch_start = self._current_ip()
            if i > 0:
                # Patch previous catch's JMP to here for chained catches
                # (single-catch is the common case; multiple catches share the
                # same thrown value dispatch since we have no type dispatch in VM)
                pass

            # The thrown value is on top of the stack (pushed by _run after THROW).
            if exc_name:
                slot = self._alloc_local(exc_name)
                if exc_type is not None and hasattr(exc_type, 'custom_typename') and exc_type.custom_typename:
                    self._local_types[exc_name] = exc_type.custom_typename
                self._emit(_instr(Op.LOCAL_SET, slot))
            else:
                self._emit(_instr(Op.POP))

            catch_stmts = (catch_body.statements
                           if isinstance(catch_body, Block) else [catch_body])
            self._visit_body(catch_stmts)

            after_patches.append(self._emit(_instr(Op.JMP, 0)))

        after_addr = self._current_ip()
        self._patch_at(jmp_past_idx, Op.JMP, after_addr)
        for idx in after_patches:
            self._patch_at(idx, Op.JMP, after_addr)

    def _visit_body(self, stmts: list):
        """
        Each body (block) gets its own defer scope, mirroring fcodegen.py's
        per-Block builder._flux_defer_stack. Statements registered via
        `defer` within this body are run (in reverse order) when this body
        falls through to its natural end; _visit_return/_visit_escape also
        flush all active scopes (this one and any enclosing ones) before
        emitting RET, since a return exits every enclosing block too.
        """
        self._defer_stack.append([])
        try:
            self._visit_body_stmts(stmts)
            self._flush_defers(self._defer_stack[-1])
        finally:
            self._defer_stack.pop()

    def _visit_defer(self, node: DeferStatement):
        if node.body is not None:
            self._defer_stack[-1].append(node.body)
        else:
            self._defer_stack[-1].append(node.expression)

    def _flush_defers(self, deferred_list: list):
        """Emit a list of deferred statements/expressions in reverse order."""
        for deferred in reversed(deferred_list):
            if isinstance(deferred, list):
                for stmt in reversed(deferred):
                    self._visit_stmt(stmt)
            elif isinstance(deferred, Expression):
                pushes = self._visit_expr(deferred)
                if pushes:
                    self._emit(_instr(Op.POP))
            else:
                self._visit_stmt(deferred)

    def _flush_all_defers(self):
        """
        Emit all pending deferred statements across every active scope,
        innermost scope first, used before RET/TAIL_SELF since a return
        exits every enclosing block.
        """
        for deferred_list in reversed(self._defer_stack):
            self._flush_defers(deferred_list)

    def _visit_body_stmts(self, stmts: list):
        from fast import ArrayLiteral as _AL
        _unpack_targets = {DataType.SINT, DataType.UINT, DataType.SLONG, DataType.ULONG,
                           DataType.BYTE, DataType.CHAR}

        # Pre-scan: find unpack groups. Pattern: one or more None-init VariableDeclarations
        # of the same type immediately followed by an ArrayLiteral([src]) VariableDeclaration.
        # Mark each group as (start_idx, end_idx_inclusive, src_expr).
        unpack_ranges: dict = {}  # start_idx -> (end_idx, src_expr)
        skip_indices: set = set()
        j = 0
        while j < len(stmts):
            s = stmts[j]
            if (isinstance(s, VariableDeclaration) and
                    s.initial_value is not None and
                    isinstance(s.initial_value, _AL) and
                    not s.initial_value.is_string and
                    len(s.initial_value.elements) == 1 and
                    s.type_spec is not None and
                    not s.type_spec.is_array and
                    s.type_spec.base_type in _unpack_targets):
                # Look back for None-init declarations of the same type
                k = j - 1
                while (k >= 0 and k not in skip_indices and
                       isinstance(stmts[k], VariableDeclaration) and
                       stmts[k].initial_value is None and
                       stmts[k].type_spec is not None and
                       stmts[k].type_spec.base_type == s.type_spec.base_type):
                    k -= 1
                group_start = k + 1
                if group_start < j:
                    unpack_ranges[group_start] = (j, s.initial_value.elements[0])
                    for idx in range(group_start, j + 1):
                        skip_indices.add(idx)
            j += 1

        i = 0
        while i < len(stmts):
            if i in unpack_ranges:
                end_idx, src_expr = unpack_ranges[i]
                group = stmts[i:end_idx + 1]
                self._emit_unpack(group, src_expr)
                i = end_idx + 1
            elif i in skip_indices:
                i += 1
            else:
                self._visit_stmt(stmts[i])
                i += 1

    def _visit_stmt(self, node: ASTNode):
        if node is None:
            return
        src = getattr(node, 'source_line', 0)
        if src:
            self._current_src_line = src
        t = type(node)
        if t is VariableDeclaration:     self._visit_var_decl(node)
        elif t is TypeDeclaration:       self._visit_type_decl(node)
        elif t is Assignment:            self._visit_assignment(node)
        elif t is CompoundAssignment:    self._visit_compound_assign(node)
        elif t is ExpressionStatement:   self._visit_expr_stmt(node)
        elif t is IfStatement:           self._visit_if(node)
        elif t is ForLoop:               self._visit_for(node)
        elif t is ForInLoop:             self._visit_for_in(node)
        elif t is WhileLoop:             self._visit_while(node)
        elif t is DoLoop:                self._visit_do(node)
        elif t is DoWhileLoop:           self._visit_do_while(node)
        elif t is DeferStatement:        self._visit_defer(node)
        elif t is NoreturnStatement:     self._emit(_instr(Op.HALT))  # mirrors fcodegen's builder.unreachable()
        elif t is TryBlock:              self._visit_try(node)
        elif t is ThrowStatement:        self._visit_throw(node)
        elif t is ReturnStatement:       self._visit_return(node)
        elif t is BreakStatement:        self._visit_break(node)
        elif t is EscapeStatement:       self._visit_escape(node)
        elif t is ContinueStatement:     self._visit_continue(node)
        elif t is Block:                 self._visit_body(node.statements)
        elif t is SwitchStatement:       self._visit_switch(node)
        elif t is FunctionDef:           self._visit_function_def(node)
        elif t is FunctionDefStatement:  self._visit_function_def(node.function_def)
        elif t is FunctionPointerDeclaration: self._visit_fp_decl(node)
        elif t is TypeFuncDef:           self._visit_type_func_def(node)
        elif t is NamespaceDef:          self._visit_namespace_def(node)
        elif t is NamespaceDefStatement: self._visit_namespace_def(node.namespace_def)
        elif t is StructDef:             self._visit_struct_def(node)
        elif t is StructDefStatement:    self._visit_struct_def(node.struct_def)
        elif t is StructFieldAssign:     self._visit_struct_field_assign(node)
        elif t is UnionDef:              self._visit_union_def(node)
        elif t is UnionDefStatement:     self._visit_union_def(node.union_def)
        elif t is ConstraDef:            pass  # compile-time only, no VM emission
        elif t is ContractDef:           pass  # compile-time only; body already inlined into annotated functions by the parser, matches fcodegen.py's visit_ContractDef
        elif t is ObjectDef:             self._visit_object_def(node)
        elif t is ObjectDefStatement:    self._visit_object_def(node.object_def)
        elif t is TraitDef:
            # Register the trait so _visit_has_expression can verify trait names.
            # Mirrors fcodegen.py's visit_TraitDef storing into
            # module.symbol_table._trait_registry.
            self._trait_registry[node.name] = node.prototypes
        elif t is InterfaceDef:          self._interface_registry[node.name] = node
        elif t is DeprecateStatement:    self._visit_deprecate(node)
        elif t is AssertStatement:       self._visit_assert(node)
        elif t is macroDefStatement:     self._macro_table[node.macro_def.name] = node.macro_def
        elif t.__name__ in ('macroDef', 'ExportBlock'): pass  # no VM emission
        elif t is ExternBlock:           self._visit_extern_block(node)
        elif t is EnumDef:               self._visit_enum_def(node)
        elif t is EnumDefStatement:      self._visit_enum_def(node.enum_def)
        elif t is LabelStatement:        self._visit_label(node)
        elif t is GotoStatement:         self._visit_goto(node)
        elif t is JumpStatement:         self._visit_jump(node)
        elif t is EmitFlux:              self._visit_emitflux(node)
        elif t is FluxVMBlock:           self._visit_fluxvm_block(node)
        elif t is ComptimeBlock:         self._visit_body(node.body)
        elif isinstance(node, list):     self._visit_body(node)
        elif t is UsingStatement:        self._visit_using(node)
        elif t is NotUsingStatement:     self._visit_not_using(node)
        else:
            raise FVMCodegenError(
                f'fvmcodegen: unsupported node in comptime: {type(node).__name__}',
                node
            )

    # ------------------------------------------------------------------
    # Variable declaration
    # ------------------------------------------------------------------

    def _visit_type_decl(self, node: TypeDeclaration):
        """
        Type alias declaration: data{8} as nbyte; or int as myint;
        At comptime this has no runtime effect — register the alias name so
        that subsequent variable declarations using it resolve correctly.
        If an initial value is present treat it like a variable declaration.
        """
        if node.type_spec is not None:
            bt = node.type_spec.base_type
            if node.type_spec.custom_typename:
                self._local_types[node.name] = node.type_spec.custom_typename
            elif bt is not None and bt == DataType.DATA and node.type_spec.bit_width:
                self._local_types[node.name] = f'__data_{node.type_spec.bit_width}'
            elif bt is not None:
                self._local_types[node.name] = bt.value if hasattr(bt, 'value') else str(bt)
        if node.initial_value is not None and not isinstance(node.initial_value, NoInit):
            slot = self._alloc_local(node.name)
            self._visit_expr(node.initial_value)
            self._emit(_instr(Op.LOCAL_SET, slot))

    def _visit_var_decl(self, node: VariableDeclaration):
        slot = self._alloc_local(node.name)
        # Track local storage class — local variables cannot escape scope
        if (node.type_spec is not None and
                getattr(node.type_spec, 'is_local', False)):
            self._local_vars.add(node.name)
        # Handle heap storage class — allocate on VM heap, slot holds PTR, reads auto-deref
        from ftypesys import StorageClass as _SC
        from fast import ArrayLiteral as _AL
        if (node.type_spec is not None and
                getattr(node.type_spec, 'storage_class', None) == _SC.HEAP):
            ts = node.type_spec
            if ts.is_array:
                # Array: allocate count * elem_size bytes
                arr_size = ts.array_size
                if hasattr(arr_size, 'value'):
                    arr_size = int(arr_size.value)
                else:
                    arr_size = int(arr_size)
                elem_bits = self._type_bit_width_base(ts.base_type, ts)
                elem_bytes = max(1, elem_bits // 8)
                elem_ttag = _datatype_to_ttag(ts.base_type)
                total_bytes = arr_size * elem_bytes
                self._heap_vars[node.name] = (elem_ttag, elem_bytes, arr_size)
                self._emit(_instr(Op.PUSH, Val(TTag.UINT, total_bytes)))
                self._emit(_instr(Op.ALLOC))   # PTR to base
                if node.initial_value is not None and isinstance(node.initial_value, _AL):
                    # Store each element at ptr + i*elem_bytes
                    for i, elem in enumerate(node.initial_value.elements):
                        self._emit(_instr(Op.DUP))               # ptr
                        self._emit(_instr(Op.PUSH, Val(TTag.UINT, i * elem_bytes)))
                        self._emit(_instr(Op.ADD))               # ptr + offset
                        self._visit_expr(elem)
                        self._emit(_instr(Op.STORE, elem_ttag, elem_bytes))
                self._emit(_instr(Op.LOCAL_SET, slot))
            else:
                bits      = self._type_bit_width(ts)
                byte_size = max(1, bits // 8)
                ttag      = self._type_ttag_from_ts(ts)
                self._heap_vars[node.name] = (ttag, byte_size)
                self._emit(_instr(Op.PUSH, Val(TTag.UINT, byte_size)))
                self._emit(_instr(Op.ALLOC))
                if node.initial_value is not None and not isinstance(node.initial_value, NoInit):
                    self._emit(_instr(Op.DUP))
                    self._visit_expr(node.initial_value)
                    self._emit(_instr(Op.STORE, ttag, byte_size))
                self._emit(_instr(Op.LOCAL_SET, slot))
            return
        # Handle singinit storage class — initialize once, persist in _globals
        from ftypesys import StorageClass as _SC2
        if (node.type_spec is not None and
                getattr(node.type_spec, 'storage_class', None) == _SC2.SINGINIT):
            guard_name = f'__singinit_guard__{node.name}'
            # Only initialize if guard not already set
            # Emit: if GLOBAL_GET guard == 0, initialize and set guard
            done_patch_idx = None
            self._emit(_instr(Op.GLOBAL_GET, guard_name))
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 0)))
            self._emit(_instr(Op.CMP_EQ))
            jnf_idx = self._emit(_instr(Op.JNF, 0))  # skip init if already done
            # Init block: evaluate initializer and store in globals
            if node.initial_value is not None and not isinstance(node.initial_value, NoInit):
                self._visit_expr(node.initial_value)
            else:
                ttag2 = self._type_ttag_from_ts(node.type_spec)
                self._emit(_instr(Op.PUSH, Val(ttag2, 0)))
            self._emit(_instr(Op.DUP))
            self._emit(_instr(Op.LOCAL_SET, slot))
            self._emit(_instr(Op.GLOBAL_SET, node.name))
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
            self._emit(_instr(Op.GLOBAL_SET, guard_name))
            jmp_idx = self._emit(_instr(Op.JMP, 0))
            # Done block: load from globals into local slot
            done_ip = self._current_ip()
            self._patch_at(jnf_idx, Op.JNF, done_ip)
            self._emit(_instr(Op.GLOBAL_GET, node.name))
            self._emit(_instr(Op.LOCAL_SET, slot))
            after_ip = self._current_ip()
            self._patch_at(jmp_idx, Op.JMP, after_ip)
            self._block_globals.add(node.name)
            self._block_globals.add(guard_name)
            # Record type so nested fn_cg bodies can resolve typed array access
            if node.type_spec is not None:
                _ts2 = node.type_spec
                self._local_typespecs[node.name] = _ts2
                if _ts2.custom_typename:
                    self._local_types[node.name] = _ts2.custom_typename
                elif _ts2.base_type is not None:
                    self._local_types[node.name] = (str(_ts2.base_type.value)
                                                    if hasattr(_ts2.base_type, 'value')
                                                    else str(_ts2.base_type))
            return

        # Record the type name and full typespec for type function resolution
        if node.type_spec is not None:
            ts = node.type_spec
            self._local_typespecs[node.name] = ts
            if ts.custom_typename:
                self._local_types[node.name] = ts.custom_typename
            elif ts.base_type is not None:
                self._local_types[node.name] = str(ts.base_type.value) if hasattr(ts.base_type, 'value') else str(ts.base_type)
        if node.initial_value is not None and not isinstance(node.initial_value, NoInit):
            # Constructor call: MyObj1 newObj()  ->  initial_value is FunctionCall('MyObj1.__init', args)
            # fcodegen._vardecl_call_constructor prepends alloca (this) as args[0].
            # Mirror that: emit STRUCT_NEW to create the struct, then call __init
            # with this (the struct) as slot 0, followed by explicit args.
            if (isinstance(node.initial_value, FunctionCall) and
                    node.initial_value.name.endswith('.__init')):
                type_name = node.initial_value.name[:-len('.__init')]
                self._emit(_instr(Op.STRUCT_NEW, type_name))   # push this
                for arg in node.initial_value.arguments:
                    self._visit_expr(arg)
                argc = 1 + len(node.initial_value.arguments)
                self._emit(_instr(Op.CALL, node.initial_value.name, argc))
                self._emit(_instr(Op.DUP))
                self._emit(_instr(Op.LOCAL_SET, slot))
                self._emit(_instr(Op.GLOBAL_SET, node.name))
                self._block_globals.add(node.name)
                return
            # Pack expression: scalar_type var = [a, b, ...] packs elements into an integer.
            # Detect this when the target type is a scalar integer and the initial value
            # is an ArrayLiteral that is not a string.
            from fast import ArrayLiteral as _AL
            _pack_targets = {DataType.SINT, DataType.UINT, DataType.SLONG, DataType.ULONG,
                             DataType.BYTE, DataType.CHAR}
            if (node.type_spec is not None and
                    not node.type_spec.is_array and
                    isinstance(node.initial_value, _AL) and
                    not node.initial_value.is_string and
                    node.type_spec.base_type in _pack_targets):
                self._emit_pack(node.initial_value, node.type_spec)
            else:
                self._visit_expr(node.initial_value)
                # Coerce the initializer's value to the declared type, the
                # same way the compiler implicitly converts an initializer
                # expression to the target variable's type (e.g. `long x = 5;`
                # must store 5 as a 64-bit value, not as the literal's
                # default 32-bit int).  Only applies to plain numeric scalar
                # declarations -- pointers, structs, enums and arrays are
                # handled separately above/below.
                if (node.type_spec is not None and
                        not getattr(node.type_spec, 'is_array', False) and
                        not getattr(node.type_spec, 'is_pointer', False)):
                    _decl_ttag = self._type_ttag_from_ts(node.type_spec)
                    if _decl_ttag in (TTag.INT, TTag.UINT, TTag.LONG, TTag.ULONG,
                                       TTag.BYTE, TTag.CHAR, TTag.FLOAT, TTag.DOUBLE,
                                       TTag.BOOL):
                        self._emit(_instr(Op.CAST, _decl_ttag))
            # If the declared type is a pointer to a named struct (e.g. BlockEntry* entry = ...),
            # tag the result with CAST PTR typename so STRUCT_LOAD can read fields through it.
            if (node.type_spec is not None and
                    getattr(node.type_spec, 'is_pointer', False) and
                    getattr(node.type_spec, 'custom_typename', None) and
                    node.type_spec.custom_typename not in self._enum_names and
                    _prim_alias_ttag(node.type_spec.custom_typename) is None):
                self._emit(_instr(Op.CAST, TTag.PTR, node.type_spec.custom_typename))
        else:
            # Zero-initialise (all Flux variables are zero-init by default)
            if (node.type_spec is not None and
                    getattr(node.type_spec, 'is_array', False) and
                    getattr(node.type_spec, 'array_size', None) is not None):
                # Stack-allocated array: emit ARRAY_NEW with zero elements
                _arr_sz = node.type_spec.array_size
                if hasattr(_arr_sz, 'value'): _arr_sz = int(_arr_sz.value)
                else: _arr_sz = int(_arr_sz)
                _elem_ttag = _datatype_to_ttag(
                    node.type_spec.base_type if node.type_spec.base_type is not None else DataType.SINT
                )
                self._emit(_instr(Op.ARRAY_NEW, _elem_ttag, _arr_sz))
            elif (node.type_spec is not None and
                    node.type_spec.custom_typename is not None):
                _ctn = node.type_spec.custom_typename
                _prim = _prim_alias_ttag(_ctn)
                if _prim is not None:
                    self._emit(_instr(Op.PUSH, Val(_prim, 0)))
                elif _ctn in self._enum_names:
                    self._emit(_instr(Op.ENUM_NEW, _ctn))
                else:
                    # Emit STRUCT_NEW even for types not yet in _struct_layouts --
                    # layout resolved at VM runtime after compiler.import.* runs
                    self._emit(_instr(Op.STRUCT_NEW, _ctn))
            else:
                ttag = _datatype_to_ttag(
                    node.type_spec.base_type if node.type_spec else DataType.SINT
                )
                self._emit(_instr(Op.PUSH, Val(ttag, 0)))
        # Mirror to VM globals so nested function bodies can access this variable.
        self._block_globals.add(node.name)
        self._emit(_instr(Op.DUP))
        self._emit(_instr(Op.LOCAL_SET, slot))
        self._emit(_instr(Op.GLOBAL_SET, node.name))

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _visit_assignment(self, node: Assignment):
        if isinstance(node.target, Identifier):
            name = node.target.name
            self._check_const_assign(name, node, 'assignment')
            if name in self._outer_globals:
                self._visit_expr(node.value)
                self._emit(_instr(Op.GLOBAL_SET, name))
                return
            if self._is_function_body:
                # Ordinary local variable inside a function body: stays
                # purely local. Mirroring into the shared VM global
                # namespace would let same-named locals in other functions
                # (or other calls to this function) alias each other.
                self._visit_expr(node.value)
                slot = self._alloc_local(name)
                self._emit(_instr(Op.LOCAL_SET, slot))
                return
            # At top-level comptime-block scope, assignments are also
            # mirrored as globals so nested function bodies (compiled as
            # separate fn_cg instances) can access them via GLOBAL_GET.
            self._block_globals.add(name)
            self._visit_expr(node.value)
            slot = self._alloc_local(name)
            self._emit(_instr(Op.DUP))
            self._emit(_instr(Op.LOCAL_SET, slot))
            self._emit(_instr(Op.GLOBAL_SET, name))
            return
        elif isinstance(node.target, MemberAccess):
            # struct.field = value -> LOCAL_GET + val + STRUCT_STORE field + LOCAL_SET
            if node.target.member == '#':
                # me1._ = MyUnionType -> ENUM_STORE
                if isinstance(node.target.object, Identifier):
                    var_name  = node.target.object.name
                    type_name = self._local_types.get(var_name)
                    if type_name and type_name in self._enum_names:
                        self._visit_expr(node.target.object)
                        self._visit_expr(node.value)
                        self._emit(_instr(Op.ENUM_STORE))
                        slot = self._alloc_local(var_name)
                        self._emit(_instr(Op.LOCAL_SET, slot))
                        return
                # Fallback: synthetic tag slot
                tag_slot_name = f'__{node.target.object.name if isinstance(node.target.object, Identifier) else "__"}__tag__'
                tag_slot = self._alloc_local(tag_slot_name)
                self._visit_expr(node.value)
                self._emit(_instr(Op.LOCAL_SET, tag_slot))
            elif isinstance(node.target.object, Identifier):
                var_name = node.target.object.name
                is_global = (var_name in self._block_globals or
                             var_name in self._outer_globals)
                self._visit_expr(node.target.object)  # push current struct
                self._visit_expr(node.value)
                self._emit(_instr(Op.STRUCT_STORE, node.target.member))
                if is_global:
                    self._emit(_instr(Op.GLOBAL_SET, var_name))  # write back to global
                else:
                    slot = self._alloc_local(var_name)
                    self._emit(_instr(Op.LOCAL_SET, slot))  # write back to local
            else:
                # Complex lhs: e.g. tbl[idx].field = val
                # If the object is an ArrayAccess into a known struct-pointer,
                # we need to: compute addr, DUP, LOAD struct, push val,
                # STRUCT_STORE field, then STORE struct back to addr.
                _obj = node.target.object
                _is_struct_ptr_array = (
                    isinstance(_obj, ArrayAccess)
                    and isinstance(_obj.array, Identifier)
                    and (self._local_types.get(_obj.array.name) or
                         getattr(self._local_typespecs.get(_obj.array.name), 'custom_typename', None))
                    in self._struct_layouts
                )
                if _is_struct_ptr_array:
                    _arr_name = _obj.array.name
                    _type_name = (self._local_types.get(_arr_name) or
                                  getattr(self._local_typespecs.get(_arr_name), 'custom_typename', None))
                    _layout = self._struct_layouts[_type_name]
                    _struct_size = _layout.total_size
                    # compute GEP address
                    self._visit_expr(_obj.array)
                    self._visit_expr(_obj.index)
                    self._emit(_instr(Op.PUSH, Val(TTag.UINT, _struct_size)))
                    self._emit(_instr(Op.MUL))
                    self._emit(_instr(Op.ADD))
                    # DUP: one copy for LOAD, one for STORE writeback
                    self._emit(_instr(Op.DUP))
                    # load current struct value
                    self._emit(_instr(Op.LOAD, TTag.STRUCT, _struct_size, _type_name))
                    # push the new field value
                    self._visit_expr(node.value)
                    # modify the field in the Val
                    self._emit(_instr(Op.STRUCT_STORE, node.target.member))
                    # stack: addr, modified_struct -> STORE back to heap
                    self._emit(_instr(Op.STORE, TTag.STRUCT, _struct_size, _type_name))
                else:
                    self._visit_expr(node.target.object)
                    self._visit_expr(node.value)
                    self._emit(_instr(Op.STRUCT_STORE, node.target.member))
        elif isinstance(node.target, ArrayAccess):
            if not isinstance(node.target.array, Identifier):
                raise FVMCodegenError(
                    'fvmcodegen: array assignment target must be a simple identifier in comptime',
                    node
                )
            arr_name = node.target.array.name
            # Heap array: compute address and use typed STORE
            if arr_name in self._heap_vars:
                heap_info = self._heap_vars[arr_name]
                if len(heap_info) == 3:
                    elem_ttag, elem_bytes, _count = heap_info
                    self._emit(_instr(Op.LOCAL_GET, self._locals[arr_name]))
                    self._visit_expr(node.target.index)
                    if elem_bytes > 1:
                        self._emit(_instr(Op.PUSH, Val(TTag.UINT, elem_bytes)))
                        self._emit(_instr(Op.MUL))
                    self._emit(_instr(Op.ADD))
                    self._visit_expr(node.value)
                    self._emit(_instr(Op.STORE, elem_ttag, elem_bytes))
                    return
            arr_slot = self._alloc_local(arr_name)
            # Check if this is a pointer-to-pointer array (e.g. byte** argv)
            # In that case, elements are pointer-sized (8 bytes) and need GEP+STORE
            _ts = self._local_typespecs.get(arr_name)
            _ptr_depth = getattr(_ts, 'pointer_depth', 0) if _ts is not None else 0
            _is_ptr_to_ptr = _ptr_depth >= 2
            if not _is_ptr_to_ptr and _ts is not None:
                # Also check non-array pointer to custom type
                _ctn = getattr(_ts, 'custom_typename', None)
                _is_ptr = getattr(_ts, 'is_pointer', False)
                _is_arr = getattr(_ts, 'is_array', False)
                if _is_ptr and not _is_arr and _ctn and _ctn in self._struct_layouts:
                    _is_ptr_to_ptr = True  # struct pointer, handled below
            if _is_ptr_to_ptr:
                # pointer-to-pointer: stride = 8 (pointer size)
                _elem_bytes = 8
                self._visit_expr(node.target.array)   # push base ptr
                self._visit_expr(node.target.index)   # push index
                self._emit(_instr(Op.PUSH, Val(TTag.UINT, _elem_bytes)))
                self._emit(_instr(Op.MUL))
                self._emit(_instr(Op.ADD))
                self._visit_expr(node.value)
                self._emit(_instr(Op.STORE, TTag.PTR, _elem_bytes))
                return
            self._visit_expr(node.target.array)   # push array
            self._visit_expr(node.target.index)   # push index
            self._visit_expr(node.value)           # push value
            self._emit(_instr(Op.ARRAY_STORE))     # -> updated array
            self._emit(_instr(Op.LOCAL_SET, arr_slot))  # write back
        elif isinstance(node.target, PointerDeref):
            # *ptr = value  ->  push ptr, push value, LOCAL_DEREF_SET
            self._visit_expr(node.target.pointer)
            self._visit_expr(node.value)
            self._emit(_instr(Op.LOCAL_DEREF_SET))
        else:
            raise FVMCodegenError(
                f'fvmcodegen: unsupported assignment target in comptime: {type(node.target).__name__}',
                node
            )

    def _visit_compound_assign(self, node: CompoundAssignment):
        """Desugar compound assignment: x op= val  ->  x = x op val"""
        if not isinstance(node.target, Identifier):
            loc = f' [{node.source_line}:{node.source_col}]' if node.source_line else ''
            raise NotImplementedError(
                f'fvmcodegen: only simple identifier compound-assignment in comptime{loc}'
            )
        name = node.target.name
        self._check_const_assign(name, node, 'compound assignment')
        slot = self._alloc_local(name)
        # Push LHS
        self._emit(_instr(Op.LOCAL_GET, slot))
        # Push RHS
        self._visit_expr(node.value)
        # Emit the base operator
        self._emit_binary_op_for_compound(node.op_token)
        # Store result
        self._emit(_instr(Op.LOCAL_SET, slot))

    def _emit_binary_op_for_compound(self, op_token):
        """Map a compound-assignment operator token to its base binary opcode."""
        from flexer import TokenType
        _map = {
            TokenType.PLUS_ASSIGN:            Op.ADD,
            TokenType.MINUS_ASSIGN:           Op.SUB,
            TokenType.MULTIPLY_ASSIGN:        Op.MUL,
            TokenType.DIVIDE_ASSIGN:          Op.DIV,
            TokenType.MODULO_ASSIGN:          Op.MOD,
            TokenType.POWER_ASSIGN:           Op.POW,
            TokenType.AND_ASSIGN:             Op.BAND,
            TokenType.OR_ASSIGN:              Op.BOR,
            TokenType.XOR_ASSIGN:             Op.BXOR,
            TokenType.BITAND_ASSIGN:          Op.BAND,
            TokenType.BITOR_ASSIGN:           Op.BOR,
            TokenType.BITXOR_ASSIGN:          Op.BXOR,
            TokenType.BITSHIFT_LEFT_ASSIGN:   Op.SHL,
            TokenType.BITSHIFT_RIGHT_ASSIGN:  Op.SHR,
        }
        oc = _map.get(op_token)
        if oc:
            self._emit(_instr(oc))
        else:
            raise NotImplementedError(
                f'fvmcodegen: compound assign op {op_token!r} not supported'
            )

    # ------------------------------------------------------------------
    # Expression statement
    # ------------------------------------------------------------------

    def _visit_expr_stmt(self, node: ExpressionStatement):
        pushes = self._visit_expr(node.expression)
        # Only pop if the expression left a value on the stack
        if pushes:
            self._emit(_instr(Op.POP))

    # ------------------------------------------------------------------
    # Expressions
    # ------------------------------------------------------------------

    def _visit_expr(self, node: ASTNode) -> bool:
        """
        Compile an expression.
        Returns True if a value was left on the VM stack, False if not
        (e.g. void compiler.io calls that consume args and push nothing).
        """
        t = type(node)
        if t is Literal:               return self._visit_literal(node)
        elif t is StringLiteral:       return self._visit_string_literal(node)
        elif t is FStringLiteral:      return self._visit_fstring_literal(node)
        elif t is ArrayLiteral:        return self._visit_array_literal(node)
        elif t is Identifier:          return self._visit_identifier(node)
        elif t is BinaryOp:            return self._visit_binary_op(node)
        elif t is UnaryOp:             return self._visit_unary_op(node)
        elif t is FunctionCall:        return self._visit_function_call(node)
        elif t is MethodCall:          return self._visit_method_call(node)
        elif t is ArrayAccess:         return self._visit_array_access(node)
        elif t is macroCall:           return self._visit_macro_call(node)
        elif t is TypeFuncCall:        return self._visit_type_func_call(node)
        elif t is StructFieldAccess:   return self._visit_struct_field_access(node)
        elif t is StructInstance:      return self._visit_struct_instance(node)
        elif t is StructLiteral:       return self._visit_struct_literal(node)
        elif t is StructRecast:        return self._visit_struct_recast(node)
        elif t is MemberAccess:        return self._visit_member_access(node)
        elif t is Assignment:          self._visit_assignment(node); return False
        elif t is CompoundAssignment:  self._visit_compound_assign(node); return False
        elif t is AddressOf:           return self._visit_address_of(node)
        elif t is PointerDeref:        return self._visit_pointer_deref(node)
        elif t is SizeOf:              return self._visit_sizeof(node)
        elif t is AlignOf:             return self._visit_alignof(node)
        elif t is TypeOf:              return self._visit_typeof(node)
        elif t is EndianOf:            return self._visit_endianof(node)
        elif t is InExpression:        return self._visit_in_expression(node)
        elif t is HasExpression:       return self._visit_has_expression(node)
        elif t is CastExpression:      return self._visit_cast(node)
        elif t is TypeConvertExpression: return self._visit_cast(node)
        elif t is InlineAsm:           return self._visit_inline_asm(node)
        elif t is TernaryOp:           return self._visit_ternary_op(node)
        elif t is BitSlice:            return self._visit_bitslice(node)
        else:
            raise FVMCodegenError(
                f'fvmcodegen: unsupported expression in comptime: {type(node).__name__}',
                node
            )

    def _visit_literal(self, node: Literal):
        dt = node.type
        ttag = _datatype_to_ttag(dt)
        raw = node.value
        if ttag in (TTag.INT, TTag.UINT, TTag.LONG, TTag.ULONG, TTag.BYTE, TTag.CHAR):
            if isinstance(raw, int):
                data = raw
            elif isinstance(raw, str) and len(raw) == 1:
                data = ord(raw)
            else:
                data = int(raw)
        elif ttag in (TTag.FLOAT, TTag.DOUBLE):
            data = float(raw) if not isinstance(raw, float) else raw
        elif ttag == TTag.BOOL:
            data = int(bool(raw))
        else:
            data = raw
        self._emit(_instr(Op.PUSH, Val(ttag, data)))
        return True

    def _visit_string_literal(self, node: StringLiteral):
        self._emit(_instr(Op.PUSH, Val(TTag.BYTES, node.value.encode('utf-8'))))
        return True

    def _visit_fstring_literal(self, node: FStringLiteral) -> bool:
        """
        f-string: each part is either a plain str or an Expression.
        Strategy: push each part as a BYTES value (converting expressions via
        INT_TO_STR), then STR_CAT them pairwise into a single string.
        An empty f-string pushes an empty BYTES value.
        """
        parts = node.parts
        if not parts:
            self._emit(_instr(Op.PUSH, Val(TTag.BYTES, b'')))
            return True

        # Strip f" prefix from first string part and closing " from last string part
        # when parse_f_string was called from primary_expression without pre-stripping.
        if parts and isinstance(parts[0], str) and parts[0].startswith('f"'):
            parts = list(parts)
            parts[0] = parts[0][2:]  # strip f"
        if parts and isinstance(parts[-1], str) and parts[-1].endswith('"'):
            parts = list(parts)
            parts[-1] = parts[-1][:-1]  # strip closing "

        def _emit_part(part):
            if isinstance(part, str):
                self._emit(_instr(Op.PUSH, Val(TTag.BYTES, part.encode('utf-8'))))
            else:
                self._visit_expr(part)
                self._emit(_instr(Op.INT_TO_STR))

        _emit_part(parts[0])
        for part in parts[1:]:
            _emit_part(part)
            self._emit(_instr(Op.STR_CAT))
        return True

    def _visit_array_literal(self, node: ArrayLiteral):
        """
        String literals (ArrayLiteral with is_string=True) are pushed as
        Val(TTag.BYTES, bytes).  _read_vm_string() in fvm.py accepts BYTES
        directly, so compiler.io.console.print and friends work without
        needing heap allocation at codegen time.
        """
        if node.is_string and node.string_value is not None:
            raw = node.string_value.encode('utf-8')
            self._emit(_instr(Op.PUSH, Val(TTag.BYTES, raw)))
            return True
        # Non-string array literal: allocate on VM heap at runtime
        elem_type = 'int'
        if node.element_type is not None:
            from ftypesys import DataType as _DT
            _dt_to_name = {
                _DT.INT: 'int', _DT.UINT: 'uint',
                _DT.LONG: 'long', _DT.ULONG: 'ulong',
                _DT.FLOAT: 'float', _DT.DOUBLE: 'double',
                _DT.BOOL: 'bool', _DT.BYTE: 'byte', _DT.CHAR: 'char',
            }
            elem_type = _dt_to_name.get(node.element_type.base_type, 'int')
        count = len(node.elements)
        self._emit(_instr(Op.ARRAY_NEW, elem_type, count))
        arr_slot = self._alloc_local('__arr_tmp__')
        self._emit(_instr(Op.LOCAL_SET, arr_slot))
        for idx, elem in enumerate(node.elements):
            self._emit(_instr(Op.LOCAL_GET, arr_slot))
            self._emit(_instr(Op.PUSH, Val(TTag.INT, idx)))
            self._visit_expr(elem)
            self._emit(_instr(Op.ARRAY_STORE))
            self._emit(_instr(Op.LOCAL_SET, arr_slot))
        self._emit(_instr(Op.LOCAL_GET, arr_slot))
        return True

    def _visit_identifier(self, node: Identifier):
        name = node.name
        if name in self._outer_globals:
            self._emit(_instr(Op.GLOBAL_GET, name))
            return True
        if name in self._locals:
            self._emit(_instr(Op.LOCAL_GET, self._locals[name]))
            if name in self._heap_vars:
                ttag, byte_size = self._heap_vars[name]
                self._emit(_instr(Op.LOAD, ttag, byte_size))
            return True
        # Try active using-namespaces: standard::datetime -> standard__datetime__name
        for ns in reversed(self._using_namespaces):
            qualified = f'{ns}__{name}'
            if qualified in self._locals:
                self._emit(_instr(Op.LOCAL_GET, self._locals[qualified]))
                return True
        # Type name used as a value (e.g. union/struct type in tagged union assignment)
        if name in self._struct_layouts:
            self._emit(_instr(Op.PUSH, Val(TTag.BYTES, name.encode('utf-8'))))
            return True
        # Block-global variable defined in this comptime block (e.g. via namespace global)
        if name in self._block_globals:
            self._emit(_instr(Op.GLOBAL_GET, name))
            return True
        loc = f' [{node.source_line}:{node.source_col}]' if node.source_line else ''
        raise NameError(f'fvmcodegen: undefined comptime variable {name!r}{loc}')

    def _visit_binary_op(self, node: BinaryOp):
        op = node.operator
        # Short-circuit logical operators as branching sequences
        if op == Operator.AND:
            self._visit_expr(node.left)
            self._emit(_instr(Op.DUP))
            jnf_idx = self._emit(_instr(Op.JNF, 0))
            self._emit(_instr(Op.POP))
            self._visit_expr(node.right)
            self._patch_at(jnf_idx, Op.JNF, self._current_ip())
            return True
        if op == Operator.OR:
            self._visit_expr(node.left)
            self._emit(_instr(Op.DUP))
            jif_idx = self._emit(_instr(Op.JIF, 0))
            self._emit(_instr(Op.POP))
            self._visit_expr(node.right)
            self._patch_at(jif_idx, Op.JIF, self._current_ip())
            return True
        self._visit_expr(node.left)
        self._visit_expr(node.right)
        # Single-opcode operators
        _op_map = {
            Operator.ADD:            Op.ADD,
            Operator.SUB:            Op.SUB,
            Operator.MUL:            Op.MUL,
            Operator.DIV:            Op.DIV,
            Operator.MOD:            Op.MOD,
            Operator.POWER:          Op.POW,
            Operator.XOR:            Op.BXOR,
            Operator.BITAND:         Op.BAND,
            Operator.BITOR:          Op.BOR,
            Operator.BITXOR:         Op.BXOR,
            Operator.BITSHIFT_LEFT:  Op.SHL,
            Operator.BITSHIFT_RIGHT: Op.SHR,
            Operator.EQUAL:          Op.CMP_EQ,
            Operator.NOT_EQUAL:      Op.CMP_NE,
            Operator.LESS_THAN:      Op.CMP_LT,
            Operator.LESS_EQUAL:     Op.CMP_LE,
            Operator.GREATER_THAN:   Op.CMP_GT,
            Operator.GREATER_EQUAL:  Op.CMP_GE,
        }
        vm_op = _op_map.get(op)
        if vm_op is not None:
            self._emit(_instr(vm_op))
            return True
        # Composite operators: base op + BNOT
        _composite_map = {
            Operator.NAND:     Op.BAND,   # !(a & b)
            Operator.NOR:      Op.BOR,    # !(a | b)
            Operator.BITNAND:  Op.BAND,   # ~(a `& b)
            Operator.BITNOR:   Op.BOR,    # ~(a `| b)
            Operator.BITXNOT:  Op.BXOR,   # ~(a `^^ b)
            Operator.BITXNAND: Op.BAND,   # ~(xor(a,b) & ...)
            Operator.BITXNOR:  Op.BOR,    # ~(xor(a,b) | ...)
        }
        base_op = _composite_map.get(op)
        if base_op is not None:
            self._emit(_instr(base_op))
            self._emit(_instr(Op.BNOT))
            return True
        loc = f' [{node.source_line}:{node.source_col}]' if node.source_line else ''
        raise NotImplementedError(
            f'fvmcodegen: binary operator {op!r} not supported in comptime{loc}'
        )

    def _visit_unary_op(self, node: UnaryOp):
        op = node.operator
        if op in (Operator.INCREMENT, Operator.DECREMENT):
            if isinstance(node.operand, MemberAccess) and isinstance(node.operand.object, Identifier):
                # struct.field++ / struct.field-- on a simple identifier receiver
                var_name  = node.operand.object.name
                field     = node.operand.member
                is_global = (var_name in self._block_globals or
                             var_name in self._outer_globals)
                delta     = Val(TTag.INT, 1)
                arith     = Op.ADD if op == Operator.INCREMENT else Op.SUB
                def _emit_get():
                    if is_global:
                        self._emit(_instr(Op.GLOBAL_GET, var_name))
                    else:
                        slot = self._alloc_local(var_name)
                        self._emit(_instr(Op.LOCAL_GET, slot))
                def _emit_set():
                    if is_global:
                        self._emit(_instr(Op.GLOBAL_SET, var_name))
                    else:
                        slot = self._alloc_local(var_name)
                        self._emit(_instr(Op.LOCAL_SET, slot))
                if node.is_postfix:
                    # push old field value for expression result
                    _emit_get()
                    self._emit(_instr(Op.STRUCT_LOAD, field))
                # compute new field value
                _emit_get()
                self._emit(_instr(Op.STRUCT_LOAD, field))
                self._emit(_instr(Op.PUSH, delta))
                self._emit(_instr(arith))
                if not node.is_postfix:
                    self._emit(_instr(Op.DUP))
                # store new value back into the struct
                _emit_get()
                self._emit(_instr(Op.SWAP))  # stack: struct_val, new_field_val
                self._emit(_instr(Op.STRUCT_STORE, field))
                _emit_set()
                return True
            if not isinstance(node.operand, Identifier):
                loc = f' [{node.source_line}:{node.source_col}]' if node.source_line else ''
                raise NotImplementedError(
                    f'fvmcodegen: ++/-- only on simple identifiers in comptime{loc}'
                )
            name = node.operand.name
            if name in self._outer_globals:
                self._emit(_instr(Op.GLOBAL_GET, name))
                self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
                self._emit(_instr(Op.ADD if op == Operator.INCREMENT else Op.SUB))
                self._emit(_instr(Op.DUP))
                self._emit(_instr(Op.GLOBAL_SET, name))
                return True
            slot = self._alloc_local(name)
            if node.is_postfix:
                self._emit(_instr(Op.LOCAL_GET, slot))
                self._emit(_instr(Op.LOCAL_GET, slot))
                self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
                self._emit(_instr(Op.ADD if op == Operator.INCREMENT else Op.SUB))
                if name in self._block_globals:
                    self._emit(_instr(Op.DUP))
                self._emit(_instr(Op.LOCAL_SET, slot))
                if name in self._block_globals:
                    self._emit(_instr(Op.GLOBAL_SET, name))
            else:
                self._emit(_instr(Op.LOCAL_GET, slot))
                self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
                self._emit(_instr(Op.ADD if op == Operator.INCREMENT else Op.SUB))
                self._emit(_instr(Op.DUP))
                self._emit(_instr(Op.LOCAL_SET, slot))
                if name in self._block_globals:
                    self._emit(_instr(Op.GLOBAL_SET, name))
            return True
        self._visit_expr(node.operand)
        _op_map = {
            Operator.SUB:    Op.NEG,
            Operator.NOT:    Op.NOT,
            Operator.BITNOT: Op.BNOT,
            Operator.BITXNOT: Op.BNOT,
        }
        vm_op = _op_map.get(op)
        if vm_op is None:
            loc = f' [{node.source_line}:{node.source_col}]' if node.source_line else ''
            raise NotImplementedError(
                f'fvmcodegen: unary operator {op!r} not supported in comptime{loc}'
            )
        self._emit(_instr(vm_op))
        return True

    def _visit_type_func_call(self, node: TypeFuncCall) -> bool:
        """
        Emit a call to a comptime type function.
        Push receiver first (becomes '_' / slot 0), then explicit args, then CALL.
        """
        self._visit_expr(node.receiver)
        for arg in node.arguments:
            self._visit_expr(arg)
        mangled = TypeFuncDef.mangle(node.type_name, node.func_name)
        self._emit(_instr(Op.CALL, mangled, 1 + len(node.arguments)))
        return True

    def _visit_sizeof(self, node: SizeOf) -> bool:
        """
        sizeof(T) returns the bit width of T as a ulong.
        Supports TypeSystem targets and Identifier targets (type aliases, locals).
        """
        from ftypesys import TypeSystem as _TS, DataType as _DT
        _prim_bits = {
            _DT.SINT:  32, _DT.UINT:  32,
            _DT.SLONG: 64, _DT.ULONG: 64,
            _DT.FLOAT: 32, _DT.DOUBLE: 64,
            _DT.BOOL:  1,  _DT.BYTE:  8,
            _DT.CHAR:  8,  _DT.DATA:  0,
        }
        bits = None
        target = node.target

        if isinstance(target, _TS):
            if target.base_type == _DT.DATA and target.bit_width:
                bits = target.bit_width
            elif target.is_pointer:
                bits = 64
            elif target.base_type in _prim_bits:
                bits = _prim_bits[target.base_type]

        elif isinstance(target, Identifier):
            # Check heap vars first — they carry full type info
            if target.name in self._heap_vars:
                heap_info = self._heap_vars[target.name]
                if len(heap_info) == 3:  # array: (elem_ttag, elem_bytes, count)
                    elem_ttag, elem_bytes, count = heap_info
                    bits = elem_bytes * 8 * count
                else:  # scalar: (ttag, byte_size)
                    bits = heap_info[1] * 8
            # Check full typespec (has array dims etc.)
            if bits is None and target.name in self._local_typespecs:
                bits = self._type_bit_width(self._local_typespecs[target.name])
            if bits is None:
                type_name = self._local_types.get(target.name)
                if type_name is not None:
                    if type_name.startswith('__data_'):
                        bits = int(type_name[7:])
                    else:
                        _name_bits = {
                            'int': 32, 'uint': 32, 'long': 64, 'ulong': 64,
                            'float': 32, 'double': 64, 'bool': 1,
                            'byte': 8, 'char': 8,
                        }
                        bits = _name_bits.get(type_name)
            # Check struct layouts
            if bits is None:
                layout = self._struct_layouts.get(target.name)
                if layout is not None:
                    bits = layout.total_bits if layout.total_bits else layout.total_size * 8

        if bits is None:
            bits = 0  # unknown — emit 0 rather than crash

        self._emit(_instr(Op.PUSH, Val(TTag.ULONG, bits)))
        return True

    def _visit_alignof(self, node: AlignOf) -> bool:
        """
        alignof(T) returns the alignment of T in bytes as a uint.
        Mirrors AlignOfTypeHandler.alignof_bytes_for_target from fcodegen.py.
        For data{N} types: alignment = (N + 7) // 8 bytes.
        For primitives: alignment = byte size.
        For pointers: 8 bytes.
        For structs: max field byte size (matching _op_alignof in fvm.py).
        """
        from ftypesys import TypeSystem as _TS, DataType as _DT
        _prim_align = {
            _DT.SINT:  4, _DT.UINT:  4,
            _DT.SLONG: 8, _DT.ULONG: 8,
            _DT.FLOAT: 4, _DT.DOUBLE: 8,
            _DT.BOOL:  1, _DT.BYTE:  1,
            _DT.CHAR:  1,
        }
        align = None
        target = node.target

        if isinstance(target, _TS):
            if target.alignment is not None:
                align = target.alignment
            elif target.base_type == _DT.DATA and target.bit_width is not None:
                align = (target.bit_width + 7) // 8
            elif target.is_pointer:
                align = 8
            elif target.base_type in _prim_align:
                align = _prim_align[target.base_type]

        elif isinstance(target, Identifier):
            # Check heap vars: use byte size as alignment proxy (mirrors _op_alignof)
            if target.name in self._heap_vars:
                heap_info = self._heap_vars[target.name]
                if len(heap_info) == 3:  # array: (elem_ttag, elem_bytes, count)
                    _, elem_bytes, _ = heap_info
                    align = elem_bytes
                else:  # scalar: (ttag, byte_size)
                    align = heap_info[1]
            # Check full typespec
            if align is None and target.name in self._local_typespecs:
                ts = self._local_typespecs[target.name]
                if ts.alignment is not None:
                    align = ts.alignment
                elif ts.base_type == _DT.DATA and ts.bit_width is not None:
                    align = (ts.bit_width + 7) // 8
                elif ts.is_pointer:
                    align = 8
                elif ts.base_type in _prim_align:
                    align = _prim_align[ts.base_type]
            # Check primitive type name string
            if align is None:
                type_name = self._local_types.get(target.name)
                if type_name is not None:
                    if type_name.startswith('__data_'):
                        bits = int(type_name[7:])
                        align = (bits + 7) // 8
                    else:
                        _name_align = {
                            'int': 4, 'uint': 4, 'long': 8, 'ulong': 8,
                            'float': 4, 'double': 8, 'bool': 1,
                            'byte': 1, 'char': 1,
                        }
                        align = _name_align.get(type_name)
            # Check struct layouts: max field byte size (mirrors _op_alignof)
            if align is None:
                layout = self._struct_layouts.get(target.name)
                if layout is not None:
                    align = max((f[3] for f in layout.fields), default=1)

        if align is None:
            align = 1  # unknown -- emit 1 rather than crash

        self._emit(_instr(Op.PUSH, Val(TTag.UINT, align)))
        return True

    def _visit_endianof(self, node: EndianOf) -> bool:
        """
        endianof(T) returns the endianness of T as an int: 0 = little, 1 = big.
        Mirrors visit_EndianOf in fcodegen.py (ir.Constant IntType(32)).
        TypeSystem.endianness: 0 = little, 1 = big (default 1).
        Identifier targets: checks local typespecs, then le/be name prefix (mirrors _op_endianof).
        """
        from ftypesys import TypeSystem as _TS, DataType as _DT
        endian = None
        target = node.target

        if isinstance(target, _TS):
            # Explicit endianness on TypeSystem (0=little, 1=big, default 1)
            endian = getattr(target, 'endianness', 1)

        elif isinstance(target, Identifier):
            # Check full typespec for declared endianness
            ts = self._local_typespecs.get(target.name)
            if ts is not None:
                endian = getattr(ts, 'endianness', 1)
            # Fall back to le/be name prefix convention (mirrors _op_endianof)
            if endian is None:
                type_name = self._local_types.get(target.name, '')
                if type_name.startswith('be'):
                    endian = 1
                elif type_name.startswith('le'):
                    endian = 0

        if endian is None:
            endian = 0  # Flux default: little-endian

        self._emit(_instr(Op.PUSH, Val(TTag.INT, endian)))
        return True

    def _visit_typeof(self, node: TypeOf) -> bool:
        """
        typeof(expr) returns an integer kind constant matching the TypeOf.KIND_* values.
        Pointer kinds are encoded as depth * 100 + pointee_base_kind.
        e.g. byte* = 107, int* = 101, int** = 201.
        """
        from ftypesys import DataType as _DT, TypeSystem as _TS
        # KIND constants mirror fast.TypeOf
        _KIND = {
            'int':    1,  'uint':   2,  'float':  3,  'double': 4,
            'bool':   5,  'char':   6,  'byte':   7,
            'long':   8,  'ulong':  9,
        }
        _DT_KIND = {
            _DT.SINT:   1, _DT.UINT:   2, _DT.FLOAT:  3, _DT.DOUBLE: 4,
            _DT.BOOL:   5, _DT.CHAR:   6, _DT.BYTE:   7,
            _DT.SLONG:  8, _DT.ULONG:  9,
            _DT.STRUCT: 12, _DT.OBJECT: 13, _DT.VOID: 14,
        }
        kind = 0  # KIND_UNKNOWN
        expr = node.expression

        if isinstance(expr, _TS):
            if expr.is_pointer:
                depth = getattr(expr, 'pointer_depth', 1) or 1
                base_kind = _DT_KIND.get(expr.base_type, 0)
                kind = depth * 100 + base_kind
            else:
                kind = _DT_KIND.get(expr.base_type, 0)
        elif isinstance(expr, Identifier):
            name = expr.name
            # Bare type keyword used as typeof argument (e.g. typeof(bool))
            if name in _KIND:
                kind = _KIND[name]
            # Known struct type
            elif name in self._struct_layouts:
                kind = 12  # KIND_STRUCT
            # Variable whose type was recorded
            else:
                ts = self._local_typespecs.get(name)
                if ts is not None and isinstance(ts, _TS):
                    if ts.is_pointer:
                        depth = getattr(ts, 'pointer_depth', 1) or 1
                        base_kind = _DT_KIND.get(ts.base_type, 0)
                        kind = depth * 100 + base_kind
                    else:
                        kind = _DT_KIND.get(ts.base_type, 0)
                else:
                    type_name = self._local_types.get(name)
                    if type_name is not None:
                        kind = _KIND.get(type_name, 0)
                        if kind == 0 and type_name in self._struct_layouts:
                            kind = 12  # KIND_STRUCT

        self._emit(_instr(Op.PUSH, Val(TTag.INT, kind)))
        return True

    def _visit_in_expression(self, node: InExpression) -> bool:
        """
        needle in haystack — linear scan of the array for needle.
        Strategy: evaluate needle and haystack once, then emit a counted
        loop that INDEX_GETs each element, CMP_EQs with needle, and BORs
        the result into an accumulator.  Leaves a BOOL on the stack.

        Since we don't know the array length at codegen time, we use the
        VM's ARRAY_LEN op if available, otherwise we emit a runtime loop
        using the meta count stored in the PTR.  For simplicity we use a
        pure bytecode loop with a runtime length read.
        """
        # Evaluate needle into a temp slot
        self._visit_expr(node.needle)
        needle_slot = self._alloc_local('__in_needle__')
        self._emit(_instr(Op.LOCAL_SET, needle_slot))

        # Evaluate haystack (array PTR) into a temp slot
        self._visit_expr(node.haystack)
        arr_slot = self._alloc_local('__in_arr__')
        self._emit(_instr(Op.LOCAL_SET, arr_slot))

        # Get array length via STR_LEN workaround — use ARRAY_LEN if it exists,
        # otherwise push the count from meta via a dedicated op.
        # Since the VM doesn't have ARRAY_LEN, we use a Python-level count stored
        # as an inline literal by pushing the array PTR and reading meta at runtime.
        # We emit a loop with a runtime index counter using JMP/JNF.

        # result accumulator = false
        result_slot = self._alloc_local('__in_result__')
        self._emit(_instr(Op.PUSH, Val(TTag.BOOL, 0)))
        self._emit(_instr(Op.LOCAL_SET, result_slot))

        # index counter = 0
        idx_slot = self._alloc_local('__in_idx__')
        self._emit(_instr(Op.PUSH, Val(TTag.INT, 0)))
        self._emit(_instr(Op.LOCAL_SET, idx_slot))

        # Get array length: push arr PTR, emit ARRAY_LEN op
        len_slot = self._alloc_local('__in_len__')
        self._emit(_instr(Op.LOCAL_GET, arr_slot))
        self._emit(_instr(Op.ARRAY_LEN))
        self._emit(_instr(Op.LOCAL_SET, len_slot))

        # Loop start: if idx >= len, jump out
        loop_start = self._current_ip()
        self._emit(_instr(Op.LOCAL_GET, idx_slot))
        self._emit(_instr(Op.LOCAL_GET, len_slot))
        self._emit(_instr(Op.CMP_GE))
        exit_patch = self._emit(_instr(Op.JIF, 0))

        # elem = arr[idx]
        self._emit(_instr(Op.LOCAL_GET, arr_slot))
        self._emit(_instr(Op.LOCAL_GET, idx_slot))
        self._emit(_instr(Op.ARRAY_LOAD))

        # result |= (elem == needle)
        self._emit(_instr(Op.LOCAL_GET, needle_slot))
        self._emit(_instr(Op.CMP_EQ))
        self._emit(_instr(Op.LOCAL_GET, result_slot))
        self._emit(_instr(Op.BOR))
        self._emit(_instr(Op.LOCAL_SET, result_slot))

        # idx += 1
        self._emit(_instr(Op.LOCAL_GET, idx_slot))
        self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
        self._emit(_instr(Op.ADD))
        self._emit(_instr(Op.LOCAL_SET, idx_slot))

        # jump back to loop start
        self._emit(_instr(Op.JMP, loop_start))

        # patch exit
        self._patch_at(exit_patch, Op.JIF, self._current_ip())

        self._emit(_instr(Op.LOCAL_GET, result_slot))
        # For '!in' / 'not in', negate the result
        if getattr(node, 'negated', False):
            self._emit(_instr(Op.NOT))
        return True

    def _visit_has_expression(self, node: HasExpression) -> bool:
        """
        'expr has TraitName' -- trait membership check.

        Resolves entirely at compile time: the static type of 'subject' is
        looked up in _object_traits, its traits list is checked against
        'trait_name', and a BOOL constant (1 or 0) is pushed onto the stack.

        Mirrors fcodegen.py's visit_HasExpression exactly.
        """
        # -- Resolve the static type name of the subject ----------------------
        obj_type_name = None

        if isinstance(node.subject, Identifier):
            # Check if the identifier is a local variable with a known type
            obj_type_name = self._local_types.get(node.subject.name)
            # If not a variable, check if the identifier is itself an object
            # type name (e.g. 'Bar has Fooable' where Bar is the type directly).
            if obj_type_name is None:
                if node.subject.name in self._object_traits:
                    obj_type_name = node.subject.name

        if obj_type_name is None:
            raise FVMCodegenError(
                f"'has': cannot determine static type of subject "
                f"'{node.subject}' -- only object instances or object type "
                f"names are supported [{node.source_line}:{node.source_col}]",
                node)

        # -- Verify the trait name is known -----------------------------------
        if node.trait_name not in self._trait_registry:
            raise FVMCodegenError(
                f"'has': '{node.trait_name}' is not a defined trait "
                f"[{node.source_line}:{node.source_col}]",
                node)

        # -- Verify the subject type is an object type ------------------------
        if obj_type_name not in self._object_traits:
            raise FVMCodegenError(
                f"'has': type '{obj_type_name}' is not an object type -- "
                f"'has' requires an object instance or object type name "
                f"[{node.source_line}:{node.source_col}]",
                node)

        # -- Push constant BOOL result ----------------------------------------
        result = int(node.trait_name in self._object_traits[obj_type_name])
        self._emit(_instr(Op.PUSH, Val(TTag.BOOL, result)))
        return True

    def _visit_pointer_deref(self, node: PointerDeref) -> bool:
        """
        *ptr -- dereference a VM stack pointer.
        PTR(slot) -> locals[slot] for regular pointers.
        For function pointers, *pb returns the slot index itself (the address of the function).
        """
        from fast import Identifier as _Id
        if (isinstance(node.pointer, _Id) and
                self._local_types.get(node.pointer.name) == '__funcptr__'):
            # *pb on a funcptr: pb holds PTR(slot); return slot index as ULONG
            slot = self._locals[node.pointer.name]
            self._emit(_instr(Op.LOCAL_GET, slot))
            self._emit(_instr(Op.CAST, TTag.ULONG))
            return True
        self._visit_expr(node.pointer)
        self._emit(_instr(Op.LOCAL_DEREF))
        return True

    def _visit_address_of(self, node: AddressOf) -> bool:
        """
        @x — push Val(TTag.PTR, slot_index).
        For variables: slot holds the variable value.
        For functions: allocate a slot holding Val(BYTES, func_name), push PTR to it.
        @arr[idx] — evaluate arr[idx], store result in a temp slot, push PTR to that slot.
        """
        if isinstance(node.expression, ArrayAccess):
            # Evaluate the subscript expression to get the element value, then
            # store it in a fresh temp slot and return a PTR to that slot.
            # This supports patterns like @days[dow][0] -> byte* used as ds[i].
            tmp_name = self._fresh_tmp()
            tmp_slot = self._alloc_local(tmp_name)
            self._visit_expr(node.expression)      # push element value
            self._emit(_instr(Op.LOCAL_SET, tmp_slot))  # store into temp slot
            self._emit(_instr(Op.PUSH, Val(TTag.PTR, tmp_slot)))
            return True
        if not isinstance(node.expression, Identifier):
            raise FVMCodegenError(
                'fvmcodegen: address-of only supported on simple identifiers in comptime',
                node
            )
        name = node.expression.name
        # Variable address
        if name in self._locals:
            slot = self._locals[name]
            # In fcodegen, @x on a pointer/noopstr local loads the pointer value
            # (equivalent to loading from the alloca).  In the VM, that means the
            # local already holds the BYTES/PTR value -- emit LOCAL_GET so that
            # INLINE_ASM receives the actual data rather than a slot-index PTR.
            ts = self._local_typespecs.get(name)
            _is_ptr_type = (
                (ts is not None and (getattr(ts, 'is_pointer', False) or
                                     getattr(ts, 'pointer_depth', 0)))
                or self._local_types.get(name) in ('noopstr', 'byte', 'char')
            )
            if _is_ptr_type:
                # import sys as _sys; _sys.stderr.write(f'[DEBUG ADDROF] {name!r} -> LOCAL_GET {slot} (_local_types={self._local_types.get(name)!r} ts={ts})\n'); _sys.stderr.flush()
                self._emit(_instr(Op.LOCAL_GET, slot))
                return True
            self._emit(_instr(Op.PUSH, Val(TTag.PTR, slot)))
            return True
        # Function address: allocate a slot for the function name value
        fn_slot_name = f'__fnaddr_{name}__'
        slot = self._alloc_local(fn_slot_name)
        # Store the function name as BYTES in that slot
        self._emit(_instr(Op.PUSH, Val(TTag.BYTES, name.encode('utf-8'))))
        self._emit(_instr(Op.LOCAL_SET, slot))
        # Push PTR to that slot
        self._emit(_instr(Op.PUSH, Val(TTag.PTR, slot)))
        return True

    def _visit_ternary_op(self, node) -> bool:
        """
        Compile a ternary expression: cond ? true_expr : false_expr
        Emits: eval cond, JNF to false branch, eval true_expr, JMP to merge,
               false branch: eval false_expr, merge.
        """
        self._visit_expr(node.condition)
        jnf_patch = self._emit(_instr(Op.JNF, 0))
        self._visit_expr(node.true_expr)
        jmp_patch = self._emit(_instr(Op.JMP, 0))
        self._patch_at(jnf_patch, Op.JNF, self._current_ip())
        self._visit_expr(node.false_expr)
        self._patch_at(jmp_patch, Op.JMP, self._current_ip())
        return True

    def _visit_inline_asm(self, node: InlineAsm) -> bool:
        """
        Emit an INLINE_ASM instruction for an inline asm block.
        Parses constraints to determine input/output operands and pushes
        input values onto the stack before the instruction.
        """
        import re as _re

        constraints = node.constraints or ''

        # Split constraints into outputs:inputs:clobbers
        parts = constraints.split(':')
        outputs_str = parts[0].strip() if len(parts) > 0 else ''
        inputs_str  = parts[1].strip() if len(parts) > 1 else ''

        # Parse output operands: "=r"(varname)
        output_names = []
        if outputs_str:
            for m in _re.finditer(r'"=r"\((\w+)\)', outputs_str):
                output_names.append(m.group(1))

        # Parse input operands: "r"(varname)
        input_names = []
        if inputs_str:
            for m in _re.finditer(r'"r"\((\w+)\)', inputs_str):
                input_names.append(m.group(1))

        n_outputs = len(output_names)
        n_inputs  = len(input_names)

        # Push input values onto the stack
        for name in input_names:
            if name in self._locals:
                self._emit(_instr(Op.LOCAL_GET, self._locals[name]))
            elif name in self._outer_globals or name in self._block_globals:
                self._emit(_instr(Op.GLOBAL_GET, name))
            else:
                self._emit(_instr(Op.PUSH, Val(TTag.LONG, 0)))

        self._emit(_instr(Op.INLINE_ASM, node.body, constraints, n_inputs, n_outputs, output_names))

        # If there are outputs, the op pushes a value
        return n_outputs > 0

    def _visit_cast(self, node) -> bool:
        """
        Type cast / type conversion expression: ulong(x), int(y), float(z), etc.
        Evaluates the inner expression then emits a CAST opcode to coerce the
        top-of-stack value to the target TTag.
        """
        self._visit_expr(node.expression)
        from ftypesys import DataType as _DT
        _dt_to_ttag = {
            _DT.SINT:   TTag.INT,
            _DT.UINT:   TTag.UINT,
            _DT.SLONG:  TTag.LONG,
            _DT.ULONG:  TTag.ULONG,
            _DT.FLOAT:  TTag.FLOAT,
            _DT.DOUBLE: TTag.DOUBLE,
            _DT.BOOL:   TTag.BOOL,
            _DT.BYTE:   TTag.BYTE,
            _DT.CHAR:   TTag.CHAR,
        }
        ts = node.target_type
        if getattr(ts, 'is_pointer', False) or getattr(ts, 'pointer_depth', 0):
            # Any pointer type (byte*, int*, Slab*, etc.) is represented as
            # TTag.PTR regardless of the pointee's base type. Checking this
            # before the scalar base-type map prevents e.g. `(byte*)raw`
            # from being tagged as TTag.BYTE (the pointee type) instead of
            # a pointer, which breaks ARRAY_STORE/ARRAY_LOAD on the result.
            target_ttag = TTag.PTR
        elif ts.base_type is not None and ts.base_type in _dt_to_ttag:
            target_ttag = _dt_to_ttag[ts.base_type]
        elif (ts.base_type is not None and ts.base_type == _DT.DATA
                and not getattr(ts, 'is_pointer', False)):
            # data{N} types (and aliases such as i16/u16/wchar) are scalar
            # integers of N bits — map to the closest integer TTag based on
            # bit width and signedness rather than falling through to PTR.
            bits = getattr(ts, 'bit_width', None) or 32
            is_signed = getattr(ts, 'is_signed', False)
            if bits <= 32:
                target_ttag = TTag.INT if is_signed else TTag.UINT
            else:
                target_ttag = TTag.LONG if is_signed else TTag.ULONG
        else:
            # Pointer cast or unknown — treat as PTR
            target_ttag = TTag.PTR
        # For pointer-to-struct casts (e.g. (Slab*)raw), tag the resulting
        # PTR value with the struct type so STRUCT_LOAD/STRUCT_STORE on the
        # pointer can read/write the pointee in heap/OS memory.
        if (target_ttag == TTag.PTR and getattr(ts, 'pointer_depth', 0)
                and getattr(ts, 'pointer_depth', 0) >= 1
                and getattr(ts, 'custom_typename', None)
                and ts.custom_typename in self._struct_layouts):
            self._emit(_instr(Op.CAST, target_ttag, ts.custom_typename))
        else:
            self._emit(_instr(Op.CAST, target_ttag))
        return True

    def _flatten_dotted_name(self, node) -> Optional[str]:
        """
        Flatten a chain of MethodCall / MemberAccess / Identifier nodes into a
        dot-separated name string, e.g. 'compiler.io.console.print'.
        Returns None if the chain contains non-name nodes.
        """
        if isinstance(node, Identifier):
            return node.name
        if isinstance(node, MemberAccess):
            base = self._flatten_dotted_name(node.object)
            return f'{base}.{node.member}' if base is not None else None
        if isinstance(node, MethodCall):
            base = self._flatten_dotted_name(node.object)
            return f'{base}.{node.method_name}' if base is not None else None
        return None

    def _visit_function_call(self, node: FunctionCall):
        _COMPILER_IO = {
            'compiler__io__console__print':  Op.COMPILER_PRINT,
            'compiler.io.console.print':     Op.COMPILER_PRINT,
            'compiler__io__console__input':  Op.COMPILER_INPUT,
            'compiler.io.console.input':     Op.COMPILER_INPUT,
            'compiler__io__readfile':        Op.COMPILER_READFILE,
            'compiler.io.readfile':          Op.COMPILER_READFILE,
            'compiler__io__writefile':       Op.COMPILER_WRITEFILE,
            'compiler.io.writefile':         Op.COMPILER_WRITEFILE,
            'compiler.fvm.dump':             Op.COMPILER_FVM_DUMP,
            'compiler__fvm__dump':           Op.COMPILER_FVM_DUMP,
            'compiler.fvm.loadlib':          Op.COMPILER_LOADLIB,
            'compiler__fvm__loadlib':        Op.COMPILER_LOADLIB,
            'compiler.fvm.trace.begin':      Op.COMPILER_FVM_TRACE_BEGIN,
            'compiler__fvm__trace__begin':   Op.COMPILER_FVM_TRACE_BEGIN,
            'compiler.fvm.trace.end':        Op.COMPILER_FVM_TRACE_END,
            'compiler__fvm__trace__end':     Op.COMPILER_FVM_TRACE_END,
            'compiler.fvm.setbp':            Op.COMPILER_FVM_SETBP,
            'compiler__fvm__setbp':          Op.COMPILER_FVM_SETBP,
            'compiler.import.stdlib':        Op.COMPILER_IMPORT_STDLIB,
            'compiler__import__stdlib':      Op.COMPILER_IMPORT_STDLIB,
            'compiler.import.local':         Op.COMPILER_IMPORT_LOCAL,
            'compiler__import__local':       Op.COMPILER_IMPORT_LOCAL,
            'compiler.fpm.package':          Op.COMPILER_FPM_PACKAGE,
            'compiler__fpm__package':        Op.COMPILER_FPM_PACKAGE,
        }
        # Opcodes that push a return value onto the stack
        _PUSHES = {Op.COMPILER_INPUT, Op.COMPILER_READFILE}
        name = node.name
        opcode = _COMPILER_IO.get(name)
        if opcode is not None:
            if opcode != Op.COMPILER_INPUT:
                for arg in node.arguments:
                    self._visit_expr(arg)
            self._emit(_instr(opcode))
            return opcode in _PUSHES
        # Function pointer call: pb() where pb is a local __funcptr__ slot
        if (name in self._locals and
                self._local_types.get(name) == '__funcptr__'):
            for arg in node.arguments:
                self._visit_expr(arg)
            # pb holds PTR(fn_slot); fn_slot holds BYTES(func_name)
            # LOCAL_GET pb -> PTR(fn_slot); LOCAL_DEREF -> BYTES(func_name)
            self._emit(_instr(Op.LOCAL_GET, self._locals[name]))
            self._emit(_instr(Op.LOCAL_DEREF))
            self._emit(_instr(Op.CALL_PTR, len(node.arguments)))
            return True
        # Try active using-namespaces for unqualified function names.
        # If known at codegen time, use the qualified name directly.
        # Otherwise keep the bare name -- the VM suffix-match (__name)
        # will find it at runtime after imports have registered functions.
        resolved_name = name
        for ns in reversed(self._using_namespaces):
            qualified = f'{ns}__{name}'
            if (qualified in self.compiled_functions or
                    qualified in self._known_functions):
                resolved_name = qualified
                break
        for arg in node.arguments:
            if isinstance(arg, Identifier) and arg.name in self._local_vars:
                raise FVMCodegenError(
                    f"fvmcodegen: local variable '{arg.name}' cannot escape scope (passed to function)",
                    arg)
            self._visit_expr(arg)
        if self._tail_call_self is not None and resolved_name == self._tail_call_self:
            self._emit(_instr(Op.TAIL_SELF, len(node.arguments)))
        else:
            self._emit(_instr(Op.CALL, resolved_name, len(node.arguments)))
        return True  # CALL/TAIL_SELF always pushes or loops

    def _visit_method_call(self, node: MethodCall):
        """
        Handle chained namespace/method calls inside comptime blocks.
        Flattens the receiver chain into a dotted name and maps compiler.io.*
        to dedicated VM opcodes; falls back to a generic CALL for others.
        """
        _COMPILER_IO_OPCODES = {
            'compiler.io.console.print':  Op.COMPILER_PRINT,
            'compiler.io.console.input':  Op.COMPILER_INPUT,
            'compiler.io.readfile':       Op.COMPILER_READFILE,
            'compiler.io.writefile':      Op.COMPILER_WRITEFILE,
            'compiler.fvm.dump':          Op.COMPILER_FVM_DUMP,
            'compiler.import.stdlib':     Op.COMPILER_IMPORT_STDLIB,
            'compiler.import.local':      Op.COMPILER_IMPORT_LOCAL,
            'compiler.fpm.package':       Op.COMPILER_FPM_PACKAGE,
            'compiler.fvm.loadlib':        Op.COMPILER_LOADLIB,
            'compiler.fvm.trace.begin':     Op.COMPILER_FVM_TRACE_BEGIN,
            'compiler.fvm.trace.end':       Op.COMPILER_FVM_TRACE_END,
            'compiler.fvm.setbp':           Op.COMPILER_FVM_SETBP,
        }
        _PUSHES = {Op.COMPILER_INPUT, Op.COMPILER_READFILE}

        full_name = self._flatten_dotted_name(node)

        if full_name in _COMPILER_IO_OPCODES:
            opcode = _COMPILER_IO_OPCODES[full_name]
            if opcode != Op.COMPILER_INPUT:
                for arg in node.arguments:
                    self._visit_expr(arg)
            self._emit(_instr(opcode))
            return opcode in _PUSHES

        if full_name is not None:
            # Check if this is an object method call: receiver_var.method_name(args)
            # where receiver_var is a local of a known object type registered via
            # _visit_object_def. Mirrors fcodegen.py's visit_MethodCall which builds
            # method_func_name = f"{obj_type_name}.{node.method_name}" and passes
            # this_ptr as args[0].
            if (isinstance(node.object, Identifier) and
                    node.object.name in self._local_types):
                type_name = self._local_types[node.object.name]
                obj_method_key = f"{type_name}.{node.method_name}"
                _is_object_type = (type_name in self._struct_layouts or
                                   type_name in getattr(self, '_object_type_names', set()))
                if (_is_object_type or
                        obj_method_key in self.compiled_functions or
                        obj_method_key in self._known_functions):
                    recv_name = node.object.name
                    # Interface enforcement. RETURN_TO is checked first because a method
                    # permitted by a RETURN_TO block (A -> B { method }) must not be
                    # blocked by a CALL_ON block (B : A { other }) that does not list it.
                    caller_type = getattr(self, '_current_object_name', None)
                    if caller_type is not None:
                        # RETURN_TO check: (provider=type_name, consumer=caller_type)
                        _returnto = getattr(self, '_returnto_whitelist', {})
                        _rkey = (type_name, caller_type)
                        _returnto_governed = _rkey in _returnto
                        _returnto_allowed  = _returnto_governed and node.method_name in _returnto[_rkey]
                        if _returnto_governed and not _returnto_allowed:
                            raise FVMCodegenError(
                                f"Interface violation: {type_name}.{node.method_name} is not "
                                f"permitted to be called from inside {caller_type}",
                                node
                            )
                        # CALL_ON check: skip when RETURN_TO already allowed this call.
                        if not _returnto_allowed:
                            _key = (caller_type, type_name)
                            _whitelist = getattr(self, '_interface_whitelist', {})
                            if _key in _whitelist and node.method_name not in _whitelist[_key]:
                                raise FVMCodegenError(
                                    f"Interface violation: {caller_type} is not permitted to "
                                    f"call {node.method_name} from {type_name}",
                                    node
                                )
                    # PASS_INTO enforcement: B(A) means A method return values may only be
                    # passed as arguments into B. Check each argument that is itself a method
                    # call on a known object type against _passinto_whitelist[(A, B)].
                    _passinto = getattr(self, '_passinto_whitelist', {})
                    for _arg in node.arguments:
                        if (isinstance(_arg, MethodCall) and
                                isinstance(_arg.object, Identifier) and
                                _arg.object.name in self._local_types):
                            _inner_type = self._local_types[_arg.object.name]
                            _pkey = (_inner_type, type_name)
                            if _pkey in _passinto and _arg.method_name not in _passinto[_pkey]:
                                raise FVMCodegenError(
                                    f"Interface violation: return value of "
                                    f"{_inner_type}.{_arg.method_name} is not permitted "
                                    f"to be passed as an argument into {type_name}",
                                    node
                                )
                    # Push 'this' (the struct value) then explicit args
                    self._visit_expr(node.object)
                    for arg in node.arguments:
                        self._visit_expr(arg)
                    self._emit(_instr(Op.CALL, obj_method_key, 1 + len(node.arguments)))
                    # All object methods return the (possibly mutated) this.
                    # Write it back into the receiver variable so mutations
                    # are visible to the caller -- structs are by value in
                    # the VM; this mirrors fcodegen's pointer-based mutation.
                    # Stack after CALL: [this_mutated]
                    # DUP x2 so we have three copies: LOCAL_SET and GLOBAL_SET
                    # consume two, one remains as the pushed return value for
                    # _visit_expr_stmt to POP.
                    recv_slot = self._alloc_local(recv_name)
                    self._emit(_instr(Op.DUP))          # [this, this]
                    self._emit(_instr(Op.DUP))          # [this, this, this]
                    self._emit(_instr(Op.LOCAL_SET, recv_slot))  # [this, this]
                    self._emit(_instr(Op.GLOBAL_SET, recv_name)) # [this]
                    return True

            # Check if this is a type function call: receiver_var.method_name(args)
            # The receiver is a local variable; look up its declared type name and
            # try the __typefunc__<type_name>__<method_name> mangled key.
            if (isinstance(node.object, Identifier) and
                    node.object.name in self._local_types):
                type_name = self._local_types[node.object.name]
                from fast import TypeFuncDef as _TFD
                mangled = _TFD.mangle(type_name, node.method_name)
                if mangled in self.compiled_functions or mangled in self._known_functions:
                    # Push receiver as first arg (_), then explicit args
                    self._visit_expr(node.object)
                    for arg in node.arguments:
                        self._visit_expr(arg)
                    self._emit(_instr(Op.CALL, mangled, 1 + len(node.arguments)))
                    return True

            for arg in node.arguments:
                self._visit_expr(arg)
            self._emit(_instr(Op.CALL, full_name, len(node.arguments)))
            return True

        loc = f' [{node.source_line}:{node.source_col}]' if node.source_line else ''
        raise NotImplementedError(
            f'fvmcodegen: method call on complex receiver not supported in comptime: {node!r}{loc}'
        )

    def _visit_macro_call(self, node) -> bool:
        """
        Expand an expression macro call inline, mirroring CodegenVisitor.visit_macroCall.
        Looks up the macroDef, substitutes arguments, and visits the expanded body.
        """
        import copy
        macro_def = self._macro_table.get(node.name)
        if macro_def is None:
            raise FVMCodegenError(
                f"fvmcodegen: unknown expression macro '{node.name}'", node)
        if len(node.arguments) != len(macro_def.params):
            raise FVMCodegenError(
                f"fvmcodegen: macro '{node.name}' expects {len(macro_def.params)} "
                f"argument(s), got {len(node.arguments)}", node)
        subst = {param: copy.deepcopy(arg)
                 for param, arg in zip(macro_def.params, node.arguments)}
        body_copy = copy.deepcopy(macro_def.body)
        expanded = self._macro_substitute(body_copy, subst)
        return self._visit_expr(expanded)

    @staticmethod
    def _macro_substitute(node, subst: dict):
        """Recursively substitute macro parameters in an AST subtree."""
        import copy
        if isinstance(node, Identifier):
            if node.name in subst:
                return copy.deepcopy(subst[node.name])
            return node
        if isinstance(node, BinaryOp):
            node.left  = FVMCodegen._macro_substitute(node.left,  subst)
            node.right = FVMCodegen._macro_substitute(node.right, subst)
            return node
        if isinstance(node, UnaryOp):
            node.operand = FVMCodegen._macro_substitute(node.operand, subst)
            return node
        if isinstance(node, macroCall):
            node.arguments = [FVMCodegen._macro_substitute(a, subst) for a in node.arguments]
            return node
        if isinstance(node, FunctionCall):
            node.arguments = [FVMCodegen._macro_substitute(a, subst) for a in node.arguments]
            return node
        if isinstance(node, ArrayAccess):
            node.array = FVMCodegen._macro_substitute(node.array, subst)
            node.index = FVMCodegen._macro_substitute(node.index, subst)
            return node
        if isinstance(node, MemberAccess):
            node.object = FVMCodegen._macro_substitute(node.object, subst)
            return node
        if isinstance(node, AddressOf):
            node.expression = FVMCodegen._macro_substitute(node.expression, subst)
            return node
        if isinstance(node, PointerDeref):
            node.pointer = FVMCodegen._macro_substitute(node.pointer, subst)
            return node
        return node

    def _visit_array_access(self, node):
        # Check if array is a heap-allocated var — use typed LOAD instead of ARRAY_LOAD
        if isinstance(node.array, Identifier) and node.array.name in self._heap_vars:
            heap_info = self._heap_vars[node.array.name]
            if len(heap_info) == 3:  # (elem_ttag, elem_bytes, count) — array
                elem_ttag, elem_bytes, _count = heap_info
                # ptr + index * elem_bytes -> LOAD elem_ttag elem_bytes
                self._emit(_instr(Op.LOCAL_GET, self._locals[node.array.name]))
                self._visit_expr(node.index)
                if elem_bytes > 1:
                    self._emit(_instr(Op.PUSH, Val(TTag.UINT, elem_bytes)))
                    self._emit(_instr(Op.MUL))
                self._emit(_instr(Op.ADD))
                self._emit(_instr(Op.LOAD, elem_ttag, elem_bytes))
                return True
        # Check if array is a pointer to a known struct type (e.g. BlockEntry*)
        # Mirror LLVM GEP: offset = index * sizeof(struct), then load struct-sized bytes
        if isinstance(node.array, Identifier):
            _arr_name = node.array.name
            _type_name = self._local_types.get(_arr_name) or self._local_typespecs.get(_arr_name)
            _in_locals = _arr_name in self._locals
            _in_block_globals = _arr_name in self._block_globals
            _in_outer_globals = _arr_name in self._outer_globals
            if isinstance(_type_name, str) and _type_name in self._struct_layouts:
                _ts = self._local_typespecs.get(_arr_name)
                _is_array = _ts is not None and getattr(_ts, 'is_array', False)
                _is_ptr = _ts is not None and getattr(_ts, 'is_pointer', False)
                if not _is_array and _is_ptr:
                    # Heap pointer to struct elements (e.g. BlockEntry* tbl) - use struct GEP
                    _layout = self._struct_layouts[_type_name]
                    _struct_size = _layout.total_size
                    self._visit_expr(node.array)
                    self._visit_expr(node.index)
                    self._emit(_instr(Op.PUSH, Val(TTag.UINT, _struct_size)))
                    self._emit(_instr(Op.MUL))
                    self._emit(_instr(Op.ADD))
                    self._emit(_instr(Op.LOAD, TTag.STRUCT, _struct_size, _type_name))
                    return True
                # Fall through to ARRAY_LOAD for VM arrays of struct pointers
        self._visit_expr(node.array)
        self._visit_expr(node.index)
        self._emit(_instr(Op.ARRAY_LOAD))
        return True

    def _visit_bitslice(self, node: BitSlice) -> bool:
        # Push value, start, end then emit BITSLICE.
        # The VM op pops end, start, value and pushes Val(TTag.DATA, result, {'bits': n}).
        self._visit_expr(node.value)
        self._visit_expr(node.start)
        self._visit_expr(node.end)
        self._emit(_instr(Op.BITSLICE))
        return True

    # ------------------------------------------------------------------
    # Control flow
    # ------------------------------------------------------------------

    def _visit_if(self, node: IfStatement):
        end_patches = []

        # Main if
        self._visit_expr(node.condition)
        jnf_idx = self._emit(_instr(Op.JNF, 0))
        self._visit_body(
            node.then_block.statements if isinstance(node.then_block, Block)
            else [node.then_block]
        )
        end_patches.append(self._emit(_instr(Op.JMP, 0)))
        self._patch_at(jnf_idx, Op.JNF, self._current_ip())

        # elif chains
        for cond, blk in (node.elif_blocks or []):
            self._visit_expr(cond)
            jnf_idx = self._emit(_instr(Op.JNF, 0))
            self._visit_body(blk.statements if isinstance(blk, Block) else [blk])
            end_patches.append(self._emit(_instr(Op.JMP, 0)))
            self._patch_at(jnf_idx, Op.JNF, self._current_ip())

        # else block
        if node.else_block is not None:
            self._visit_body(
                node.else_block.statements if isinstance(node.else_block, Block)
                else [node.else_block]
            )

        end_ip = self._current_ip()
        for idx in end_patches:
            self._patch_at(idx, Op.JMP, end_ip)

    def _emit_unpack(self, group: list, src_expr):
        """
        Unpack a scalar source into multiple variables.
        group[0] is the first (highest-bits) variable, group[-1] the last (lowest-bits).
        Element bit width is inferred from the target element type.
        """
        elem_dt = group[0].type_spec.base_type
        elem_ttag = _datatype_to_ttag(elem_dt)
        _bits = {
            DataType.SINT: 32, DataType.UINT: 32,
            DataType.SLONG: 64, DataType.ULONG: 64,
            DataType.BYTE: 8, DataType.CHAR: 8, DataType.BOOL: 1,
        }
        elem_bits = _bits.get(elem_dt, 32)
        n = len(group)
        # Build a mask for elem_bits
        mask = (1 << elem_bits) - 1

        # Evaluate and store the source once
        self._visit_expr(src_expr)
        src_slot = self._alloc_local('__unpack_src__')
        self._emit(_instr(Op.LOCAL_SET, src_slot))

        for i, decl in enumerate(group):
            slot = self._alloc_local(decl.name)
            # group[0] = MSB side: shift = (n-1-i)*elem_bits
            shift = (n - 1 - i) * elem_bits
            self._emit(_instr(Op.LOCAL_GET, src_slot))
            if shift > 0:
                self._emit(_instr(Op.PUSH, Val(TTag.INT, shift)))
                self._emit(_instr(Op.SHR))
            self._emit(_instr(Op.PUSH, Val(TTag.LONG, mask)))
            self._emit(_instr(Op.BAND))
            self._emit(_instr(Op.CAST, elem_ttag))
            self._emit(_instr(Op.LOCAL_SET, slot))
            # Record type
            if decl.type_spec is not None and decl.type_spec.base_type is not None:
                bt = decl.type_spec.base_type
                self._local_types[decl.name] = bt.value if hasattr(bt, 'value') else str(bt)

    def _emit_pack(self, arr: 'ArrayLiteral', target_type_spec):
        """
        Pack an ArrayLiteral into a scalar integer value.
        Elements are packed from LSB to MSB; the bit width of each element is
        inferred from the element type on the ArrayLiteral, defaulting to 32 bits
        (int-sized) per element.  The result is left on the stack as the target type.
        """
        target_ttag = _datatype_to_ttag(
            target_type_spec.base_type if target_type_spec else DataType.SLONG
        )
        # Determine per-element bit width from element_type or default to 32
        elem_bits = 32
        if arr.element_type is not None and arr.element_type.base_type is not None:
            _eb = {
                DataType.SINT: 32, DataType.UINT: 32,
                DataType.SLONG: 64, DataType.ULONG: 64,
                DataType.BYTE: 8,  DataType.CHAR: 8,
                DataType.BOOL: 1,
            }
            elem_bits = _eb.get(arr.element_type.base_type, 32)

        # Total bit width of the target type
        _total_bits = {
            DataType.SINT: 32, DataType.UINT: 32,
            DataType.SLONG: 64, DataType.ULONG: 64,
            DataType.BYTE: 8, DataType.CHAR: 8,
        }
        total_bits = _total_bits.get(
            target_type_spec.base_type if target_type_spec else DataType.SLONG, 64
        )
        n = len(arr.elements)
        if n == 0:
            self._emit(_instr(Op.PUSH, Val(target_ttag, 0)))
            return

        # Evaluate first element as the accumulator; it occupies the HIGH bits.
        # Element i shifts left by (n - 1 - i) * elem_bits.
        self._visit_expr(arr.elements[0])
        shift0 = (n - 1) * elem_bits
        if shift0 > 0:
            self._emit(_instr(Op.PUSH, Val(TTag.INT, shift0)))
            self._emit(_instr(Op.SHL))
        acc_slot = self._alloc_local('__pack_acc__')
        self._emit(_instr(Op.LOCAL_SET, acc_slot))

        for i, elem in enumerate(arr.elements[1:], start=1):
            shift = (n - 1 - i) * elem_bits
            self._visit_expr(elem)
            if shift > 0:
                self._emit(_instr(Op.PUSH, Val(TTag.INT, shift)))
                self._emit(_instr(Op.SHL))
            self._emit(_instr(Op.LOCAL_GET, acc_slot))
            self._emit(_instr(Op.BOR))
            self._emit(_instr(Op.LOCAL_SET, acc_slot))

        self._emit(_instr(Op.LOCAL_GET, acc_slot))
        self._emit(_instr(Op.CAST, target_ttag))

    def _visit_fp_decl(self, node: FunctionPointerDeclaration):
        """
        Function pointer declaration: def{}* pb() -> void = @bar;
        @bar stores Val(TTag.BYTES, func_name) in a named slot, then
        pb holds Val(TTag.PTR, that_slot) — same as @x for variables.
        """
        fp_slot = self._alloc_local(node.name)
        if node.initializer is not None:
            self._visit_expr(node.initializer)
        else:
            self._emit(_instr(Op.PUSH, Val(TTag.PTR, 0)))
        self._emit(_instr(Op.LOCAL_SET, fp_slot))
        self._local_types[node.name] = '__funcptr__'

    def _visit_function_def(self, node: FunctionDef):
        """
        Compile a comptime function definition and store its bytecode in
        self.compiled_functions so the caller (visit_ComptimeBlock in fcodegen.py)
        can register it with the VM before execute().
        Parameters are pre-loaded into local slots 0..N-1 by the VM _call() mechanism.
        """
        fn_cg = FVMCodegen(known_functions=dict(self._known_functions), program_statements=self._program_statements)
        fn_cg._outer_globals = set(self._block_globals)
        fn_cg._is_function_body = True
        fn_cg._using_namespaces = list(self._using_namespaces)
        fn_cg._struct_layouts = dict(self._struct_layouts)
        fn_cg._enum_names = set(self._enum_names)
        fn_cg._macro_table = dict(self._macro_table)
        fn_cg._local_types = dict(self._local_types)
        fn_cg._local_typespecs = dict(self._local_typespecs)
        # Allocate a slot for each parameter so LOCAL_GET/SET work by name
        for param in node.parameters:
            fn_cg._alloc_local(param.name)
            # print(f"[PARAM DEBUG] {node.name} param={param.name!r} type_spec={param.type_spec} ctn={getattr(param.type_spec, chr(99)+chr(117)+chr(115)+chr(116)+chr(111)+chr(109)+chr(95)+chr(116)+chr(121)+chr(112)+chr(101)+chr(110)+chr(97)+chr(109)+chr(101), None) if param.type_spec else None}", flush=True)
            if param.type_spec is not None:
                fn_cg._local_typespecs[param.name] = param.type_spec
                _ctn = getattr(param.type_spec, 'custom_typename', None)
                if _ctn:
                    fn_cg._local_types[param.name] = _ctn
                elif param.type_spec.base_type is not None:
                    _bt = param.type_spec.base_type
                    fn_cg._local_types[param.name] = str(_bt.value) if hasattr(_bt, 'value') else str(_bt)
        # <~ strict recursion: self-calls and returns in this body emit TAIL_SELF
        if node.is_recursive:
            fn_cg._tail_call_self = node.name
            fn_cg._tail_call_argc = len(node.parameters)
        # Skip forward declarations -- empty Block bodies with None params.
        _is_forward_decl = (
            node.body is None or
            (isinstance(node.body, Block) and
             not node.body.statements and
             all(getattr(p, 'name', p) is None for p in node.parameters))
        )
        if _is_forward_decl:
            return
        # Compile the body
        body_stmts = (
            node.body.statements if isinstance(node.body, Block) else [node.body]
        )
        fn_cg._visit_body(body_stmts)
        if node.is_recursive:
            # <~ function: _visit_return already emits TAIL_SELF inline.
            # If the body did not explicitly terminate, append the implicit
            # self tail-call (mirrors the runtime musttail insertion).
            argc = len(node.parameters)
            last = fn_cg._instructions[-1].op if fn_cg._instructions else None
            if last not in (Op.TAIL_SELF, Op.RET):
                fn_cg._emit(_instr(Op.TAIL_SELF, argc))
        else:
            # Normal function: ensure every path ends with RET.
            if not fn_cg._instructions or fn_cg._instructions[-1].op != Op.RET:
                from fvm import TTag as _TTag
                fn_cg._emit(_instr(Op.PUSH, Val(_TTag.VOID, 0)))
                fn_cg._emit(_instr(Op.RET))
        # Mark the original node so the LLVM codegen skips any template
        # instantiation that deep-copies it (fparser propagates this flag).
        node._is_comptime_only = True
        # Propagate nested function definitions upward without overwriting existing entries
        for _k, _v in fn_cg.compiled_functions.items():
            if _k not in self.compiled_functions:
                self.compiled_functions[_k] = _v
        self.compiled_functions[node.name] = fn_cg._instructions
        # Mark the original node so the LLVM codegen skips it unconditionally,
        # regardless of when _comptime_functions is populated.
        node._is_comptime_only = True

    def _visit_type_func_def(self, node: TypeFuncDef):
        """
        Compile a comptime type function definition.
        Registered under TypeFuncDef.mangle(type_name, func_name) so that
        TypeFuncCall sites can find it by the same mangled name.
        The implicit receiver parameter '_' occupies slot 0.
        """
        fn_cg = FVMCodegen(known_functions=dict(self._known_functions), program_statements=self._program_statements)
        fn_cg._outer_globals = set(self._block_globals)
        fn_cg._is_function_body = True
        fn_cg._using_namespaces = list(self._using_namespaces)
        fn_cg._struct_layouts = dict(self._struct_layouts)
        fn_cg._enum_names = set(self._enum_names)
        fn_cg._macro_table = dict(self._macro_table)
        fn_cg._local_types = dict(self._local_types)
        fn_cg._local_typespecs = dict(self._local_typespecs)
        # Slot 0: implicit receiver '_'
        fn_cg._alloc_local('_')
        # Explicit parameters follow
        for param in node.parameters:
            fn_cg._alloc_local(param.name)
            if param.type_spec is not None:
                fn_cg._local_typespecs[param.name] = param.type_spec
                _ctn = getattr(param.type_spec, 'custom_typename', None)
                if _ctn:
                    fn_cg._local_types[param.name] = _ctn
        body_stmts = (
            node.body.statements if isinstance(node.body, Block) else [node.body]
        )
        fn_cg._visit_body(body_stmts)
        if not fn_cg._instructions or fn_cg._instructions[-1].op != Op.RET:
            from fvm import TTag as _TTag
            fn_cg._emit(_instr(Op.PUSH, Val(_TTag.VOID, 0)))
            fn_cg._emit(_instr(Op.RET))
        for _k, _v in fn_cg.compiled_functions.items():
            if _k not in self.compiled_functions:
                self.compiled_functions[_k] = _v
        mangled = TypeFuncDef.mangle(node.type_name, node.func_name)
        self.compiled_functions[mangled] = fn_cg._instructions
        node._is_comptime_only = True

    def _type_bit_width(self, ts) -> int:
        """
        Compute the bit width of a TypeSystem without llvmlite.
        Flux structs are tightly packed — no padding.
        """
        from ftypesys import DataType as _DT
        if ts is None:
            return 32
        if ts.bit_width is not None:
            return ts.bit_width
        if ts.is_pointer:
            return 64
        if ts.is_array and ts.array_size and ts.base_type is not None:
            elem_bits = self._type_bit_width_base(ts.base_type, ts)
            arr_size = ts.array_size
            if hasattr(arr_size, 'value'):  # Literal node
                arr_size = int(arr_size.value)
            return elem_bits * int(arr_size)
        if ts.base_type is not None:
            return self._type_bit_width_base(ts.base_type, ts)
        if ts.custom_typename is not None:
            # Nested struct — look up in our own registry
            layout = self._struct_layouts.get(ts.custom_typename)
            if layout is not None:
                return layout.total_bits if layout.total_bits else layout.total_size * 8
        return 32

    def _type_bit_width_base(self, base_type, ts=None) -> int:
        from ftypesys import DataType as _DT
        _map = {
            _DT.SINT: 32, _DT.UINT: 32,
            _DT.SLONG: 64, _DT.ULONG: 64,
            _DT.FLOAT: 32, _DT.DOUBLE: 64,
            _DT.BOOL: 1, _DT.BYTE: 8, _DT.CHAR: 8,
            _DT.DATA: ts.bit_width if ts and ts.bit_width else 0,
        }
        return _map.get(base_type, 32)

    def _type_ttag_from_ts(self, ts) -> TTag:
        """Map a TypeSystem to the closest VM TTag."""
        from ftypesys import DataType as _DT
        if ts is None:
            return TTag.INT
        if ts.is_pointer:
            return TTag.PTR
        if ts.custom_typename is not None:
            _prim = _prim_alias_ttag(ts.custom_typename)
            if _prim is not None:
                return _prim
            return TTag.STRUCT
        if ts.base_type is not None:
            if ts.base_type == _DT.DATA:
                # data{N} types (and aliases such as u64/i32/wchar) are
                # scalar integers of N bits -- map to the closest integer
                # TTag based on bit width and signedness, the same way
                # _visit_cast resolves explicit (u64)/(i32) casts. Without
                # this, u64 etc fall through to the generic DATA->INT
                # default below, which truncates 64-bit pointer values to
                # 32 bits when the declared-type coercion CAST is emitted.
                bits = getattr(ts, 'bit_width', None) or 32
                is_signed = getattr(ts, 'is_signed', False)
                if bits <= 32:
                    return TTag.INT if is_signed else TTag.UINT
                else:
                    return TTag.LONG if is_signed else TTag.ULONG
            return _datatype_to_ttag(ts.base_type)
        return TTag.INT

    def _visit_struct_def(self, node: StructDef, prefix: str = ''):
        """
        Compute a StructLayout for this struct and register it.
        Flux structs are tightly packed — zero padding between fields.
        Handles nested structs recursively.
        """
        from fvm import StructLayout as _SL
        from ftypesys import DataType as _DT

        full_name = f'{prefix}__{node.name}' if prefix else node.name

        # Recurse into nested structs first so their layouts are available
        for nested in node.nested_structs:
            self._visit_struct_def(nested, prefix=full_name)

        fields = []
        byte_offset = 0
        total_bits = 0
        for member in node.members:
            bits = self._type_bit_width(member.type_spec)
            byte_size = max(1, (bits + 7) // 8)
            ttag = self._type_ttag_from_ts(member.type_spec)
            fields.append((member.name, ttag, byte_offset, byte_size))
            byte_offset += byte_size
            total_bits += bits

        layout = _SL(name=full_name, fields=fields, total_size=byte_offset, total_bits=total_bits)
        self._struct_layouts[full_name] = layout
        # Also register under bare name for convenience
        if prefix:
            self._struct_layouts[node.name] = layout
        node._is_comptime_only = True

    def _visit_struct_instance(self, node: StructInstance) -> bool:
        self._emit(_instr(Op.STRUCT_NEW, node.struct_name))
        tmp_slot = self._alloc_local('__struct_tmp__')
        self._emit(_instr(Op.LOCAL_SET, tmp_slot))
        for fname, fexpr in (node.field_values or {}).items():
            self._emit(_instr(Op.LOCAL_GET, tmp_slot))
            self._visit_expr(fexpr)
            self._emit(_instr(Op.STRUCT_STORE, fname))
            self._emit(_instr(Op.LOCAL_SET, tmp_slot))
        self._emit(_instr(Op.LOCAL_GET, tmp_slot))
        return True

    def _visit_struct_literal(self, node: StructLiteral) -> bool:
        """
        Struct literal {field=val, ...} — requires struct_type to be set.
        """
        if node.struct_type is None:
            raise FVMCodegenError(
                'fvmcodegen: StructLiteral has no struct_type in comptime', node)
        self._emit(_instr(Op.STRUCT_NEW, node.struct_type))
        tmp_slot = self._alloc_local('__struct_lit_tmp__')
        self._emit(_instr(Op.LOCAL_SET, tmp_slot))
        for fname, fexpr in (node.field_values or {}).items():
            self._emit(_instr(Op.LOCAL_GET, tmp_slot))
            self._visit_expr(fexpr)
            self._emit(_instr(Op.STRUCT_STORE, fname))
            self._emit(_instr(Op.LOCAL_SET, tmp_slot))
        if node.positional_values:
            layout = self._struct_layouts.get(node.struct_type)
            if layout:
                for (fname, _, _, _), fexpr in zip(layout.fields, node.positional_values):
                    self._emit(_instr(Op.LOCAL_GET, tmp_slot))
                    self._visit_expr(fexpr)
                    self._emit(_instr(Op.STRUCT_STORE, fname))
                    self._emit(_instr(Op.LOCAL_SET, tmp_slot))
        self._emit(_instr(Op.LOCAL_GET, tmp_slot))
        return True

    def _visit_struct_recast(self, node: StructRecast) -> bool:
        """
        StructRecast: T t from src
        Zero-copy reinterpretation. The destination slot receives a
        Val(TTag.PTR, src_slot, meta={struct_type, stack_slot, field_bit_offsets})
        pointing directly at the source frame slot. No heap allocation,
        no data movement. FIELD_GET/FIELD_SET on a stack_slot pointer
        extract/pack bits from the integer value in that slot directly.
        Source is invalidated by name.
        """
        layout = self._struct_layouts.get(node.target_type)
        if layout is None:
            raise FVMCodegenError(
                f'fvmcodegen: StructRecast: unknown struct type {node.target_type!r}', node)

        if not isinstance(node.source_expr, Identifier):
            raise FVMCodegenError(
                f'fvmcodegen: StructRecast source must be a simple identifier in comptime', node)

        src_name = node.source_expr.name
        if src_name not in self._locals:
            raise FVMCodegenError(
                f'fvmcodegen: StructRecast: source {src_name!r} not found in locals', node)
        src_slot = self._locals[src_name]

        # Pre-compute bit offsets for each field (LSB-first packed layout)
        _precise = {TTag.BOOL: 1, TTag.BYTE: 8, TTag.CHAR: 8,
                    TTag.INT: 32, TTag.UINT: 32,
                    TTag.LONG: 64, TTag.ULONG: 64,
                    TTag.FLOAT: 32, TTag.DOUBLE: 64}
        field_bit_offsets = {}
        bit_cursor = 0
        for fname, fttag, _byte_off, fbyte_size in layout.fields:
            field_bit_offsets[fname] = bit_cursor
            bit_cursor += _precise.get(fttag, fbyte_size * 8)

        # Emit STRUCT_NEW and populate each field by extracting bits from src
        self._emit(_instr(Op.STRUCT_NEW, node.target_type))
        tmp_slot = self._alloc_local('__recast_tmp__')
        self._emit(_instr(Op.LOCAL_SET, tmp_slot))
        for fname, fttag, _byte_off, fbyte_size in layout.fields:
            bit_off = field_bit_offsets.get(fname, 0)
            fbit_w  = _precise.get(fttag, fbyte_size * 8)
            mask    = (1 << fbit_w) - 1
            # LOCAL_GET src >> bit_off & mask
            self._emit(_instr(Op.LOCAL_GET, src_slot))
            if bit_off:
                self._emit(_instr(Op.PUSH, Val(TTag.INT, bit_off)))
                self._emit(_instr(Op.SHR))
            self._emit(_instr(Op.PUSH, Val(TTag.LONG, mask)))
            self._emit(_instr(Op.BAND))
            self._emit(_instr(Op.CAST, fttag))
            # STRUCT_STORE field -> write back
            self._emit(_instr(Op.LOCAL_GET, tmp_slot))
            self._emit(_instr(Op.SWAP))
            self._emit(_instr(Op.STRUCT_STORE, fname))
            self._emit(_instr(Op.LOCAL_SET, tmp_slot))
        self._emit(_instr(Op.LOCAL_GET, tmp_slot))

        # Invalidate source by name; slot index still exists but unreachable.
        if not getattr(node, 'suppress_invalidate', False):
            if src_name in self._locals:
                del self._locals[src_name]
            if src_name in self._local_types:
                del self._local_types[src_name]

        return True

    def _visit_member_access(self, node: MemberAccess) -> bool:
        """
        obj.member - struct field access or namespace path component.
        """
        if isinstance(node.object, Identifier):
            var_name = node.object.name
            type_name = self._local_types.get(var_name)
            if var_name in self._locals:
                if type_name and type_name in self._enum_names:
                    # me1._ -> ENUM_LOAD
                    self._visit_expr(node.object)
                    self._emit(_instr(Op.ENUM_LOAD))
                    return True
                # Struct field access: use STRUCT_LOAD
                self._visit_expr(node.object)
                self._emit(_instr(Op.STRUCT_LOAD, node.member))
                return True
            # Check if it is a known global before treating as namespace prefix
            if var_name in self._block_globals or var_name in self._outer_globals:
                self._visit_expr(node.object)
                self._emit(_instr(Op.STRUCT_LOAD, node.member))
                return True
            # Identifier not a known local or global - namespace path prefix, push nothing
            return False
        elif isinstance(node.object, MemberAccess):
            produced = self._visit_member_access(node.object)
            if produced:
                self._emit(_instr(Op.STRUCT_LOAD, node.member))
                return True
            return False
        # Generic: evaluate object and STRUCT_LOAD
        self._visit_expr(node.object)
        self._emit(_instr(Op.STRUCT_LOAD, node.member))
        return True

    def _visit_struct_field_access(self, node: StructFieldAccess) -> bool:
        self._visit_expr(node.struct_instance)
        self._emit(_instr(Op.STRUCT_LOAD, node.field_name))
        return True

    def _visit_struct_field_assign(self, node: StructFieldAssign):
        self._visit_expr(node.struct_instance)
        self._visit_expr(node.value)
        self._emit(_instr(Op.STRUCT_STORE, node.field_name))

    def _visit_enum_def(self, node: EnumDef):
        """
        Enum definition: register each value as a comptime local integer.
        e.g. enum MyEnum { Thing1, Thing2, Thing3 } ->
             Thing1=0, Thing2=1, Thing3=2 as INT locals.
        Also guards the LLVM codegen from visiting this node.
        """
        self._enum_names.add(node.name)
        for name, value in node.values.items():
            slot = self._alloc_local(name)
            self._emit(_instr(Op.PUSH, Val(TTag.INT, int(value))))
            self._emit(_instr(Op.LOCAL_SET, slot))
            self._local_types[name] = 'int'
        node._is_comptime_only = True

    def _visit_union_def(self, node: UnionDef):
        """
        Compute a StructLayout for a union.
        All members share offset 0; total size is the largest member size.
        Uses the same VM machinery as structs (STRUCT_NEW, FIELD_GET, FIELD_SET).
        """
        from fvm import StructLayout as _SL

        fields = []
        max_byte_size = 0
        for member in node.members:
            bits = self._type_bit_width(member.type_spec)
            byte_size = max(1, (bits + 7) // 8)
            ttag = self._type_ttag_from_ts(member.type_spec)
            fields.append((member.name, ttag, 0, byte_size))  # all at offset 0
            max_byte_size = max(max_byte_size, byte_size)

        layout = _SL(name=node.name, fields=fields, total_size=max_byte_size)
        self._struct_layouts[node.name] = layout
        node._is_comptime_only = True

    def _visit_extern_block(self, node: ExternBlock):
        """
        Register extern function prototypes with the VM so they can be called
        via ctypes at comptime runtime. Emits EXTERN_DECL instructions for
        each prototype so the VM's _extern_protos dict is populated.
        """
        for decl in (node.declarations or []):
            ret_ttag = self._type_ttag_from_ts(decl.return_type) if decl.return_type is not None else TTag.VOID
            self._emit(_instr(Op.EXTERN_DECL, decl.name, ret_ttag))

    def _visit_namespace_def(self, node: NamespaceDef, prefix: str = ''):
        """
        Compile a comptime namespace definition.

        Functions are registered under their fully-qualified mangled name
        (e.g. A__foo for namespace A { def foo... }).  Nested namespaces
        are recursed with the accumulated prefix.  Structs, objects, enums,
        and unions are ignored — they have no runtime representation in the VM.
        """
        ns_name = f'{prefix}__{node.name}' if prefix else node.name
        node._is_comptime_only = True

        for var in (node.variables or []):
            # global variables in a namespace are initialized and registered as block globals
            self._visit_var_decl(var)
            self._block_globals.add(var.name)

        for func in node.functions:
            if func is None:
                continue
            fn_cg = FVMCodegen(known_functions=self._known_functions, program_statements=self._program_statements)
            fn_cg._outer_globals = set(self._block_globals)
            fn_cg._is_function_body = True
            fn_cg._using_namespaces = list(self._using_namespaces)
            fn_cg._struct_layouts = dict(self._struct_layouts)
            fn_cg._enum_names = set(self._enum_names)
            fn_cg._macro_table = dict(self._macro_table)
            fn_cg._local_types = dict(self._local_types)
            fn_cg._local_typespecs = dict(self._local_typespecs)
            for param in func.parameters:
                fn_cg._alloc_local(param.name)
                if param.type_spec is not None:
                    fn_cg._local_typespecs[param.name] = param.type_spec
                    _ctn = getattr(param.type_spec, 'custom_typename', None)
                    if _ctn:
                        fn_cg._local_types[param.name] = _ctn
                    elif param.type_spec.base_type is not None:
                        _bt = param.type_spec.base_type
                        fn_cg._local_types[param.name] = str(_bt.value) if hasattr(_bt, 'value') else str(_bt)
            # Skip forward declarations -- they have empty Block bodies and None params.
            # Registering them as stubs would block the real implementations.
            _is_forward_decl = (
                func.body is None or
                (isinstance(func.body, Block) and
                 not func.body.statements and
                 all(getattr(p, 'name', p) is None for p in func.parameters))
            )
            if _is_forward_decl:
                continue
            body_stmts = (
                func.body.statements if isinstance(func.body, Block) else [func.body]
            )
            fn_cg._visit_body(body_stmts)
            if not fn_cg._instructions or fn_cg._instructions[-1].op != Op.RET:
                from fvm import TTag as _TTag
                fn_cg._emit(_instr(Op.PUSH, Val(_TTag.VOID, 0)))
                fn_cg._emit(_instr(Op.RET))
            for _k, _v in fn_cg.compiled_functions.items():
                if _k not in self.compiled_functions:
                    self.compiled_functions[_k] = _v
            for _k, _v in fn_cg.compiled_overloads.items():
                if _k not in self.compiled_overloads:
                    self.compiled_overloads[_k] = _v
                else:
                    self.compiled_overloads[_k].extend(_v)
            mangled = f'{ns_name}__{func.name}'
            # Build a param-type signature for overload discrimination.
            # e.g. fmalloc(size_t) -> fmalloc__, fmalloc(ulong) -> fmalloc__
            def _ts_tag(ts):
                if ts is None: return 'void'
                bt = getattr(ts, 'base_type', None)
                if bt is None: return 'ptr'
                base = str(bt).split('.')[-1].lower() if bt is not None else 'void'
                if getattr(ts, 'is_array', False):
                    return base + 'arr'
                if getattr(ts, 'is_pointer', False) or getattr(ts, 'pointer_depth', 0):
                    return base + 'ptr'
                return base
            param_sig = '__$' + '_'.join(_ts_tag(p.type_spec) for p in func.parameters) if func.parameters else ''
            overload_key = mangled + param_sig
            self.compiled_functions[overload_key] = fn_cg._instructions
            # if 'print__$bytearr' in overload_key:
            #     import sys as _sys
            #     _sys.stderr.write(f'[DEBUG STORE] {overload_key} params={[getattr(p,"name",p) for p in func.parameters]} instrs[0]={fn_cg._instructions[0] if fn_cg._instructions else None}\n'); _sys.stderr.flush()
            # import sys as _sys; _sys.stderr.write(f'[DEBUG NS] registered overload_key={overload_key!r} param_sig={param_sig!r}\n'); _sys.stderr.flush()
            if overload_key.endswith('print__$byte'):
                pass
            # if overload_key.endswith('print__$byte'):
            #     import sys as _sys
            #     _sys.stderr.write(f'[DEBUG BODY print__$byte] first 10 instrs:\n')
            #     for _i, _ins in enumerate(fn_cg._instructions[:10]):
            #         _sys.stderr.write(f'  {_i}: {_ins.op.name} {_ins.operands}\n')
            #     _sys.stderr.flush()
            # Register overload table for runtime dispatch by arg types.
            for reg_name in (mangled, func.name):
                if reg_name not in self.compiled_overloads:
                    self.compiled_overloads[reg_name] = []
                self.compiled_overloads[reg_name].append((func.parameters, fn_cg._instructions))
            # Plain name: first overload wins as default.
            if mangled not in self.compiled_functions:
                self.compiled_functions[mangled] = fn_cg._instructions
            if func.name not in self.compiled_functions:
                self.compiled_functions[func.name] = fn_cg._instructions
            func._is_comptime_only = True

        for struct in node.structs:
            self._visit_struct_def(struct, prefix=ns_name)

        for extern_block in node.extern_blocks:
            self._visit_extern_block(extern_block)

        for nested in node.nested_namespaces:
            self._visit_namespace_def(nested, prefix=ns_name)

    def _visit_using(self, node):
        ns = node.namespace_path.replace('::', '__')
        if ns not in self._excluded_namespaces and ns not in self._using_namespaces:
            self._using_namespaces.append(ns)

    def _visit_not_using(self, node):
        ns = node.namespace_path.replace('::', '__')
        self._excluded_namespaces.add(ns)
        if ns in self._using_namespaces:
            self._using_namespaces.remove(ns)

    def _visit_switch(self, node: SwitchStatement):
        """
        Compile a switch statement.

        Strategy: evaluate the subject once into a temp slot, then for each
        non-default case emit CMP_EQ + JNF to skip the body.  The default
        case (Case.value is None) is emitted last and always falls through.
        break inside a case body jumps past the entire switch.
        """
        # Evaluate subject expression and store in a temp local
        self._visit_expr(node.expression)
        subject_slot = self._alloc_local('__switch_subject__')
        self._emit(_instr(Op.LOCAL_SET, subject_slot))

        break_patches: List[int] = []
        default_case: Optional[Case] = None

        for case in node.cases:
            if case.value is None:
                # defer default to end
                default_case = case
                continue

            # Push subject and case value, compare
            self._emit(_instr(Op.LOCAL_GET, subject_slot))
            self._visit_expr(case.value)
            self._emit(_instr(Op.CMP_EQ))
            skip_patch = self._emit(_instr(Op.JNF, 0))

            # Emit case body
            body_stmts = (
                case.body.statements if isinstance(case.body, Block) else [case.body]
            )
            for stmt in body_stmts:
                if stmt is None:
                    continue
                self._visit_stmt(stmt)

            # Jump past the switch after a matched (non-breaking) case body
            break_patches.append(self._emit(_instr(Op.JMP, 0)))
            self._patch_at(skip_patch, Op.JNF, self._current_ip())

        # Emit default case body if present
        if default_case is not None:
            body_stmts = (
                default_case.body.statements
                if isinstance(default_case.body, Block)
                else [default_case.body]
            )
            for stmt in body_stmts:
                if stmt is None:
                    continue
                self._visit_stmt(stmt)

        after_switch = self._current_ip()
        for idx in break_patches:
            self._patch_at(idx, Op.JMP, after_switch)

    def _visit_for(self, node: ForLoop):
        if node.init is not None:
            self._visit_stmt(node.init)

        loop_start = self._current_ip()

        exit_patch = None
        if node.condition is not None:
            self._visit_expr(node.condition)
            exit_patch = self._emit(_instr(Op.JNF, 0))

        self._break_stack.append([])
        self._continue_stack.append([])

        body_stmts = (
            node.body.statements if isinstance(node.body, Block) else [node.body]
        )
        for stmt in body_stmts:
            if stmt is None:
                continue
            self._visit_stmt(stmt)

        update_ip = self._current_ip()
        if node.update is not None:
            self._visit_stmt(node.update)

        self._emit(_instr(Op.JMP, loop_start))
        after_loop = self._current_ip()

        break_patches = self._break_stack.pop()
        continue_patches = self._continue_stack.pop()
        if exit_patch is not None:
            self._patch_at(exit_patch, Op.JNF, after_loop)
        for idx in continue_patches:
            self._patch_at(idx, Op.JMP, update_ip)
        for idx in break_patches:
            self._patch_at(idx, Op.JMP, after_loop)

    def _visit_for_in(self, node: ForInLoop):
        """
        Compile a for-in loop at comptime, mirroring fcodegen.py's visit_ForInLoop.

        The iterable is evaluated first to determine its runtime kind:
          - TTag.BYTES  : null-terminated byte string (byte*). Walk byte by byte
                          until a zero byte is found. Mirrors fcodegen's i8* branch.
          - TTag.ARRAY  : VM array value. Walk by index from 0 to len-1.
                          Mirrors fcodegen's ArrayType branch.
          - TTag.PTR    : heap pointer. Walk pointer arithmetic until slot value
                          is zero (null). Mirrors fcodegen's pointer-of-pointer branch.

        The loop variable named node.variables[0] is defined in the local scope
        for each iteration body execution, mirroring fcodegen's alloca/define.

        Break/continue are handled via the same _break_stack/_continue_stack
        mechanism used by _visit_for and _visit_while.
        """
        var_name = node.variables[0]
        body_stmts = (
            node.body.statements if isinstance(node.body, Block) else [node.body]
        )

        # Evaluate iterable once to a local slot so we can reference it per-iteration
        # without re-evaluating the expression. Use a hidden slot name.
        iter_slot_name = f'__forin_iter__{var_name}'
        iter_slot = self._alloc_local(iter_slot_name)
        self._visit_expr(node.iterable)
        self._emit(_instr(Op.DUP))
        self._emit(_instr(Op.LOCAL_SET, iter_slot))

        # We need to branch based on the runtime kind of the iterable.
        # At comptime all types are known statically via the typespec, but
        # rather than duplicate typespec inspection, we mirror fcodegen: the
        # iterable's TTag determines behavior. We use a type-tag dispatch at
        # codegen time by inspecting what _visit_expr will have pushed.
        #
        # Static dispatch: resolve the iterable's kind from typespec if available.
        iter_kind = 'bytes'  # default: treat as null-terminated byte string
        if isinstance(node.iterable, Identifier):
            _ts = self._local_typespecs.get(node.iterable.name)
            if _ts is not None:
                _is_arr = getattr(_ts, 'is_array', False)
                _is_ptr = getattr(_ts, 'is_pointer', False)
                if _is_arr:
                    iter_kind = 'array'
                elif _is_ptr:
                    # byte* -> bytes walk; other pointer -> pointer walk
                    from ftypesys import DataType as _DT
                    if getattr(_ts, 'base_type', None) == _DT.BYTE:
                        iter_kind = 'bytes'
                    else:
                        iter_kind = 'ptr'

        # Allocate the loop variable slot
        var_slot = self._alloc_local(var_name)

        self._break_stack.append([])
        self._continue_stack.append([])

        if iter_kind == 'bytes':
            # -- null-terminated byte string: walk index 0..N until byte==0 --
            # idx slot
            idx_slot_name = f'__forin_idx__{var_name}'
            idx_slot = self._alloc_local(idx_slot_name)
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 0)))
            self._emit(_instr(Op.LOCAL_SET, idx_slot))

            # cond: load iter[idx], if byte == 0 exit
            loop_cond = self._current_ip()
            self._emit(_instr(Op.LOCAL_GET, iter_slot))   # push string
            self._emit(_instr(Op.LOCAL_GET, idx_slot))    # push index
            self._emit(_instr(Op.ARRAY_LOAD))             # push byte at index
            self._emit(_instr(Op.DUP))                    # keep for condition check
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 0)))
            self._emit(_instr(Op.CMP_EQ))                 # byte == 0?
            exit_patch = self._emit(_instr(Op.JIF, 0))   # jump out if zero (end of string)
            # store byte into var slot (already on stack from DUP above)
            self._emit(_instr(Op.LOCAL_SET, var_slot))

            # body
            for stmt in body_stmts:
                if stmt is None:
                    continue
                self._visit_stmt(stmt)

            # latch: idx++, jump back to cond
            latch_ip = self._current_ip()
            self._emit(_instr(Op.LOCAL_GET, idx_slot))
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
            self._emit(_instr(Op.ADD))
            self._emit(_instr(Op.LOCAL_SET, idx_slot))
            self._emit(_instr(Op.JMP, loop_cond))

            after_loop = self._current_ip()
            self._patch_at(exit_patch, Op.JIF, after_loop)

        elif iter_kind == 'array':
            # -- VM array: walk index 0 .. ARRAY_LEN-1 --
            idx_slot_name = f'__forin_idx__{var_name}'
            idx_slot = self._alloc_local(idx_slot_name)
            len_slot_name = f'__forin_len__{var_name}'
            len_slot = self._alloc_local(len_slot_name)

            # Store length once
            self._emit(_instr(Op.LOCAL_GET, iter_slot))
            self._emit(_instr(Op.ARRAY_LEN))
            self._emit(_instr(Op.LOCAL_SET, len_slot))

            self._emit(_instr(Op.PUSH, Val(TTag.INT, 0)))
            self._emit(_instr(Op.LOCAL_SET, idx_slot))

            loop_cond = self._current_ip()
            self._emit(_instr(Op.LOCAL_GET, idx_slot))
            self._emit(_instr(Op.LOCAL_GET, len_slot))
            self._emit(_instr(Op.CMP_LT))
            exit_patch = self._emit(_instr(Op.JNF, 0))

            # load element into var slot
            self._emit(_instr(Op.LOCAL_GET, iter_slot))
            self._emit(_instr(Op.LOCAL_GET, idx_slot))
            self._emit(_instr(Op.ARRAY_LOAD))
            self._emit(_instr(Op.LOCAL_SET, var_slot))

            for stmt in body_stmts:
                if stmt is None:
                    continue
                self._visit_stmt(stmt)

            latch_ip = self._current_ip()
            self._emit(_instr(Op.LOCAL_GET, idx_slot))
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
            self._emit(_instr(Op.ADD))
            self._emit(_instr(Op.LOCAL_SET, idx_slot))
            self._emit(_instr(Op.JMP, loop_cond))

            after_loop = self._current_ip()
            self._patch_at(exit_patch, Op.JNF, after_loop)

        else:
            # -- ptr walk: dereference slot until null --
            # Mirrors fcodegen's pointer-of-pointer branch: walk until *ptr == 0
            loop_cond = self._current_ip()
            self._emit(_instr(Op.LOCAL_GET, iter_slot))
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 0)))
            self._emit(_instr(Op.CMP_EQ))
            exit_patch = self._emit(_instr(Op.JIF, 0))

            self._emit(_instr(Op.LOCAL_GET, iter_slot))
            self._emit(_instr(Op.LOCAL_SET, var_slot))

            for stmt in body_stmts:
                if stmt is None:
                    continue
                self._visit_stmt(stmt)

            latch_ip = self._current_ip()
            self._emit(_instr(Op.LOCAL_GET, iter_slot))
            self._emit(_instr(Op.PUSH, Val(TTag.INT, 1)))
            self._emit(_instr(Op.ADD))
            self._emit(_instr(Op.LOCAL_SET, iter_slot))
            self._emit(_instr(Op.JMP, loop_cond))

            after_loop = self._current_ip()
            self._patch_at(exit_patch, Op.JIF, after_loop)

        # Patch break/continue
        break_patches = self._break_stack.pop()
        continue_patches = self._continue_stack.pop()
        for idx in break_patches:
            self._patch_at(idx, Op.JMP, after_loop)
        for idx in continue_patches:
            self._patch_at(idx, Op.JMP, latch_ip)

    def _visit_while(self, node: WhileLoop):
        loop_start = self._current_ip()
        self._visit_expr(node.condition)
        exit_patch = self._emit(_instr(Op.JNF, 0))

        self._break_stack.append([])
        self._continue_stack.append([])
        body_stmts = (
            node.body.statements if isinstance(node.body, Block) else [node.body]
        )
        for stmt in body_stmts:
            if stmt is None:
                continue
            self._visit_stmt(stmt)

        self._emit(_instr(Op.JMP, loop_start))
        after_loop = self._current_ip()
        self._patch_at(exit_patch, Op.JNF, after_loop)
        break_patches = self._break_stack.pop()
        continue_patches = self._continue_stack.pop()
        for idx in break_patches:
            self._patch_at(idx, Op.JMP, after_loop)
        for idx in continue_patches:
            self._patch_at(idx, Op.JMP, loop_start)

    def _visit_label(self, node: LabelStatement):
        """Record the current IP as the target for this label name."""
        self._labels[node.name] = self._current_ip()
        # Resolve any forward gotos that were waiting for this label
        remaining = []
        for idx, target in self._goto_patches:
            if target == node.name:
                self._patch_at(idx, Op.JMP, self._current_ip())
            else:
                remaining.append((idx, target))
        self._goto_patches = remaining

    def _visit_goto(self, node: GotoStatement):
        """
        Emit a jump to a label or a named comptime block.

        For named comptime blocks: compile the block's body as a standalone
        function (registered under '__comptime_block__<name>') and emit a
        CALL -- this lets the VM handle recursion naturally at runtime.
        Inlining the body directly would cause Python-level infinite recursion
        during codegen for mutually-recursive comptime blocks.

        Goto to a comptime block from non-comptime code is caught by
        fcodegen.py's visit_GotoStatement and raises a FluxCodegenError.
        """
        from fast import ComptimeBlock as _ComptimeBlock
        for _s in self._program_statements:
            if isinstance(_s, _ComptimeBlock) and _s.name == node.target:
                func_key = f'__comptime_block__{node.target}'
                # Compile the block body as a function the first time it's
                # targeted; subsequent gotos reuse the compiled function.
                if func_key not in self.compiled_functions:
                    # Register a stub first to break mutual-recursion cycles
                    self.compiled_functions[func_key] = []
                    fn_cg = FVMCodegen(
                        known_functions=dict(self._known_functions),
                        program_statements=self._program_statements)
                    fn_cg._outer_globals      = set(self._block_globals)
                    fn_cg._is_function_body   = False
                    fn_cg._using_namespaces   = list(self._using_namespaces)
                    fn_cg._struct_layouts     = dict(self._struct_layouts)
                    fn_cg._enum_names         = set(self._enum_names)
                    fn_cg._macro_table        = dict(self._macro_table)
                    fn_cg._local_types        = dict(self._local_types)
                    fn_cg._local_typespecs    = dict(self._local_typespecs)
                    fn_cg._interface_registry = self._interface_registry
                    fn_cg._interface_whitelist= self._interface_whitelist
                    fn_cg.compiled_functions  = self.compiled_functions
                    fn_cg._visit_body(_s.body)
                    fn_cg._emit(_instr(Op.PUSH, Val(TTag.VOID, 0)))
                    fn_cg._emit(_instr(Op.RET))
                    self.compiled_functions[func_key] = fn_cg._instructions
                self._emit(_instr(Op.CALL, func_key, 0))
                return
        # Regular label goto
        if node.target in self._labels:
            self._emit(_instr(Op.JMP, self._labels[node.target]))
        else:
            patch_idx = self._emit(_instr(Op.JMP, 0))
            self._goto_patches.append((patch_idx, node.target))

    def _visit_jump(self, node: JumpStatement):
        """
        jump expr — low-level jump to an address expression.
        In the VM context, if the expression is a label address we resolve it;
        otherwise treat as a goto to whatever the expression evaluates to.
        """
        from fast import Identifier as _Id
        if isinstance(node.target, _Id) and node.target.name in self._labels:
            self._emit(_instr(Op.JMP, self._labels[node.target.name]))
        elif isinstance(node.target, _Id):
            patch_idx = self._emit(_instr(Op.JMP, 0))
            self._goto_patches.append((patch_idx, node.target.name))
        else:
            # Dynamic address — evaluate and jump (best-effort)
            self._visit_expr(node.target)
            # No direct indirect-jump in VM; fall through silently

    def _resolve_goto_patches(self):
        """Resolve any remaining goto patches after a body is fully emitted."""
        for idx, target in self._goto_patches:
            if target in self._labels:
                self._patch_at(idx, Op.JMP, self._labels[target])
        self._goto_patches = [(i, t) for i, t in self._goto_patches
                              if t not in self._labels]

    def _visit_do(self, node: DoLoop):
        """Plain do loop: infinite loop, only exits via break."""
        loop_start = self._current_ip()
        self._break_stack.append([])
        self._continue_stack.append([])
        body_stmts = (
            node.body.statements if isinstance(node.body, Block) else [node.body]
        )
        for stmt in body_stmts:
            if stmt is None:
                continue
            self._visit_stmt(stmt)
        self._emit(_instr(Op.JMP, loop_start))
        after_loop = self._current_ip()
        break_patches = self._break_stack.pop()
        continue_patches = self._continue_stack.pop()
        for idx in break_patches:
            self._patch_at(idx, Op.JMP, after_loop)
        for idx in continue_patches:
            self._patch_at(idx, Op.JMP, loop_start)

    def _visit_do_while(self, node: DoWhileLoop):
        loop_start = self._current_ip()
        self._break_stack.append([])
        self._continue_stack.append([])
        body_stmts = (
            node.body.statements if isinstance(node.body, Block) else [node.body]
        )
        for stmt in body_stmts:
            if stmt is None:
                continue
            self._visit_stmt(stmt)
        cond_ip = self._current_ip()
        self._visit_expr(node.condition)
        self._emit(_instr(Op.JIF, loop_start))
        after_loop = self._current_ip()
        break_patches = self._break_stack.pop()
        continue_patches = self._continue_stack.pop()
        for idx in break_patches:
            self._patch_at(idx, Op.JMP, after_loop)
        for idx in continue_patches:
            self._patch_at(idx, Op.JMP, cond_ip)

    def _visit_return(self, node: ReturnStatement):
        if node.value is not None and isinstance(node.value, Identifier) and node.value.name in self._local_vars:
            raise FVMCodegenError(
                f"fvmcodegen: local variable '{node.value.name}' cannot escape scope (returned from function)",
                node)
        if node.value is not None:
            self._visit_expr(node.value)
        else:
            self._emit(_instr(Op.PUSH, Val(TTag.VOID, 0)))
        # A return exits every enclosing block, so run all pending `defer`
        # statements (innermost scope first) now, after the return value
        # has been computed and pushed but before RET consumes it. Each
        # deferred statement is stack-neutral (ExpressionStatement pops any
        # value it leaves), so the return value underneath is undisturbed.
        self._flush_all_defers()
        # Inside a <~ function every return is a re-entry, not an exit.
        # escape bypasses this by calling _visit_escape directly.
        if self._tail_call_self is not None:
            self._emit(_instr(Op.TAIL_SELF, self._tail_call_argc))
        else:
            self._emit(_instr(Op.RET))

    def _visit_escape(self, node: EscapeStatement):
        """
        escape call; -- exits strict recursion by making a normal non-tail call.
        Temporarily clears _tail_call_self so the inner call emits CALL not TAIL_SELF,
        then restores it. The return value of the escaped call becomes the return
        value of the <~ function, ending the tail-call loop.
        """
        saved = self._tail_call_self
        self._tail_call_self = None
        self._visit_expr(node.call)
        self._tail_call_self = saved
        self._flush_all_defers()
        self._emit(_instr(Op.RET))

    def _visit_break(self, node: BreakStatement):
        idx = self._emit(_instr(Op.JMP, 0))
        if self._break_stack:
            self._break_stack[-1].append(idx)
        # else: unpatched (break outside loop -- should not happen in valid Flux)

    def _visit_continue(self, node: ContinueStatement):
        idx = self._emit(_instr(Op.JMP, 0))
        if self._continue_stack:
            self._continue_stack[-1].append(idx)

    # ------------------------------------------------------------------
    # emitflux
    # ------------------------------------------------------------------

    def _visit_fluxvm_block(self, node: FluxVMBlock):
        """
        fluxvm { OP [operands...] } -- inline FVM bytecode.
        Each non-empty line is one instruction:
          first token  = Op name  resolved via Op[name]
          remaining    = operands: integer literals, quoted strings,
                         local variable names (resolved to slot index),
                         or TTag names (resolved via TTag[name]).
        Op names are taken directly from the Op enum so no separate
        table is needed -- adding a new Op automatically makes it available.
        """
        from fvm import Op as _Op, TTag as _TTag
        for raw_line in node.body.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('//'):
                continue
            # Strip inline comment
            if '/' in line:
                line = line[:line.index('/')].strip()
            if not line:
                continue
            parts = line.split()
            op_name = parts[0].upper()
            try:
                op = _Op[op_name]
            except KeyError:
                raise FVMCodegenError(
                    f'fluxvm: unknown opcode {op_name!r}', node)
            raw_operands = []
            for tok in parts[1:]:
                # Integer literal (decimal or hex or binary)
                try:
                    raw_operands.append(int(tok, 0))
                    continue
                except ValueError:
                    pass
                # Quoted string literal
                if (tok.startswith('"') and tok.endswith('"')) or \
                   (tok.startswith("'") and tok.endswith("'")):
                    raw_operands.append(tok[1:-1])
                    continue
                # TTag name (e.g. INT, BOOL, ULONG)
                try:
                    raw_operands.append(_TTag[tok.upper()])
                    continue
                except KeyError:
                    pass
                # Local variable name -> slot index
                if tok in self._locals:
                    raw_operands.append(self._locals[tok])
                    continue
                raise FVMCodegenError(
                    f'fluxvm: unresolved operand {tok!r} on line {line!r}', node)
            # PUSH requires a Val, not a raw value.
            # Syntax: PUSH <value> [TTAG]  -- TTAG defaults to INT for integers,
            #         BYTES for strings.
            if op == _Op.PUSH:
                if not raw_operands:
                    raise FVMCodegenError('fluxvm: PUSH requires a value operand', node)
                value = raw_operands[0]
                if len(raw_operands) >= 2 and isinstance(raw_operands[1], _TTag):
                    ttag = raw_operands[1]
                elif isinstance(value, str):
                    ttag = _TTag.BYTES
                    value = value.encode('utf-8')
                elif isinstance(value, float):
                    ttag = _TTag.DOUBLE
                else:
                    ttag = _TTag.INT
                self._emit(_instr(op, Val(ttag, value)))
            else:
                self._emit(_instr(op, *raw_operands))

    def _visit_emitflux(self, node: EmitFlux):
        """
        Emit an EMITFLUX opcode.  Operands:
          [0] source_text : str              -- raw Flux text with placeholder names
          [1] var_names   : [(name, slot)]   -- snapshot of current locals

        At VM execution time the actual values in those slots are used for
        variable substitution in _op_emitflux().
        """
        var_snapshot = list(self._locals.items())  # [(name, slot), ...]
        self._emit(_instr(Op.EMITFLUX, node.source_text, var_snapshot))