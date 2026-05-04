#!/usr/bin/env python3
"""
Flux Language Server (flsp.py)
Diagnostics-only LSP server for the Flux language.

Requirements:
    pip install pygls lsprotocol

Usage:
    python flsp.py          # stdio mode (default, for editors)
    python flsp.py --tcp    # TCP mode on port 2087 (for debugging)

The server expects to be launched from the Flux repo root, or for
FLUXC_SRCDIR to be set so that fparser.py / flexer.py etc. are importable.

Editor config examples
----------------------
Neovim (init.lua):
    vim.lsp.start({
        name = "flux",
        cmd  = { "python3", "/path/to/flsp.py" },
        filetypes = { "flux" },
        root_dir = vim.fn.getcwd(),
    })

Helix (languages.toml):
    [[language]]
    name = "flux"
    language-servers = ["flux-lsp"]
    file-types = ["fx"]

    [language-server.flux-lsp]
    command = "python3"
    args    = ["/path/to/flsp.py"]
"""

import sys
import os
import logging
import traceback
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

# ---------------------------------------------------------------------------
# Make the Flux compiler modules importable
# ---------------------------------------------------------------------------
_FLUXC_SRCDIR = os.environ.get("FLUXC_SRCDIR", str(Path(__file__).parent.resolve()))
if _FLUXC_SRCDIR not in sys.path:
    sys.path.insert(0, _FLUXC_SRCDIR)

# ---------------------------------------------------------------------------
# pygls / lsprotocol imports
# ---------------------------------------------------------------------------
try:
    from pygls.server import LanguageServer
    from lsprotocol import types as lsp
except Exception as e:
    print(
        f"ERROR: Could not import pygls/lsprotocol: {e}\n"
        "Install them with:  pip install pygls lsprotocol",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Flux compiler imports
# ---------------------------------------------------------------------------
_flux_import_error: Optional[str] = None
try:
    from fparser import FluxParser, ParseError
    from fmacros import build_compiler_macros
except Exception as exc:
    _flux_import_error = (
        f"Could not import Flux compiler modules: {exc}\n"
        f"Make sure FLUXC_SRCDIR points to the Flux repo root, or run this\n"
        f"script from that directory.\n"
        f"FLUXC_SRCDIR = {_FLUXC_SRCDIR}"
    )

# ---------------------------------------------------------------------------
# Logging  (goes to stderr so it doesn't corrupt stdio LSP traffic)
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format="%(asctime)s [flux-lsp] %(levelname)s  %(message)s",
)
log = logging.getLogger("flux-lsp")

import builtins
_real_print = builtins.print
def _silent_print(*args, **kwargs):
    kwargs['file'] = sys.stderr
    _real_print(*args, **kwargs)
builtins.print = _silent_print

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------
SERVER_NAME    = "flux-lsp"
SERVER_VERSION = "1.0.0"

flux_server = LanguageServer(SERVER_NAME, SERVER_VERSION)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    path   = unquote(parsed.path)
    if sys.platform == "win32" and path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return path


def _make_range(line: int, col: int, end_col: Optional[int] = None) -> lsp.Range:
    """Convert 1-based line/col to a zero-based LSP Range."""
    ln = max(0, line - 1)
    sc = max(0, col  - 1)
    ec = (sc + 1) if end_col is None else max(sc + 1, end_col - 1)
    return lsp.Range(
        start=lsp.Position(line=ln, character=sc),
        end  =lsp.Position(line=ln, character=ec),
    )


def _diag_from_parse_error(exc: "ParseError") -> lsp.Diagnostic:
    line = getattr(exc, 'display_line', None) or 1
    col  = getattr(exc, 'display_col',  None) or 1
    return lsp.Diagnostic(
        range    = _make_range(line, col),
        message  = str(exc),
        severity = lsp.DiagnosticSeverity.Error,
        source   = SERVER_NAME,
    )


def _parse_diagnostics(file_path: str) -> List[lsp.Diagnostic]:
    prev_cwd = os.getcwd()
    try:
        os.chdir(_FLUXC_SRCDIR)
        parser = FluxParser.from_file(file_path, compiler_macros=build_compiler_macros())
        parser.parse()
        return []
    except ParseError as exc:
        return [_diag_from_parse_error(exc)]
    except ValueError as exc:
        # parse() wraps ParseError in ValueError - unwrap __cause__ to get location.
        if isinstance(exc.__cause__, ParseError):
            cause = exc.__cause__
            log.debug("__cause__ token=%s display_line=%s display_col=%s str=%r",
                      getattr(cause, 'token', 'MISSING'),
                      getattr(cause, 'display_line', 'MISSING'),
                      getattr(cause, 'display_col', 'MISSING'),
                      str(cause))
            return [_diag_from_parse_error(cause)]
        log.debug("ValueError during validation:\n%s", traceback.format_exc())
        return [lsp.Diagnostic(
            range    = _make_range(1, 1),
            message  = str(exc),
            severity = lsp.DiagnosticSeverity.Error,
            source   = SERVER_NAME,
        )]
    except Exception as exc:
        log.debug("Unexpected error during validation:\n%s", traceback.format_exc())
        return [lsp.Diagnostic(
            range    = _make_range(1, 1),
            message  = f"Internal compiler error: {exc}",
            severity = lsp.DiagnosticSeverity.Error,
            source   = SERVER_NAME,
        )]
    finally:
        os.chdir(prev_cwd)


def _validate(ls: LanguageServer, uri: str) -> None:
    if _flux_import_error:
        ls.publish_diagnostics(uri, [lsp.Diagnostic(
            range    = _make_range(1, 1),
            message  = _flux_import_error,
            severity = lsp.DiagnosticSeverity.Error,
            source   = SERVER_NAME,
        )])
        return

    file_path = _uri_to_path(uri)
    log.debug("Validating %s", file_path)
    diags = _parse_diagnostics(file_path)
    ls.publish_diagnostics(uri, diags)
    log.debug("Published %d diagnostic(s) for %s", len(diags), file_path)


# ---------------------------------------------------------------------------
# LSP lifecycle
# ---------------------------------------------------------------------------

@flux_server.feature(lsp.INITIALIZE)
def on_initialize(ls: LanguageServer, params: lsp.InitializeParams):
    log.info("Flux LSP initializing (client: %s)", getattr(params, "client_info", "unknown"))
    if _flux_import_error:
        log.error(_flux_import_error)


@flux_server.feature(lsp.INITIALIZED)
def on_initialized(ls: LanguageServer, params: lsp.InitializedParams):
    log.info("Flux LSP ready.")


@flux_server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: lsp.DidOpenTextDocumentParams):
    _validate(ls, params.text_document.uri)


@flux_server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: LanguageServer, params: lsp.DidChangeTextDocumentParams):
    _validate(ls, params.text_document.uri)


@flux_server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: LanguageServer, params: lsp.DidSaveTextDocumentParams):
    _validate(ls, params.text_document.uri)


@flux_server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: LanguageServer, params: lsp.DidCloseTextDocumentParams):
    ls.publish_diagnostics(params.text_document.uri, [])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Flux Language Server")
    ap.add_argument("--tcp",  action="store_true", help="TCP mode on port 2087")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=2087)
    args = ap.parse_args()

    if args.tcp:
        log.info("Starting in TCP mode on %s:%d", args.host, args.port)
        flux_server.start_tcp(args.host, args.port)
    else:
        log.info("Starting in stdio mode")
        flux_server.start_io()


if __name__ == "__main__":
    main()