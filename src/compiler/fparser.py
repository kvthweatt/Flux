#!/usr/bin/env python3
"""
Flux Language Parser

Copyright (C) 2026 Karac Thweatt

Contributors:

    Piotr Bednarski

A recursive descent parser for the Flux programming language.
Converts tokens from the lexer into an Abstract Syntax Tree (AST).

Usage:
    python3 parser.py file.fx          # Parse and show AST
    python3 parser.py file.fx -v       # Verbose parsing with debug info
    python3 parser.py file.fx -a       # Show AST structure
"""

import os
from pathlib import Path
from typing import Set, Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
import sys
from fconfig import config as _flux_config, get_byte_width as _get_byte_width
from flexer import FluxLexer
from fpreprocess import *

# Import preprocessor and lexer
sys.path.insert(0, str(Path(__file__).parent))
try:
    from fpreprocess import FXPreprocessor
    from flexer import FluxLexer
except ImportError:
    # If running from different location, try alternate paths
    try:
        from .fpreprocess import FXPreprocessor
        from .flexer import FluxLexer
    except ImportError:
        raise ImportError("Could not import FXPreprocessor or FluxLexer")


import sys
from contextlib import contextmanager
from typing import List, Optional, Union, Any
from flexer import FluxLexer, TokenType, Token
from fast import *

# Calling-convention tokens that may appear in place of 'def'
_CALLING_CONV_TOKENS = {
    TokenType.CDECL,
    TokenType.STDCALL,
    TokenType.FASTCALL,
    TokenType.THISCALL,
    TokenType.VECTORCALL,
}

# Map calling-convention TokenType -> Flux keyword string used by FunctionDef._CALLING_CONV_MAP
_CALLING_CONV_TOKEN_TO_STR = {
    TokenType.CDECL:      'cdecl',
    TokenType.STDCALL:    'stdcall',
    TokenType.FASTCALL:   'fastcall',
    TokenType.THISCALL:   'thiscall',
    TokenType.VECTORCALL: 'vectorcall',
}

_TOKEN_SYMBOL_MAP = {
    # Operators
    TokenType.PLUS:               '+',
    TokenType.MINUS:              '-',
    TokenType.MULTIPLY:           '*',
    TokenType.DIVIDE:             '/',
    TokenType.MODULO:             '%',
    TokenType.LESS_THAN:          '<',
    TokenType.GREATER_THAN:       '>',
    TokenType.ASSIGN:             '=',
    TokenType.LOGICAL_OR:         '|',
    TokenType.LOGICAL_AND:        '&',
    TokenType.BITXOR_OP:          '^',
    TokenType.NOT:                '!',
    TokenType.QUESTION:           '?',
    TokenType.ADDRESS_OF:         '@',
    TokenType.TIE:                '~',
    TokenType.INCREMENT:          '++',
    TokenType.DECREMENT:          '--',
    TokenType.EQUAL:              '==',
    TokenType.NOT_EQUAL:          '!=',
    TokenType.LESS_EQUAL:         '<=',
    TokenType.GREATER_EQUAL:      '>=',
    TokenType.NAND_OP:            '!&',
    TokenType.NOR_OP:             '!|',
    TokenType.XOR_OP:             '^|',
    TokenType.BITSHIFT_LEFT:      '<<',
    TokenType.BITSHIFT_RIGHT:     '>>',
    TokenType.BITNAND_OP:         '`!&',
    TokenType.BITNOR_OP:          '`!|',
    TokenType.BITXNAND:           '`^|!&',
    TokenType.BITXNOR:            '`^|!|',
    # Punctuation / delimiters
    TokenType.LEFT_PAREN:         '(',
    TokenType.RIGHT_PAREN:        ')',
    TokenType.LEFT_BRACE:         '{',
    TokenType.RIGHT_BRACE:        '}',
    TokenType.LEFT_BRACKET:       '[',
    TokenType.RIGHT_BRACKET:      ']',
    TokenType.SEMICOLON:          ';',
    TokenType.COLON:              ':',
    TokenType.COMMA:              ',',
    TokenType.DOT:                '.',
    TokenType.RETURN_ARROW:       '->',
    TokenType.SCOPE:              '::',
    TokenType.BACKSLASH:          '\\',
    TokenType.STRINGIFY:          '$',
}

_SYMBOL_MANGLE = {
    '%': 'pct',  '+': 'plus', '-': 'minus', '*': 'mul',
    '/': 'div',  '<': 'lt',   '>': 'gt',    '=': 'eq',
    '&': 'amp',  '|': 'pipe', '^': 'xor',   '!': 'not',
    '?': 'qst',  '@': 'at',   '~': 'tilde', '\\': 'bslash',
    '$': 'dol',
}

# Tokens that can begin a primary expression.  Used by binary-level parsers to
# detect a spurious token or missing operator mid-expression rather than letting
# the error bubble up as a misleading "expected ';'" at statement level.
# LEFT_BRACE is excluded - it legitimately follows expressions in statement contexts.
# COLON is excluded - it appears in ternary and for-in contexts above expression level.
_EXPRESSION_START_TOKENS = {
    TokenType.IDENTIFIER,
    TokenType.SINT_LITERAL,
    TokenType.UINT_LITERAL,
    TokenType.SLONG_LITERAL,
    TokenType.ULONG_LITERAL,
    TokenType.FLOAT,
    TokenType.DOUBLE,
    TokenType.CHAR,
    TokenType.STRING_LITERAL,
    TokenType.F_STRING,
    TokenType.G_STRING,
    TokenType.I_STRING,
    TokenType.TRUE,
    TokenType.FALSE,
    TokenType.VOID,
    TokenType.THIS,
    TokenType.NO_INIT,
    TokenType.LEFT_PAREN,
    TokenType.LEFT_BRACKET,
    TokenType.ELLIPSIS,
}

from ferrors import FluxParseError, FluxSyntaxError, FluxWarning, ParseError, emit_warning

def _resolve_inheritance(child_name, base_names, child_members, child_methods, parsed_objects, error_fn):
    """
    Resolve and merge inheritance for an object definition.

    Returns (merged_members, merged_methods) where:
    - merged_members: grandparent ... parent (L-to-R) ... child members
    - merged_methods: child methods + deduplicated inherited methods
                      (excluding __init, __exit, __expr from parents)

    Diamond inheritance is handled by tagging each member with its original
    defining object. Members that trace back to the same origin are deduplicated
    silently; members with the same name from different origins are an error.
    """

    # ------------------------------------------------------------------ #
    # 1. Collect flattened members from a parent chain (DFS, parents first)
    # ------------------------------------------------------------------ #
    def collect_members(obj_name, visited_for_cycle):
        """Return list of (StructMember, origin_object_name) in declaration order."""
        if obj_name in visited_for_cycle:
            return []
        visited_for_cycle = visited_for_cycle | {obj_name}

        if obj_name not in parsed_objects:
            error_fn(f"Inheritance error: '{obj_name}' must be fully defined before "
                     f"'{child_name}' can inherit from it")

        obj = parsed_objects[obj_name]
        result = []

        # Recurse into this object's own parents first
        for base in obj.base_objects:
            result.extend(collect_members(base, visited_for_cycle))

        # Then this object's own members (private members not inherited,
        # unless they are friend-private for the child being resolved)
        for m in obj.members:
            if getattr(m, 'is_private', False):
                # Friend-private: pass through only to the named friend
                if getattr(m, 'friend_of', None) == child_name:
                    result.append((m, obj_name))
                # Plain private: never inherited
            else:
                result.append((m, obj_name))

        return result

    # ------------------------------------------------------------------ #
    # 2. Collect flattened methods from a parent chain
    # ------------------------------------------------------------------ #
    _NEVER_INHERITED = {'__init', '__exit', '__expr'}

    def collect_methods(obj_name, visited_for_cycle):
        """Return list of FunctionDef from the parent chain, excluding never-inherited."""
        if obj_name in visited_for_cycle:
            return []
        visited_for_cycle = visited_for_cycle | {obj_name}

        if obj_name not in parsed_objects:
            # error already raised from collect_members; just return empty
            return []

        obj = parsed_objects[obj_name]
        result = []

        for base in obj.base_objects:
            result.extend(collect_methods(base, visited_for_cycle))

        for m in obj.methods:
            if isinstance(m, FunctionDef) and m.name not in _NEVER_INHERITED:
                if getattr(m, 'is_private', False):
                    # Friend-private: pass through only to the named friend
                    if getattr(m, 'friend_of', None) == child_name:
                        result.append(m)
                    # Plain private: never inherited
                else:
                    result.append(m)

        return result

    # ------------------------------------------------------------------ #
    # 3. Build merged member list
    # ------------------------------------------------------------------ #
    # Accumulate (member, origin) pairs from all parents in order
    inherited_member_pairs = []
    for base in base_names:
        inherited_member_pairs.extend(collect_members(base, set()))

    # Deduplicate by member name, tracking origin for diamond detection
    seen_members = {}   # member_name -> origin_object_name
    dedup_inherited = []
    for (m, origin) in inherited_member_pairs:
        if m.name in seen_members:
            prev_origin = seen_members[m.name]
            if prev_origin != origin:
                error_fn(
                    f"Inheritance conflict: member '{m.name}' is defined in both "
                    f"'{prev_origin}' and '{origin}', inherited by '{child_name}'"
                )
            # Same origin (diamond) - silently skip duplicate
        else:
            seen_members[m.name] = origin
            dedup_inherited.append(m)

    # Child members must not shadow any inherited member
    child_member_names = {m.name for m in child_members}
    for m in dedup_inherited:
        if m.name in child_member_names:
            error_fn(
                f"Inheritance conflict: member '{m.name}' is defined in both "
                f"a parent of '{child_name}' and '{child_name}' itself"
            )

    merged_members = dedup_inherited + child_members

    # ------------------------------------------------------------------ #
    # 4. Build merged method list
    # ------------------------------------------------------------------ #
    def sig_key(method):
        """(name, tuple of param type reprs) - mirrors the mangler's key."""
        param_types = tuple(
            repr(p.type_spec) for p in method.parameters if p.name != 'this'
        )
        return (method.name, param_types)

    # Gather all inherited methods
    all_inherited = []
    for base in base_names:
        all_inherited.extend(collect_methods(base, set()))

    # Build sig_key -> list of FunctionDef (possibly from different parents)
    inherited_map = {}
    for m in all_inherited:
        k = sig_key(m)
        if k not in inherited_map:
            inherited_map[k] = []
        # Deduplicate by object identity (diamond - same FunctionDef object)
        if not any(existing is m for existing in inherited_map[k]):
            inherited_map[k].append(m)

    # Check for conflicts and build the final inherited set.
    # Rules:
    #   - Child method marked with '+' (_is_override=True) -> child always wins.
    #   - Child method with a non-empty body (no '+') -> child wins.
    #   - Child method with an empty body (no '+') -> parent wins; stub is dropped.
    def _has_body(m):
        return isinstance(m, FunctionDef) and m.body is not None and bool(m.body.statements)

    def _is_explicit_override(m):
        return isinstance(m, FunctionDef) and getattr(m, '_is_override', False)

    def _is_no_override(m):
        return isinstance(m, FunctionDef) and getattr(m, '_no_override', False)

    child_override_keys = {sig_key(m) for m in child_methods
                           if _is_explicit_override(m) or _has_body(m)}

    # Build a map of sig_key -> method for no-override enforcement
    inherited_no_override_keys = {}
    for candidates in inherited_map.values():
        for m in candidates:
            if _is_no_override(m):
                inherited_no_override_keys[sig_key(m)] = m

    # Error if child tries to win a signature the parent sealed with !+
    for k in child_override_keys:
        if k in inherited_no_override_keys:
            method_name = k[0]
            sig_str = ', '.join(k[1]) if k[1] else ''
            error_fn(
                f"Override error: method '{method_name}({sig_str})' is marked no-override "
                f"in a parent of '{child_name}'"
            )

    final_inherited = []
    for k, candidates in inherited_map.items():
        # Child wins for this signature (explicit override or non-empty body)
        if k in child_override_keys:
            continue

        if len(candidates) == 1:
            final_inherited.append(candidates[0])
        else:
            # Multiple different FunctionDef objects for same signature = conflict
            conflict_sources = []
            for m in candidates:
                # Walk parsed_objects to find which object defined this method
                for oname, odef in parsed_objects.items():
                    if any(om is m for om in odef.methods):
                        conflict_sources.append(oname)
                        break
                else:
                    conflict_sources.append('?')

            method_name = k[0]
            sig_str = ', '.join(k[1]) if k[1] else ''
            error_fn(
                f"Inheritance conflict: method '{method_name}({sig_str})' has different "
                f"implementations in '{conflict_sources[0]}' and '{conflict_sources[1]}'. "
                f"Object '{child_name}' must override it."
            )

    # Build the set of signatures that were actually inherited (parent won)
    inherited_sig_keys = {sig_key(m) for m in final_inherited}

    # Keep child methods that either:
    #   - are explicitly marked '+' (_is_override), OR
    #   - have a non-empty body (real override), OR
    #   - are empty but have NO inherited counterpart (standalone empty method on child)
    filtered_child_methods = [
        m for m in child_methods
        if not isinstance(m, FunctionDef)
           or _is_explicit_override(m)
           or _has_body(m)
           or sig_key(m) not in inherited_sig_keys
    ]

    merged_methods = filtered_child_methods + final_inherited
    return merged_members, merged_methods


@dataclass
class TemplateEntry:
    kind: str                          # 'function' | 'struct' | 'object' | 'operator'
    params: List[str]                  # template parameter names in declaration order
    node: object                       # the template AST node (FunctionDef, StructDef, etc.)
    constraints: dict                  # param_name -> [allowed_type_spec_strings]
    relational_constraints: list       # relational constraint entries
    defaults: dict                     # param_name -> TypeSystem default
    no_default: set                    # param names that must be supplied explicitly
    emitted: set                       # mangled names already instantiated


class TemplateRegistry:
    def __init__(self):
        self._entries: dict = {}

    def register(self, name: str, kind: str, params: list, node: object,
                 constraints=None, relational=None, defaults=None, no_default=None) -> None:
        existing = self._entries.get(name)
        if existing is not None and existing.kind == kind:
            # Overwrite in place so that aliases sharing this entry pick up the new node.
            existing.params = list(params)
            existing.node = node
            if constraints:
                existing.constraints = constraints
            if relational:
                existing.relational_constraints = relational
            if defaults:
                existing.defaults = defaults
            if no_default:
                existing.no_default = no_default
            return
        self._entries[name] = TemplateEntry(
            kind=kind,
            params=list(params),
            node=node,
            constraints=constraints or {},
            relational_constraints=relational or [],
            defaults=defaults or {},
            no_default=no_default or set(),
            emitted=set(),
        )

    def lookup(self, name: str):
        return self._entries.get(name)

    def has(self, name: str) -> bool:
        return name in self._entries

    def register_alias(self, alias: str, original: str) -> None:
        if original in self._entries:
            self._entries[alias] = self._entries[original]

    def mark_emitted(self, name: str, mangled: str) -> None:
        entry = self._entries.get(name)
        if entry is not None:
            entry.emitted.add(mangled)

    def is_emitted(self, name: str, mangled: str) -> bool:
        entry = self._entries.get(name)
        return entry is not None and mangled in entry.emitted

    def all_of_kind(self, kind: str) -> dict:
        return {k: v for k, v in self._entries.items() if v.kind == kind}

    def keys(self):
        return self._entries.keys()

    def items(self):
        return self._entries.items()

    def __contains__(self, name):
        return name in self._entries

    def __iter__(self):
        return iter(self._entries)

    def __bool__(self):
        return bool(self._entries)


class FluxParser:
    def __init__(self, tokens: List[Token], default_byte_width: int = 8, source_lines: Optional[List[str]] = None):
        self.tokens = tokens
        self.position = 0
        self.current_token = self.tokens[0] if tokens else None
        self.parse_errors = []  # Track parse errors
        self._source_lines: Optional[List[str]] = source_lines  # for rich error display
        self._processing_imports = set()
        self.symbol_table = SymbolTable()
        self._preprocessor_macros = []
        self._macros = {}  # name -> macroDef, populated as macro definitions are parsed
        self._namespace_stack = []  # Track current namespace path for symbol registration
        self._object_init_params = {}  # object_name -> __init parameter count (excluding 'this')
        self._templates = TemplateRegistry()  # all template state (functions/structs/objects/operators)
        self._pending_template_instances = []  # (kind, node) tuples: 'struct' | 'object' | 'function'
        self._parsed_objects = {}  # object_name -> ObjectDef AST node
        self._parsed_traits = {}   # trait_name -> TraitDef AST node
        self._custom_operators: Dict[str, str] = {}  # symbol string -> base function name (binary)
        self._custom_prefix_ops: Dict[str, str] = {}   # symbol string -> func_name (prefix unary)
        self._custom_postfix_ops: Dict[str, str] = {}  # symbol string -> func_name (postfix unary)
        self._custom_ternary_ops: Dict[tuple, str] = {}   # (left_sym, right_sym) -> func_name (ternary)
        self._custom_circumfix_ops: Dict[tuple, str] = {} # (left_sym, right_sym) -> func_name (circumfix)
        self._active_template_params: set = set()  # template param names in scope during current def/struct parse
        self._contracts: Dict[str, Block] = {}  # name -> Block of statements to inject
        self._contract_bindings: Dict[str, dict] = {}  # name -> binding spec dict from # binding { ... }
        self._constras: dict = {}  # name -> (params: List[str], relations: list)
        self._function_depth = 0  # Tracks nesting depth; nested function defs are illegal
        self._loop_depth = 0      # Tracks nesting depth of for/while/do-while loops
        self._in_for_init = False # True while parsing the init clause of a for(...) header
        self._in_trait = 0        # Tracks nesting depth inside trait bodies (prototypes only)
        self._default_byte_width = default_byte_width if default_byte_width is not None else _get_byte_width(_flux_config)
        self._comptime_strings: Dict[str, str] = {}  # var_name -> string value, for ~$ codify splicing
        self._in_comptime: int = 0  # Nesting depth inside comptime blocks
        # Populated by from_file after preprocessing; maps global line index (0-based) -> (filename, local_line 1-based)
        self._line_map: List[tuple] = []
        # Ditto-in-args context.
        # _last_call_expr       -- FunctionCall from the most recent call statement.
        # _last_noncall_src     -- raw source text of the most recent non-call expression
        #                          statement that cleared _last_call_expr; shown as the
        #                          preceding context line in the ditto error message.
        self._last_call_expr: Optional['FunctionCall'] = None
        self._last_noncall_src: str = ''
        # Ditto-as-statement context.
        # Holds the concrete AST node of the most recently parsed statement so
        # that a bare `#";` can deep-copy and re-insert it.  Updated by the
        # statement-loop callers (parse() and block()) after each call to
        # statement().  When `#";` itself resolves, it stores the copy back here
        # so that chained `#";` repeat the original, not a meta-ditto node.
        self._last_stmt: Optional[Statement] = None
        # Set by function_def/struct_def/object_def when they register a template so
        # namespace_def can read the bare name without diffing the registry.
        self._last_template_registered: Optional[str] = None
        # Names of template objects currently being parsed (pre-registration forward decls).
        # Allows type_spec() to recognise self-referential return types like Tensor<T>*
        # inside method signatures without a sentinel ObjectDef in the registry.
        self._template_object_forward_decls: set = set()


    @contextmanager
    def _template_scope(self, params: List[str]):
        prev = self._active_template_params
        self._active_template_params = set(params) if params else prev
        try:
            yield
        finally:
            self._active_template_params = prev

    def resolve_source_location(self, global_line: int) -> tuple:
        """
        Translate a 1-based global (merged) line number to (filename, local_line).
        Falls back to (None, global_line) when no map is available or the line is
        out of range (e.g. it came from an import that produced no output lines).
        """
        if self._line_map and 1 <= global_line <= len(self._line_map):
            return self._line_map[global_line - 1]
        return (None, global_line)

    @classmethod
    def from_file(self, source_file: str, compiler_macros: Optional[Dict[str, str]] = None, verbose: bool = False):
        """
        Create a parser by preprocessing and lexing a source file.
        """
        # Step 1: Preprocess
        preprocessor = FXPreprocessor(source_file, compiler_constants=compiler_macros or {})
        preprocessed_source = preprocessor.process()

        # Step 2: Lex
        print(f"[INFO] [lexer] ► Lexical analysis")
        lexer = FluxLexer(preprocessed_source)
        tokens = lexer.tokenize()

        # Step 3: Create parser
        print(f"[INFO] [parser] ► Parsing")
        source_lines = preprocessed_source.splitlines(keepends=True)
        parser = self(tokens, source_lines=source_lines)
        print(f"[INFO] [parser] ► AST generated.")

        # Expose final macro set to parser/codegen if needed
        parser._preprocessor_macros = dict(preprocessor.constants)

        # Expose line map so error reporting can translate global -> (file, local_line)
        # line_map[i] = (filename, local_line_number) for output_lines[i] (0-based)
        # The merged source has one extra '\n' join between each line, so global line N
        # (1-based) corresponds to line_map[N-1] when N <= len(line_map).
        parser._line_map = preprocessor.line_map

        return parser

    @contextmanager
    def _lookahead(self):
        saved_pos = self.position
        saved_token = self.current_token
        try:
            yield
        finally:
            self.position = saved_pos
            self.current_token = saved_token
    
    def error(self, message: str, expected_type=None, prev_token=None, annotation: str = "", prev_source_line: str = "") -> None:
        """Raise a parse error with current token context"""
        raise FluxParseError(message, self.current_token, self._source_lines, expected_type, prev_token, self._line_map, annotation, prev_source_line=prev_source_line)

    def warn(self, message: str) -> None:
        """Emit a non-fatal compiler warning to stderr with source location context."""
        emit_warning(message, self.current_token, self._source_lines, self._line_map)

    def advance(self) -> Token:
        """Move to the next token"""
        if self.position < len(self.tokens) - 1:
            self.position += 1
            self.current_token = self.tokens[self.position]
        return self.current_token
    
    def peek(self, offset: int = 1) -> Optional[Token]:
        """Look ahead at the next token without consuming it"""
        pos = self.position + offset
        if pos < len(self.tokens):
            return self.tokens[pos]
        return None
    
    def expect(self, *token_types: TokenType) -> bool:
        """Check if current token matches any of the given types"""
        if self.current_token is None:
            return False
        return self.current_token.type in token_types
    
    # ------------------------------------------------------------------
    # Relational constraint operator helpers
    # ------------------------------------------------------------------
    # All type-algebra operators are sequences of existing tokens.
    # These helpers centralise detection and consumption so every parse
    # site (constra_def, function_def, type_func_def, and their
    # lookahead skippers) stays in sync.
    #
    # Current operator set:
    #   ~=       TIE ASSIGN                       compatible
    #   !~=      NOT TIE ASSIGN                   incompatible
    #   !@       NOT ADDRESS_OF                   no-address-of
    #   !`<      NOT BACKTICK LESS_THAN            no-truncation (independent)
    #   !`<=     NOT BACKTICK LESS_EQUAL           no-truncation (between)
    #   !`>      NOT BACKTICK GREATER_THAN         no-widening (independent)
    #   !`>=     NOT BACKTICK GREATER_EQUAL        no-widening (between)
    # ------------------------------------------------------------------

    def _is_relconstraint_op(self) -> bool:
        """Return True if the current position starts a relational constraint operator."""
        if self.expect(TokenType.TIE) and self.peek(1) and self.peek(1).type == TokenType.ASSIGN:
            return True
        if self.expect(TokenType.NOT):
            p1 = self.peek(1)
            if p1 is None:
                return False
            if p1.type == TokenType.TIE and self.peek(2) and self.peek(2).type == TokenType.ASSIGN:
                return True
            if p1.type == TokenType.ADDRESS_OF:
                return True
            if p1.type == TokenType.MINUS_ASSIGN:
                return True
            if p1.type == TokenType.BACKTICK:
                p2 = self.peek(2)
                if p2 and p2.type in (TokenType.LESS_THAN, TokenType.LESS_EQUAL,
                                      TokenType.GREATER_THAN, TokenType.GREATER_EQUAL):
                    return True
        return False

    def _consume_relconstraint_op(self) -> str:
        """Consume the tokens of the current relational constraint operator and return its string."""
        if self.expect(TokenType.TIE):
            self.consume(TokenType.TIE)
            self.consume(TokenType.ASSIGN)
            return "~="
        self.consume(TokenType.NOT)
        if self.expect(TokenType.TIE):
            self.consume(TokenType.TIE)
            self.consume(TokenType.ASSIGN)
            return "!~="
        if self.expect(TokenType.ADDRESS_OF):
            self.advance()
            return "!@"
        if self.expect(TokenType.MINUS_ASSIGN):
            self.advance()
            return "!-="
        # BACKTICK branch - !`< !`<= !`> !`>=
        self.consume(TokenType.BACKTICK)
        if self.expect(TokenType.LESS_EQUAL):
            self.advance()
            return "!`<="
        elif self.expect(TokenType.LESS_THAN):
            self.advance()
            return "!`<"
        elif self.expect(TokenType.GREATER_EQUAL):
            self.advance()
            return "!`>="
        elif self.expect(TokenType.GREATER_THAN):
            self.advance()
            return "!`>"
        self.error("Unknown constraint operator after '!`'", TokenType.GREATER_THAN)

    def _skip_relconstraint_op(self) -> None:
        """Advance past the tokens of a relational constraint operator (lookahead use)."""
        if self.expect(TokenType.TIE):
            self.advance()  # TIE
            self.advance()  # ASSIGN
            return
        self.advance()  # NOT
        if self.expect(TokenType.TIE):
            self.advance()  # TIE
            self.advance()  # ASSIGN
            return
        if self.expect(TokenType.ADDRESS_OF):
            self.advance()  # ADDRESS_OF
            return
        self.advance()  # BACKTICK
        self.advance()  # LESS_THAN | LESS_EQUAL | GREATER_THAN | GREATER_EQUAL

    def consume(self, expected_type: TokenType, message: str = None) -> Token:
        """Consume a token of the expected type or raise error"""
        if not self.expect(expected_type):
            from ferrors import _TOKEN_SYMBOL_MAP as _tsm
            exp_sym = _tsm.get(expected_type, expected_type.name)
            got_tok = self.current_token
            got_sym = _tsm.get(got_tok.type, got_tok.type.name) if got_tok else 'EOF'
            got_val = f" {got_tok.value}" if got_tok and got_tok.value not in (got_sym, '') else ''
            msg = message or f"Unexpected {got_val.strip() or got_sym}, expected {exp_sym}"
            prev = self.tokens[self.position - 1] if self.position > 0 else None
            self.error(msg, expected_type, prev)
        token = self.current_token
        self.advance()
        return token
    
    def synchronize(self) -> None:
        """Synchronize parser state after an error"""
        self.advance()
        while not self.expect(TokenType.EOF):
            if self.tokens[self.position - 1].type == TokenType.SEMICOLON:
                return
            if self.expect(TokenType.DEF, TokenType.STRUCT, TokenType.OBJECT, 
                         TokenType.NAMESPACE, TokenType.IF, TokenType.WHILE,
                         TokenType.FOR, TokenType.RETURN):
                return
            self.advance()

    # ============ GRAMMAR RULES ============

    # ============ CUSTOM OPERATOR HELPERS ============

    def _tokens_to_op_key(self, token_types: list, token_values: list = None) -> str:
        parts = []
        for i, t in enumerate(token_types):
            if t == TokenType.IDENTIFIER and token_values and token_values[i]:
                parts.append(token_values[i])
            else:
                parts.append(_TOKEN_SYMBOL_MAP[t])
        return ''.join(parts)

    def _mangle_op_symbol(self, symbol: str) -> str:
        parts = self._symbol_to_parts(symbol) or [symbol]
        mangled_parts = []
        for part in parts:
            if all(c in _SYMBOL_MANGLE or c.isalnum() or c == '_' for c in part):
                # Identifier-like part: use directly if all alnum/underscore, else mangle char by char
                if all(c.isalnum() or c == '_' for c in part):
                    mangled_parts.append(part)
                else:
                    mangled_parts.append('_'.join(_SYMBOL_MANGLE.get(c, hex(ord(c))) for c in part))
            else:
                mangled_parts.append('_'.join(_SYMBOL_MANGLE.get(c, hex(ord(c))) for c in part))
        return '_'.join(mangled_parts)

    def _symbol_to_token_types(self, symbol: str) -> list:
        parts = self._symbol_to_parts(symbol)
        if parts is None:
            return None
        result = []
        for part in parts:
            # Check if this part is an identifier (not in any symbol map value)
            if all(part != tok_str for tok_str in _TOKEN_SYMBOL_MAP.values()):
                result.append(TokenType.IDENTIFIER)
            else:
                _REVERSE = {v: k for v, k in ((s, t) for t, s in _TOKEN_SYMBOL_MAP.items())}
                result.append(_REVERSE[part])
        return result

    def _symbol_to_parts(self, symbol: str) -> list:
        # Build reverse map sorted longest-first to match lexer greedy behaviour
        _REVERSE = sorted(_TOKEN_SYMBOL_MAP.items(), key=lambda kv: len(kv[1]), reverse=True)
        result = []
        pos = 0
        while pos < len(symbol):
            matched = False
            for tok_type, tok_str in _REVERSE:
                if symbol[pos:pos+len(tok_str)] == tok_str:
                    result.append(tok_str)
                    pos += len(tok_str)
                    matched = True
                    break
            if not matched:
                # Try to consume an identifier (letters, digits, underscore)
                end = pos
                if end < len(symbol) and (symbol[end].isalpha() or symbol[end] == '_'):
                    while end < len(symbol) and (symbol[end].isalnum() or symbol[end] == '_'):
                        end += 1
                    result.append(symbol[pos:end])
                    pos = end
                else:
                    return None
        return result

    def _match_custom_op(self):
        """
        Greedy longest-match against registered custom operators from current position.
        Returns (symbol_string, token_count) or (None, 0).
        """
        best_symbol = None
        best_length = 0

        for symbol in self._custom_operators:
            candidate_types = self._symbol_to_token_types(symbol)
            if candidate_types is None:
                continue
            n = len(candidate_types)
            if n <= best_length:
                continue
            tokens_match = True
            for i in range(n):
                tok = self.current_token if i == 0 else self.peek(i)
                if tok is None:
                    tokens_match = False
                    break
                if candidate_types[i] == TokenType.IDENTIFIER:
                    # Match identifier tokens by value embedded in the symbol string
                    # Extract the identifier value from the symbol at this position
                    sym_parts = self._symbol_to_parts(symbol)
                    if tok.type != TokenType.IDENTIFIER or tok.value != sym_parts[i]:
                        tokens_match = False
                        break
                elif tok.type != candidate_types[i]:
                    tokens_match = False
                    break
            if tokens_match:
                best_symbol = symbol
                best_length = n

        return best_symbol, best_length

    def _match_custom_unary_op(self, op_table: dict):
        """
        Greedy longest-match against the given custom unary operator table.
        Returns (symbol_string, token_count) or (None, 0).
        """
        best_symbol = None
        best_length = 0

        for symbol in op_table:
            candidate_types = self._symbol_to_token_types(symbol)
            if candidate_types is None:
                continue
            n = len(candidate_types)
            if n <= best_length:
                continue
            tokens_match = True
            for i in range(n):
                tok = self.current_token if i == 0 else self.peek(i)
                if tok is None:
                    tokens_match = False
                    break
                if candidate_types[i] == TokenType.IDENTIFIER:
                    sym_parts = self._symbol_to_parts(symbol)
                    if tok.type != TokenType.IDENTIFIER or tok.value != sym_parts[i]:
                        tokens_match = False
                        break
                elif tok.type != candidate_types[i]:
                    tokens_match = False
                    break
            if tokens_match:
                best_symbol = symbol
                best_length = n

        return best_symbol, best_length

    def operator_def(self) -> FunctionDef:
        """
        operator_def -> 'operator' ('<' template_params '>')? '(' parameter_list ')' '[' op_tokens+ ']' '->' type_spec
                        (':' contract_list)? (';' | block (':' post_contract_list)? ';')
        """
        tok = self.current_token
        # Consume 'operator' keyword token
        self.consume(TokenType.OPERATOR)

        # Parse optional template parameter list: operator<T, K>(...)
        # Use lookahead to confirm all angle-bracket contents are identifiers.
        template_params = []
        if self.expect(TokenType.LESS_THAN):
            with self._lookahead():
                is_template = False
                self.advance()  # consume '<'
                if self.expect(TokenType.IDENTIFIER):
                    self.advance()
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        if not self.expect(TokenType.IDENTIFIER):
                            break
                        self.advance()
                    if self.expect(TokenType.GREATER_THAN):
                        is_template = True
            if is_template:
                self.advance()  # consume '<'
                template_params.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    template_params.append(self.consume(TokenType.IDENTIFIER).value)
                self.consume(TokenType.GREATER_THAN)

        self.consume(TokenType.LEFT_PAREN)
        _tmpl_scope_ctx = self._template_scope(template_params if template_params else [])
        _tmpl_scope_ctx.__enter__()
        params = self.parameter_list()
        self.consume(TokenType.RIGHT_PAREN)

        def _parse_op_bracket():
            self.consume(TokenType.LEFT_BRACKET)
            tt_list = []
            tv_list = []
            while not self.expect(TokenType.RIGHT_BRACKET):
                if self.current_token.type == TokenType.IDENTIFIER:
                    tt_list.append(TokenType.IDENTIFIER)
                    tv_list.append(self.current_token.value)
                elif self.current_token.type not in _TOKEN_SYMBOL_MAP:
                    self.error(f"Token '{self.current_token.value}' cannot be part of an operator symbol", TokenType.IDENTIFIER)
                else:
                    tt_list.append(self.current_token.type)
                    tv_list.append(None)
                self.advance()
            self.consume(TokenType.RIGHT_BRACKET)
            return tt_list, tv_list

        op_token_types, op_token_values = _parse_op_bracket()
        symbol = self._tokens_to_op_key(op_token_types, op_token_values)

        # Optional second bracket -- ternary operator: a [lop] b [rop] c
        symbol2 = None
        if self.expect(TokenType.LEFT_BRACKET):
            op2_types, op2_values = _parse_op_bracket()
            symbol2 = self._tokens_to_op_key(op2_types, op2_values)

        if symbol2 is not None:
            if len(params) == 1:
                # Circumfix operator: [lop] x [rop], one parameter
                pass
            elif len(params) != 3:
                self.error("Two-bracket operator requires either 1 parameter (circumfix) or 3 parameters (ternary)")
            mangled_fragment = self._mangle_op_symbol(symbol) + '__' + self._mangle_op_symbol(symbol2)
        else:
            mangled_fragment = self._mangle_op_symbol(symbol)
        func_name = f"operator__{mangled_fragment}"

        self.consume(TokenType.RETURN_ARROW)
        return_type = self.type_spec()

        # Pre-contracts: -> rtype : Contract1, Contract2 { ... }
        contract_stmts = []
        _pre_contract_names = []
        _pre_contract_arities = []
        if self.expect(TokenType.COLON):
            self.advance()
            contract_name, call_args = self._parse_contract_ref()
            if contract_name not in self._contracts:
                self.error(f"Undefined contract '{contract_name}'")
            contract_stmts.extend(self._resolve_contract(contract_name, params, call_args))
            _pre_contract_names.append(contract_name)
            _pre_contract_arities.append(len(call_args) if call_args is not None else None)
            while self.expect(TokenType.COMMA):
                self.advance()
                contract_name, call_args = self._parse_contract_ref()
                if contract_name not in self._contracts:
                    self.error(f"Undefined contract '{contract_name}'")
                contract_stmts.extend(self._resolve_contract(contract_name, params, call_args))
                _pre_contract_names.append(contract_name)
                _pre_contract_arities.append(len(call_args) if call_args is not None else None)

        unary_binding = None  # None | 'prefix' | 'postfix' -- set in non-prototype path
        if self.expect(TokenType.SEMICOLON):
            self.advance()
            body = Block([])
            is_prototype = True
        elif self.expect(TokenType.RETURN_ARROW):
            # Brace-omitted single-statement return: operator(...) [...] -> type -> expr;
            for param in params:
                if param.name is None:
                    self.error(f"Operator definition requires parameter names, but parameter of type {param.type_spec} has no name")
            for param in params:
                if param.name:
                    self.symbol_table.define(param.name, SymbolKind.VARIABLE, param.type_spec)
            self.advance()  # consume '->'
            expr = self.expression()
            self.consume(TokenType.SEMICOLON)
            body = Block([ReturnStatement(expr)])
            is_prototype = False
        else:
            body = self.block()
            if contract_stmts:
                body.statements = contract_stmts + body.statements
            # Post-contracts: } : Post1, Post2;
            post_contract_stmts = []
            _post_contract_names = []
            _post_contract_arities = []
            if self.expect(TokenType.COLON):
                self.advance()
                post_name, post_call_args = self._parse_contract_ref()
                if post_name not in self._contracts:
                    self.error(f"Undefined post-contract '{post_name}'")
                post_contract_stmts.extend(self._resolve_contract(post_name, params, post_call_args))
                _post_contract_names.append(post_name)
                _post_contract_arities.append(len(post_call_args) if post_call_args is not None else None)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    post_name, post_call_args = self._parse_contract_ref()
                    if post_name not in self._contracts:
                        self.error(f"Undefined post-contract '{post_name}'")
                    post_contract_stmts.extend(self._resolve_contract(post_name, params, post_call_args))
                    _post_contract_names.append(post_name)
                    _post_contract_arities.append(len(post_call_args) if post_call_args is not None else None)
            if post_contract_stmts:
                body = self._apply_post_contracts(body, return_type, post_contract_stmts)
            if _pre_contract_names or _post_contract_names:
                self._validate_contract_binding(func_name, _pre_contract_names, _pre_contract_arities,
                                                _post_contract_names, _post_contract_arities)
            # Parse optional unary binding: # binding {:this}  or  # binding {this:}
            # Must be checked BEFORE consuming the terminating ';'.
            # Only valid when the operator has exactly one parameter.
            if self.expect(TokenType.TAG):
                next_tok = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
                if next_tok and next_tok.type == TokenType.IDENTIFIER and next_tok.value == 'binding':
                    if len(params) != 1:
                        self.error("# binding on an operator definition is only valid for unary operators (exactly one parameter)")
                    self.advance()  # consume TAG (#)
                    self.advance()  # consume 'binding'
                    self.consume(TokenType.LEFT_BRACE)
                    if self.expect(TokenType.COLON):
                        # {:this} -- postfix
                        self.advance()  # consume ':'
                        self.consume(TokenType.THIS)
                        unary_binding = 'postfix'
                    elif self.expect(TokenType.THIS):
                        # {this:} -- prefix
                        self.advance()  # consume 'this'
                        self.consume(TokenType.COLON)
                        unary_binding = 'prefix'
                    else:
                        self.error("Unary # binding must be {:this} for postfix or {this:} for prefix")
                    self.consume(TokenType.RIGHT_BRACE)
            self.consume(TokenType.SEMICOLON)
            is_prototype = False

        # Only register truly novel symbols in _custom_operators.
        # Built-in operator symbols (those whose string matches an Operator enum value)
        # must NOT be added here, because custom_op_expression would then rewrite every
        # use of that operator into a FunctionCall regardless of operand types.
        # Built-in operator overloads are resolved at codegen time inside BinaryOp.codegen.
        _tmpl_scope_ctx.__exit__(None, None, None)
        from ftypesys import Operator as _Operator
        _builtin_op_values = {op.value for op in _Operator}
        if unary_binding is not None:
            # Unary custom operator -- register in prefix or postfix table only.
            if unary_binding == 'prefix':
                self._custom_prefix_ops[symbol] = func_name
            else:
                self._custom_postfix_ops[symbol] = func_name
        elif symbol2 is not None:
            if len(params) == 1:
                # Circumfix operator: [lop] x [rop]
                self._custom_circumfix_ops[(symbol, symbol2)] = func_name
            else:
                # Ternary custom operator: a [lop] b [rop] c
                self._custom_ternary_ops[(symbol, symbol2)] = func_name
            self.symbol_table.define(symbol2, SymbolKind.OPERATOR)
        elif symbol in _builtin_op_values:
            # Overloading a built-in operator is only permitted when at least one
            # parameter is an object or struct type - OR the overload is templated
            # (in which case the concrete types are not known yet).
            if not template_params:
                def _is_non_builtin(ts):
                    # Any type that is not one of the core primitive keywords is
                    # non-builtin: objects, structs, custom-typename aliases, DATA
                    # width types (i32, ui32, be16, ...), and pointers.
                    return (ts.custom_typename is not None or
                            ts.base_type in (DataType.STRUCT, DataType.OBJECT, DataType.DATA) or
                            ts.is_pointer)
                if not any(_is_non_builtin(p.type_spec) for p in params):
                    self.error(
                        f"Overloading built-in operator '{symbol}' requires at least "
                        f"one parameter to be a non-builtin type"
                    )
        else:
            self._custom_operators[symbol] = func_name
        self.symbol_table.define(symbol, SymbolKind.OPERATOR)

        # If this is a template operator, store it for deferred instantiation.
        if template_params:
            func_def = FunctionDef(
                name=func_name,
                parameters=params,
                return_type=return_type,
                body=body,
                is_prototype=is_prototype,
                no_mangle=False
            ).set_location(tok.line, tok.column)
            self._templates.register(symbol, 'operator', template_params, func_def)
            return None

        return FunctionDef(
            name=func_name,
            parameters=params,
            return_type=return_type,
            body=body,
            is_prototype=is_prototype,
            no_mangle=False
        ).set_location(tok.line, tok.column)

    def _match_custom_ternary_left(self):
        """
        Greedy longest-match against the LEFT symbols of all registered ternary operators.
        Returns (left_symbol, token_count) or (None, 0).
        """
        left_syms = {lsym: lsym for lsym, _ in self._custom_ternary_ops}
        return self._match_custom_unary_op(left_syms)

    def custom_op_expression(self) -> Expression:
        """
        custom_op_expression -> multiplicative_expression
                                  ( custom_binary_op multiplicative_expression
                                  | custom_ternary_left multiplicative_expression custom_ternary_right multiplicative_expression
                                  )*
        """
        expr = self.multiplicative_expression()

        while True:
            # Check ternary operators first (longer patterns take precedence).
            if self._custom_ternary_ops:
                matched_left, left_len = self._match_custom_ternary_left()
                if matched_left is not None:
                    tok = self.current_token
                    for _ in range(left_len):
                        self.advance()
                    mid = self.multiplicative_expression()
                    # Now match the right symbol of the pair.
                    # Find which pair(s) have this left symbol.
                    right_syms = {rsym: rsym for (lsym, rsym) in self._custom_ternary_ops if lsym == matched_left}
                    matched_right, right_len = self._match_custom_unary_op(right_syms)
                    if matched_right is None:
                        self.error(f"Expected right operator of ternary '{matched_left}' ... '{list(right_syms)[0]}'")
                    for _ in range(right_len):
                        self.advance()
                    right = self.multiplicative_expression()
                    func_name = self._custom_ternary_ops[(matched_left, matched_right)]
                    expr = FunctionCall(func_name, [expr, mid, right]).set_location(tok.line, tok.column)
                    continue

            matched_symbol, matched_length = self._match_custom_op()
            if matched_symbol is None:
                break
            for _ in range(matched_length):
                self.advance()
            right = self.multiplicative_expression()
            func_name = self._custom_operators[matched_symbol]
            expr = FunctionCall(func_name, [expr, right])

        return expr

    # ============ GRAMMAR RULES ============

    def parse(self) -> Program:
        """
        program -> statement* EOF
        """
        statements = []
        while not self.expect(TokenType.EOF):
            try:
                stmt = self.statement()
                if isinstance(stmt, list):
                    statements.extend(stmt)
                    if stmt:
                        self._last_stmt = stmt[-1]
                elif stmt:
                    statements.append(stmt)
                    self._last_stmt = stmt
            except FluxParseError as e:
                raise
        # Append template instantiations after all other statements so that
        # namespace functions they depend on are registered before their bodies run.
        # Order: structs first, then objects, then functions (invariant enforced here).
        _KIND_ORDER = {'struct': 0, 'object': 1, 'function': 2}
        for _, node in sorted(self._pending_template_instances, key=lambda t: _KIND_ORDER[t[0]]):
            statements.append(node)
        return Program(self.symbol_table, statements=statements)
    
    def has_errors(self) -> bool:
        """Check if any parse errors occurred during parsing"""
        return len(self.parse_errors) > 0
    
    def get_errors(self) -> List[str]:
        """Get list of parse error messages"""
        return self.parse_errors.copy()

    def _is_trait_prefixed_object(self) -> bool:
        """Look ahead to determine if current position is a trait-prefixed object definition.
        Pattern: IDENTIFIER+ 'object'
        where the final token before the identifiers run out is OBJECT.
        """
        if not self.expect(TokenType.IDENTIFIER):
            return False
        # Start scanning from the next token (offset=1 is next after current)
        offset = 1
        while True:
            tok = self.peek(offset)
            if tok is None:
                return False
            if tok.type == TokenType.OBJECT:
                return True
            if tok.type != TokenType.IDENTIFIER:
                return False
            offset += 1

    def _parse_trait_prefixed_object(self) -> 'ObjectDef':
        """Parse one or more trait names followed by 'object ...'"""
        trait_names = []
        while self.expect(TokenType.IDENTIFIER):
            # Check that next non-identifier token is OBJECT; if current is identifier and next is object, consume it as trait
            trait_names.append(self.current_token.value)
            self.advance()
            if self.expect(TokenType.OBJECT):
                break
        return self.object_def(trait_names=trait_names)

    def _is_bare_function_def(self) -> bool:
        """
        Lookahead predicate: returns True when the current position begins a
        bare function definition (no 'def' keyword):

            name([params]) -> type ;
            name([params]) -> type { body } ;

        Pattern: IDENTIFIER '(' ... ')' '->'
        The lookahead never consumes tokens.
        """
        with self._lookahead():
            if not self.expect(TokenType.IDENTIFIER):
                return False
            self.advance()
            if not self.expect(TokenType.LEFT_PAREN):
                return False
            self.advance()
            depth = 1
            while depth > 0 and not self.expect(TokenType.EOF):
                if self.expect(TokenType.LEFT_PAREN):
                    depth += 1
                elif self.expect(TokenType.RIGHT_PAREN):
                    depth -= 1
                    if depth == 0:
                        break
                self.advance()
            if not self.expect(TokenType.RIGHT_PAREN):
                return False
            self.advance()
            return self.expect(TokenType.RETURN_ARROW)

    def statement(self) -> Optional[Statement]:
        """
        statement -> 
                  | function_def_statement
                  | struct_def
                  | object_def_statement
                  | namespace_def
                  | custom_type_statement
                  | variable_declaration ';'
                  | expression_statement
                  | assignment_statement
                  | control_statement
        """
        # Parse storage class FIRST (global, local, heap, stack, register)
        # BUT NOT const/volatile - those belong to type_spec()!
        storage_class = None
        
        if self.expect(TokenType.GLOBAL):
            storage_class = 'global'
            self.advance()
        elif self.expect(TokenType.LOCAL):
            storage_class = 'local'
            self.advance()
        elif self.expect(TokenType.HEAP):
            storage_class = 'heap'
            self.advance()
        elif self.expect(TokenType.STACK):
            storage_class = 'stack'
            self.advance()
        elif self.expect(TokenType.REGISTER):
            storage_class = 'register'
            self.advance()
        elif self.expect(TokenType.SINGINIT):
            storage_class = 'singinit'
            self.advance()
        
        # Check for const/volatile (but DON'T consume them - type_spec will handle that)
        # OR check if we just parsed a storage class
        if storage_class or self.expect(TokenType.CONST, TokenType.VOLATILE):
            # Look ahead to determine what kind of statement this is
            saved_pos = self.position
            saved_token = self.current_token
            
            # Skip past const/volatile to see what comes next
            while self.expect(TokenType.CONST, TokenType.VOLATILE, TokenType.SINGINIT, TokenType.INLINE):
                self.advance()
            
            is_asm = self.expect(TokenType.ASM)
            is_func = self.expect(TokenType.DEF) or self.expect(TokenType.INLINE) or self.current_token.type in _CALLING_CONV_TOKENS or self._is_bare_function_def()
            
            # Restore position
            self.position = saved_pos
            self.current_token = saved_token
            
            if is_asm:
                # Special case: volatile asm
                is_volatile = False
                if self.expect(TokenType.VOLATILE):
                    is_volatile = True
                    self.advance()
                return self.asm_statement(is_volatile=is_volatile)
            elif is_func:
                return self.function_def()
            else:
                # It's a variable declaration - type_spec() will parse const/volatile
                # The storage class token was already consumed above; back up so type_spec() can see it
                if storage_class is not None:
                    self.position -= 1
                    self.current_token = self.tokens[self.position]
                var_decl = self.variable_declaration()
                self.consume(TokenType.SEMICOLON)
                return var_decl
        
        # No storage class or qualifiers - check for other statement types
        if self.expect(TokenType.MACRO):
            return self.macro_def()
        elif self.expect(TokenType.USING):
            return self.using_statement()
        elif self.expect(TokenType.NOT):
            self.advance()
            if self.expect(TokenType.USING):
                self.advance()
                return self.not_using_statement()
        elif self.expect(TokenType.OPERATOR):
            return self.operator_def()
        elif self.expect(TokenType.EXTERN):
            return self.extern_statement()
        elif self.expect(TokenType.EXPORT):
            return self.export_statement()
        elif self.expect(TokenType.CONTRACT):
            return self.contract_def()
        elif self.expect(TokenType.CONSTRAINT):
            return self.constra_def()
        elif self.expect(TokenType.EFFECT):
            return self.effect_def()
        elif self.expect(TokenType.INLINE):
            return self.function_def()
        elif self.expect(TokenType.DEF):
            return self.function_def()
        elif self.current_token.type in _CALLING_CONV_TOKENS:
            return self.function_def()
        elif self._is_bare_function_def():
            return self.function_def()
        elif self.expect(TokenType.ENUM):
            return self.enum_def()
        elif self.peek() and self.peek().type == TokenType.ENUM:
            # Typed enum: TYPE enum NAME { ... }
            return self.enum_def()
        elif self.expect(TokenType.UNION):
            return self.union_def()
        elif self.expect(TokenType.STRUCT):
            if self.peek() and self.peek().type == TokenType.MULTIPLY:
                # This is a struct pointer variable declaration like: struct* pm
                return self.variable_declaration_statement()
            else:
                return self.struct_def()
        elif self.expect(TokenType.OBJECT):
            if self.peek() and self.peek().type == TokenType.MULTIPLY:
                # object pointer variable declaration: object* or object*[]
                return self.variable_declaration_statement()
            else:
                return self.object_def()
        elif self.expect(TokenType.TRAIT):
            return self.trait_def()
        elif self.expect(TokenType.INTERFACE):
            return self.interface_def()
        elif self._is_trait_prefixed_object():
            return self._parse_trait_prefixed_object()
        elif self.expect(TokenType.NAMESPACE):
            return self.namespace_def()
        elif self.expect(TokenType.IF):
            return self.if_statement()
        elif self.expect(TokenType.DO):
            return self.do_while_statement()
        elif self.expect(TokenType.WHILE):
            return self.while_statement()
        elif self.expect(TokenType.FOR):
            return self.for_statement()
        elif self.expect(TokenType.SWITCH):
            return self.switch_statement()
        elif self.expect(TokenType.TRY):
            return self.try_statement()
        elif self.expect(TokenType.RETURN):
            return self.return_statement()
        elif self.expect(TokenType.RETURN_ARROW):
            return self.return_arrow_ret()
        elif self.expect(TokenType.BREAK):
            return self.break_statement()
        elif self.expect(TokenType.CONTINUE):
            return self.continue_statement()
        elif self.expect(TokenType.LABEL):
            return self.label_statement()
        elif self.expect(TokenType.GOTO):
            return self.goto_statement()
        elif self.expect(TokenType.JUMP):
            return self.jump_statement()
        elif self.expect(TokenType.THROW):
            return self.throw_statement()
        elif self.expect(TokenType.ASSERT):
            return self.assert_statement()
        elif self.expect(TokenType.DEFER):
            return self.defer_statement()
        elif self.expect(TokenType.ESCAPE_KW):
            return self.escape_statement()
        elif self.expect(TokenType.DEPRECATE):
            return self.deprecate_statement()
        elif self.expect(TokenType.NORET):
            return self.noreturn_statement()
        elif self.expect(TokenType.LEFT_BRACE):
            return self.block_statement()
        elif self._is_type_func_def():
            return self.type_func_def()
        elif self.is_dual_assign_declaration():
            return self.dual_assign_declaration()
        elif self.is_variable_declaration():
            return self.variable_declaration_statement()
        elif self.expect(TokenType.UNSIGNED):
            return self.variable_declaration_statement()
        elif self.expect(TokenType.SIGNED):
            return self.variable_declaration_statement()
        elif self.expect(TokenType.SINT, TokenType.UINT, TokenType.DATA, TokenType.CHAR, TokenType.BYTE, 
                         TokenType.FLOAT_KW, TokenType.DOUBLE_KW, TokenType.BOOL_KW, TokenType.VOID,
                         TokenType.SLONG, TokenType.ULONG, TokenType.DICT):
            return self.variable_declaration_statement()
        elif self.expect(TokenType.DITTO):
            import copy
            tok = self.current_token
            self.advance()  # consume DITTO
            self.consume(TokenType.SEMICOLON)
            if self._last_stmt is None:
                self.error("Ditto operator '#\"' used as a statement before any preceding statement to repeat")
            duplicated = copy.deepcopy(self._last_stmt)
            # Store the concrete copy so chained `#";` repeats the original.
            self._last_stmt = duplicated
            return duplicated
        elif self.expect(TokenType.SEMICOLON):
            self.advance()
            return None
        elif self.expect(TokenType.AUTO) and self.peek() and self.peek().type == TokenType.LEFT_BRACE:
            # Handle destructuring assignment
            destructure = self.destructuring_assignment()
            self.consume(TokenType.SEMICOLON)
            return destructure
        elif self.expect(TokenType.AUTO) and self.peek() and self.peek().type == TokenType.IDENTIFIER:
            # Handle auto type inference: auto name = expr;
            decl = self.auto_variable_declaration()
            self.consume(TokenType.SEMICOLON)
            return decl
        elif self.expect(TokenType.CODIFY):
            # ~$varname; - compile-time code injection.
            # The parser re-lexes the string literal stored in varname and parses
            # it into statements that are spliced in place of this statement.
            # A completely fresh parser is used with zero shared state so that
            # no symbol-table mutations bleed back into the outer parse.
            tok = self.current_token
            self.advance()  # consume CODIFY (~$)
            if self.expect(TokenType.STRING_LITERAL):
                source_text = self.current_token.value
                self.advance()
            elif self.expect(TokenType.F_STRING):
                raw = self.consume(TokenType.F_STRING).value
                fstr = self.parse_f_string(raw[2:-1])  # strip f" and closing "
                source_text = "".join(p if isinstance(p, str) else self._comptime_strings[p.name] for p in fstr.parts)
            elif self.expect(TokenType.I_STRING):
                istr = self.parse_i_string(self.consume(TokenType.I_STRING).value)
                source_text = "".join(p if isinstance(p, str) else self._comptime_strings[p.name] for p in istr.parts)
            elif self.expect(TokenType.IDENTIFIER):
                var_name = self.current_token.value
                self.advance()
                if var_name not in self._comptime_strings:
                    self.error(
                        f"~$: '{var_name}' is not a compile-time-known byte* string literal. "
                        f"Only variables declared as 'byte* name = \"...\";' are supported."
                    )
                source_text = self._comptime_strings[var_name]
            else:
                self.error("~$: expected identifier, string literal, f-string, or i-string after codify operator", TokenType.IDENTIFIER)
            self.consume(TokenType.SEMICOLON)
            sub_lexer = FluxLexer(source_text)
            sub_tokens = sub_lexer.tokenize()
            sub_parser = FluxParser(sub_tokens)
            sub_stmts = []
            while not sub_parser.expect(TokenType.EOF):
                stmt = sub_parser.statement()
                if isinstance(stmt, list):
                    sub_stmts.extend(s for s in stmt if s is not None)
                elif stmt is not None:
                    sub_stmts.append(stmt)
            return sub_stmts if sub_stmts else None
        elif self.expect(TokenType.COMPTIME):
            return self.comptime_block()
        elif self.expect(TokenType.EMITFLUX):
            if self._in_comptime == 0:
                self.error("'emitflux' is only valid inside a 'comptime' block")
            return self.emitflux_statement()
        elif self.expect(TokenType.ASM):
            return self.asm_statement()
        elif self.expect(TokenType.FLUXVM):
            if self._in_comptime == 0:
                self.error("'fluxvm' is only valid inside a 'comptime' block")
            return self.fluxvm_statement()
        elif (self.expect(TokenType.IDENTIFIER) and self.current_token.value == 'error'
              and self.peek() is not None and self.peek().type != TokenType.ASSIGN):
            return self.error_return_statement()
        else:
            return self.expression_statement()
    
    def using_statement(self) -> Union[UsingStatement, List[UsingStatement]]:
        """
        using_statement -> 'using' namespace_path (',' namespace_path)* ';'
        namespace_path -> IDENTIFIER ('::' IDENTIFIER)*
        """
        tok = self.current_token
        self.consume(TokenType.USING)

        def parse_namespace_path() -> str:
            path = self.consume(TokenType.IDENTIFIER).value
            while self.expect(TokenType.SCOPE):  # ::
                self.advance()
                path += "__" + self.consume(TokenType.IDENTIFIER).value
            return path

        paths = [parse_namespace_path()]
        while self.expect(TokenType.COMMA):
            self.advance()
            paths.append(parse_namespace_path())

        self.consume(TokenType.SEMICOLON)

        if len(paths) == 1:
            return UsingStatement(paths[0]).set_location(tok.line, tok.column)
        return [UsingStatement(p).set_location(tok.line, tok.column) for p in paths]

    def not_using_statement(self) -> Union[NotUsingStatement, List[NotUsingStatement]]:
        """
        not_using_statement -> '!' 'using' namespace_path (',' namespace_path)* ';'
        namespace_path -> IDENTIFIER ('::' IDENTIFIER)*
        """
        tok = self.current_token
        def parse_namespace_path() -> str:
            path = self.consume(TokenType.IDENTIFIER).value
            while self.expect(TokenType.SCOPE):  # ::
                self.advance()
                path += "__" + self.consume(TokenType.IDENTIFIER).value
            return path

        paths = [parse_namespace_path()]
        while self.expect(TokenType.COMMA):
            self.advance()
            paths.append(parse_namespace_path())

        # For now, handle only single namespace per statement
        self.consume(TokenType.SEMICOLON)

        if len(paths) == 1:
            return NotUsingStatement(paths[0]).set_location(tok.line, tok.column)
        return [NotUsingStatement(p).set_location(tok.line, tok.column) for p in paths]

    def deprecate_statement(self) -> DeprecateStatement:
        """
        deprecate_statement -> 'deprecate' namespace_path ';'
        namespace_path -> IDENTIFIER ('::' IDENTIFIER)*
        Statically checks at compile time that no references to the namespace exist.
        """
        tok = self.current_token
        self.consume(TokenType.DEPRECATE)
        path = self.consume(TokenType.IDENTIFIER).value
        while self.expect(TokenType.SCOPE):
            self.advance()
            path += "::" + self.consume(TokenType.IDENTIFIER).value
        self.consume(TokenType.SEMICOLON)
        return DeprecateStatement(path).set_location(tok.line, tok.column)

    def extern_statement(self) -> ExternBlock:
        """
        extern_statement -> 'extern' '{' extern_function_def* '}' ';'
                         | 'extern' 'def' IDENTIFIER '(' parameter_list? ')' '->' type_spec ';'
        """
        tok = self.current_token
        self.consume(TokenType.EXTERN)
        
        declarations = []
        
        # Check if this is a block or single declaration
        if self.expect(TokenType.LEFT_BRACE):
            # Block form: extern Ellipsis;
            self.advance()
            
            while not self.expect(TokenType.RIGHT_BRACE):
                # Each declaration must be a function prototype or variable declaration
                if self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
                    func_def = self.function_def()
                    # Handle both single FunctionDef and list of FunctionDef (multi-function prototypes)
                    if isinstance(func_def, list):
                        for fd in func_def:
                            if not fd.is_prototype:
                                self.error("Extern functions must be prototypes (declarations only, no body)")
                            declarations.append(fd)
                    else:
                        if not func_def.is_prototype:
                            self.error("Extern functions must be prototypes (declarations only, no body)")
                        declarations.append(func_def)
                else:
                    # Variable declaration: type_spec IDENTIFIER ;
                    var_tok = self.current_token
                    type_sp = self.type_spec()
                    var_name = self.consume(TokenType.IDENTIFIER).value
                    if self.expect(TokenType.ASSIGN) or self.expect(TokenType.ADDRESS_ASSIGN):
                        self.error("Extern variable declarations cannot have an initializer")
                    self.consume(TokenType.SEMICOLON)
                    var_decl = VariableDeclaration(var_name, type_sp, None)
                    declarations.append(var_decl.set_location(var_tok.line, var_tok.column))
            
            self.consume(TokenType.RIGHT_BRACE)
            self.consume(TokenType.SEMICOLON)
        elif self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
            # Single declaration form: extern def ...;  or  extern cdecl ...;
            func_def = self.function_def()
            # Handle both single FunctionDef and list of FunctionDef (multi-function prototypes)
            if isinstance(func_def, list):
                for fd in func_def:
                    if not fd.is_prototype:
                        self.error("Extern functions must be prototypes (declarations only, no body)")
                    declarations.append(fd)
            else:
                if not func_def.is_prototype:
                    self.error("Extern functions must be prototypes (declarations only, no body)")
                declarations.append(func_def)
        else:
            # Single extern variable declaration: extern type_spec IDENTIFIER ;
            var_tok = self.current_token
            type_sp = self.type_spec()
            var_name = self.consume(TokenType.IDENTIFIER).value
            if self.expect(TokenType.ASSIGN) or self.expect(TokenType.ADDRESS_ASSIGN):
                self.error("Extern variable declarations cannot have an initializer")
            self.consume(TokenType.SEMICOLON)
            var_decl = VariableDeclaration(var_name, type_sp, None)
            declarations.append(var_decl.set_location(var_tok.line, var_tok.column))
        
        return ExternBlock(declarations).set_location(tok.line, tok.column)

    def export_statement(self) -> 'ExportBlock':
        """
        export_statement -> 'export' '{' export_function_def* '}' ';'
                         | 'export' 'def' function_def ';'

        Marks functions as externally visible (dllexport / ELF global).
        Unlike 'extern', exported functions must have full definitions (bodies).
        Supports the same inline and block forms as 'extern':

            export def !!some_func() -> rtype { ... };

            export
            {
                def !!some_func() -> rtype { ... };
            };
        """
        tok = self.current_token
        self.consume(TokenType.EXPORT)

        definitions = []

        if self.expect(TokenType.LEFT_BRACE):
            # Block form: export { ... };
            self.advance()

            while not self.expect(TokenType.RIGHT_BRACE):
                if self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
                    func_def = self.function_def()
                    if isinstance(func_def, list):
                        for fd in func_def:
                            if fd.is_prototype:
                                self.error("'export' requires a full definition, not a prototype")
                            definitions.append(fd)
                    else:
                        if func_def.is_prototype:
                            self.error("'export' requires a full definition, not a prototype")
                        definitions.append(func_def)
                else:
                    self.error("Expected function definition inside export block", TokenType.DEF)

            self.consume(TokenType.RIGHT_BRACE)
            self.consume(TokenType.SEMICOLON)
            return ExportBlock(definitions).set_location(tok.line, tok.column)

        elif self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
            # Single form: export def ...;
            func_def = self.function_def()
            if isinstance(func_def, list):
                for fd in func_def:
                    if fd.is_prototype:
                        self.error("'export' requires a full definition, not a prototype")
                    definitions.append(fd)
            else:
                if func_def.is_prototype:
                    self.error("'export' requires a full definition, not a prototype")
                definitions.append(func_def)
        else:
            self.error("Expected '{' or 'def' after 'export'", TokenType.LEFT_BRACE)

        return ExportBlock(definitions).set_location(tok.line, tok.column)

    def _parse_contract_ref(self):
        """
        Parse a contract reference at an attachment site.
        Returns (contract_name, call_site_args_or_None).

        Syntax:
            ContractName                  -> ('ContractName', None)
            ContractName(a, b)            -> ('ContractName', ['a', 'b'])
        """
        name = self.consume(TokenType.IDENTIFIER).value
        call_args = None
        if self.expect(TokenType.LEFT_PAREN):
            self.advance()
            call_args = []
            if not self.expect(TokenType.RIGHT_PAREN):
                call_args.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    call_args.append(self.consume(TokenType.IDENTIFIER).value)
            self.consume(TokenType.RIGHT_PAREN)
        return name, call_args

    def _validate_contract_binding(self, func_name: str,
                                    pre_contract_names: list,
                                    pre_contract_arities: list,
                                    post_contract_names: list,
                                    post_contract_arities: list):
        """
        Validate that a function's pre/post contracts satisfy all active # binding
        constraints declared on those contracts.

        For every contract (pre or post) that has a # binding, we check:
          - pre_side: required names must appear as pre-contracts on the function.
            'this' on pre-side = the contract itself must be a pre-contract.
            '!' = no pre-contracts allowed.
          - post_side: required names must appear as post-contracts on the function.
            'this' on post-side = the contract itself must be a post-contract.
            '!' = no post-contracts allowed.
            ',' = all required present in that order, forbidden absent.
            '|' = any subset present in that order, forbidden absent.
            '&' = all required present, forbidden absent.
        """
        def _matches_ref(name, arity_or_none, names, arities):
            for n, a in zip(names, arities):
                if n == name and (arity_or_none is None or arity_or_none == a):
                    return True
            return False

        # Unified loop: check every contract that has a binding, whether it appears
        # as a pre-contract, a post-contract, or both.
        # 'this' always means the contract itself.
        # is_pre / is_post indicate which position(s) the contract occupies on this function.
        all_bound = set(pre_contract_names + post_contract_names) & set(self._contract_bindings.keys())
        for cname in list(dict.fromkeys(pre_contract_names + post_contract_names)):
            if cname not in self._contract_bindings:
                continue
            binding = self._contract_bindings[cname]
            pre_spec = binding['pre']
            post_spec = binding['post']
            post_op = binding['post_op']
            is_pre = cname in pre_contract_names
            is_post = cname in post_contract_names

            # --- validate pre_side ---
            # pre_spec names (other than 'this') must appear as pre-contracts on the function.
            # 'this' on the pre-side means the contract itself must be a pre-contract.
            if pre_spec == ['!']:
                if pre_contract_names:
                    self.error(
                        f"Contract '{cname}' binding declares no pre-contract is allowed "
                        f"on function '{func_name}', but pre-contracts are present: {pre_contract_names}"
                    )
            else:
                for required_pre in pre_spec:
                    if required_pre == 'this':
                        if not is_pre:
                            self.error(
                                f"Contract '{cname}' binding requires itself as a pre-contract "
                                f"on function '{func_name}', but it is only used as a post-contract"
                            )
                    elif required_pre not in pre_contract_names:
                        if required_pre in post_contract_names:
                            self.error(
                                f"Contract '{cname}' binding requires '{required_pre}' as a "
                                f"pre-contract on function '{func_name}', but it is inverted "
                                f"(used as a post-contract instead)"
                            )
                        else:
                            self.error(
                                f"Contract '{cname}' binding requires pre-contract '{required_pre}' "
                                f"on function '{func_name}', but it is not present"
                            )

            # --- validate post_side ---
            if not post_spec:
                continue

            # 'this' on post-side means the contract itself must be a post-contract.
            if post_spec == [('!', None, False)]:
                if post_contract_names:
                    self.error(
                        f"Contract '{cname}' binding declares no post-contract is allowed "
                        f"on function '{func_name}', but post-contracts are present: {post_contract_names}"
                    )
                continue

            # Resolve 'this' to the contract's own name throughout post_spec.
            resolved = [(cname if n == 'this' else n, a, neg) for n, a, neg in post_spec]

            if post_op is None or post_op == ',':
                required_order = [(n, a) for n, a, neg in resolved if not neg]
                forbidden      = [(n, a) for n, a, neg in resolved if neg]
                for fn, fa in forbidden:
                    if _matches_ref(fn, fa, post_contract_names, post_contract_arities):
                        self.error(
                            f"Contract '{cname}' binding forbids post-contract '{fn}' "
                            f"on function '{func_name}'"
                        )
                indices = []
                for rn, ra in required_order:
                    found_idx = None
                    for i, (pn, pa) in enumerate(zip(post_contract_names, post_contract_arities)):
                        if pn == rn and (ra is None or ra == pa):
                            found_idx = i
                            break
                    if found_idx is None:
                        if _matches_ref(rn, ra, pre_contract_names, pre_contract_arities):
                            self.error(
                                f"Contract '{cname}' binding requires '{rn}' as a "
                                f"post-contract on function '{func_name}', but it is inverted "
                                f"(used as a pre-contract instead)"
                            )
                        else:
                            self.error(
                                f"Contract '{cname}' binding requires post-contract '{rn}' "
                                f"on function '{func_name}'"
                            )
                    indices.append(found_idx)
                for i in range(1, len(indices)):
                    if indices[i] <= indices[i - 1]:
                        self.error(
                            f"Contract '{cname}' binding requires post-contracts "
                            f"{[n for n, _ in required_order]} in that order on function '{func_name}'"
                        )

            elif post_op == '|':
                required_order = [(n, a) for n, a, neg in resolved if not neg]
                forbidden      = [(n, a) for n, a, neg in resolved if neg]
                for fn, fa in forbidden:
                    if _matches_ref(fn, fa, post_contract_names, post_contract_arities):
                        self.error(
                            f"Contract '{cname}' binding forbids post-contract '{fn}' "
                            f"on function '{func_name}'"
                        )
                present = []
                for rn, ra in required_order:
                    for i, (pn, pa) in enumerate(zip(post_contract_names, post_contract_arities)):
                        if pn == rn and (ra is None or ra == pa):
                            present.append((rn, i))
                            break
                for i in range(1, len(present)):
                    if present[i][1] <= present[i - 1][1]:
                        self.error(
                            f"Contract '{cname}' binding requires post-contracts "
                            f"{[n for n, _ in required_order]} in that order on function '{func_name}'"
                        )

            elif post_op == '&':
                for rn, ra, neg in resolved:
                    matched = _matches_ref(rn, ra, post_contract_names, post_contract_arities)
                    if not neg and not matched:
                        if _matches_ref(rn, ra, pre_contract_names, pre_contract_arities):
                            self.error(
                                f"Contract '{cname}' binding requires '{rn}' as a "
                                f"post-contract on function '{func_name}', but it is inverted "
                                f"(used as a pre-contract instead)"
                            )
                        else:
                            self.error(
                                f"Contract '{cname}' binding requires post-contract '{rn}' "
                                f"on function '{func_name}'"
                            )
                    elif neg and matched:
                        self.error(
                            f"Contract '{cname}' binding forbids post-contract '{rn}' "
                            f"on function '{func_name}'"
                        )

    def _resolve_contract(self, contract_name: str, func_params: list,
                          call_site_args: list = None) -> list:
        """
        Return a deep-copied, substituted list of statements for the named contract.

        call_site_args: optional list of identifier strings supplied at the
        attachment site, e.g. the ['y', 'x'] from `: LessThan(y, x)`.  When
        provided they define the mapping order (contract param[i] -> call_site_args[i],
        which must itself be a name of a real function parameter).  When absent,
        mapping is positional: contract param[i] -> real_params[i].

        For plain (unparameterized) contracts the statements are returned as-is
        (deep-copied so each injection site is independent).
        """
        import copy
        c_params, c_body = self._contracts[contract_name]
        real_params = [p for p in func_params if not getattr(p, '_is_variadic_sentinel', False)]
        real_param_names = {p.name for p in real_params if p.name is not None}
        if c_params:
            if call_site_args is not None:
                # Explicit remapping: arity must match contract params
                if len(call_site_args) != len(c_params):
                    self.error(
                        f"Contract '{contract_name}' expects {len(c_params)} parameter(s) "
                        f"but {len(call_site_args)} argument(s) given at attachment site"
                    )
                # Remap contract params to function params positionally.
                # call_site_args[i] is the contract param name that maps to real_params[i].
                if len(real_params) < len(call_site_args):
                    self.error(
                        f"Contract '{contract_name}' attachment maps {len(call_site_args)} "
                        f"parameter(s) but function only has {len(real_params)}"
                    )
                subst = {
                    call_site_args[i]: real_params[i].name
                    for i in range(len(call_site_args))
                    if real_params[i].name is not None
                }
            else:
                # Positional mapping
                if len(c_params) != len(real_params):
                    self.error(
                        f"Contract '{contract_name}' expects {len(c_params)} parameter(s) "
                        f"but function has {len(real_params)}"
                    )
                subst = {
                    c_param: real_params[i].name
                    for i, c_param in enumerate(c_params)
                    if real_params[i].name is not None
                }
            stmts_copy = copy.deepcopy(c_body.statements)
            return self._substitute_contract_stmts(stmts_copy, subst)
        return copy.deepcopy(c_body.statements)

    def _substitute_contract_stmts(self, stmts: list, subst: dict) -> list:
        """
        Walk a list of statements and replace every Identifier whose name is a
        key in `subst` with a new Identifier of the mapped name.  This covers
        the statement-level nodes that appear in contract bodies.
        """
        for stmt in stmts:
            self._substitute_stmt(stmt, subst)
        return stmts

    def _substitute_stmt(self, stmt, subst: dict) -> None:
        """In-place substitution over a single statement node."""
        if stmt is None:
            return
        if isinstance(stmt, AssertStatement):
            stmt.condition = self._substitute_expr(stmt.condition, subst)
            if stmt.message is not None and not isinstance(stmt.message, str):
                stmt.message = self._substitute_expr(stmt.message, subst)
        elif isinstance(stmt, ExpressionStatement):
            stmt.expression = self._substitute_expr(stmt.expression, subst)
        elif isinstance(stmt, ReturnStatement):
            if stmt.value is not None:
                stmt.value = self._substitute_expr(stmt.value, subst)
        elif isinstance(stmt, (Assignment, CompoundAssignment, TernaryAssign)):
            stmt.target = self._substitute_expr(stmt.target, subst)
            stmt.value  = self._substitute_expr(stmt.value,  subst)
        elif isinstance(stmt, VariableDeclaration):
            if stmt.initial_value is not None:
                stmt.initial_value = self._substitute_expr(stmt.initial_value, subst)
        elif isinstance(stmt, Block):
            self._substitute_contract_stmts(stmt.statements, subst)
        elif isinstance(stmt, IfStatement):
            stmt.condition = self._substitute_expr(stmt.condition, subst)
            self._substitute_contract_stmts(stmt.then_block.statements, subst)
            if stmt.else_block:
                self._substitute_contract_stmts(stmt.else_block.statements, subst)
            stmt.elif_blocks = [
                (self._substitute_expr(cond, subst),
                 Block(self._substitute_contract_stmts(blk.statements, subst)))
                for cond, blk in stmt.elif_blocks
            ]
        elif isinstance(stmt, (ForLoop, ForInLoop, WhileLoop, DoLoop, DoWhileLoop)):
            self._substitute_contract_stmts(stmt.body.statements, subst)
        elif isinstance(stmt, TryBlock):
            self._substitute_contract_stmts(stmt.try_body.statements, subst)
            for _, _, blk in stmt.catch_blocks:
                self._substitute_contract_stmts(blk.statements, subst)

    def _substitute_expr(self, expr, subst: dict):
        """Recursively substitute Identifiers in an expression node."""
        if expr is None:
            return expr
        if isinstance(expr, Identifier):
            if expr.name in subst:
                return Identifier(subst[expr.name]).set_location(expr.source_line, expr.source_col)
            return expr
        if isinstance(expr, BinaryOp):
            expr.left  = self._substitute_expr(expr.left,  subst)
            expr.right = self._substitute_expr(expr.right, subst)
        elif isinstance(expr, UnaryOp):
            expr.operand = self._substitute_expr(expr.operand, subst)
        elif isinstance(expr, (CastExpression, TieExpression)):
            expr.expression = self._substitute_expr(expr.expression, subst)
        elif isinstance(expr, FunctionCall):
            expr.arguments = [self._substitute_expr(a, subst) for a in expr.arguments]
        elif isinstance(expr, MethodCall):
            expr.object    = self._substitute_expr(expr.object, subst)
            expr.arguments = [self._substitute_expr(a, subst) for a in expr.arguments]
        elif isinstance(expr, MemberAccess):
            expr.object = self._substitute_expr(expr.object, subst)
        elif isinstance(expr, ArrayAccess):
            expr.array = self._substitute_expr(expr.array, subst)
            expr.index = self._substitute_expr(expr.index, subst)
        elif isinstance(expr, TernaryOp):
            expr.condition  = self._substitute_expr(expr.condition,  subst)
            expr.true_expr  = self._substitute_expr(expr.true_expr,  subst)
            expr.false_expr = self._substitute_expr(expr.false_expr, subst)
        elif isinstance(expr, NullCoalesce):
            expr.left  = self._substitute_expr(expr.left,  subst)
            expr.right = self._substitute_expr(expr.right, subst)
        elif isinstance(expr, ArrayLiteral):
            expr.elements = [self._substitute_expr(e, subst) for e in expr.elements]
        elif isinstance(expr, FStringLiteral):
            expr.parts = [
                self._substitute_expr(part, subst) if not isinstance(part, str) else part
                for part in expr.parts
            ]
        return expr

    def _apply_post_contracts(self, body: Block, return_type, post_stmts: list) -> Block:
        """
        Rewrite every ReturnStatement in body so that post-contract assertions
        run against the return value before the function actually returns.

        Each ``return <expr>;`` becomes::

            <return_type> r = <expr>;
            <post_contract assertions referencing r>
            return r;

        The rewrite is recursive so returns inside nested if/for/while/try blocks
        are also caught.  The sentinel name ``r`` matches the convention used
        in contract bodies (e.g. ``assert(r > 10, ...)``).
        """
        import copy

        def _rewrite_stmts(stmts):
            out = []
            for stmt in stmts:
                if isinstance(stmt, ReturnStatement) and stmt.value is not None:
                    # <return_type> r = <expr>;
                    r_decl = VariableDeclaration(
                        name='r',
                        type_spec=return_type,
                        initial_value=stmt.value,
                    )
                    r_decl.set_location(stmt.source_line, stmt.source_col)
                    # deep-copy contract stmts so each return site is independent
                    injected = copy.deepcopy(post_stmts)
                    # return r;
                    r_ret = ReturnStatement(Identifier('r'))
                    r_ret.set_location(stmt.source_line, stmt.source_col)
                    out.append(r_decl)
                    out.extend(injected)
                    out.append(r_ret)
                elif isinstance(stmt, Block):
                    out.append(Block(_rewrite_stmts(stmt.statements)))
                elif isinstance(stmt, IfStatement):
                    stmt.then_block = Block(_rewrite_stmts(stmt.then_block.statements))
                    if stmt.else_block is not None:
                        stmt.else_block = Block(_rewrite_stmts(stmt.else_block.statements))
                    stmt.elif_blocks = [
                        (cond, Block(_rewrite_stmts(blk.statements)))
                        for cond, blk in stmt.elif_blocks
                    ]
                    out.append(stmt)
                elif isinstance(stmt, (ForLoop, ForInLoop, WhileLoop, DoLoop, DoWhileLoop)):
                    stmt.body = Block(_rewrite_stmts(stmt.body.statements))
                    out.append(stmt)
                elif isinstance(stmt, SwitchStatement):
                    stmt.cases = [
                        type(c)(c.value, Block(_rewrite_stmts(c.body.statements)))
                        if hasattr(c, 'body') else c
                        for c in stmt.cases
                    ]
                    out.append(stmt)
                elif isinstance(stmt, TryBlock):
                    stmt.try_body = Block(_rewrite_stmts(stmt.try_body.statements))
                    stmt.catch_blocks = [
                        (exc_type, exc_name, Block(_rewrite_stmts(blk.statements)))
                        for exc_type, exc_name, blk in stmt.catch_blocks
                    ]
                    out.append(stmt)
                else:
                    out.append(stmt)
            return out

        # For void functions there are no return values to wrap, but we still
        # need to inject the contract statements before every bare return;
        # as well as at the implicit fall-through end of the body.
        is_void = (
            hasattr(return_type, 'base_type') and return_type.base_type == DataType.VOID
        ) or str(return_type) == 'void'
        if is_void:
            def _rewrite_void_stmts(stmts):
                out = []
                for stmt in stmts:
                    if isinstance(stmt, ReturnStatement) and stmt.value is None:
                        # Inject contract code before the bare return;
                        out.extend(copy.deepcopy(post_stmts))
                        out.append(stmt)
                    elif isinstance(stmt, Block):
                        out.append(Block(_rewrite_void_stmts(stmt.statements)))
                    elif isinstance(stmt, IfStatement):
                        stmt.then_block = Block(_rewrite_void_stmts(stmt.then_block.statements))
                        if stmt.else_block is not None:
                            stmt.else_block = Block(_rewrite_void_stmts(stmt.else_block.statements))
                        stmt.elif_blocks = [
                            (cond, Block(_rewrite_void_stmts(blk.statements)))
                            for cond, blk in stmt.elif_blocks
                        ]
                        out.append(stmt)
                    elif isinstance(stmt, (ForLoop, ForInLoop, WhileLoop, DoLoop, DoWhileLoop)):
                        stmt.body = Block(_rewrite_void_stmts(stmt.body.statements))
                        out.append(stmt)
                    elif isinstance(stmt, SwitchStatement):
                        stmt.cases = [
                            type(c)(c.value, Block(_rewrite_void_stmts(c.body.statements)))
                            if hasattr(c, 'body') else c
                            for c in stmt.cases
                        ]
                        out.append(stmt)
                    elif isinstance(stmt, TryBlock):
                        stmt.try_body = Block(_rewrite_void_stmts(stmt.try_body.statements))
                        stmt.catch_blocks = [
                            (exc_type, exc_name, Block(_rewrite_void_stmts(blk.statements)))
                            for exc_type, exc_name, blk in stmt.catch_blocks
                        ]
                        out.append(stmt)
                    else:
                        out.append(stmt)
                return out
            body.statements = _rewrite_void_stmts(body.statements) + copy.deepcopy(post_stmts)
        else:
            body.statements = _rewrite_stmts(body.statements)
        return body

    def contract_def(self) -> ContractDef:
        """
        contract_def -> 'contract' IDENTIFIER ('(' param_list ')')? block ';'
                        ('# binding' '{' binding_spec '}' ';')?

        Parses a contract definition and registers its statement block in
        self._contracts so function_def() can inject it at parse time.
        ContractDef is returned so it appears in the top-level statement
        list (for diagnostics / future tooling); codegen ignores it.
        Supports multiple comma-separated contracts on one function:
            def foo(int x) -> int : NonZero, Positive { ... };

        Optional binding syntax (after the ';'):
            contract MyC(a,b) { } # binding { this : OtherContract };
            contract MyC(a,b) { } # binding { this : OtherContract(3) };
            contract MyC(a,b) { } # binding { this : C1, C2 };
            contract MyC(a,b) { } # binding { this : C1 | C2 };
            contract MyC(a,b) { } # binding { this : C1 & !C2 };
            contract MyC(a,b) { } # binding { this, C1 :! };
            contract MyC(a,b) { } # binding { this :! };
        """
        tok = self.current_token
        self.consume(TokenType.CONTRACT)
        name = self.consume(TokenType.IDENTIFIER).value
        # Optional parameter list for parameterized contracts: contract Foo(a, b) { ... }
        params = []
        if self.expect(TokenType.LEFT_PAREN):
            self.advance()
            if not self.expect(TokenType.RIGHT_PAREN):
                params.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    params.append(self.consume(TokenType.IDENTIFIER).value)
            self.consume(TokenType.RIGHT_PAREN)
        # Forward declaration: contract Foo; or contract Foo(a,b); or comma list
        if self.expect(TokenType.SEMICOLON) or self.expect(TokenType.COMMA):
            # Collect all names in the declaration list
            entries = [(name, params)]
            while self.expect(TokenType.COMMA):
                self.advance()
                n = self.consume(TokenType.IDENTIFIER).value
                p = []
                if self.expect(TokenType.LEFT_PAREN):
                    self.advance()
                    if not self.expect(TokenType.RIGHT_PAREN):
                        p.append(self.consume(TokenType.IDENTIFIER).value)
                        while self.expect(TokenType.COMMA):
                            self.advance()
                            p.append(self.consume(TokenType.IDENTIFIER).value)
                    self.consume(TokenType.RIGHT_PAREN)
                entries.append((n, p))
            self.consume(TokenType.SEMICOLON)
            nodes = []
            for n, p in entries:
                if n not in self._contracts:
                    self._contracts[n] = (p, Block([]))
                nodes.append(ContractDef(n, Block([]), p, None).set_location(tok.line, tok.column))
            return nodes
        body = self.block()
        # Optional # binding { ... };
        # Syntax: contract MyC(a,b) { } # binding { pre : post };
        # The single trailing ';' follows the binding when present, or follows '}' directly.
        binding = None
        if self.expect(TokenType.TAG):
            # peek ahead: token after TAG should be identifier 'binding'
            next_tok = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
            if next_tok and next_tok.type == TokenType.IDENTIFIER and next_tok.value == 'binding':
                self.advance()  # consume TAG
                self.advance()  # consume 'binding' identifier
                self.consume(TokenType.LEFT_BRACE)
                binding = self._parse_binding_spec()
                self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        self._contracts[name] = (params, body)
        # Store binding keyed by contract name for validation at function sites
        if binding is not None:
            self._contract_bindings[name] = binding
        return ContractDef(name, body, params, binding).set_location(tok.line, tok.column)

    def _parse_binding_spec(self) -> dict:
        """
        Parse the interior of a # binding { ... } annotation.

        Grammar:
            binding_spec = pre_side ':' post_side

            pre_side  = '!'                          # no pre-contract allowed
                      | pre_name (',' pre_name)*     # named pre-contracts (first = 'this')

            pre_name  = 'this' | IDENTIFIER

            post_side = '!'                          # no post-contract allowed
                      | binding_ref (op binding_ref)*

            op        = ',' | '|' | '&'

            binding_ref = '!'? IDENTIFIER ('(' INT ')')?

        Returns a dict:
            {
                'pre':    list of str  ('!' for no-contract, or names including 'this'),
                'post':   list of (name, arity_or_None, negated),
                'post_op': ',' | '|' | '&' | None
            }
        """
        # Parse pre-side
        pre = []
        if self.expect(TokenType.NOT):
            # '!' alone = no-contract on pre side
            self.advance()
            pre = ['!']
        else:
            # Expect 'this' (THIS token) or IDENTIFIER
            if self.expect(TokenType.THIS):
                pre.append('this')
                self.advance()
            else:
                pre.append(self.consume(TokenType.IDENTIFIER).value)
            while self.expect(TokenType.COMMA):
                self.advance()  # consume comma
                if self.expect(TokenType.THIS):
                    pre.append('this')
                    self.advance()
                else:
                    pre.append(self.consume(TokenType.IDENTIFIER).value)

        self.consume(TokenType.COLON)

        # Parse post-side
        # Helper: consume a contract name on the post-side (IDENTIFIER or 'this' keyword)
        def _consume_binding_name():
            if self.expect(TokenType.THIS):
                self.advance()
                return 'this'
            return self.consume(TokenType.IDENTIFIER).value

        post = []
        post_op = None
        if self.expect(TokenType.NOT):
            # Check if next is a RIGHT_BRACE (bare '!' = no-contract) or a name (negated ref)
            next_pos = self.position + 1
            next_tok = self.tokens[next_pos] if next_pos < len(self.tokens) else None
            if next_tok and next_tok.type == TokenType.RIGHT_BRACE:
                self.advance()  # consume '!'
                post = [('!', None, False)]
            else:
                # '!Name' -- a negated contract ref
                self.advance()  # consume '!'
                ref_name = _consume_binding_name()
                arity = None
                if self.expect(TokenType.LEFT_PAREN):
                    self.advance()
                    arity = int(self.consume(TokenType.SINT_LITERAL).value)
                    self.consume(TokenType.RIGHT_PAREN)
                post.append((ref_name, arity, True))
                # Continue with operator chain
                while self.expect(TokenType.COMMA) or self.expect(TokenType.LOGICAL_OR) or self.expect(TokenType.LOGICAL_AND):
                    op = self.current_token
                    if op.type == TokenType.COMMA:
                        cur_op = ','
                    elif op.type == TokenType.LOGICAL_OR:
                        cur_op = '|'
                    else:
                        cur_op = '&'
                    if post_op is None:
                        post_op = cur_op
                    elif post_op != cur_op:
                        self.error("Mixed operators in # binding post-side are not allowed; use the same operator throughout")
                    self.advance()
                    negated = False
                    if self.expect(TokenType.NOT):
                        self.advance()
                        negated = True
                    ref_name = _consume_binding_name()
                    arity = None
                    if self.expect(TokenType.LEFT_PAREN):
                        self.advance()
                        arity = int(self.consume(TokenType.SINT_LITERAL).value)
                        self.consume(TokenType.RIGHT_PAREN)
                    post.append((ref_name, arity, negated))
        else:
            # Named contract ref (possibly negated, possibly with arity)
            negated = False
            if self.expect(TokenType.NOT):
                self.advance()
                negated = True
            ref_name = _consume_binding_name()
            arity = None
            if self.expect(TokenType.LEFT_PAREN):
                self.advance()
                arity = int(self.consume(TokenType.SINT_LITERAL).value)
                self.consume(TokenType.RIGHT_PAREN)
            post.append((ref_name, arity, negated))
            # Operator chain
            while self.expect(TokenType.COMMA) or self.expect(TokenType.LOGICAL_OR) or self.expect(TokenType.LOGICAL_AND):
                op = self.current_token
                if op.type == TokenType.COMMA:
                    cur_op = ','
                elif op.type == TokenType.LOGICAL_OR:
                    cur_op = '|'
                else:
                    cur_op = '&'
                if post_op is None:
                    post_op = cur_op
                elif post_op != cur_op:
                    self.error("Mixed operators in # binding post-side are not allowed; use the same operator throughout")
                self.advance()
                negated = False
                if self.expect(TokenType.NOT):
                    self.advance()
                    negated = True
                ref_name = _consume_binding_name()
                arity = None
                if self.expect(TokenType.LEFT_PAREN):
                    self.advance()
                    arity = int(self.consume(TokenType.SINT_LITERAL).value)
                    self.consume(TokenType.RIGHT_PAREN)
                post.append((ref_name, arity, negated))

        return {'pre': pre, 'post': post, 'post_op': post_op}

    def constra_def(self) -> 'ConstraDef':
        """
        constra_def -> 'constra' IDENTIFIER '(' param_list ')' '{' relation_list '}' ';'
                     | 'constra' IDENTIFIER '{' relation_list '}' ';'
                     | 'constra' IDENTIFIER '=' IDENTIFIER ('+' IDENTIFIER)* ';'

        Parses a named relational constraint set and registers it in self._constras.
        Relations use the formal parameter names declared in the constra parameter list.

        Syntax:
            constra MyCS(A, B)
            {
                A ~= B
            };

        Merge syntax (union of two or more existing constraint sets):
            constra MyCS3 = MyCS1 + MyCS2;

        All sources must have the same arity. The merged set adopts the
        parameter names of the first source unless an explicit rename list
        is supplied before '=':
            constra MyCS3(M, N) = MyCS1 + MyCS2;

        Relations from all sources are concatenated after remapping each
        source's formal parameter names to the final parameter names.
        Mutex pairs (~= / !~= and !`<= / !`>=) are detected at merge time.
        """
        tok = self.current_token
        self.consume(TokenType.CONSTRAINT)
        name = self.consume(TokenType.IDENTIFIER).value
        # Optional rename param list before '=': constra A(M,N) = B + C;
        rename_params = None
        if self.expect(TokenType.LEFT_PAREN) and not self.expect(TokenType.LEFT_BRACE):
            # Speculatively parse the param list; only treat as rename if '=' follows.
            _saved_pos = self.position
            _saved_tok = self.current_token
            self.advance()  # consume '('
            _rp = []
            if not self.expect(TokenType.RIGHT_PAREN):
                _rp.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    _rp.append(self.consume(TokenType.IDENTIFIER).value)
            self.consume(TokenType.RIGHT_PAREN)
            if self.expect(TokenType.ASSIGN):
                rename_params = _rp
            else:
                # Not a merge -- restore and fall through to normal constra body parse
                self.position = _saved_pos
                self.current_token = _saved_tok
        # Merge form: constra A = B + C;  or  constra A(M,N) = B + C;
        if self.expect(TokenType.ASSIGN):
            self.advance()
            sources = []  # list of (src_name, src_params, src_relations)
            def _collect_one():
                src_tok = self.current_token
                src_name = self.consume(TokenType.IDENTIFIER).value
                if src_name not in self._constras:
                    self.current_token = src_tok
                    self.error(f"Unknown constraint set '{src_name}' in constra merge")
                src_params, src_relations = self._constras[src_name]
                sources.append((src_name, src_params, src_relations))
            _collect_one()
            while self.expect(TokenType.PLUS):
                self.advance()
                _collect_one()
            self.consume(TokenType.SEMICOLON)
            # Arity check: all sources must have the same number of parameters
            base_arity = len(sources[0][1])
            for src_name, src_params, _ in sources[1:]:
                if len(src_params) != base_arity:
                    self.current_token = tok
                    self.error(
                        f"Cannot merge constraint sets of different arity: "
                        f"'{sources[0][0]}' has {base_arity} parameter(s) but "
                        f"'{src_name}' has {len(src_params)}"
                    )
            # Determine final param names
            if rename_params is not None:
                if len(rename_params) != base_arity:
                    self.current_token = tok
                    self.error(
                        f"Rename parameter list has {len(rename_params)} name(s) but "
                        f"merged constraint sets have arity {base_arity}"
                    )
                final_params = rename_params
            else:
                # Use first source's param names
                final_params = list(sources[0][1])
            # Build merged relations, remapping each source's formal params -> final_params
            merged_relations = []
            for _, src_params, src_relations in sources:
                mapping = dict(zip(src_params, final_params))
                for lhs_f, op_f, rhs_f in src_relations:
                    merged_relations.append(
                        ([mapping.get(n, n) for n in lhs_f], op_f,
                         [mapping.get(n, n) for n in rhs_f])
                    )
            # Mutex conflict check: certain op pairs on the same (lhs, rhs) cannot both hold
            # Mutex pairs: (~= , !~=) and (!`<= , !`>=)
            _MUTEX_PAIRS = [
                ("~=", "!~="),
                ("!`<=", "!`>="),
            ]
            _mutex_map = {}
            for _ma, _mb in _MUTEX_PAIRS:
                _mutex_map[_ma] = _mb
                _mutex_map[_mb] = _ma
            _seen_ops = {}  # (frozenset(lhs), frozenset(rhs)) -> set of ops
            for lhs_r, op_r, rhs_r in merged_relations:
                _key = (frozenset(lhs_r), frozenset(rhs_r))
                _ops = _seen_ops.setdefault(_key, set())
                if op_r in _mutex_map and _mutex_map[op_r] in _ops:
                    _lhs_str = ' & '.join(sorted(lhs_r))
                    _rhs_str = ' & '.join(sorted(rhs_r))
                    self.current_token = tok
                    self.error(
                        f"Conflicting constraints in merge '{name}': "
                        f"'{_lhs_str} {_mutex_map[op_r]} {_rhs_str}' and "
                        f"'{_lhs_str} {op_r} {_rhs_str}' "
                        f"cannot be true simultaneously"
                    )
                _ops.add(op_r)
            self._constras[name] = (final_params, merged_relations)
            return ConstraDef(name, final_params, merged_relations).set_location(tok.line, tok.column)
        params = []
        if self.expect(TokenType.LEFT_PAREN):
            self.advance()
            if not self.expect(TokenType.RIGHT_PAREN):
                params.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    params.append(self.consume(TokenType.IDENTIFIER).value)
            self.consume(TokenType.RIGHT_PAREN)
        self.consume(TokenType.LEFT_BRACE)
        # Record the source position of the body start for raw text extraction
        _body_start_line = self.current_token.line if self.current_token else 0
        relations = []
        def _parse_id_list_cs():
            # Parse a list of names joined by &.
            # Each element is a bare IDENTIFIER or a bracket group [A & B & ...].
            # e.g: B & [A !@ A]  or  D & E & [F & G]
            def _one_element():
                if self.expect(TokenType.LEFT_BRACKET):
                    self.advance()
                    # Inside brackets is a full relation: A !@ A, or A & B ~= C etc.
                    # Parse the id list, operator, and rhs, emit as a relation,
                    # and return the combined names for chaining.
                    ns = [self.consume(TokenType.IDENTIFIER).value]
                    while self.expect(TokenType.LOGICAL_AND):
                        nxt = self.peek(1)
                        if nxt and nxt.type == TokenType.IDENTIFIER:
                            self.advance()
                            ns.extend([self.consume(TokenType.IDENTIFIER).value])
                        else:
                            break
                    if self._is_relconstraint_op():
                        op = self._consume_relconstraint_op()
                        rhs_ns = [self.consume(TokenType.IDENTIFIER).value]
                        while self.expect(TokenType.LOGICAL_AND):
                            nxt = self.peek(1)
                            if nxt and nxt.type == TokenType.IDENTIFIER:
                                self.advance()
                                rhs_ns.append(self.consume(TokenType.IDENTIFIER).value)
                            else:
                                break
                        relations.append((ns, op, rhs_ns))
                        ns = rhs_ns
                    self.consume(TokenType.RIGHT_BRACKET)
                    return ns
                return [self.consume(TokenType.IDENTIFIER).value]

            names = _one_element()
            # Keep consuming & elements as long as next is [ or IDENTIFIER
            while self.expect(TokenType.LOGICAL_AND):
                next_tok = self.peek(1)
                if next_tok and next_tok.type in (TokenType.IDENTIFIER, TokenType.LEFT_BRACKET):
                    self.advance()  # consume &
                    names.extend(_one_element())
                else:
                    break
            return names
        def _is_constraint_op():
            return self._is_relconstraint_op()
        def _parse_rel_expr():
            # Parse a chained relational expression: A ~= B !~= C ~= D ...
            # Each step: consume op, consume rhs id-list, emit a (lhs, op, rhs) tuple
            lhs = _parse_id_list_cs()
            while _is_constraint_op():
                op = self._consume_relconstraint_op()
                rhs = _parse_id_list_cs()
                relations.append((lhs, op, rhs))
                # rhs becomes lhs for next chained op
                lhs = rhs
        _parse_rel_expr()
        while not self.expect(TokenType.RIGHT_BRACE):
            if self.expect(TokenType.COMMA):
                self.advance()
            _parse_rel_expr()
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        self._constras[name] = (params, relations)
        cd = ConstraDef(name, params, relations).set_location(tok.line, tok.column)
        cd._body_start_line = _body_start_line
        cd._body_end_line   = self.current_token.line if self.current_token else _body_start_line
        return cd

    def function_def(self, calling_conv: Optional[str] = None) -> Union[FunctionDef, List[FunctionDef]]:
        """
        function_def -> ('const')? ('volatile')? ('inline')? ('def' | calling_conv_kw) ('!!')? (IDENTIFIER | STRING_LITERAL | F_STRING | I_STRING | STRINGIFY) '(' parameter_list? ')' '->' type_spec (';' | block ';')
        
        Now supports string literals as function names for mangled/decorated names:
            def "??@YAPAX?_FOO"()->void{};

        Also supports f-string, i-string, and stringify names evaluated at compile time:
            def f"{x}_{y}"() -> void {};
            def i"{}":{x * 333;}() -> void {};
            def $X() -> void {};

        Calling convention syntax (replaces 'def'):
            cdecl foo() -> void {};
            fastcall bar(int x) -> int {};
        """
        is_const = False
        is_volatile = False
        is_inline = False
        no_mangle = False
        tok = self.current_token
        
        if self.expect(TokenType.CONST):
            is_const = True
            self.advance()
        
        if self.expect(TokenType.VOLATILE):
            is_volatile = True
            self.advance()

        if self.expect(TokenType.INLINE):
            is_inline = True
            self.advance()
        
        # Consume 'def' OR a calling-convention keyword if present; bare functions omit both
        if self.current_token.type in _CALLING_CONV_TOKENS:
            # Calling convention keyword stands in place of 'def'
            calling_conv = _CALLING_CONV_TOKEN_TO_STR[self.current_token.type]
            self.advance()
        elif self.expect(TokenType.DEF):
            self.advance()
        
        # Check if this is a function pointer declaration (def{}* or cc{}*)
        if self.expect(TokenType.FUNCTION_POINTER):
            self.advance()  # consume the {}* token
            return self.function_pointer_declaration(calling_conv=calling_conv)

        if calling_conv == 'cdecl':
            no_mangle = True
        
        if self.expect(TokenType.NO_MANGLE):
            no_mangle = True
            self.consume(TokenType.NO_MANGLE)
        
        # Function name can be an IDENTIFIER, STRING_LITERAL, F_STRING, I_STRING, or STRINGIFY
        if self.expect(TokenType.STRING_LITERAL):
            # String literal function name (e.g., for mangled names)
            name = self.consume(TokenType.STRING_LITERAL).value
            # Note: The string literal includes quotes, you may want to strip them
            # name = name.strip('"')  # Uncomment if you want to remove quotes
        elif self.expect(TokenType.F_STRING):
            # F-string function name (e.g., def f"{x} {y}"() -> void)
            # Stored as a FStringLiteral node; codegen evaluates it at compile time.
            tok = self.current_token
            name = self.parse_f_string(self.consume(TokenType.F_STRING).value).set_location(tok.line, tok.column)
        elif self.expect(TokenType.I_STRING):
            # I-string function name (e.g., def i"{}":{x * 333;}() -> void)
            # Stored as a FStringLiteral node; codegen evaluates it at compile time.
            tok = self.current_token
            name = self.parse_i_string(self.consume(TokenType.I_STRING).value).set_location(tok.line, tok.column)
        elif self.expect(TokenType.STRINGIFY):
            # Stringify function name (e.g., def $X() -> void)
            # Also handles def $~$T() where codify binds tighter than stringify.
            tok = self.current_token
            self.advance()
            if self.expect(TokenType.CODIFY):
                resolved = self._consume_codify()
                name = StringLiteral(resolved).set_location(tok.line, tok.column)
            else:
                if not self.expect(TokenType.IDENTIFIER):
                    self.error("Expected identifier after '$' in function name", TokenType.IDENTIFIER)
                str_name = self.current_token.value
                self.advance()
                str_member = None
                if self.expect(TokenType.DOT):
                    self.advance()
                    if self.expect(TokenType.IDENTIFIER):
                        str_member = self.current_token.value
                        self.advance()
                    elif self.expect(TokenType.TAG):
                        self.advance()
                        str_member = "#"
                    else:
                        self.error("Expected member name after '.' in stringify function name", TokenType.IDENTIFIER)
                name = Stringify(str_name, str_member).set_location(tok.line, tok.column)
        elif self.expect(TokenType.IDENTIFIER):
            name = self.consume(TokenType.IDENTIFIER).value
        else:
            self.error("Expected function name (identifier or string literal)", TokenType.IDENTIFIER)
        
        # Parse optional template parameter list: def name<T, U>(...)
        # Supports optional per-param constraints: def name<T: type1 | type2, U>(...)
        # Use lookahead to confirm this is actually a template list (all IDENTIFIERs,
        # with optional ': ...' constraint clauses) before consuming anything, to
        # avoid misreading comparison operators.
        template_params = []
        _func_constraints = {}
        _func_relations = []
        _func_defaults = {}
        _func_no_default = set()
        if self.expect(TokenType.LESS_THAN):
            with self._lookahead():
                is_template = False
                self.advance()  # consume '<'
                # Accept optional <!+ prefix on first entry
                if self.expect(TokenType.NOT):
                    self.advance()
                    if self.expect(TokenType.PLUS):
                        self.advance()
                if self.expect(TokenType.CODIFY):
                    self.advance()
                    if self.expect(TokenType.IDENTIFIER, TokenType.F_STRING, TokenType.I_STRING):
                        self.advance()
                # Helper used in lookahead to skip ':{' ... '}'
                def _la_skip_constraint_set_fd():
                    self.advance()  # consume ':'
                    self.advance()  # consume '{'
                    depth = 1
                    while not self.expect(TokenType.EOF):
                        if self.expect(TokenType.LEFT_BRACE):
                            depth += 1
                            self.advance()
                        elif self.expect(TokenType.RIGHT_BRACE):
                            depth -= 1
                            self.advance()
                            if depth == 0:
                                break
                        else:
                            self.advance()
                # Helper to skip a type-constraint value after ':' (not followed by '{')
                def _la_skip_type_constraint_fd():
                    depth = 0
                    while not self.expect(TokenType.EOF):
                        if self.expect(TokenType.LESS_THAN):
                            depth += 1
                            self.advance()
                        elif self.expect(TokenType.GREATER_THAN):
                            if depth == 0:
                                break
                            depth -= 1
                            self.advance()
                        elif self.expect(TokenType.COMMA) and depth == 0:
                            break
                        else:
                            self.advance()
                # First entry: ':{...}' constraint set, identifier param, or bare relation (accepted
                # in lookahead so the real parse can emit a proper error for it)
                _la_first_ok = False
                if self.expect(TokenType.COLON):
                    _la_saved = self.position
                    self.advance()
                    if self.expect(TokenType.LEFT_BRACE):
                        self.position = _la_saved
                        self.current_token = self.tokens[self.position]
                        _la_skip_constraint_set_fd()
                        _la_first_ok = True
                    else:
                        self.position = _la_saved
                        self.current_token = self.tokens[self.position]
                elif self.expect(TokenType.IDENTIFIER):
                    self.advance()
                    if self.expect(TokenType.COLON):
                        self.advance()
                        _la_skip_type_constraint_fd()
                    else:
                        # Skip optional '&' IDENTIFIER chain and relation op
                        # (bare relation - accepted here so real parse can error properly)
                        while self.expect(TokenType.LOGICAL_AND):
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER):
                                self.advance()
                        if self._is_relconstraint_op() and not self.expect(TokenType.TIE):
                            # !`< !`<= !`> !`>= - skip op then rhs identifier chain
                            self._skip_relconstraint_op()
                            if self.expect(TokenType.IDENTIFIER):
                                self.advance()
                                while self.expect(TokenType.LOGICAL_AND):
                                    self.advance()
                                    if self.expect(TokenType.IDENTIFIER):
                                        self.advance()
                        elif self.expect(TokenType.TIE) and self.peek(1) and self.peek(1).type == TokenType.ASSIGN:
                            self.advance()
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER):
                                self.advance()
                                while self.expect(TokenType.LOGICAL_AND):
                                    self.advance()
                                    if self.expect(TokenType.IDENTIFIER):
                                        self.advance()
                        elif self.expect(TokenType.NOT) and self.peek(1) and self.peek(1).type == TokenType.TIE \
                                and self.peek(2) and self.peek(2).type == TokenType.ASSIGN:
                            self.advance()
                            self.advance()
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER):
                                self.advance()
                                while self.expect(TokenType.LOGICAL_AND):
                                    self.advance()
                                    if self.expect(TokenType.IDENTIFIER):
                                        self.advance()
                    _la_first_ok = True
                if _la_first_ok:
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        if self.expect(TokenType.NOT):
                            self.advance()
                            if self.expect(TokenType.PLUS):
                                self.advance()
                        if self.expect(TokenType.COLON):
                            _la_saved2 = self.position
                            self.advance()
                            if self.expect(TokenType.LEFT_BRACE):
                                self.position = _la_saved2
                                self.current_token = self.tokens[self.position]
                                _la_skip_constraint_set_fd()
                            else:
                                self.position = _la_saved2
                                self.current_token = self.tokens[self.position]
                                break
                        elif self.expect(TokenType.CODIFY):
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER, TokenType.F_STRING, TokenType.I_STRING):
                                self.advance()  # consume token after CODIFY
                            if self.expect(TokenType.COLON):
                                self.advance()
                                _la_skip_type_constraint_fd()
                        elif not self.expect(TokenType.IDENTIFIER):
                            break
                        else:
                            self.advance()
                            if self.expect(TokenType.COLON):
                                self.advance()
                                _la_skip_type_constraint_fd()
                            else:
                                # Skip bare relation in subsequent entry
                                while self.expect(TokenType.LOGICAL_AND):
                                    self.advance()
                                    if self.expect(TokenType.IDENTIFIER):
                                        self.advance()
                                if self._is_relconstraint_op():
                                    self._skip_relconstraint_op()
                                    if self.expect(TokenType.IDENTIFIER):
                                        self.advance()
                                        while self.expect(TokenType.LOGICAL_AND):
                                            self.advance()
                                            if self.expect(TokenType.IDENTIFIER):
                                                self.advance()
                    if self.expect(TokenType.GREATER_THAN):
                        is_template = True

            if is_template:
                (template_params, _func_constraints,
                 _func_relations, _func_defaults,
                 _func_no_default) = self._parse_template_param_list(allow_codify=False)

        # Expose template param names so type_spec() can detect and defer
        # myStru<T>-style type arguments that are still unresolved template params.
        _tmpl_scope_ctx = self._template_scope(template_params if template_params else [])
        _tmpl_scope_ctx.__enter__()
        self.consume(TokenType.LEFT_PAREN)
        parameters = []
        if not self.expect(TokenType.RIGHT_PAREN):
            parameters = self.parameter_list()
        self.consume(TokenType.RIGHT_PAREN)
        
        is_recursive = False
        if self.expect(TokenType.RECURSE_ARROW):
            is_recursive = True
            self.advance()
        else:
            self.consume(TokenType.RETURN_ARROW)
        return_type = self.type_spec()

        # Parse optional error channel type: -> int ^| ErrType
        error_type = None
        if self.expect(TokenType.XOR_OP):
            self.advance()
            error_type = self.type_spec()

        # NOTE: _active_template_params intentionally stays set through the body parse
        # so that template struct usages inside the body (e.g. myStru<T> x;) are also
        # deferred correctly.  It is restored after the entire function is parsed.

        # Tag annotation variables -- always initialized here so they are defined
        # regardless of which branch below is taken.
        is_deprecated = False
        effect_ann = None
        attenuate_ann = None

        # Pattern: def foo() -> int, foo() -> bool, foo(int) -> void;
        if self.expect(TokenType.TAG) or self.expect(TokenType.COMMA):
            # Check if this is a multi-function prototype declaration or just tags on a single prototype
            # Parse any tags that appear before the comma
            _first_effect_ann = None
            _first_attenuate_ann = None
            _first_deprecated = False
            while self.expect(TokenType.TAG):
                self.advance()
                if self.expect(TokenType.DEPRECATE):
                    self.advance()
                    _first_deprecated = True
                elif self.expect(TokenType.EFFECT):
                    self.advance()
                    self.consume(TokenType.LEFT_BRACE)
                    _first_effect_ann = EffectAnnotation(self._parse_effect_expr())
                    self.consume(TokenType.RIGHT_BRACE)
                elif self.expect(TokenType.IDENTIFIER) and self.current_token.value == 'attenuate':
                    self.advance()
                    self.consume(TokenType.LEFT_BRACE)
                    _first_attenuate_ann = AttenuateAnnotation(self._parse_effect_expr())
                    self.consume(TokenType.RIGHT_BRACE)
                else:
                    self.error("Expected 'deprecate', 'effect', or 'attenuate' after '#'")

            if self.expect(TokenType.COMMA):
                # This is a multi-function prototype declaration
                prototypes = []

                # Detect variadic sentinel in first prototype's parameters
                _is_var = any(getattr(p, '_is_variadic_sentinel', False) for p in parameters)
                _real_params = [p for p in parameters if not getattr(p, '_is_variadic_sentinel', False)]
                
                # Add the first prototype with its tags
                _first_fd = FunctionDef(name, _real_params, return_type, Block([]),
                                        is_const, is_volatile, True, no_mangle, _is_var, calling_conv,
                                        False, is_inline, _first_deprecated, _first_effect_ann, _first_attenuate_ann,
                                        error_type=error_type)
                prototypes.append(_first_fd)
                
                # Parse additional prototypes
                while self.expect(TokenType.COMMA):
                    self.advance()  # consume comma
                    
                    # Each additional prototype has its own name (can also be string literal, f-string, or i-string)
                    if self.expect(TokenType.STRING_LITERAL):
                        proto_name = self.consume(TokenType.STRING_LITERAL).value
                    elif self.expect(TokenType.F_STRING):
                        tok = self.current_token
                        proto_name = self.parse_f_string(self.consume(TokenType.F_STRING).value).set_location(tok.line, tok.column)
                    elif self.expect(TokenType.I_STRING):
                        tok = self.current_token
                        proto_name = self.parse_i_string(self.consume(TokenType.I_STRING).value).set_location(tok.line, tok.column)
                    elif self.expect(TokenType.STRINGIFY):
                        tok = self.current_token
                        self.advance()
                        if self.expect(TokenType.CODIFY):
                            resolved = self._consume_codify()
                            proto_name = StringLiteral(resolved).set_location(tok.line, tok.column)
                        else:
                            if not self.expect(TokenType.IDENTIFIER):
                                self.error("Expected identifier after '$' in function name", TokenType.IDENTIFIER)
                            _sn = self.current_token.value
                            self.advance()
                            _sm = None
                            if self.expect(TokenType.DOT):
                                self.advance()
                                if self.expect(TokenType.IDENTIFIER):
                                    _sm = self.current_token.value
                                    self.advance()
                                elif self.expect(TokenType.TAG):
                                    self.advance()
                                    _sm = "#"
                                else:
                                    self.error("Expected member name after '.' in stringify function name", TokenType.IDENTIFIER)
                            proto_name = Stringify(_sn, _sm).set_location(tok.line, tok.column)
                    elif self.expect(TokenType.IDENTIFIER):
                        proto_name = self.consume(TokenType.IDENTIFIER).value
                    else:
                        self.error("Expected function name (identifier or string literal)", TokenType.IDENTIFIER)

                    # Optional template params for this prototype: name<T, U>(...)
                    proto_template_params = []
                    if self.expect(TokenType.LESS_THAN):
                        with self._lookahead():
                            _is_tmpl = False
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER):
                                self.advance()
                                while self.expect(TokenType.COMMA):
                                    self.advance()
                                    if not self.expect(TokenType.IDENTIFIER):
                                        break
                                    self.advance()
                                if self.expect(TokenType.GREATER_THAN):
                                    _is_tmpl = True
                        if _is_tmpl:
                            self.advance()  # consume '<'
                            proto_template_params.append(self.consume(TokenType.IDENTIFIER).value)
                            while self.expect(TokenType.COMMA):
                                self.advance()
                                proto_template_params.append(self.consume(TokenType.IDENTIFIER).value)
                            self.consume(TokenType.GREATER_THAN)
                    with self._template_scope(proto_template_params if proto_template_params else []):
                    
                        self.consume(TokenType.LEFT_PAREN)
                        proto_parameters = []
                        if not self.expect(TokenType.RIGHT_PAREN):
                            proto_parameters = self.parameter_list()
                        self.consume(TokenType.RIGHT_PAREN)
                    
                        self.consume(TokenType.RETURN_ARROW)
                        proto_return_type = self.type_spec()
                        # Parse optional error channel type for this prototype
                        proto_error_type = None
                        if self.expect(TokenType.XOR_OP):
                            self.advance()
                            proto_error_type = self.type_spec()

                    # Parse tags for this prototype entry
                    _proto_effect_ann = None
                    _proto_attenuate_ann = None
                    _proto_deprecated = False
                    while self.expect(TokenType.TAG):
                        self.advance()
                        if self.expect(TokenType.DEPRECATE):
                            self.advance()
                            _proto_deprecated = True
                        elif self.expect(TokenType.EFFECT):
                            self.advance()
                            self.consume(TokenType.LEFT_BRACE)
                            _proto_effect_ann = EffectAnnotation(self._parse_effect_expr())
                            self.consume(TokenType.RIGHT_BRACE)
                        elif self.expect(TokenType.IDENTIFIER) and self.current_token.value == 'attenuate':
                            self.advance()
                            self.consume(TokenType.LEFT_BRACE)
                            _proto_attenuate_ann = AttenuateAnnotation(self._parse_effect_expr())
                            self.consume(TokenType.RIGHT_BRACE)
                        else:
                            self.error("Expected 'deprecate', 'effect', or 'attenuate' after '#'")

                    _proto_is_var = any(getattr(p, '_is_variadic_sentinel', False) for p in proto_parameters)
                    _proto_real = [p for p in proto_parameters if not getattr(p, '_is_variadic_sentinel', False)]

                    # no_mangle applies to ALL functions in this comma-separated list
                    _proto_fd = FunctionDef(proto_name, _proto_real, proto_return_type,
                                            Block([]), is_const, is_volatile, True, no_mangle, _proto_is_var, calling_conv,
                                            False, is_inline, _proto_deprecated, _proto_effect_ann, _proto_attenuate_ann,
                                            error_type=proto_error_type)
                    if proto_template_params:
                        _proto_fd._is_trait_template_proto = True
                    prototypes.append(_proto_fd)
                
                self.consume(TokenType.SEMICOLON)
                
                # Restore active template params - this early return bypasses the normal restore at end of function_def.
                _tmpl_scope_ctx.__exit__(None, None, None)
                # Return the list of prototypes
                return [fd.set_location(tok.line, tok.column) for fd in prototypes]

            # Single prototype with tags -- fall through to normal prototype/definition path
            # carrying the parsed tags into the tag variables below
            is_deprecated = _first_deprecated
            effect_ann = _first_effect_ann
            attenuate_ann = _first_attenuate_ann
        # Resolve contract(s): def foo(int x) -> int : NonZero, LessThan(y,x) { ... }
        contract_stmts = []
        _pre_contract_names = []
        _pre_contract_arities = []
        if self.expect(TokenType.COLON):
            self.advance()
            contract_name, call_args = self._parse_contract_ref()
            if contract_name not in self._contracts:
                self.error(f"Undefined contract '{contract_name}'")
            contract_stmts.extend(self._resolve_contract(contract_name, parameters, call_args))
            _pre_contract_names.append(contract_name)
            _pre_contract_arities.append(len(call_args) if call_args is not None else None)
            # Support multiple contracts: : NonZero, Positive
            while self.expect(TokenType.COMMA):
                self.advance()
                contract_name, call_args = self._parse_contract_ref()
                if contract_name not in self._contracts:
                    self.error(f"Undefined contract '{contract_name}'")
                contract_stmts.extend(self._resolve_contract(contract_name, parameters, call_args))
                _pre_contract_names.append(contract_name)
                _pre_contract_arities.append(len(call_args) if call_args is not None else None)

        is_prototype = False
        body = None

        # Detect and strip variadic sentinel parameters
        is_variadic = any(getattr(p, '_is_variadic_sentinel', False) for p in parameters)
        real_parameters = [p for p in parameters if not getattr(p, '_is_variadic_sentinel', False)]
        
        # Validate <~ recursive function constraints
        if is_recursive:
            _ret_is_void = (
                (hasattr(return_type, 'base_type') and return_type.base_type == DataType.VOID)
                or repr(return_type) == 'void'
                or str(return_type) == 'void'
            )
            is_void_form = (len(real_parameters) == 0 and _ret_is_void)
            is_single_param_form = (len(real_parameters) == 1 and repr(real_parameters[0].type_spec) == repr(return_type))
            if not is_void_form and not is_single_param_form:
                if len(real_parameters) == 0:
                    self.error(f"Recursive function '{name}' with no parameters must return void")
                elif len(real_parameters) == 1:
                    self.error(f"Recursive function '{name}': return type must match parameter type")
                else:
                    self.error(f"Recursive function '{name}' declared with '<~' must have exactly one parameter, or no parameters with void return")

        # Parse optional 'as operator[sym]' or 'as operator[sym1][sym2]' suffix.
        # Present before the prototype ';' or the definition body '{'.
        _as_op_symbol = None   # left (or only) operator symbol string
        _as_op_symbol2 = None  # right operator symbol string (ternary only)
        _as_op_binding = None  # None | 'prefix' | 'postfix' (unary)
        if self.expect(TokenType.AS):
            self.advance()  # consume 'as'
            self.consume(TokenType.OPERATOR)
            # Parse first bracket group
            self.consume(TokenType.LEFT_BRACKET)
            _as_tt1, _as_tv1 = [], []
            while not self.expect(TokenType.RIGHT_BRACKET):
                if self.current_token.type == TokenType.IDENTIFIER:
                    _as_tt1.append(TokenType.IDENTIFIER)
                    _as_tv1.append(self.current_token.value)
                elif self.current_token.type not in _TOKEN_SYMBOL_MAP:
                    self.error(f"Token '{self.current_token.value}' cannot be part of an operator symbol", TokenType.IDENTIFIER)
                else:
                    _as_tt1.append(self.current_token.type)
                    _as_tv1.append(None)
                self.advance()
            self.consume(TokenType.RIGHT_BRACKET)
            _as_op_symbol = self._tokens_to_op_key(_as_tt1, _as_tv1)
            # Optional second bracket group (ternary)
            if self.expect(TokenType.LEFT_BRACKET):
                self.consume(TokenType.LEFT_BRACKET)
                _as_tt2, _as_tv2 = [], []
                while not self.expect(TokenType.RIGHT_BRACKET):
                    if self.current_token.type == TokenType.IDENTIFIER:
                        _as_tt2.append(TokenType.IDENTIFIER)
                        _as_tv2.append(self.current_token.value)
                    elif self.current_token.type not in _TOKEN_SYMBOL_MAP:
                        self.error(f"Token '{self.current_token.value}' cannot be part of an operator symbol", TokenType.IDENTIFIER)
                    else:
                        _as_tt2.append(self.current_token.type)
                        _as_tv2.append(None)
                    self.advance()
                self.consume(TokenType.RIGHT_BRACKET)
                _as_op_symbol2 = self._tokens_to_op_key(_as_tt2, _as_tv2)
            # Optional unary binding (only when exactly one param and one symbol)
            if _as_op_symbol2 is None and self.expect(TokenType.TAG):
                _nb = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
                if _nb and _nb.type == TokenType.IDENTIFIER and _nb.value == 'binding':
                    if len(real_parameters) != 1:
                        self.error("# binding on 'as operator' is only valid for unary operators (exactly one parameter)")
                    self.advance()  # consume '#'
                    self.advance()  # consume 'binding'
                    self.consume(TokenType.LEFT_BRACE)
                    if self.expect(TokenType.COLON):
                        self.advance()
                        self.consume(TokenType.THIS)
                        _as_op_binding = 'postfix'
                    elif self.expect(TokenType.THIS):
                        self.advance()
                        self.consume(TokenType.COLON)
                        _as_op_binding = 'prefix'
                    else:
                        self.error("Unary # binding must be {:this} for postfix or {this:} for prefix")
                    self.consume(TokenType.RIGHT_BRACE)

        if self.expect(TokenType.TAG) or self.expect(TokenType.SEMICOLON):
            # Prototype path: parse any # tags then consume the semicolon.
            while self.expect(TokenType.TAG):
                self.advance()
                if self.expect(TokenType.DEPRECATE):
                    self.advance()
                    is_deprecated = True
                elif self.expect(TokenType.EFFECT):
                    self.advance()
                    self.consume(TokenType.LEFT_BRACE)
                    effect_expr = self._parse_effect_expr()
                    self.consume(TokenType.RIGHT_BRACE)
                    effect_ann = EffectAnnotation(effect_expr)
                elif self.expect(TokenType.IDENTIFIER) and self.current_token.value == 'attenuate':
                    self.advance()
                    self.consume(TokenType.LEFT_BRACE)
                    att_expr = self._parse_effect_expr()
                    self.consume(TokenType.RIGHT_BRACE)
                    attenuate_ann = AttenuateAnnotation(att_expr)
                else:
                    self.error("Expected 'deprecate', 'effect', or 'attenuate' after '#'")
            if self.expect(TokenType.SEMICOLON):
                is_prototype = True
                self.advance()
                body = Block([])
        elif self.expect(TokenType.RETURN_ARROW):
            # Brace-omitted single-statement return: name([params]) -> type -> expr;
            # If any real parameter lacks a name, this is an error for a definition
            for param in real_parameters:
                if param.name is None:
                    self.error(f"Function definition requires parameter names, but parameter of type {param.type_spec} has no name")
            if self._function_depth > 0:
                self.error(f"Illegal nested function definition '{name}': function definitions are not allowed inside another function body")
            for param in real_parameters:
                if param.name:
                    self.symbol_table.define(param.name, SymbolKind.VARIABLE, param.type_spec)
            self.advance()  # consume '->'
            self._function_depth += 1
            expr = self.expression()
            self._function_depth -= 1
            self.consume(TokenType.SEMICOLON)
            body = Block([ReturnStatement(expr)])
            is_prototype = False
        else:
            # Inside a trait body only prototypes are allowed - a missing ';' would
            # otherwise fall through to block() and emit a confusing LEFT_BRACE error.
            if self._in_trait and not self.expect(TokenType.LEFT_BRACE):
                prev = self.tokens[self.position - 1] if self.position > 0 else None
                self.error(
                    f"Expected {TokenType.SEMICOLON.name}, got {self.current_token.type.name}",
                    expected_type=TokenType.SEMICOLON,
                    prev_token=prev,
                )
            # If any real parameter lacks a name, this is an error for a definition
            for param in real_parameters:
                if param.name is None:
                    self.error(f"Function definition requires parameter names, but parameter of type {param.type_spec} has no name")
            if self._function_depth > 0:
                self.error(f"Illegal nested function definition '{name}': function definitions are not allowed inside another function body")
            # Register parameters in the symbol table BEFORE parsing the body so
            # that template inference inside the body (e.g. foo(a, 3) where 'a' is
            # a parameter with a known concrete type) can resolve argument types via
            # get_type_spec().  Without this, lookup returns None during body parsing
            # and inference falls back to an unresolved FunctionCall.
            for param in real_parameters:
                if param.name:
                    self.symbol_table.define(param.name, SymbolKind.VARIABLE, param.type_spec)
            self._function_depth += 1
            body = self.block()
            self._function_depth -= 1
            # Prepend pre-contract statements to the top of the function body
            if contract_stmts:
                body.statements = contract_stmts + body.statements
            # Post-contracts: } : ContractName, OtherContract;
            # The contract body sees 'r' as the return value.
            # Each return expr is rewritten to: r = expr; <asserts>; return r;
            post_contract_stmts = []
            _post_contract_names = []
            _post_contract_arities = []
            if self.expect(TokenType.COLON):
                self.advance()
                post_name, post_call_args = self._parse_contract_ref()
                if post_name not in self._contracts:
                    self.error(f"Undefined post-contract '{post_name}'")
                post_contract_stmts.extend(self._resolve_contract(post_name, parameters, post_call_args))
                _post_contract_names.append(post_name)
                _post_contract_arities.append(len(post_call_args) if post_call_args is not None else None)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    post_name, post_call_args = self._parse_contract_ref()
                    if post_name not in self._contracts:
                        self.error(f"Undefined post-contract '{post_name}'")
                    post_contract_stmts.extend(self._resolve_contract(post_name, parameters, post_call_args))
                    _post_contract_names.append(post_name)
                    _post_contract_arities.append(len(post_call_args) if post_call_args is not None else None)
            if post_contract_stmts:
                body = self._apply_post_contracts(body, return_type, post_contract_stmts)
            if _pre_contract_names or _post_contract_names:
                self._validate_contract_binding(name, _pre_contract_names, _pre_contract_arities,
                                                _post_contract_names, _post_contract_arities)
            # Parse optional # qualifier tags after the closing brace -- any order, any count.
            # Syntax: def foo() -> void { ... } # effect { expr } # attenuate { expr };
            while self.expect(TokenType.TAG):
                self.advance()
                if self.expect(TokenType.DEPRECATE):
                    self.advance()
                    is_deprecated = True
                elif self.expect(TokenType.EFFECT):
                    self.advance()
                    self.consume(TokenType.LEFT_BRACE)
                    effect_expr = self._parse_effect_expr()
                    self.consume(TokenType.RIGHT_BRACE)
                    effect_ann = EffectAnnotation(effect_expr)
                elif self.expect(TokenType.IDENTIFIER) and self.current_token.value == 'attenuate':
                    self.advance()
                    self.consume(TokenType.LEFT_BRACE)
                    att_expr = self._parse_effect_expr()
                    self.consume(TokenType.RIGHT_BRACE)
                    attenuate_ann = AttenuateAnnotation(att_expr)
                else:
                    self.error("Expected 'deprecate', 'effect', or 'attenuate' after '#'")
            self.consume(TokenType.SEMICOLON)
        
        # Restore the previous active template param set now that the entire function
        # (params, return type, and body) has been parsed.
        _tmpl_scope_ctx.__exit__(None, None, None)

        # If this is a template function, store it and return None (no immediate codegen)
        if template_params:
            func_def = FunctionDef(name, real_parameters, return_type, body, is_const,
                                   is_volatile, is_prototype, no_mangle, is_variadic, calling_conv,
                                   is_recursive, is_inline, is_deprecated, effect_ann, attenuate_ann,
                                   error_type=error_type)
            if self._in_comptime > 0:
                func_def._is_comptime_only = True
            self._register_template_function(name, template_params, func_def,
                                              _func_constraints, _func_relations,
                                              _func_defaults, _func_no_default)
            # Comptime template functions must be returned so the VM codegen sees
            # the definition and compiles it into compiled_functions.
            if self._in_comptime > 0:
                return func_def
            return None

        func_def = FunctionDef(name, real_parameters, return_type, body, is_const,
                               is_volatile, is_prototype, no_mangle, is_variadic, calling_conv,
                               is_recursive, is_inline, is_deprecated, effect_ann, attenuate_ann,
                               error_type=error_type).set_location(tok.line, tok.column)

        # Register 'as operator' if present
        if _as_op_symbol is not None:
            from ftypesys import Operator as _Operator
            _builtin_op_values = {op.value for op in _Operator}
            if _as_op_symbol2 is not None:
                if len(real_parameters) == 1:
                    # Circumfix 'as operator': [lop] x [rop]
                    self._custom_circumfix_ops[(_as_op_symbol, _as_op_symbol2)] = name
                elif len(real_parameters) == 3:
                    # Ternary 'as operator': a [lop] b [rop] c
                    self._custom_ternary_ops[(_as_op_symbol, _as_op_symbol2)] = name
                else:
                    self.error("Two-bracket 'as operator' requires either 1 parameter (circumfix) or 3 parameters (ternary)")
                self.symbol_table.define(_as_op_symbol2, SymbolKind.OPERATOR)
            elif _as_op_binding is not None:
                # Unary
                if _as_op_binding == 'prefix':
                    self._custom_prefix_ops[_as_op_symbol] = name
                else:
                    self._custom_postfix_ops[_as_op_symbol] = name
            elif _as_op_symbol in _builtin_op_values:
                if not template_params:
                    def _is_non_builtin(ts):
                        return (ts.custom_typename is not None or
                                ts.base_type in (DataType.STRUCT, DataType.OBJECT, DataType.DATA) or
                                ts.is_pointer)
                    if not any(_is_non_builtin(p.type_spec) for p in real_parameters):
                        self.error(
                            f"Overloading built-in operator '{_as_op_symbol}' requires at least "
                            f"one parameter to be a non-builtin type"
                        )
            else:
                self._custom_operators[_as_op_symbol] = name
            self.symbol_table.define(_as_op_symbol, SymbolKind.OPERATOR)

        return func_def

    def _is_function_pointer_declaration(self) -> bool:
        """
        Check if current position starts a function pointer declaration.
        
        Pattern: return_type{}* identifier(param_types)
        Example: void{}* fp()
        """
        with self._lookahead():
            # Skip storage class and qualifiers
            if self.expect(TokenType.GLOBAL, TokenType.LOCAL, TokenType.HEAP, 
                          TokenType.STACK, TokenType.REGISTER, TokenType.SINGINIT):
                self.advance()
            if self.expect(TokenType.CONST):
                self.advance()
            if self.expect(TokenType.VOLATILE):
                self.advance()
            if self.expect(TokenType.SIGNED, TokenType.UNSIGNED):
                self.advance()
            
            # Must have a base type
            if not self.expect(TokenType.SINT, TokenType.FLOAT_KW, TokenType.DOUBLE_KW, TokenType.CHAR, 
                              TokenType.BOOL_KW, TokenType.DATA, TokenType.VOID, 
                              TokenType.SLONG, TokenType.ULONG,
                              TokenType.IDENTIFIER):
                return False
            
            self.advance()
            
            # Check for {}* pattern
            if not self.expect(TokenType.LEFT_BRACE):
                return False
            self.advance()
            
            if not self.expect(TokenType.RIGHT_BRACE):
                return False
            self.advance()
            
            if not self.expect(TokenType.MULTIPLY):
                return False
            self.advance()
            
            # Must have identifier
            if not self.expect(TokenType.IDENTIFIER):
                return False
            self.advance()
            
            # Must have parameter list
            if not self.expect(TokenType.LEFT_PAREN):
                return False
            
            # This is a function pointer!
            return True

    def function_pointer_type(self) -> FunctionPointerType:
        """
        Parse function pointer type specification.
        
        Syntax: def{}* identifier()->return_type
        Example: def{}* fp()->int
        
        The identifier has already been consumed by function_pointer_declaration.
        This method parses: ()->return_type
        """
        # Parse parameter types in parentheses
        self.consume(TokenType.LEFT_PAREN)
        
        parameter_types = []
        if not self.expect(TokenType.RIGHT_PAREN):
            # Parse first parameter type
            parameter_types.append(self.type_spec())
            
            # Parse remaining parameter types
            while self.expect(TokenType.COMMA):
                self.advance()
                parameter_types.append(self.type_spec())
        
        self.consume(TokenType.RIGHT_PAREN)
        
        # Parse return type after ->
        self.consume(TokenType.RETURN_ARROW)
        return_type = self.type_spec()
        
        #print("GOT FUNCTION POINTER")
        
        return FunctionPointerType(return_type, parameter_types)

    def function_pointer_declaration(self, calling_conv: Optional[str] = None) -> Union['FunctionPointerDeclaration', List['FunctionPointerDeclaration']]:
        """
        Parse function pointer declaration(s).
        
        Single syntax:
            def{}* name(param_types) -> return_type;
            def{}* name(param_types) -> return_type = @function_name;
            fastcall{}* name(param_types) -> return_type = @function_name;
        
        Comma-separated syntax (all share the same def{}* prefix):
            def{}* name1(param_types) -> return_type,
                   name2(param_types) -> return_type,
                   name3(param_types) -> return_type;
        
        Returns a single FunctionPointerDeclaration or a list when multiple
        declarations are chained with commas.
        """
        if self._loop_depth > 0 and not self._in_for_init:
            _is_singinit = self.expect(TokenType.SINGINIT)
            if not _is_singinit:
                _peek_idx = self.position + 1
                if _peek_idx < len(self.tokens):
                    _is_singinit = self.tokens[_peek_idx].type == TokenType.SINGINIT
            if not _is_singinit:
                self.warn("pointer declaration inside a loop body, this will continually allocate new slots on the stack each iteration.")
        def _parse_one_fp() -> 'FunctionPointerDeclaration':
            """Parse a single name + type + optional initializer."""
            name = self.consume(TokenType.IDENTIFIER).value
            fp_type = self.function_pointer_type()
            fp_type.calling_conv = calling_conv  # Attach the calling convention

            initializer = None
            if self.expect(TokenType.ASSIGN):
                self.advance()
                if self.expect(TokenType.ADDRESS_OF):
                    self.consume(TokenType.ADDRESS_OF, "Expected '@' for function address")
                    if self.expect(TokenType.STRING_LITERAL):
                        func_name = self.current_token.value
                        self.advance()
                    else:
                        func_name = self.consume(TokenType.IDENTIFIER).value
                    expr = Identifier(func_name)
                    # Support member access chains: @item.fn, @obj.member.fn, etc.
                    while self.expect(TokenType.DOT):
                        self.advance()
                        member = self.consume(TokenType.IDENTIFIER).value
                        expr = MemberAccess(expr, member)
                    initializer = AddressOf(expr)
                else:
                    initializer = self.expression()

            return FunctionPointerDeclaration(name, fp_type, initializer)

        # Parse the first declaration
        first = _parse_one_fp()

        # If followed by a comma, this is a multi-declaration chain
        if self.expect(TokenType.COMMA):
            declarations = [first]
            while self.expect(TokenType.COMMA):
                self.advance()  # consume ','
                declarations.append(_parse_one_fp())
            self.consume(TokenType.SEMICOLON)
            return declarations

        self.consume(TokenType.SEMICOLON)
        return first

    def parameter_list(self) -> List[Parameter]:
        """
        parameter_list -> parameter (',' parameter)*
        """
        params = [self.parameter()]
        
        while self.expect(TokenType.COMMA):
            self.advance()
            params.append(self.parameter())
        
        return params
    
    def parameter(self) -> Parameter:
        """
        parameter -> type_spec IDENTIFIER?
        Returns Parameter where name may be None.
        """
        tok = self.current_token
        # Handle variadic ellipsis sentinel: def foo(...) -> void
        if self.expect(TokenType.ELLIPSIS):
            self.advance()
            sentinel = Parameter(None, TypeSystem(base_type=DataType.VOID))
            sentinel._is_variadic_sentinel = True
            return sentinel

        type_spec = self.type_spec()

        # Identifier is optional
        name = None
        if self.expect(TokenType.IDENTIFIER):
            name = self.consume(TokenType.IDENTIFIER).value

        # Optional default value: int x = 5
        default_value = None
        if name is not None and self.expect(TokenType.ASSIGN):
            self.advance()
            default_value = self.expression()

        return Parameter(name, type_spec, default_value).set_location(tok.line, tok.column)

    def enum_def(self) -> Union[EnumDefStatement, List[EnumDefStatement]]:
        """
        enum_def -> ('enum' | type_spec 'enum') IDENTIFIER (',' IDENTIFIER)* (';' | '{' enum_item (',' enum_item)* '}' ';')
        enum_item -> IDENTIFIER ('=' INTEGER)?
        """
        tok = self.current_token
        # Parse optional underlying type before the 'enum' keyword
        underlying_type = None
        if not self.expect(TokenType.ENUM):
            underlying_type = self.type_spec()
        self.consume(TokenType.ENUM)
        name = self.consume(TokenType.IDENTIFIER, f"Expected: enumurated list name after enum keyword at Line {self.current_token.line:,.0f}:{self.current_token.column} in build\\tmp.fx").value
        
        # Check for comma-separated prototypes
        names = [name]
        while self.expect(TokenType.COMMA):
            self.advance()
            names.append(self.consume(TokenType.IDENTIFIER).value)
        
        # Handle forward declaration (prototype)
        if self.expect(TokenType.SEMICOLON):
            self.advance()
            # Return multiple prototypes if comma-separated
            if len(names) > 1:
                return [EnumDefStatement(EnumDef(n, {}, underlying_type)).set_location(tok.line, tok.column) for n in names]
            return EnumDefStatement(EnumDef(name, {}, underlying_type)).set_location(tok.line, tok.column)
        
        # Full definition - only allowed for single name
        if len(names) > 1:
            self.error("Comma-separated names are only allowed for prototypes (forward declarations)")
        
        self.consume(TokenType.LEFT_BRACE)
        
        values = {}
        current_value = 0
        
        while not self.expect(TokenType.RIGHT_BRACE):
            item_name = self.consume(TokenType.IDENTIFIER).value
            
            # Check if explicit value is provided
            if self.expect(TokenType.ASSIGN):
                self.advance()
                # Parse the integer value
                value_token = self.consume(TokenType.SINT_LITERAL)
                current_value = int(value_token.value, 0)
            
            values[item_name] = current_value
            current_value += 1
            
            # Handle comma separator
            if self.expect(TokenType.COMMA):
                self.advance()
            elif not self.expect(TokenType.RIGHT_BRACE):
                self.error("Expected ',' or '}' in enum definition", TokenType.COMMA)
        
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        return EnumDefStatement(EnumDef(name, values, underlying_type)).set_location(tok.line, tok.column)


    def macro_def(self) -> macroDefStatement:
        """
        macro_def -> 'macro' IDENTIFIER '(' param_list? ')' '{' expression ';'? '}' ';'

        param_list -> IDENTIFIER (',' IDENTIFIER)*

        The trailing ';' inside the braces is a body terminator only.
        It is consumed here and is NOT part of the stored body expression,
        so it will not be injected when the macro is expanded at the call site.
        """
        tok = self.current_token
        self.consume(TokenType.MACRO)
        name = self.consume(TokenType.IDENTIFIER).value

        # Parameter list
        self.consume(TokenType.LEFT_PAREN)
        params = []
        if not self.expect(TokenType.RIGHT_PAREN):
            params.append(self.consume(TokenType.IDENTIFIER).value)
            while self.expect(TokenType.COMMA):
                self.advance()
                params.append(self.consume(TokenType.IDENTIFIER).value)
        self.consume(TokenType.RIGHT_PAREN)

        # Pre-register the macro name before parsing the body so that recursive
        # self-calls inside the body are recognised as macroCall nodes rather
        # than being treated as ordinary FunctionCall nodes.
        # We use a sentinel placeholder; the real node replaces it below.
        self._macros[name] = None

        # Body: a single expression wrapped in braces
        self.consume(TokenType.LEFT_BRACE)
        body = self.expression()
        # Trailing ';' is a body terminator -- consume silently, NOT stored in body
        if self.expect(TokenType.SEMICOLON):
            self.advance()
        self.consume(TokenType.RIGHT_BRACE)
        # Outer terminating ';'
        self.consume(TokenType.SEMICOLON)

        node = macroDef(name=name, params=params, body=body).set_location(tok.line, tok.column)
        self._macros[name] = node   # replace placeholder with real definition
        return macroDefStatement(macro_def=node).set_location(tok.line, tok.column)

    def union_def(self) -> UnionDefStatement:
        """
        union_def -> 'union' IDENTIFIER (';' | '{' union_member* '}' (IDENTIFIER)? ';')

        Tagged union syntax: union name {} tagname;
        where tagname is an identifier that is an enum type
        """
        tok = self.current_token
        self.consume(TokenType.UNION)
        name = self.consume(TokenType.IDENTIFIER).value
        
        # Handle forward declaration
        if self.expect(TokenType.SEMICOLON):
            self.advance()
            return UnionDefStatement(UnionDef(name, [])).set_location(tok.line, tok.column)
        
        self.consume(TokenType.LEFT_BRACE)
        members = []
        
        while not self.expect(TokenType.RIGHT_BRACE):
            members.append(self.union_member())
        
        self.consume(TokenType.RIGHT_BRACE)
        
        # Check for optional tag name (tagged union): } # EnumName;
        tag_name = None
        if self.expect(TokenType.TAG):
            self.advance()
            tag_name = self.consume(TokenType.IDENTIFIER).value
        
        self.consume(TokenType.SEMICOLON)
        return UnionDefStatement(UnionDef(name, members, tag_name)).set_location(tok.line, tok.column)

    def union_member(self) -> UnionMember:
        """
        union_member -> type_spec IDENTIFIER ('=' expression)? ';'
        """
        tok = self.current_token
        type_spec = self.type_spec()
        name = self.consume(TokenType.IDENTIFIER).value
        
        # Optional initial value
        initial_value = None
        if self.expect(TokenType.ASSIGN):
            self.advance()
            initial_value = self.expression()
        
        self.consume(TokenType.SEMICOLON)
        return UnionMember(name, type_spec, initial_value).set_location(tok.line, tok.column)
    
    def struct_def(self) -> Union[StructDef, List[StructDef]]:
        """
        struct_def -> 'struct' IDENTIFIER (',' IDENTIFIER)* (';' | '{' struct_member* '}')
        """
        tok = self.current_token
        self.consume(TokenType.STRUCT)
        name = self.consume(TokenType.IDENTIFIER).value

        # Parse optional template parameter list: struct name<T, U, ...>
        # Use lookahead to confirm all angle-bracket contents are identifiers.
        template_params = []
        if self.expect(TokenType.LESS_THAN):
            with self._lookahead():
                is_template = False
                self.advance()  # consume '<'
                if self.expect(TokenType.IDENTIFIER):
                    self.advance()
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        if not self.expect(TokenType.IDENTIFIER):
                            break
                        self.advance()
                    if self.expect(TokenType.GREATER_THAN):
                        is_template = True
            if is_template:
                self.advance()  # consume '<'
                template_params.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    template_params.append(self.consume(TokenType.IDENTIFIER).value)
                self.consume(TokenType.GREATER_THAN)
        
        # Check for comma-separated prototypes
        names = [name]
        while self.expect(TokenType.COMMA):
            self.advance()
            names.append(self.consume(TokenType.IDENTIFIER).value)
        
        base_structs = []
        members = []
        nested_structs = []

        def _parse_base_struct_ref(extra_template_params_out):
            """Parse a base struct name, optionally followed by <T,U,...> template args.
            Returns the struct ref as a plain name or deferred "Name<T,U>" string.
            Also collects any new template param names (identifiers in active params
            or unknown names that look like type params) into extra_template_params_out.
            """
            base_name = self.consume(TokenType.IDENTIFIER).value
            if not self.expect(TokenType.LESS_THAN):
                return base_name
            # Lookahead: confirm all angle-bracket contents are identifiers (template args).
            with self._lookahead():
                _ok = False
                self.advance()  # consume '<' tentatively
                if self.expect(TokenType.IDENTIFIER):
                    self.advance()
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        if not self.expect(TokenType.IDENTIFIER):
                            break
                        self.advance()
                    if self.expect(TokenType.GREATER_THAN):
                        _ok = True
            if not _ok:
                return base_name
            # Consume the template arg list
            self.advance()  # consume '<'
            args = [self.consume(TokenType.IDENTIFIER).value]
            while self.expect(TokenType.COMMA):
                self.advance()
                args.append(self.consume(TokenType.IDENTIFIER).value)
            self.consume(TokenType.GREATER_THAN)
            # Collect args that are new template params (not already declared)
            known = set(template_params)
            for arg in args:
                if arg not in known and arg not in extra_template_params_out:
                    extra_template_params_out.append(arg)
                    known.add(arg)
            return f"{base_name}<{','.join(args)}>"

        # Pre-composition: struct BMP : Header, InfoHeader;
        # Also: struct B<U> : A<T>  (generic struct inheriting from generic base)
        # Post-composition (no body): struct BMP : Header, InfoHeader : PostData;
        extra_tparams = []  # extra template params gathered from base struct generic args
        if self.expect(TokenType.COLON):
            self.advance()
            base_structs.append(_parse_base_struct_ref(extra_tparams))
            while self.expect(TokenType.COMMA):
                self.advance()
                base_structs.append(_parse_base_struct_ref(extra_tparams))
            # Second colon = post-composition list
            post_structs = []
            if self.expect(TokenType.COLON):
                self.advance()
                post_structs.append(_parse_base_struct_ref(extra_tparams))
                while self.expect(TokenType.COMMA):
                    self.advance()
                    post_structs.append(_parse_base_struct_ref(extra_tparams))
            # Merge extra template params into this struct's template_params
            if extra_tparams:
                template_params = template_params + extra_tparams
            if self.expect(TokenType.SEMICOLON):
                self.advance()
                return StructDef(name, members, base_structs, post_structs=post_structs, nested_structs=nested_structs, template_params=template_params).set_location(tok.line, tok.column)

        # Handle forward declarations (prototypes) - not a prototype if base_structs present
        if self.expect(TokenType.SEMICOLON) and not base_structs:
            self.advance()
            # Return multiple prototypes if comma-separated
            if len(names) > 1:
                return [StructDef(n, [], [], []).set_location(tok.line, tok.column) for n in names]
            return StructDef(name, members, base_structs, nested_structs).set_location(tok.line, tok.column)

        # Full definition - only allowed for single name
        if len(names) > 1:
            self.error("Comma-separated names are only allowed for prototypes (forward declarations)")

        self.consume(TokenType.LEFT_BRACE)
        comptime_blocks = []

        while not self.expect(TokenType.RIGHT_BRACE):
            if self.expect(TokenType.PUBLIC):
                self.advance()
                self.consume(TokenType.LEFT_BRACE)
                while not self.expect(TokenType.RIGHT_BRACE):
                    if self.expect(TokenType.STRUCT):
                        nested_struct_result = self.struct_def()
                        # Handle both single struct and list of structs
                        if isinstance(nested_struct_result, list):
                            nested_structs.extend(nested_struct_result)
                        else:
                            nested_structs.append(nested_struct_result)
                        self.consume(TokenType.SEMICOLON)
                    else:
                        member = self.struct_member()
                        if isinstance(member, list):
                            for m in member:
                                m.is_private = False
                                members.append(m)
                        else:
                            member.is_private = False
                            members.append(member)
                self.consume(TokenType.RIGHT_BRACE)
                self.consume(TokenType.SEMICOLON)
            elif self.expect(TokenType.PRIVATE):
                self.advance()
                self.consume(TokenType.LEFT_BRACE)
                while not self.expect(TokenType.RIGHT_BRACE):
                    if self.expect(TokenType.STRUCT):
                        nested_struct_result = self.struct_def()
                        # Handle both single struct and list of structs
                        if isinstance(nested_struct_result, list):
                            nested_structs.extend(nested_struct_result)
                        else:
                            nested_structs.append(nested_struct_result)
                        self.consume(TokenType.SEMICOLON)
                    else:
                        member = self.struct_member()
                        if isinstance(member, list):
                            for m in member:
                                m.is_private = True
                                members.append(m)
                        else:
                            member.is_private = True
                            members.append(member)
                self.consume(TokenType.RIGHT_BRACE)
                self.consume(TokenType.SEMICOLON)
            elif self.expect(TokenType.STRUCT):
                # Handle nested struct
                nested_struct_result = self.struct_def()
                # Handle both single struct and list of structs
                if isinstance(nested_struct_result, list):
                    nested_structs.extend(nested_struct_result)
                else:
                    nested_structs.append(nested_struct_result)
                # Allow both with and without semicolon for nested structs
                self.expect(TokenType.SEMICOLON)
            elif self.expect(TokenType.COMPTIME):
                # comptime block inside struct body -- emitflux results become members
                cb = self.comptime_block()
                comptime_blocks.append((len(members), cb))
            else:
                member = self.struct_member()
                if isinstance(member, list):
                    members.extend(member)
                else:
                    members.append(member)

        self.consume(TokenType.RIGHT_BRACE)

        # Post-composition: struct BMP : Header, InfoHeader { ... } : PostData;
        # Members from post_structs are appended after the struct's own inline members.
        # Also supports generic bases: struct B<U> { U y; } : A<T>;
        post_structs = []
        if self.expect(TokenType.COLON):
            self.advance()
            post_structs.append(_parse_base_struct_ref(extra_tparams))
            while self.expect(TokenType.COMMA):
                self.advance()
                post_structs.append(_parse_base_struct_ref(extra_tparams))
            # Merge any new template params collected from post-body base refs
            new_from_post = [p for p in extra_tparams if p not in template_params]
            if new_from_post:
                template_params = template_params + new_from_post

        self.consume(TokenType.SEMICOLON)
        sd = StructDef(name, members, base_structs, post_structs=post_structs,
                       nested_structs=nested_structs, template_params=template_params,
                       comptime_blocks=comptime_blocks)
        sd.set_location(tok.line, tok.column)
        if template_params:
            self._templates.register(name, 'struct', template_params, sd)
            self._last_template_registered = name
            if self._in_comptime > 0:
                sd._is_comptime_only = True
                return sd
            return None  # no immediate emission; instantiated on use
        return sd
    
    def struct_member(self) -> Union[StructMember, List[StructMember]]:
        """
        struct_member -> type_spec IDENTIFIER (',' IDENTIFIER)* ('=' expression (',' expression)*)? ';'
        """
        tok = self.current_token
        type_spec = self.type_spec()
        name = self.consume(TokenType.IDENTIFIER).value
        members = [name]

        # Handle comma-separated variable names
        while self.expect(TokenType.COMMA):
            next_tok = self.peek()
            if next_tok and next_tok.type == TokenType.IDENTIFIER:
                self.advance()
                members.append(self.consume(TokenType.IDENTIFIER).value)
            else:
                break
        
        # Handle optional initial values (comma-separated)
        initial_values = []
        if self.expect(TokenType.ASSIGN):
            self.advance()
            initial_values.append(self.expression())
            
            # Handle comma-separated initializers
            while self.expect(TokenType.COMMA):
                self.advance()
                initial_values.append(self.expression())
        
        self.consume(TokenType.SEMICOLON)
        
        # If multiple members, return a list
        if len(members) > 1:
            result = []
            for i, member_name in enumerate(members):
                # Assign initializer if available
                member_initial_value = initial_values[i] if i < len(initial_values) else None
                result.append(StructMember(member_name, type_spec, member_initial_value).set_location(tok.line, tok.column))
            return result
        else:
            member_initial_value = initial_values[0] if initial_values else None
            return StructMember(members[0], type_spec, member_initial_value).set_location(tok.line, tok.column)

    def trait_def(self) -> 'TraitDef':
        """
        trait_def -> 'trait' IDENTIFIER '{' (function_prototype ';')* '}' ';'
                   | 'trait' IDENTIFIER '=' IDENTIFIER ('&' IDENTIFIER)* ';'
        """
        tok = self.current_token
        self.consume(TokenType.TRAIT)
        name = self.consume(TokenType.IDENTIFIER).value

        # Trait composition: trait Foo = Bar & Baz & Qux;
        if self.expect(TokenType.ASSIGN):
            self.advance()
            composed = [self.consume(TokenType.IDENTIFIER).value]
            while self.expect(TokenType.LOGICAL_AND):
                self.advance()
                composed.append(self.consume(TokenType.IDENTIFIER).value)
            self.consume(TokenType.SEMICOLON)
            # Flatten the prototypes of all named traits into a new TraitDef
            prototypes = []
            for base_name in composed:
                base = self._parsed_traits.get(base_name)
                if base is None:
                    self.error(
                        f"Trait composition error: '{base_name}' must be defined "
                        f"before it can be composed into '{name}'"
                    )
                prototypes.extend(base.prototypes)
            trait = TraitDef(name, prototypes).set_location(tok.line, tok.column)
            self._parsed_traits[name] = trait
            return trait

        self.consume(TokenType.LEFT_BRACE)
        prototypes = []
        self._in_trait += 1
        while not self.expect(TokenType.RIGHT_BRACE):
            if self.expect(TokenType.INLINE) or self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
                proto = self.function_def()
                if proto is None:
                    # Templated prototype: function_def() stored it in _templates
                    # and returned None.  Recover the FunctionDef so the trait registry
                    # can record it; the compliance checker will skip it.
                    bare_name = next(reversed(self._templates.all_of_kind('function')))
                    recovered = self._templates.lookup(bare_name).node
                    recovered._is_trait_template_proto = True
                    prototypes.append(recovered)
                elif isinstance(proto, list):
                    prototypes.extend(proto)
                else:
                    prototypes.append(proto)
            else:
                self.error(f"Expected 'def' inside trait '{name}'", TokenType.DEF)
        self._in_trait -= 1
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        trait = TraitDef(name, prototypes).set_location(tok.line, tok.column)
        self._parsed_traits[name] = trait
        return trait

    def effect_def(self) -> 'EffectDef':
        """
        effect_def -> 'effect' IDENTIFIER '{' effect_expr '}' ';'
                    | 'effect' IDENTIFIER '.' IDENTIFIER '{' effect_expr '}' ';'

        Parses a user-defined effect declaration and returns an EffectDef node.
        The name may be a simple identifier or a dot-separated namespaced name.
        """
        tok = self.current_token
        self.consume(TokenType.EFFECT)
        name = self.consume(TokenType.IDENTIFIER).value
        # Support namespaced effect names: effect Hook.Detour { ... }
        while self.expect(TokenType.DOT):
            self.advance()
            sub = self.consume(TokenType.IDENTIFIER).value
            name = name + '.' + sub
        self.consume(TokenType.LEFT_BRACE)
        body = self._parse_effect_expr()
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        return EffectDef(name, body).set_location(tok.line, tok.column)

    def _parse_effect_expr(self) -> 'Expression':
        """
        Parse an effect algebra expression inside { }.
        Precedence (lowest to highest):
            | (or)
            & (and)
            > (priority)
            -> (implication)
            ^ (xor / exactly-one)
            <-> (mutual implication)
            unary: * ~ ! ? @ !@ .. ... ^(suppress) <*
            primary: IDENTIFIER (possibly dotted), ( expr ), [ expr ]
        """
        return self._effect_or()

    def _effect_or(self) -> 'Expression':
        left = self._effect_and()
        while self.expect(TokenType.LOGICAL_OR):
            self.advance()
            right = self._effect_and()
            left = EffectExpr('|', left, right)
        return left

    def _effect_and(self) -> 'Expression':
        left = self._effect_priority()
        while self.expect(TokenType.LOGICAL_AND):
            self.advance()
            right = self._effect_priority()
            left = EffectExpr('&', left, right)
        return left

    def _effect_priority(self) -> 'Expression':
        left = self._effect_implies()
        while self.expect(TokenType.GREATER_THAN):
            self.advance()
            right = self._effect_implies()
            left = EffectExpr('>', left, right)
        return left

    def _effect_implies(self) -> 'Expression':
        left = self._effect_xor()
        while self.expect(TokenType.RETURN_ARROW):
            self.advance()
            right = self._effect_xor()
            left = EffectExpr('->', left, right)
        return left

    def _effect_xor(self) -> 'Expression':
        left = self._effect_mutual()
        while self.expect(TokenType.XOR_OP):
            self.advance()
            right = self._effect_mutual()
            left = EffectExpr('^|', left, right)
        return left

    def _effect_mutual(self) -> 'Expression':
        # <-> mutual implication -- lexes as CHAIN_ARROW (<-) + GREATER_THAN (>)
        left = self._effect_unary()
        while (self.expect(TokenType.CHAIN_ARROW) and self.peek()
               and self.peek().type == TokenType.GREATER_THAN):
            self.advance()  # consume '<-'
            self.advance()  # consume '>'
            right = self._effect_unary()
            left = EffectExpr('<->', left, right)
        return left

    def _effect_unary(self) -> 'Expression':
        tok = self.current_token

        # !@ (permanent non-attenuatable) -- must check before ! alone
        if (self.expect(TokenType.NOT) and self.peek()
                and self.peek().type == TokenType.ADDRESS_OF):
            self.advance()  # consume '!'
            self.advance()  # consume '@'
            operand = self._effect_unary()
            return EffectExpr('!@', operand)

        # ! (excludes)
        if self.expect(TokenType.NOT):
            self.advance()
            operand = self._effect_unary()
            return EffectExpr('!', operand)

        # * (implies/propagates) -- but *. is the global wildcard primary, not a unary op
        if self.expect(TokenType.MULTIPLY):
            if self.peek() and self.peek().type == TokenType.DOT:
                # *. -- fall through to _effect_primary to handle *.*
                pass
            else:
                self.advance()
                operand = self._effect_unary()
                return EffectExpr('*', operand)

        # ~ (requires)
        if self.expect(TokenType.TIE):
            self.advance()
            operand = self._effect_unary()
            return EffectExpr('~', operand)

        # ? (weak)
        if self.expect(TokenType.QUESTION):
            self.advance()
            operand = self._effect_unary()
            return EffectExpr('?', operand)

        # @ (attenuatable)
        if self.expect(TokenType.ADDRESS_OF):
            self.advance()
            operand = self._effect_unary()
            return EffectExpr('@', operand)

        # ... (propagates indefinitely) -- must check before ..
        if self.expect(TokenType.ELLIPSIS):
            self.advance()
            operand = self._effect_unary()
            return EffectExpr('...', operand)

        # .. (one-level propagation)
        if self.expect(TokenType.RANGE):
            self.advance()
            operand = self._effect_unary()
            return EffectExpr('..', operand)

        # ^X (suppress) -- bare ^ not followed by | is the suppress operator
        if (self.expect(TokenType.EXPONENT) and self.peek()
                and self.peek().type != TokenType.LOGICAL_OR):
            self.advance()
            operand = self._effect_unary()
            return EffectExpr('^suppress', operand)

        # <* (caller propagation) -- < followed by *
        if (self.expect(TokenType.LESS_THAN) and self.peek()
                and self.peek().type == TokenType.MULTIPLY):
            self.advance()  # consume '<'
            self.advance()  # consume '*'
            operand = self._effect_unary()
            return EffectExpr('<*', operand)

        return self._effect_primary()

    def _effect_primary(self) -> 'Expression':
        tok = self.current_token

        # Parenthesised group
        if self.expect(TokenType.LEFT_PAREN):
            self.advance()
            expr = self._parse_effect_expr()
            self.consume(TokenType.RIGHT_PAREN)
            return expr

        # Bracketed group (alternative grouping syntax from the spec: [expr])
        if self.expect(TokenType.LEFT_BRACKET):
            self.advance()
            expr = self._parse_effect_expr()
            self.consume(TokenType.RIGHT_BRACKET)
            return expr

        # Global wildcard *.*
        if self.expect(TokenType.MULTIPLY):
            self.advance()  # consume '*'
            self.consume(TokenType.DOT)
            if not self.expect(TokenType.MULTIPLY):
                self.error("Expected '*' after '*.' in wildcard effect expression")
            self.advance()  # consume second '*'
            return EffectName('*.*').set_location(tok.line, tok.column)

        # Effect name -- identifier, possibly dotted (IO.Socket, Hook.Detour)
        # Supports namespace wildcard: IO.* means all effects in IO namespace.
        if self.expect(TokenType.IDENTIFIER) or self.expect(TokenType.EFFECT):
            name = self.current_token.value
            self.advance()
            while self.expect(TokenType.DOT):
                self.advance()
                if self.expect(TokenType.MULTIPLY):
                    # Namespace wildcard: IO.*
                    self.advance()
                    name = name + '.*'
                    break
                if not self.expect(TokenType.IDENTIFIER):
                    self.error("Expected identifier or '*' after '.' in effect name")
                sub = self.current_token.value
                self.advance()
                name = name + '.' + sub
            return EffectName(name).set_location(tok.line, tok.column)

        self.error("Expected effect expression (identifier, unary operator, or grouped expression)")

    def interface_def(self) -> 'InterfaceDef':
        """
        interface_def -> 'interface' IDENTIFIER '(' param_list ')' '{' protocol_list '}' ';'

        param_list    -> IDENTIFIER ':' IDENTIFIER (',' IDENTIFIER ':' IDENTIFIER)*
        protocol_list -> (protocol_block ';')*

        protocol_block ->
            IDENTIFIER ':' IDENTIFIER '{' prototype_list '}'         # A : B  CALL_ON
          | IDENTIFIER '(' IDENTIFIER ')' '{' prototype_list '}'     # B(A)   PASS_INTO
          | IDENTIFIER '->' IDENTIFIER '{' prototype_list '}'        # A -> B RETURN_TO

        prototype_list -> function_prototype (',' function_prototype)*
        """
        from fast import InterfaceDef, InterfaceProtocol, ProtocolKind
        tok = self.current_token
        self.consume(TokenType.INTERFACE)
        name = self.consume(TokenType.IDENTIFIER).value

        # Parse parameter list: (A: Readable, B: Writable)
        # Every parameter MUST have a trait constraint -- bare (A, B) is illegal.
        self.consume(TokenType.LEFT_PAREN)
        params = []
        if not self.expect(TokenType.RIGHT_PAREN):
            param_name = self.consume(TokenType.IDENTIFIER).value
            if not self.expect(TokenType.COLON):
                err_tok = self.current_token
                raise SyntaxError(
                    f"Interface parameter '{param_name}' must have a trait constraint "
                    f"(e.g. {param_name}: SomeTrait) [{err_tok.line}:{err_tok.column}]")
            self.advance()
            trait_name = self.consume(TokenType.IDENTIFIER).value
            params.append((param_name, trait_name))
            while self.expect(TokenType.COMMA):
                self.advance()
                param_name = self.consume(TokenType.IDENTIFIER).value
                if not self.expect(TokenType.COLON):
                    err_tok = self.current_token
                    raise SyntaxError(
                        f"Interface parameter '{param_name}' must have a trait constraint "
                        f"(e.g. {param_name}: SomeTrait) [{err_tok.line}:{err_tok.column}]")
                self.advance()
                trait_name = self.consume(TokenType.IDENTIFIER).value
                params.append((param_name, trait_name))
        self.consume(TokenType.RIGHT_PAREN)

        # Parse body: { <protocol_block>; ... }
        self.consume(TokenType.LEFT_BRACE)
        protocols = []
        while not self.expect(TokenType.RIGHT_BRACE):
            first = self.consume(TokenType.IDENTIFIER).value

            if self.expect(TokenType.COLON):
                # A : B { ... }  -- CALL_ON (existing)
                self.advance()
                callee = self.consume(TokenType.IDENTIFIER).value
                proto_methods = self._parse_interface_proto_list()
                protocol = InterfaceProtocol(first, callee, proto_methods, ProtocolKind.CALL_ON)

            elif self.expect(TokenType.LEFT_PAREN):
                # B(A) { ... }  -- PASS_INTO
                # first = B (receiver), inside parens = A (provider)
                self.advance()
                provider = self.consume(TokenType.IDENTIFIER).value
                self.consume(TokenType.RIGHT_PAREN)
                proto_methods = self._parse_interface_proto_list()
                # Store as caller=provider(A), callee=receiver(B): "A provides into B"
                protocol = InterfaceProtocol(provider, first, proto_methods, ProtocolKind.PASS_INTO)

            elif self.expect(TokenType.RETURN_ARROW):
                # A -> B { ... }  -- RETURN_TO
                self.advance()
                callee = self.consume(TokenType.IDENTIFIER).value
                proto_methods = self._parse_interface_proto_list()
                protocol = InterfaceProtocol(first, callee, proto_methods, ProtocolKind.RETURN_TO)

            else:
                err_tok = self.current_token
                raise SyntaxError(
                    f"Expected ':', '(' or '->' in interface protocol block "
                    f"[{err_tok.line}:{err_tok.column}]")

            protocol.set_location(tok.line, tok.column)
            protocols.append(protocol)
            self.consume(TokenType.SEMICOLON)

        self.consume(TokenType.RIGHT_BRACE)

        # Parse optional # qualifier tags -- any order, any count.
        # Syntax: interface Foo(...) { ... } # attenuate { expr } # effect { expr };
        iface_effect_ann = None
        iface_attenuate_ann = None
        while self.expect(TokenType.TAG):
            self.advance()
            if self.expect(TokenType.EFFECT):
                self.advance()
                self.consume(TokenType.LEFT_BRACE)
                eff_expr = self._parse_effect_expr()
                self.consume(TokenType.RIGHT_BRACE)
                iface_effect_ann = EffectAnnotation(eff_expr)
            elif self.expect(TokenType.IDENTIFIER) and self.current_token.value == 'attenuate':
                self.advance()
                self.consume(TokenType.LEFT_BRACE)
                att_expr = self._parse_effect_expr()
                self.consume(TokenType.RIGHT_BRACE)
                iface_attenuate_ann = AttenuateAnnotation(att_expr)
            else:
                self.error("Expected 'effect' or 'attenuate' after '#' in interface definition")

        self.consume(TokenType.SEMICOLON)
        idef = InterfaceDef(name, params, protocols)
        idef.attenuate_annotation = iface_attenuate_ann
        idef.effect_annotation = iface_effect_ann
        return idef.set_location(tok.line, tok.column)

    def _parse_interface_proto_list(self) -> list:
        """
        Parse the { prototype_list } body shared by all three interface protocol forms.
        Prototypes are comma-separated bare signatures: name(params) -> type
        Returns a list of FunctionDef nodes with is_prototype=True.
        """
        self.consume(TokenType.LEFT_BRACE)
        proto_methods = []
        while not self.expect(TokenType.RIGHT_BRACE):
            proto_tok = self.current_token
            func_name = self.consume(TokenType.IDENTIFIER).value
            self.consume(TokenType.LEFT_PAREN)
            sig_params = []
            if not self.expect(TokenType.RIGHT_PAREN):
                p_type = self.type_spec()
                p_name = self.consume(TokenType.IDENTIFIER).value
                sig_params.append(Parameter(p_name, p_type).set_location(proto_tok.line, proto_tok.column))
                while self.expect(TokenType.COMMA):
                    self.advance()
                    p_type = self.type_spec()
                    p_name = self.consume(TokenType.IDENTIFIER).value
                    sig_params.append(Parameter(p_name, p_type).set_location(proto_tok.line, proto_tok.column))
            self.consume(TokenType.RIGHT_PAREN)
            self.consume(TokenType.RETURN_ARROW)
            ret_type = self.type_spec()
            proto = FunctionDef(func_name, sig_params, ret_type, Block([]), is_prototype=True)
            proto.set_location(proto_tok.line, proto_tok.column)
            proto_methods.append(proto)
            # Signatures are comma-separated; a trailing comma or closing brace ends the list
            if self.expect(TokenType.COMMA):
                self.advance()
            else:
                break
        self.consume(TokenType.RIGHT_BRACE)
        return proto_methods

    def object_def(self, trait_names: Optional[List[str]] = None) -> Union[ObjectDef, List[ObjectDef]]:
        """
        object_def -> 'object' IDENTIFIER (',' IDENTIFIER)* (';' | '{' object_body '}')
        object_body -> (object_member | access_specifier)*
        """
        tok = self.current_token
        self.consume(TokenType.OBJECT)
        name = self.consume(TokenType.IDENTIFIER).value
        traits = trait_names if trait_names is not None else []

        # Parse optional template parameter list: object Name<T, U, ...>
        template_params = []
        if self.expect(TokenType.LESS_THAN):
            with self._lookahead():
                is_template = False
                self.advance()  # consume '<'
                if self.expect(TokenType.IDENTIFIER):
                    self.advance()
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        if not self.expect(TokenType.IDENTIFIER):
                            break
                        self.advance()
                    if self.expect(TokenType.GREATER_THAN):
                        is_template = True
            if is_template:
                self.advance()  # consume '<'
                template_params.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    template_params.append(self.consume(TokenType.IDENTIFIER).value)
                self.consume(TokenType.GREATER_THAN)

        _obj_tmpl_scope_ctx = self._template_scope(template_params if template_params else [])
        _obj_tmpl_scope_ctx.__enter__()

        # Check for comma-separated prototypes
        names = [name]
        if self.expect(TokenType.COMMA):
            # Comma-separated prototype list - inheritance not allowed here
            while self.expect(TokenType.COMMA):
                self.advance()
                names.append(self.consume(TokenType.IDENTIFIER).value)

        # Parse inheritance list: object A : B, C
        base_objects = []
        if self.expect(TokenType.COLON):
            if len(names) > 1:
                self.error("Cannot use comma-separated prototype names with an inheritance list")
            self.advance()  # consume ':'
            base_objects.append(self.consume(TokenType.IDENTIFIER).value)
            while self.expect(TokenType.COMMA):
                self.advance()
                # Stop if we hit the body or end - those belong elsewhere
                if self.expect(TokenType.LEFT_BRACE, TokenType.SEMICOLON):
                    break
                base_objects.append(self.consume(TokenType.IDENTIFIER).value)
        
        methods = []
        members = []
        nested_objects = []
        nested_structs = []

        # Handle forward declarations (prototypes)
        if self.expect(TokenType.SEMICOLON):
            is_prototype = True
            self.advance()
            _obj_tmpl_scope_ctx.__exit__(None, None, None)
            # Return multiple prototypes if comma-separated
            if len(names) > 1:
                return [ObjectDef(n, [], [], [], [], traits=traits).set_location(tok.line, tok.column) for n in names]
            proto = ObjectDef(name, methods, members, nested_objects, nested_structs, traits=traits)
            proto.base_objects = base_objects
            return proto.set_location(tok.line, tok.column)

        # Full definition - only allowed for single name
        if len(names) > 1:
            self.error("Comma-separated names are only allowed for prototypes (forward declarations)")

        # Add to the forward-decl set before parsing the body so that type_spec()
        # can resolve self-referential return types like Tensor<T>* inside method
        # signatures without needing a sentinel ObjectDef in the registry.
        if template_params:
            self._template_object_forward_decls.add(name)

        self.consume(TokenType.LEFT_BRACE)
        
        while not self.expect(TokenType.RIGHT_BRACE):
            if self.expect(TokenType.PUBLIC, TokenType.PRIVATE):
                is_private = self.current_token.type == TokenType.PRIVATE
                self.advance()
                # Optional friend syntax: private : SomeFriend { ... }
                friend_name = None
                if is_private and self.expect(TokenType.COLON):
                    self.advance()  # consume ':'
                    friend_name = self.consume(TokenType.IDENTIFIER).value
                self.consume(TokenType.LEFT_BRACE)
                
                while not self.expect(TokenType.RIGHT_BRACE):
                    _is_override = False
                    _no_override = False
                    if self.expect(TokenType.NOT) and self.peek().type == TokenType.PLUS and self.peek(2).type in ({TokenType.INLINE, TokenType.DEF} | _CALLING_CONV_TOKENS):
                        _no_override = True
                        self.advance()  # consume '!'
                        self.advance()  # consume '+'
                    elif self.expect(TokenType.PLUS) and self.peek().type in ({TokenType.INLINE, TokenType.DEF} | _CALLING_CONV_TOKENS):
                        _is_override = True
                        self.advance()  # consume '+'
                    if self.expect(TokenType.INLINE) or self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
                        self._last_template_registered = None
                        method = self.function_def()
                        if method is None:
                            # Template method: re-register under qualified ObjectName.methodname key
                            # and record a stub in methods so trait compliance can see the name.
                            bare_name = self._last_template_registered
                            if bare_name:
                                qualified = f"{name}.{bare_name}"
                                self._templates.register_alias(qualified, bare_name)
                            recovered = self._templates.lookup(bare_name).node if bare_name else None
                            if recovered is None:
                                self.error("Internal: template method registered no name")
                            stub = FunctionDef(recovered.name, [], recovered.return_type,
                                               Block([]), is_prototype=True)
                            stub._is_template_method = True
                            stub.is_private = is_private
                            stub.friend_of = friend_name
                            stub._is_override = _is_override
                            stub._no_override = _no_override
                            methods.append(stub)
                        elif isinstance(method, list):
                            for m in method:
                                m.is_private = is_private
                                m.friend_of = friend_name
                                m._is_override = _is_override
                                m._no_override = _no_override
                                methods.append(m)
                        else:
                            method.is_private = is_private
                            method.friend_of = friend_name
                            method._is_override = _is_override
                            method._no_override = _no_override
                            methods.append(method)
                    elif self.expect(TokenType.OBJECT):
                        nested_obj_result = self.object_def()
                        # Handle both single object and list of objects
                        if isinstance(nested_obj_result, list):
                            for obj in nested_obj_result:
                                obj.is_private = is_private
                                nested_objects.append(obj)
                        else:
                            nested_obj_result.is_private = is_private
                            nested_objects.append(nested_obj_result)
                        self.consume(TokenType.SEMICOLON)
                    elif self.expect(TokenType.STRUCT):
                        nested_struct_result = self.struct_def()
                        # Handle both single struct and list of structs
                        if isinstance(nested_struct_result, list):
                            for struct in nested_struct_result:
                                struct.is_private = is_private
                                nested_structs.append(struct)
                        else:
                            nested_struct_result.is_private = is_private
                            nested_structs.append(nested_struct_result)
                        self.consume(TokenType.SEMICOLON)
                    else:
                        # Field declaration
                        var = self.variable_declaration()
                        if isinstance(var, list):
                            for v in var:
                                member = StructMember(v.name, v.type_spec, v.initial_value, is_private)
                                member.friend_of = friend_name
                                members.append(member)
                        else:
                            member = StructMember(var.name, var.type_spec, var.initial_value, is_private)
                            member.friend_of = friend_name
                            members.append(member)
                        self.consume(TokenType.SEMICOLON)
                
                self.consume(TokenType.RIGHT_BRACE)
                self.consume(TokenType.SEMICOLON)
            else:
                # Regular member (defaults to public)
                _is_override = False
                _no_override = False
                if self.expect(TokenType.NOT) and self.peek().type == TokenType.PLUS and self.peek(2).type in ({TokenType.INLINE, TokenType.DEF} | _CALLING_CONV_TOKENS):
                    _no_override = True
                    self.advance()  # consume '!'
                    self.advance()  # consume '+'
                elif self.expect(TokenType.PLUS) and self.peek().type in ({TokenType.INLINE, TokenType.DEF} | _CALLING_CONV_TOKENS):
                    _is_override = True
                    self.advance()  # consume '+'
                if self.expect(TokenType.INLINE) or self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
                    self._last_template_registered = None
                    method = self.function_def()
                    if method is None:
                        # Template method: re-register under qualified ObjectName.methodname key
                        # and record a stub in methods so trait compliance can see the name.
                        bare_name = self._last_template_registered
                        if bare_name:
                            qualified = f"{name}.{bare_name}"
                            self._templates.register_alias(qualified, bare_name)
                        recovered = self._templates.lookup(bare_name).node if bare_name else None
                        if recovered is None:
                            self.error("Internal: template method registered no name")
                        stub = FunctionDef(recovered.name, [], recovered.return_type,
                                           Block([]), is_prototype=True)
                        stub._is_template_method = True
                        stub._is_override = _is_override
                        stub._no_override = _no_override
                        methods.append(stub)
                    elif isinstance(method, list):
                        for m in method:
                            m._is_override = _is_override
                            m._no_override = _no_override
                        methods.extend(method)
                    else:
                        method._is_override = _is_override
                        method._no_override = _no_override
                        methods.append(method)
                elif self.expect(TokenType.OBJECT):
                    nested_obj_result = self.object_def()
                    # Handle both single object and list of objects
                    if isinstance(nested_obj_result, list):
                        nested_objects.extend(nested_obj_result)
                    else:
                        nested_objects.append(nested_obj_result)
                    self.consume(TokenType.SEMICOLON)
                elif self.expect(TokenType.STRUCT):
                    nested_struct_result = self.struct_def()
                    # Handle both single struct and list of structs
                    if isinstance(nested_struct_result, list):
                        nested_structs.extend(nested_struct_result)
                    else:
                        nested_structs.append(nested_struct_result)
                    self.consume(TokenType.SEMICOLON)
                else:
                    # Field declaration
                    var = self.variable_declaration()
                    if isinstance(var, list):
                        for v in var:
                            member = StructMember(v.name, v.type_spec, v.initial_value, False)
                            members.append(member)
                    else:
                        member = StructMember(var.name, var.type_spec, var.initial_value, False)
                        members.append(member)
                    self.consume(TokenType.SEMICOLON)
        
        self.consume(TokenType.RIGHT_BRACE)

        # Parse interface attachments: } : InterfaceName(arg, ...), Other(arg, ...) ;
        def _consume_iface_arg():
            if self.expect(TokenType.THIS):
                self.advance()
                return 'this'
            return self.consume(TokenType.IDENTIFIER).value

        interface_attachments = []
        if self.expect(TokenType.COLON):
            self.advance()  # consume ':'
            iface_name = self.consume(TokenType.IDENTIFIER).value
            self.consume(TokenType.LEFT_PAREN)
            iface_args = []
            if not self.expect(TokenType.RIGHT_PAREN):
                iface_args.append(_consume_iface_arg())
                while self.expect(TokenType.COMMA):
                    self.advance()
                    iface_args.append(_consume_iface_arg())
            self.consume(TokenType.RIGHT_PAREN)
            interface_attachments.append((iface_name, iface_args))
            while self.expect(TokenType.COMMA):
                self.advance()
                iface_name = self.consume(TokenType.IDENTIFIER).value
                self.consume(TokenType.LEFT_PAREN)
                iface_args = []
                if not self.expect(TokenType.RIGHT_PAREN):
                    iface_args.append(_consume_iface_arg())
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        iface_args.append(_consume_iface_arg())
                self.consume(TokenType.RIGHT_PAREN)
                interface_attachments.append((iface_name, iface_args))

        self.consume(TokenType.SEMICOLON)

        # Resolve inheritance: merge parent members and methods before validation
        if base_objects:
            members, methods = _resolve_inheritance(
                name, base_objects, members, methods, self._parsed_objects, self.error
            )

        # Register __init parameter count for single-arg constructor sugar
        for method in methods:
            if isinstance(method, FunctionDef) and method.name == '__init':
                # Exclude the implicit 'this' parameter
                explicit_params = [p for p in method.parameters if p.name != 'this']
                self._object_init_params[name] = len(explicit_params)
                break

        # __init, __exit, and __expr are all mandatory on every fully-defined object.
        # Validate presence and signatures for each.

        # --- __init ---
        init_method = next((m for m in methods if isinstance(m, FunctionDef) and m.name == '__init'), None)
        if init_method is None:
            self.error(
                f"Object '{name}' is missing a __init() method. "
                f"Every object must define 'def __init(...) -> this {{ ... }};' "
                f"to specify its constructor."
            )
        else:
            ret = init_method.return_type
            is_this_return = (
                ret is not None
                and getattr(ret, 'base_type', None) == DataType.THIS
            )
            if not is_this_return:
                self.error(
                    f"Object '{name}': __init() must return 'this'"
                )

        # --- __exit ---
        exit_method = next((m for m in methods if isinstance(m, FunctionDef) and m.name == '__exit'), None)
        if exit_method is None:
            self.error(
                f"Object '{name}' is missing a __exit() method. "
                f"Every object must define 'def __exit() -> void {{ ... }};' "
                f"to specify its destructor."
            )
        else:
            explicit_params = [p for p in exit_method.parameters if p.name != 'this']
            if explicit_params:
                self.error(
                    f"Object '{name}': __exit() must take no parameters "
                    f"(got {len(explicit_params)})"
                )
            ret = exit_method.return_type
            is_void = (
                ret is None
                or (ret.base_type == DataType.VOID and not getattr(ret, 'is_pointer', False))
            )
            if not is_void:
                self.error(
                    f"Object '{name}': __exit() must return void"
                )

        # --- __expr ---
        expr_method = next((m for m in methods if isinstance(m, FunctionDef) and m.name == '__expr'), None)
        if expr_method is None:
            self.error(
                f"Object '{name}' is missing a __expr() method. "
                f"Every object must define 'def __expr() -> <type> {{ ... }};' "
                f"to specify its expression-context value."
            )
        else:
            explicit_params = [p for p in expr_method.parameters if p.name != 'this']
            if explicit_params:
                self.error(
                    f"Object '{name}': __expr() must take no parameters "
                    f"(got {len(explicit_params)})"
                )
            ret = expr_method.return_type
            is_bare_void = (
                ret is None
                or (ret.base_type == DataType.VOID and not getattr(ret, 'is_pointer', False))
            )
            if is_bare_void:
                self.error(
                    f"Object '{name}': __expr() must have a non-void return type"
                )

        # Trait compliance: verify the object implements every non-template
        # prototype required by each trait it declares.
        implemented_names = {m.name for m in methods if isinstance(m, FunctionDef)}
        for trait_name in traits:
            trait_def_node = self._parsed_traits.get(trait_name)
            if trait_def_node is None:
                self.error(f"Object '{name}' declares trait '{trait_name}' which has not been defined")
            for proto in trait_def_node.prototypes:
                if getattr(proto, '_is_trait_template_proto', False):
                    continue  # template protos are checked at instantiation time
                if proto.name not in implemented_names:
                    self.error(
                        f"Object '{name}' doesn't implement required function '{proto.name}' "
                        f"from trait '{trait_name}'"
                    )

        obj_def = ObjectDef(name, methods, members, nested_objects, nested_structs, traits=traits, template_params=template_params, interfaces=interface_attachments)
        obj_def.base_objects = base_objects
        obj_def = obj_def.set_location(tok.line, tok.column)
        _obj_tmpl_scope_ctx.__exit__(None, None, None)
        self._template_object_forward_decls.discard(name)
        if template_params:
            self._templates.register(name, 'object', template_params, obj_def)
            self._last_template_registered = name
            return None
        self._parsed_objects[name] = obj_def
        return obj_def
    
    def namespace_def(self) -> NamespaceDef:
        """
        namespace_def -> 'namespace' IDENTIFIER '{' namespace_body* '}' ';'
        """
        tok = self.current_token
        self.consume(TokenType.NAMESPACE)
        name = self.consume(TokenType.IDENTIFIER).value
        
        # ADDED: Push namespace onto stack for qualified name tracking
        self._namespace_stack.append(name)
        current_namespace = '__'.join(self._namespace_stack)
        
        # Parse optional base namespaces
        base_namespaces = []
        if self.expect(TokenType.COLON):
            self.advance()
            base_name = self.consume(TokenType.IDENTIFIER).value
            base_namespaces.append(base_name)
            
            while self.expect(TokenType.COMMA):
                self.advance()
                base_name = self.consume(TokenType.IDENTIFIER).value
                base_namespaces.append(base_name)
        
        self.consume(TokenType.LEFT_BRACE)
        
        functions = []
        structs = []
        objects = []
        enums = []
        unions = []
        extern_blocks = []
        variables = []
        nested_namespaces = []
        
        while not self.expect(TokenType.RIGHT_BRACE):
            if self.expect(TokenType.GLOBAL, TokenType.LOCAL, TokenType.HEAP, 
                           TokenType.STACK, TokenType.REGISTER, TokenType.SINGINIT,
                           TokenType.CONST, TokenType.VOLATILE):
                var_decl = self.variable_declaration()
                if isinstance(var_decl, list):
                    variables.extend(var_decl)
                else:
                    variables.append(var_decl)
                self.consume(TokenType.SEMICOLON)
            elif self.expect(TokenType.INLINE) or self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS or self._is_bare_function_def():
                if self.expect(TokenType.DEF) and self.peek().type == TokenType.FUNCTION_POINTER:
                    self.advance() #def
                    self.advance() #{}*
                    func_ptr = self.function_pointer_declaration()
                    variables.append(func_ptr)
                elif self.current_token.type in _CALLING_CONV_TOKENS and self.peek().type == TokenType.FUNCTION_POINTER:
                    cc_str = _CALLING_CONV_TOKEN_TO_STR[self.current_token.type]
                    self.advance() # cc keyword
                    self.advance() # {}*
                    func_ptr = self.function_pointer_declaration(calling_conv=cc_str)
                    variables.append(func_ptr)
                else:
                    self._last_template_registered = None
                    func = self.function_def()
                    # function_def() returns None for template functions (deferred instantiation).
                    if func is None:
                        # Register the template under its namespace-qualified names so that
                        # call-site lookup resolves correctly.
                        bare_name = self._last_template_registered
                        if bare_name:
                            ns_mangled = f"{current_namespace}__{bare_name}"
                            ns_scoped  = f"{current_namespace}::{bare_name}"
                            self._templates.register_alias(ns_mangled, bare_name)
                            self._templates.register_alias(ns_scoped,  bare_name)
                    elif isinstance(func, list):
                        for f in func:
                            functions.append(f)
                            qualified_name = f"{current_namespace}__{f.name}"
                            self.symbol_table.define(qualified_name, SymbolKind.FUNCTION)
                            self.symbol_table.define(f.name, SymbolKind.FUNCTION)
                    else:
                        functions.append(func)
                        qualified_name = f"{current_namespace}__{func.name}"
                        self.symbol_table.define(qualified_name, SymbolKind.FUNCTION)
                        self.symbol_table.define(func.name, SymbolKind.FUNCTION)
            elif self.expect(TokenType.STRUCT):
                struct_result = self.struct_def()
                # struct_def() returns None for template structs (deferred instantiation).
                # In that case we must still register the template under all the qualified
                # names callers may use to reference it, then skip adding it to `structs`.
                if struct_result is None:
                    # struct_def() set _last_template_registered to the bare name it registered.
                    # Register it under the namespace-qualified forms so that type_spec() can
                    # find it when the caller writes XYZ::myStru2<int>.
                    bare_name = self._last_template_registered
                    if bare_name:
                        ns_mangled = f"{current_namespace}__{bare_name}"
                        ns_scoped  = f"{current_namespace}::{bare_name}"
                        self._templates.register_alias(ns_mangled, bare_name)
                        self._templates.register_alias(ns_scoped,  bare_name)
                # Handle both single struct and list of structs (comma-separated prototypes)
                elif isinstance(struct_result, list):
                    for struct in struct_result:
                        structs.append(struct)
                        # ADDED: Register struct type in symbol table
                        qualified_name = f"{current_namespace}__{struct.name}"
                        self.symbol_table.define(qualified_name, SymbolKind.TYPE)
                        self.symbol_table.define(struct.name, SymbolKind.TYPE)
                else:
                    structs.append(struct_result)
                    # ADDED: Register struct type in symbol table
                    qualified_name = f"{current_namespace}__{struct_result.name}"
                    self.symbol_table.define(qualified_name, SymbolKind.TYPE)
                    self.symbol_table.define(struct_result.name, SymbolKind.TYPE)
            elif self.expect(TokenType.OBJECT):
                obj_result = self.object_def()
                # object_def() returns None for template objects (deferred instantiation).
                if obj_result is None:
                    bare_name = self._last_template_registered
                    if bare_name:
                        ns_mangled = f"{current_namespace}__{bare_name}"
                        ns_scoped  = f"{current_namespace}::{bare_name}"
                        self._templates.register_alias(ns_mangled, bare_name)
                        self._templates.register_alias(ns_scoped,  bare_name)
                # Handle both single object and list of objects (comma-separated prototypes)
                elif isinstance(obj_result, list):
                    objects.extend(obj_result)
                else:
                    objects.append(obj_result)
            elif self.expect(TokenType.TRAIT):
                trait_result = self.trait_def()
                # TraitDef is registered at codegen time; store in objects list for codegen traversal
                objects.append(trait_result)
            elif self.expect(TokenType.INTERFACE):
                iface_result = self.interface_def()
                objects.append(iface_result)
            elif self._is_trait_prefixed_object():
                obj_result = self._parse_trait_prefixed_object()
                if obj_result is None:
                    bare_name = self._last_template_registered
                    if bare_name:
                        ns_mangled = f"{current_namespace}__{bare_name}"
                        ns_scoped  = f"{current_namespace}::{bare_name}"
                        self._templates.register_alias(ns_mangled, bare_name)
                        self._templates.register_alias(ns_scoped,  bare_name)
                elif isinstance(obj_result, list):
                    objects.extend(obj_result)
                else:
                    objects.append(obj_result)
            elif self.expect(TokenType.ENUM) or (self.peek() and self.peek().type == TokenType.ENUM):
                enum_result = self.enum_def()
                # Handle both single enum and list of enums (comma-separated prototypes)
                if isinstance(enum_result, list):
                    for enum_stmt in enum_result:
                        enum = enum_stmt.enum_def  # Unwrap to get the EnumDef
                        enums.append(enum)
                        # ADDED: Register enum type in symbol table
                        qualified_name = f"{current_namespace}__{enum.name}"
                        self.symbol_table.define(qualified_name, SymbolKind.TYPE)
                        self.symbol_table.define(enum.name, SymbolKind.TYPE)
                else:
                    enum = enum_result.enum_def  # Unwrap to get the EnumDef
                    enums.append(enum)
                    # ADDED: Register enum type in symbol table
                    qualified_name = f"{current_namespace}__{enum.name}"
                    self.symbol_table.define(qualified_name, SymbolKind.TYPE)
                    self.symbol_table.define(enum.name, SymbolKind.TYPE)
            elif self.expect(TokenType.UNION):
                union_stmt = self.union_def()
                union = union_stmt.union_def  # Unwrap UnionDefStatement -> UnionDef
                unions.append(union)
                qualified_name = f"{current_namespace}__{union.name}"
                self.symbol_table.define(qualified_name, SymbolKind.TYPE)
                self.symbol_table.define(union.name, SymbolKind.TYPE)
            elif self.expect(TokenType.OPERATOR):
                op_func = self.operator_def()
                functions.append(op_func)
                qualified_name = f"{current_namespace}__{op_func.name}"
                self.symbol_table.define(qualified_name, SymbolKind.FUNCTION)
                self.symbol_table.define(op_func.name, SymbolKind.FUNCTION)
            elif self.expect(TokenType.EXTERN):
                extern = self.extern_statement()
                extern_blocks.append(extern)
            elif self.expect(TokenType.NAMESPACE):
                # Nested namespace - recursion will handle namespace stack
                nested_ns = self.namespace_def()
                merged = False
                for existing_ns in nested_namespaces:
                    if existing_ns.name == nested_ns.name:
                        existing_ns.functions.extend(nested_ns.functions)
                        existing_ns.structs.extend(nested_ns.structs)
                        existing_ns.objects.extend(nested_ns.objects)
                        existing_ns.enums.extend(nested_ns.enums)
                        existing_ns.unions.extend(nested_ns.unions)
                        existing_ns.variables.extend(nested_ns.variables)
                        existing_ns.nested_namespaces.extend(nested_ns.nested_namespaces)
                        existing_ns.base_namespaces.extend(nested_ns.base_namespaces)
                        merged = True
                        break
                if not merged:
                    nested_namespaces.append(nested_ns)
            elif self.expect(TokenType.IF):
                if_stmt = self.if_statement()
                pass
            elif self.is_variable_declaration():
                var_decl = self.variable_declaration()
                if isinstance(var_decl, list):
                    variables.extend(var_decl)
                    # ADDED: Register variables with qualified names
                    for vd in var_decl:
                        qualified_name = f"{current_namespace}__{vd.name}"
                        self.symbol_table.define(qualified_name, SymbolKind.VARIABLE, vd.type_spec)
                        self.symbol_table.define(vd.name, SymbolKind.VARIABLE, vd.type_spec)
                else:
                    variables.append(var_decl)
                    # ADDED: Register variable with qualified name
                    qualified_name = f"{current_namespace}__{var_decl.name}"
                    self.symbol_table.define(qualified_name, SymbolKind.VARIABLE, var_decl.type_spec)
                    self.symbol_table.define(var_decl.name, SymbolKind.VARIABLE, var_decl.type_spec)
                self.consume(TokenType.SEMICOLON)
            else:
                self.error("Expected function, struct, object, namespace, enum, union, or variable declaration", TokenType.DEF)
        
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        
        # ADDED: Pop namespace from stack
        self._namespace_stack.pop()

        return NamespaceDef(
            name=name,
            functions=functions,
            structs=structs,
            objects=objects,
            enums=enums,
            unions=unions,
            extern_blocks=extern_blocks,
            variables=variables,
            nested_namespaces=nested_namespaces,
            base_namespaces=base_namespaces
        ).set_location(tok.line, tok.column)
    
    def type_spec(self) -> TypeSystem:
        """
        type_spec -> ('global'|'local'|'heap'|'stack'|'register')? ('const')? ('volatile')? ('signed'|'unsigned')? ('~')? base_type alignment? array_spec? pointer_spec?
        array_spec -> ('[' expression? ']')+

        NOTE: Storage class can come FIRST, before qualifiers
        """
        is_tied = False
        is_local = False
        is_const = False
        is_volatile = False
        is_signed = False
        signedness_explicit = False
        storage_class = None
        singinit_seen = False

        if self.expect(TokenType.SINGINIT):
            singinit_seen = True
            storage_class = StorageClass.SINGINIT
            self.advance()

        if self.expect(TokenType.GLOBAL, TokenType.LOCAL, TokenType.HEAP,
                       TokenType.STACK, TokenType.REGISTER):
            if self.expect(TokenType.GLOBAL):
                storage_class = StorageClass.GLOBAL
                self.advance()
            elif self.expect(TokenType.LOCAL):
                is_local = True
                storage_class = StorageClass.LOCAL
                self.advance()
            elif self.expect(TokenType.HEAP):
                storage_class = StorageClass.HEAP
                self.advance()
            elif self.expect(TokenType.STACK):
                storage_class = StorageClass.STACK
                self.advance()
            elif self.expect(TokenType.REGISTER):
                storage_class = StorageClass.REGISTER
                self.advance()
        elif not singinit_seen and self.expect(TokenType.REGISTER):
            storage_class = StorageClass.REGISTER
            self.advance()

        # Allow singinit after a location class too (e.g. heap singinit float[])
        if not singinit_seen and self.expect(TokenType.SINGINIT):
            singinit_seen = True
            self.advance()  # consume it; storage_class already set to the location class

        # Parse qualifiers AFTER storage class
        if self.expect(TokenType.CONST):
            is_const = True
            self.advance()

        if self.expect(TokenType.VOLATILE):
            is_volatile = True
            self.advance()

        if self.expect(TokenType.SIGNED):
            is_signed = True
            signedness_explicit = True
            self.advance()
        elif self.expect(TokenType.UNSIGNED):
            is_signed = False
            signedness_explicit = True
            self.advance()

        # Parse TIE operator (before base type)
        if self.expect(TokenType.TIE):
            is_tied = True
            self.advance()

        # Base type parsing
        base_type_result = self.base_type()
        custom_typename = None

        # Handle custom type names
        if isinstance(base_type_result, list):
            base_type = base_type_result[0]
            if base_type == DataType.DICT:
                # Don't early-return -- fall through so pointer suffix (*) is parsed
                _dict_key_ts = base_type_result[1]
                _dict_val_ts = base_type_result[2]
                # Parse pointer suffix then build the TypeSystem
                _dict_ptr_depth = 0
                while self.expect(TokenType.MULTIPLY):
                    _dict_ptr_depth += 1
                    self.advance()
                return TypeSystem(
                    base_type=DataType.DICT,
                    dict_key_type=_dict_key_ts,
                    dict_value_type=_dict_val_ts,
                    storage_class=storage_class,
                    is_const=is_const,
                    is_volatile=is_volatile,
                    is_pointer=_dict_ptr_depth > 0,
                    pointer_depth=_dict_ptr_depth,
                )
            custom_typename = base_type_result[1]
        else:
            base_type = base_type_result

        # "" as a type means byte* (string).  The sentinel __string__ was set
        # by base_type; resolve it to pointer_depth=1 with no custom typename.
        if custom_typename == '__string__':
            custom_typename = None
            return TypeSystem(
                base_type=DataType.BYTE,
                is_pointer=True,
                pointer_depth=1,
                is_const=is_const,
                is_volatile=is_volatile,
                storage_class=storage_class,
            )

        # Template struct/object instantiation: MyStruct<int> or MyObj<T, U>
        # After parsing a custom typename, check if '<' follows and it names a template struct or object.
        if custom_typename is not None and self.expect(TokenType.LESS_THAN):
            # Resolve the struct name: try the raw token (bare or "NS::bare"), then
            # the __ mangled form ("NS__bare"), so namespace-qualified references work.
            _tmpl_key = None
            _is_object_tmpl = False
            if custom_typename in self._templates and self._templates.lookup(custom_typename).kind == 'struct':
                _tmpl_key = custom_typename
            elif custom_typename in self._templates and self._templates.lookup(custom_typename).kind == 'object':
                _tmpl_key = custom_typename
                _is_object_tmpl = True
            elif custom_typename in self._template_object_forward_decls:
                _tmpl_key = custom_typename
                _is_object_tmpl = True
            else:
                # "XYZ_TEST::myStru2" -> try "XYZ_TEST__myStru2"
                _mangled_attempt = custom_typename.replace("::", "__")
                if _mangled_attempt in self._templates and self._templates.lookup(_mangled_attempt).kind == 'struct':
                    _tmpl_key = _mangled_attempt
                elif _mangled_attempt in self._templates and self._templates.lookup(_mangled_attempt).kind == 'object':
                    _tmpl_key = _mangled_attempt
                    _is_object_tmpl = True
            if _tmpl_key is not None:
                self.advance()  # consume '<'
                type_names = []
                type_specs_list = []
                _first_arg_tok = self.current_token
                ts = self.type_spec()
                type_names.append(self._type_system_to_mangle_str(ts))
                type_specs_list.append(ts)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    ts = self.type_spec()
                    type_names.append(self._type_system_to_mangle_str(ts))
                    type_specs_list.append(ts)
                self.consume(TokenType.GREATER_THAN)
                # If any type argument is still an active template param, defer resolution.
                if any(n in self._active_template_params for n in type_names):
                    custom_typename = f"{_tmpl_key}<{','.join(type_names)}>"
                elif _is_object_tmpl:
                    custom_typename = self._resolve_template_object(
                        _tmpl_key, type_names, type_specs_list, usage_tok=_first_arg_tok)
                else:
                    custom_typename = self._resolve_template_struct(
                        _tmpl_key, type_names, type_specs_list, usage_tok=_first_arg_tok)

        # Bit width and alignment for data types
        bit_width = None
        alignment = None
        endianness = 1  # Default is big-endian in Flux. Primary guarantee, second in AST.

        # Track whether this data type was declared non-functional (data!{N})
        _data_no_functions = False

        if base_type == DataType.DATA and custom_typename is None:
            # Optional '!' before '{' marks the type as non-functional: data!{N}
            if self.expect(TokenType.NOT):
                _data_no_functions = True
                self.advance()  # consume '!'
            if self.expect(TokenType.LEFT_BRACE):
                self.advance()
                bit_width = int(self.consume(TokenType.SINT_LITERAL).value)

                if self.expect(TokenType.COLON):
                    self.advance()
                    alignment = int(self.consume(TokenType.SINT_LITERAL).value)
                    if self.expect(TokenType.COLON):
                        self.advance()
                        endianness = int(self.consume(TokenType.SINT_LITERAL).value)
                elif self.expect(TokenType.SCOPE):
                    self.advance()
                    alignment = bit_width
                    endianness = int(self.consume(TokenType.SINT_LITERAL).value)

                self.consume(TokenType.RIGHT_BRACE)

        # Pointer specification - support multiple levels
        # Must be parsed BEFORE array brackets so that `int*[]` (array of pointers)
        # is handled correctly: base=int, pointer_depth=1, is_array=True.
        pointer_depth = 0
        while self.expect(TokenType.MULTIPLY):
            pointer_depth += 1
            self.advance()

        # Array specification - support multiple dimensions.
        # Parsed AFTER pointer so `int*[]` means "array of int-pointers".
        array_dims = []
        while self.expect(TokenType.LEFT_BRACKET):
            self.advance()
            if not self.expect(TokenType.RIGHT_BRACKET):
                expr = self.expression()
                array_dims.append(expr)
            else:
                array_dims.append(None)
            self.consume(TokenType.RIGHT_BRACKET)

        # Trailing pointer after array brackets: `byte[N]*` means pointer to array.
        # Parsed AFTER array spec so `byte[1]*` means "pointer to byte[1]".
        while self.expect(TokenType.MULTIPLY):
            pointer_depth += 1
            self.advance()

        is_array = len(array_dims) > 0
        array_size = array_dims[0] if array_dims else None
        array_dimensions = array_dims if array_dims else None

        #if custom_typename == "byte":
        #    print(custom_typename)
        #    exit()

        # ---- FULL TYPE ALIAS RESOLUTION (canonicalize) ----
        resolved_spec = None
        if custom_typename is not None:
            resolved_spec = self.symbol_table.get_type_spec(custom_typename)
            #print(resolved_spec)
            #exit()

        if resolved_spec is not None:
            # Start from the alias' full TypeSystem (canonical)
            t = TypeSystem(
                base_type=resolved_spec.base_type,
                is_signed=resolved_spec.is_signed,
                is_const=resolved_spec.is_const,
                is_volatile=resolved_spec.is_volatile,
                is_tied=resolved_spec.is_tied,
                is_local=resolved_spec.is_local,
                bit_width=resolved_spec.bit_width,
                alignment=resolved_spec.alignment,
                endianness=resolved_spec.endianness,
                is_array=resolved_spec.is_array,
                array_size=resolved_spec.array_size,
                array_dimensions=list(resolved_spec.array_dimensions) if resolved_spec.array_dimensions else None,
                array_element_type=resolved_spec.array_element_type,
                is_pointer=resolved_spec.is_pointer,
                pointer_depth=resolved_spec.pointer_depth,
                custom_typename=resolved_spec.custom_typename,
                storage_class=resolved_spec.storage_class,
            )

            # Apply use-site qualifiers (override / add)
            if is_tied:
                t.is_tied = True
            if is_const:
                t.is_const = True
            if is_volatile:
                t.is_volatile = True
            if storage_class is not None:
                t.storage_class = storage_class
                t.is_local = (storage_class == StorageClass.LOCAL)

            # Only override signedness if user explicitly wrote signed/unsigned
            if signedness_explicit:
                t.is_signed = is_signed

            # Apply use-site arrays (append dimensions if alias already has them)
            if is_array:
                if t.array_dimensions:
                    t.is_array = True
                    t.array_dimensions = (array_dimensions or []) + t.array_dimensions
                    t.array_size = t.array_dimensions[0] if t.array_dimensions else t.array_size
                else:
                    t.is_array = True
                    t.array_dimensions = array_dimensions
                    t.array_size = array_size
                # Build element type spec from the resolved alias base type
                if not t.array_element_type:
                    t.array_element_type = TypeSystem(
                        base_type=t.base_type,
                        is_signed=t.is_signed,
                        is_const=t.is_const,
                        is_volatile=t.is_volatile,
                        bit_width=t.bit_width,
                        alignment=t.alignment,
                        endianness=t.endianness,
                        is_array=False,
                        array_size=None,
                        array_dimensions=None,
                        array_element_type=None,
                        is_pointer=False,
                        pointer_depth=0,
                        custom_typename=t.custom_typename,
                        storage_class=t.storage_class,
                    )
                    
            # Apply use-site pointers (add depth)
            if pointer_depth > 0:
                t.is_pointer = True
                t.pointer_depth = (t.pointer_depth or 0) + pointer_depth

            #print(f"[TYPE_SPEC DEBUG] Resolved alias: custom_typename={custom_typename}, is_array={t.is_array}, array_size={t.array_size}, is_pointer={t.is_pointer}, pointer_depth={t.pointer_depth}", file=sys.stdout)
            return t

        if base_type == DataType.BYTE and bit_width is None:
            bit_width = self._default_byte_width
            alignment = alignment if alignment is not None else bit_width

        # No alias: return what we parsed normally.
        # When this is an array type, build an element TypeSystem so that
        # array element loads carry the correct signedness metadata through
        # to arithmetic (preventing sext where zext is required).
        elem_type_spec = None
        if is_array:
            elem_type_spec = TypeSystem(
                base_type=base_type,
                is_signed=is_signed,
                is_const=is_const,
                is_volatile=is_volatile,
                bit_width=bit_width,
                alignment=alignment,
                endianness=endianness,
                is_array=False,
                array_size=None,
                array_dimensions=None,
                array_element_type=None,
                is_pointer=False,
                pointer_depth=0,
                custom_typename=custom_typename,
                storage_class=storage_class
            )

        return TypeSystem(
            base_type=base_type,
            is_signed=is_signed,
            is_const=is_const,
            is_volatile=is_volatile,
            is_tied=is_tied,
            is_local=storage_class == StorageClass.LOCAL,
            bit_width=bit_width,
            alignment=alignment,
            endianness=endianness,
            is_array=is_array,
            array_size=array_size,
            array_dimensions=array_dimensions,
            array_element_type=elem_type_spec,
            is_pointer=pointer_depth > 0,
            pointer_depth=pointer_depth,
            custom_typename=custom_typename,
            storage_class=storage_class,
            no_functions=_data_no_functions,
        )

        #print(f"[TYPE_SPEC DEBUG] Non-alias: custom_typename={custom_typename}, is_array={is_array}, array_size={array_size}, is_pointer={pointer_depth > 0}, pointer_depth={pointer_depth}", file=sys.stdout)
    
    def base_type(self) -> Union[DataType, List]:
        """
        base_type -> 'int' | 'uint' | 'float' | 'char' | 'bool' | 'data' | 'void' | 'struct' | IDENTIFIER
        Returns DataType for built-in types, or [DataType.DATA, typename] for custom types
        """
        if self.expect(TokenType.SINT):
            self.advance()
            return DataType.SINT
        elif self.expect(TokenType.UINT):
            self.advance()
            return DataType.UINT
        elif self.expect(TokenType.FLOAT_KW):
            self.advance()
            return DataType.FLOAT
        elif self.expect(TokenType.DOUBLE_KW):
            self.advance()
            return DataType.DOUBLE
        elif self.expect(TokenType.SLONG):
            self.advance()
            return DataType.SLONG
        elif self.expect(TokenType.ULONG):
            self.advance()
            return DataType.ULONG
        elif self.expect(TokenType.CHAR):
            self.advance()
            return DataType.CHAR
        elif self.expect(TokenType.BOOL_KW):
            self.advance()
            return DataType.BOOL
        elif self.expect(TokenType.BYTE):
            self.advance()
            return DataType.BYTE
        elif self.expect(TokenType.DATA):
            self.advance()
            return DataType.DATA
        elif self.expect(TokenType.DICT):
            # dict{K:V} -- consume 'dict', then parse {KeyType:ValueType}
            self.advance()
            self.consume(TokenType.LEFT_BRACE)
            key_ts = self.type_spec()
            self.consume(TokenType.COLON)
            val_ts = self.type_spec()
            self.consume(TokenType.RIGHT_BRACE)
            return [DataType.DICT, key_ts, val_ts]
        elif self.expect(TokenType.VOID):
            self.advance()
            return DataType.VOID
        elif self.expect(TokenType.THIS):
            self.advance()
            return DataType.THIS
        elif self.expect(TokenType.STRUCT):
            # Handle 'struct' keyword as a generic struct type
            # This allows syntax like: struct* ptr or struct MyStruct
            self.advance()
            return DataType.STRUCT
        elif self.expect(TokenType.STRING_LITERAL) and self.current_token.value == '':
            # "" used as a type specifier means the string (byte*) type.
            self.advance()
            return [DataType.BYTE, '__string__']
        elif self.expect(TokenType.OBJECT):
            self.advance()
            return DataType.OBJECT
        elif self.expect(TokenType.IDENTIFIER):
            # Custom type - return [DataType.DATA, typename]
            # Consume namespace-qualified names: A::B::C
            custom_typename = self.current_token.value
            self.advance()
            while self.expect(TokenType.SCOPE):
                self.advance()  # consume ::
                if self.expect(TokenType.IDENTIFIER):
                    custom_typename = custom_typename + "::" + self.current_token.value
                    self.advance()
                else:
                    break
            return [DataType.DATA, custom_typename]
        elif self.expect(TokenType.CODIFY):
            # ~$varname or ~$f"..." used as a type - resolve string then map to correct DataType
            custom_typename = self._consume_codify()
            _CODIFY_BUILTIN_MAP = {
                'byte': DataType.BYTE, 'int': DataType.SINT, 'uint': DataType.UINT,
                'long': DataType.SLONG, 'ulong': DataType.ULONG, 'float': DataType.FLOAT,
                'double': DataType.DOUBLE, 'bool': DataType.BOOL, 'char': DataType.CHAR,
                'void': DataType.VOID,
            }
            if custom_typename in _CODIFY_BUILTIN_MAP:
                return [_CODIFY_BUILTIN_MAP[custom_typename], None]
            return [DataType.DATA, custom_typename]
        else:
            self.error("Expected type specifier", TokenType.IDENTIFIER)
    
    def is_variable_declaration(self) -> bool:
        """
        Check if the current position starts a variable declaration.
        Uses the _lookahead context manager for cleaner position management.
        """
        with self._lookahead():
            # Skip const/volatile qualifiers
            if self.expect(TokenType.CONST):
                self.advance()
            if self.expect(TokenType.VOLATILE):
                self.advance()
            
            # Skip signedness
            if self.expect(TokenType.SIGNED, TokenType.UNSIGNED):
                self.advance()

            if self.expect(TokenType.TIE):
                self.advance()
            
            # Must have a base type
            if not self.expect(TokenType.SINT, TokenType.UINT, TokenType.FLOAT_KW, TokenType.DOUBLE_KW,
                             TokenType.CHAR,  TokenType.BOOL_KW, TokenType.BYTE, TokenType.DATA, TokenType.VOID, 
                             TokenType.SLONG, TokenType.ULONG,
                             TokenType.STRUCT, TokenType.OBJECT, TokenType.IDENTIFIER, TokenType.DICT):
                return False
            
            self.advance()
            
            # Handle namespace-qualified type names: A::B::C
            while self.expect(TokenType.SCOPE):
                self.advance()  # consume ::
                if self.expect(TokenType.IDENTIFIER):
                    self.advance()
                else:
                    break

            # Handle template args: MyStruct<int> or MyStruct<T, U>
            if self.expect(TokenType.LESS_THAN):
                self.advance()  # consume '<'
                depth = 1
                while depth > 0 and not self.expect(TokenType.EOF):
                    if self.expect(TokenType.LESS_THAN):
                        depth += 1
                    elif self.expect(TokenType.GREATER_THAN):
                        depth -= 1
                        if depth == 0:
                            break
                    self.advance()
                if self.expect(TokenType.GREATER_THAN):
                    self.advance()

            # Handle optional bit-width/alignment specification {width:alignment}
            if self.expect(TokenType.LEFT_BRACE):
                self.advance()
                if self.expect(TokenType.SINT_LITERAL):
                    self.advance()
                if self.expect(TokenType.COLON):
                    self.advance()
                    if self.expect(TokenType.SINT_LITERAL):
                        self.advance()
                elif self.expect(TokenType.SCOPE):
                    self.advance()
                    if self.expect(TokenType.SINT_LITERAL):
                        self.advance()
                if self.expect(TokenType.RIGHT_BRACE):
                    self.advance()

            # Consume leading pointer levels (mirrors type_spec order: ptr then bracket)
            while self.expect(TokenType.MULTIPLY):
                self.advance()
            
            # Handle array dimensions
            while self.expect(TokenType.LEFT_BRACKET):
                self.advance()
                if not self.expect(TokenType.RIGHT_BRACKET):
                    # Skip through array size expression
                    bracket_depth = 1
                    while bracket_depth > 0 and not self.expect(TokenType.EOF):
                        if self.expect(TokenType.LEFT_BRACKET):
                            bracket_depth += 1
                        elif self.expect(TokenType.RIGHT_BRACKET):
                            bracket_depth -= 1
                            if bracket_depth == 0:
                                break
                        self.advance()
                if self.expect(TokenType.RIGHT_BRACKET):
                    self.advance()
            
            # Consume all pointer levels (*, **, ***, etc.)
            while self.expect(TokenType.MULTIPLY):
                self.advance()
            
            # Handle type alias ('as' keyword)
            if self.expect(TokenType.AS):
                self.advance()
                if self.expect(TokenType.VOID):
                    return False
                return self.expect(TokenType.IDENTIFIER)
            
            # Must have an identifier for the variable name
            if not self.expect(TokenType.IDENTIFIER):
                return False
            
            self.advance()
            
            # Variable declaration should be followed by one of these tokens
            return self.expect(TokenType.ASSIGN, TokenType.SEMICOLON, 
                             TokenType.LEFT_PAREN, TokenType.LEFT_BRACE,
                             TokenType.COMMA, TokenType.LEFT_BRACKET, TokenType.FROM,
                             TokenType.ADDRESS_ASSIGN)

    def is_dual_assign_declaration(self) -> bool:
        """
        Check if the current position starts a dual-assign declaration:
            success_type ^| error_type success_name, error_name = call();

        Strategy: consume the leading type spec (same logic as is_variable_declaration),
        then check that the next token is XOR_OP.
        """
        with self._lookahead():
            # Skip const/volatile/signed/unsigned qualifiers
            if self.expect(TokenType.CONST):
                self.advance()
            if self.expect(TokenType.VOLATILE):
                self.advance()
            if self.expect(TokenType.SIGNED, TokenType.UNSIGNED):
                self.advance()

            # Must have a base type
            if not self.expect(TokenType.SINT, TokenType.UINT, TokenType.FLOAT_KW, TokenType.DOUBLE_KW,
                               TokenType.CHAR, TokenType.BOOL_KW, TokenType.BYTE, TokenType.DATA, TokenType.VOID,
                               TokenType.SLONG, TokenType.ULONG,
                               TokenType.STRUCT, TokenType.OBJECT, TokenType.IDENTIFIER, TokenType.DICT):
                return False
            self.advance()

            # Handle namespace-qualified type names: A::B::C
            while self.expect(TokenType.SCOPE):
                self.advance()
                if self.expect(TokenType.IDENTIFIER):
                    self.advance()
                else:
                    break

            # Handle template args: MyStruct<int>
            if self.expect(TokenType.LESS_THAN):
                self.advance()
                depth = 1
                while depth > 0 and not self.expect(TokenType.EOF):
                    if self.expect(TokenType.LESS_THAN):
                        depth += 1
                    elif self.expect(TokenType.GREATER_THAN):
                        depth -= 1
                        if depth == 0:
                            break
                    self.advance()
                if self.expect(TokenType.GREATER_THAN):
                    self.advance()

            # Handle optional bit-width specification {width}
            if self.expect(TokenType.LEFT_BRACE):
                self.advance()
                if self.expect(TokenType.SINT_LITERAL):
                    self.advance()
                if self.expect(TokenType.COLON) or self.expect(TokenType.SCOPE):
                    self.advance()
                    if self.expect(TokenType.SINT_LITERAL):
                        self.advance()
                if self.expect(TokenType.RIGHT_BRACE):
                    self.advance()

            # Skip pointer levels
            while self.expect(TokenType.MULTIPLY):
                self.advance()

            # Skip array dimensions
            while self.expect(TokenType.LEFT_BRACKET):
                self.advance()
                bracket_depth = 1
                while bracket_depth > 0 and not self.expect(TokenType.EOF):
                    if self.expect(TokenType.LEFT_BRACKET):
                        bracket_depth += 1
                    elif self.expect(TokenType.RIGHT_BRACKET):
                        bracket_depth -= 1
                        if bracket_depth == 0:
                            break
                    self.advance()
                if self.expect(TokenType.RIGHT_BRACKET):
                    self.advance()

            # After the type spec the next token must be XOR_OP (^|)
            return self.expect(TokenType.XOR_OP)

    # ------------------------------------------------------------------
    # Type function definitions
    # ------------------------------------------------------------------

    # Tokens that may begin the "receiver" of a type function definition.
    # These are all the primitive type keywords plus literal tokens plus
    # STRING_LITERAL (for the "" receiver).
    _TYPE_FUNC_RECEIVER_TOKENS = frozenset({
        # Type keywords
        TokenType.BYTE,
        TokenType.SINT,
        TokenType.UINT,
        TokenType.SLONG,
        TokenType.ULONG,
        TokenType.FLOAT_KW,
        TokenType.DOUBLE_KW,
        TokenType.BOOL_KW,
        # TRUE/FALSE used as bool null literals
        TokenType.TRUE,
        TokenType.FALSE,
        # Numeric literal null forms (0, 0u, 0l, 0ul, 0f, 0d)
        TokenType.SINT_LITERAL,
        TokenType.UINT_LITERAL,
        TokenType.SLONG_LITERAL,
        TokenType.ULONG_LITERAL,
        TokenType.FLOAT,
        TokenType.DOUBLE,
        # char type keyword / char literal
        TokenType.CHAR,
        # String literal null form ("") or f-string/i-string form (f"", i"")
        TokenType.STRING_LITERAL,
        TokenType.F_STRING,
        TokenType.I_STRING,
        # Named struct: IDENTIFIER handled separately in _is_type_func_def
    })

    def _consume_codify(self) -> str:
        """
        After CODIFY (~$) has been detected, consume it plus the following
        IDENTIFIER or F_STRING/I_STRING and return the resolved string value.
        Handles: ~$varname  ~$f"{x}"  ~$i"{x}"
        """
        self.advance()  # consume CODIFY
        if self.expect(TokenType.F_STRING):
            raw = self.consume(TokenType.F_STRING).value
            fstr = self.parse_f_string(raw[2:-1])
            return "".join(p if isinstance(p, str) else self._comptime_strings.get(p.name, p.name) for p in fstr.parts)
        elif self.expect(TokenType.I_STRING):
            istr = self.parse_i_string(self.consume(TokenType.I_STRING).value)
            return "".join(p if isinstance(p, str) else self._comptime_strings.get(p.name, p.name) for p in istr.parts)
        else:
            var_name = self.consume(TokenType.IDENTIFIER).value
            return self._comptime_strings.get(var_name, var_name)

    def _resolve_fstring_name(self, node) -> str:
        """
        Attempt to resolve an FStringLiteral to a plain string at parse time.
        Used to get compile-time method names like f"{z}" where z is a known global.
        Returns the resolved string, or falls back to str(node) if unresolvable.
        """
        parts = []
        for part in node.parts:
            if isinstance(part, str):
                clean = part[2:] if part.startswith('f"') else part
                clean = clean[:-1] if clean.endswith('"') else clean
                parts.append(clean)
            elif isinstance(part, Identifier):
                # Look up in _comptime_strings (populated for byte* string-literal globals)
                val = self._comptime_strings.get(part.name)
                if val is not None:
                    parts.append(val)
                else:
                    return str(node)  # unresolvable
            else:
                return str(node)  # unresolvable
        return ''.join(parts)

    def _is_type_func_def(self) -> bool:
        """
        Lookahead predicate: returns True when the current position begins a
        type function definition of the form

            RECEIVER.func_name([params]) -> return_type { body } ;
            RECEIVER.func_name([params]) -> return_type ;          (prototype)

        where RECEIVER is a type keyword, literal, or named struct identifier.
        The lookahead never consumes tokens.
        """
        with self._lookahead():
            tok = self.current_token

            # Must start with a recognised receiver token or an IDENTIFIER (struct name)
            # Optionally preceded by '~' for a tied-type receiver: ~byte*.func()
            if tok.type == TokenType.TIE:
                self.advance()
                tok = self.current_token
            if tok.type in self._TYPE_FUNC_RECEIVER_TOKENS:
                self.advance()
            elif tok.type == TokenType.IDENTIFIER:
                # Could be a named struct type used as receiver.
                # We'll accept if it is followed by '.' IDENTIFIER '('
                self.advance()
            else:
                return False

            # Skip any pointer stars: byte*.func(), int**.func(), etc.
            while self.expect(TokenType.MULTIPLY):
                self.advance()

            # Skip bare array brackets: FieldSpec[].func(), int[].func(), etc.
            if self.expect(TokenType.LEFT_BRACKET):
                self.advance()
                if not self.expect(TokenType.RIGHT_BRACKET):
                    return False
                self.advance()

            # Must be followed by '.'
            if not self.expect(TokenType.DOT):
                return False
            self.advance()

            # Then an identifier or string literal (the function name)
            if not self.expect(TokenType.IDENTIFIER, TokenType.STRING_LITERAL, TokenType.F_STRING, TokenType.I_STRING):
                return False
            self.advance()

            # Skip optional template parameter list: <T, U, ...>
            # RECURSE_ARROW '<~' is lexed as a single token; treat it as '<' + implicit '~'
            if self.expect(TokenType.LESS_THAN, TokenType.RECURSE_ARROW):
                self.advance()  # consume '<' or '<~'
                depth_t = 1
                while depth_t > 0 and not self.expect(TokenType.EOF):
                    if self.expect(TokenType.LESS_THAN, TokenType.RECURSE_ARROW):
                        depth_t += 1
                    elif self.expect(TokenType.GREATER_THAN):
                        depth_t -= 1
                        if depth_t == 0:
                            break
                    self.advance()
                if not self.expect(TokenType.GREATER_THAN):
                    return False
                self.advance()  # consume '>'

            # Then '('
            if not self.expect(TokenType.LEFT_PAREN):
                return False
            self.advance()

            # Scan past the parameter list (balanced parentheses)
            depth = 1
            while depth > 0 and not self.expect(TokenType.EOF):
                if self.expect(TokenType.LEFT_PAREN):
                    depth += 1
                elif self.expect(TokenType.RIGHT_PAREN):
                    depth -= 1
                    if depth == 0:
                        break
                self.advance()
            if not self.expect(TokenType.RIGHT_PAREN):
                return False
            self.advance()  # consume ')'

            # Must be followed by '->'
            return self.expect(TokenType.RETURN_ARROW)

    @staticmethod
    def _type_func_receiver_type_name(tok: 'Token') -> Optional[str]:
        """
        Return the canonical type-name string for a type-function receiver
        token, or None if the token is not a recognised receiver.

        The type name is used to build the mangled function name
        ``__typefunc__<type_name>__<func_name>``.
        """
        _KW_MAP = {
            TokenType.BYTE:       'byte',
            TokenType.SINT:       'int',
            TokenType.UINT:       'uint',
            TokenType.SLONG:      'long',
            TokenType.ULONG:      'ulong',
            TokenType.FLOAT_KW:   'float',
            TokenType.DOUBLE_KW:  'double',
            TokenType.BOOL_KW:    'bool',
            TokenType.TRUE:       'bool',
            TokenType.FALSE:      'bool',
            TokenType.SINT_LITERAL:  'int',
            TokenType.UINT_LITERAL:  'uint',
            TokenType.SLONG_LITERAL: 'long',
            TokenType.ULONG_LITERAL: 'ulong',
            TokenType.FLOAT:      'float',
            TokenType.DOUBLE:     'double',
            TokenType.STRING_LITERAL: 'string',
            TokenType.F_STRING:      'string',
            TokenType.I_STRING:      'string',
        }
        if tok.type in _KW_MAP:
            return _KW_MAP[tok.type]
        if tok.type == TokenType.CHAR:
            return 'char'
        # IDENTIFIER: named struct type
        if tok.type == TokenType.IDENTIFIER:
            return tok.value
        return None

    @staticmethod
    def _type_func_receiver_type_spec(type_name: str, pointer_depth: int = 0, is_array: bool = False) -> 'TypeSystem':
        """
        Build a TypeSystem for the implicit ``_`` parameter of a type
        function, given the canonical type-name string, pointer depth, and
        whether the receiver is an unsized array (e.g. FieldSpec[]).
        """
        _BUILTIN_MAP = {
            'byte':   DataType.BYTE,
            'int':    DataType.SINT,
            'uint':   DataType.UINT,
            'long':   DataType.SLONG,
            'ulong':  DataType.ULONG,
            'float':  DataType.FLOAT,
            'double': DataType.DOUBLE,
            'bool':   DataType.BOOL,
            'char':   DataType.CHAR,
        }
        if type_name == 'string' or (type_name == 'byte' and pointer_depth >= 1):
            # byte* / string - i8*
            depth = max(1, pointer_depth)
            return TypeSystem(base_type=DataType.BYTE, pointer_depth=depth, is_pointer=True)
        if type_name in _BUILTIN_MAP:
            base = _BUILTIN_MAP[type_name]
            if is_array:
                return TypeSystem(base_type=base, is_array=True, array_size=None)
            if pointer_depth > 0:
                return TypeSystem(base_type=base, pointer_depth=pointer_depth, is_pointer=True)
            return TypeSystem(base_type=base)
        # Named struct/object type
        if is_array:
            return TypeSystem(base_type=DataType.DATA, custom_typename=type_name,
                              is_array=True, array_size=None)
        if pointer_depth > 0:
            return TypeSystem(base_type=DataType.DATA, custom_typename=type_name,
                              pointer_depth=pointer_depth, is_pointer=True)
        return TypeSystem(base_type=DataType.DATA, custom_typename=type_name)

    def type_func_def(self) -> 'TypeFuncDef':
        """
        Parse a type function definition.

        Syntax:
            RECEIVER.func_name([params]) -> return_type { body } ;
            RECEIVER.func_name([params]) -> return_type ;          (prototype)

        The receiver establishes the type that the function extends.  Within
        the body ``this`` is an implicit first parameter holding the receiver value.
        """
        tok = self.current_token

        # --- Receiver ---
        # Optional leading '~' marks a tied-type receiver: ~byte*.func()
        recv_is_tied = False
        if self.expect(TokenType.TIE):
            recv_is_tied = True
            self.advance()
        recv_tok = self.current_token
        type_name = self._type_func_receiver_type_name(recv_tok)
        if type_name is None:
            self.error("Expected a type keyword, literal, or struct name as type function receiver", TokenType.IDENTIFIER)
        # Non-functional types (declared with data!{N}) cannot have type functions
        if self.symbol_table.is_nofunc(type_name):
            self.error(
                f"Type {type_name} is non-functional (declared with data!) "
                f"and cannot have type functions defined on it"
            )
        self.advance()  # consume receiver token

        # Consume any pointer stars after the base type: byte*.func(), int**.func()
        recv_pointer_depth = 0
        while self.expect(TokenType.MULTIPLY):
            recv_pointer_depth += 1
            self.advance()

        # Consume bare array brackets: FieldSpec[].func(), int[].func(), etc.
        recv_is_array = False
        if self.expect(TokenType.LEFT_BRACKET):
            self.advance()
            self.consume(TokenType.RIGHT_BRACKET)
            recv_is_array = True

        self.consume(TokenType.DOT)

        if self.expect(TokenType.F_STRING, TokenType.I_STRING):
            if self.expect(TokenType.F_STRING):
                _fname_fsl = self.parse_f_string(self.consume(TokenType.F_STRING).value)
            else:
                _fname_fsl = self.parse_i_string(self.consume(TokenType.I_STRING).value)
            func_name = self._resolve_fstring_name(_fname_fsl)
            if func_name == str(_fname_fsl):
                func_name = _fname_fsl
        elif self.expect(TokenType.STRING_LITERAL):
            func_name = self.current_token.value
            self.advance()
        else:
            func_name = self.consume(TokenType.IDENTIFIER).value

        # --- Optional template parameter list: byte.my_func<T, U>(...) ---
        # Supports optional per-param constraints: byte.my_func<T: int | float>(...) ---
        template_params = []
        _typefunc_constraints = {}
        _typefunc_relations = []
        _typefunc_defaults = {}
        _typefunc_no_default = set()
        if self.expect(TokenType.LESS_THAN, TokenType.RECURSE_ARROW):
            # RECURSE_ARROW '<~' is lexed as a single token; split it by consuming it
            # and injecting a synthetic TIE token so the rest of the parser sees '<' + '~'.
            if self.expect(TokenType.RECURSE_ARROW):
                _ra_tok = self.current_token
                _tie_tok = Token(TokenType.TIE, '~', _ra_tok.line, _ra_tok.column + 1)
                self.tokens = self.tokens[:self.position] + [_tie_tok] + self.tokens[self.position:]
                self.tokens[self.position] = Token(TokenType.LESS_THAN, '<', _ra_tok.line, _ra_tok.column)
            with self._lookahead():
                is_template = False
                self.advance()  # consume '<'
                # Accept optional <!+ prefix on first entry
                if self.expect(TokenType.NOT):
                    self.advance()
                    if self.expect(TokenType.PLUS):
                        self.advance()
                if self.expect(TokenType.CODIFY):
                    self.advance()
                # Helper used in lookahead to skip ':{' ... '}'
                def _la_skip_cset_tf():
                    self.advance()  # consume ':'
                    self.advance()  # consume '{'
                    depth = 1
                    while not self.expect(TokenType.EOF):
                        if self.expect(TokenType.LEFT_BRACE):
                            depth += 1
                            self.advance()
                        elif self.expect(TokenType.RIGHT_BRACE):
                            depth -= 1
                            self.advance()
                            if depth == 0:
                                break
                        else:
                            self.advance()
                def _la_skip_type_con_tf():
                    depth = 0
                    while not self.expect(TokenType.EOF):
                        if self.expect(TokenType.LESS_THAN):
                            depth += 1
                            self.advance()
                        elif self.expect(TokenType.GREATER_THAN):
                            if depth == 0:
                                break
                            depth -= 1
                            self.advance()
                        elif self.expect(TokenType.COMMA) and depth == 0:
                            break
                        else:
                            self.advance()
                _la_tf_first_ok = False
                if self.expect(TokenType.COLON):
                    _la_tf_saved = self.position
                    self.advance()
                    if self.expect(TokenType.LEFT_BRACE):
                        self.position = _la_tf_saved
                        self.current_token = self.tokens[self.position]
                        _la_skip_cset_tf()
                        _la_tf_first_ok = True
                    else:
                        self.position = _la_tf_saved
                        self.current_token = self.tokens[self.position]
                elif self.expect(TokenType.IDENTIFIER):
                    self.advance()
                    if self.expect(TokenType.COLON):
                        self.advance()
                        _la_skip_type_con_tf()
                    else:
                        # Skip bare relation (accepted here so real parse can error properly)
                        while self.expect(TokenType.LOGICAL_AND):
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER):
                                self.advance()
                        if self._is_relconstraint_op():
                            self._skip_relconstraint_op()
                            if self.expect(TokenType.CODIFY):
                                self.advance()
                                if self.expect(TokenType.IDENTIFIER, TokenType.F_STRING, TokenType.I_STRING):
                                    self.advance()
                            elif self.expect(TokenType.IDENTIFIER):
                                self.advance()
                            while self.expect(TokenType.LOGICAL_AND):
                                self.advance()
                                if self.expect(TokenType.CODIFY):
                                    self.advance()
                                    if self.expect(TokenType.IDENTIFIER, TokenType.F_STRING, TokenType.I_STRING):
                                        self.advance()
                                elif self.expect(TokenType.IDENTIFIER):
                                    self.advance()
                    _la_tf_first_ok = True
                if _la_tf_first_ok:
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        if self.expect(TokenType.NOT):
                            self.advance()
                            if self.expect(TokenType.PLUS):
                                self.advance()
                        if self.expect(TokenType.COLON):
                            _la_tf_saved2 = self.position
                            self.advance()
                            if self.expect(TokenType.LEFT_BRACE):
                                self.position = _la_tf_saved2
                                self.current_token = self.tokens[self.position]
                                _la_skip_cset_tf()
                            else:
                                self.position = _la_tf_saved2
                                self.current_token = self.tokens[self.position]
                                break
                        elif self.expect(TokenType.CODIFY):
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER, TokenType.F_STRING, TokenType.I_STRING):
                                self.advance()  # consume token after CODIFY
                            if self.expect(TokenType.COLON):
                                self.advance()
                                _la_skip_type_con_tf()
                        elif not self.expect(TokenType.IDENTIFIER):
                            break
                        else:
                            self.advance()
                            if self.expect(TokenType.COLON):
                                self.advance()
                                _la_skip_type_con_tf()
                            else:
                                # Skip bare relation in subsequent entry
                                while self.expect(TokenType.LOGICAL_AND):
                                    self.advance()
                                    if self.expect(TokenType.IDENTIFIER):
                                        self.advance()
                                if self._is_relconstraint_op():
                                    self._skip_relconstraint_op()
                                    if self.expect(TokenType.CODIFY):
                                        self.advance()
                                        if self.expect(TokenType.IDENTIFIER):
                                            self.advance()
                                    elif self.expect(TokenType.IDENTIFIER):
                                        self.advance()
                                    while self.expect(TokenType.LOGICAL_AND):
                                        self.advance()
                                        if self.expect(TokenType.CODIFY):
                                            self.advance()
                                            if self.expect(TokenType.IDENTIFIER):
                                                self.advance()
                                        elif self.expect(TokenType.IDENTIFIER):
                                            self.advance()
                    if self.expect(TokenType.GREATER_THAN):
                        is_template = True
            if is_template:
                (template_params, _typefunc_constraints,
                 _typefunc_relations, _typefunc_defaults,
                 _typefunc_no_default) = self._parse_template_param_list(allow_codify=True)

        # Expose template param names so type_spec() inside params/return type defers them.
        _tf_tmpl_scope_ctx = self._template_scope(template_params if template_params else [])
        _tf_tmpl_scope_ctx.__enter__()

        self.consume(TokenType.LEFT_PAREN)
        parameters = []
        if not self.expect(TokenType.RIGHT_PAREN):
            parameters = self.parameter_list()
        self.consume(TokenType.RIGHT_PAREN)

        self.consume(TokenType.RETURN_ARROW)
        return_type = self.type_spec()

        receiver_ts = self._type_func_receiver_type_spec(type_name, recv_pointer_depth, recv_is_array)
        if recv_is_tied:
            receiver_ts.is_tied = True

        # Derive the canonical type name used for mangling.
        # byte* and "" both map to 'string' so they share the same type func namespace.
        # A leading '~' marks a tied-type receiver, prefixed with 'tied_'.
        if recv_pointer_depth > 0 and type_name == 'byte':
            effective_type_name = 'string'
        elif recv_pointer_depth > 0:
            effective_type_name = type_name + '_ptr' * recv_pointer_depth
        elif recv_is_array:
            effective_type_name = type_name + '_arr'
        else:
            effective_type_name = type_name
        if recv_is_tied:
            effective_type_name = 'tied_' + effective_type_name

        # Prototype if ';' follows immediately after return type
        if self.expect(TokenType.SEMICOLON):
            self.advance()
            _tf_tmpl_scope_ctx.__exit__(None, None, None)
            if template_params:
                mangled_base = f"__typefunc__{effective_type_name}__{func_name}"
                receiver_param = Parameter(name='_', type_spec=receiver_ts)
                synthetic_fd = FunctionDef(mangled_base, [receiver_param] + list(parameters),
                                           return_type, Block([]), is_prototype=True)
                self._register_template_function(mangled_base, template_params, synthetic_fd,
                                                 _typefunc_constraints, _typefunc_relations,
                                                 _typefunc_defaults, _typefunc_no_default)
                return None
            return TypeFuncDef(
                type_name=effective_type_name,
                func_name=func_name,
                parameters=parameters,
                return_type=return_type,
                body=Block([]),
                receiver_type_spec=receiver_ts,
                is_prototype=True,
            ).set_location(tok.line, tok.column)

        body = self.block()
        self.consume(TokenType.SEMICOLON)

        _tf_tmpl_scope_ctx.__exit__(None, None, None)

        if template_params:
            mangled_base = f"__typefunc__{effective_type_name}__{func_name}"
            receiver_param = Parameter(name='_', type_spec=receiver_ts)
            synthetic_fd = FunctionDef(mangled_base, [receiver_param] + list(parameters),
                                       return_type, body)
            self._register_template_function(mangled_base, template_params, synthetic_fd,
                                             _typefunc_constraints, _typefunc_relations,
                                             _typefunc_defaults, _typefunc_no_default)
            return None

        return TypeFuncDef(
            type_name=effective_type_name,
            func_name=func_name,
            parameters=parameters,
            return_type=return_type,
            body=body,
            receiver_type_spec=receiver_ts,
            is_prototype=False,
        ).set_location(tok.line, tok.column)

    def variable_declaration_statement(self) -> Union[Statement, List[Statement]]:
        """
        variable_declaration_statement -> variable_declaration ';'
        Returns either a single statement or a list of statements for multiple declarations
        """
        decl = self.variable_declaration()
        self.consume(TokenType.SEMICOLON)
        return decl
    
    def variable_declaration(self) -> Union[VariableDeclaration, TypeDeclaration, List[VariableDeclaration]]:
        tok = self.current_token
        if self._loop_depth > 0 and not self._in_for_init:
            # singinit declares a singleton -- it allocates exactly once regardless
            # of how many times the loop iterates, so the warning does not apply
            _is_singinit = self.expect(TokenType.SINGINIT)
            # also check one token ahead in case the declaration starts with a
            # storage class before singinit (e.g. heap singinit ...)
            if not _is_singinit:
                _peek_idx = self.position + 1
                if _peek_idx < len(self.tokens):
                    _is_singinit = self.tokens[_peek_idx].type == TokenType.SINGINIT
            if not _is_singinit:
                self.warn("variable declaration inside a loop body - this will continually allocate new slots on the stack each iteration.")
        # Capture the raw identifier used as a type name before alias resolution wipes custom_typename
        raw_type_identifier = None
        if self.expect(TokenType.IDENTIFIER):
            raw_type_identifier = self.current_token.value
        type_spec = self.type_spec()
        
        if self.expect(TokenType.AS):
            self.advance()
            type_name = self.consume(TokenType.IDENTIFIER).value
            # Register type alias in current scope
            self.symbol_table.define(type_name, SymbolKind.TYPE, type_spec)
            # If declared with data!{N}, record this type as non-functional
            if getattr(type_spec, 'no_functions', False):
                self.symbol_table.mark_nofunc(type_name)
            
            initial_value = None
            if self.expect(TokenType.ASSIGN):
                self.advance()
                initial_value = self.expression()
                
                if isinstance(initial_value, StructLiteral) and initial_value.struct_type is None:
                    if type_spec.custom_typename:
                        initial_value.struct_type = type_spec.custom_typename
                    else:
                        self.error("Struct literal initialization requires a custom type")

            # Check for comma-separated type alias declarations
            if self.expect(TokenType.COMMA):
                declarations = [TypeDeclaration(type_name, type_spec, initial_value)]
                
                while self.expect(TokenType.COMMA):
                    self.advance()
                    alias_name = self.consume(TokenType.IDENTIFIER).value
                    self.symbol_table.define(alias_name, SymbolKind.TYPE, type_spec)
                    if getattr(type_spec, 'no_functions', False):
                        self.symbol_table.mark_nofunc(alias_name)
                    
                    alias_value = None
                    if self.expect(TokenType.ASSIGN):
                        self.advance()
                        alias_value = self.expression()
                        
                        if isinstance(alias_value, StructLiteral) and alias_value.struct_type is None:
                            if type_spec.custom_typename:
                                alias_value.struct_type = type_spec.custom_typename
                            else:
                                self.error("Struct literal initialization requires a custom type")
                    
                    declarations.append(TypeDeclaration(alias_name, type_spec, alias_value))
                
                return [d.set_location(tok.line, tok.column) for d in declarations]
            
            return TypeDeclaration(type_name, type_spec, initial_value).set_location(tok.line, tok.column)
        else:
            name = self.consume(TokenType.IDENTIFIER).value
            self.symbol_table.define(name, SymbolKind.VARIABLE, type_spec)
            
            if self.expect(TokenType.LEFT_PAREN):
                self.advance()
                args = []
                if not self.expect(TokenType.RIGHT_PAREN):
                    args = self.argument_list()
                self.consume(TokenType.RIGHT_PAREN)
                
                if type_spec.custom_typename:
                    constructor_name = f"{type_spec.custom_typename}.__init"
                elif raw_type_identifier is not None:
                    constructor_name = f"{raw_type_identifier}.__init"
                else:
                    constructor_name = type_spec.base_type.value + "__init"
                
                constructor_call = FunctionCall(constructor_name, args)
                var_decl = VariableDeclaration(name, type_spec, constructor_call)
                if type_spec.storage_class == StorageClass.GLOBAL:
                    var_decl.is_global = True
                return var_decl.set_location(tok.line, tok.column)
            
            names = [name]
            initializers = []
            
            # Check if first variable has an initializer or FROM keyword
            if self.expect(TokenType.ADDRESS_ASSIGN):
                # `byte* x @= expr;` is sugar for `byte* x = @expr;`
                addr_tok = self.current_token
                self.advance()
                rhs = self.expression()
                initializers.append(AddressOf(rhs).set_location(addr_tok.line, addr_tok.column))
            elif self.expect(TokenType.FROM):
                # Syntactic sugar: Type name from source; => Type name = Type from source;
                # Optionally: Type name from source!; suppresses invalidation of source.
                self.advance()
                source_expr = self.expression()
                # If the source is a bare struct literal, supply the type context from the declaration
                if isinstance(source_expr, StructLiteral) and source_expr.struct_type is None and type_spec.custom_typename:
                    source_expr.struct_type = type_spec.custom_typename
                # Create StructRecast with the type from type_spec
                if type_spec.custom_typename:
                    from fast import StructRecast, Identifier
                    recast = StructRecast(type_spec.custom_typename, source_expr)
                    # `!` after RHS suppresses invalidation of the source reference
                    if self.expect(TokenType.NOT):
                        self.advance()
                        recast.suppress_invalidate = True
                    else:
                        recast.suppress_invalidate = False
                    initializers.append(recast)
                else:
                    # Primitive type: treat as bit reinterpretation via CastExpression
                    initializers.append(CastExpression(type_spec, source_expr).set_location(tok.line, tok.column))
            elif self.expect(TokenType.ASSIGN):
                self.advance()
                init_expr = self.expression()

                if type_spec.base_type == DataType.DICT:
                    def _dict_ts_key(ts):
                        if ts is None:
                            return 'unknown'
                        base = ts.custom_typename if ts.custom_typename else str(ts.base_type)
                        return base + ('*' * ts.pointer_depth if ts.pointer_depth else '')
                    # Collect all dict operand type_specs from the RHS expression tree
                    operand_types = []
                    stack = [init_expr]
                    while stack:
                        expr = stack.pop()
                        if hasattr(expr, 'operator') and hasattr(expr, 'left') and hasattr(expr, 'right'):
                            stack.append(expr.left)
                            stack.append(expr.right)
                        elif hasattr(expr, 'name'):
                            entry = self.symbol_table.lookup_variable(expr.name)
                            if (entry and entry.type_spec and
                                    getattr(entry.type_spec, 'base_type', None) == DataType.DICT):
                                operand_types.append(entry.type_spec)
                    # 1. Check operands are compatible with each other
                    if len(operand_types) > 1:
                        ref = operand_types[0]
                        for ots in operand_types[1:]:
                            if (_dict_ts_key(ots.dict_key_type)   != _dict_ts_key(ref.dict_key_type) or
                                    _dict_ts_key(ots.dict_value_type) != _dict_ts_key(ref.dict_value_type)):
                                self.error(
                                    f"Dict operands are incompatible: "
                                    f"dict{{{_dict_ts_key(ref.dict_key_type)}:{_dict_ts_key(ref.dict_value_type)}}} "
                                    f"cannot be combined with "
                                    f"dict{{{_dict_ts_key(ots.dict_key_type)}:{_dict_ts_key(ots.dict_value_type)}}}"
                                )
                    # 2. Check RHS result type matches declared type
                    rhs_ts = operand_types[0] if operand_types else None
                    if rhs_ts is not None:
                        dk = _dict_ts_key(type_spec.dict_key_type)
                        dv = _dict_ts_key(type_spec.dict_value_type)
                        rk = _dict_ts_key(rhs_ts.dict_key_type)
                        rv = _dict_ts_key(rhs_ts.dict_value_type)
                        if dk != rk or dv != rv:
                            self.error(
                                f"Dict type mismatch: declared dict{{{dk}:{dv}}} "
                                f"is incompatible with dict{{{rk}:{rv}}}"
                            )

                    # Propagate _known_keys: union of all operand known keys
                    if operand_types:
                        all_known = set()
                        all_have_keys = True
                        for ots in operand_types:
                            if hasattr(ots, '_known_keys') and ots._known_keys is not None:
                                all_known |= ots._known_keys
                            else:
                                all_have_keys = False
                        if all_have_keys:
                            type_spec._known_keys = all_known
                # rewrite `ObjType name = expr` as a constructor call `ObjType name(expr)`
                # Skip the sugar when the RHS is itself a custom operator call or any
                # FunctionCall whose name is registered as returning this object type -
                # in that case init_expr already produces the object value directly.
                _is_custom_op_result = (
                    isinstance(init_expr, FunctionCall) and
                    init_expr.name in self._custom_operators.values()
                )
                if (not _is_custom_op_result and
                        raw_type_identifier is not None and
                        raw_type_identifier in self._object_init_params and
                        self._object_init_params[raw_type_identifier] == 1):
                    constructor_name = f"{raw_type_identifier}.__init"
                    constructor_call = FunctionCall(constructor_name, [init_expr])
                    var_decl = VariableDeclaration(name, type_spec, constructor_call)
                    if type_spec.storage_class == StorageClass.GLOBAL:
                        var_decl.is_global = True
                    return var_decl.set_location(tok.line, tok.column)

                initializers.append(init_expr)
                # Record byte* string-literal initialisers so ~$varname can splice them
                if (isinstance(init_expr, StringLiteral) and
                        type_spec.is_pointer and type_spec.base_type == DataType.BYTE):
                    self._comptime_strings[name] = init_expr.value
            elif self.expect(TokenType.LEFT_BRACE):
                if type_spec.base_type == DataType.DICT:
                    # dict{K:V} Name { k1: v1, k2: v2, ... };
                    self.advance()  # consume '{'
                    entries = []
                    while not self.expect(TokenType.RIGHT_BRACE):
                        key_expr = self.expression()
                        self.consume(TokenType.COLON)
                        val_expr = self.expression()
                        entries.append(key_expr)
                        entries.append(val_expr)
                        if self.expect(TokenType.COMMA):
                            self.advance()
                    self.consume(TokenType.RIGHT_BRACE)
                    capacity = len(entries) // 2
                    type_spec.dict_capacity = capacity
                    # Store known string keys for compile-time lookup validation
                    if all(isinstance(entries[i * 2], StringLiteral) for i in range(capacity)):
                        type_spec._known_keys = {entries[i * 2].value for i in range(capacity)}
                    initializers.append(DictLiteral(entries).set_location(tok.line, tok.column))
                else:
                    self.error(
                        f"Expected {TokenType.ASSIGN.name}, got {TokenType.LEFT_BRACE.name}",
                        expected_type=TokenType.ASSIGN,
                    )
            else:
                initializers.append(None)
            
            if self.expect(TokenType.COMMA) and initializers[0] is None:
                # Mode: int x, y, z  or  int x, y = 1, z  or  int x,y,z = 1,2,3
                # Peek ahead: if after collecting all bare names we see `from` or `=`
                # without a per-name `=` immediately after each name, treat as bulk
                # initializer mode.  But if any name is immediately followed by `=`
                # or `@=`, switch to per-name mode for the remainder.
                while self.expect(TokenType.COMMA):
                    self.advance()
                    var_name = self.consume(TokenType.IDENTIFIER).value
                    self.symbol_table.define(var_name, SymbolKind.VARIABLE, type_spec)
                    names.append(var_name)
                    if self.expect(TokenType.ADDRESS_ASSIGN):
                        addr_tok = self.current_token
                        self.advance()
                        rhs = self.expression()
                        initializers.append(AddressOf(rhs).set_location(addr_tok.line, addr_tok.column))
                    elif self.expect(TokenType.ASSIGN):
                        self.advance()
                        if self.expect(TokenType.DITTO):
                            import copy
                            if not initializers or initializers[-1] is None:
                                self.error("Ditto operator '#\"' used before any initializer to repeat")
                            self.advance()
                            initializers.append(copy.deepcopy(initializers[-1]))
                        else:
                            initializers.append(self.expression())
                    else:
                        initializers.append(None)
                # If no per-name initializers were collected and a bulk assign/from follows, apply it.
                if all(v is None for v in initializers):
                    initializers = []
                    if self.expect(TokenType.FROM):
                        # Mode: type a,b,c,d from source_expr;
                        self.advance()
                        source_expr = self.expression()
                        for i in range(len(names)):
                            initializers.append(ArrayAccess(source_expr, Literal(i, DataType.SINT)))
                    elif self.expect(TokenType.ASSIGN):
                        self.advance()
                        for _ in names:
                            initializers.append(self.expression())
                            if self.expect(TokenType.COMMA):
                                self.advance()
                            else:
                                break
            elif self.expect(TokenType.COMMA):
                # Mode: int x = 1, y = 2, z = 3; each name has its own initializer
                # Also handles: int* px @= x, px2 @= x; (address-assign sugar)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    var_name = self.consume(TokenType.IDENTIFIER).value
                    self.symbol_table.define(var_name, SymbolKind.VARIABLE, type_spec)
                    names.append(var_name)
                    if self.expect(TokenType.ADDRESS_ASSIGN):
                        addr_tok = self.current_token
                        self.advance()
                        rhs = self.expression()
                        initializers.append(AddressOf(rhs).set_location(addr_tok.line, addr_tok.column))
                    elif self.expect(TokenType.ASSIGN):
                        self.advance()
                        if self.expect(TokenType.DITTO):
                            import copy
                            self.advance()
                            initializers.append(copy.deepcopy(initializers[-1]))
                        else:
                            initializers.append(self.expression())
                        # Record byte* string-literal initialisers in comma-chain so ~$varname can splice them
                        if (isinstance(initializers[-1], StringLiteral) and
                                type_spec.is_pointer and type_spec.base_type == DataType.BYTE):
                            self._comptime_strings[var_name] = initializers[-1].value
                    else:
                        initializers.append(None)
            
            # If we have multiple variables, create multiple declarations
            if len(names) > 1:
                if len(initializers) < len(names):
                    initializers = [None] * (len(names) - len(initializers)) + initializers
                # Create a declaration for each variable
                declarations = []
                for i, var_name in enumerate(names):
                    init_val = initializers[i] if i < len(initializers) else None
                    
                    if init_val and isinstance(init_val, StructLiteral) and init_val.struct_type is None:
                        if type_spec.custom_typename:
                            init_val.struct_type = type_spec.custom_typename
                    
                    var_decl = VariableDeclaration(var_name, type_spec, init_val)
                    if type_spec.storage_class == StorageClass.GLOBAL:
                        var_decl.is_global = True
                    declarations.append(var_decl.set_location(tok.line, tok.column))
                
                return declarations
            else:
                # Single variable declaration
                initial_value = initializers[0] if initializers else None
                
                if initial_value and isinstance(initial_value, StructLiteral) and initial_value.struct_type is None:
                    if type_spec.custom_typename:
                        initial_value.struct_type = type_spec.custom_typename
                
                var_decl = VariableDeclaration(names[0], type_spec, initial_value)
                
                if type_spec.storage_class == StorageClass.GLOBAL:
                    var_decl.is_global = True
                
                return var_decl.set_location(tok.line, tok.column)
    
    def block_statement(self) -> Union[Block, IfStatement]:
        """
        block_statement -> block (('if' '(' expression ')') ('else' block)? ';')?

        Supports the postfix-if form:
            { stmt1; stmt2; } if (cond);
            { stmt1; stmt2; } if (cond) else { stmt3; };

        A bare block-then-block is intentionally rejected here: the 'if'
        keyword MUST follow the closing brace before any second block is
        allowed (the else block).
        """
        tok = self.current_token
        body = self.block()

        # Postfix 'if' on a block: `{ ... } if (cond);`
        if self.expect(TokenType.IF):
            self.advance()
            self.consume(TokenType.LEFT_PAREN, "Expected '(' after 'if' in block-if statement")
            condition = self.expression()
            self.consume(TokenType.RIGHT_PAREN, "Expected ')' after condition in block-if statement")

            # Optional else block - but NOT an immediate bare block (that would
            # be ambiguous / wrong syntax).  Only 'else { ... }' is accepted.
            else_block = None
            if self.expect(TokenType.ELSE):
                self.advance()
                else_block = self.block()

            self.consume(TokenType.SEMICOLON)
            return IfStatement(condition, body, [], else_block).set_location(tok.line, tok.column)

        # Plain anonymous block - no postfix condition.
        # Reject an immediately following block: `{ ... } { ... }` is not valid.
        if self.expect(TokenType.LEFT_BRACE):
            self.error("Unexpected block after block statement. Did you mean '{ ... } if (cond);'?", TokenType.LEFT_BRACE)

        self.consume(TokenType.SEMICOLON)
        return body
    
    def block(self) -> Block:
        tok = self.current_token
        self.consume(TokenType.LEFT_BRACE)
        
        statements = []
        while not self.expect(TokenType.RIGHT_BRACE):
            stmt = self.statement()
            if stmt:
                # Handle multiple declarations returned as a list
                if isinstance(stmt, list):
                    statements.extend(stmt)
                    self._last_stmt = stmt[-1]
                else:
                    statements.append(stmt)
                    self._last_stmt = stmt
        
        self.consume(TokenType.RIGHT_BRACE)
        
        return Block(statements).set_location(tok.line, tok.column)

    def asm_statement(self, is_volatile: bool = False) -> ExpressionStatement:
        """
        asm_statement -> ('volatile')? 'asm' ASM_BLOCK (':' operand_list)? (':' operand_list)? (':' clobber_list)? ';'
                       | ('volatile')? 'asm' ASM_BLOCK ';'   # shorthand when no outputs, inputs, or clobbers
        """
        tok = self.current_token
        # Check for volatile keyword if not already passed in
        if not is_volatile and self.expect(TokenType.VOLATILE):
            is_volatile = True
            self.advance()

        self.consume(TokenType.ASM)

        # Get the ASM block content
        asm_block_token = self.consume(TokenType.ASM_BLOCK)
        asm_body = asm_block_token.value

        # If a ';' follows the block directly, skip all colon sections - no operands or clobbers.
        output_operands = ""
        input_operands = ""
        clobber_list = ""
        if not self.expect(TokenType.SEMICOLON):
            # Parse optional output operands (first colon)
            if self.expect(TokenType.COLON):
                self.advance()
                output_operands = self.parse_operand_list()

            # Parse optional input operands (second colon)
            if self.expect(TokenType.COLON):
                self.advance()
                input_operands = self.parse_operand_list()

            # Parse optional clobber list (third colon)
            if self.expect(TokenType.COLON):
                self.advance()
                clobber_list = self.parse_clobber_list()

        self.consume(TokenType.SEMICOLON)
        
        # Construct constraints string for LLVM
        # The full LLVM inline asm syntax is: asm "code" : outputs : inputs : clobbers
        constraints = ""
        if output_operands or input_operands or clobber_list:
            # Build full constraint string with all parts
            constraint_parts = []
            
            # Add output operands
            if output_operands:
                constraint_parts.append(output_operands)
            else:
                constraint_parts.append("")  # Empty output section
            
            # Add input operands if any inputs or clobbers exist
            if input_operands or clobber_list:
                if input_operands:
                    constraint_parts.append(input_operands)
                else:
                    constraint_parts.append("")  # Empty input section
            
            # Add clobber list if it exists
            if clobber_list:
                constraint_parts.append(clobber_list)
            
            # Join with colons for LLVM format
            constraints = ":".join(constraint_parts)
        
        asm_node = InlineAsm(
            body=asm_body,
            is_volatile=is_volatile,
            constraints=constraints
        )
        asm_node.set_location(tok.line, tok.column)
        return ExpressionStatement(asm_node).set_location(tok.line, tok.column)
    
    def fluxvm_statement(self) -> 'FluxVMBlock':
        """
        fluxvm_statement -> 'fluxvm' FLUXVM_BLOCK ';'
        Parses inline FVM bytecode. The block content is stored as raw text
        for assembly by fvmcodegen._visit_fluxvm_block at comptime.
        """
        from fast import FluxVMBlock
        from flexer import TokenType
        tok = self.current_token
        self.consume(TokenType.FLUXVM)
        block_token = self.consume(TokenType.FLUXVM_BLOCK)
        self.consume(TokenType.SEMICOLON)
        return FluxVMBlock(body=block_token.value).set_location(tok.line, tok.column)

    def comptime_block(self) -> ComptimeBlock:
        """
        comptime_block -> 'comptime' IDENTIFIER? '{' statement* '}' ';'
        Parses a compile-time execution block. The body may contain any valid
        Flux statements plus emitflux blocks.
        An optional name allows the block to be targeted by goto inside other
        comptime blocks: `comptime MyBlock { ... };`
        """
        tok = self.current_token
        self.consume(TokenType.COMPTIME)
        block_name = None
        if self.expect(TokenType.IDENTIFIER):
            block_name = self.current_token.value
            self.advance()
        self.consume(TokenType.LEFT_BRACE)
        self._in_comptime += 1
        body = []
        while not self.expect(TokenType.RIGHT_BRACE):
            if self.expect(TokenType.EOF):
                self.error("Unexpected EOF inside 'comptime' block")
            stmt = self.statement()
            if isinstance(stmt, list):
                body.extend(s for s in stmt if s is not None)
            elif stmt is not None:
                body.append(stmt)
        self._in_comptime -= 1
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        return ComptimeBlock(body=body, name=block_name).set_location(tok.line, tok.column)

    def _token_to_source(self, t) -> str:
        """
        Reconstruct the source text of a single token as it would appear in Flux source.
        Used by emitflux_statement to capture the raw body text.
        """
        tt = t.type
        if tt == TokenType.STRING_LITERAL:
            # Re-add quotes; escape any contained double-quotes and backslashes
            escaped = t.value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        if tt == TokenType.CHAR:
            # Numeric char literals (97c) must round-trip as digits + suffix, not as a
            # quoted character -- otherwise codified source would reconstruct '97' (a
            # two-character string literal) instead of the original 97c.
            if t.value.isdigit():
                return f"{t.value}c"
            escaped = t.value.replace('\\', '\\\\').replace("'", "\\'")
            return f"'{escaped}'"
        if tt == TokenType.BYTE_LITERAL:
            return f"{t.value}b"
        if tt == TokenType.F_STRING:
            # F-string token value includes the f" prefix and closing "
            return t.value
        if tt == TokenType.G_STRING:
            escaped = t.value.replace('\\', '\\\\').replace('"', '\\"')
            return f'g"{escaped}"'
        if tt == TokenType.I_STRING:
            return t.value
        # For all other tokens the value is already the source text
        # (keywords, identifiers, numeric literals, operators)
        if t.value:
            return t.value
        # Fall back to the reverse token-type map
        from flexer import _TOKEN_TYPE_TO_STR
        return _TOKEN_TYPE_TO_STR.get(tt, '')

    def emitflux_statement(self) -> EmitFlux:
        """
        emitflux_statement -> 'emitflux' '{' <raw source text> '}' ';'
        Captures the raw Flux source text between braces without parsing it.
        Nested braces are handled by depth counting.
        """
        tok = self.current_token
        self.consume(TokenType.EMITFLUX)
        self.consume(TokenType.LEFT_BRACE)
        # Scan the token stream for the matching closing brace, collecting source text.
        depth = 1
        parts = []
        while depth > 0:
            if self.expect(TokenType.EOF):
                self.error("Unexpected EOF inside 'emitflux' block")
            # #}; -- escaped close-brace-semicolon: captured as }; without affecting depth
            if self.expect(TokenType.TAG):
                _p1 = self.peek(1)
                _p2 = self.peek(2)
                if (_p1 is not None and _p1.type == TokenType.RIGHT_BRACE and
                        _p2 is not None and _p2.type == TokenType.SEMICOLON):
                    self.advance()  # past #
                    parts.append('}')
                    self.advance()  # past }
                    parts.append(';')
                    self.advance()  # past ;
                    continue
                else:
                    parts.append(self._token_to_source(self.current_token))
                    self.advance()
                    continue
            if self.expect(TokenType.LEFT_BRACE):
                depth += 1
                parts.append('{')
            elif self.expect(TokenType.RIGHT_BRACE):
                # Check for early-terminator syntax: } # emitflux;
                # This terminates the emitflux block at any depth.
                # peek(1) is the token after the closing brace.
                _peek1 = self.peek(1)
                _peek2 = self.peek(2)
                if (_peek1 is not None and _peek1.type == TokenType.TAG):
                    # The }# is the terminator token, not content -- do not append it.
                    # The open structure is intentionally left unclosed in this emission;
                    # Consume }, # -- semicolon consumed below
                    self.advance()  # past }
                    self.advance()  # past #
                    break
                depth -= 1
                if depth > 0:
                    parts.append('}')
                else:
                    # Matching close brace -- advance past it and stop
                    self.advance()
                    break
            else:
                parts.append(self._token_to_source(self.current_token))
            self.advance()
        self.consume(TokenType.SEMICOLON)
        # Merge ~$ with the immediately following token (f-string, i-string, or identifier)
        # to avoid reconstructing "~$ f"..."" with a spurious space.
        merged = []
        idx = 0
        while idx < len(parts):
            if parts[idx] == '~$' and idx + 1 < len(parts):
                merged.append('~$' + parts[idx + 1])
                idx += 2
            else:
                merged.append(parts[idx])
                idx += 1
        source_text = ' '.join(merged)
        return EmitFlux(source_text=source_text).set_location(tok.line, tok.column)

    def parse_operand_list(self) -> str:
        """
        Parse operand list like: "=r" (variable), "m" (memory)
        """
        operands = []
        
        # Handle empty operand list
        if self.expect(TokenType.COLON, TokenType.SEMICOLON):
            return ""
        
        while not self.expect(TokenType.COLON, TokenType.SEMICOLON):
            # Parse constraint string
            if self.expect(TokenType.STRING_LITERAL):
                constraint = self.current_token.value
                self.advance()
                
                # Parse operand expression in parentheses
                if self.expect(TokenType.LEFT_PAREN):
                    self.advance()
                    # For now, just consume until closing paren
                    operand_expr = ""
                    paren_depth = 1
                    while paren_depth > 0 and not self.expect(TokenType.EOF):
                        if self.expect(TokenType.LEFT_PAREN):
                            paren_depth += 1
                        elif self.expect(TokenType.RIGHT_PAREN):
                            paren_depth -= 1
                        
                        if paren_depth > 0:
                            operand_expr += self.current_token.value
                        self.advance()
                    
                    operands.append(f'"{constraint}"({operand_expr})')
                
                # Handle comma separation
                if self.expect(TokenType.COMMA):
                    self.advance()
            else:
                # Skip unexpected tokens
                self.advance()
        
        return ",".join(operands)
    
    def parse_clobber_list(self) -> str:
        """
        Parse clobber list like: "rax", "rcx", "memory"
        """
        clobbers = []
        
        # Handle empty clobber list
        if self.expect(TokenType.SEMICOLON):
            return ""
        
        while not self.expect(TokenType.SEMICOLON):
            if self.expect(TokenType.STRING_LITERAL):
                clobbers.append(f'"{self.current_token.value}"')
                self.advance()
                
                if self.expect(TokenType.COMMA):
                    self.advance()
            else:
                # Skip unexpected tokens
                self.advance()
        
        return ",".join(clobbers)
    
    def block_or_single_stmt(self) -> Block:
        """
        block_or_single_stmt -> '{' ... '}'
                              | '->' expression
                              | expression

        Single-statement form does NOT consume a trailing ';'. The
        enclosing if_statement owns the ';' between branches and the
        final terminating ';'.
        Result is always a Block.
        """
        tok = self.current_token
        if self.expect(TokenType.LEFT_BRACE):
            return self.block()
        if self.expect(TokenType.RETURN_ARROW):
            self.advance()
            expr = self.expression()
            stmt = ReturnStatement(expr).set_location(tok.line, tok.column)
        else:
            expr = self.expression()
            stmt = ExpressionStatement(expr).set_location(tok.line, tok.column)
        return Block([stmt]).set_location(tok.line, tok.column)

    def if_statement(self) -> IfStatement:
        """
        if_statement -> 'if' '(' expression ')' block_or_single_stmt
                        (('elif' | 'else' 'if') '(' expression ')' block_or_single_stmt)*
                        ('else' block_or_single_stmt)? ';'

        Braceless single-statement bodies do not carry their own ';'.
        The single ';' at the end of the chain terminates the whole if.
        Brace-block bodies also work and the same terminating ';' applies.
        """
        tok = self.current_token
        self.consume(TokenType.IF)
        self.consume(TokenType.LEFT_PAREN)
        condition = self.expression()
        self.consume(TokenType.RIGHT_PAREN)
        then_block = self.block_or_single_stmt()

        elif_blocks = []
        while self.expect(TokenType.ELIF) or (self.expect(TokenType.ELSE) and self.peek() and self.peek().type == TokenType.IF):
            if self.expect(TokenType.ELIF):
                self.advance()
            else:
                self.advance()  # consume 'else'
                self.advance()  # consume 'if'

            self.consume(TokenType.LEFT_PAREN)
            elif_condition = self.expression()
            self.consume(TokenType.RIGHT_PAREN)
            elif_block = self.block_or_single_stmt()
            elif_blocks.append((elif_condition, elif_block))

        else_block = None
        if self.expect(TokenType.ELSE):
            self.advance()
            else_block = self.block_or_single_stmt()

        self.consume(TokenType.SEMICOLON)
        return IfStatement(condition, then_block, elif_blocks, else_block).set_location(tok.line, tok.column)
    
    def while_statement(self) -> WhileLoop:
        """
        while_statement -> 'while' '(' expression ')' block ';'
        """
        tok = self.current_token
        self.consume(TokenType.WHILE)
        self.consume(TokenType.LEFT_PAREN)
        condition = self.expression()
        self.consume(TokenType.RIGHT_PAREN)
        self._loop_depth += 1
        body = self.block()
        self._loop_depth -= 1
        self.consume(TokenType.SEMICOLON)
        return WhileLoop(condition, body).set_location(tok.line, tok.column)
    
    def do_while_statement(self) -> Union[DoLoop, DoWhileLoop]:
        """
        do_while_statement -> 'do' block ('while' '(' expression ')' ';' | ';')
        
        Supports both:
            do { ... };              # Plain do loop (executes once)
            do { ... } while (cond); # Do-while loop (repeats while condition is true)
        """
        tok = self.current_token
        self.consume(TokenType.DO)
        self._loop_depth += 1
        body = self.block()
        self._loop_depth -= 1
        
        # Check if this is a do-while or plain do
        if self.expect(TokenType.WHILE):
            # Do-while loop
            self.advance()
            self.consume(TokenType.LEFT_PAREN)
            condition = self.expression()
            self.consume(TokenType.RIGHT_PAREN)
            self.consume(TokenType.SEMICOLON)
            return DoWhileLoop(body, condition).set_location(tok.line, tok.column)
        elif self.expect(TokenType.SEMICOLON):
            # Plain do loop
            self.advance()
            return DoLoop(body).set_location(tok.line, tok.column)
        else:
            self.error("Expected 'while' or ';' after do block", TokenType.SEMICOLON)
    
    def for_statement(self) -> Union[ForLoop, ForInLoop]:
        """
        for_statement -> 'for' '(' (for_in_loop | for_c_loop) ')' block ';'
        """
        tok = self.current_token
        self.consume(TokenType.FOR)
        self.consume(TokenType.LEFT_PAREN)
        
        # Check if it's a for-in loop by looking ahead
        is_for_in = False
        
        is_destructure_for_in = False
        with self._lookahead():
            # Look for pattern: identifier (',' identifier)* 'in' expression
            if self.expect(TokenType.IDENTIFIER):
                self.advance()
                while self.expect(TokenType.COMMA):
                    self.advance()
                    if self.expect(TokenType.IDENTIFIER):
                        self.advance()
                    else:
                        break
                if self.expect(TokenType.IN):
                    is_for_in = True
            # Look for pattern: auto '{' identifier (',' identifier)* '}' 'in'
            # or: auto identifier 'in'
            elif self.expect(TokenType.AUTO):
                self.advance()
                if self.expect(TokenType.LEFT_BRACE):
                    self.advance()
                    if self.expect(TokenType.IDENTIFIER):
                        self.advance()
                        while self.expect(TokenType.COMMA):
                            self.advance()
                            if self.expect(TokenType.IDENTIFIER):
                                self.advance()
                            else:
                                break
                        if self.expect(TokenType.RIGHT_BRACE):
                            self.advance()
                            if self.expect(TokenType.IN):
                                is_for_in = True
                                is_destructure_for_in = True
                elif self.expect(TokenType.IDENTIFIER):
                    self.advance()
                    if self.expect(TokenType.IN):
                        is_for_in = True
                        is_destructure_for_in = True

        if is_for_in:
            # for-in loop
            variables = []
            if is_destructure_for_in:
                # consume 'auto'
                self.consume(TokenType.AUTO)
                if self.expect(TokenType.LEFT_BRACE):
                    # auto {x, y, ...} in iterable
                    self.consume(TokenType.LEFT_BRACE)
                    variables.append(self.consume(TokenType.IDENTIFIER).value)
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        variables.append(self.consume(TokenType.IDENTIFIER).value)
                    self.consume(TokenType.RIGHT_BRACE)
                else:
                    # auto x in iterable
                    variables.append(self.consume(TokenType.IDENTIFIER).value)
            else:
                variables.append(self.consume(TokenType.IDENTIFIER).value)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    variables.append(self.consume(TokenType.IDENTIFIER).value)

            self.consume(TokenType.IN)
            iterable = self.expression()
            self.consume(TokenType.RIGHT_PAREN)
            self._loop_depth += 1
            body = self.block()
            self._loop_depth -= 1
            self.consume(TokenType.SEMICOLON)

            return ForInLoop(variables, iterable, body, is_destructure=is_destructure_for_in).set_location(tok.line, tok.column)
        else:
            # C-style for loop
            init = None
            if not self.expect(TokenType.SEMICOLON):
                if self.is_variable_declaration():
                    self._in_for_init = True
                    var_decl = self.variable_declaration()
                    self._in_for_init = False
                    # If multiple declarations, wrap in a Block
                    if isinstance(var_decl, list):
                        init = Block(var_decl)
                    else:
                        init = var_decl
                else:
                    init = ExpressionStatement(self.expression())
            self.consume(TokenType.SEMICOLON)
            
            condition = None
            if not self.expect(TokenType.SEMICOLON):
                condition = self.expression()
            self.consume(TokenType.SEMICOLON)
            
            update = None
            if not self.expect(TokenType.RIGHT_PAREN):
                update = ExpressionStatement(self.expression())
            
            self.consume(TokenType.RIGHT_PAREN)
            self._loop_depth += 1
            body = self.block()
            self._loop_depth -= 1
            self.consume(TokenType.SEMICOLON)
            
            return ForLoop(init, condition, update, body).set_location(tok.line, tok.column)
    
    def switch_statement(self) -> SwitchStatement:
        """
        switch_statement -> 'switch' '(' expression ')' '{' switch_case* '}' ';'
        """
        tok = self.current_token
        self.consume(TokenType.SWITCH)
        self.consume(TokenType.LEFT_PAREN)
        expression = self.expression()
        self.consume(TokenType.RIGHT_PAREN)
        self.consume(TokenType.LEFT_BRACE)
        
        cases = []
        while not self.expect(TokenType.RIGHT_BRACE):
            case = self.switch_case()
            cases.append(case)
        
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)

        # Tagged union switch (v.#) is exhaustively checked at codegen -- no default required.
        # All other switches must have a default case.
        is_tagged_union_switch = (
            isinstance(expression, MemberAccess) and
            expression.member == '#'
        )
        if not is_tagged_union_switch:
            has_default = any(c.value is None for c in cases)
            if not has_default:
                saved = self.current_token
                self.current_token = tok
                self.error("Switch statement requires a default case", TokenType.DEFAULT)
                self.current_token = saved

        return SwitchStatement(expression, cases).set_location(tok.line, tok.column)
    
    def switch_case(self) -> Case:
        """
        switch_case -> ('case' '(' expression ')' | 'default' '{' statement* '}' ';') block
        """
        tok = self.current_token
        value = None
        if self.expect(TokenType.CASE):
            self.advance()
            self.consume(TokenType.LEFT_PAREN)
            value = self.expression()
            self.consume(TokenType.RIGHT_PAREN)
            body = self.block()
        elif self.expect(TokenType.DEFAULT):
            self.advance()
            body = self.block()
            self.consume(TokenType.SEMICOLON)
            value = None
        else:
            self.error("Expected 'case' or 'default'", TokenType.IDENTIFIER)
        return Case(value, body).set_location(tok.line, tok.column)
    
    def try_statement(self) -> TryBlock:
        """
        try_statement -> 'try' block catch_block+ ';'
        """
        tok = self.current_token
        self.consume(TokenType.TRY)
        try_body = self.block()
        
        catch_blocks = []
        while self.expect(TokenType.CATCH):
            self.advance()
            self.consume(TokenType.LEFT_PAREN)
            
            # Handle empty catch blocks (catch-all)
            if self.expect(TokenType.RIGHT_PAREN):
                self.advance()
                catch_body = self.block()
                catch_blocks.append((None, None, catch_body))
            else:
                # Exception type and name
                if self.expect(TokenType.AUTO):
                    self.advance()
                    exception_type = None
                    exception_name = self.consume(TokenType.IDENTIFIER).value
                else:
                    exception_type = self.type_spec()
                    exception_name = self.consume(TokenType.IDENTIFIER).value
                
                self.consume(TokenType.RIGHT_PAREN)
                catch_body = self.block()
                catch_blocks.append((exception_type, exception_name, catch_body))
        
        self.consume(TokenType.SEMICOLON)
        return TryBlock(try_body, catch_blocks).set_location(tok.line, tok.column)
    
    def return_statement(self) -> ReturnStatement:
        """
        return_statement -> 'return' expression? ';'
        """
        tok = self.current_token
        self.consume(TokenType.RETURN)
        value = None
        if not self.expect(TokenType.SEMICOLON):
            value = self.expression()
        self.consume(TokenType.SEMICOLON)
        return ReturnStatement(value).set_location(tok.line, tok.column)

    def return_arrow_ret(self) -> ReturnStatement:
        """
        '->' expression? ';'
        """
        tok = self.current_token
        self.consume(TokenType.RETURN_ARROW)
        value = None
        if not self.expect(TokenType.SEMICOLON):
            value = self.expression()
        self.consume(TokenType.SEMICOLON)
        return ReturnStatement(value).set_location(tok.line, tok.column)
    
    def error_return_statement(self) -> 'ErrorReturnStatement':
        """
        error_return_statement ->
            'error' ';'
            'error' expression ';'
            'error' '->' expression ';'
            'error' 'return' expression ';'

        The 'error' identifier has already been confirmed as the current token.
        """
        tok = self.current_token
        self.advance()  # consume 'error'
        value = None
        if self.expect(TokenType.RETURN_ARROW):
            # error -> expr;
            self.advance()
            value = self.expression()
        elif self.expect(TokenType.RETURN):
            # error return expr;
            self.advance()
            value = self.expression()
        elif not self.expect(TokenType.SEMICOLON):
            # error expr;
            value = self.expression()
        self.consume(TokenType.SEMICOLON)
        return ErrorReturnStatement(value).set_location(tok.line, tok.column)

    def dual_assign_declaration(self) -> 'DualAssignDeclaration':
        """
        dual_assign_declaration ->
            type ^| type IDENTIFIER ',' IDENTIFIER '=' expression ';'

        Declares two variables from a single dual-return call:
            int ^| ErrType result, err = f();
        """
        tok = self.current_token
        success_type = self.type_spec()
        self.consume(TokenType.XOR_OP, "Expected '^|' in dual-assign declaration")
        error_type = self.type_spec()
        success_name = self.consume(TokenType.IDENTIFIER, "Expected success variable name").value
        self.consume(TokenType.COMMA, "Expected ',' between variable names in dual-assign declaration")
        error_name = self.consume(TokenType.IDENTIFIER, "Expected error variable name").value
        self.consume(TokenType.ASSIGN, "Expected '=' in dual-assign declaration")
        call_expr = self.expression()
        self.consume(TokenType.SEMICOLON)
        # Register both names in the symbol table as variables
        self.symbol_table.define(success_name, SymbolKind.VARIABLE, success_type)
        self.symbol_table.define(error_name, SymbolKind.VARIABLE, error_type)
        return DualAssignDeclaration(
            success_type=success_type,
            error_type=error_type,
            success_name=success_name,
            error_name=error_name,
            call_expr=call_expr,
        ).set_location(tok.line, tok.column)

    def break_statement(self) -> BreakStatement:
        """
        break_statement -> 'break' ';'
        """
        tok = self.current_token
        self.consume(TokenType.BREAK)
        if self.expect(TokenType.SWITCH):
            self.consume(TokenType.SEMICOLON)
            return BreakSwitchStatement().set_location(tok.line, tok.column)
        self.consume(TokenType.SEMICOLON)
        return BreakStatement().set_location(tok.line, tok.column)
    
    def continue_statement(self) -> ContinueStatement:
        """
        continue_statement -> 'continue' ';'
        """
        tok = self.current_token
        self.consume(TokenType.CONTINUE)
        self.consume(TokenType.SEMICOLON)
        return ContinueStatement().set_location(tok.line, tok.column)

    def label_statement(self) -> LabelStatement:
        """
        label_statement -> 'label' IDENTIFIER ':'
        """
        tok = self.current_token
        self.consume(TokenType.LABEL)
        if self._loop_depth > 0:
            self.error("'label' is not permitted inside a loop body")
        name = self.consume(TokenType.IDENTIFIER).value
        self.consume(TokenType.COLON)
        return LabelStatement(name).set_location(tok.line, tok.column)

    def goto_statement(self) -> GotoStatement:
        """
        goto_statement -> 'goto' IDENTIFIER ';'
        """
        tok = self.current_token
        self.consume(TokenType.GOTO)
        name = self.consume(TokenType.IDENTIFIER).value
        self.consume(TokenType.SEMICOLON)
        return GotoStatement(name).set_location(tok.line, tok.column)

    def jump_statement(self) -> JumpStatement:
        """
        jump_statement -> 'jump' expression ';'
        The expression must evaluate to an address (pointer or integer literal).
        """
        tok = self.current_token
        self.consume(TokenType.JUMP)
        target = self.expression()
        self.consume(TokenType.SEMICOLON)
        return JumpStatement(target).set_location(tok.line, tok.column)

    def throw_statement(self) -> ThrowStatement:
        """
        throw_statement -> 'throw' '(' expression ')' ';'
        """
        tok = self.current_token
        self.consume(TokenType.THROW)
        self.consume(TokenType.LEFT_PAREN)
        expression = self.expression()
        self.consume(TokenType.RIGHT_PAREN)
        self.consume(TokenType.SEMICOLON)
        return ThrowStatement(expression).set_location(tok.line, tok.column)
    
    def assert_statement(self) -> AssertStatement:
        """
        assert_statement -> 'assert' '(' expression (',' (STRING_LITERAL | F_STRING | I_STRING))? ')' ';'
        """
        tok = self.current_token
        self.consume(TokenType.ASSERT)
        self.consume(TokenType.LEFT_PAREN)
        condition = self.expression()
        
        message = None
        if self.expect(TokenType.COMMA):
            self.advance()
            if self.expect(TokenType.F_STRING):
                f_string_content = self.consume(TokenType.F_STRING).value
                message = self.parse_f_string(f_string_content).set_location(tok.line, tok.column)
            elif self.expect(TokenType.I_STRING):
                i_string_content = self.consume(TokenType.I_STRING).value
                message = self.parse_i_string(i_string_content).set_location(tok.line, tok.column)
            else:
                message = self.consume(TokenType.STRING_LITERAL).value
        
        self.consume(TokenType.RIGHT_PAREN)
        self.consume(TokenType.SEMICOLON)
        return AssertStatement(condition, message).set_location(tok.line, tok.column)

    def defer_statement(self) -> DeferStatement:
        """
        defer_statement -> 'defer' expression ';'
                         | 'defer' '{' statement* '}' ';'
        """
        tok = self.current_token
        self.consume(TokenType.DEFER)

        if self.expect(TokenType.LEFT_BRACE):
            # Block form: defer { stmt1; stmt2; };
            self.advance()
            statements = []
            while not self.expect(TokenType.RIGHT_BRACE):
                stmt = self.statement()
                if stmt:
                    if isinstance(stmt, list):
                        statements.extend(stmt)
                    else:
                        statements.append(stmt)
            self.consume(TokenType.RIGHT_BRACE)
            self.consume(TokenType.SEMICOLON)
            return DeferStatement(expression=None, body=statements).set_location(tok.line, tok.column)

        # Single expression form: defer expr;
        expr = self.expression()
        self.consume(TokenType.SEMICOLON)
        return DeferStatement(expression=expr, body=None).set_location(tok.line, tok.column)

    def escape_statement(self) -> EscapeStatement:
        """
        escape_statement -> 'escape' call_expression ';'
        Only valid inside a <~ recursive function.
        """
        tok = self.current_token
        self.consume(TokenType.ESCAPE_KW)
        expr = self.expression()
        self.consume(TokenType.SEMICOLON)
        return EscapeStatement(expr).set_location(tok.line, tok.column)

    def noreturn_statement(self) -> 'NoreturnStatement':
        """
        noreturn_statement -> 'noreturn' ';'
        Emits an LLVM unreachable instruction - the program terminates here.
        """
        tok = self.current_token
        self.consume(TokenType.NORET)
        self.consume(TokenType.SEMICOLON)
        return NoreturnStatement().set_location(tok.line, tok.column)

    def expression_statement(self) -> Union[ExpressionStatement, List[Statement]]:
        """
        expression_statement -> expression ';'
                              | expression member_assign_block   (when expr is lvalue and '{' follows)
                              | expression array_assign_block    (when expr is array lvalue and '{' with '[' items follows)
        """
        tok = self.current_token
        expr = self.expression()

        # Member-assign block: `base { .field = val; ... };`
        # Array-assign block:  `base { [idx] = val; ... };`
        # Triggered when an lvalue expression is immediately followed by '{'.
        if self.expect(TokenType.LEFT_BRACE) and isinstance(expr, (Identifier, ArrayAccess, MemberAccess)):
            # Peek past '{' to decide which block variant this is.
            # peek(1) is the token immediately after the current '{'.
            next_tok = self.peek(1)
            if next_tok is not None and next_tok.type == TokenType.LEFT_BRACKET:
                stmts = self._array_assign_block(expr, tok)
            else:
                stmts = self._member_assign_block(expr, tok)
            self.consume(TokenType.SEMICOLON)
            self._last_call_expr = None
            if self._source_lines and 1 <= tok.line <= len(self._source_lines):
                self._last_noncall_src = self._source_lines[tok.line - 1].rstrip('\r\n')
            else:
                self._last_noncall_src = ''
            # Returned as a flat list (same convention used throughout this parser,
            # e.g. multiple declarations) so the caller's `isinstance(stmt, list)`
            # handling splices each desugared assignment in as its own statement,
            # matching the shape codegen already handles for `base.field = val;`.
            return stmts

        self.consume(TokenType.SEMICOLON)
        # Track ditto-in-args context across statements.
        if isinstance(expr, FunctionCall):
            self._last_call_expr = expr
            self._last_noncall_src = ''
        else:
            self._last_call_expr = None
            # Capture the raw source text of this invalidating statement so the
            # ditto error can show it as a preceding context line.
            if self._source_lines and 1 <= tok.line <= len(self._source_lines):
                self._last_noncall_src = self._source_lines[tok.line - 1].rstrip('\r\n')
            else:
                self._last_noncall_src = ''
        return ExpressionStatement(expr).set_location(tok.line, tok.column)
    
    def _member_assign_block(self, base: Expression, tok) -> List[Statement]:
        """
        member_assign_block -> '{' member_assign_item* '}'

        member_assign_item ->
            '.' IDENTIFIER '=' expression ';'
          | '.' IDENTIFIER '[' expression ']' '=' expression ';'
          | '.' IDENTIFIER '{' member_assign_item* '}'  ';'

        Desugars to a flat list of ExpressionStatement(Assignment) nodes -
        the exact same shape as writing `base.field = val;` by hand - rather
        than a single Block wrapped in one ExpressionStatement. Nested
        `.field { ... }` blocks are flattened into this same list rather than
        nested, since a Block is a compound statement in its own right, not
        an expression a single ExpressionStatement can wrap and evaluate.

        Declarations and non-member statements inside the block are illegal.
        """
        self.consume(TokenType.LEFT_BRACE)
        statements: List[Statement] = []

        while not self.expect(TokenType.RIGHT_BRACE):
            # Every item must start with '.'
            if not self.expect(TokenType.DOT):
                self.error(
                    "declarations and non-member statements are illegal inside "
                    "a member-assign block; expected '.' or '}'",
                    TokenType.DOT
                )

            item_tok = self.current_token
            self.consume(TokenType.DOT)
            field_name = self.consume(TokenType.IDENTIFIER).value
            member = MemberAccess(base, field_name).set_location(item_tok.line, item_tok.column)

            if self.expect(TokenType.LEFT_BRACE):
                # Nested block: .field { ... }; - flatten into the same list.
                # Peek past '{' to decide: '[' items -> array-assign, '.' items -> member-assign.
                _inner_next = self.peek(1)
                if _inner_next is not None and _inner_next.type == TokenType.LEFT_BRACKET:
                    nested_stmts = self._array_assign_block(member, item_tok)
                else:
                    nested_stmts = self._member_assign_block(member, item_tok)
                self.consume(TokenType.SEMICOLON)
                statements.extend(nested_stmts)

            elif self.expect(TokenType.LEFT_BRACKET):
                # Array element: .field[idx] = expr;
                #             or .field[idx] { nested block };
                self.consume(TokenType.LEFT_BRACKET)
                idx_expr = self.expression()
                self.consume(TokenType.RIGHT_BRACKET)
                lvalue = ArrayAccess(member, idx_expr).set_location(item_tok.line, item_tok.column)

                if self.expect(TokenType.LEFT_BRACE):
                    # Nested block on subscripted member: .field[idx] { .x = ...; }; 
                    nested_stmts = self._member_assign_block(lvalue, item_tok)
                    self.consume(TokenType.SEMICOLON)
                    statements.extend(nested_stmts)
                else:
                    self.consume(TokenType.ASSIGN)
                    rvalue = self.expression()
                    self.consume(TokenType.SEMICOLON)
                    assignment = Assignment(lvalue, rvalue).set_location(item_tok.line, item_tok.column)
                    statements.append(ExpressionStatement(assignment).set_location(item_tok.line, item_tok.column))

            else:
                # Simple: .field = expr;
                self.consume(TokenType.ASSIGN)
                rvalue = self.expression()
                self.consume(TokenType.SEMICOLON)
                assignment = Assignment(member, rvalue).set_location(item_tok.line, item_tok.column)
                statements.append(ExpressionStatement(assignment).set_location(item_tok.line, item_tok.column))

        self.consume(TokenType.RIGHT_BRACE)
        return statements

    def _array_assign_block(self, base: Expression, tok) -> List[Statement]:
        """
        array_assign_block -> '{' array_assign_item* '}'

        array_assign_item -> '[' expression ']' '=' expression ';'

        Desugars to a flat list of ExpressionStatement(Assignment) nodes,
        identical in shape to writing `base[idx] = val;` by hand.

        Only index-assignment items are legal inside this block; member
        (dot) items and declarations are not permitted.
        """
        self.consume(TokenType.LEFT_BRACE)
        statements: List[Statement] = []

        while not self.expect(TokenType.RIGHT_BRACE):
            if not self.expect(TokenType.LEFT_BRACKET):
                self.error(
                    "only index-assignment items '[idx] = val;' are legal inside "
                    "an array-assign block; expected '[' or '}'",
                    TokenType.LEFT_BRACKET
                )

            item_tok = self.current_token
            self.consume(TokenType.LEFT_BRACKET)
            idx_expr = self.expression()
            self.consume(TokenType.RIGHT_BRACKET)
            lvalue = ArrayAccess(base, idx_expr).set_location(item_tok.line, item_tok.column)
            self.consume(TokenType.ASSIGN)
            rvalue = self.expression()
            self.consume(TokenType.SEMICOLON)
            assignment = Assignment(lvalue, rvalue).set_location(item_tok.line, item_tok.column)
            statements.append(ExpressionStatement(assignment).set_location(item_tok.line, item_tok.column))

        self.consume(TokenType.RIGHT_BRACE)
        return statements

    def expression(self) -> Expression:
        """
        expression -> assignment_expression
        """
        return self.assignment_expression()
    
    def assignment_expression(self) -> Expression:
        """
        assignment_expression -> logical_or_expression (('=' | '+=' | '-=' | '*=' | '/=' | '%=') assignment_expression)?
        
        Now handles struct field assignment:
            struct_instance.field = value
        """
        tok = self.current_token
        expr = self.ternary_expression()
        
        if self.expect(TokenType.ASSIGN):
            self.advance()
            if self.expect(TokenType.DITTO):
                import copy
                self.advance()  # consume DITTO
                prev = self._last_stmt
                if prev is None:
                    self.error("Ditto #\" in assignment: no preceding statement to repeat")
                if isinstance(prev, ExpressionStatement):
                    inner = prev.expression
                else:
                    inner = prev
                if not isinstance(inner, Assignment):
                    self.error("Ditto #\" in assignment: preceding statement is not an assignment")
                value = copy.deepcopy(inner.value)
            else:
                value = self.assignment_expression()

            # Check if this is struct field assignment
            if isinstance(expr, MemberAccess):
                # This could be struct field assignment or object member assignment
                # The codegen will determine based on type
                # For now, use Assignment and let codegen handle it
                return Assignment(expr, value).set_location(tok.line, tok.column)
            else:
                return Assignment(expr, value).set_location(tok.line, tok.column)
        elif self.expect(TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN, TokenType.MULTIPLY_ASSIGN, 
                         TokenType.DIVIDE_ASSIGN, TokenType.MODULO_ASSIGN, TokenType.EXPONENT_ASSIGN,
                         TokenType.XOR_ASSIGN, TokenType.BITXOR_ASSIGN, TokenType.BITXNOR_ASSIGN, TokenType.BITSHIFT_LEFT_ASSIGN, TokenType.BITSHIFT_RIGHT_ASSIGN,
                         TokenType.BITAND_ASSIGN, TokenType.BITOR_ASSIGN, TokenType.BITNAND_ASSIGN, TokenType.BITNOR_ASSIGN,
                         TokenType.OR_ASSIGN, TokenType.AND_ASSIGN):
            # Handle compound assignments
            op_token = self.current_token.type
            self.advance()
            value = self.assignment_expression()
            return CompoundAssignment(expr, op_token, value).set_location(tok.line, tok.column)
        elif self.expect(TokenType.ADDRESS_ASSIGN):
            # `x @= expr;` is sugar for `x = @expr;`
            addr_tok = self.current_token
            self.advance()
            rhs = self.assignment_expression()
            value = AddressOf(rhs).set_location(addr_tok.line, addr_tok.column)
            return Assignment(expr, value).set_location(tok.line, tok.column)
        elif self.expect(TokenType.TERNARY_ASSIGN):
            # Handle ternary assignment: x ?= value  (assign value to x only if x == 0)
            self.advance()
            value = self.assignment_expression()
            return TernaryAssign(expr, value).set_location(tok.line, tok.column)

        return expr

    def ternary_expression(self) -> Expression:
        """
        ternary_expression -> logical_or_expression ('?' expression ':' ternary_expression)?
        """
        tok = self.current_token
        expr = self.null_coalesce_expression()
        
        if self.expect(TokenType.QUESTION):
            self.advance()
            true_expr = self.expression()  # The value if true
            self.consume(TokenType.COLON, "Expected ':' in ternary expression")
            false_expr = self.ternary_expression()  # Right associative
            return TernaryOp(expr, true_expr, false_expr).set_location(tok.line, tok.column)
        
        return expr

    def null_coalesce_expression(self) -> Expression:
        """null_coalesce_expression -> logical_or_expression ('??' null_coalesce_expression)?"""
        tok = self.current_token
        expr = self.logical_or_expression()
        
        if self.expect(TokenType.NULL_COALESCE):
            self.advance()
            #print("GOT NULL COALESCE")
            right = self.null_coalesce_expression()  # Right associative
            return NullCoalesce(expr, right).set_location(tok.line, tok.column)
        
        return expr
    
    def logical_or_expression(self) -> Expression:
        """
        logical_or_expression -> logical_and_expression ('or' logical_and_expression)*
        """
        expr = self.logical_and_expression()
        
        while self.expect(TokenType.LOGICAL_OR, TokenType.OR):
            op_tok = self.current_token
            operator = Operator.OR
            self.advance()
            right = self.logical_and_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        return expr
    
    def logical_and_expression(self) -> Expression:
        """
        logical_and_expression -> logical_xor_expression ('and' logical_xor_expression)*
        """
        expr = self.logical_xor_expression()
        
        while self.expect(TokenType.LOGICAL_AND, TokenType.AND):
            op_tok = self.current_token
            operator = Operator.AND
            self.advance()
            right = self.logical_xor_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        return expr

    def logical_xor_expression(self) -> Expression:
        """
        logical_xor_expression -> bitwise_or_expression ('xor' bitwise_or_expression)*
        """
        expr = self.bitwise_or_expression()

        while self.expect(TokenType.XOR_OP, TokenType.XOR):
            op_tok = self.current_token
            operator = Operator.XOR
            self.advance()
            right = self.bitwise_or_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)

        return expr
    
    def equality_expression(self) -> Expression:
        """
        equality_expression -> chain_expression (('==' | '!=' | 'in' | '!in' | 'not in') chain_expression)*

        'in' produces an InExpression (membership test): needle in haystack.
        '!in' and 'not in' produce a negated InExpression: needle not in haystack.
        Both negated forms are two-token sequences (NOT + IN) since ! and not share
        the same NOT token type.
        """
        expr = self.chain_expression()

        while True:
            # Check for '!in' or 'not in' -- both lex as NOT followed by IN
            if self.expect(TokenType.NOT) and self.peek() and self.peek().type == TokenType.IN:
                op_tok = self.current_token
                self.advance()  # consume NOT
                self.advance()  # consume IN
                haystack = self.chain_expression()
                expr = InExpression(needle=expr, haystack=haystack, negated=True).set_location(op_tok.line, op_tok.column)
                continue

            if not self.expect(TokenType.IS, TokenType.EQUAL, TokenType.NOT_EQUAL, TokenType.IN, TokenType.HAS):
                break

            op_tok = self.current_token
            if self.current_token.type == TokenType.IN:
                self.advance()
                haystack = self.chain_expression()
                expr = InExpression(needle=expr, haystack=haystack, negated=False).set_location(op_tok.line, op_tok.column)
            elif self.current_token.type == TokenType.HAS:
                self.advance()
                # Right-hand side of 'has' must be a plain identifier (trait name)
                if self.current_token.type != TokenType.IDENTIFIER:
                    raise SyntaxError(
                        f"Expected trait name after 'has' [{op_tok.line}:{op_tok.column}]")
                trait_name = self.current_token.value
                self.advance()
                expr = HasExpression(subject=expr, trait_name=trait_name).set_location(op_tok.line, op_tok.column)
            else:
                if self.current_token.type == TokenType.EQUAL:
                    operator = Operator.EQUAL
                elif self.current_token.type == TokenType.IS:
                    operator = Operator.EQUAL
                else:  # NOT_EQUAL
                    operator = Operator.NOT_EQUAL

                self.advance()
                right = self.chain_expression()
                expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
                self._try_instantiate_template_op(operator.value, expr.left, expr.right)

        return expr

    def chain_expression(self) -> Expression:
        """
        chain_expression -> relational_expression ('<-' chain_expression)?
        Right associative chain arrow
        """
        tok = self.current_token
        expr = self.relational_expression()
        
        if self.expect(TokenType.CHAIN_ARROW):
            # Peek ahead to determine what kind of chain this is
            next_pos = self.position + 1  # Look past the '<-'
            if next_pos < len(self.tokens):
                next_token = self.tokens[next_pos]
                peek_after = self.tokens[next_pos + 1] if next_pos + 1 < len(self.tokens) else None
                            
            # Chain arrow (function call chaining)
            self.advance()  # consume '<-'
            right = self.chain_expression()
            

            if isinstance(expr, FunctionCall):
                expr.arguments.insert(0, right)
                return expr
            else:
                self.error("Chain arrow requires function call on left side")
        
        return expr

    def bitwise_or_expression(self) -> Expression:
        """
        bitwise_or_expression -> bitwise_xor_expression (('`|' | '`!|') bitwise_xor_expression)*
        """
        expr = self.bitwise_xor_expression()
        
        while self.expect(TokenType.BITOR_OP, TokenType.BITNOR_OP):
            op_tok = self.current_token
            if self.current_token.type == TokenType.BITOR_OP:
                operator = Operator.BITOR
            else:  # BITNOR_OP
                operator = Operator.BITNOR
            self.advance()
            right = self.bitwise_xor_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        return expr

    def bitwise_xor_expression(self) -> Expression:
        """
        bitwise_xor_expression -> bitwise_and_expression (('`^|' | '`^|!|') bitwise_and_expression)*
        """
        expr = self.bitwise_and_expression()
        
        while self.expect(TokenType.BITXOR_OP, TokenType.BITXNOR):
            op_tok = self.current_token
            if self.current_token.type == TokenType.BITXOR_OP:
                operator = Operator.BITXOR
            else:  # BITXNOR
                operator = Operator.BITXNOR
            self.advance()
            right = self.bitwise_and_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        return expr

    def bitwise_and_expression(self) -> Expression:
        """
        bitwise_and_expression -> equality_expression ('&' equality_expression)*
        """
        expr = self.equality_expression()
        
        while self.expect(TokenType.BITAND_OP, TokenType.BITNAND_OP):
            op_tok = self.current_token
            if self.current_token.type == TokenType.BITAND_OP:
                operator = Operator.BITAND
            else:  # BITNAND_OP
                operator = Operator.BITNAND
            self.advance()
            right = self.equality_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        return expr
    
    def relational_expression(self) -> Expression:
        """
        relational_expression -> shift_expression (('<' | '<=' | '>' | '>=') shift_expression)*
        """
        expr = self.shift_expression()
        
        while self.expect(TokenType.LESS_THAN, TokenType.LESS_EQUAL, TokenType.GREATER_THAN, TokenType.GREATER_EQUAL):
            op_tok = self.current_token
            if self.current_token.type == TokenType.LESS_THAN:
                operator = Operator.LESS_THAN
            elif self.current_token.type == TokenType.LESS_EQUAL:
                operator = Operator.LESS_EQUAL
            elif self.current_token.type == TokenType.GREATER_THAN:
                operator = Operator.GREATER_THAN
            else:  # GREATER_EQUAL
                operator = Operator.GREATER_EQUAL
            
            self.advance()
            right = self.shift_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        return expr
    
    def shift_expression(self) -> Expression:
        """
        shift_expression -> additive_expression (('<<' | '>>') additive_expression)*
        """
        expr = self.additive_expression()
        
        while self.expect(TokenType.BITSHIFT_LEFT, TokenType.BITSHIFT_RIGHT):
            op_tok = self.current_token
            if self.current_token.type == TokenType.BITSHIFT_LEFT:
                operator = Operator.BITSHIFT_LEFT
            else:  # RIGHT_SHIFT
                operator = Operator.BITSHIFT_RIGHT
            
            self.advance()
            right = self.additive_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        return expr
    
    def additive_expression(self) -> Expression:
        """
        additive_expression -> range_expression
        """
        return self.range_expression()
    
    def range_expression(self) -> Expression:
        """
        range_expression -> arithmetic_expression ('..' arithmetic_expression)?
        """
        tok = self.current_token
        expr = self.arithmetic_expression()
        
        if self.expect(TokenType.RANGE):  # ..
            self.advance()
            end_expr = self.arithmetic_expression()
            return RangeExpression(expr, end_expr).set_location(tok.line, tok.column)
        
        return expr
    
    def arithmetic_expression(self) -> Expression:
        """
        arithmetic_expression -> custom_op_expression (('+' | '-') custom_op_expression)*
        """
        expr = self.custom_op_expression()
        
        while self.expect(TokenType.PLUS, TokenType.MINUS):
            op_tok = self.current_token
            if self.current_token.type == TokenType.PLUS:
                operator = Operator.ADD
            else:  # MINUS
                operator = Operator.SUB
            
            self.advance()
            right = self.custom_op_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        # If the next token can start a primary expression but we're not in an
        # operator position, there's a spurious token or a missing operator here.
        if (self.current_token is not None
                and self.current_token.type in _EXPRESSION_START_TOKENS):
            # Don't fire if the identifier is a registered custom operator --
            # custom_op_expression (our caller) will consume it as an infix op.
            _is_custom_op_ident = (
                self.current_token.type == TokenType.IDENTIFIER
                and self._match_custom_op()[0] is not None
            )
            if not _is_custom_op_ident:
                self.error(
                    f"Unexpected '{self.current_token.value}' in expression"
                    f" - missing operator before this token?"
                )
        
        return expr
    
    def multiplicative_expression(self) -> Expression:
        """
        multiplicative_expression -> cast_expression (('*' | '/' | '%' | '^') cast_expression)*
        """
        expr = self.cast_expression()
        
        while self.expect(TokenType.MULTIPLY, TokenType.DIVIDE, TokenType.MODULO, TokenType.EXPONENT):
            # Do not consume this token if it is the start of a registered ternary
            # right-hand symbol (e.g. the '%' in '%$'). The ternary match runs in
            # custom_op_expression above us; consuming the token here would eat it
            # before the right-symbol check ever runs.
            if self._custom_ternary_ops:
                right_syms = {rsym: rsym for (_, rsym) in self._custom_ternary_ops}
                _m, _ = self._match_custom_unary_op(right_syms)
                if _m is not None:
                    break
            op_tok = self.current_token
            if self.current_token.type == TokenType.MULTIPLY:
                operator = Operator.MUL
            elif self.current_token.type == TokenType.DIVIDE:
                operator = Operator.DIV
            elif self.current_token.type == TokenType.MODULO:
                operator = Operator.MOD
            else:
                operator = Operator.POWER

            
            self.advance()
            right = self.cast_expression()
            expr = BinaryOp(expr, operator, right).set_location(op_tok.line, op_tok.column)
            self._try_instantiate_template_op(operator.value, expr.left, expr.right)
        
        if (self.current_token is not None
                and self.current_token.type in _EXPRESSION_START_TOKENS):
            # Don't fire if the identifier is a registered custom operator --
            # custom_op_expression (our caller) will consume it as an infix op.
            _is_custom_op_ident = (
                self.current_token.type == TokenType.IDENTIFIER
                and self._match_custom_op()[0] is not None
            )
            if not _is_custom_op_ident:
                self.error(
                    f"Unexpected '{self.current_token.value}' in expression"
                    f" - missing operator before this token?"
                )
        return expr
    
    def cast_expression(self) -> Expression:
        """
        cast_expression -> ('(' type_spec ')')? unary_expression
        
        Handles:
        - (Type)expr -> CastExpression (for ALL types - struct or primitive)
        - expr (no cast)
        """
        if self.expect(TokenType.LEFT_PAREN):
            # Look ahead to see if this is a cast
            saved_pos = self.position
            try:
                tok = self.current_token
                self.advance()  # consume '('
                target_type = self.type_spec()
                if self.expect(TokenType.RIGHT_PAREN):
                    self.advance()  # consume ')'
                    expr = self.cast_expression()
                    
                    # ALWAYS use CastExpression - let codegen figure out if it's a struct
                    return CastExpression(target_type, expr).set_location(tok.line, tok.column)
                else:
                    # Not a cast, restore position
                    self.position = saved_pos
                    self.current_token = self.tokens[self.position]
            except:
                # Not a cast, restore position
                self.position = saved_pos
                self.current_token = self.tokens[self.position]
        
        return self.unary_expression()
    
    def unary_expression(self) -> Expression:
        """
        unary_expression -> ('is' 'not' | '-' | '+' | '*' | '@' | '++' | '--' | '`!' | '`^|!' | '`^|!&' | '`^|!|') unary_expression
                         | postfix_expression
        """
        if self.expect(TokenType.IS):
            tok = self.current_token
            operator = Operator.EQUAL
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.NOT):
            tok = self.current_token
            operator = Operator.NOT
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.BITNOT_OP):
            tok = self.current_token
            operator = Operator.BITNOT
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.BITXNOT):
            tok = self.current_token
            operator = Operator.BITXNOT
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.BITXNAND):
            tok = self.current_token
            operator = Operator.BITXNAND
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.BITXNOR):
            tok = self.current_token
            operator = Operator.BITXNOR
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.MINUS):
            tok = self.current_token
            operator = Operator.SUB
            self.advance()
            operand = self.cast_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.PLUS):
            tok = self.current_token
            operator = Operator.ADD
            self.advance()
            operand = self.cast_expression()
            return UnaryOp(operator, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.MULTIPLY):
            # Pointer dereference operator
            tok = self.current_token
            self.advance()
            operand = self.cast_expression()
            return PointerDeref(operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.ADDRESS_OF):
            # Address-of operator
            tok = self.current_token
            self.advance()
            operand = self.unary_expression()
            return AddressOf(operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.ADDRESS_CAST):
            # Address cast operator (@) - converts integer literal to pointer
            # Uses CastExpression with void* as target type
            tok = self.current_token
            self.advance()
            operand = self.unary_expression()
            # Create a void pointer TypeSystem (i8*)
            void_ptr_type = TypeSystem(
                base_type=DataType.VOID,
                is_pointer=True,
                pointer_depth=1
            )
            return CastExpression(void_ptr_type, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.INCREMENT):
            # Prefix increment
            tok = self.current_token
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(Operator.INCREMENT, operand).set_location(tok.line, tok.column)
        elif self.expect(TokenType.DECREMENT):
            # Prefix decrement
            tok = self.current_token
            self.advance()
            operand = self.unary_expression()
            return UnaryOp(Operator.DECREMENT, operand).set_location(tok.line, tok.column)
        else:
            # Check for a custom prefix unary operator before falling through
            if self._custom_prefix_ops:
                matched_sym, matched_len = self._match_custom_unary_op(self._custom_prefix_ops)
                if matched_sym is not None:
                    tok = self.current_token
                    for _ in range(matched_len):
                        self.advance()
                    operand = self.unary_expression()
                    func_name = self._custom_prefix_ops[matched_sym]
                    return FunctionCall(func_name, [operand]).set_location(tok.line, tok.column)
            if self._custom_circumfix_ops:
                left_syms = {lsym: lsym for lsym, _ in self._custom_circumfix_ops}
                matched_left, left_len = self._match_custom_unary_op(left_syms)
                if matched_left is not None:
                    tok = self.current_token
                    for _ in range(left_len):
                        self.advance()
                    operand = self.unary_expression()
                    right_syms = {rsym: rsym for (lsym, rsym) in self._custom_circumfix_ops if lsym == matched_left}
                    matched_right, right_len = self._match_custom_unary_op(right_syms)
                    if matched_right is None:
                        self.error(f"Expected closing operator of circumfix '{matched_left}' ... '{list(right_syms)[0]}'")
                    for _ in range(right_len):
                        self.advance()
                    func_name = self._custom_circumfix_ops[(matched_left, matched_right)]
                    return FunctionCall(func_name, [operand]).set_location(tok.line, tok.column)
            return self.postfix_expression()
    
    # ------------------------------------------------------------------
    # Shared template-inference helpers (Step 1 of template refactor)
    # ------------------------------------------------------------------

    @staticmethod
    def _ts_repr_simple(ts) -> str:
        """Produce a readable source-like string for a TypeSystem (for constraint error messages)."""
        name = ts.custom_typename if ts.custom_typename else (
            ts.base_type.value if hasattr(ts.base_type, 'value') else str(ts.base_type))
        if ts.is_pointer:
            name += '*' * ts.pointer_depth
        if ts.is_array:
            name += '[]'
        return name

    def _register_template_function(self, name: str, template_params: list,
                                     node, constraints: dict, relations: list,
                                     defaults: dict, no_default: set) -> None:
        """Register a template function (or type-function) in the template registry.

        Centralises the ``self._templates.register(...)`` call so that
        ``function_def``, ``type_function_definition``, and ``operator_def``
        all go through one place, making future changes (e.g. adding a new
        keyword argument to ``TemplateRegistry.register``) a one-line edit.
        """
        self._templates.register(
            name, 'function', template_params, node,
            constraints=constraints or {},
            relational=relations or [],
            defaults=defaults or {},
            no_default=no_default or set(),
        )
        self._last_template_registered = name

    def _parse_template_param_list(self, allow_codify: bool = False):
        """Parse a template parameter list ``< T, U: int|float, ... >`` and return
        ``(template_params, constraints, relations, defaults, no_default)``.

        Must be called when ``self.current_token`` is already the ``<`` token
        (caller has already confirmed via lookahead that this is a template list,
        not a comparison operator).  Consumes the closing ``>``.

        Parameters
        ----------
        allow_codify : bool
            When True (type-function context), relation list identifiers and entry
            names inside constraint-sets may be prefixed with the CODIFY (``~$``)
            operator.  When False (regular function context), only bare IDENTIFIERs
            are accepted there.
        """
        self.advance()  # consume '<'

        template_params: list = []
        constraints: dict = {}        # param_name -> [(TypeSystem, source_text)]
        relations: list = []          # [(lhs_names, op, rhs_names)]
        defaults: dict = {}           # param_name -> TypeSystem
        no_default: set = set()       # param_names marked <!+

        def _consume_id_or_codify():
            """Consume and return IDENTIFIER or ~$ CODIFY token value."""
            if allow_codify and self.expect(TokenType.CODIFY):
                return self._consume_codify()
            return self.consume(TokenType.IDENTIFIER).value

        def _parse_id_list():
            """Parse one side of a relation: (CODIFY? IDENTIFIER) ('&' (CODIFY? IDENTIFIER))*"""
            names = [_consume_id_or_codify()]
            while self.expect(TokenType.LOGICAL_AND):
                self.advance()
                names.append(_consume_id_or_codify())
            return names

        def _parse_constraint_set():
            """Parse ':{ entry, ... }' and append relations into the outer ``relations`` list."""
            self.consume(TokenType.COLON)
            self.consume(TokenType.LEFT_BRACE)

            def _parse_one_cs_entry():
                _entry_tok = self.current_token
                # In allow_codify mode the entry name itself can be a ~$ token
                if allow_codify and self.expect(TokenType.CODIFY):
                    _entry_name = self._consume_codify()
                    _is_codify = True
                else:
                    _entry_name = self.consume(TokenType.IDENTIFIER).value
                    _is_codify = False

                if not _is_codify and self.expect(TokenType.LEFT_PAREN):
                    # Named constra with explicit args: MyCS(T, U)
                    if _entry_name not in self._constras:
                        self.current_token = _entry_tok
                        self.error(f"Unknown named constraint set '{_entry_name}'")
                    cs_params, cs_relations = self._constras[_entry_name]
                    self.advance()  # consume '('
                    call_args = []
                    if not self.expect(TokenType.RIGHT_PAREN):
                        call_args.append(self.consume(TokenType.IDENTIFIER).value)
                        while self.expect(TokenType.COMMA):
                            self.advance()
                            call_args.append(self.consume(TokenType.IDENTIFIER).value)
                    self.consume(TokenType.RIGHT_PAREN)
                    if len(call_args) != len(cs_params):
                        self.current_token = _entry_tok
                        self.error(
                            f"Named constraint set '{_entry_name}' expects "
                            f"{len(cs_params)} argument(s), got {len(call_args)}"
                        )
                    for arg in call_args:
                        if arg not in template_params:
                            self.error(
                                f"'{arg}' is not a template parameter; "
                                f"valid parameters are: {', '.join(template_params)}"
                            )
                    mapping = dict(zip(cs_params, call_args))
                    for lhs_f, compat_f, rhs_f in cs_relations:
                        relations.append(
                            ([mapping.get(n, n) for n in lhs_f], compat_f,
                             [mapping.get(n, n) for n in rhs_f])
                        )
                elif not _is_codify and _entry_name in self._constras and not (
                        self.expect(TokenType.LOGICAL_AND) or
                        self._is_relconstraint_op()):
                    # Bare constra name - map template params in order of appearance
                    cs_params, cs_relations = self._constras[_entry_name]
                    ordered_tparams = list(template_params)
                    if len(cs_params) != len(ordered_tparams):
                        self.current_token = _entry_tok
                        self.error(
                            f"Named constraint set '{_entry_name}' has {len(cs_params)} "
                            f"parameter(s) but the template has {len(ordered_tparams)} "
                            f"parameter(s); use explicit arguments: '{_entry_name}(...)'"
                        )
                    mapping = dict(zip(cs_params, ordered_tparams))
                    for lhs_f, compat_f, rhs_f in cs_relations:
                        relations.append(
                            ([mapping.get(n, n) for n in lhs_f], compat_f,
                             [mapping.get(n, n) for n in rhs_f])
                        )
                else:
                    # Raw relation: lhs already started with _entry_name
                    lhs = [_entry_name]
                    while self.expect(TokenType.LOGICAL_AND):
                        self.advance()
                        lhs.append(_consume_id_or_codify())
                    op = self._consume_relconstraint_op()
                    rhs = _parse_id_list()
                    relations.append((lhs, op, rhs))

            _parse_one_cs_entry()
            while self.expect(TokenType.COMMA):
                self.advance()
                _parse_one_cs_entry()
            self.consume(TokenType.RIGHT_BRACE)

        def _parse_param_entry(param_name):
            """Parse an optional ``: type1 | +type2 | ...`` constraint clause for *param_name*."""
            if self.expect(TokenType.COLON):
                template_params.append(param_name)
                self.advance()
                _allowed = []
                _default_ts = None
                _saw_default = False
                _default_tok = None
                # parse first alternative
                _is_default = self.expect(TokenType.PLUS)
                if _is_default:
                    _default_tok = self.current_token
                    self.advance()
                    _saw_default = True
                _src = '""' if self.expect(TokenType.STRING_LITERAL) else None
                _ts = self.type_spec()
                _allowed.append((_ts, _src or self._ts_repr_simple(_ts)))
                if _is_default:
                    _default_ts = _ts
                while self.expect(TokenType.LOGICAL_OR):
                    self.advance()
                    _is_default = self.expect(TokenType.PLUS)
                    if _is_default:
                        if _default_tok is None:
                            _default_tok = self.current_token
                        self.advance()
                        _saw_default = True
                    _src = '""' if self.expect(TokenType.STRING_LITERAL) else None
                    _ts = self.type_spec()
                    _allowed.append((_ts, _src or self._ts_repr_simple(_ts)))
                    if _is_default:
                        _default_ts = _ts
                constraints[param_name] = _allowed
                if _saw_default:
                    if param_name in no_default:
                        _saved_err_tok = self.current_token
                        if _default_tok is not None:
                            self.current_token = _default_tok
                        self.error(
                            f"Template parameter '{param_name}' is marked '!+' (no default) "
                            f"but a default type was supplied with '+'"
                        )
                        self.current_token = _saved_err_tok
                    defaults[param_name] = _default_ts
            else:
                template_params.append(param_name)

        # Parse first entry: ':{...}' constraint set, or identifier param entry
        if self.expect(TokenType.COLON):
            _parse_constraint_set()
        else:
            _no_default_first = False
            if self.expect(TokenType.NOT):
                self.advance()
                self.consume(TokenType.PLUS)
                _no_default_first = True
            _first_id = _consume_id_or_codify()
            if _no_default_first:
                no_default.add(_first_id)
            if self.expect(TokenType.LOGICAL_AND) or self._is_relconstraint_op():
                self.error(
                    f"Relational template constraints must be wrapped in a constraint set "
                    f"as :{{T ~= U}}. Did you mean :{{{_first_id} ~= ...}}, or did you "
                    f"intend a type constraint {_first_id}: ?"
                )
            _parse_param_entry(_first_id)

        while self.expect(TokenType.COMMA):
            self.advance()
            if self.expect(TokenType.COLON):
                _parse_constraint_set()
            else:
                _no_default_next = False
                if self.expect(TokenType.NOT):
                    self.advance()
                    self.consume(TokenType.PLUS)
                    _no_default_next = True
                _next_id = _consume_id_or_codify()
                if _no_default_next:
                    no_default.add(_next_id)
                if self.expect(TokenType.LOGICAL_AND) or self._is_relconstraint_op():
                    self.error(
                        f"Relational template constraints must be wrapped in a constraint "
                        f"set: :{{T ~= U}}. Did you mean :{{{_next_id} ~= ...}}, or did "
                        f"you intend a type constraint {_next_id}: ?"
                    )
                _parse_param_entry(_next_id)

        self.consume(TokenType.GREATER_THAN)
        return template_params, constraints, relations, defaults, no_default

    _LITERAL_DT_MAP = None  # populated on first use

    @classmethod
    def _literal_dt_map(cls):
        if cls._LITERAL_DT_MAP is None:
            cls._LITERAL_DT_MAP = {
                DataType.SINT:   TypeSystem(base_type=DataType.SINT,   is_signed=True),
                DataType.UINT:   TypeSystem(base_type=DataType.UINT,   is_signed=False),
                DataType.SLONG:  TypeSystem(base_type=DataType.SLONG,  is_signed=True),
                DataType.ULONG:  TypeSystem(base_type=DataType.ULONG,  is_signed=False),
                DataType.FLOAT:  TypeSystem(base_type=DataType.FLOAT),
                DataType.DOUBLE: TypeSystem(base_type=DataType.DOUBLE),
                DataType.CHAR:   TypeSystem(base_type=DataType.CHAR,   is_signed=True),
                DataType.BOOL:   TypeSystem(base_type=DataType.BOOL),
                DataType.BYTE:   TypeSystem(base_type=DataType.BYTE),
            }
        return cls._LITERAL_DT_MAP

    def _infer_type_from_arg(self, arg) -> 'TypeSystem | None':
        """Return the TypeSystem implied by a single call-site argument expression.

        Handles:
          * Identifier  -> symbol-table lookup
          * Literal     -> DataType -> TypeSystem map
          * StringLiteral -> byte* (pointer to i8)

        AddressOf(@x) unwrapping is done by the caller before passing `arg`
        so this method only sees the inner expression.

        Returns None when the type cannot be determined.
        """
        if isinstance(arg, Identifier):
            return self.symbol_table.get_type_spec(arg.name)
        if isinstance(arg, Literal):
            return self._literal_dt_map().get(arg.type)
        if isinstance(arg, StringLiteral):
            return TypeSystem(base_type=DataType.BYTE, is_signed=True,
                              bit_width=8, is_pointer=True, pointer_depth=1)
        return None

    def _infer_template_params(self, entry: 'TemplateEntry', args: list,
                               skip_first_param: bool = False) -> 'dict | None':
        """Infer template-param -> TypeSystem bindings from call-site arguments.

        Matches each declared function parameter's type-spec against the
        corresponding call-site argument (via _infer_type_from_arg), handling:
          * bare template params  (e.g. declared type is T)
          * deferred struct params (e.g. declared type is Tensor<T>)

        `skip_first_param` – set True for type-function calls where the first
        declared parameter is the implicit `this` receiver (already consumed).

        Returns a dict {param_name: TypeSystem} on success, or None when not
        all params could be inferred (caller should decide what to do).
        """
        template_param_names = entry.params
        template_func = entry.node
        inferred: dict = {}

        decl_params = template_func.parameters
        if skip_first_param:
            decl_params = decl_params[1:]

        for i, decl_param in enumerate(decl_params):
            if i >= len(args):
                break
            param_ts = decl_param.type_spec
            if param_ts is None:
                continue

            # Dict param: dict{T:U} -- infer T and U from the argument's dict type spec
            if param_ts.base_type == DataType.DICT:
                arg = args[i]
                arg_entry = self.symbol_table.lookup_variable(arg.name) if isinstance(arg, Identifier) else None
                arg_ts = arg_entry.type_spec if arg_entry else None
                if arg_ts is None and isinstance(arg, Identifier):
                    arg_ts = self.symbol_table.get_type_spec(arg.name)
                if arg_ts is not None and getattr(arg_ts, 'base_type', None) == DataType.DICT:
                    key_param = getattr(param_ts.dict_key_type, 'custom_typename', None) or (
                        param_ts.dict_key_type.base_type if isinstance(getattr(param_ts.dict_key_type, 'base_type', None), str) else None)
                    val_param = getattr(param_ts.dict_value_type, 'custom_typename', None) or (
                        param_ts.dict_value_type.base_type if isinstance(getattr(param_ts.dict_value_type, 'base_type', None), str) else None)
                    if key_param and key_param in template_param_names and key_param not in inferred:
                        inferred[key_param] = arg_ts.dict_key_type
                    if val_param and val_param in template_param_names and val_param not in inferred:
                        inferred[val_param] = arg_ts.dict_value_type
                    # Store the full arg dict TypeSystem keyed by param index for capacity patching
                    inferred[f'__dict_arg_ts_{i}__'] = arg_ts
                continue

            param_tname = (
                param_ts.custom_typename if param_ts.custom_typename
                else (param_ts.base_type if isinstance(param_ts.base_type, str) else None)
            )
            struct_param_map = {}  # template_param_name -> inner arg index
            if param_tname and '<' in param_tname and '>' in param_tname:
                bracket = param_tname.index('<')
                inner_args = [a.strip() for a in param_tname[bracket + 1:-1].split(',')]
                for idx2, inner in enumerate(inner_args):
                    if inner in template_param_names:
                        struct_param_map[inner] = idx2
                param_tname = None  # declared type is a struct, not a bare param name

            if param_tname is not None and param_tname not in template_param_names:
                continue  # concrete declared type – no inference needed

            arg = args[i]
            # Unwrap address-of (@x) to allow symbol-table lookup of the inner identifier
            if (isinstance(arg, AddressOf)
                    and isinstance(getattr(arg, 'expression', None), Identifier)):
                arg = arg.expression

            if struct_param_map:
                # The argument must be a struct/object instance; recover the concrete
                # type args from the mangled name (e.g. Tensor__float -> float).
                arg_ts = self.symbol_table.get_type_spec(arg.name) if isinstance(arg, Identifier) else None
                if arg_ts and arg_ts.custom_typename:
                    arg_ctn = arg_ts.custom_typename
                    _entries = {**self._templates.all_of_kind('struct'),
                                **self._templates.all_of_kind('object')}
                    for tmpl_name, _te in _entries.items():
                        sep = tmpl_name + '__'
                        if arg_ctn.startswith(sep) or arg_ctn == tmpl_name:
                            suffix = arg_ctn[len(sep):]
                            concrete_args = suffix.split('__') if suffix else []
                            for tparam, pos in struct_param_map.items():
                                if pos < len(concrete_args) and tparam not in inferred:
                                    carg = concrete_args[pos]
                                    resolved = self.symbol_table.get_type_spec(carg)
                                    if resolved is None:
                                        _dtbv = {dt.value: dt for dt in DataType}
                                        if carg in _dtbv:
                                            resolved = TypeSystem(base_type=_dtbv[carg],
                                                is_signed=_dtbv[carg] in (DataType.SINT, DataType.CHAR))
                                        else:
                                            resolved = TypeSystem(base_type=DataType.DATA,
                                                                  custom_typename=carg)
                                    inferred[tparam] = resolved
                            break
            elif param_tname is not None:
                inferred_ts = self._infer_type_from_arg(arg)
                if inferred_ts is not None:
                    inferred[param_tname] = inferred_ts

        return inferred

    @staticmethod
    def _ts_matches(concrete, allowed) -> bool:
        """Return True if concrete TypeSystem satisfies the allowed TypeSystem constraint."""
        # object* is the erasure type for all object pointers -- it satisfies
        # any constraint whose allowed type is a named object (DataType.DATA).
        if (concrete.base_type == DataType.OBJECT and
                allowed.base_type == DataType.DATA and
                allowed.custom_typename is not None):
            return True
        if concrete.base_type != allowed.base_type:
            return False
        if concrete.is_pointer != allowed.is_pointer:
            return False
        if concrete.pointer_depth != allowed.pointer_depth:
            return False
        if concrete.is_array != allowed.is_array:
            return False
        if concrete.custom_typename != allowed.custom_typename:
            return False
        # bit_width: 0 means unspecified/default - treat 0 as wildcard
        if allowed.bit_width and concrete.bit_width and concrete.bit_width != allowed.bit_width:
            return False
        return True

    @staticmethod
    def _types_compatible(a_ts, b_ts) -> bool:
        """Return True if two TypeSystems are compatible for relational constraint (~=) checks."""
        # Pointer vs non-pointer is always incompatible
        if a_ts.is_pointer != b_ts.is_pointer:
            return False
        # Both pointer: pointer depth must match
        if a_ts.is_pointer and a_ts.pointer_depth != b_ts.pointer_depth:
            return False
        # Width must match (0 means unresolved/default - treat as wildcard)
        aw = a_ts.bit_width or 0
        bw = b_ts.bit_width or 0
        if aw and bw and aw != bw:
            return False
        return True

    @staticmethod
    def _walk_ast(node):
        """Yield every AST node in the tree depth-first."""
        if node is None:
            return
        yield node
        for attr in vars(node).values():
            if isinstance(attr, list):
                for item in attr:
                    if hasattr(item, '__dataclass_fields__'):
                        yield from FluxParser._walk_ast(item)
            elif hasattr(attr, '__dataclass_fields__'):
                yield from FluxParser._walk_ast(attr)

    @staticmethod
    def _bw(ts) -> int:
        """Return the bit width of a TypeSystem, or 0 if unknown."""
        if ts is None:
            return 0
        if ts.bit_width:
            return ts.bit_width
        from ftypesys import get_builtin_bit_width as _gbw
        try:
            return _gbw(ts.base_type)
        except Exception:
            return 0

    @staticmethod
    def _ts_of_expr(expr, local_type_table):
        """Best-effort TypeSystem for an expression node during body-level relation checks."""
        from fast import (CastExpression as _CastExpr,
                          TypeConvertExpression as _TypeConvExpr,
                          Identifier as _Ident,
                          Literal as _Literal)
        ts = getattr(expr, '_resolved_type', None)
        if ts is not None:
            return ts
        if isinstance(expr, (_CastExpr, _TypeConvExpr)):
            return expr.target_type
        if isinstance(expr, _Ident):
            return local_type_table.get(expr.name)
        if isinstance(expr, _Literal):
            return TypeSystem(base_type=expr.type,
                              is_signed=expr.type in (DataType.SINT, DataType.SLONG,
                                                      DataType.CHAR, DataType.FLOAT,
                                                      DataType.DOUBLE))
        return None

    def _substitute_type(self, ts, mapping):
        """
        Substitute template parameter names in a TypeSystem according to mapping.
        Returns a (possibly new, shallow-copied) TypeSystem with params resolved.
        Called by _substitute_node for every TypeSystem field encountered.
        """
        import copy
        if not isinstance(ts, TypeSystem):
            return ts
        # Dict type: substitute T and U in dict_key_type and dict_value_type
        if ts.base_type == DataType.DICT:
            new_key = self._substitute_type(ts.dict_key_type, mapping) if ts.dict_key_type else ts.dict_key_type
            new_val = self._substitute_type(ts.dict_value_type, mapping) if ts.dict_value_type else ts.dict_value_type
            if new_key is not ts.dict_key_type or new_val is not ts.dict_value_type:
                result = copy.copy(ts)
                result.dict_key_type = new_key
                result.dict_value_type = new_val
                return result
            return copy.copy(ts)
        name = ts.custom_typename if ts.custom_typename else (
            ts.base_type if isinstance(ts.base_type, str) else None)
        if name and name in mapping:
            concrete = mapping[name]
            result = copy.copy(concrete)
            if ts.is_pointer:
                result.is_pointer = True
                result.pointer_depth = (result.pointer_depth or 0) + ts.pointer_depth
            if ts.is_array:
                result.is_array = True
                result.array_dimensions = ts.array_dimensions
                result.array_size = ts.array_size
            if ts.is_const:
                result.is_const = True
            if ts.is_volatile:
                result.is_volatile = True
            return result
        # Deferred template struct/object: "Name<T,U>" where T/U may now be in mapping.
        if name and '<' in name and '>' in name:
            bracket = name.index('<')
            struct_base = name[:bracket]
            raw_args = name[bracket + 1:-1].split(',')
            _sentry = self._templates.lookup(struct_base)
            if _sentry is not None and _sentry.kind == 'struct' and any(a in mapping for a in raw_args):
                concrete_type_names, concrete_type_specs = [], []
                for arg in raw_args:
                    arg = arg.strip()
                    if arg in mapping:
                        cts = mapping[arg]
                        concrete_type_names.append(self._type_system_to_mangle_str(cts))
                        concrete_type_specs.append(cts)
                    else:
                        concrete_type_names.append(arg)
                        concrete_type_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=arg))
                mangled = self._resolve_template_struct(struct_base, concrete_type_names, concrete_type_specs)
                result = copy.copy(ts)
                result.custom_typename = mangled
                result.base_type = DataType.DATA
                return result
            if _sentry is not None and _sentry.kind == 'object' and any(a in mapping for a in raw_args):
                concrete_type_names, concrete_type_specs = [], []
                for arg in raw_args:
                    arg = arg.strip()
                    if arg in mapping:
                        cts = mapping[arg]
                        concrete_type_names.append(self._type_system_to_mangle_str(cts))
                        concrete_type_specs.append(cts)
                    else:
                        concrete_type_names.append(arg)
                        concrete_type_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=arg))
                mangled = self._resolve_template_object(struct_base, concrete_type_names, concrete_type_specs)
                result = copy.copy(ts)
                result.custom_typename = mangled
                result.base_type = DataType.DATA
                return result
        return copy.copy(ts)

    def _substitute_node(self, obj, mapping):
        """
        Recursively deep-copy and substitute template params in an arbitrary AST value.
        Handles TypeSystem, list, dict, str (deferred struct refs), Identifier, FunctionCall,
        and any dataclass AST node. Called by _substitute_template.
        """
        import copy
        if obj is None:
            return None
        if isinstance(obj, TypeSystem):
            return self._substitute_type(obj, mapping)
        if isinstance(obj, list):
            return [self._substitute_node(item, mapping) for item in obj]
        if isinstance(obj, dict):
            return {k: self._substitute_node(v, mapping) for k, v in obj.items()}
        # Resolve deferred template struct refs stored as strings in
        # base_structs / post_structs: e.g. "A<T>" where T is in mapping.
        if isinstance(obj, str):
            if '<' in obj and '>' in obj and any(p in obj for p in mapping):
                bracket = obj.index('<')
                struct_base = obj[:bracket]
                raw_args = obj[bracket + 1:-1].split(',')
                _sentry = self._templates.lookup(struct_base)
                if (_sentry is not None and _sentry.kind == 'struct' and
                        any(a.strip() in mapping for a in raw_args)):
                    concrete_type_names, concrete_type_specs = [], []
                    for arg in raw_args:
                        arg = arg.strip()
                        if arg in mapping:
                            cts = mapping[arg]
                            concrete_type_names.append(self._type_system_to_mangle_str(cts))
                            concrete_type_specs.append(cts)
                        else:
                            concrete_type_names.append(arg)
                            concrete_type_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=arg))
                    return self._resolve_template_struct(struct_base, concrete_type_names, concrete_type_specs)
            return obj
        if not hasattr(obj, '__dataclass_fields__'):
            return obj
        # Identifier used as expression whose name is a template param
        # (e.g. sizeof(T) parses T as Identifier, not TypeSystem).
        if isinstance(obj, Identifier) and obj.name in mapping:
            return copy.copy(mapping[obj.name])
        # Deferred template call: FunctionCall whose name is "func<T,U>"
        # or "ObjName<T>.method" constructor/method call patterns.
        if isinstance(obj, FunctionCall) and isinstance(obj.name, str) and '<' in obj.name and '>' in obj.name:
            _gt_pos = obj.name.index('>')
            if _gt_pos + 1 < len(obj.name) and obj.name[_gt_pos + 1] == '.':
                _lt = obj.name.index('<')
                _obj_base = obj.name[:_lt]
                _raw_args = obj.name[_lt + 1:_gt_pos].split(',')
                _method = obj.name[_gt_pos + 1:]
                _oentry = self._templates.lookup(_obj_base)
                if (_oentry is not None and _oentry.kind == 'object' and
                        any(a.strip() in mapping for a in _raw_args)):
                    _concrete_names, _concrete_specs = [], []
                    for _a in _raw_args:
                        _a = _a.strip()
                        if _a in mapping:
                            _cts = mapping[_a]
                            _concrete_names.append(self._type_system_to_mangle_str(_cts))
                            _concrete_specs.append(_cts)
                        else:
                            _concrete_names.append(_a)
                            _concrete_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=_a))
                    _mangled_obj = self._resolve_template_object(_obj_base, _concrete_names, _concrete_specs)
                    _new_obj = copy.copy(obj)
                    _new_obj.name = _mangled_obj + _method
                    _new_obj.arguments = [self._substitute_node(a, mapping) for a in obj.arguments]
                    return _new_obj
            bracket = obj.name.index('<')
            fn_base = obj.name[:bracket]
            raw_args = obj.name[bracket + 1:-1].split(',')
            _fentry = self._templates.lookup(fn_base)
            if (_fentry is not None and _fentry.kind == 'function' and
                    any(a.strip() in mapping for a in raw_args)):
                concrete_type_names, concrete_type_specs = [], []
                for arg in raw_args:
                    arg = arg.strip()
                    if arg in mapping:
                        cts = mapping[arg]
                        concrete_type_names.append(self._type_system_to_mangle_str(cts))
                        concrete_type_specs.append(cts)
                    else:
                        concrete_type_names.append(arg)
                        concrete_type_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=arg))
                resolved_name = self._resolve_template_call(fn_base, concrete_type_names, concrete_type_specs)
                new_obj = copy.copy(obj)
                new_obj.name = resolved_name
                new_obj.arguments = [self._substitute_node(a, mapping) for a in obj.arguments]
                return new_obj
            if (_fentry is not None and _fentry.kind == 'object' and
                    any(a.strip() in mapping for a in raw_args)):
                concrete_type_names, concrete_type_specs = [], []
                for arg in raw_args:
                    arg = arg.strip()
                    if arg in mapping:
                        cts = mapping[arg]
                        concrete_type_names.append(self._type_system_to_mangle_str(cts))
                        concrete_type_specs.append(cts)
                    else:
                        concrete_type_names.append(arg)
                        concrete_type_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=arg))
                resolved_name = self._resolve_template_object(fn_base, concrete_type_names, concrete_type_specs)
                new_obj = copy.copy(obj)
                new_obj.name = resolved_name
                new_obj.arguments = [self._substitute_node(a, mapping) for a in obj.arguments]
                return new_obj
        # Dataclass AST node - shallow copy then recurse into fields
        new_obj = copy.copy(obj)
        for field_name in obj.__dataclass_fields__:
            old_val = getattr(obj, field_name)
            setattr(new_obj, field_name, self._substitute_node(old_val, mapping))
        return new_obj

    def _substitute_template(self, node, mapping):
        """
        Deep-copy an AST node, substituting every TypeSystem whose custom_typename
        (or base_type string) appears in `mapping` with the corresponding concrete TypeSystem.
        Also substitutes Identifier nodes whose name is a template param, for cases
        where a param name appears as an expression (e.g. sizeof-style use).
        Delegates to _substitute_node / _substitute_type for the recursive walk.
        """
        return self._substitute_node(node, mapping)

    def _type_system_to_mangle_str(self, ts):
        """Produce a short string identifying a TypeSystem for name mangling.

        For fully-resolved DATA types (e.g. a u64 alias that resolved to
        base_type=DATA, bit_width=64, is_signed=False) we incorporate the
        bit_width and signedness so that distinct numeric types produce distinct
        mangle strings (e.g. 'data_u64') instead of collapsing to the bare
        string 'data' and losing all width/signedness information.
        """
        if ts.custom_typename:
            return ts.custom_typename
        if ts.is_pointer:
            return f"ptr_{self._type_system_to_mangle_str(TypeSystem(base_type=ts.base_type, bit_width=ts.bit_width, custom_typename=ts.custom_typename))}"
        base = ts.base_type if isinstance(ts.base_type, str) else (
            ts.base_type.value if hasattr(ts.base_type, 'value') else str(ts.base_type))
        # For DATA types with a known bit_width, embed width+signedness so that
        # e.g. u64 (data/64/unsigned) and i32 (data/32/signed) get distinct names.
        if base == 'data' and ts.bit_width is not None:
            sign = 'i' if ts.is_signed else 'u'
            return f"data_{sign}{ts.bit_width}"
        return base

    def _build_template_mapping(self, template_params, type_names, type_specs):
        """
        Build the param-name → TypeSystem substitution mapping shared by all
        instantiation paths.

        Resolution order for each param:
          1. A pre-resolved TypeSystem from type_specs (avoids lossy mangle round-trip).
          2. A symbol-table alias (e.g. 'u64' → DATA/64-bit).
          3. A primitive DataType keyword ('sint', 'float', …).
          4. Fall back to a DATA custom_typename from the mangle string.
        """
        _datatype_by_value = {dt.value: dt for dt in DataType}
        mapping = {}
        specs = type_specs or []
        for i, (param, tname) in enumerate(zip(template_params, type_names)):
            if i < len(specs) and specs[i] is not None:
                mapping[param] = specs[i]
            else:
                resolved = self.symbol_table.get_type_spec(tname)
                if resolved is not None:
                    mapping[param] = resolved
                elif tname in _datatype_by_value:
                    dt = _datatype_by_value[tname]
                    mapping[param] = TypeSystem(
                        base_type=dt,
                        is_signed=dt in (DataType.SINT, DataType.CHAR))
                else:
                    mapping[param] = TypeSystem(base_type=DataType.DATA, custom_typename=tname)
        return mapping

    def _instantiate_template_node(self, kind, name, template_params, template_node,
                                   type_names, type_specs, usage_tok=None):
        """
        Shared instantiation body for 'struct' and 'object' template kinds.
        Handles: mangle, is_emitted guard, mapping build, substitute, stamp name,
        kind-specific post-steps, and append to _pending_template_instances.
        Returns the mangled name.
        """
        mangled = name + '__' + '_'.join(type_names)
        if not self._templates.is_emitted(name, mangled):
            self._templates.mark_emitted(name, mangled)
            mapping = self._build_template_mapping(template_params, type_names, type_specs)
            concrete = self._substitute_template(template_node, mapping)
            concrete.name = mangled
            concrete.template_params = []
            if getattr(template_node, '_is_comptime_only', False):
                concrete._is_comptime_only = True
            if usage_tok is not None:
                for member in getattr(concrete, 'members', []):
                    member.set_location(usage_tok.line, usage_tok.column)
            if kind == 'object':
                self._parsed_objects[mangled] = concrete
                self._object_init_params[mangled] = self._object_init_params.get(template_node.name, 0)
            self._pending_template_instances.append((kind, concrete))
        return mangled

    def _resolve_template_struct(self, struct_name, type_names, type_specs=None, usage_tok=None):
        """
        Instantiate a template struct with concrete type arguments.
        Returns the mangled concrete struct name.

        usage_tok, when provided, is the token at the start of the first
        template argument (e.g. the 'T' in 'typeof(A<T>)'). If the
        instantiation contains an unresolvable type argument, the eventual
        codegen error should point at *this* token rather than wherever the
        template's own field happens to be declared, since that's where the
        bad argument was actually written. Only applies on first
        instantiation of a given mangled name -- _templates.is_emitted
        caches instances, so a later usage of the same bad instantiation
        will not get its own location (a pre-existing limitation of the
        instantiation cache, not something this fix changes).
        """
        entry = self._templates.lookup(struct_name)
        if entry is None or entry.kind != 'struct':
            self.error(f"Unknown template struct '{struct_name}'")
        if len(type_names) != len(entry.params):
            self.error(
                f"Template struct '{struct_name}' expects {len(entry.params)} "
                f"type argument(s), got {len(type_names)}"
            )
        return self._instantiate_template_node(
            'struct', struct_name, entry.params, entry.node,
            type_names, type_specs, usage_tok)

    def _resolve_template_object(self, object_name, type_names, type_specs=None, usage_tok=None):
        """
        Instantiate a template object with concrete type arguments.
        Returns the mangled concrete object name.

        usage_tok: see _resolve_template_struct -- same purpose (the first
        template argument's token), applied to the object's members so an
        unresolvable member type error points at the bad argument instead
        of the template's own definition.
        """
        entry = self._templates.lookup(object_name)
        if entry is None or entry.kind != 'object':
            self.error(f"Unknown template object '{object_name}'")
        if len(type_names) != len(entry.params):
            self.error(
                f"Template object '{object_name}' expects {len(entry.params)} "
                f"type argument(s), got {len(type_names)}"
            )
        return self._instantiate_template_node(
            'object', object_name, entry.params, entry.node,
            type_names, type_specs, usage_tok)

    def _resolve_template_call(self, func_name, arg_type_names, arg_type_specs=None, arg_positions=None):
        """
        Given a template function name and a list of concrete type-name strings
        (one per template param, in declaration order), produce and register a
        concrete FunctionDef if not already done.  Returns the mangled call name.

        arg_type_specs, if provided, must be a parallel list of already-resolved
        TypeSystem objects (as returned by type_spec()).  Using them avoids the
        lossy round-trip through the mangle string that previously caused fully-
        resolved alias types (e.g. u64 -> DATA/64-bit) to lose their bit_width.
        """
        entry = self._templates.lookup(func_name)
        if entry is None or entry.kind not in ('function',):
            self.error(f"Unknown template function '{func_name}'")
        template_params = entry.params
        template_func = entry.node

        if len(arg_type_names) != len(template_params):
            self.error(
                f"Template function '{func_name}' expects {len(template_params)} "
                f"type argument(s), got {len(arg_type_names)}"
            )

        # Enforce template constraints if any were declared for this function.
        # Also check under qualified names (the entry may be keyed by a namespace-qualified variant).
        _constraints_map = entry.constraints
        if not _constraints_map:
            # Try stripping namespace prefix to find the bare-name entry
            for _ck, _ce in self._templates.items():
                if (func_name.endswith('__' + _ck) or func_name == _ck) and _ce.constraints:
                    _constraints_map = _ce.constraints
                    break
        if _constraints_map:
            for i, param_name in enumerate(template_params):
                if param_name not in _constraints_map:
                    continue
                allowed_specs = _constraints_map[param_name]
                # Get the concrete TypeSystem for this param
                concrete_ts = None
                if arg_type_specs is not None and i < len(arg_type_specs):
                    concrete_ts = arg_type_specs[i]
                if concrete_ts is None:
                    continue
                # allowed_specs is a list of (TypeSystem, source_text) tuples
                if not any(self._ts_matches(concrete_ts, a_ts) for a_ts, _ in allowed_specs):
                    allowed_strs = ' | '.join(a_src for _, a_src in allowed_specs)
                    # Produce a readable name for the function in the error message.
                    # __typefunc__string__f  -> i-string
                    # __typefunc__string__X  -> "".X  (generic string type func)
                    # __typefunc__TYPE__NAME -> TYPE.NAME
                    # everything else        -> func_name as-is
                    if func_name.startswith('__typefunc__'):
                        _inner = func_name[len('__typefunc__'):]
                        _recv, _, _meth = _inner.partition('__')
                        _ISTR_METHODS = {'f', 'format'}
                        if _recv == 'string' and _meth in _ISTR_METHODS:
                            _display_name = 'i-string'
                        else:
                            _display_name = f'"{_recv}".{_meth}' if _recv == 'string' else f'{_recv}.{_meth}'
                    else:
                        _display_name = func_name
                    _saved_pos_tok = self.current_token
                    if arg_positions is not None and i < len(arg_positions):
                        _aline, _acol = arg_positions[i]
                        self.current_token = type('_Tok', (), {'line': _aline, 'column': _acol})()
                    self.error(
                        f"Template parameter '{param_name}' of '{_display_name}' was instantiated "
                        f"with type '{arg_type_names[i]}', which does not satisfy the constraint "
                        f"[{allowed_strs}]"
                    )
                    self.current_token = _saved_pos_tok

        # Check relation constraints (T~U, T!~U, T&U~V, etc.)
        _pending_body_checks = []  # (op, lname, rname, lts, rts) for body-level ops
        _relations_list = entry.relational_constraints
        if not _relations_list:
            for _rk, _re in self._templates.items():
                if (func_name.endswith('__' + _rk) or func_name == _rk) and _re.relational_constraints:
                    _relations_list = _re.relational_constraints
                    break
        if _relations_list:
            # Build param_name -> concrete TypeSystem mapping for relation checks
            _param_to_ts = {}
            for i, pname in enumerate(template_params):
                if arg_type_specs is not None and i < len(arg_type_specs):
                    _param_to_ts[pname] = arg_type_specs[i]
            # Body-walk helpers for !`< !`<= !`> !`>=
            # These ops require scanning the instantiated function body for
            # cast/truncation/widening operations involving the constrained types.
            # The walk is deferred until after _substitute_template produces
            # concrete_func; the _pending_body_checks list carries the work.
            _TRUNCATION_OPS = {"!`<", "!`<="}
            _WIDENING_OPS   = {"!`>", "!`>="}
            _ADDRESS_OPS    = {"!@"}
            _body_check_ops = _TRUNCATION_OPS | _WIDENING_OPS | _ADDRESS_OPS

            for lhs_names, op, rhs_names in _relations_list:
                for lname in lhs_names:
                    for rname in rhs_names:
                        lts = _param_to_ts.get(lname)
                        rts = _param_to_ts.get(rname)
                        if lts is None or rts is None:
                            continue

                        if op == "~=":
                            if not self._types_compatible(lts, rts):
                                lmangle = self._type_system_to_mangle_str(lts)
                                rmangle = self._type_system_to_mangle_str(rts)
                                self.error(
                                    f"Relation constraint '{lname} ~= {rname}' violated: "
                                    f"'{lmangle}' and '{rmangle}' are not compatible "
                                    f"(pointer mismatch or width mismatch)"
                                )
                        elif op == "!~=":
                            if self._types_compatible(lts, rts):
                                lmangle = self._type_system_to_mangle_str(lts)
                                rmangle = self._type_system_to_mangle_str(rts)
                                self.error(
                                    f"Relation constraint '{lname} !~= {rname}' violated: "
                                    f"'{lmangle}' and '{rmangle}' must be incompatible "
                                    f"but are compatible"
                                )
                        elif op in _body_check_ops:
                            if op == "!@":
                                # !@ : walk the original template body for AddressOf nodes
                                # whose operand is an identifier declared with a constrained
                                # param type.  Done here (before substitution) so the type
                                # names are still the abstract param names (T, U, ...).
                                _addr_param_names = set()
                                _addr_param_names.add(lname)
                                _addr_param_names.add(rname)
                                # Collect variable/parameter names declared with a constrained type
                                _tparam_vars = {}
                                for _tp in template_func.parameters:
                                    if (_tp.name and _tp.type_spec and
                                            _tp.type_spec.custom_typename in _addr_param_names):
                                        _tparam_vars[_tp.name] = _tp.type_spec.custom_typename
                                from fast import VariableDeclaration as _TVarDecl
                                for _tn in self._walk_ast(template_func):
                                    if isinstance(_tn, _TVarDecl) and _tn.type_spec:
                                        if _tn.type_spec.custom_typename in _addr_param_names:
                                            _tparam_vars[_tn.name] = _tn.type_spec.custom_typename
                                # Scan for AddressOf whose operand is one of those variables
                                from fast import AddressOf as _TAddressOf, Identifier as _TIdent
                                for _tn in self._walk_ast(template_func):
                                    if not isinstance(_tn, _TAddressOf):
                                        continue
                                    _expr = _tn.expression
                                    if not isinstance(_expr, _TIdent):
                                        continue
                                    if _expr.name not in _tparam_vars:
                                        continue
                                    _line = getattr(_tn, 'source_line', '?')
                                    _col  = getattr(_tn, 'source_col',  '?')
                                    _lmangle = self._type_system_to_mangle_str(lts)
                                    _rmangle = self._type_system_to_mangle_str(rts)
                                    if lname == rname or _lmangle == _rmangle:
                                        _type_clause = _lmangle
                                    else:
                                        _type_clause = f"{_lmangle} and {_rmangle}"
                                    _saved_err_tok = self.current_token
                                    if isinstance(_line, int) and isinstance(_col, int) and _line > 0:
                                        self.current_token = type('_Tok', (), {'line': _line, 'column': _col})()
                                    self.error(
                                        f"Type relation {lname} {op} {rname} violated: "
                                        f"cannot take address of {_type_clause}",
                                    )
                                    self.current_token = _saved_err_tok
                            else:
                                _pending_body_checks.append((op, lname, rname, lts, rts))

        # Build mangled name: func__tmpl__T1__T2
        mangled = func_name + '__tmpl__' + '__'.join(arg_type_names)

        if not self._templates.is_emitted(func_name, mangled):
            self._templates.mark_emitted(func_name, mangled)

            # Build the substitution mapping: param name -> concrete TypeSystem
            mapping = self._build_template_mapping(template_params, arg_type_names, arg_type_specs)

            # Deep-copy + substitute
            concrete_func = self._substitute_template(template_func, mapping)

            # Patch dict parameter capacities: after substitution, dict params have
            # capacity 0 because the template declared dict{T:U} with no literal.
            # Fill in the actual capacity from the call-site arg type specs.
            _dict_arg_ts_map = getattr(self, '_pending_dict_arg_ts', {})
            for p_idx, param in enumerate(concrete_func.parameters):
                if (param.type_spec is not None and
                        getattr(param.type_spec, 'base_type', None) == DataType.DICT and
                        (param.type_spec.dict_capacity is None or param.type_spec.dict_capacity == 0)):
                    arg_ts = _dict_arg_ts_map.get(f'__dict_arg_ts_{p_idx}__')
                    if arg_ts is not None and arg_ts.dict_capacity:
                        param.type_spec.dict_capacity = arg_ts.dict_capacity
            # Also patch return type if it's a dict with capacity 0
            if (concrete_func.return_type is not None and
                    getattr(concrete_func.return_type, 'base_type', None) == DataType.DICT and
                    (concrete_func.return_type.dict_capacity is None or concrete_func.return_type.dict_capacity == 0)):
                for arg_ts in _dict_arg_ts_map.values():
                    if arg_ts is not None and arg_ts.dict_capacity:
                        concrete_func.return_type.dict_capacity = arg_ts.dict_capacity
                        break
            concrete_func.name = func_name  # Keep original name; normal mangling handles uniqueness
            if getattr(template_func, '_is_comptime_only', False):
                concrete_func._is_comptime_only = True
            concrete_func.no_mangle = False
            # Tag with the originating namespace so the codegen can restore context
            # when emitting the body (template instances are emitted at top level,
            # outside any namespace visit, so _current_namespace would otherwise be empty).
            # Find the most-qualified key for this function in the registry -
            # that encodes the namespace the template was defined in.
            _src_ns = ''
            for _key in self._templates.all_of_kind('function'):
                if _key.endswith('__' + func_name) and '__' in _key:
                    # e.g. "standard__tensors__tensor_make" ends with "__tensor_make"
                    _candidate_ns = _key[:-(len(func_name) + 2)]
                    if len(_candidate_ns) > len(_src_ns):
                        _src_ns = _candidate_ns
            concrete_func._source_namespace = _src_ns

            # Body-level relation checks: !`< !`<= !`> !`>=
            # Walk the substituted AST looking for CastExpression / TypeConvertExpression
            # nodes that truncate or widen one of the constrained parameter types.
            if _pending_body_checks:
                from fast import (CastExpression as _CastExpr,
                                  TypeConvertExpression as _TypeConvExpr,
                                  BinaryOp as _BinaryOp,
                                  UnaryOp as _UnaryOp,
                                  Assignment as _Assignment,
                                  CompoundAssignment as _CompoundAssignment,
                                  ReturnStatement as _ReturnStatement,
                                  Literal as _Literal)

                # Build a name -> TypeSystem table from the concrete function's
                # parameters and local variable declarations.  This is needed
                # because _resolved_type annotations are set by codegen, not by
                # the parser, so Identifier nodes in the substituted AST carry no
                # type at this point.
                from fast import VariableDeclaration as _VarDecl
                _local_type_table = {}
                for _p in concrete_func.parameters:
                    if _p.name is not None:
                        _local_type_table[_p.name] = _p.type_spec
                for _n in self._walk_ast(concrete_func):
                    if isinstance(_n, _VarDecl):
                        _local_type_table[_n.name] = _n.type_spec

                # Local aliases so the checker closures below can call the
                # promoted private methods without spelling out self every time.
                _bw = self._bw
                def _ts_of_expr(expr):
                    return self._ts_of_expr(expr, _local_type_table)

                def _arithmetic_result_width(node):
                    """
                    For a BinaryOp, infer the result width as the minimum of the two
                    operand widths (C-style implicit truncation to narrower type).
                    Returns (result_width, max_operand_width) or (0, 0) if unknown.
                    """
                    lts = _ts_of_expr(node.left)
                    rts = _ts_of_expr(node.right)
                    lw = _bw(lts)
                    rw = _bw(rts)
                    if not lw or not rw:
                        return 0, 0
                    return min(lw, rw), max(lw, rw)

                # ----------------------------------------------------------------
                # Node-type checker registry.
                # Each entry: node_type -> checker(node, op, lname, rname, lts, rts,
                #                                  is_trunc, _between, constrained)
                #             -> (violated: bool, src_w, dst_w, line, col)
                #
                # Add new checkers here as new relational constraint semantics land.
                # ----------------------------------------------------------------

                def _check_cast_node(node, op, lname, rname, lts, rts,
                                     is_trunc, between, constrained):
                    # Explicit cast / type-convert: (type)expr or type(expr)
                    src_ts = _ts_of_expr(node.expression)
                    dst_ts = node.target_type
                    src_w  = _bw(src_ts)
                    dst_w  = _bw(dst_ts)
                    if not src_w or not dst_w:
                        return False, 0, 0, '?', '?'
                    if is_trunc:
                        if dst_w >= src_w:
                            return False, 0, 0, '?', '?'
                    else:
                        if dst_w <= src_w:
                            return False, 0, 0, '?', '?'
                    src_match = any(_bw(cts) == src_w for cts in constrained.values())
                    dst_match = any(_bw(cts) == dst_w for cts in constrained.values())
                    if between:
                        violated = src_match and dst_match
                    else:
                        violated = src_match or dst_match
                    line = getattr(node, 'source_line', '?')
                    col  = getattr(node, 'source_col',  '?')
                    return violated, src_w, dst_w, line, col

                def _check_binaryop_node(node, op, lname, rname, lts, rts,
                                         is_trunc, between, constrained):
                    # Arithmetic BinaryOp: detect implicit lowering context.
                    # When a constrained type participates in arithmetic with a
                    # narrower type, the result is implicitly narrowed - a lowering
                    # context even without an explicit cast node.
                    result_w, max_w = _arithmetic_result_width(node)
                    if not result_w or result_w == max_w:
                        # No width change - no narrowing / widening
                        return False, 0, 0, '?', '?'
                    if is_trunc:
                        # result_w < max_w means the wider operand's value was narrowed
                        pass
                    else:
                        # widening check: result_w > min operand width
                        lts_n = _ts_of_expr(node.left)
                        rts_n = _ts_of_expr(node.right)
                        lw_n  = _bw(lts_n)
                        rw_n  = _bw(rts_n)
                        if not lw_n or not rw_n:
                            return False, 0, 0, '?', '?'
                        if result_w <= min(lw_n, rw_n):
                            return False, 0, 0, '?', '?'
                    # Check whether the constrained params are involved
                    constrained_widths = {_bw(cts) for cts in constrained.values()}
                    narrow_match = result_w in constrained_widths
                    wide_match   = max_w    in constrained_widths
                    if between:
                        violated = narrow_match and wide_match
                    else:
                        violated = narrow_match or wide_match
                    line = getattr(node, 'source_line', '?')
                    col  = getattr(node, 'source_col',  '?')
                    return violated, result_w, max_w, line, col

                def _check_unaryop_node(node, op, lname, rname, lts, rts,
                                        is_trunc, between, constrained):
                    # Placeholder: unary ops do not currently produce narrowing /
                    # widening contexts.  Hook is present for future operators
                    # (e.g. sign-extension, bit-truncation unary ops).
                    return False, 0, 0, '?', '?'

                def _check_return_node(node, op, lname, rname, lts, rts,
                                       is_trunc, between, constrained):
                    # 'return expr' is a truncation context when the function's declared
                    # return type is narrower than the expression being returned.
                    if node.value is None:
                        return False, 0, 0, '?', '?'
                    ret_ts = concrete_func.return_type
                    expr_ts = _ts_of_expr(node.value)
                    # BinaryOp has no _resolved_type at parse time; infer from operands.
                    if expr_ts is None and isinstance(node.value, _BinaryOp):
                        _rw_result, _rw_max = _arithmetic_result_width(node.value)
                        expr_w = _rw_max if _rw_max else _rw_result
                    else:
                        expr_w = _bw(expr_ts)
                    ret_w = _bw(ret_ts)
                    if not ret_w or not expr_w:
                        return False, 0, 0, '?', '?'
                    if is_trunc:
                        if expr_w <= ret_w:
                            return False, 0, 0, '?', '?'
                        src_w, dst_w = expr_w, ret_w
                    else:
                        if expr_w >= ret_w:
                            return False, 0, 0, '?', '?'
                        src_w, dst_w = expr_w, ret_w
                    src_match = any(_bw(cts) == src_w for cts in constrained.values())
                    dst_match = any(_bw(cts) == dst_w for cts in constrained.values())
                    if between:
                        violated = src_match and dst_match
                    else:
                        violated = src_match or dst_match
                    line = getattr(node, 'source_line', '?')
                    col  = getattr(node, 'source_col',  '?')
                    return violated, src_w, dst_w, line, col

                # Registry maps node type -> checker function
                _node_checkers = {
                    _CastExpr:          _check_cast_node,
                    _TypeConvExpr:      _check_cast_node,
                    _BinaryOp:          _check_binaryop_node,
                    _UnaryOp:           _check_unaryop_node,
                    _ReturnStatement:   _check_return_node,
                }

                for _op, _lname, _rname, _lts, _rts in _pending_body_checks:
                    _lw = _bw(_lts)
                    _rw = _bw(_rts)
                    _between  = _op in ("!`<=", "!`>=")
                    _is_trunc = _op in ("!`<",  "!`<=")
                    _constrained = {_lname: _lts, _rname: _rts}

                    for _node in self._walk_ast(concrete_func):
                        _checker = _node_checkers.get(type(_node))
                        if _checker is None:
                            continue
                        _violated, _sw, _dw, _line, _col = _checker(
                            _node, _op, _lname, _rname, _lts, _rts,
                            _is_trunc, _between, _constrained
                        )
                        if not _violated:
                            continue
                        _kind    = "truncation" if _is_trunc else "widening"
                        _scope   = "between" if _between else "on"
                        _lmangle = self._type_system_to_mangle_str(_lts)
                        _rmangle = self._type_system_to_mangle_str(_rts)
                        # Build operand annotation for BinaryOp violations
                        _annotation = ""
                        if isinstance(_node, _BinaryOp):
                            _lt_n = _ts_of_expr(_node.left)
                            _rt_n = _ts_of_expr(_node.right)
                            _lt_s = self._type_system_to_mangle_str(_lt_n) if _lt_n else "?"
                            _rt_s = self._type_system_to_mangle_str(_rt_n) if _rt_n else "?"
                            # Centre \ / under the operator: space in \ / is at
                            # offset len(_lt_s)+2 within the annotation (1-based),
                            # so pad = _col - len(_lt_s) - 2
                            _pad = max(0, _col - len(_lt_s) - 3) if isinstance(_col, int) else 0
                            _annotation = " " * _pad + f"{_lt_s} \\ / {_rt_s}"
                        elif isinstance(_node, _ReturnStatement):
                            _ret_mangle = self._type_system_to_mangle_str(concrete_func.return_type)
                            _annotation = f"// 5 + x will lower to {_ret_mangle}"
                        # For unary relations (lname == rname) the types are the same;
                        # emit "on {type}" rather than "on {type} and {type}".
                        if _lname == _rname or _lmangle == _rmangle:
                            _type_clause = _lmangle
                        else:
                            _type_clause = f"{_lmangle} and {_rmangle}"
                        _saved_err_tok = self.current_token
                        if isinstance(_line, int) and isinstance(_col, int) and _line > 0:
                            self.current_token = type('_Tok', (), {'line': _line, 'column': _col})()
                        if _op == "!@":
                            self.error(
                                f"Type relation {_lname} {_op} {_rname} violated: "
                                f"cannot take address of {_type_clause}",
                                annotation=_annotation
                            )
                        else:
                            self.error(
                                f"Type relation {_lname} {_op} {_rname} violated: "
                                f"illegal {_kind} {_scope} {_type_clause}",
                                annotation=_annotation
                            )
                        self.current_token = _saved_err_tok

            # If this is a method template (qualified name), inject directly into the
            # object's method list so it is compiled via emit_method_body, which
            # correctly registers 'this' and builds the method signature.
            if '.' in func_name:
                object_part = func_name.rsplit('.', 1)[0]
                method_part = func_name.rsplit('.', 1)[1]
                concrete_func.name = method_part
                obj_def = self._parsed_objects.get(object_part)
                if obj_def is not None:
                    obj_def.methods.append(concrete_func)
                else:
                    self._pending_template_instances.append(('function', concrete_func))
            else:
                self._pending_template_instances.append(('function', concrete_func))

        return func_name  # Call site uses the original name; overload resolution finds it

    def _try_instantiate_template_op(self, op_symbol: str, left_expr, right_expr):
        """
        Called immediately after every BinaryOp creation.  If a template operator is
        registered for `op_symbol` and we can infer concrete types from both operands,
        instantiate the concrete FunctionDef so codegen's overload lookup finds it.
        """
        if not (self._templates.has(op_symbol) and self._templates.lookup(op_symbol).kind == 'operator'):
            return
        lts = self._infer_type_from_expr(left_expr)
        rts = self._infer_type_from_expr(right_expr)
        if lts is None or rts is None:
            return
        self._resolve_template_operator(op_symbol, [lts, rts])

    def _resolve_template_operator(self, op_symbol: str, arg_type_specs: list):
        """
        Instantiate a template operator for the given concrete operand TypeSystems.
        `op_symbol` is the raw operator symbol string (e.g. '+').
        `arg_type_specs` is a list of two TypeSystem objects - one per operand.

        A concrete FunctionDef is produced (via _substitute_template) and appended to
        _pending_template_instances so codegen can find it by normal overload resolution
        inside visit_BinaryOp.  The BinaryOp AST node is left unchanged.
        """
        entry = self._templates.lookup(op_symbol)
        if entry is None or entry.kind != 'operator':
            return
        template_params = entry.params
        template_func = entry.node
        #import sys as _sys
        #_sys.stderr.write(f'[DEBUG _resolve_template_operator] op={op_symbol!r} template_params={template_params} arg_type_specs=[{", ".join(str(t) for t in arg_type_specs)}]\n')
        #_sys.stderr.write(f'[DEBUG _resolve_template_operator] func.params=[{", ".join(str(p.type_spec) for p in template_func.parameters)}]\n')
        #_sys.stderr.flush()
        # less than the number of operands (2 for a binary operator). Infer the
        # template param bindings by matching the function's declared parameter
        # typespecs against the concrete operand typespecs from the call site.
        # e.g. operator<T>(Ring<T>* dst, Ring<T>* src): T is inferred from dst/src.
        if len(arg_type_specs) != len(template_func.parameters):
            #import sys as _sys; _sys.stderr.write(f'[DEBUG rto] bail operand count {len(arg_type_specs)} != param count {len(template_func.parameters)}\n'); _sys.stderr.flush()
            return  # Wrong number of operands entirely - cannot instantiate

        # Keep the original call-site operand types for the primitive guard below.
        # After inference, arg_type_specs becomes the inferred template params (e.g. [int])
        # which may look primitive even when the operands themselves are struct pointers.
        _original_operand_specs = list(arg_type_specs)

        if len(template_params) != len(arg_type_specs):
            # Infer: build mapping from template param names -> concrete TypeSystems
            # by unifying each function parameter's declared typespec with the
            # corresponding concrete operand typespec from the call site.
            inferred: dict = {}
            for func_param, concrete_ts in zip(template_func.parameters, arg_type_specs):
                decl_ts = func_param.type_spec
                if decl_ts is None:
                    continue
                decl_name = decl_ts.custom_typename
                if not decl_name:
                    continue
                # Case 1: the declared type IS a bare template param name, e.g. T
                if decl_name in template_params:
                    # Strip pointer depth from concrete to get the plain type
                    concrete_inner = concrete_ts
                    if concrete_ts.is_pointer and decl_ts.is_pointer:
                        import copy as _cp
                        concrete_inner = _cp.copy(concrete_ts)
                        concrete_inner.is_pointer = False
                        concrete_inner.pointer_depth = max(0, (concrete_ts.pointer_depth or 1) - (decl_ts.pointer_depth or 1))
                        if concrete_inner.pointer_depth == 0:
                            concrete_inner.is_pointer = False
                    if decl_name not in inferred:
                        inferred[decl_name] = concrete_inner
                    continue
                # Case 2: declared type is a parameterised name like "Ring<T>"
                if '<' in decl_name and '>' in decl_name:
                    bracket = decl_name.index('<')
                    _base = decl_name[:bracket]
                    _raw_params = [s.strip() for s in decl_name[bracket + 1:-1].split(',')]
                    # concrete_ts.custom_typename should be the mangled form e.g. "Ring__int"
                    conc_name = concrete_ts.custom_typename if concrete_ts.custom_typename else ''
                    # The mangled name is struct_base + "__" + "_".join(type_names)
                    # Try to recover the concrete type names by resolving the mangled struct
                    if conc_name.startswith(_base + '__'):
                        remainder = conc_name[len(_base) + 2:]  # e.g. "int" or "int_float"
                        # We only handle the single-param case robustly here
                        if len(_raw_params) == 1 and _raw_params[0] in template_params:
                            pname = _raw_params[0]
                            if pname not in inferred:
                                # Look up the concrete TypeSystem from the symbol table
                                resolved = self.symbol_table.get_type_spec(remainder)
                                if resolved is not None:
                                    inferred[pname] = resolved
                                else:
                                    # Fallback: construct a DATA type from the remainder name
                                    from ftypesys import DataType as _DT
                                    _dt_by_val = {dt.value: dt for dt in _DT}
                                    if remainder in _dt_by_val:
                                        inferred[pname] = TypeSystem(base_type=_dt_by_val[remainder])
                                    else:
                                        inferred[pname] = TypeSystem(base_type=_DT.DATA, custom_typename=remainder)
            # Verify all template params are accounted for
            if not all(p in inferred for p in template_params):
                #import sys as _sys; _sys.stderr.write(f'[DEBUG rto] bail could not infer\n'); _sys.stderr.flush()
                return  # Could not infer all template params - skip instantiation
            # Replace arg_type_specs with the inferred single-param list
            arg_type_specs = [inferred[p] for p in template_params]

        # Mirror the parser's non-builtin guard for concrete operator overloads:
        # refuse to instantiate when all operand types are plain primitives.
        # This prevents the overload from hijacking every built-in arithmetic
        # operation in the standard library (e.g. every i + 1 loop increment).
        from ftypesys import Operator as _Operator
        _builtin_op_values = {op.value for op in _Operator}
        if op_symbol in _builtin_op_values:
            def _is_non_builtin(ts):
                # DATA with no custom_typename is a fixed-width int alias (i32, u64,
                # etc.) - treat it as primitive. Only structs, objects, named custom
                # types, or pointers count as genuinely non-builtin.
                return (ts.custom_typename is not None or
                        ts.base_type in (DataType.STRUCT, DataType.OBJECT) or
                        ts.is_pointer)
            if not any(_is_non_builtin(ts) for ts in _original_operand_specs):
                #import sys as _sys; _sys.stderr.write(f'[DEBUG rto] bail all-primitive\n'); _sys.stderr.flush()
                return  # All-primitive instantiation - skip to avoid overriding builtins

        # Build a stable mangle key so each unique pair of concrete types is only
        # instantiated once.
        type_names = [self._type_system_to_mangle_str(ts) for ts in arg_type_specs]
        mangle_key = template_func.name + '__tmpl__' + '__'.join(type_names)

        if self._templates.is_emitted(op_symbol, mangle_key):
            return
        self._templates.mark_emitted(op_symbol, mangle_key)

        # Build the substitution mapping: template param name -> concrete TypeSystem
        mapping = self._build_template_mapping(template_params, type_names, arg_type_specs)

        concrete_func = self._substitute_template(template_func, mapping)
        # Keep the original mangled function name (e.g. operator__plus); the
        # LLVM-level overload uniqueness comes from distinct parameter types.
        concrete_func.name = template_func.name
        concrete_func.no_mangle = False
        # Tag with _source_namespace so pass 3 in fcodegen picks it up as a
        # template instantiation and emits it after all namespace functions are
        # registered. Without this attribute the pass 3 filter silently skips it.
        concrete_func._source_namespace = ''
        self._pending_template_instances.append(('function', concrete_func))

    def _infer_type_from_expr(self, expr) -> 'TypeSystem | None':
        """
        Best-effort parse-time type inference for a BinaryOp operand.
        Returns a TypeSystem if the type can be determined, else None.
        """
        from fast import Identifier, Literal, BinaryOp as _BinaryOp
        if isinstance(expr, Identifier):
            return self.symbol_table.get_type_spec(expr.name)
        if isinstance(expr, Literal):
            return self._literal_dt_map().get(expr.type)
        return None

    def postfix_expression(self) -> Expression:
        """
        postfix_expression -> ('~')? primary_expression (postfix_operator)*
        postfix_operator -> '[' expression ']'
                         | '(' argument_list? ')'
                         | '.' IDENTIFIER        # Field access for structs
                         | '->' IDENTIFIER
                         | '++'
                         | '--'
        """
        # '~' (tie/move) binds to the primary before any postfix operators,
        # so ~x.f(...) parses as (~x).f(...) not ~(x.f(...)).
        tie_tok = None
        if self.expect(TokenType.TIE):
            tie_tok = self.current_token
            self.advance()

        expr = self.primary_expression()

        if tie_tok is not None:
            expr = TieExpression(expr).set_location(tie_tok.line, tie_tok.column)
        
        # Handle explicit template call: foo<int>(args) or foo<i32>(args)
        # Check before the main postfix loop so <type> is consumed before '('
        if (isinstance(expr, Identifier) and
                self._templates.has(expr.name) and self._templates.lookup(expr.name).kind == 'function' and
                self.expect(TokenType.LESS_THAN)):
            # Parse the explicit type argument list
            tok = self.current_token
            self.advance()  # consume '<'
            type_names = []
            type_specs = []
            # Each type arg is a full type_spec (covers SINT, UINT, IDENTIFIER aliases, etc.)
            ts = self.type_spec()
            type_names.append(self._type_system_to_mangle_str(ts))
            type_specs.append(ts)
            while self.expect(TokenType.COMMA):
                self.advance()
                ts = self.type_spec()
                type_names.append(self._type_system_to_mangle_str(ts))
                type_specs.append(ts)
            self.consume(TokenType.GREATER_THAN)
            # Now consume the argument list
            self.consume(TokenType.LEFT_PAREN)
            args = []
            if not self.expect(TokenType.RIGHT_PAREN):
                args = self.argument_list()
            self.consume(TokenType.RIGHT_PAREN)
            # If any type arg is still an active template param, we are inside a
            # template function body.  Defer instantiation: store the call as a
            # FunctionCall with a deferred name "funcname<T,U>" so that
            # _substitute_template can expand it when concrete types are known.
            if any(n in self._active_template_params for n in type_names):
                deferred_name = f"{expr.name}<{','.join(type_names)}>"
                expr = FunctionCall(deferred_name, args).set_location(tok.line, tok.column)
            else:
                mangled = self._resolve_template_call(expr.name, type_names, type_specs)
                expr = FunctionCall(mangled, args).set_location(tok.line, tok.column)

        # Handle implicit template call: foo(args) - infer <T, U, ...> from argument types.
        # Only triggered when the function name is a known template function and the next
        # token is '(' (no explicit '<' type list was written by the programmer).
        elif (isinstance(expr, Identifier) and
                self._templates.has(expr.name) and self._templates.lookup(expr.name).kind == 'function' and
                self.expect(TokenType.LEFT_PAREN)):
            tok = self.current_token
            self.consume(TokenType.LEFT_PAREN)
            # Advance tok by one column so constraint errors point at the argument,
            # not the opening paren.
            tok = type('_Tok', (), {'line': tok.line, 'column': tok.column + 1})()
            args = []
            if not self.expect(TokenType.RIGHT_PAREN):
                args = self.argument_list()
            self.consume(TokenType.RIGHT_PAREN)

            _entry_6487 = self._templates.lookup(expr.name)
            template_param_names = _entry_6487.params

            # Infer template-param -> TypeSystem bindings from call-site arguments.
            inferred: dict = self._infer_template_params(_entry_6487, args)

            # Build per-param source positions for error reporting (best-effort).
            _arg_pos: dict = {}
            for i, decl_param in enumerate(_entry_6487.node.parameters):
                if i >= len(args):
                    break
                param_ts = decl_param.type_spec
                if param_ts is None:
                    continue
                param_tname = (
                    param_ts.custom_typename if param_ts.custom_typename
                    else (param_ts.base_type if isinstance(param_ts.base_type, str) else None)
                )
                if param_tname and param_tname in template_param_names and param_tname not in _arg_pos:
                    _arg_pos[param_tname] = (
                        getattr(args[i], 'source_line', None),
                        getattr(args[i], 'source_col',  None),
                    )

            # Only proceed with implicit instantiation if every template param was resolved
            # to a *concrete* type. If any inferred TypeSystem maps a param back to itself
            # (e.g. inferred["T"] = TypeSystem(custom_typename="T")), the variable was
            # declared inside a template body and its type is still abstract -- skip.
            # Fill in defaults for any unresolved params before the completeness check.
            _defaults_map = (self._templates.lookup(expr.name).defaults if self._templates.has(expr.name) else {}) or {}
            _no_default_set = (self._templates.lookup(expr.name).no_default if self._templates.has(expr.name) else set()) or set()
            for _p in template_param_names:
                if _p not in inferred and _p in _defaults_map:
                    inferred[_p] = _defaults_map[_p]
            # Check <!+ params are resolved
            for _p in _no_default_set:
                if _p not in inferred:
                    _saved_tok3 = self.current_token
                    self.current_token = tok
                    self.error(
                        f"Template parameter '{_p}' of '{expr.name}' has no default "
                        f"and could not be inferred - it must be supplied explicitly"
                    )
                    self.current_token = _saved_tok3
            if sum(1 for k in inferred if not k.startswith('__dict_arg_ts_')) == len(template_param_names):
                type_names = [self._type_system_to_mangle_str(inferred[p]) for p in template_param_names]
                type_specs = [inferred[p] for p in template_param_names]
                # Reject self-referential inferences: if any mangle string equals a template
                # param name of the callee, the argument's type is still abstract.
                if any(tn in template_param_names for tn in type_names):
                    expr = FunctionCall(expr.name, args).set_location(tok.line, tok.column)
                else:
                    _saved_tok = self.current_token
                    self.current_token = tok
                    _positions = [
                        _arg_pos.get(p, (None, None))
                        for p in template_param_names
                    ]
                    # Collect concrete dict arg TypeSystems for capacity patching
                    _dict_arg_ts_map = {k: v for k, v in inferred.items() if k.startswith('__dict_arg_ts_')}
                    self._pending_dict_arg_ts = _dict_arg_ts_map
                    mangled = self._resolve_template_call(expr.name, type_names, type_specs,
                                                          arg_positions=_positions)
                    self._pending_dict_arg_ts = {}
                    self.current_token = _saved_tok
                    expr = FunctionCall(mangled, args).set_location(tok.line, tok.column)
            else:
                # Inference incomplete.  If we are inside a template body and every
                # unresolved param is an active template param, emit a deferred call
                # "funcname<T,U>" so _substitute_template can expand it when the
                # outer template is instantiated with concrete types.
                unresolved = [p for p in template_param_names if p not in inferred]
                if unresolved and all(p in self._active_template_params for p in unresolved):
                    # Build the deferred type-arg list: resolved params use their inferred
                    # mangle string; unresolved params pass through as bare names (e.g. "T").
                    deferred_type_args = []
                    for p in template_param_names:
                        if p in inferred:
                            deferred_type_args.append(self._type_system_to_mangle_str(inferred[p]))
                        else:
                            deferred_type_args.append(p)
                    deferred_name = f"{expr.name}<{','.join(deferred_type_args)}>"
                    expr = FunctionCall(deferred_name, args).set_location(tok.line, tok.column)
                else:
                    # Inference incomplete and not inside a template body - emit a plain
                    # FunctionCall and let the codegen/type-checker surface an error.
                    expr = FunctionCall(expr.name, args).set_location(tok.line, tok.column)

        while True:
            if self.expect(TokenType.LEFT_BRACKET):
                # Array access or array slice [start:end] or range assignment [start..end] = {fill}
                tok = self.current_token
                self.advance()
                # Check for bit-index: [`index]
                if self.expect(TokenType.BACKTICK):
                    self.advance()  # consume `
                    bit_index = self.expression()
                    self.consume(TokenType.RIGHT_BRACKET)
                    expr = BitIndexAccess(expr, bit_index).set_location(tok.line, tok.column)
                    continue
                start_index = self.expression()
                # Check if this is a bit-slice operation [start``end]
                if self.expect(TokenType.BITSLICE):
                    self.advance()  # consume ``
                    end_index = self.expression()
                    self.consume(TokenType.RIGHT_BRACKET)
                    expr = BitSlice(expr, start_index, end_index).set_location(tok.line, tok.column)
                # Check if this is a slice operation [start:end]
                elif self.expect(TokenType.COLON):
                    self.advance()
                    end_index = self.expression()
                    self.consume(TokenType.RIGHT_BRACKET)
                    # Create an ArraySlice node
                    expr = ArraySlice(expr, start_index, end_index).set_location(tok.line, tok.column)
                else:
                    # Regular array access
                    self.consume(TokenType.RIGHT_BRACKET)
                    # Check for set-notation range assignment: array[start..end] = {fill}
                    # start_index will be a RangeExpression if the subscript was `start..end`
                    if isinstance(start_index, RangeExpression) and self.expect(TokenType.ASSIGN):
                        self.advance()  # consume '='
                        self.consume(TokenType.LEFT_BRACE, "Expected '{' after '=' in range assignment")
                        fill = self.expression()
                        self.consume(TokenType.RIGHT_BRACE, "Expected '}' after fill value in range assignment")
                        expr = RangeAssignment(expr, start_index.start, start_index.end, fill).set_location(tok.line, tok.column)
                        # RangeAssignment is a statement; break out of postfix loop
                        break
                    # Dict key validation: if expr is a known dict and key is a string literal,
                    # verify the key exists at compile time.
                    if isinstance(expr, Identifier):
                        _dict_entry = self.symbol_table.lookup_variable(expr.name)
                        if (_dict_entry and _dict_entry.type_spec and
                                getattr(_dict_entry.type_spec, 'base_type', None) == DataType.DICT and
                                isinstance(start_index, StringLiteral)):
                            _known_keys = getattr(_dict_entry.type_spec, '_known_keys', None)
                            if _known_keys is not None and start_index.value not in _known_keys:
                                self.error(f"Key \"{start_index.value}\" does not exist in dict '{expr.name}'")
                    expr = ArrayAccess(expr, start_index).set_location(tok.line, tok.column)
            elif self.expect(TokenType.LEFT_PAREN):
                # Function call
                tok = self.current_token
                self.advance()
                args = []
                # Determine the callee name (if a plain identifier) so that ditto
                # tokens inside the argument list can be validated against _last_call_expr.
                _callee_name_for_ditto = expr.name if isinstance(expr, Identifier) else None
                if not self.expect(TokenType.RIGHT_PAREN):
                    args = self.argument_list(callee_name=_callee_name_for_ditto)
                self.consume(TokenType.RIGHT_PAREN)
                if isinstance(expr, Identifier):
                    if expr.name in self._macros:
                        # Expression macro invocation - build macroCall instead of FunctionCall
                        expr = macroCall(name=expr.name, arguments=args).set_location(tok.line, tok.column)
                    else:
                        expr = FunctionCall(expr.name, args).set_location(tok.line, tok.column)
                elif isinstance(expr, StringLiteral):
                    # String literal function name (for targeting mangled names like "??0Widget@@QEAA@AEBV0@@Z")
                    expr = FunctionCall(expr.value, args).set_location(tok.line, tok.column)
                elif isinstance(expr, FStringLiteral):
                    # F-string literal function name: f"{x} {y}"() - name resolved at codegen time
                    expr = FunctionCall(expr, args).set_location(tok.line, tok.column)
                elif isinstance(expr, Stringify):
                    # Stringify call: $X() - name resolved at codegen time (like FStringLiteral)
                    expr = FunctionCall(expr, args).set_location(tok.line, tok.column)
                    
                elif isinstance(expr, MemberAccess):
                    # Method call: obj.method() -> call obj_type.method with obj as first arg
                    # If tagged as a type function template, infer T and instantiate.
                    _tfk = getattr(expr, '_typefunc_template_key', None)
                    if _tfk and _tfk in self._templates:
                        _tfk_entry = self._templates.lookup(_tfk)
                        _tmpl_params = _tfk_entry.params
                        # skip_first_param=True: first declared param is implicit 'this' receiver
                        _inferred = self._infer_template_params(_tfk_entry, args, skip_first_param=True)
                        if len(_inferred) == len(_tmpl_params):
                            _tnames = [self._type_system_to_mangle_str(_inferred[p]) for p in _tmpl_params]
                            _tspecs = [_inferred[p] for p in _tmpl_params]
                            _saved_tok_tf = self.current_token
                            self.current_token = type('_Tok', (), {'line': tok.line, 'column': tok.column + 1})()
                            _mname = self._resolve_template_call(_tfk, _tnames, _tspecs)
                            self.current_token = _saved_tok_tf
                            expr = FunctionCall(_mname, [expr.object] + list(args)).set_location(tok.line, tok.column)
                        else:
                            expr = MethodCall(expr.object, expr.member, args).set_location(tok.line, tok.column)
                    else:
                        expr = MethodCall(expr.object, expr.member, args).set_location(tok.line, tok.column)
                else:
                    self.error(f"Cannot call function on complex expression: {type(expr).__name__}")
            elif self.expect(TokenType.DOT):
                # Member access - could be struct field or object method/member
                tok = self.current_token
                self.advance()
                if self.expect(TokenType.F_STRING, TokenType.I_STRING):
                    if self.expect(TokenType.F_STRING):
                        _mfsl = self.parse_f_string(self.consume(TokenType.F_STRING).value)
                    else:
                        _mfsl = self.parse_i_string(self.consume(TokenType.I_STRING).value)
                    member = self._resolve_fstring_name(_mfsl)
                elif self.expect(TokenType.STRING_LITERAL):
                    member = self.current_token.value
                    self.advance()
                elif self.expect(TokenType.TAG):
                    # .# is the tagged union tag accessor
                    self.advance()
                    member = "#"
                else:
                    member = self.consume(TokenType.IDENTIFIER).value

                # Handle templated method call: obj.method<T>(args)
                # Build the qualified key that was registered in object_def
                # Also check for type function templates registered under the mangled key.
                _tfunc_key = None
                if isinstance(expr, Identifier):
                    _recv_ts = self.symbol_table.get_type_spec(expr.name)
                    if _recv_ts is not None:
                        _recv_pdepth = getattr(_recv_ts, 'pointer_depth', 0)
                        if _recv_ts.custom_typename:
                            _recv_tname = _recv_ts.custom_typename
                        elif _recv_pdepth > 0 and getattr(_recv_ts, 'base_type', None) == DataType.BYTE:
                            _recv_tname = 'string'
                        elif _recv_pdepth > 0:
                            _recv_tname = str(_recv_ts.base_type.value) + '_ptr' * _recv_pdepth
                        else:
                            _recv_tname = str(_recv_ts.base_type.value)
                        if getattr(_recv_ts, 'is_tied', False):
                            _recv_tname = 'tied_' + _recv_tname
                        _candidate = f"__typefunc__{_recv_tname}__{member}"
                        if _candidate in self._templates:
                            _tfunc_key = _candidate
                        elif _candidate not in self._templates:
                            # Also try without tied_ prefix as fallback
                            _untied = f"__typefunc__{_recv_tname.removeprefix('tied_')}__{member}"
                            if _untied in self._templates:
                                _tfunc_key = _untied
                elif isinstance(expr, TieExpression) and isinstance(getattr(expr, 'operand', None), Identifier):
                    # ~x.member - receiver is a tied variable being moved
                    _recv_ts = self.symbol_table.get_type_spec(expr.operand.name)
                    if _recv_ts is not None:
                        _recv_pdepth = getattr(_recv_ts, 'pointer_depth', 0)
                        if _recv_ts.custom_typename:
                            _recv_tname = _recv_ts.custom_typename
                        elif _recv_pdepth > 0 and getattr(_recv_ts, 'base_type', None) == DataType.BYTE:
                            _recv_tname = 'string'
                        elif _recv_pdepth > 0:
                            _recv_tname = str(_recv_ts.base_type.value) + '_ptr' * _recv_pdepth
                        else:
                            _recv_tname = str(_recv_ts.base_type.value)
                        # Always use tied_ prefix for a TieExpression receiver
                        _recv_tname = 'tied_' + _recv_tname
                        _candidate = f"__typefunc__{_recv_tname}__{member}"
                        if _candidate in self._templates:
                            _tfunc_key = _candidate
                        else:
                            # Fallback: untied type function
                            _untied = f"__typefunc__{_recv_tname.removeprefix('tied_')}__{member}"
                            if _untied in self._templates:
                                _tfunc_key = _untied
                elif isinstance(expr, (StringLiteral, FStringLiteral)):
                    # String/f-string/i-string literal receiver - always type 'string'
                    _candidate = f"__typefunc__string__{member}"
                    if _candidate in self._templates:
                        _tfunc_key = _candidate
                if self.expect(TokenType.LESS_THAN):
                    obj_name = expr.name if isinstance(expr, Identifier) else None
                    qualified = f"{obj_name}.{member}" if obj_name else None
                    _tmpl_key = qualified if (qualified and qualified in self._templates) else _tfunc_key
                    if _tmpl_key and _tmpl_key in self._templates:
                        self.advance()  # consume '<'
                        type_names = []
                        type_specs = []
                        ts = self.type_spec()
                        type_names.append(self._type_system_to_mangle_str(ts))
                        type_specs.append(ts)
                        while self.expect(TokenType.COMMA):
                            self.advance()
                            ts = self.type_spec()
                            type_names.append(self._type_system_to_mangle_str(ts))
                            type_specs.append(ts)
                        self.consume(TokenType.GREATER_THAN)
                        self.consume(TokenType.LEFT_PAREN)
                        args = []
                        if not self.expect(TokenType.RIGHT_PAREN):
                            args = self.argument_list()
                        self.consume(TokenType.RIGHT_PAREN)
                        mangled = self._resolve_template_call(_tmpl_key, type_names, type_specs)
                        expr = FunctionCall(mangled, ([expr] + list(args)) if _tmpl_key and _tmpl_key.startswith('__typefunc__') else args).set_location(tok.line, tok.column)
                        continue

                # Implicit template type func call: a.my_func(args) where my_func is
                # a type function template - infer T from argument types at parse time.
                if _tfunc_key and self.expect(TokenType.LEFT_PAREN):
                    _prev_expr = expr
                    expr = MemberAccess(expr, member).set_location(tok.line, tok.column)
                    # Fall through to the LEFT_PAREN handler which creates MethodCall;
                    # template instantiation will be triggered there via _tfunc_key.
                    # Store the key on the MemberAccess so the call handler can find it.
                    expr._typefunc_template_key = _tfunc_key
                else:
                    # Create MemberAccess node - codegen will determine if it's
                    # StructFieldAccess or object member based on type
                    expr = MemberAccess(expr, member).set_location(tok.line, tok.column)
            elif self.expect(TokenType.INCREMENT):
                # Postfix increment - but not if ++ begins a registered custom operator
                tok = self.current_token
                matched_sym, _ = self._match_custom_op()
                if matched_sym is not None:
                    break
                self.advance()
                expr = UnaryOp(Operator.INCREMENT, expr, is_postfix=True).set_location(tok.line, tok.column)
            elif self.expect(TokenType.DECREMENT):
                # Postfix decrement - but not if -- begins a registered custom operator
                tok = self.current_token
                matched_sym, _ = self._match_custom_op()
                if matched_sym is not None:
                    break
                self.advance()
                expr = UnaryOp(Operator.DECREMENT, expr, is_postfix=True).set_location(tok.line, tok.column)
            elif self.expect(TokenType.NOT_NULL):
                # Postfix not-null operator: expr!?
                # Evaluates to true (i8 1) when operand is non-zero/non-null,
                # false (i8 0) when it is zero/null.
                tok = self.current_token
                self.advance()
                expr = NotNull(expr).set_location(tok.line, tok.column)
            elif self.expect(TokenType.AS):
                # AS cast expression (postfix) - support all type casts
                tok = self.current_token
                self.advance()
                target_type = self.type_spec()
                
                # Check if this is a struct cast
                if target_type.custom_typename:
                    expr = StructRecast(target_type.custom_typename, expr).set_location(tok.line, tok.column)
                else:
                    expr = CastExpression(target_type, expr).set_location(tok.line, tok.column)
            elif self.expect(TokenType.FROM):
                # FROM restructuring: StructType from source_expr
                # This creates a StructRecast where expr (the identifier) is the target type
                tok = self.current_token
                self.advance()
                source_expr = self.postfix_expression()
                
                # expr should be an Identifier representing the target struct type
                if isinstance(expr, Identifier):
                    target_typename = expr.name
                    expr = StructRecast(target_typename, source_expr).set_location(tok.line, tok.column)
                else:
                    self.error("Expected struct type name before 'from' keyword", TokenType.IDENTIFIER)
            elif self.expect(TokenType.IF):
                # If expression: value if (condition) [else alternative]
                tok = self.current_token
                self.advance()
                self.consume(TokenType.LEFT_PAREN, "Expected '(' after 'if' in if-expression")
                condition = self.expression()
                self.consume(TokenType.RIGHT_PAREN, "Expected ')' after condition in if-expression")

                # Check for else clause
                else_expr = None
                if self.expect(TokenType.ELSE):
                    self.advance()
                    # Parse the else expression as a postfix expression
                    # This handles: else z, else noinit, else (noinit if (...)), etc.
                    else_expr = self.postfix_expression()

                expr = IfExpression(expr, condition, else_expr).set_location(tok.line, tok.column)
            elif self._custom_postfix_ops:
                # Custom postfix unary operator: expr [op]
                matched_sym, matched_len = self._match_custom_unary_op(self._custom_postfix_ops)
                if matched_sym is None:
                    break
                tok = self.current_token
                for _ in range(matched_len):
                    self.advance()
                func_name = self._custom_postfix_ops[matched_sym]
                expr = FunctionCall(func_name, [expr]).set_location(tok.line, tok.column)
            else:
                break
        
        return expr
    
    def argument_list(self, callee_name: str = None) -> List[Expression]:
        """
        argument_list -> expression (',' expression)*

        When callee_name is provided, a DITTO token ('#"') may appear in place of
        an argument expression.  It repeats the argument at the same position from
        the most recent function-call expression statement (_last_call_expr).

        Rules (all produce a compiler error on violation):
          - _last_call_expr must be a FunctionCall (previous statement was a call).
          - _last_call_expr.name must equal callee_name (same function).
          - _last_call_expr must have the same arity as the current call being parsed
            (checked lazily as each ditto is encountered).
        """
        import copy

        def _parse_one_arg(pos: int) -> Expression:
            """Parse one argument at position `pos`, handling DITTO."""
            if callee_name is not None and self.expect(TokenType.DITTO):
                prev = self._last_call_expr
                if prev is None or not isinstance(prev, FunctionCall):
                    self.error(
                        "Ditto '#\"' in argument list: previous statement is not a function call",
                        annotation="DITTO disallowed here",
                        prev_source_line=self._last_noncall_src,
                    )
                if isinstance(prev.name, str) and prev.name != callee_name:
                    self.error(
                        f"Ditto '#\"' in argument list: previous call was to '{prev.name}', "
                        f"but current call is to '{callee_name}'",
                        annotation="DITTO disallowed here",
                    )
                if pos >= len(prev.arguments):
                    self.error(
                        f"Ditto '#\"' in argument list: argument position {pos} is out of range "
                        f"(previous call to '{prev.name}' had {len(prev.arguments)} argument(s))",
                        annotation="DITTO disallowed here",
                    )
                self.advance()  # consume DITTO
                return copy.deepcopy(prev.arguments[pos])
            return self.expression()

        args = [_parse_one_arg(0)]

        while self.expect(TokenType.COMMA):
            self.advance()
            args.append(_parse_one_arg(len(args)))

        return args

    def parse_f_string(self, f_string_content: str) -> FStringLiteral:
        """Parse f-string into parts without evaluating anything"""
        parts = []
        i = 0
        n = len(f_string_content)
        
        while i < n:
            if f_string_content[i] == '{' and i + 1 < n and f_string_content[i + 1] == '{':
                # Escaped {{
                parts.append('{')
                i += 2
            elif f_string_content[i] == '}' and i + 1 < n and f_string_content[i + 1] == '}':
                # Escaped }}
                parts.append('}')
                i += 2
            elif f_string_content[i] == '{':
                # Start of embedded expression - parse but don't evaluate
                expr_start = i + 1
                expr_end = f_string_content.find('}', expr_start)
                if expr_end == -1:
                    self.error("Unclosed expression in f-string")
                
                # Extract expression text
                expr_text = f_string_content[expr_start:expr_end]
                
                # Parse the expression normally (but don't evaluate it)
                from flexer import FluxLexer
                lexer = FluxLexer(expr_text)
                tokens = lexer.tokenize()
                expr_parser = FluxParser(tokens)
                # Propagate registered macros so call sites inside f-strings
                # are recognised and produce macroCall instead of FunctionCall.
                expr_parser._macros = self._macros
                expr_parser._custom_circumfix_ops = self._custom_circumfix_ops
                expr_parser._custom_prefix_ops = self._custom_prefix_ops
                expr_parser._custom_postfix_ops = self._custom_postfix_ops
                expr_parser._custom_operators = self._custom_operators
                expr_parser._custom_ternary_ops = self._custom_ternary_ops
                expression = expr_parser.expression()
                
                parts.append(expression)
                i = expr_end + 1
            else:
                # Regular character - accumulate into current string part
                if not parts or not isinstance(parts[-1], str):
                    parts.append(f_string_content[i])
                else:
                    parts[-1] += f_string_content[i]
                i += 1
        
        return FStringLiteral(parts)

    def parse_i_string(self, token_value: str) -> 'FStringLiteral':
        """Parse i-string token into FStringLiteral.

        Token value format: i"<template>":{<expr>;<expr>;...}
        Each {} in the template is replaced positionally by the corresponding expression.
        """
        from flexer import FluxLexer

        # Strip leading i"
        rest = token_value[2:]  # strip i"

        # Find the closing quote of the template
        template = ""
        idx = 0
        while idx < len(rest):
            if rest[idx] == '\\' and idx + 1 < len(rest):
                template += rest[idx:idx+2]
                idx += 2
            elif rest[idx] == '"':
                idx += 1
                break
            else:
                template += rest[idx]
                idx += 1

        # Parse expression list from :{...} block
        expressions = []
        remainder = rest[idx:].lstrip()
        if remainder.startswith(':'):
            remainder = remainder[1:].lstrip()
        if remainder.startswith('{') and remainder.endswith('}'):
            exprs_text = remainder[1:-1]
            for expr_text in exprs_text.split(';'):
                expr_text = expr_text.strip()
                if not expr_text:
                    continue
                lexer = FluxLexer(expr_text)
                tokens = lexer.tokenize()
                expr_parser = FluxParser(tokens)
                # Propagate macros so call sites inside i-strings are recognised.
                expr_parser._macros = self._macros
                expr_parser._custom_circumfix_ops = self._custom_circumfix_ops
                expr_parser._custom_prefix_ops = self._custom_prefix_ops
                expr_parser._custom_postfix_ops = self._custom_postfix_ops
                expr_parser._custom_operators = self._custom_operators
                expr_parser._custom_ternary_ops = self._custom_ternary_ops
                expressions.append(expr_parser.expression())

        # Build FStringLiteral parts, substituting {} placeholders positionally
        parts = []
        expr_index = 0
        i = 0
        n = len(template)
        while i < n:
            if template[i] == '{' and i + 1 < n and template[i+1] == '}':
                if expr_index < len(expressions):
                    parts.append(expressions[expr_index])
                    expr_index += 1
                i += 2
            else:
                if not parts or not isinstance(parts[-1], str):
                    parts.append(template[i])
                else:
                    parts[-1] += template[i]
                i += 1

        return FStringLiteral(parts)

    def primary_expression(self) -> Expression:
        """
        primary_expression -> IDENTIFIER
                           | INTEGER
                           | FLOAT
                           | CHAR
                           | STRING_LITERAL
                           | 'true'
                           | 'false'
                           | 'void'
                           | 'this'
                           | 'super'
                           | '(' expression ')'
                           | array_literal
                           | struct_literal  # Returns StructLiteral, not old Literal
        """
        if self.expect(TokenType.IDENTIFIER):
            return self.scoped_identifier()
        elif self.expect(TokenType.SINT_LITERAL):
            tok = self.current_token
            if self.current_token.value.startswith('0d'):
                number_str = self.current_token.value[2:]
                # Define the digits for base 32: 0-9, A-V
                digits = '0123456789ABCDEFGHIJKLMNOPQRSTUV'
                digits_map = {char: idx for idx, char in enumerate(digits)}
                
                value = 0
                for char in number_str.upper():
                    value = value * 32 + digits_map[char]
                self.advance()
            else:
                value = int(self.current_token.value, 0)
                self.advance()
            return Literal(value, DataType.SINT).set_location(tok.line, tok.column)
        elif self.expect(TokenType.UINT_LITERAL):
            #print(self.current_token.value)
            tok = self.current_token
            if self.current_token.value.startswith('0d'):
                number_str = self.current_token.value[2:]
                # Define the digits for base 32: 0-9, A-V
                digits = '0123456789ABCDEFGHIJKLMNOPQRSTUV'
                digits_map = {char: idx for idx, char in enumerate(digits)}
                
                value = 0
                for char in number_str.upper():
                    value = value * 32 + digits_map[char]
                self.advance()
            else:
                value = int(self.current_token.value, 0)
                self.advance()
            #print(value)
            return Literal(value, DataType.UINT).set_location(tok.line, tok.column)
        elif self.expect(TokenType.SLONG_LITERAL):
            tok = self.current_token
            value = int(tok.value, 0)
            self.advance()
            return Literal(value, DataType.SLONG).set_location(tok.line, tok.column)
        elif self.expect(TokenType.ULONG_LITERAL):
            tok = self.current_token
            value = int(tok.value, 0)
            self.advance()
            return Literal(value, DataType.ULONG).set_location(tok.line, tok.column)
        elif self.expect(TokenType.FLOAT):
            tok = self.current_token
            value = float(tok.value)
            self.advance()
            return Literal(value, DataType.FLOAT).set_location(tok.line, tok.column)
        elif self.expect(TokenType.DOUBLE):
            tok = self.current_token
            value = float(tok.value)
            self.advance()
            return Literal(value, DataType.DOUBLE).set_location(tok.line, tok.column)
        elif self.expect(TokenType.CHAR):
            tok = self.current_token
            # A quoted char literal ('a') has tok.value as the literal character string.
            # normalize_char_value will call ord() on it.
            # A numeric char literal (97c) has tok.value as an int (the codepoint directly)
            # set by the lexer. normalize_char_value returns it as-is.
            self.advance()
            return Literal(tok.value, DataType.CHAR).set_location(tok.line, tok.column)
        elif self.expect(TokenType.BYTE_LITERAL):
            tok = self.current_token
            value = int(tok.value, 0)
            self.advance()
            return Literal(value, DataType.BYTE).set_location(tok.line, tok.column)
        elif self.expect(TokenType.STRING_LITERAL):
            tok = self.current_token
            value = tok.value
            self.advance()
            return StringLiteral(value).set_location(tok.line, tok.column)
        elif self.expect(TokenType.G_STRING):
            tok = self.current_token
            value = tok.value
            self.advance()
            return StringLiteral(value, storage_class=StorageClass.GLOBAL).set_location(tok.line, tok.column)
        elif self.expect(TokenType.F_STRING):
            tok = self.current_token
            f_string_content = self.current_token.value
            self.advance()
            return self.parse_f_string(f_string_content).set_location(tok.line, tok.column)
        elif self.expect(TokenType.I_STRING):
            tok = self.current_token
            token_value = tok.value
            self.advance()
            return self.parse_i_string(token_value).set_location(tok.line, tok.column)
        elif self.expect(TokenType.TRUE):
            tok = self.current_token
            self.advance()
            return Literal(True, DataType.BOOL).set_location(tok.line, tok.column)
        elif self.expect(TokenType.FALSE):
            tok = self.current_token
            self.advance()
            return Literal(False, DataType.BOOL).set_location(tok.line, tok.column)
        elif self.expect(TokenType.VOID):
            tok = self.current_token
            self.advance()
            return Literal(0, DataType.VOID).set_location(tok.line, tok.column)
        elif self.expect(TokenType.THIS):
            tok = self.current_token
            self.advance()
            return Identifier("this").set_location(tok.line, tok.column)
        elif self.expect(TokenType.NO_INIT):
            tok = self.current_token
            self.advance()
            return NoInit().set_location(tok.line, tok.column)
        elif self.expect(TokenType.LEFT_PAREN):
            self.advance()
            expr = self.expression()
            self.consume(TokenType.RIGHT_PAREN)
            return expr
        elif self.expect(TokenType.LEFT_BRACKET):
            return self.array_literal()
        elif self.expect(TokenType.ELLIPSIS):
            # Variadic access: ...[N]
            tok = self.current_token
            self.advance()
            self.consume(TokenType.LEFT_BRACKET)
            index_expr = self.expression()
            self.consume(TokenType.RIGHT_BRACKET)
            return VariadicAccess(index_expr).set_location(tok.line, tok.column)
        elif self.expect(TokenType.COLON):
            # Placeholder syntax :(N)
            tok = self.current_token
            self.advance()  # consume ':'
            self.consume(TokenType.LEFT_PAREN)
            if not self.expect(TokenType.SINT_LITERAL, TokenType.UINT_LITERAL):
                self.error("Expected integer in placeholder :(N)", TokenType.SINT_LITERAL)
            index = int(self.current_token.value, 0)
            self.advance()
            self.consume(TokenType.RIGHT_PAREN)
            return AcceptorPlaceholder(index).set_location(tok.line, tok.column)
        elif self.expect(TokenType.DICT_LITERAL):
            tok = self.current_token
            self.advance()  # consume 'd{'
            keys = []
            values = []
            while not self.expect(TokenType.RIGHT_BRACE):
                k = self.expression()
                self.consume(TokenType.COLON)
                v = self.expression()
                keys.append(k)
                values.append(v)
                if self.expect(TokenType.COMMA):
                    self.advance()
            self.consume(TokenType.RIGHT_BRACE)
            return DictLiteralExpr(keys=keys, values=values).set_location(tok.line, tok.column)
        elif self.expect(TokenType.LEFT_BRACE):
            return self.struct_literal()
        elif self.expect(TokenType.SIZEOF):
            return self.sizeof_expression()
        elif self.expect(TokenType.ALIGNOF):
            return self.alignof_expression()
        elif self.expect(TokenType.ENDIANOF):
            return self.endianof_expression()
        elif self.expect(TokenType.TYPEOF):
            return self.typeof_expression()
        elif self.expect(TokenType.STRUCT):
            tok = self.current_token
            self.advance()
            return Literal(value=DataType.STRUCT.value, type=DataType.STRUCT).set_location(tok.line, tok.column)
        elif self.expect(TokenType.OBJECT):
            tok = self.current_token
            self.advance()
            return Literal(value=DataType.OBJECT.value, type=DataType.OBJECT).set_location(tok.line, tok.column)
        elif self.expect(TokenType.STRINGIFY):
            # Stringify operator: $x or $x.member produces the name/value as a string.
            # Parsed here (primary level) so that the postfix loop can handle ($X)(args)
            # as a function call - e.g.  $X();  def $X() -> void {};
            # Also handles $~$IDENT and $~$f"..." (codify-then-stringify): codification
            # binds tighter, so the codify result becomes the stringified name.
            # Only enter this branch when '$' is followed by something that belongs to a
            # stringify expression. If the next token is a symbol character (e.g. '%' in
            # a custom operator '$%'), do not consume '$' -- fall through so the custom
            # operator machinery upstream can match the full operator sequence.
            _next = self.peek()
            _stringify_valid_next = (
                _next is not None and (
                    _next.type == TokenType.IDENTIFIER or
                    _next.type == TokenType.CODIFY or
                    _next.type == TokenType.DOT or
                    _next.type == TokenType.TAG or
                    _next.type in {
                        TokenType.SINT, TokenType.UINT, TokenType.SLONG, TokenType.ULONG,
                        TokenType.FLOAT_KW, TokenType.DOUBLE_KW, TokenType.BOOL_KW, TokenType.BYTE,
                    }
                )
            )
            if _stringify_valid_next:
                tok = self.current_token
                self.advance()
                if self.expect(TokenType.CODIFY):
                    # $~$expr -- resolve the codify expression first, then stringify it
                    resolved = self._consume_codify()
                    return StringLiteral(resolved).set_location(tok.line, tok.column)
                # Also accept built-in type keywords: $int, $float, $bool, etc.
                _STRINGIFY_KW = {
                    TokenType.SINT: "int", TokenType.UINT: "uint",
                    TokenType.SLONG: "long", TokenType.ULONG: "ulong",
                    TokenType.FLOAT_KW: "float", TokenType.DOUBLE_KW: "double",
                    TokenType.BOOL_KW: "bool", TokenType.BYTE: "byte",
                }
                if self.current_token.type in _STRINGIFY_KW:
                    kw_str = _STRINGIFY_KW[self.current_token.type]
                    self.advance()
                    return StringLiteral(kw_str).set_location(tok.line, tok.column)
                if not self.expect(TokenType.IDENTIFIER):
                    self.error("Expected identifier after '$'", TokenType.IDENTIFIER)
                name = self.current_token.value
                self.advance()
                member = None
                if self.expect(TokenType.DOT):
                    self.advance()
                    if self.expect(TokenType.IDENTIFIER):
                        member = self.current_token.value
                        self.advance()
                    elif self.expect(TokenType.TAG):
                        # $.# - stringify the tag of a tagged union
                        self.advance()
                        member = "#"
                    else:
                        self.error("Expected member name after '.' in stringify expression", TokenType.IDENTIFIER)
                return Stringify(name, member).set_location(tok.line, tok.column)
        elif self.expect(TokenType.CODIFY):
            # ~$f"..." on the RHS of an assignment in comptime context.
            # Treat as an f-string expression that evaluates to a string at VM runtime.
            tok = self.current_token
            self.advance()  # consume CODIFY
            if self.expect(TokenType.F_STRING):
                fstr_node = self.parse_f_string(self.consume(TokenType.F_STRING).value)
                return fstr_node.set_location(tok.line, tok.column)
            elif self.expect(TokenType.I_STRING):
                istr_node = self.parse_i_string(self.consume(TokenType.I_STRING).value)
                return istr_node.set_location(tok.line, tok.column)
            else:
                # ~$varname -- resolve from comptime strings or treat as identifier
                var_name = self.consume(TokenType.IDENTIFIER).value
                resolved = self._comptime_strings.get(var_name, var_name)
                return StringLiteral(resolved).set_location(tok.line, tok.column)
        elif self.expect(TokenType.SINT, TokenType.UINT, TokenType.FLOAT_KW, TokenType.DOUBLE_KW,
                         TokenType.CHAR, TokenType.BYTE, TokenType.BOOL_KW, TokenType.SLONG, TokenType.ULONG):
            # Built-in type convert expression: float(x), int(y), char(z), etc.
            kw_token = self.current_token
            kw_map = {
                TokenType.SINT:      DataType.SINT,
                TokenType.UINT:      DataType.UINT,
                TokenType.FLOAT_KW:  DataType.FLOAT,
                TokenType.DOUBLE_KW: DataType.DOUBLE,
                TokenType.CHAR:      DataType.CHAR,
                TokenType.BYTE:      DataType.BYTE,
                TokenType.BOOL_KW:   DataType.BOOL,
                TokenType.SLONG:      DataType.SLONG,
                TokenType.ULONG:     DataType.ULONG,
            }
            target_data_type = kw_map[kw_token.type]
            saved_pos = self.position
            self.advance()  # consume the type keyword
            if self.expect(TokenType.LEFT_PAREN):
                self.advance()  # consume '('
                inner_expr = self.expression()
                self.consume(TokenType.RIGHT_PAREN)
                target_type = TypeSystem(base_type=target_data_type)
                return TypeConvertExpression(target_type, inner_expr).set_location(kw_token.line, kw_token.column)
            else:
                # Not a type-convert expression - backtrack and fall through to error
                self.position = saved_pos
                self.current_token = self.tokens[self.position]
                self.error(f"Unexpected token: {self.current_token.type.name if self.current_token else 'EOF'}")
        else:
            self.error(f"Unexpected token: {self.current_token.type.name if self.current_token else 'EOF'}")

    def scoped_identifier(self) -> Expression:
        """
        scoped_identifier -> IDENTIFIER ('::' IDENTIFIER)*
        
        Handles:
        - Simple identifier: x
        - Scoped identifier: namespace::x
        - Nested scope: namespace::subnamespace::x
        - Type member: Type::static_member
        """
        tok = self.current_token
        parts = [self.consume(TokenType.IDENTIFIER).value]
        
        while self.expect(TokenType.SCOPE):
            self.advance()
            parts.append(self.consume(TokenType.IDENTIFIER).value)
        
        # If we have multiple parts, it's a scoped identifier
        if len(parts) > 1:
            # Join with :: to create the full scoped name
            full_name = "__".join(parts)
            return Identifier(full_name).set_location(tok.line, tok.column)
        else:
            # Single identifier
            return Identifier(parts[0]).set_location(tok.line, tok.column)

    def alignof_expression(self) -> AlignOf:
        """
        alignof_expression -> 'alignof' '(' (type_spec | expression) ')'
        """
        tok = self.current_token
        self.consume(TokenType.ALIGNOF)
        self.consume(TokenType.LEFT_PAREN)
        
        # Look ahead to determine if it's a type or expression
        saved_pos = self.position
        try:
            # Try to parse as type spec first
            target = self.type_spec()
            self.consume(TokenType.RIGHT_PAREN)
            return AlignOf(target).set_location(tok.line, tok.column)
        except ParseError:
            # If type parsing fails, try as expression
            self.position = saved_pos
            self.current_token = self.tokens[self.position]
            expr = self.expression()
            self.consume(TokenType.RIGHT_PAREN)
            return AlignOf(expr).set_location(tok.line, tok.column)

    def sizeof_expression(self) -> SizeOf:
        """
        sizeof_expression -> 'sizeof' '(' (type_spec | expression) ')'
        """
        tok = self.current_token
        self.consume(TokenType.SIZEOF)
        self.consume(TokenType.LEFT_PAREN)
        
        # Look ahead to determine if it's a type or expression
        saved_pos = self.position
        
        # Check if it starts with a known type keyword
        if self.expect(TokenType.SINT, TokenType.FLOAT_KW, TokenType.DOUBLE_KW, TokenType.CHAR, 
                      TokenType.BOOL_KW, TokenType.DATA, TokenType.VOID,
                      TokenType.SLONG, TokenType.ULONG,
                      TokenType.CONST, TokenType.VOLATILE, TokenType.SIGNED, TokenType.UNSIGNED):
            # Definitely a type, parse as type_spec
            try:
                target = self.type_spec()
                self.consume(TokenType.RIGHT_PAREN)
                return SizeOf(target).set_location(tok.line, tok.column)
            except ParseError:
                # If type parsing fails, try as expression
                self.position = saved_pos
                self.current_token = self.tokens[self.position]
                expr = self.expression()
                self.consume(TokenType.RIGHT_PAREN)
                return SizeOf(expr).set_location(tok.line, tok.column)
        else:
            # Could be identifier (variable) or custom type - try expression first
            try:
                expr = self.expression()
                self.consume(TokenType.RIGHT_PAREN)
                return SizeOf(expr).set_location(tok.line, tok.column)
            except ParseError:
                # If expression parsing fails, try as type spec
                self.position = saved_pos
                self.current_token = self.tokens[self.position]
                target = self.type_spec()
                self.consume(TokenType.RIGHT_PAREN)
                return SizeOf(target).set_location(tok.line, tok.column)

    def endianof_expression(self) -> EndianOf:
        tok = self.current_token
        self.consume(TokenType.ENDIANOF)
        self.consume(TokenType.LEFT_PAREN, "Expected '(' after endianof")

        saved_pos = self.position

        if self.expect(TokenType.SINT, TokenType.FLOAT_KW, TokenType.DOUBLE_KW, TokenType.CHAR,
                      TokenType.BOOL_KW, TokenType.DATA, TokenType.VOID,
                      TokenType.SLONG, TokenType.ULONG,
                      TokenType.CONST, TokenType.VOLATILE, TokenType.SIGNED, TokenType.UNSIGNED,
                      TokenType.IDENTIFIER):
            print("EndianOf encountered")
            try:
                target = self.type_spec()
                self.consume(TokenType.RIGHT_PAREN, "Expected ')' after expression in endianof")
                return EndianOf(target).set_location(tok.line, tok.column)
            except ParseError:
                self.position = saved_pos
                self.current_token = self.tokens[self.position]
                target = self.expression()
                self.consume(TokenType.RIGHT_PAREN)
                return EndianOf(target).set_location(tok.line, tok.column)

    def typeof_expression(self) -> TypeOf:
        """
        typeof_expression -> 'typeof' '(' (type_spec | expression) ')'
        """
        tok = self.current_token
        self.consume(TokenType.TYPEOF)
        self.consume(TokenType.LEFT_PAREN)

        saved_pos = self.position

        if self.expect(TokenType.SINT, TokenType.FLOAT_KW, TokenType.DOUBLE_KW, TokenType.CHAR,
                      TokenType.BOOL_KW, TokenType.DATA, TokenType.VOID,
                      TokenType.SLONG, TokenType.ULONG,
                      TokenType.CONST, TokenType.VOLATILE, TokenType.SIGNED, TokenType.UNSIGNED):
            try:
                target = self.type_spec()
                self.consume(TokenType.RIGHT_PAREN)
                return TypeOf(target).set_location(tok.line, tok.column)
            except ParseError:
                self.position = saved_pos
                self.current_token = self.tokens[self.position]
                expr = self.expression()
                self.consume(TokenType.RIGHT_PAREN)
                return TypeOf(expr).set_location(tok.line, tok.column)
        else:
            try:
                expr = self.expression()
                self.consume(TokenType.RIGHT_PAREN)
                return TypeOf(expr).set_location(tok.line, tok.column)
            except ParseError:
                self.position = saved_pos
                self.current_token = self.tokens[self.position]
                target = self.type_spec()
                self.consume(TokenType.RIGHT_PAREN)
                return TypeOf(target).set_location(tok.line, tok.column)

    def array_literal(self) -> Expression:
        """
        array_literal -> '[' (array_comprehension | expression (',' expression)*)? ']'
        array_comprehension -> expression 'for' '(' type_spec IDENTIFIER 'in' expression ')'
        """
        tok = self.current_token
        self.consume(TokenType.LEFT_BRACKET)
        
        if self.expect(TokenType.RIGHT_BRACKET):
            self.advance()
            return ArrayLiteral([]).set_location(tok.line, tok.column)  # Empty array literal
        
        # Parse first expression
        first_expr = self.expression()
        
        # Check if this is an array comprehension
        if self.expect(TokenType.FOR):
            #print("DOING ARRAY ArrayComprehension")
            # This is an array comprehension: [expr for (type var in iterable)]
            self.advance()  # consume 'for'
            self.consume(TokenType.LEFT_PAREN)
            
            # Parse variable type and name
            variable_type = self.type_spec()
            variable_name = self.consume(TokenType.IDENTIFIER).value
            
            self.consume(TokenType.IN)
            
            # Parse iterable expression
            iterable = self.expression()
            
            self.consume(TokenType.RIGHT_PAREN)
            self.consume(TokenType.RIGHT_BRACKET)
            
            return ArrayComprehension(
                expression=first_expr,
                variable=variable_name,
                variable_type=variable_type,
                iterable=iterable
            ).set_location(tok.line, tok.column)
        else:
            # Regular array literal: [expr, expr, ...]
            elements = [first_expr]
            
            while self.expect(TokenType.COMMA):
                self.advance()
                elements.append(self.expression())
            
            self.consume(TokenType.RIGHT_BRACKET)
            return ArrayLiteral(elements).set_location(tok.line, tok.column)  # Array literal
    
    def expression_block(self) -> Expression:
        """
        expression_block -> '{' expression '}'
        Used for acceptor blocks that contain a single expression with placeholders.
        """
        tok = self.current_token
        self.consume(TokenType.LEFT_BRACE)
        expr = self.expression()
        self.consume(TokenType.RIGHT_BRACE)
        return expr
    
    def struct_literal(self) -> StructLiteral:
        """
        struct_literal -> '{' (named_init | positional_init)? '}'
        named_init -> IDENTIFIER '=' expression (',' IDENTIFIER '=' expression)*
        positional_init -> expression (',' expression)*
        
        Returns StructLiteral AST node.
        Supports both:
            {a = 10, b = 20}  // Named fields
            {10, 20}          // Positional (field order from struct definition)
        """
        tok = self.current_token
        self.consume(TokenType.LEFT_BRACE)
        field_values = {}
        positional_values = []
        is_positional = False
        
        if not self.expect(TokenType.RIGHT_BRACE):
            # Look ahead to determine if this is named or positional
            # If we see IDENTIFIER followed by '=', it's named
            # Otherwise, it's positional
            if self.expect(TokenType.IDENTIFIER) and self.peek() and self.peek().type == TokenType.ASSIGN:
                # Named initialization
                is_positional = False
                name = self.consume(TokenType.IDENTIFIER).value
                self.consume(TokenType.ASSIGN)
                value = self.expression()
                field_values[name] = value
                
                while self.expect(TokenType.COMMA):
                    self.advance()
                    name = self.consume(TokenType.IDENTIFIER).value
                    self.consume(TokenType.ASSIGN)
                    value = self.expression()
                    field_values[name] = value
            else:
                # Positional initialization
                is_positional = True
                value = self.expression()
                positional_values.append(value)
                
                while self.expect(TokenType.COMMA):
                    self.advance()
                    value = self.expression()
                    positional_values.append(value)
        
        self.consume(TokenType.RIGHT_BRACE)
        
        # Return StructLiteral with either named or positional values
        if is_positional:
            return StructLiteral(field_values={}, positional_values=positional_values).set_location(tok.line, tok.column)
        else:
            return StructLiteral(field_values=field_values, positional_values=[]).set_location(tok.line, tok.column)

    def struct_body_item(self):
            if self.expect(TokenType.PUBLIC):
                self.advance()
                self.consume(TokenType.LEFT_BRACE)
                while not self.expect(TokenType.RIGHT_BRACE):
                    self.parse_object_body_item(methods, members, nested_objects, nested_structs, is_private=False)
                self.consume(TokenType.RIGHT_BRACE)
                self.consume(TokenType.SEMICOLON)
            elif self.expect(TokenType.PRIVATE):
                self.advance()
                self.consume(TokenType.LEFT_BRACE)
                while not self.expect(TokenType.RIGHT_BRACE):
                    self.parse_object_body_item(methods, members, nested_objects, nested_structs, is_private=True)
                self.consume(TokenType.RIGHT_BRACE)
                self.consume(TokenType.SEMICOLON)

    def auto_variable_declaration(self) -> VariableDeclaration:
        """
        auto_variable_declaration -> 'auto' IDENTIFIER '=' expression
        The type of the variable is inferred from the RHS expression by the codegen.
        A sentinel TypeSystem with storage_class=StorageClass.AUTO is used so that
        visit_VariableDeclaration in fcodegen.py can detect and handle type inference.
        """
        from ftypesys import StorageClass as _SC, DataType as _DT
        tok = self.current_token
        self.consume(TokenType.AUTO)
        name = self.consume(TokenType.IDENTIFIER).value
        self.consume(TokenType.ASSIGN)
        initial_value = self.expression()
        # Sentinel type spec: storage_class=AUTO signals deferred type inference
        auto_ts = TypeSystem(base_type=_DT.VOID, storage_class=_SC.AUTO)
        self.symbol_table.define(name, SymbolKind.VARIABLE, auto_ts)
        return VariableDeclaration(name, auto_ts, initial_value).set_location(tok.line, tok.column)

    def destructuring_assignment(self) -> DestructuringAssignment:
        """
        destructuring_assignment -> 'auto' '{' destructure_vars '}' '=' expression ('from' IDENTIFIER)?
        """
        tok = self.current_token
        self.consume(TokenType.AUTO)
        self.consume(TokenType.LEFT_BRACE)
        
        # Parse variables in destructuring pattern
        variables = []
        while not self.expect(TokenType.RIGHT_BRACE):
            if self.expect(TokenType.IDENTIFIER):
                name = self.consume(TokenType.IDENTIFIER).value
                if self.expect(TokenType.AS):
                    self.advance()
                    type_spec = self.type_spec()
                    variables.append((name, type_spec))
                else:
                    variables.append(name)
            
            if not self.expect(TokenType.RIGHT_BRACE):
                self.consume(TokenType.COMMA)
        
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.ASSIGN)
        source = self.expression()
        
        # Optional 'from' clause
        source_type = None
        if self.expect(TokenType.FROM):
            self.advance()
            source_type = Identifier(self.consume(TokenType.IDENTIFIER).value)
        
        is_explicit = any(isinstance(var, tuple) for var in variables)
        return DestructuringAssignment(variables, source, source_type, is_explicit).set_location(tok.line, tok.column)

# Add main function for testing
def main():
    """Main function for testing the parser"""
    if len(sys.argv) < 2:
        print("Usage: python3 parser3.py <file.fx> [-v] [-a]")
        sys.exit(1)
    
    filename = sys.argv[1]
    verbose = "-v" in sys.argv
    show_ast = "-a" in sys.argv
    
    try:
        with open(filename, 'r') as f:
            source = f.read()

        print("\n[PREPROCESSOR] Standard library / user-defined macros:\n")
        from fpreprocess import FXPreprocessor
        preprocessor = FXPreprocessor(filename)
        result = preprocessor.process()
        
        # Tokenize
        lexer = FluxLexer(result)
        tokens = lexer.tokenize()
        
        if verbose:
            print("Tokens:")
            for token in tokens:
                print(f"  {token}")
            print()
        
        # Parse
        parser = FluxParser(tokens, source_lines=result.splitlines(keepends=True))
        parser._line_map = preprocessor.line_map
        ast = parser.parse()
        
        if show_ast:
            print("AST:")
            print(ast)
        else:
            print("Parse successful!")
            print(f"Generated AST with {len(ast.statements)} top-level statements")
    
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        sys.exit(1)
    except ParseError as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()