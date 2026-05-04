#!/usr/bin/env python3
"""
fmacros.py — Flux predefined macro table
=========================================
Single source of truth for the compiler_macros dict that is passed to
FXPreprocessor (via FluxParser.from_file).  Both fc.py and flsp.py import
this so the preprocessor always sees identical defines regardless of which
tool is driving the parse.

Public API
----------
    build_compiler_macros(module_triple: str | None = None,
                          cfg_platform:  str | None = None) -> dict[str, str]

If *module_triple* is omitted the function detects it from the running OS.
If *cfg_platform* is omitted it is read from flux_config.cfg.
"""

import platform as _platform
from typing import Dict, Optional

from fconfig import config as _cfg, get_byte_width as _get_byte_width


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_triple(sys_name: str) -> str:
    """Return a reasonable LLVM target triple for the current host."""
    if sys_name == "Windows":
        return "x86_64-pc-windows-msvc"
    if sys_name == "Darwin":
        import subprocess
        try:
            arch = subprocess.check_output(["uname", "-m"], text=True).strip()
            if arch == "arm64":
                return "arm64-apple-macosx11.0.0"
        except Exception:
            return "arm64-apple-macosx11.0.0"
        return "x86_64-apple-macosx10.15.0"
    return "x86_64-pc-linux-gnu"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_compiler_macros(
    module_triple: Optional[str] = None,
    cfg_platform:  Optional[str] = None,
) -> Dict[str, str]:
    """
    Build and return the predefined macro dict that must be passed to
    FluxParser.from_file(..., compiler_macros=...) so the preprocessor can
    resolve #import directives and #if / #ifdef blocks correctly.

    Parameters
    ----------
    module_triple:
        LLVM target triple string (e.g. "x86_64-pc-windows-msvc").
        Detected from the running OS when not supplied.
    cfg_platform:
        Value of the ``operating_system`` key from flux_config.cfg.
        Read from the live config when not supplied.
    """
    sys_name     = _platform.system()
    triple       = module_triple or _detect_triple(sys_name)
    cfg_platform = cfg_platform  or _cfg.get("operating_system", "")

    macros: Dict[str, str] = {
        # Compiler identification
        "__FLUX__":         "1",
        "__FLUX_MAJOR__":   "1",
        "__FLUX_MINOR__":   "0",
        "__FLUX_PATCH__":   "0",
        "__FLUX_VERSION__": "1",

        # LLVM backend
        "__LLVM__": "1",

        # Architecture (all off by default; enabled below)
        "__ARCH_X86__":   "0",
        "__ARCH_X86_64__":"0",
        "__ARCH_ARM__":   "0",
        "__ARCH_ARM64__": "0",
        "__ARCH_RISCV__": "0",

        # Platform (all off by default; enabled below)
        "__WINDOWS__": "0",
        "__LINUX__":   "0",
        "__MACOS__":   "0",
        "__POSIX__":   "0",

        # Feature detection
        "__LITTLE_ENDIAN__": "0",   # Switch if desired.
        "__BIG_ENDIAN__":    "1",   # Always big-endian.
        "__SIZEOF_PTR__":    "8",   # Assume 64-bit.
        "__SIZEOF_INT__":    "4",   # Always 32-bit.
        "__SIZEOF_LONG__":   "8",   # Always 64-bit.
        "__BYTE_WIDTH__":    str(_get_byte_width(_cfg)),

        # Compilation mode
        "__DEBUG__":    "1" if _cfg.get("debug", False)  else "0",
        "__RELEASE__":  "0" if _cfg.get("debug", True)   else "1",
        "__OPTIMIZE__": _cfg.get("optimization_level", "0"),
    }

    # ── Platform-specific flags ────────────────────────────────────────────
    if sys_name == "Windows":
        macros.update({
            "__WINDOWS__": "1",
            "__WIN32__":   "1",
            "__WIN64__":   "1" if "x86_64" in triple else "0",
        })
    elif sys_name == "Darwin":
        macros.update({
            "__MACOS__":  "1",
            "__APPLE__":  "1",
            "__MACH__":   "1",
            "__POSIX__":  "1",
        })
    elif cfg_platform == "DOS":
        macros.update({
            "__DOS__":    "1",
            "__MSDOS__":  "1",
            "__16BIT__":  "1",
            "__I86__":    "1",
            "__TINY__":   "1" if _cfg.get("dos_target") == "com"   else "0",
            "__SMALL__":  "1" if _cfg.get("dos_model")  == "small" else "0",
        })
    else:  # Linux / generic Unix
        macros.update({
            "__LINUX__":       "1",
            "__UNIX__":        "1",
            "__POSIX__":       "1",
            "__gnu_linux__":   "1",
        })

    # ── Architecture flags ─────────────────────────────────────────────────
    if "x86_64" in triple or "amd64" in triple:
        macros.update({
            "__ARCH_X86_64__": "1",
            "__x86_64__":      "1",
            "__amd64__":       "1",
        })
    elif "i386" in triple or "i686" in triple:
        macros.update({
            "__ARCH_X86__": "1",
            "__i386__":     "1",
            "__i686__":     "1",
        })
    elif "arm64" in triple or "aarch64" in triple:
        macros.update({
            "__ARCH_ARM64__": "1",
            "__arm64__":      "1",
            "__aarch64__":    "1",
        })

    return macros