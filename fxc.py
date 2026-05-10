#!/usr/bin/env python3
"""
Flux Compiler Entrypoint

Copyright (C) 2026 Karac Thweatt

Contributors:

    Piotr Maciej Bednarski
    reinitd <molliver@aurictradecollective.org>


USAGE:
    python fc.py filename.fx
    
    Includes the standard library into the available paths.
    
    Outputs to the same folder with filename.exe (or just filename on *nix systems)
    

This language is in active development. There are known and unknown issues.

Please report any issues to kvthweatt@gmail.com or create an issue on the GitHub page.
"""

import sys
import os
from pathlib import Path
#from fconfig import *

# Resolve compiler root: prefer FLUXC_SRCDIR env var, fall back to script location
FLUXC_SRCDIR = Path(os.environ.get("FLUXC_SRCDIR", Path(__file__).parent)).resolve()

# Write it back so fc.py and fconfig.py see the same root when they're imported
os.environ["FLUXC_SRCDIR"] = str(FLUXC_SRCDIR)

# Add src/compiler and src/stdlib to Python path
sys.path.insert(0, str(FLUXC_SRCDIR / "src" / "compiler"))
sys.path.insert(0, str(FLUXC_SRCDIR / "src" / "stdlib"))
sys.path.insert(0, str(FLUXC_SRCDIR / "src" / "stdlib" / "runtime"))
# Import compiler components
from fc import FluxCompiler # type: ignore
from fc import config

class TeeOutput:
    """Writes to both console and file simultaneously"""
    def __init__(self, console, file):
        self.console = console
        self.file = file
    
    def write(self, message):
        # Write to console first
        self.console.write(message)
        self.console.flush()
        # Then write to file
        self.file.write(message)
        self.file.flush()
    
    def flush(self):
        self.console.flush()
        self.file.flush()
    
    def isatty(self):
        """Return console's tty status for color detection"""
        return self.console.isatty() if hasattr(self.console, 'isatty') else False


def main():
    # Setup debug output redirection - ALWAYS ENABLED
    original_stdout = sys.stdout
    debug_file = None
    
    try:
        # Create build directory if it doesn't exist
        build_dir = FLUXC_SRCDIR / "build"
        build_dir.mkdir(exist_ok=True)
        
        # Open debug.txt for writing
        debug_path = build_dir / "debug.txt"
        debug_file = open(debug_path, 'w', encoding='utf-8', buffering=1)
        
        # Write confirmation to console before redirecting
        original_stdout.write(f"[DEBUG] Creating debug output file at: {debug_path.absolute()}\n")
        original_stdout.flush()
        
        # Redirect stdout to both console and file
        sys.stdout = TeeOutput(original_stdout, debug_file)
        
        # First line in debug file
        print(f"=== Flux Compiler Debug Log ===")
        print(f"Debug file location: {debug_path.absolute()}")
        print(f"Working directory: {FLUXC_SRCDIR}")
        print(f"Arguments: {' '.join(sys.argv)}")
        print("=" * 40)
        
        if len(sys.argv) < 2:
            print("Flux Language Compiler")
            print("Usage: python fxc.py <input.fx> [options]\n")
            print("Basic Options:")
            print("  -o <output>         Output binary name")
            print("  -v <level>          Legacy verbosity level (0-5)")
            print("  -dos                Compile for DOS (16-bit)")
            print("  -com                Create COM file instead of EXE (requires -dos)")
            print("  --library           Compile as static library instead of executable")
            print("  -lib <libs...>      Link extra libraries (e.g. -lib lib1.a lib2.a lib3.lib)")
            print("")
            print("LLVM Options:")
            print("  --march <arch>      Target architecture (e.g. x86-64, arm64, riscv64)")
            print("  --mcpu <cpu>        Target CPU (e.g. native, apple-m1, skylake)")
            print("  --mattr <attrs>     Target attributes (comma-separated, e.g. +avx2,+sse4.2)")
            print("")
            print("Advanced Logging Options:")
            print("  --log-level <n>     Logging level: 0=silent, 1=error, 2=warning, 3=info, 4=debug, 5=trace")
            print("  --log-file <path>   Write logs to file")
            print("  --log-timestamp     Include timestamps in log output")
            print("  --log-no-color      Disable colored output")
            print("  --log-filter <comp> Only show logs from specific components (comma-separated)")
            print("                      Examples: lexer,parser or compiler,build")
            print("")
            print("Environment Variables:")
            print("  FLUX_LOG_LEVEL      Set default log level (0-5)")
            print("  FLUX_LOG_FILE       Set default log file path")
            print("  FLUX_LOG_TIMESTAMP  Enable timestamps (1/true/yes)")
            print("  FLUX_LOG_NO_COLOR   Disable colors (1/true/yes)")
            print("  FLUX_LOG_COMPONENTS Filter components (comma-separated)")
            print("")
            print("Examples:")
            print("  python fxc.py hello.fx")
            print("  python fxc.py hello.fx -o hello --log-level 4")
            print("  python fxc.py hello.fx -dos -com        # Create DOS COM file")
            print("  python fxc.py hello.fx -dos -o hello.exe # Create DOS EXE file")
            print("  python fxc.py hello.fx --log-filter lexer,parser --log-timestamp")
            sys.exit(1)
    
        args = sys.argv[1:]  # Skip script name
        dos_mode = False
        com_mode = False
        input_file = None
        output_bin = None
        verbosity = None
        compile_as_library = False
        extra_libs = []
        logger_config = {}
        llc_config = {}
    
        i = 0
        while i < len(args):
            arg = args[i]
        
            # Check for flags
            if arg == "-dos":
                dos_mode = True
                i += 1
            elif arg == "-com":
                com_mode = True
                i += 1
            elif arg == "-v" and i + 1 < len(args):
                verbosity = int(args[i + 1])
                i += 2
            elif arg == "-o" and i + 1 < len(args):
                output_bin = args[i + 1]
                i += 2
            elif arg == "--library":
                compile_as_library = True
                i += 1
            elif arg == "-lib":
                # Consume all following args that look like library files
                i += 1
                while i < len(args) and not args[i].startswith('-'):
                    extra_libs.append(args[i])
                    i += 1
            elif arg == "--log-level" and i + 1 < len(args):
                logger_config['level'] = int(args[i + 1])
                i += 2
            elif arg == "--log-file" and i + 1 < len(args):
                logger_config['log_file'] = args[i + 1]
                i += 2
            elif arg == "--log-timestamp":
                logger_config['timestamp'] = True
                i += 1
            elif arg == "--log-no-color":
                logger_config['colors'] = False
                i += 1
            elif arg == "--log-filter" and i + 1 < len(args):
                components = [c.strip() for c in args[i + 1].split(',')]
                logger_config['component_filter'] = components
                i += 2
            elif arg == "--mcpu" and i + 1 < len(args):
                # TODO Implement in fc.py
                llc_config['mcpu'] = args[i + 1]
                i += 2
            elif arg == "--march" and i + 1 < len(args):
                # TODO Implement in fc.py
                llc_config['march'] = args[i + 1]
                i += 2
            elif arg == "--mattr" and i + 1 < len(args):
                # TODO Implement in fc.py
                llc_config['mattr'] = args[i + 1]
                i += 2
            else:
                # Positional argument - should be input file
                if input_file is None:
                    input_file = arg
                    # Fix Windows path if needed
                    if "\\" in input_file and "\\\\" not in input_file:
                        input_file = input_file.replace("\\", "\\")
                else:
                    print(f"Warning: Unexpected argument '{arg}'")
                i += 1
    
        # Validate arguments
        if com_mode and not dos_mode:
            print("Error: -com flag requires -dos flag", file=sys.stderr)
            sys.exit(1)
    
        # Create compiler instance with advanced logging
        try:
            # Pass the TeeOutput streams to the logger so it captures everything
            logger_config["output_stream"] = sys.stdout  # This is now our TeeOutput
            logger_config["error_stream"] = sys.stderr   # Keep stderr separate for errors
        
            compiler = FluxCompiler(verbosity=verbosity, llc_config=llc_config, **logger_config)
        
            # Show configuration if debug level or higher
            if logger_config.get('level', 0) >= 4:
                print(f"Flux Compiler Configuration:")
                print(f"  Input file: {input_file}")
                print(f"  Output: {output_bin or 'auto-detected'}")
                print(f"  Mode: {'Library' if compile_as_library else 'Executable'}")
                if dos_mode:
                    print(f"  Target: {'DOS COM' if com_mode else 'DOS EXE'}")
                print(f"  Log level: {logger_config.get('level', 'default')}")
                if logger_config.get('log_file'):
                    print(f"  Log file: {logger_config['log_file']}")
                if logger_config.get('component_filter'):
                    print(f"  Component filter: {', '.join(logger_config['component_filter'])}")
        
            binary_path = ""
        
            # Compile the file based on target
            if dos_mode:
                # Use DOS compilation method
                binary_path = compiler.compile_dos(input_file, output_bin, com_file=com_mode)
            elif config.get('target') == "bootloader":
                binary_path = compiler.compile_bootloader(input_file, output_bin)
            elif compile_as_library:
                binary_path = compiler.compile_library(input_file, output_bin)
            else:
                binary_path = compiler.compile_file(input_file, output_bin, extra_libs=extra_libs)
        
            # Final success message
            if logger_config.get('level', 0) < 3:
                if dos_mode:
                    mode = "COM" if com_mode else "EXE"
                    print(f"✓ DOS {mode} compilation successful: {binary_path}")
                else:
                    mode = "library" if compile_as_library else "executable"
                    print(f"✓ Compilation successful: {binary_path} ({mode})")
            
        except Exception as e:
            print(f"✗ Compilation failed: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            # Ensure cleanup even on unexpected exit
            try:
                # Comment out cleanup to preserve LLVM IR files for debugging
                # compiler.cleanup()
                pass
            except:
                pass

    finally:
        # Always restore stdout and close debug file
        sys.stdout = original_stdout
        if debug_file:
            debug_file.close()
            original_stdout.write(f"[DEBUG] Debug output saved to: {debug_path.absolute()}\n")

if __name__ == "__main__":
    main()