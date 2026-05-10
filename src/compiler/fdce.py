#!/usr/bin/env python3
"""
Flux Dead Code Eliminator  (fdce.py)

Copyright (C) 2026 Karac Thweatt

Contributors:
    Piotr Bednarski

Runs on the AST produced by FluxParser *before* code generation.

Strategy
--------
Only namespace-level *functions* are candidates for elimination.
Top-level structs, objects, enums, and traits are always preserved.

Liveness closure:
  1. Seed from non-namespace top-level code + entry points.
  2. Expand: for each live name, walk that function's body and add its refs.
  3. Repeat until stable.
  4. Eliminate anything never reached.

Mangling
--------
Flux mangles  ns::func  ->  ns__func  at call sites, and nested namespaces
produce  outer__inner__func.  A call site may use any *suffix* of the full
mangled name (e.g. helpers__compare_ignore_case for a function that lives
at standard__strings__helpers__compare_ignore_case).

We therefore index every function under ALL suffix variants of its fully-
qualified mangled name, and the ref collector decomposes every __-name it
sees into all its suffix variants too.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Set

# ---------------------------------------------------------------------------
# Primitive / keyword names – never user-defined symbols
# ---------------------------------------------------------------------------

_PRIMITIVE_TYPES: frozenset = frozenset({
    'int', 'uint', 'float', 'double', 'bool', 'byte', 'char',
    'void', 'str', 'string', 'i8', 'i16', 'i32', 'i64', 'i128',
    'u8', 'u16', 'u32', 'u64', 'u128', 'f32', 'f64',
    'ptr', 'ref', 'null', 'nullptr', 'true', 'false',
})

# ---------------------------------------------------------------------------
# Entry-point / always-keep function names
# ---------------------------------------------------------------------------

_ALWAYS_KEEP: frozenset = frozenset({
    'main',
    'FRTStartup', 'frt_startup',
})

# ---------------------------------------------------------------------------
# Mangling helpers
# ---------------------------------------------------------------------------

def _all_suffixes(mangled: str) -> List[str]:
    """
    Return every __-suffix of a mangled name, including the full name and
    the bare name.

    Example:
        'standard__strings__helpers__compare_ignore_case'
        -> ['standard__strings__helpers__compare_ignore_case',
            'strings__helpers__compare_ignore_case',
            'helpers__compare_ignore_case',
            'compare_ignore_case']
    """
    parts = mangled.split('__')
    results = []
    for i in range(len(parts)):
        results.append('__'.join(parts[i:]))
    return results


# ---------------------------------------------------------------------------
# Generic AST walker – collects every referenced name from a subtree
# ---------------------------------------------------------------------------

class _RefCollector:
    """
    Depth-first AST walker.  Uses id()-based visited set to handle cyclic
    / shared AST references.
    """

    def __init__(self) -> None:
        self.refs: Set[str] = set()
        self._visited: Set[int] = set()

    def collect(self, node: Any) -> None:
        self._walk(node)

    def _add(self, name: str) -> None:
        """Add a name and ALL its suffix variants."""
        if not name or name in _PRIMITIVE_TYPES:
            return
        # Handle :: qualified names (convert to __ form first)
        if '::' in name:
            name = name.replace('::', '__')
        # Handle object construction / method calls written as  TypeName.__init
        # or  TypeName.methodName  (dot-separated).  Convert the dot to __ so
        # the pruner's  cur_prefix__ObjName__methodName  pattern can match it.
        # We add BOTH the dot form and the __ form so nothing is lost.
        if '.' in name:
            name_dunder = name.replace('.', '__')
            for variant in _all_suffixes(name_dunder):
                if variant and variant not in _PRIMITIVE_TYPES:
                    self.refs.add(variant)
        for variant in _all_suffixes(name):
            if variant and variant not in _PRIMITIVE_TYPES:
                self.refs.add(variant)

    def _walk(self, node: Any) -> None:
        if node is None:
            return
        if isinstance(node, (int, float, bool, bytes)):
            return
        if isinstance(node, str):
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                self._walk(child)
            return
        if isinstance(node, dict):
            for v in node.values():
                self._walk(v)
            return

        node_id = id(node)
        if node_id in self._visited:
            return
        self._visited.add(node_id)

        cls = type(node).__name__

        # ── Identifier ───────────────────────────────────────────────────
        if cls == 'Identifier':
            name = getattr(node, 'name', None)
            if isinstance(name, str):
                self._add(name)
            return

        # ── FunctionCall ──────────────────────────────────────────────────
        if cls == 'FunctionCall':
            name = getattr(node, 'name', None)
            if isinstance(name, str):
                self._add(name)
            self._walk(getattr(node, 'arguments', None))
            self._walk(getattr(node, 'args', None))
            self._walk(getattr(node, 'type_args', None))
            return

        # ── MethodCall ────────────────────────────────────────────────────
        # MethodCall represents  obj.method(args)  *and* namespaced calls
        # like  helpers::compare_ignore_case(x, y)  which the parser may
        # represent as MethodCall(object=Identifier("helpers"),
        #                         method_name="compare_ignore_case", ...).
        # We must register both the bare method_name AND the qualified
        # object__method_name variant so the liveness index is hit.
        if cls == 'MethodCall':
            method_name = getattr(node, 'method_name', None)
            obj = getattr(node, 'object', None)
            if isinstance(method_name, str) and method_name:
                # Register the bare method name
                self._add(method_name)
                # If the receiver is an Identifier (e.g. a namespace alias),
                # also register the qualified  obj__method  variant so that
                # partial-suffix matching in the liveness index can find it.
                if obj is not None:
                    obj_name = getattr(obj, 'name', None)
                    if isinstance(obj_name, str) and obj_name:
                        self._add(obj_name + '__' + method_name)
            self._walk(obj)
            self._walk(getattr(node, 'arguments', None))
            self._walk(getattr(node, 'args', None))
            return

        # ── MemberAccess / StructFieldAccess ──────────────────────────────
        if cls in ('MemberAccess', 'StructFieldAccess'):
            self._walk(getattr(node, 'obj', None))
            self._walk(getattr(node, 'object', None))
            self._walk(getattr(node, 'arguments', None))
            self._walk(getattr(node, 'args', None))
            return

        # ── TypeSpec / TypeSystem ─────────────────────────────────────────
        if cls in ('TypeSpec', 'TypeSystem'):
            type_name = getattr(node, 'name', None)
            if isinstance(type_name, str):
                self._add(type_name)
            self._walk_all_fields(node)
            return

        # ── Generic dataclass / AST object ───────────────────────────────
        if hasattr(node, '__dataclass_fields__'):
            self._walk_all_fields(node)
            return

        # ── Fallback ──────────────────────────────────────────────────────
        if hasattr(node, '__dict__'):
            for v in vars(node).values():
                self._walk(v)

    def _walk_all_fields(self, node: Any) -> None:
        if hasattr(node, '__dataclass_fields__'):
            for fname in node.__dataclass_fields__:
                self._walk(getattr(node, fname, None))
        elif hasattr(node, '__dict__'):
            for v in vars(node).values():
                self._walk(v)


def _collect_refs(node: Any) -> Set[str]:
    c = _RefCollector()
    c.collect(node)
    return c.refs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_str_name(node: Any) -> bool:
    return isinstance(getattr(node, 'name', None), str)


def _func_is_entry_point(func: Any) -> bool:
    name = getattr(func, 'name', '')
    if not isinstance(name, str):
        return False
    if getattr(func, 'no_mangle', False):
        return True
    if getattr(func, 'is_extern', False):
        return True
    if getattr(func, 'is_prototype', False):
        return True
    base = name.split('::')[-1] if '::' in name else name
    base = base.rsplit('__', 1)[-1] if '__' in base else base
    return base in _ALWAYS_KEEP


# ---------------------------------------------------------------------------
# Index all namespace functions under ALL suffix variants of mangled name
# ---------------------------------------------------------------------------

def _index_namespace_functions(program) -> Dict[str, List[Any]]:
    """
    Index every namespace FunctionDef under all suffix variants of its
    fully-qualified mangled name so that partial-qualification call sites
    still hit the index.

    e.g. a function  compare_ignore_case  inside  standard::strings::helpers
    is indexed under:
        'standard__strings__helpers__compare_ignore_case'
        'strings__helpers__compare_ignore_case'
        'helpers__compare_ignore_case'
        'compare_ignore_case'
    """
    from fast import NamespaceDef, NamespaceDefStatement, FunctionDef

    index: Dict[str, List[Any]] = {}

    def _index_ns(ns: Any, full_prefix: str) -> None:
        ns_name = getattr(ns, 'name', '') or ''
        cur_prefix = (full_prefix + '__' + ns_name) if full_prefix else ns_name

        for func in getattr(ns, 'functions', []):
            if not isinstance(func, FunctionDef) or not _is_str_name(func):
                continue
            full_mangled = (cur_prefix + '__' + func.name) if cur_prefix else func.name
            for variant in _all_suffixes(full_mangled):
                if variant:
                    index.setdefault(variant, []).append(func)

        for nested in getattr(ns, 'nested_namespaces', []):
            _index_ns(nested, cur_prefix)

    for stmt in program.statements:
        ns = None
        if isinstance(stmt, NamespaceDef):
            ns = stmt
        elif isinstance(stmt, NamespaceDefStatement):
            ns = getattr(stmt, 'namespace_def', None)
        if ns is not None:
            _index_ns(ns, '')

    return index


# ---------------------------------------------------------------------------
# Fixed-point liveness closure
# ---------------------------------------------------------------------------

def _compute_live_functions(program, ns_func_index: Dict[str, List[Any]],
                             used_ns_prefixes: set,
                             verbose: bool = False) -> Set[str]:
    from fast import NamespaceDef, NamespaceDefStatement

    from fast import ObjectDef

    # Step 1: Seed from all non-namespace top-level code.
    seed: Set[str] = set()
    for stmt in program.statements:
        if isinstance(stmt, (NamespaceDef, NamespaceDefStatement)):
            continue
        seed |= _collect_refs(stmt)

    # Step 2: Seed entry points.
    for name, funcs in ns_func_index.items():
        for func in funcs:
            if _func_is_entry_point(func):
                seed.add(name)

    # Step 3: Object methods are NOT pre-seeded into the liveness set.
    #
    # Object methods are only reachable via explicit call sites in live code —
    # the fixed-point expansion in Step 4 discovers them naturally when walking
    # the bodies of live namespace functions.
    #
    # Pre-seeding method names caused a cascade: bare names like 'split_lines'
    # and 'count_lines' collide with same-named namespace-level functions in
    # ns_func_index, marking those functions live and pulling in all their
    # callees even when the methods were never called from user code.
    #
    # Special methods (__init__, __exit__, __copy__, __move__) for objects in
    # used namespaces are handled conservatively in _prune_namespace: they are
    # preserved whenever the object has any live regular method.


    # Step 3b: Collect object methods that are directly live (their mangled name
    # variant appears in seed) so we can walk their bodies in Step 5.
    # We build a map: live_method_name_variant -> [ObjectMethod, ...] across all
    # namespaces.  This is separate from ns_func_index (which is functions only).
    from fast import NamespaceDef, NamespaceDefStatement, ObjectDef

    obj_method_index: Dict[str, List[Any]] = {}

    def _index_obj_methods(ns: Any, full_prefix: str) -> None:
        ns_name = getattr(ns, 'name', '') or ''
        cur_prefix = (full_prefix + '__' + ns_name) if full_prefix else ns_name
        for obj in getattr(ns, 'objects', []):
            if not isinstance(obj, ObjectDef):
                continue
            obj_name = getattr(obj, 'name', '') or ''
            for method in getattr(obj, 'methods', []):
                method_name = getattr(method, 'name', None)
                if not isinstance(method_name, str):
                    continue
                full_method = (cur_prefix + '__' + obj_name + '__' + method_name
                               if cur_prefix else obj_name + '__' + method_name)
                for variant in _all_suffixes(full_method):
                    if variant:
                        obj_method_index.setdefault(variant, []).append(method)
        for nested in getattr(ns, 'nested_namespaces', []):
            _index_obj_methods(nested, cur_prefix)

    for stmt in program.statements:
        ns = None
        if isinstance(stmt, NamespaceDef):
            ns = stmt
        elif isinstance(stmt, NamespaceDefStatement):
            ns = getattr(stmt, 'namespace_def', None)
        if ns is not None:
            _index_obj_methods(ns, '')

    # Step 4: Fixed-point expansion over namespace functions ONLY.
    # Object methods are NOT included in this expansion — their bare names
    # (e.g. 'println', 'len') collide with namespace function names and would
    # incorrectly mark object methods live just because a namespace function
    # of the same name is reachable.
    #
    # Object method liveness is determined entirely by the pruner: a method is
    # live only if its fully-qualified  cur_prefix__ObjName__methodName  variant
    # (or a suffix of it) appears in the live set — which only happens when
    # _RefCollector sees an explicit  TypeName.__init  or  obj.method()  call
    # site in live code and registers the dot→dunder form.
    live: Set[str] = set()
    frontier: Set[str] = seed

    while frontier:
        new_frontier: Set[str] = set()
        for name in frontier:
            if name in live:
                continue
            live.add(name)
            funcs = ns_func_index.get(name)
            if funcs:
                for func in funcs:
                    for ref in _collect_refs(func):
                        if ref not in live:
                            new_frontier.add(ref)
        frontier = new_frontier

    return live


# ---------------------------------------------------------------------------
# Prune dead functions from a namespace (mutates in place)
# ---------------------------------------------------------------------------

def _ns_is_used(full_prefix: str, used_ns_prefixes: set) -> bool:
    """True if the namespace is equal to or deeper than any used:: path."""
    for used in used_ns_prefixes:
        if full_prefix == used or full_prefix.startswith(used + '__'):
            return True
    return False


def _prune_namespace(ns_node: Any, live: Set[str], full_prefix: str,
                     verbose: bool, used_ns_prefixes: set) -> int:
    from fast import FunctionDef, ObjectDef

    eliminated = 0
    ns_name = getattr(ns_node, 'name', '') or ''
    cur_prefix = (full_prefix + '__' + ns_name) if full_prefix else ns_name

    # Prune dead functions
    if hasattr(ns_node, 'functions'):
        kept = []
        for func in ns_node.functions:
            if not isinstance(func, FunctionDef) or not _is_str_name(func):
                kept.append(func)
                continue

            full_mangled = (cur_prefix + '__' + func.name) if cur_prefix else func.name
            is_live = _func_is_entry_point(func) or any(
                v in live for v in _all_suffixes(full_mangled)
            )

            if is_live:
                kept.append(func)
            else:
                eliminated += 1
                if verbose:
                    print(f"[DCE] Eliminated unreferenced FunctionDef "
                          f"(in namespace '{ns_name}'): '{func.name}'",
                          file=sys.stdout)
        ns_node.functions = kept

    # Prune dead methods from ObjectDefs, then drop entirely-dead objects.
    #
    # Granularity matters: an object can be *partially* live — e.g. string's
    # __init__ is called by println, so the object must stay, but icompare/
    # contains/split_lines etc. are never called and their callees may have
    # already been eliminated.  If we kept those dead methods, codegen would
    # crash trying to emit a call to a function that no longer exists.
    #
    # Strategy:
    #   1. For each method, check liveness under  cur_prefix__ObjName__method.
    #   2. Drop dead methods from obj.methods in place.
    #   3. If ALL methods were dead, drop the whole ObjectDef too.
    #
    # Special methods (__init__, __exit__, __copy__, __move__) are kept as long
    # as the object itself is referenced anywhere, because codegen may emit
    # implicit calls to them.
    # __exit__, __copy__, __move__ are kept implicitly when the object is live
    # (codegen may emit them without explicit call sites).
    # __init__ is NOT here — it appears explicitly as  TypeName.__init  in
    # construction FunctionCall nodes, so _add() will register it as a regular
    # ref and it is subject to normal per-method liveness.
    _ALWAYS_KEEP_METHODS: frozenset = frozenset({
        '__exit', '__copy', '__move',
    })

    if hasattr(ns_node, 'objects'):
        kept_objs = []
        for obj in ns_node.objects:
            if not isinstance(obj, ObjectDef):
                kept_objs.append(obj)
                continue

            obj_name = getattr(obj, 'name', '') or ''

            # First pass: determine which methods are live.
            kept_methods = []
            any_regular_method_live = False
            for method in getattr(obj, 'methods', []):
                method_name = getattr(method, 'name', None)
                if not isinstance(method_name, str):
                    kept_methods.append(method)
                    continue

                full_method = (cur_prefix + '__' + obj_name + '__' + method_name
                               if cur_prefix else obj_name + '__' + method_name)
                # Only consider suffixes that still contain the object name — bare
                # method name suffixes (e.g. 'println', 'len') must NOT be used
                # because they collide with same-named namespace functions in the
                # live set.  A method is only live if something explicitly referenced
                # it in qualified form (e.g. 'string____init', 'string__println').
                obj_anchor = obj_name + '__' + method_name
                method_live = any(
                    v in live
                    for v in _all_suffixes(full_method)
                    if obj_anchor in v or v == full_method
                )

                if method_live:
                    kept_methods.append(method)
                    if method_name not in _ALWAYS_KEEP_METHODS:
                        any_regular_method_live = True
                elif method_name in _ALWAYS_KEEP_METHODS:
                    # Defer: keep special methods only if the object is otherwise live.
                    kept_methods.append(('__defer_special__', method))
                else:
                    eliminated += 1
                    if verbose:
                        print(f"[DCE] Eliminated unreferenced ObjectMethod "
                              f"(object '{obj_name}' in namespace '{ns_name}'): "
                              f"'{method_name}'",
                              file=sys.stdout)

            # Resolve deferred special methods.
            # The object is live if any regular (non-special) method is live.
            # Special methods (__init__, __exit__, etc.) are kept automatically
            # whenever the object itself is live, since codegen may emit implicit
            # calls to them. If NO regular method is live, the whole object is dead
            # and special methods are dropped along with it.
            obj_ref_live = any_regular_method_live

            resolved_methods = []
            for entry in kept_methods:
                if isinstance(entry, tuple) and entry[0] == '__defer_special__':
                    method = entry[1]
                    if obj_ref_live:
                        resolved_methods.append(method)
                    else:
                        eliminated += 1
                        if verbose:
                            mname = getattr(method, 'name', '?')
                            print(f"[DCE] Eliminated unreferenced ObjectMethod "
                                  f"(object '{obj_name}' in namespace '{ns_name}'): "
                                  f"'{mname}'",
                                  file=sys.stdout)
                else:
                    resolved_methods.append(entry)

            if resolved_methods:
                obj.methods = resolved_methods
                kept_objs.append(obj)
            else:
                eliminated += 1
                if verbose:
                    print(f"[DCE] Eliminated unreferenced ObjectDef "
                          f"(in namespace '{ns_name}'): '{obj_name}'",
                          file=sys.stdout)

        ns_node.objects = kept_objs

    for nested in getattr(ns_node, 'nested_namespaces', []):
        eliminated += _prune_namespace(nested, live, cur_prefix, verbose, used_ns_prefixes)

    return eliminated


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def eliminate(program, *, verbose: bool = False):
    """
    Run dead code elimination on a parsed Flux *Program* AST node.

    Only namespace-level functions are eliminated.  All top-level structs,
    objects, enums, traits, and variables are preserved unconditionally.

    Parameters
    ----------
    program : fast.Program
        Root AST node from FluxParser.parse().
    verbose : bool
        Print a line for each eliminated declaration when True.

    Returns
    -------
    fast.Program
        The same node, mutated in place.
    """
    from fast import NamespaceDef, NamespaceDefStatement

    if verbose:
        print(f"[DCE] Starting dead code elimination "
              f"({len(program.statements)} top-level statement(s))...",
              file=sys.stdout)

    ns_func_index = _index_namespace_functions(program)
    unique_funcs = len(set(id(f) for funcs in ns_func_index.values() for f in funcs))

    if verbose:
        print(f"[DCE] Indexed {unique_funcs} unique namespace function(s) "
              f"under {len(ns_func_index)} name variant(s).",
              file=sys.stdout)

    from fast import UsingStatement
    used_ns_prefixes: set = set()
    for stmt in program.statements:
        if isinstance(stmt, UsingStatement):
            used_ns_prefixes.add(stmt.namespace_path.replace('::', '__'))

    live = _compute_live_functions(program, ns_func_index, used_ns_prefixes, verbose=verbose)

    if verbose:
        print(f"[DCE] Live set: {len(live)} name variant(s).", file=sys.stdout)

    total_eliminated = 0
    for stmt in program.statements:
        ns = None
        if isinstance(stmt, NamespaceDef):
            ns = stmt
        elif isinstance(stmt, NamespaceDefStatement):
            ns = getattr(stmt, 'namespace_def', None)
        if ns is not None:
            total_eliminated += _prune_namespace(ns, live, '', verbose, used_ns_prefixes)

    if verbose:
        if total_eliminated == 0:
            print("[DCE] No dead namespace functions found.", file=sys.stdout)
        else:
            print(f"[DCE] Eliminated {total_eliminated} unreferenced namespace "
                  f"function(s).", file=sys.stdout)
        print(f"[DCE] Done. {len(program.statements)} top-level statement(s) remain.",
              file=sys.stdout)

    return program