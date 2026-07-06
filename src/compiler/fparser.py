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
    TokenType.XOR_OP:             '^^',
    TokenType.BITSHIFT_LEFT:      '<<',
    TokenType.BITSHIFT_RIGHT:     '>>',
    TokenType.BITNAND_OP:         '`!&',
    TokenType.BITNOR_OP:          '`!|',
    TokenType.BITXNAND:           '`^^!&',
    TokenType.BITXNOR:            '`^^!|',
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
}

_SYMBOL_MANGLE = {
    '%': 'pct',  '+': 'plus', '-': 'minus', '*': 'mul',
    '/': 'div',  '<': 'lt',   '>': 'gt',    '=': 'eq',
    '&': 'amp',  '|': 'pipe', '^': 'xor',   '!': 'not',
    '?': 'qst',  '@': 'at',   '~': 'tilde', '\\': 'bslash',
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
        self._template_instantiations = []  # concrete FunctionDef nodes to inject into program
        self._template_struct_instances = []      # concrete StructDefs to inject
        self._template_object_instances = []      # concrete ObjectDefs to inject
        self._parsed_objects = {}  # object_name -> ObjectDef AST node
        self._custom_operators: Dict[str, str] = {}  # symbol string -> base function name
        self._active_template_params: set = set()  # template param names in scope during current def/struct parse
        self._contracts: Dict[str, Block] = {}  # name -> Block of statements to inject
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
    def from_file(self, source_file: str, compiler_macros: Optional[Dict[str, str]] = None):
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
    
    def error(self, message: str, expected_type=None, prev_token=None, annotation: str = "") -> None:
        """Raise a parse error with current token context"""
        raise FluxParseError(message, self.current_token, self._source_lines, expected_type, prev_token, self._line_map, annotation)

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
        params = self.parameter_list()
        self.consume(TokenType.RIGHT_PAREN)

        self.consume(TokenType.LEFT_BRACKET)
        op_token_types = []
        op_token_values = []
        while not self.expect(TokenType.RIGHT_BRACKET):
            if self.current_token.type == TokenType.IDENTIFIER:
                op_token_types.append(TokenType.IDENTIFIER)
                op_token_values.append(self.current_token.value)
            elif self.current_token.type not in _TOKEN_SYMBOL_MAP:
                self.error(f"Token '{self.current_token.value}' cannot be part of an operator symbol", TokenType.IDENTIFIER)
            else:
                op_token_types.append(self.current_token.type)
                op_token_values.append(None)
            self.advance()
        self.consume(TokenType.RIGHT_BRACKET)

        symbol           = self._tokens_to_op_key(op_token_types, op_token_values)
        mangled_fragment = self._mangle_op_symbol(symbol)
        func_name        = f"operator__{mangled_fragment}"

        self.consume(TokenType.RETURN_ARROW)
        return_type = self.type_spec()

        # Pre-contracts: -> rtype : Contract1, Contract2 { ... }
        contract_stmts = []
        if self.expect(TokenType.COLON):
            self.advance()
            contract_name, call_args = self._parse_contract_ref()
            if contract_name not in self._contracts:
                self.error(f"Undefined contract '{contract_name}'")
            contract_stmts.extend(self._resolve_contract(contract_name, params, call_args))
            while self.expect(TokenType.COMMA):
                self.advance()
                contract_name, call_args = self._parse_contract_ref()
                if contract_name not in self._contracts:
                    self.error(f"Undefined contract '{contract_name}'")
                contract_stmts.extend(self._resolve_contract(contract_name, params, call_args))

        if self.expect(TokenType.SEMICOLON):
            self.advance()
            body = Block([])
            is_prototype = True
        else:
            body = self.block()
            if contract_stmts:
                body.statements = contract_stmts + body.statements
            # Post-contracts: } : Post1, Post2;
            post_contract_stmts = []
            if self.expect(TokenType.COLON):
                self.advance()
                post_name, post_call_args = self._parse_contract_ref()
                if post_name not in self._contracts:
                    self.error(f"Undefined post-contract '{post_name}'")
                post_contract_stmts.extend(self._resolve_contract(post_name, params, post_call_args))
                while self.expect(TokenType.COMMA):
                    self.advance()
                    post_name, post_call_args = self._parse_contract_ref()
                    if post_name not in self._contracts:
                        self.error(f"Undefined post-contract '{post_name}'")
                    post_contract_stmts.extend(self._resolve_contract(post_name, params, post_call_args))
            if post_contract_stmts:
                body = self._apply_post_contracts(body, return_type, post_contract_stmts)
            self.consume(TokenType.SEMICOLON)
            is_prototype = False

        # Only register truly novel symbols in _custom_operators.
        # Built-in operator symbols (those whose string matches an Operator enum value)
        # must NOT be added here, because custom_op_expression would then rewrite every
        # use of that operator into a FunctionCall regardless of operand types.
        # Built-in operator overloads are resolved at codegen time inside BinaryOp.codegen.
        from ftypesys import Operator as _Operator
        _builtin_op_values = {op.value for op in _Operator}
        if symbol in _builtin_op_values:
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

    def custom_op_expression(self) -> Expression:
        """
        custom_op_expression -> multiplicative_expression (custom_op multiplicative_expression)*
        """
        expr = self.multiplicative_expression()

        while True:
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
                elif stmt:
                    statements.append(stmt)
            except FluxParseError as e:
                raise
        # Append template instantiations after all other statements so that
        # namespace functions they depend on are registered before their bodies run.
        if self._template_struct_instances:
            statements = statements + self._template_struct_instances
        if self._template_object_instances:
            statements = statements + self._template_object_instances
        if self._template_instantiations:
            statements = statements + self._template_instantiations
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
            is_func = self.expect(TokenType.DEF) or self.expect(TokenType.INLINE) or self.current_token.type in _CALLING_CONV_TOKENS
            
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
        elif self.expect(TokenType.INLINE):
            return self.function_def()
        elif self.expect(TokenType.DEF):
            return self.function_def()
        elif self.current_token.type in _CALLING_CONV_TOKENS:
            return self.function_def()
        elif self.expect(TokenType.ENUM):
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
        elif self.is_variable_declaration():
            return self.variable_declaration_statement()
        elif self.expect(TokenType.UNSIGNED):
            return self.variable_declaration_statement()
        elif self.expect(TokenType.SIGNED):
            return self.variable_declaration_statement()
        elif self.expect(TokenType.SINT, TokenType.UINT, TokenType.DATA, TokenType.CHAR, TokenType.BYTE, 
                         TokenType.FLOAT_KW, TokenType.DOUBLE_KW, TokenType.BOOL_KW, TokenType.VOID,
                         TokenType.SLONG, TokenType.ULONG):
            return self.variable_declaration_statement()
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
                # Each declaration must be a function prototype
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
                    self.error("Expected function declaration inside extern block", TokenType.DEF)
            
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
            self.error("Expected '{' or 'def' after 'extern'", TokenType.LEFT_BRACE)
        
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
        contract_def -> 'contract' IDENTIFIER block ';'

        Parses a contract definition and registers its statement block in
        self._contracts so function_def() can inject it at parse time.
        ContractDef is returned so it appears in the top-level statement
        list (for diagnostics / future tooling); codegen ignores it.
        Supports multiple comma-separated contracts on one function:
            def foo(int x) -> int : NonZero, Positive { ... };
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
        body = self.block()
        self.consume(TokenType.SEMICOLON)
        self._contracts[name] = (params, body)
        return ContractDef(name, body, params).set_location(tok.line, tok.column)

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
        relations = []
        def _parse_id_list_cs():
            names = [self.consume(TokenType.IDENTIFIER).value]
            while self.expect(TokenType.LOGICAL_AND):
                self.advance()
                names.append(self.consume(TokenType.IDENTIFIER).value)
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
        while self.expect(TokenType.COMMA):
            self.advance()
            _parse_rel_expr()
        self.consume(TokenType.RIGHT_BRACE)
        self.consume(TokenType.SEMICOLON)
        self._constras[name] = (params, relations)
        return ConstraDef(name, params, relations).set_location(tok.line, tok.column)

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
        
        # Consume 'def' OR a calling-convention keyword (already consumed by caller when CC-prefixed)
        if self.current_token.type in _CALLING_CONV_TOKENS:
            # Calling convention keyword stands in place of 'def'
            calling_conv = _CALLING_CONV_TOKEN_TO_STR[self.current_token.type]
            self.advance()
        elif self.expect(TokenType.DEF):
            self.advance()
        else:
            self.error("Expected 'def' or calling convention keyword", TokenType.DEF)
        
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
            # Stored as a Stringify node; codegen evaluates it at compile time.
            tok = self.current_token
            self.advance()
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
        def _ts_repr_simple(ts):
            """Produce a readable source-like string for a TypeSystem (for constraint error messages)."""
            name = ts.custom_typename if ts.custom_typename else (ts.base_type.value if hasattr(ts.base_type, 'value') else str(ts.base_type))
            if ts.is_pointer:
                name += '*' * ts.pointer_depth
            if ts.is_array:
                name += '[]'
            return name
        template_params = []
        _func_constraints = {}  # param_name -> list of (TypeSystem, source_text)
        _func_relations = []    # list of (lhs_names, op: str, rhs_names)
        _func_defaults = {}     # param_name -> TypeSystem (the default type)
        _func_no_default = set()  # param_names marked <!+
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
                self.advance()  # consume '<'
                # Helper: parse one side of a relation: IDENTIFIER ('&' IDENTIFIER)*
                def _parse_id_list():
                    names = [self.consume(TokenType.IDENTIFIER).value]
                    while self.expect(TokenType.LOGICAL_AND):
                        self.advance()
                        names.append(self.consume(TokenType.IDENTIFIER).value)
                    return names
                # Helper: parse a ':{' ... '}' constraint set and collect relational constraints
                def _parse_constraint_set_fd():
                    self.consume(TokenType.COLON)
                    self.consume(TokenType.LEFT_BRACE)
                    # Parse one or more comma-separated entries: raw relation or named constra
                    def _parse_one_cs_entry():
                        # Peek: IDENTIFIER followed by '~', '!~', '&', or '(' -> constra ref or relation
                        _entry_tok = self.current_token
                        _entry_name = self.consume(TokenType.IDENTIFIER).value
                        if self.expect(TokenType.LEFT_PAREN):
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
                                _func_relations.append(
                                    ([mapping.get(n, n) for n in lhs_f], compat_f,
                                     [mapping.get(n, n) for n in rhs_f])
                                )
                        elif _entry_name in self._constras and not (
                                self.expect(TokenType.LOGICAL_AND) or
                                self._is_relconstraint_op()):
                            # Bare constra name - map template params in order of appearance
                            cs_params, cs_relations = self._constras[_entry_name]
                            # Collect template params seen so far (in declaration order)
                            ordered_tparams = [p for p in template_params]
                            if len(cs_params) != len(ordered_tparams):
                                self.current_token = _entry_tok
                                self.error(
                                    f"Named constraint set '{_entry_name}' has {len(cs_params)} "
                                    f"parameter(s) but the template has {len(ordered_tparams)} "
                                    f"parameter(s); use explicit arguments: '{_entry_name}(...)'"
                                )
                            mapping = dict(zip(cs_params, ordered_tparams))
                            for lhs_f, compat_f, rhs_f in cs_relations:
                                _func_relations.append(
                                    ([mapping.get(n, n) for n in lhs_f], compat_f,
                                     [mapping.get(n, n) for n in rhs_f])
                                )
                        else:
                            # Raw relation: lhs already started with _entry_name
                            lhs = [_entry_name]
                            while self.expect(TokenType.LOGICAL_AND):
                                self.advance()
                                lhs.append(self.consume(TokenType.IDENTIFIER).value)
                            op = self._consume_relconstraint_op()
                            rhs = _parse_id_list()
                            _func_relations.append((lhs, op, rhs))
                    _parse_one_cs_entry()
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        _parse_one_cs_entry()
                    self.consume(TokenType.RIGHT_BRACE)
                # Helper: parse a param entry with optional <!+ prefix and constraint with optional + default
                def _parse_param_entry(param_name):
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
                        _allowed.append((_ts, _src or _ts_repr_simple(_ts)))
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
                            _allowed.append((_ts, _src or _ts_repr_simple(_ts)))
                            if _is_default:
                                _default_ts = _ts
                        _func_constraints[param_name] = _allowed
                        if _saw_default:
                            if param_name in _func_no_default:
                                _saved_err_tok = self.current_token
                                if _default_tok is not None:
                                    self.current_token = _default_tok
                                self.error(
                                    f"Template parameter '{param_name}' is marked '!+' (no default) "
                                    f"but a default type was supplied with '+'"
                                )
                                self.current_token = _saved_err_tok
                            _func_defaults[param_name] = _default_ts
                    else:
                        template_params.append(param_name)
                # Parse first entry: ':{...}' constraint set, or identifier param entry
                if self.expect(TokenType.COLON):
                    _parse_constraint_set_fd()
                else:
                    _no_default_first = False
                    if self.expect(TokenType.NOT):
                        self.advance()
                        self.consume(TokenType.PLUS)
                        _no_default_first = True
                    if self.expect(TokenType.CODIFY):
                        _first_id = self._consume_codify()
                    else:
                        _first_id = self.consume(TokenType.IDENTIFIER).value
                    if _no_default_first:
                        _func_no_default.add(_first_id)
                    if self.expect(TokenType.LOGICAL_AND) or self._is_relconstraint_op():
                        self.error(
                            f"Relational template constraints must be wrapped in a constraint set as :{{T ~= U}}. "
                            f"Did you mean :{{{_first_id} ~= ...}}, or did you intend a type constraint {_first_id}: ?"
                        )
                    _parse_param_entry(_first_id)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    if self.expect(TokenType.COLON):
                        _parse_constraint_set_fd()
                    else:
                        _no_default_next = False
                        if self.expect(TokenType.NOT):
                            self.advance()
                            self.consume(TokenType.PLUS)
                            _no_default_next = True
                        if self.expect(TokenType.CODIFY):
                            _next_id = self._consume_codify()
                        else:
                            _next_id = self.consume(TokenType.IDENTIFIER).value
                        if _no_default_next:
                            _func_no_default.add(_next_id)
                        if self.expect(TokenType.LOGICAL_AND) or self._is_relconstraint_op():
                            self.error(
                                f"Relational template constraints must be wrapped in a constraint set: :{{T ~= U}}. "
                                f"Did you mean :{{{_next_id} ~= ...}}, or did you intend a type constraint {_next_id}: ?"
                            )
                        _parse_param_entry(_next_id)
                self.consume(TokenType.GREATER_THAN)

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

        # NOTE: _active_template_params intentionally stays set through the body parse
        # so that template struct usages inside the body (e.g. myStru<T> x;) are also
        # deferred correctly.  It is restored after the entire function is parsed.
        # Pattern: def foo() -> int, foo() -> bool, foo(int) -> void;
        if self.expect(TokenType.COMMA):
            # This is a multi-function prototype declaration
            prototypes = []

            # Detect variadic sentinel in first prototype's parameters
            _is_var = any(getattr(p, '_is_variadic_sentinel', False) for p in parameters)
            _real_params = [p for p in parameters if not getattr(p, '_is_variadic_sentinel', False)]
            
            # Add the first prototype
            prototypes.append(FunctionDef(name, _real_params, return_type, Block([]),
                                        is_const, is_volatile, True, no_mangle, _is_var, calling_conv,
                                        False, is_inline))
            
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

                _proto_is_var = any(getattr(p, '_is_variadic_sentinel', False) for p in proto_parameters)
                _proto_real = [p for p in proto_parameters if not getattr(p, '_is_variadic_sentinel', False)]

                # no_mangle applies to ALL functions in this comma-separated list
                _proto_fd = FunctionDef(proto_name, _proto_real, proto_return_type,
                                        Block([]), is_const, is_volatile, True, no_mangle, _proto_is_var, calling_conv,
                                        False, is_inline)
                if proto_template_params:
                    _proto_fd._is_trait_template_proto = True
                prototypes.append(_proto_fd)
            
            self.consume(TokenType.SEMICOLON)
            
            # Restore active template params - this early return bypasses the normal restore at end of function_def.
            _tmpl_scope_ctx.__exit__(None, None, None)
            # Return the list of prototypes
            return [fd.set_location(tok.line, tok.column) for fd in prototypes]
        # Resolve contract(s): def foo(int x) -> int : NonZero, LessThan(y,x) { ... }
        contract_stmts = []
        if self.expect(TokenType.COLON):
            self.advance()
            contract_name, call_args = self._parse_contract_ref()
            if contract_name not in self._contracts:
                self.error(f"Undefined contract '{contract_name}'")
            contract_stmts.extend(self._resolve_contract(contract_name, parameters, call_args))
            # Support multiple contracts: : NonZero, Positive
            while self.expect(TokenType.COMMA):
                self.advance()
                contract_name, call_args = self._parse_contract_ref()
                if contract_name not in self._contracts:
                    self.error(f"Undefined contract '{contract_name}'")
                contract_stmts.extend(self._resolve_contract(contract_name, parameters, call_args))

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
        
        if self.expect(TokenType.SEMICOLON):
            is_prototype = True
            self.advance()
            body = Block([])
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
            if self.expect(TokenType.COLON):
                self.advance()
                post_name, post_call_args = self._parse_contract_ref()
                if post_name not in self._contracts:
                    self.error(f"Undefined post-contract '{post_name}'")
                post_contract_stmts.extend(self._resolve_contract(post_name, parameters, post_call_args))
                while self.expect(TokenType.COMMA):
                    self.advance()
                    post_name, post_call_args = self._parse_contract_ref()
                    if post_name not in self._contracts:
                        self.error(f"Undefined post-contract '{post_name}'")
                    post_contract_stmts.extend(self._resolve_contract(post_name, parameters, post_call_args))
            if post_contract_stmts:
                body = self._apply_post_contracts(body, return_type, post_contract_stmts)
            self.consume(TokenType.SEMICOLON)
        
        # Restore the previous active template param set now that the entire function
        # (params, return type, and body) has been parsed.
        _tmpl_scope_ctx.__exit__(None, None, None)

        # If this is a template function, store it and return None (no immediate codegen)
        if template_params:
            func_def = FunctionDef(name, real_parameters, return_type, body, is_const,
                                   is_volatile, is_prototype, no_mangle, is_variadic, calling_conv,
                                   is_recursive, is_inline)
            if self._in_comptime > 0:
                func_def._is_comptime_only = True
            self._templates.register(name, 'function', template_params, func_def,
                                     constraints=_func_constraints or {},
                                     relational=_func_relations or [],
                                     defaults=_func_defaults or {},
                                     no_default=_func_no_default or set())
            # Comptime template functions must be returned so the VM codegen sees
            # the definition and compiles it into compiled_functions.
            if self._in_comptime > 0:
                return func_def
            return None

        return FunctionDef(name, real_parameters, return_type, body, is_const,
                          is_volatile, is_prototype, no_mangle, is_variadic, calling_conv,
                          is_recursive, is_inline).set_location(tok.line, tok.column)

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
        enum_def -> 'enum' IDENTIFIER (',' IDENTIFIER)* (';' | '{' enum_item (',' enum_item)* '}' ';')
        enum_item -> IDENTIFIER ('=' INTEGER)?
        """
        tok = self.current_token
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
                return [EnumDefStatement(EnumDef(n, {})).set_location(tok.line, tok.column) for n in names]
            return EnumDefStatement(EnumDef(name, {})).set_location(tok.line, tok.column)
        
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
        return EnumDefStatement(EnumDef(name, values)).set_location(tok.line, tok.column)


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
        self._macros[name] = node   # register so call sites can be recognised
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
        """
        tok = self.current_token
        self.consume(TokenType.TRAIT)
        name = self.consume(TokenType.IDENTIFIER).value
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
        return TraitDef(name, prototypes).set_location(tok.line, tok.column)

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
        self.consume(TokenType.SEMICOLON)
        return InterfaceDef(name, params, protocols).set_location(tok.line, tok.column)

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

        # Pre-register in _templates before parsing the body so that
        # type_spec() can resolve self-referential return types like Tensor<T>*
        # inside method signatures (e.g. def __expr() -> Tensor<T>*).
        # We store a sentinel now and overwrite with the real ObjectDef after.
        if template_params:
            _sentinel = ObjectDef(name, [], [], [], [], traits=traits, template_params=template_params)
            self._templates.register(name, 'object', template_params, _sentinel)

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
                        _obj_tmpl_keys_before = set(self._templates.all_of_kind('function').keys())
                        method = self.function_def()
                        if method is None:
                            # Template method: re-register under qualified ObjectName.methodname key
                            # and record a stub in methods so trait compliance can see the name.
                            _new_method_names = [k for k in self._templates.all_of_kind('function')
                                                 if k not in _obj_tmpl_keys_before]
                            for bare_name in _new_method_names:
                                qualified = f"{name}.{bare_name}"
                                self._templates.register_alias(qualified, bare_name)
                            bare_name = _new_method_names[-1] if _new_method_names else next(reversed(self._templates.all_of_kind('function')))
                            recovered = self._templates.lookup(bare_name).node
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
                    _obj_tmpl_keys_before = set(self._templates.all_of_kind('function').keys())
                    method = self.function_def()
                    if method is None:
                        # Template method: re-register under qualified ObjectName.methodname key
                        # and record a stub in methods so trait compliance can see the name.
                        _new_method_names = [k for k in self._templates.all_of_kind('function')
                                             if k not in _obj_tmpl_keys_before]
                        for bare_name in _new_method_names:
                            qualified = f"{name}.{bare_name}"
                            self._templates.register_alias(qualified, bare_name)
                        bare_name = _new_method_names[-1] if _new_method_names else next(reversed(self._templates.all_of_kind('function')))
                        recovered = self._templates.lookup(bare_name).node
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

        # __expr is mandatory on every fully-defined object (not prototypes).
        # Validate its signature if present; error if absent.
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

        obj_def = ObjectDef(name, methods, members, nested_objects, nested_structs, traits=traits, template_params=template_params, interfaces=interface_attachments)
        obj_def.base_objects = base_objects
        obj_def = obj_def.set_location(tok.line, tok.column)
        _obj_tmpl_scope_ctx.__exit__(None, None, None)
        if template_params:
            self._templates.register(name, 'object', template_params, obj_def)
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
            elif self.expect(TokenType.INLINE) or self.expect(TokenType.DEF) or self.current_token.type in _CALLING_CONV_TOKENS:
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
                    _ns_tmpl_keys_before = set(self._templates.all_of_kind('function').keys())
                    func = self.function_def()
                    # function_def() returns None for template functions (deferred instantiation).
                    if func is None:
                        # Register the template under its namespace-qualified names so that
                        # call-site lookup resolves correctly.
                        _new_bare_names = [k for k in self._templates.all_of_kind('function')
                                           if k not in _ns_tmpl_keys_before]
                        for bare_name in _new_bare_names:
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
                    # The template was registered under its bare name by struct_def.
                    # Also register it under the namespace-qualified forms so that
                    # type_spec() can find it when the caller writes XYZ::myStru2<int>.
                    if self._templates.all_of_kind('struct'):
                        bare_name = next(reversed(self._templates.all_of_kind('struct')))
                        # Register under  "NS__bare"  and  "NS::bare"  so both lookup
                        # styles hit the same template definition.
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
                    # Register under namespace-qualified names so type_spec() can find it.
                    if self._templates.all_of_kind('object'):
                        bare_name = next(reversed(self._templates.all_of_kind('object')))
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
                    if self._templates.all_of_kind('object'):
                        bare_name = next(reversed(self._templates.all_of_kind('object')))
                        ns_mangled = f"{current_namespace}__{bare_name}"
                        ns_scoped  = f"{current_namespace}::{bare_name}"
                        self._templates.register_alias(ns_mangled, bare_name)
                        self._templates.register_alias(ns_scoped,  bare_name)
                elif isinstance(obj_result, list):
                    objects.extend(obj_result)
                else:
                    objects.append(obj_result)
            elif self.expect(TokenType.ENUM):
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

        if base_type == DataType.DATA and custom_typename is None:
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
                    t.array_dimensions = t.array_dimensions + (array_dimensions or [])
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
            storage_class=storage_class
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
            self.error("Objects cannot be used as types in struct members.", TokenType.IDENTIFIER)
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
                             TokenType.STRUCT, TokenType.IDENTIFIER):
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
    def _type_func_receiver_type_spec(type_name: str, pointer_depth: int = 0) -> 'TypeSystem':
        """
        Build a TypeSystem for the implicit ``_`` parameter of a type
        function, given the canonical type-name string and pointer depth.
        pointer_depth > 0 means the receiver is a pointer (e.g. byte* receiver).
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
            if pointer_depth > 0:
                return TypeSystem(base_type=_BUILTIN_MAP[type_name],
                                  pointer_depth=pointer_depth, is_pointer=True)
            return TypeSystem(base_type=_BUILTIN_MAP[type_name])
        # Named struct/object type
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
        the body ``_`` is an implicit first parameter holding the receiver value.
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
        self.advance()  # consume receiver token

        # Consume any pointer stars after the base type: byte*.func(), int**.func()
        recv_pointer_depth = 0
        while self.expect(TokenType.MULTIPLY):
            recv_pointer_depth += 1
            self.advance()

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
        def _ts_repr_simple_tf(ts):
            name = ts.custom_typename if ts.custom_typename else (ts.base_type.value if hasattr(ts.base_type, 'value') else str(ts.base_type))
            if ts.is_pointer:
                name += '*' * ts.pointer_depth
            if ts.is_array:
                name += '[]'
            return name
        template_params = []
        _typefunc_constraints = {}  # param_name -> list of (TypeSystem, source_text)
        _typefunc_relations = []    # list of (lhs_names, op: str, rhs_names)
        _typefunc_defaults = {}     # param_name -> TypeSystem (the default type)
        _typefunc_no_default = set()  # param_names marked <!+
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
                self.advance()  # consume '<'
                def _parse_id_list_tf():
                    if self.expect(TokenType.CODIFY):
                        names = [self._consume_codify()]
                    else:
                        names = [self.consume(TokenType.IDENTIFIER).value]
                    while self.expect(TokenType.LOGICAL_AND):
                        self.advance()
                        if self.expect(TokenType.CODIFY):
                            names.append(self._consume_codify())
                        else:
                            names.append(self.consume(TokenType.IDENTIFIER).value)
                    return names
                # Helper: parse a ':{' ... '}' constraint set and collect relational constraints
                def _parse_constraint_set_tf():
                    self.consume(TokenType.COLON)
                    self.consume(TokenType.LEFT_BRACE)
                    def _parse_one_cs_entry_tf():
                        _entry_tok = self.current_token
                        if self.expect(TokenType.CODIFY):
                            _entry_name = self._consume_codify()
                            _entry_is_codify = True
                        else:
                            _entry_name = self.consume(TokenType.IDENTIFIER).value
                            _entry_is_codify = False
                        if not _entry_is_codify and self.expect(TokenType.LEFT_PAREN):
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
                                _typefunc_relations.append(
                                    ([mapping.get(n, n) for n in lhs_f], compat_f,
                                     [mapping.get(n, n) for n in rhs_f])
                                )
                        elif not _entry_is_codify and _entry_name in self._constras and not (
                                self.expect(TokenType.LOGICAL_AND) or
                                self._is_relconstraint_op()):
                            # Bare constra name - map template params in order of appearance
                            cs_params, cs_relations = self._constras[_entry_name]
                            ordered_tparams = [p for p in template_params]
                            if len(cs_params) != len(ordered_tparams):
                                self.current_token = _entry_tok
                                self.error(
                                    f"Named constraint set '{_entry_name}' has {len(cs_params)} "
                                    f"parameter(s) but the template has {len(ordered_tparams)} "
                                    f"parameter(s); use explicit arguments: '{_entry_name}(...)'"
                                )
                            mapping = dict(zip(cs_params, ordered_tparams))
                            for lhs_f, compat_f, rhs_f in cs_relations:
                                _typefunc_relations.append(
                                    ([mapping.get(n, n) for n in lhs_f], compat_f,
                                     [mapping.get(n, n) for n in rhs_f])
                                )
                        else:
                            # Raw relation
                            lhs = [_entry_name]
                            while self.expect(TokenType.LOGICAL_AND):
                                self.advance()
                                if self.expect(TokenType.CODIFY):
                                    lhs.append(self._consume_codify())
                                else:
                                    lhs.append(self.consume(TokenType.IDENTIFIER).value)
                            op = self._consume_relconstraint_op()
                            rhs = _parse_id_list_tf()
                            _typefunc_relations.append((lhs, op, rhs))
                    _parse_one_cs_entry_tf()
                    while self.expect(TokenType.COMMA):
                        self.advance()
                        _parse_one_cs_entry_tf()
                    self.consume(TokenType.RIGHT_BRACE)
                def _parse_param_entry_tf(param_name):
                    if self.expect(TokenType.COLON):
                        template_params.append(param_name)
                        self.advance()
                        _allowed = []
                        _default_ts = None
                        _saw_default = False
                        _default_tok = None
                        _is_default = self.expect(TokenType.PLUS)
                        if _is_default:
                            _default_tok = self.current_token
                            self.advance()
                            _saw_default = True
                        _src = '""' if self.expect(TokenType.STRING_LITERAL) else None
                        _ts = self.type_spec()
                        _allowed.append((_ts, _src or _ts_repr_simple_tf(_ts)))
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
                            _allowed.append((_ts, _src or _ts_repr_simple_tf(_ts)))
                            if _is_default:
                                _default_ts = _ts
                        _typefunc_constraints[param_name] = _allowed
                        if _saw_default:
                            if param_name in _typefunc_no_default:
                                _saved_err_tok = self.current_token
                                if _default_tok is not None:
                                    self.current_token = _default_tok
                                self.error(
                                    f"Template parameter '{param_name}' is marked '!+' (no default) "
                                    f"but a default type was supplied with '+'"
                                )
                                self.current_token = _saved_err_tok
                            _typefunc_defaults[param_name] = _default_ts
                    else:
                        template_params.append(param_name)
                # Parse first entry: ':{...}' constraint set, or identifier param entry
                if self.expect(TokenType.COLON):
                    _parse_constraint_set_tf()
                else:
                    _no_default_first = False
                    if self.expect(TokenType.NOT):
                        self.advance()
                        self.consume(TokenType.PLUS)
                        _no_default_first = True
                    if self.expect(TokenType.CODIFY):
                        _first_id = self._consume_codify()
                    else:
                        _first_id = self.consume(TokenType.IDENTIFIER).value
                    if _no_default_first:
                        _typefunc_no_default.add(_first_id)
                    if self.expect(TokenType.LOGICAL_AND, TokenType.TIE) or (self.expect(TokenType.NOT) and not self.expect(TokenType.COLON)):
                        self.error(
                            f"Relational template constraints must be wrapped in a constraint set :{{T ~ U}}. "
                            f"Did you mean :{{{_first_id} ~ ...}}, or did you intend a type constraint {_first_id}: ?"
                        )
                    _parse_param_entry_tf(_first_id)
                while self.expect(TokenType.COMMA):
                    self.advance()
                    if self.expect(TokenType.COLON):
                        _parse_constraint_set_tf()
                    else:
                        _no_default_next = False
                        if self.expect(TokenType.NOT):
                            self.advance()
                            self.consume(TokenType.PLUS)
                            _no_default_next = True
                        if self.expect(TokenType.CODIFY):
                            _next_id = self._consume_codify()
                        else:
                            _next_id = self.consume(TokenType.IDENTIFIER).value
                        if _no_default_next:
                            _typefunc_no_default.add(_next_id)
                        if self.expect(TokenType.LOGICAL_AND, TokenType.TIE) or (self.expect(TokenType.NOT) and not self.expect(TokenType.COLON)):
                            self.error(
                                f"Relational template constraints must be wrapped in a constraint set :{{T ~ U}}."
                                f"\nDid you mean :{{{_next_id} ~ ...}}, or did you intend a type constraint {_next_id}:"
                            )
                        _parse_param_entry_tf(_next_id)
                self.consume(TokenType.GREATER_THAN)

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

        receiver_ts = self._type_func_receiver_type_spec(type_name, recv_pointer_depth)
        if recv_is_tied:
            receiver_ts.is_tied = True

        # Derive the canonical type name used for mangling.
        # byte* and "" both map to 'string' so they share the same type func namespace.
        # A leading '~' marks a tied-type receiver, prefixed with 'tied_'.
        if recv_pointer_depth > 0 and type_name == 'byte':
            effective_type_name = 'string'
        elif recv_pointer_depth > 0:
            effective_type_name = type_name + '_ptr' * recv_pointer_depth
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
                self._templates.register(mangled_base, 'function', template_params, synthetic_fd,
                                         constraints=_typefunc_constraints or {},
                                         relational=_typefunc_relations or [],
                                         defaults=_typefunc_defaults or {},
                                         no_default=_typefunc_no_default or set())
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
            self._templates.register(mangled_base, 'function', template_params, synthetic_fd,
                                     constraints=_typefunc_constraints or {},
                                     relational=_typefunc_relations or [],
                                     defaults=_typefunc_defaults or {},
                                     no_default=_typefunc_no_default or set())
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
                    self.error("FROM syntax requires a custom type (struct)")
            elif self.expect(TokenType.ASSIGN):
                self.advance()
                init_expr = self.expression()

                # Sugar: if the type is a known object with exactly one __init param,
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
                else:
                    statements.append(stmt)
        
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
            if self.expect(TokenType.LEFT_BRACE):
                depth += 1
                parts.append('{')
            elif self.expect(TokenType.RIGHT_BRACE):
                depth -= 1
                if depth > 0:
                    parts.append('}')
                else:
                    # Matching close brace — advance past it and stop
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
    
    def if_statement(self) -> IfStatement:
        """
        if_statement -> 'if' '(' expression ')' block (('elif' | 'else' 'if') '(' expression ')' block)* ('else' block)? ';'
        """
        tok = self.current_token
        self.consume(TokenType.IF)
        self.consume(TokenType.LEFT_PAREN)
        condition = self.expression()
        self.consume(TokenType.RIGHT_PAREN)
        then_block = self.block()
        
        elif_blocks = []
        while self.expect(TokenType.ELIF) or (self.expect(TokenType.ELSE) and self.peek() and self.peek().type == TokenType.IF):
            if self.expect(TokenType.ELIF):
                self.advance()
            else:
                # Handle 'else if'
                self.advance()  # consume 'else'
                self.advance()  # consume 'if'
            
            self.consume(TokenType.LEFT_PAREN)
            elif_condition = self.expression()
            self.consume(TokenType.RIGHT_PAREN)
            elif_block = self.block()
            elif_blocks.append((elif_condition, elif_block))
        
        else_block = None
        if self.expect(TokenType.ELSE):
            self.advance()
            else_block = self.block()
        
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

        if is_for_in:
            # for-in loop
            variables = []
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
            
            return ForInLoop(variables, iterable, body).set_location(tok.line, tok.column)
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
    
    def break_statement(self) -> BreakStatement:
        """
        break_statement -> 'break' ';'
        """
        tok = self.current_token
        self.consume(TokenType.BREAK)
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

    def expression_statement(self) -> ExpressionStatement:
        """
        expression_statement -> expression ';'
        """
        tok = self.current_token
        expr = self.expression()
        self.consume(TokenType.SEMICOLON)
        return ExpressionStatement(expr).set_location(tok.line, tok.column)
    
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
                         TokenType.DIVIDE_ASSIGN, TokenType.MODULO_ASSIGN, TokenType.POWER_ASSIGN,
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
            
            if isinstance(expr, (FunctionCall, AcceptorBlock)):
                if isinstance(expr, FunctionCall):
                    expr.arguments.insert(0, right)
                    return expr
                else:  # AcceptorBlock
                    # For AcceptorBlock on left, we can't use old-style chaining
                    self.error("AcceptorBlock on left side requires labeled input syntax (N:func)")
            else:
                self.error("Chain arrow requires function call or acceptor block on left side")
        
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
        bitwise_xor_expression -> bitwise_and_expression (('`^^' | '`^^!|') bitwise_and_expression)*
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
        
        while self.expect(TokenType.MULTIPLY, TokenType.DIVIDE, TokenType.MODULO, TokenType.POWER):
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
        unary_expression -> ('is' 'not' | '-' | '+' | '*' | '@' | '++' | '--' | '`!' | '`^^!' | '`^^!&' | '`^^!|') unary_expression
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
            return self.postfix_expression()
    
    def _substitute_template(self, node, mapping):
        """
        Deep-copy an AST node, substituting every TypeSystem whose custom_typename
        (or base_type string) appears in `mapping` with the corresponding concrete TypeSystem.
        Also substitutes Identifier nodes whose name is a template param, for cases
        where a param name appears as an expression (e.g. sizeof-style use).
        """
        import copy

        def sub_type(ts):
            if not isinstance(ts, TypeSystem):
                return ts
            # Check if the whole type is a template param
            name = ts.custom_typename if ts.custom_typename else (
                ts.base_type if isinstance(ts.base_type, str) else None)
            if name and name in mapping:
                concrete = mapping[name]
                # Copy concrete and carry over pointer/array depth from the template usage
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
            # Deferred template struct/object application: "Name<T,U>" where T/U may now
            # be in the mapping.  Resolve it to the concrete mangled name.
            if name and '<' in name and '>' in name:
                bracket = name.index('<')
                struct_base = name[:bracket]
                raw_args = name[bracket + 1:-1].split(',')
                _sentry = self._templates.lookup(struct_base)
                if _sentry is not None and _sentry.kind == 'struct' and any(a in mapping for a in raw_args):
                    concrete_type_names = []
                    concrete_type_specs = []
                    for arg in raw_args:
                        arg = arg.strip()
                        if arg in mapping:
                            concrete_ts = mapping[arg]
                            concrete_type_names.append(self._type_system_to_mangle_str(concrete_ts))
                            concrete_type_specs.append(concrete_ts)
                        else:
                            # Arg is already a concrete name (e.g. another non-param type)
                            concrete_type_names.append(arg)
                            concrete_type_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=arg))
                    mangled = self._resolve_template_struct(struct_base, concrete_type_names, concrete_type_specs)
                    result = copy.copy(ts)
                    result.custom_typename = mangled
                    result.base_type = DataType.DATA
                    return result
                if _sentry is not None and _sentry.kind == 'object' and any(a in mapping for a in raw_args):
                    concrete_type_names = []
                    concrete_type_specs = []
                    for arg in raw_args:
                        arg = arg.strip()
                        if arg in mapping:
                            concrete_ts = mapping[arg]
                            concrete_type_names.append(self._type_system_to_mangle_str(concrete_ts))
                            concrete_type_specs.append(concrete_ts)
                        else:
                            concrete_type_names.append(arg)
                            concrete_type_specs.append(TypeSystem(base_type=DataType.DATA, custom_typename=arg))
                    mangled = self._resolve_template_object(struct_base, concrete_type_names, concrete_type_specs)
                    result = copy.copy(ts)
                    result.custom_typename = mangled
                    result.base_type = DataType.DATA
                    return result
            return copy.copy(ts)

        def walk(obj):
            if obj is None:
                return None
            if isinstance(obj, TypeSystem):
                return sub_type(obj)
            if isinstance(obj, list):
                return [walk(item) for item in obj]
            if isinstance(obj, dict):
                return {k: walk(v) for k, v in obj.items()}
            # Resolve deferred template struct refs stored as strings in
            # base_structs / post_structs: e.g. "A<T>" where T is in mapping.
            if isinstance(obj, str):
                if '<' in obj and '>' in obj and any(p in obj for p in mapping):
                    bracket = obj.index('<')
                    struct_base = obj[:bracket]
                    raw_args = obj[bracket + 1:-1].split(',')
                    _sentry = self._templates.lookup(struct_base)
                    if _sentry is not None and _sentry.kind == 'struct' and any(a.strip() in mapping for a in raw_args):
                        concrete_type_names = []
                        concrete_type_specs = []
                        for arg in raw_args:
                            arg = arg.strip()
                            if arg in mapping:
                                concrete_ts = mapping[arg]
                                concrete_type_names.append(self._type_system_to_mangle_str(concrete_ts))
                                concrete_type_specs.append(concrete_ts)
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
                # Handle "ObjName<T>.method" - substitute the type arg in the object name.
                _gt_pos = obj.name.index('>')
                if _gt_pos + 1 < len(obj.name) and obj.name[_gt_pos + 1] == '.':
                    _lt = obj.name.index('<')
                    _obj_base = obj.name[:_lt]
                    _raw_args = obj.name[_lt + 1:_gt_pos].split(',')
                    _method = obj.name[_gt_pos + 1:]  # e.g. '.__init'
                    _oentry = self._templates.lookup(_obj_base)
                    if _oentry is not None and _oentry.kind == 'object' and any(a.strip() in mapping for a in _raw_args):
                        _concrete_names = []
                        _concrete_specs = []
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
                        _new_obj.arguments = [walk(a) for a in obj.arguments]
                        return _new_obj
                bracket = obj.name.index('<')
                fn_base = obj.name[:bracket]
                raw_args = obj.name[bracket + 1:-1].split(',')
                _fentry = self._templates.lookup(fn_base)
                if _fentry is not None and _fentry.kind == 'function' and any(a.strip() in mapping for a in raw_args):
                    concrete_type_names = []
                    concrete_type_specs = []
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
                    new_obj.arguments = [walk(a) for a in obj.arguments]
                    return new_obj
                if _fentry is not None and _fentry.kind == 'object' and any(a.strip() in mapping for a in raw_args):
                    concrete_type_names = []
                    concrete_type_specs = []
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
                    new_obj.arguments = [walk(a) for a in obj.arguments]
                    return new_obj
            # It's a dataclass AST node - shallow copy then recurse into fields
            new_obj = copy.copy(obj)
            for field_name in obj.__dataclass_fields__:
                old_val = getattr(obj, field_name)
                setattr(new_obj, field_name, walk(old_val))
            return new_obj

        return walk(node)

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
        template_params = entry.params
        template_sd = entry.node
        if len(type_names) != len(template_params):
            self.error(
                f"Template struct '{struct_name}' expects {len(template_params)} "
                f"type argument(s), got {len(type_names)}"
            )
        mangled = struct_name + "__" + "_".join(type_names)
        if not self._templates.is_emitted(struct_name, mangled):
            self._templates.mark_emitted(struct_name, mangled)
            mapping = {}
            for param, tname, tspec in zip(
                    template_params, type_names,
                    type_specs or [None] * len(type_names)):
                if tspec is not None:
                    mapping[param] = tspec
                else:
                    mapping[param] = TypeSystem(
                        base_type=DataType.DATA, custom_typename=tname)
            concrete = self._substitute_template(template_sd, mapping)
            concrete.name = mangled
            concrete.template_params = []
            if getattr(template_sd, '_is_comptime_only', False):
                concrete._is_comptime_only = True
            if usage_tok is not None:
                for member in getattr(concrete, 'members', []):
                    member.set_location(usage_tok.line, usage_tok.column)
            self._template_struct_instances.append(concrete)
        return mangled

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
        template_params = entry.params
        template_od = entry.node
        if len(type_names) != len(template_params):
            self.error(
                f"Template object '{object_name}' expects {len(template_params)} "
                f"type argument(s), got {len(type_names)}"
            )
        mangled = object_name + "__" + "_".join(type_names)
        if not self._templates.is_emitted(object_name, mangled):
            self._templates.mark_emitted(object_name, mangled)
            mapping = {}
            for param, tname, tspec in zip(
                    template_params, type_names,
                    type_specs or [None] * len(type_names)):
                if tspec is not None:
                    mapping[param] = tspec
                else:
                    mapping[param] = TypeSystem(
                        base_type=DataType.DATA, custom_typename=tname)
            concrete = self._substitute_template(template_od, mapping)
            concrete.name = mangled
            concrete.template_params = []
            if usage_tok is not None:
                for member in getattr(concrete, 'members', []):
                    member.set_location(usage_tok.line, usage_tok.column)
            self._parsed_objects[mangled] = concrete
            self._object_init_params[mangled] = self._object_init_params.get(template_od.name, 0)
            self._template_object_instances.append(concrete)
        return mangled

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
                # Check if concrete_ts matches any allowed spec
                def _ts_matches(concrete, allowed):
                    """Return True if concrete TypeSystem matches the allowed TypeSystem."""
                    # Compare structural identity on the fields that define a type
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
                # allowed_specs is a list of (TypeSystem, source_text) tuples
                if not any(_ts_matches(concrete_ts, a_ts) for a_ts, _ in allowed_specs):
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
            def _types_compatible(a_ts, b_ts):
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
                            if not _types_compatible(lts, rts):
                                lmangle = self._type_system_to_mangle_str(lts)
                                rmangle = self._type_system_to_mangle_str(rts)
                                self.error(
                                    f"Relation constraint '{lname} ~= {rname}' violated: "
                                    f"'{lmangle}' and '{rmangle}' are not compatible "
                                    f"(pointer mismatch or width mismatch)"
                                )
                        elif op == "!~=":
                            if _types_compatible(lts, rts):
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
                                def _walk_tmpl(node):
                                    if node is None:
                                        return
                                    yield node
                                    for _attr in vars(node).values():
                                        if isinstance(_attr, list):
                                            for _item in _attr:
                                                if hasattr(_item, '__dataclass_fields__'):
                                                    yield from _walk_tmpl(_item)
                                        elif hasattr(_attr, '__dataclass_fields__'):
                                            yield from _walk_tmpl(_attr)
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
                                for _tn in _walk_tmpl(template_func):
                                    if isinstance(_tn, _TVarDecl) and _tn.type_spec:
                                        if _tn.type_spec.custom_typename in _addr_param_names:
                                            _tparam_vars[_tn.name] = _tn.type_spec.custom_typename
                                # Scan for AddressOf whose operand is one of those variables
                                from fast import AddressOf as _TAddressOf, Identifier as _TIdent
                                for _tn in _walk_tmpl(template_func):
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

            # Map DataType enum value strings back to DataType members
            _datatype_by_value = {dt.value: dt for dt in DataType}

            # Build the substitution mapping: param name -> concrete TypeSystem
            mapping = {}
            for i, (param_name, type_name) in enumerate(zip(template_params, arg_type_names)):
                # If a pre-resolved TypeSystem was supplied, use it directly.
                # This is the correct path for type aliases like u64 whose
                # resolution (bit_width, signedness, etc.) would otherwise be
                # lost when round-tripping through the mangle string.
                if arg_type_specs is not None and i < len(arg_type_specs):
                    mapping[param_name] = arg_type_specs[i]
                    continue
                # Fallback: try symbol table alias first
                resolved = self.symbol_table.get_type_spec(type_name)
                if resolved is not None:
                    mapping[param_name] = resolved
                elif type_name in _datatype_by_value:
                    # Primitive keyword type (sint, uint, float, char, bool, void, data)
                    mapping[param_name] = TypeSystem(
                        base_type=_datatype_by_value[type_name],
                        is_signed=_datatype_by_value[type_name] in (DataType.SINT, DataType.CHAR)
                    )
                else:
                    # Custom type name (object, struct) - use custom_typename
                    mapping[param_name] = TypeSystem(
                        base_type=DataType.DATA,
                        custom_typename=type_name
                    )

            # Deep-copy + substitute
            concrete_func = self._substitute_template(template_func, mapping)
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

                def _walk(node):
                    """Yield every node in the AST (depth-first)."""
                    if node is None:
                        return
                    yield node
                    for attr in vars(node).values():
                        if isinstance(attr, list):
                            for item in attr:
                                if hasattr(item, '__dataclass_fields__'):
                                    yield from _walk(item)
                        elif hasattr(attr, '__dataclass_fields__'):
                            yield from _walk(attr)

                def _bw(ts):
                    """Return bit width of a TypeSystem, 0 if unknown."""
                    if ts is None:
                        return 0
                    if ts.bit_width:
                        return ts.bit_width
                    from ftypesys import get_builtin_bit_width as _gbw
                    try:
                        return _gbw(ts.base_type)
                    except Exception:
                        return 0

                # Build a name -> TypeSystem table from the concrete function's
                # parameters and local variable declarations.  This is needed
                # because _resolved_type annotations are set by codegen, not by
                # the parser, so Identifier nodes in the substituted AST carry no
                # type at this point.
                from fast import VariableDeclaration as _VarDecl, Identifier as _Ident
                _local_type_table = {}
                for _p in concrete_func.parameters:
                    if _p.name is not None:
                        _local_type_table[_p.name] = _p.type_spec
                for _n in _walk(concrete_func):
                    if isinstance(_n, _VarDecl):
                        _local_type_table[_n.name] = _n.type_spec

                def _ts_of_expr(expr):
                    """Best-effort TypeSystem for an expression node."""
                    ts = getattr(expr, '_resolved_type', None)
                    if ts is not None:
                        return ts
                    # CastExpression / TypeConvertExpression carry their own target type
                    if isinstance(expr, (_CastExpr, _TypeConvExpr)):
                        return expr.target_type
                    # Identifier: look up in the local type table built above
                    if isinstance(expr, _Ident):
                        return _local_type_table.get(expr.name)
                    # Literal: build a minimal TypeSystem so e.g. 5 in '5 + x' resolves to int
                    if isinstance(expr, _Literal):
                        return TypeSystem(base_type=expr.type,
                                          is_signed=expr.type in (DataType.SINT, DataType.SLONG,
                                                                   DataType.CHAR, DataType.FLOAT,
                                                                   DataType.DOUBLE))
                    return None

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

                    for _node in _walk(concrete_func):
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
                    self._template_instantiations.append(concrete_func)
            else:
                self._template_instantiations.append(concrete_func)

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
        _template_instantiations so codegen can find it by normal overload resolution
        inside visit_BinaryOp.  The BinaryOp AST node is left unchanged.
        """
        entry = self._templates.lookup(op_symbol)
        if entry is None or entry.kind != 'operator':
            return
        template_params = entry.params
        template_func = entry.node
        if len(template_params) != len(arg_type_specs):
            return  # Arity mismatch - cannot instantiate

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
            if not any(_is_non_builtin(ts) for ts in arg_type_specs):
                return  # All-primitive instantiation - skip to avoid overriding builtins

        # Build a stable mangle key so each unique pair of concrete types is only
        # instantiated once.
        type_names = [self._type_system_to_mangle_str(ts) for ts in arg_type_specs]
        mangle_key = template_func.name + '__tmpl__' + '__'.join(type_names)

        if self._templates.is_emitted(op_symbol, mangle_key):
            return
        self._templates.mark_emitted(op_symbol, mangle_key)

        # Build the substitution mapping: template param name -> concrete TypeSystem
        mapping = {pname: ts for pname, ts in zip(template_params, arg_type_specs)}

        concrete_func = self._substitute_template(template_func, mapping)
        # Keep the original mangled function name (e.g. operator__plus); the
        # LLVM-level overload uniqueness comes from distinct parameter types.
        concrete_func.name = template_func.name
        concrete_func.no_mangle = False
        self._template_instantiations.append(concrete_func)

    def _infer_type_from_expr(self, expr) -> 'TypeSystem | None':
        """
        Best-effort parse-time type inference for a BinaryOp operand.
        Returns a TypeSystem if the type can be determined, else None.
        """
        from fast import Identifier, Literal, BinaryOp as _BinaryOp
        if isinstance(expr, Identifier):
            return self.symbol_table.get_type_spec(expr.name)
        if isinstance(expr, Literal):
            _dt_map = {
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
            return _dt_map.get(expr.type)
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
            template_func = _entry_6487.node

            # Build a mapping from template-param-name -> inferred TypeSystem by
            # walking each declared parameter and matching its template param name
            # against the corresponding call-site argument.
            inferred: dict = {}  # template param name -> TypeSystem
            _arg_pos: dict = {}  # template param name -> (line, col) of call-site arg

            for i, decl_param in enumerate(template_func.parameters):
                if i >= len(args):
                    break
                param_ts = decl_param.type_spec
                if param_ts is None:
                    continue
                # The declared parameter type names a template param when its
                
                # The declared parameter type names a template param directly when
                # its custom_typename appears in template_param_names (e.g. param type is T).
                # It may also be a deferred template-struct token like "Tensor<T>" or
                # "standard__tensors__Tensor<T>" - in that case extract the inner type
                # args and match them against template_param_names instead.
                param_tname = (
                    param_ts.custom_typename if param_ts.custom_typename
                    else (param_ts.base_type if isinstance(param_ts.base_type, str) else None)
                )

                # Resolve deferred template-struct param: "StructName<T>" -> param_tname = "T"
                # Builds a mapping: template_param_name -> position-in-arg-type so we can
                # extract the concrete type from the call-site argument's declared type.
                struct_param_map = {}  # template_param_name -> inner arg index
                if param_tname and "<" in param_tname and ">" in param_tname:
                    bracket = param_tname.index("<")
                    inner_args = [a.strip() for a in param_tname[bracket+1:-1].split(",")]
                    for idx2, inner in enumerate(inner_args):
                        if inner in template_param_names:
                            struct_param_map[inner] = idx2
                    # Reset param_tname - the declared param is a struct, not a bare T.
                    # We will infer via struct_param_map below.
                    param_tname = None

                if param_tname is not None and param_tname not in template_param_names:
                    continue  # This param's type is concrete - no inference needed here.

                # Try to derive the concrete TypeSystem from the call-site argument.
                arg = args[i]
                inferred_ts = None

                # Unwrap address-of (@x) to get the underlying identifier for type lookup.
                _arg_for_lookup = arg
                if (isinstance(arg, AddressOf)
                        and isinstance(getattr(arg, 'expression', None), Identifier)):
                    _arg_for_lookup = arg.expression
                if isinstance(_arg_for_lookup, Identifier):
                    arg = _arg_for_lookup
                if isinstance(arg, Identifier):
                    # Look up the variable\'s declared type in the symbol table.
                    arg_ts = self.symbol_table.get_type_spec(arg.name)
                    if arg_ts is not None:
                        if struct_param_map and arg_ts.custom_typename:
                            # The argument is a template struct/object instance: e.g. Tensor__float*.
                            # Recover which concrete type was substituted for each inner
                            # template param by looking up the mangled name's template record.
                            arg_ctn = arg_ts.custom_typename
                            # Search template structs and objects in the unified registry.
                            _struct_obj_entries = {**self._templates.all_of_kind('struct'),
                                                   **self._templates.all_of_kind('object')}
                            _tmpl_registries = [_struct_obj_entries]
                            for _registry in _tmpl_registries:
                                _found = False
                                for tmpl_name, _te in _registry.items():
                                    tmpl_params = _te.params
                                    sep = tmpl_name + "__"
                                    if arg_ctn.startswith(sep) or arg_ctn == tmpl_name:
                                        suffix = arg_ctn[len(sep):]
                                        concrete_args = suffix.split("__") if suffix else []
                                        for tparam, pos in struct_param_map.items():
                                            if pos < len(concrete_args):
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
                                        _found = True
                                        break
                                if _found:
                                    break
                        elif param_tname is not None:
                            inferred_ts = arg_ts
                elif isinstance(arg, Literal):
                    # Map the Literal's DataType to a minimal TypeSystem.
                    _dt_map = {
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
                    inferred_ts = _dt_map.get(arg.type)
                elif isinstance(arg, StringLiteral):
                    # A string literal is a byte* (pointer to i8).
                    inferred_ts = TypeSystem(base_type=DataType.BYTE, is_signed=True,
                                            bit_width=8, is_pointer=True, pointer_depth=1)

                if inferred_ts is not None and param_tname is not None:
                    if param_tname in inferred:
                        # A previous argument already fixed this param - check consistency.
                        prev_ts = inferred[param_tname]
                        prev_name = self._type_system_to_mangle_str(prev_ts)
                        new_name  = self._type_system_to_mangle_str(inferred_ts)
                        if prev_name != new_name:
                            _saved_tok2 = self.current_token
                            self.current_token = tok
                            self.error(
                                f"Template parameter '{param_tname}' of '{expr.name}' cannot be "
                                f"inferred: argument types conflict ('{prev_name}' vs '{new_name}')"
                            )
                            self.current_token = _saved_tok2
                    else:
                        inferred[param_tname] = inferred_ts
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
            if len(inferred) == len(template_param_names):
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
                    mangled = self._resolve_template_call(expr.name, type_names, type_specs,
                                                          arg_positions=_positions)
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
                # Array access or array slice [start:end]
                tok = self.current_token
                self.advance()
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
                    expr = ArrayAccess(expr, start_index).set_location(tok.line, tok.column)
            elif self.expect(TokenType.LEFT_PAREN):
                # Function call
                tok = self.current_token
                self.advance()
                args = []
                if not self.expect(TokenType.RIGHT_PAREN):
                    args = self.argument_list()
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
                        _tmpl_fd = _tfk_entry.node
                        _inferred = {}
                        _decl_params = _tmpl_fd.parameters[1:]  # skip implicit '_'
                        for _i, _dp in enumerate(_decl_params):
                            if _i >= len(args):
                                break
                            _pts = _dp.type_spec
                            _ptn = (_pts.custom_typename if _pts and _pts.custom_typename
                                    else (str(_pts.base_type) if _pts else None))
                            if _ptn not in _tmpl_params:
                                continue
                            _arg = args[_i]
                            if isinstance(_arg, Identifier):
                                _its = self.symbol_table.get_type_spec(_arg.name)
                                if _its is not None:
                                    _inferred[_ptn] = _its
                            elif isinstance(_arg, Literal):
                                _dtm = {
                                    DataType.SINT:   TypeSystem(base_type=DataType.SINT,  is_signed=True),
                                    DataType.UINT:   TypeSystem(base_type=DataType.UINT),
                                    DataType.SLONG:  TypeSystem(base_type=DataType.SLONG, is_signed=True),
                                    DataType.ULONG:  TypeSystem(base_type=DataType.ULONG),
                                    DataType.FLOAT:  TypeSystem(base_type=DataType.FLOAT),
                                    DataType.DOUBLE: TypeSystem(base_type=DataType.DOUBLE),
                                    DataType.BYTE:   TypeSystem(base_type=DataType.BYTE),
                                    DataType.BOOL:   TypeSystem(base_type=DataType.BOOL),
                                    DataType.CHAR:   TypeSystem(base_type=DataType.CHAR,  is_signed=True),
                                }
                                _its = _dtm.get(_arg.type)
                                if _its is not None:
                                    _inferred[_ptn] = _its
                            elif isinstance(_arg, StringLiteral):
                                # A string literal is byte* (pointer to i8).
                                _inferred[_ptn] = TypeSystem(base_type=DataType.BYTE, is_signed=True,
                                                             bit_width=8, is_pointer=True, pointer_depth=1)
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
            else:
                break
        
        return expr
    
    def argument_list(self) -> List[Expression]:
        """
        argument_list -> expression (',' expression)*
        """
        args = [self.expression()]
        
        while self.expect(TokenType.COMMA):
            self.advance()
            args.append(self.expression())
        
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
            value = float(tok.value)
            self.advance()
            return Literal(value, DataType.SLONG).set_location(tok.line, tok.column)
        elif self.expect(TokenType.ULONG_LITERAL):
            tok = self.current_token
            value = float(tok.value)
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
            # A quoted char literal ('a') has tok.value as the literal character itself.
            # A numeric char literal (97c) has tok.value as a digit string from the lexer's
            # suffix handling -- convert it to an int so normalize_char_value doesn't take
            # ord() of the first digit by mistake.
            if tok.value.isdigit():
                value = int(tok.value)
            else:
                value = tok.value
            self.advance()
            return Literal(value, DataType.CHAR).set_location(tok.line, tok.column)
        elif self.expect(TokenType.BYTE_LITERAL):
            tok = self.current_token
            value = int(tok.value)
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
            tok = self.current_token
            self.advance()
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