#!/usr/bin/env python3
"""
Flux Compiler with Full Toolchain Integration

Copyright (C) 2025 Karac Thweatt

Contributors:

    Piotr Bednarski
"""

import sys, os, subprocess
from pathlib import Path
from llvmlite import ir
from fparser import FluxParser, ParseError
from fast import *
from fcodegen import visitor as _codegen_visitor
from flogger import FluxLogger, FluxLoggerConfig, LogLevel
from fconfig import *
from fmacros import build_compiler_macros

# Resolve compiler root: prefer FLUXC_SRCDIR env var, fall back to script location
FLUXC_SRCDIR = Path(os.environ.get("FLUXC_SRCDIR", Path(__file__).parent)).resolve()

def get_debug_level(level: str):
    match(level):
        case ("none"):
            return 0
        case ("lexer"):
            return 1
        case ("parser"):
            return 2
        case ("ast"):
            return 3
        case ("compiler"):
            return 4
        case ("linker"):
            return 5
        case ("codegen"):
            return 6
        case ("trace"):
            return 7
        case ("everything"):
            return 8
        case _:
            return 0

def set_debug_level():
    tmp_debug_levels = []
    debug_level = config['debug_level']
    debug_level = debug_level.split(" | ")
    if len(debug_level) == 1:
        debug_level = debug_level[0]
        return [get_debug_level(debug_level)]
        return
    for level in debug_level:
        tmp_debug_levels.append(get_debug_level(level))
    return tmp_debug_levels


def debugger(debug_levels: list, target_levels: list, args: list):
    for level in target_levels:
        if level in debug_levels:
            try:
                print("START DEBUG")
                print('\n'.join(args))
                print("END DEBUG")
            except:
                print("START DEBUG")
                print(args)
                print("END DEBUG")
            continue


def resolve_llvm_tool(tool_name: str) -> str:
    """
    Resolve the full path to an LLVM tool on Windows.

    Resolution order:
      1. llvm_path from flux_config.cfg  (e.g. D:\\LLVM\\bin)
      2. PATH lookup via `where`
      3. Hard-coded default  C:\\Program Files\\LLVM\\bin

    Args:
        tool_name: bare executable name without extension, e.g. "lld-link" or "llc"

    Returns:
        Full path string to the .exe, e.g. "D:\\LLVM\\bin\\lld-link.exe"

    Raises:
        FileNotFoundError: if the tool cannot be found by any method
    """
    if tool_name is None or str(tool_name).lower() == "none":
        tool_name = "llc"
        
    exe = tool_name + ".exe"

    # 1. Explicit path from config
    cfg_llvm = config.get('llvm_path', '').strip()
    if cfg_llvm:
        candidate = Path(cfg_llvm) / exe
        if candidate.exists():
            return str(candidate)

    # 2. PATH lookup (works even if llvm_path is not set)
    try:
        result = subprocess.run(
            ["where", tool_name],
            check=True, capture_output=True, text=True
        )
        # `where` may return multiple lines; take the first hit
        found = result.stdout.strip().splitlines()[0].strip()
        if found:
            return found
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 3. Hard-coded fallback
    fallback = Path(r"C:\Program Files\LLVM\bin") / exe
    if fallback.exists():
        return str(fallback)

    raise FileNotFoundError(
        f"Cannot find '{exe}'. "
        f"Set 'llvm_path' in flux_config.cfg to your LLVM bin directory "
        f"(e.g. llvm_path = D:\\LLVM\\bin), or add LLVM to your PATH."
    )


class FluxCompiler:
    def __init__(self, /, 
                 verbosity: int = None, 
                 logger: FluxLogger = None,
                 llc_config: dict = None,
                 **logger_kwargs):
        """
        Initialize the Flux compiler with configurable logging
        
        Args:
            verbosity: Legacy verbosity level (0-5) - maps to new logging system
            logger: Custom FluxLogger instance (overrides verbosity)
            **logger_kwargs: Additional arguments for FluxLogger creation
        """
        # Initialize logger
        self.debug_levels = set_debug_level()
        logger_kwargs['level'] = min(verbosity if verbosity is not None else logger_kwargs.get('level', 3), 5)
        self.logger = FluxLoggerConfig.create_logger(**logger_kwargs)

        self.llc_config = llc_config or {}
        self.temp_files = []
        
        # Store legacy verbosity for backward compatibility
        self.verbosity = verbosity
        
        self.module = ir.Module(name="flux_module")
        import platform
        self.platform = platform.system()
        
        # Initialize predefined_macros as empty dict
        self.predefined_macros = {}
        
        # Store config platform for DOS detection
        self.cfg_platform = config.get('operating_system', '')

        if config.get('target') == "bootloader":
            # intentionally break this for the else coming after this.
            self.platform = None
            # heheh yeah qemu time
            self.module_triple = "i386-unknown-none-code16"
            self.module.triple = self.module_triple
            # 16-bit data layout
            self.module.data_layout = "e-m:e-p:16:16-i64:32-f80:32-n8:16-a:0:16-S16"
        else:
            # Configure platform-specific settings
            if self.platform == "Windows":
                self.module_triple = "x86_64-pc-windows-msvc"
                self.module.triple = self.module_triple
                # Set proper Windows data layout for x86_64
                self.module.data_layout = "e-m:w-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
            elif self.platform == "Darwin":  # macOS
                # Detect macOS architecture
                try:
                    arch = subprocess.check_output(["uname", "-m"], text=True).strip()
                    if arch == "arm64":
                        self.module_triple = "arm64-apple-macosx11.0.0"
                        self.module.triple = self.module_triple
                        self.module.data_layout = "e-m:o-i64:64-i128:128-n32:64-S128"
                        return
                    else:
                        self.module_triple = "x86_64-apple-macosx10.15.0"
                        self.module.triple = self.module_triple
                        self.module.data_layout = "e-m:o-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
                        return
                except:
                    self.module_triple = "arm64-apple-macosx11.0.0"  # Default to ARM64
                    self.module.triple = self.module_triple
                    self.module.data_layout = "e-m:o-i64:64-i128:128-n32:64-S128"
                    return
            else:  # Linux and others
                if self.cfg_platform == "DOS":
                    self.platform = "DOS"
                    # 16-bit real mode configuration
                    self.module_triple = "i386-unknown-none-code16"
                    self.module.triple = self.module_triple
                    self.module.data_layout = "e-m:e-p:16:16-i64:32-f80:32-n8:16:32:64-S16"
                    self.is_dos_target = True
                else:
                    self.module_triple = "x86_64-pc-linux-gnu"
                    self.module.triple = self.module_triple
                    self.module.data_layout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
            
        debugger(self.debug_levels, [4,5,6,7,8], [f"Target platform: {self.platform}",
                                              f"Module triple: {self.module_triple}"])

    def _get_llc_target_flags(self) -> list:
        """
        Build command-line flags for llc from llc_config, falling back to
        flux_config.cfg values when the CLI didn't supply them.

        CLI flags take precedence over config file values. Returns an
        empty list if nothing is set, so llc uses its own defaults. 
        """
        flags = []

        # --march
        march = self.llc_config.get('march') or config.get('architecture', '').strip()
        if march and march.lower() != 'none':
            flags.append(f"-march={march}")
        
        # --mcpu
        mcpu = self.llc_config.get('mcpu') or config.get('cpu', '').strip()
        if mcpu and mcpu.lower() != 'none':
            flags.append(f"-mcpu={mcpu}")
        
        # --mattr
        mattr = self.llc_config.get('mattr')
        if mattr and mattr.lower() != 'none':
            flags.append(f"-mattr={mattr}")
        
        if flags:
            self.logger.debug(f"LLC target flags: {' '.join(flags)}", "compiler")
        
        return flags


    def compile_file(self, filename: str, output_bin: str = None, extra_libs: list = None) -> str:
        """
        Compile a Flux source file to executable binary
        
        Args:
            filename: Path to the .fx source file
            output_bin: Optional output binary name
            extra_libs: Optional list of extra library paths to link (e.g. ['lib1.a', 'lib2.a'])
            
        Returns:
            Path to the generated executable
        """
        extra_libs = extra_libs or []
        try:
            self.logger.section(f"Preprocessing Flux file: {filename}", LogLevel.INFO)
            self.predefined_macros = build_compiler_macros(
                module_triple=self.module_triple,
                cfg_platform=self.cfg_platform,
            )
            print("[COMPILER] Pre-defined / built in macros:\n")
            for key, value in self.predefined_macros.items():
                print("[COMPILER]", key, value)
            
            # NOTE: ADD DEBUG LEVEL IN COMPILER & CONFIG FOR PREPROCESSOR
            # WRAP IN DEBUGGER
            #print("[PREPROCESSOR] All Macros:")
            #for key, value in preprocessor.macros.items():
            #    print("[PREPROCESSOR]", key, value)
            # /WRAP
            #self.logger.step("[INFO] ► Reading source file", LogLevel.INFO, "compiler")
            parser = FluxParser.from_file(filename, compiler_macros=self.predefined_macros)
            ast = parser.parse()

            if parser.parse_errors:
                exit()

            # Attach the line map to the module so codegen can produce accurate
            # per-file error locations instead of global merged-source line numbers.
            self.module._flux_line_map = parser._line_map

            #print("*"*40)
            #print("==== PARSER GENERATED SYMBOL TABLE ====")
            #print(parser.symbol_table.scopes)
            #print("==== PARSER GENERATED SYMBOL TABLE ====")
            #print("*"*40)

            # CHECK FIRST
            #
            # LEFT OFF REPLACING LOG DEBUGGER WITH DEBUGGER FUNCTION
            # CONTINUE BELOW
            
            # Step 4: Code generation
            self.logger.step("LLVM IR code generation", LogLevel.INFO, "codegen")
            try:
                self.module = _codegen_visitor.compile(ast, self.module)
                llvm_ir = str(self.module)
                self.logger.debug(f"Generated LLVM IR ({len(llvm_ir)} chars)", "codegen")
                
                # Log LLVM IR if requested (legacy compatibility + new system)
                if self.verbosity == 2 or self.logger.level >= LogLevel.TRACE:
                    self.logger.log_data(LogLevel.TRACE, "Generated LLVM IR", llvm_ir, "codegen")
                    
            except Exception as e:
                #self.logger.error(f"Code generation failed: {e}", "codegen")
                raise

            source_path = Path(filename)
            base_name = source_path.stem
            
            # Step 5: Create build directory
            self.logger.step("Preparing build environment", LogLevel.DEBUG, "build")
            temp_dir = Path(f"build/{base_name}")
            temp_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Build directory: {temp_dir.absolute()}", "build")
            
            # Step 6: Generate LLVM IR file
            self.logger.step("Writing LLVM IR file", LogLevel.DEBUG, "build")
            ll_file = temp_dir / f"{base_name}.ll"
            try:
                with open(ll_file, 'w') as f:
                    f.write(llvm_ir)
                self.temp_files.append(ll_file)
                self.logger.debug(f"LLVM IR written to: {ll_file}", "build")
            except Exception as e:
                self.logger.error(f"Failed to write LLVM IR file: {e}", "build")
                raise
            
            # Step 7: Compile to object file (platform-specific)
            self.logger.step(f"Compiling to object file ({self.platform})", LogLevel.INFO, "compiler")

            # Check for default configuration
            compiler = config.get('compiler')
            if compiler == "none":
                raise RuntimeError("Compiler not set! Please set your compiler in config\\flux_config.cfg")

            if self.platform == "Darwin":  # macOS
                obj_file = temp_dir / f"{base_name}.o"
                compiler_path = subprocess.check_output(["which", compiler], text=True, stderr=subprocess.DEVNULL).strip()
                
                # Try llc first, fallback to clang if not available
                command_line = None
                match (compiler):
                    case "llc":
                        command_line = [
                            compiler_path,
                            "-O" + config['lto_optimization_level'],  # Aggressive optimization level
                            "-filetype=obj",                    # Direct object file output
                            "-mtriple=" + self.module_triple,   # Target triple
                            *self._get_llc_target_flags(),   # march/mcpu/mattr
                            #"-march=" + config['architecture'], # Architecture
                            #"-mcpu=" + config['cpu'],           # Target CPU
                            "-enable-misched",                  # Enable machine instruction scheduler
                            "-enable-tail-merge",               # Merge similar tail code
                            "-optimize-regalloc",               # Optimize register allocation
                            "-relocation-model=static",         # Static relocation (no PIC)
                            "-tail-dup-size=3",                 # Tail duplication threshold
                            "-tailcallopt",                     # Enable tail call optimization
                            "-x86-asm-syntax=intel",            # Intel syntax assembly
                            "-x86-use-base-pointer",            # Use base pointer
                            "-no-x86-call-frame-opt",           # Disable call frame optimization (smaller)
                            "-disable-verify",                  # Disable verification for speed
                            str(ll_file),
                            "-o",
                            str(obj_file)
                        ]
                    case "clang":
                        command_line = [
                            compiler_path,
                            "-c",
                            "-O3",
                            str(ll_file),
                            "-o",
                            str(obj_file)
                        ]
                
                success = False
                try:
                    result = subprocess.run(command_line, check=True, capture_output=True, text=True)
                    success = True
                except Exception as e:
                    self.logger.error(f"{compiler}: {e}", "compiler")
                
                if not success:
                    self.logger.error(f"{compiler} could not compile LLVM IR", "compiler")
                    raise RuntimeError("Compilation failed - no suitable compiler found")
                    
            elif self.platform == "Windows":
                obj_file = temp_dir / f"{base_name}.obj"
                
                # Use configuration to determine desired compiler.
                compiler = config.get('compiler')
                if not compiler or compiler.lower() == "none":
                    compiler = "llc"
                # Resolve full path to the compiler so non-default LLVM installs work.
                compiler_exe = resolve_llvm_tool(compiler)
                # TODO:
                # match (compiler):   case "clang", case "llc", etc...
                compiler_args = [
                    #"-O" + config['lto_optimization_level'],  # Aggressive optimization level
                    "-filetype=obj",                    # Direct object file output
                    "-mtriple=" + self.module_triple,   # Target triple
                    #"-march=" + config['architecture'], # Architecture
                    #"-mcpu=" + config['cpu'],           # Target CPU
                    "-enable-misched",                  # Enable machine instruction scheduler
                    "-enable-tail-merge",               # Merge similar tail code
                    "-optimize-regalloc",               # Optimize register allocation
                    "-relocation-model=pic",         # Static relocation (no PIC)
                    "-tail-dup-size=3",                 # Tail duplication threshold
                    "-tailcallopt",                     # Enable tail call optimization
                    "-x86-asm-syntax=intel",            # Intel syntax assembly
                    "-x86-use-base-pointer",            # Use base pointer
                    "-no-x86-call-frame-opt",           # Disable call frame optimization (smaller)
                    "-disable-verify",                  # Disable verification for speed
                    str(ll_file),
                    "-o",
                    str(obj_file)
                ]

                # Compile LLVM IR to object file using desired compiler
                cmd = [compiler_exe] + compiler_args
                self.logger.debug(f"Running: {' '.join(cmd)}", compiler)
                
                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    self.logger.trace(f"{compiler} output: {result.stdout}", compiler)
                    if result.stderr:
                        self.logger.warning(f"{compiler} stderr: {result.stderr}", compiler)
                    self.temp_files.append(obj_file)
                    
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"{compiler} compilation failed: {e.stderr}", compiler)
                    raise
                    
            else:  # Linux and others - use traditional assembly step
                asm_file = temp_dir / f"{base_name}.s"
                obj_file = temp_dir / f"{base_name}.o"
                
                # Generate assembly
                cmd = [
                    "llc",
                    "-O3",                        # Maximum optimization level
                    #"-mtriple=x86_64-linux",      # Explicit target triple
                    *self._get_llc_target_flags(),   # march/mcpu/mattr
                    "-enable-misched",            # Enable machine instruction scheduler
                    "-enable-tail-merge",         # Merge similar tail code
                    "-disable-verify",            # Disable verification for speed
                    "-filetype=asm",              # Assembly file output
                    "-no-x86-call-frame-opt",     # Disable call frame optimization (smaller)
                    "-optimize-regalloc",         # Optimize register allocation
                    "-relocation-model=static",   # Static relocation (no PIC)
                    "-tail-dup-size=3",           # Tail duplication threshold
                    "-tailcallopt",               # Enable tail call optimization
                    "-x86-asm-syntax=att",        # ATT syntax assembly
                    "-x86-use-base-pointer",      # Use base pointer
                    str(ll_file),
                    "-o",
                    str(asm_file)                 # Output to assembly file
                ]

                # If user/config didn't specify march/mcpu, fall back to x86-64/native
                if not any(f.startswith('-march=') for f in cmd):
                    cmd.insert(2, '--march=x86-64')
                
                if not any(f.startswith('-mcpu=') for f in cmd):
                    cmd.insert(3, '-mcpu=native')

                self.logger.debug(f"Running: {' '.join(cmd)}", "llc")
                
                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    self.logger.trace(f"LLC output: {result.stdout}", "llc")
                    if result.stderr:
                        self.logger.warning(f"LLC stderr: {result.stderr}", "llc")
                    self.temp_files.append(asm_file)
                    
                    # Log assembly if requested (legacy compatibility)
                    if self.verbosity == 3 or self.logger.level >= LogLevel.TRACE:
                        with open(asm_file, "r") as f:
                            asm_content = f.read()
                        self.logger.log_data(LogLevel.TRACE, "Generated Assembly", asm_content, "llc")
                    
                    # Assemble to object file
                    as_cmd = ["as", "--64", str(asm_file), "-o", str(obj_file)]
                    self.logger.debug(f"Running: {' '.join(as_cmd)}", "as")
                    
                    as_result = subprocess.run(as_cmd, check=True, capture_output=True, text=True)
                    self.logger.trace(f"AS output: {as_result.stdout}", "as")
                    if as_result.stderr:
                        self.logger.warning(f"AS stderr: {as_result.stderr}", "as")
                        
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Assembly failed: {e.stderr}", "as")
                    raise

            self.temp_files.append(obj_file)
            self.logger.debug(f"Object file created: {obj_file}", "build")

            # For Library
            if getattr(self, "compile_only", False):
                self.logger.success(f"Object file compiled: {obj_file}")
                if output_bin:
                    import shutil
                    Path(output_bin).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(obj_file, output_bin)
                    return output_bin
                return str(obj_file)
            
            # Legacy verbosity level 4 - show everything
            if self.verbosity == 4:
                self.logger.log_data(LogLevel.INFO, "All Tokens", tokens, "legacy")
                self.logger.log_data(LogLevel.INFO, "Complete AST", ast, "legacy")
                self.logger.log_data(LogLevel.INFO, "Complete LLVM IR", llvm_ir, "legacy")
                if self.platform == "Linux":
                    with open(asm_file, "r") as f:
                        asm_content = f.read()
                    self.logger.log_data(LogLevel.INFO, "Complete Assembly", asm_content, "legacy")
            
            # Step 8: Link executable
            output_bin = output_bin or f"./{base_name}"
            # Add .exe extension for Windows executables
            output_dir = output_bin.replace(".exe","")
            if self.platform == "Windows" and not output_bin.endswith('.exe'):
                output_bin += ".exe"

            failure_flag = True
            
            self.logger.step(f"Linking executable: {output_bin}", LogLevel.INFO, "linker")
            
            if self.platform == "Darwin":  # macOS
                link_cmd = ["clang", str(obj_file), "-o", f"build/{output_dir}/{output_bin}"]
            elif self.platform == "Windows":
                # Use LLD — resolve the full path so non-default LLVM installs work.
                linker_name = config['linker']
                try:
                    linker_exe = resolve_llvm_tool(linker_name)
                except FileNotFoundError as e:
                    self.logger.error(str(e), "linker")
                    raise
                link_cmd = [
                    linker_exe,
                    "/entry:" + config.get('entrypoint', 'main'),                 # TODO -> f"/entry:{entrypoint}"
                                                   # Custom entrypoint support, default main if unspecified
                    "/stack:67108864",
                    "/nodefaultlib" if int(config['no_default_libraries']) == 1 else "",
                    "/subsystem:" + config['subsystem'],
                    "/opt:ref" if int(config['remove_unused_funcs']) == 1 else "",                    # Remove unused functions/data
                    "/opt:icf" if int(config['comdat_folding']) == 1 else "",                    # Identical COMDAT folding
                    "/section:.text,ERW",
                    #"/merge:.rdata=.text" if int(config['merge_read_only_w_text']) == 1 else "",         # Merge read-only data with code
                    "/merge:.data=.text" if int(config['marge_data_and_code']) == 1 else "",          # Merge data with code
                    "/align:" + config['memory_alignment'] if int(config['memory_alignment']) != 0 else "",                    # 32-bit memory alignment (minimal padding)
                    "/filealign:" + config['bin_disk_alignment'] if int(config['bin_disk_alignment']) != 0 else "",                # 32-bit file alignment (tiny executable)
                    "/driver" if int(config['driver_mode']) == 1 else "",      # Driver mode
                    "/" + config['mode'],                    # Release mode (no debug info)
                    "/fixed" if int(config['fixed_base_address']) == 1 else "",                      # Fixed base address
                    "/incremental:no" if int(config['incremental_linking']) == 1 else "",             # Disable incremental linking
                    "/strip" if int(config['strip_executable']) == 1 else "",                  # Remove all symbols
                    "/guard:no" if int(config['control_flow_guard']) == 1 else "",                   # Disable CFG (Control Flow Guard)
                    "/dynamicbase:no" if int(config['aslr']) == 1 else "",             # Disable ASLR (for smaller size)
                    #"/highentropyva:no" if int(config['no_default_libraries']) == 0 else "",           # Disable high entropy ASLR
                    "/nxcompat:no" if int(config['dep_compatibility']) == 1 else "",                # Disable DEP compatibility
                    f"/opt:lldlto={config.get('lto_optimization_level', 3)}",               # Aggressive LTO optimization if available
                    "/opt:lldltojobs=all" if int(config['all_cores_for_lto']) == 1 else "",         # Use all cores for LTO
                    str(obj_file),
                    # Only link essential libraries
                    #config['lib_files'],
                    'legacy_stdio_definitions.lib',
                    #'libvcruntime.lib',
                    "kernel32.lib",
                    "ucrt.lib",
                    "opengl32.lib",
                    "Ws2_32.lib",
                    "shell32.lib",
                    "freetype.lib",
                    "ole32.lib",
                    "mmdevapi.lib",
                    "comdlg32.lib",
                    "d2d1.lib",
                    "dwrite.lib",
                    #"libsynchronization.lib",
                    #"libcmt.lib",
                    #"msvcrt.lib",   # Optional, link with C runtime
                    "user32.lib",  # Uncomment only if GUI functions are used
                    "gdi32.lib",   # Uncomment only if drawing functions are used
                    *extra_libs,
                    f"/out:build\\{output_dir}\\{output_bin}"
                ]
                self.logger.debug(f"Running: {' '.join(link_cmd)}", "linker")
                
                try:
                    result = subprocess.run(link_cmd, check=True, capture_output=True, text=True)
                    self.logger.trace(f"Linker output: {result.stdout}", "linker")
                    if result.stderr:
                        self.logger.warning(f"Linker stderr: {result.stderr}", "linker")
                        print(f"\n\nRESULT\n{result}\n\n")
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Linking failed: {e.stderr}", "linker")
                    if "undefined symbol:" in e.stderr and \
                            "standard__memory__allocators__stdheap__fmalloc__1__dataE1_ubits64__ret_dataE1_ubits64" in e.stderr:
                        self.logger.error(
                            "Undefined symbol: fmalloc\n"
                            "  'heap' requires the standard memory allocator. Add '#import \"standard.fx\";' to your source file.",
                            "linker"
                        )
                        raise RuntimeError("Missing import: standard.fx required for 'heap' keyword")
                    if config['linker'] == "lld-link":
                        self.logger.step(f"Falling back to clang...", LogLevel.INFO, "linker")
                        try:
                            result = subprocess.run(
                                f"clang {str(obj_file)} -o build\\{output_dir}\\{output_bin} "
                                "-fuse-ld=lld-link "
                                "-Os "
                                "-flto "
                                "-fvisibility=hidden "
                                "-fmerge-all-constants "
                                "-fno-unwind-tables "
                                "-fno-asynchronous-unwind-tables "
                                "-nodefaultlibs "  # Don't use default libs, but we'll specify our own
                                "-Wl,/OPT:REF "
                                "-Wl,/OPT:ICF "
                                "-Wl,/DEBUG:NONE "
                                "-Wl,/INCREMENTAL:NO "
                                "-Wl,/LTCG "
                                "-Wl,/MERGE:.rdata=.text "
                                #"-Wl,/ALIGN:16 "
                                "-Wl,/ENTRY:FRTStartup "  # Use CRT startup for compatibility
                                "-Wl,/SUBSYSTEM:CONSOLE "
                                # Link only necessary libraries:
                                "-lkernel32 "  # Windows kernel functions (CreateFile, ReadFile, etc.)
                                "-lucrt "  # Modern C runtime (strlen, fopen, etc.)
                                "-lWs2_32 "
                                "-luser32 "
                                "-lgdi32 "
                                "-lopengl32 "
                                "-lcomdlg32 "
                                "-lole32 "
                                "-lmmdevapi "
                                "-lcomdlg32 "
                                "-ld2d1 "
                                "-ldwrite "
                                "-lucrt -lmsvcrt "
                                #"-lfreetype "
                                #"-lgdiplus "
                                #"-ld2d1 "
                                #"-ldwrite "
                                #"-llibsynchronization "
                                "-llegacy_stdio_definitions "  # For stdio functions in UCRT
                                # Alternatively for older MSVCRT:
                                # "-lmsvcrt "  # Old C runtime (smaller but may have issues)
                            )
                        except Exception as e:
                            print("EXCEPTION:",e)
                            raise
                    if result.returncode == 1:
                        raise RuntimeError(f"\n{result.args}")
            else:  # Linux and others
                link_cmd = [
                    "ld",
                    "--gc-sections",                    # Remove unused sections
                    "--as-needed",                      # Only link needed libraries
                    "--strip-all",                      # Strip all symbols
                    "--build-id=none",                  # No build ID
                    "--no-eh-frame-hdr",                # No exception handling frame header
                    "--no-ld-generated-unwind-info",    # No unwind info
                    "-z", "noseparate-code",            # Don't separate code segments
                    "-z", "norelro",                    # Disable RELRO (size tradeoff)
                    "-z", "now",                        # Bind now (alternative to norelro)
                    "-z", "noexecstack",                # No executable stack
                    "-z", "max-page-size=0x1000",       # Small page size
                    "-z", "common-page-size=0x1000",    # Small common page size
                    "-z", "defs",                       # Report undefined symbols (strict)
                    "--hash-style=gnu",                 # GNU hash style (faster)
                    "--sort-section=alignment",         # Sort by alignment
                    "--compress-debug-sections=none",   # No debug compression
                    "--fatal-warnings",                 # Treat warnings as errors
                    "--stats",                          # Show linker statistics
                    "--cref",                           # Cross reference output
                    "-Map", f"{output_bin}.map",        # Generate map file
                    "--orphan-handling=place",          # Handle orphan sections
                    #"--icf=all",                        # Identical Code Folding
                    #"--print-icf-sections",             # Show ICF statistics
                    #"--plugin-opt=O3",                  # LTO optimization level 3
                    #"--plugin-opt=merge-functions",     # Merge similar functions
                    #"--plugin-opt=dce",                 # Dead code elimination
                    #"--plugin-opt=inline",              # Function inlining
                    #"--unresolved-symbols=ignore-all",
                    #"-lc",
                    "-Ttext-segment=0x400000",              # Text segment address
                    "--section-start", ".rodata=0x500000",  # Read-only data address
                    "--section-start", ".data=0x600000",    # Data section address
                    "--section-start", ".bss=0x700000",     # BSS section address
                    "-dynamic-linker", "/lib64/ld-linux-x86-64.so.2",
                    "-e", "_start",                         # Entry point
                    str(obj_file),
                    # Library search paths
                    "-L/usr/lib/x86_64-linux-gnu",
                    "-L/usr/lib",
                    "-L/lib/x86_64-linux-gnu",
                    "-L/lib",
                    # Runtime dependencies -- Enable if you want them in your code.
                    #"/usr/lib/x86_64-linux-gnu/Scrt1.o",        # Startup code
                    #"/usr/lib/x86_64-linux-gnu/crti.o",         # C runtime init
                    #"-lc",                                     # C library
                    #"/usr/lib/x86_64-linux-gnu/crtn.o",        # C runtime term
                    #"-lgcc",                                   # GCC runtime
                    #"-lgcc_eh",                                # GCC exception handling
                    #"-lwayland-client",
                    "--start-group",
                    "-lc",
                    "--end-group",
                    *extra_libs,
                    "-o", f"build/{output_dir}/{output_bin}"
                ]
                #link_cmd = ["clang", "-static", str(obj_file), "-o", output_bin]
                self.logger.debug(f"Running: {' '.join(link_cmd)}", "linker")
                
                try:
                    result = subprocess.run(link_cmd, check=True, capture_output=True, text=True)
                    self.logger.trace(f"Linker output: {result.stdout}", "linker")
                    if result.stderr:
                        self.logger.warning(f"Linker stderr: {result.stderr}", "linker")
                        failed = True
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Linking failed: {e.stderr}", "linker")
                    raise
                
            # Success!
            self.logger.success(f"Compilation completed: {output_bin}")
            return output_bin
            
        except Exception as e:
            # Comment out cleanup to preserve LLVM IR files for debugging
            # self.cleanup()
            self.logger.failure(f"Compilation failed: {e}")
            sys.exit(1)

    def compile_dos(self, filename: str, output_bin: str = None, com_file: bool = False) -> str:
        """
        Compile a Flux source file to 16-bit DOS executable
        """
        try:
            self.logger.section(f"COMPILING {filename.upper()} FOR 16-BIT DOS", LogLevel.INFO)
            base_name = Path(filename).stem
            
            # Initialize macros
            if not hasattr(self, 'predefined_macros'):
                self.predefined_macros = {}
            
            # Update macros for DOS target
            self.predefined_macros.update({
                '__DOS__': '1',
                '__MSDOS__': '1',
                '__16BIT__': '1',
                '__I86__': '1',
                '__TINY__': '1' if com_file else '0',
                '__MODEL_SMALL__': '1',
            })
            
            # Preprocessing
            preprocessor = FXPreprocessor(filename, compiler_macros=self.predefined_macros)
            result = preprocessor.process()
            
            # Lexical analysis
            self.logger.step("Lexical analysis", LogLevel.INFO, "lexer")
            lexer = FluxLexer(result)
            tokens = lexer.tokenize()
            
            # Parsing
            self.logger.step("Parsing", LogLevel.INFO, "parser")
            parser = FluxParser(tokens)
            ast = parser.parse()
            
            if parser.has_errors():
                for error in parser.get_errors():
                    self.logger.error(error, "parser")
                raise RuntimeError("Parse errors detected")
            
            # Create build directory
            temp_dir = Path(f"build/{base_name}_dos")
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate LLVM IR with 16-bit target
            self.logger.step("LLVM IR code generation", LogLevel.INFO, "codegen")
            dos_module = ir.Module(name="dos_module")
            dos_module.triple = "i386-unknown-none"
            dos_module = _codegen_visitor.compile(ast, dos_module)
            llvm_ir = str(dos_module)
            
            # Write LLVM IR
            ll_file = temp_dir / f"{base_name}.ll"
            with open(ll_file, 'w') as f:
                f.write(llvm_ir)
            self.temp_files.append(ll_file)
            
            # Generate assembly with PROPER settings for DOS
            asm_file = temp_dir / f"{base_name}.asm"
            
            # Try different llc approaches
            llc_attempts = [
                # Try with explicit Intel syntax and 16-bit hints
                [
                    "llc",
                    "-march=x86",
                    "-mcpu=i386",
                    "-x86-asm-syntax=intel",  # Force Intel syntax
                    "-code-model=small",      # 16-bit code model
                    "-relocation-model=static",
                    "-filetype=asm",
                    str(ll_file),
                    "-o",
                    str(asm_file)
                ],
                # Fallback: simpler
                [
                    "llc",
                    "-march=x86",
                    "-x86-asm-syntax=intel",
                    "-filetype=asm",
                    str(ll_file),
                    "-o",
                    str(asm_file)
                ]
            ]
            
            success = False
            for llc_cmd in llc_attempts:
                try:
                    self.logger.debug(f"Trying: {' '.join(llc_cmd)}", "llc")
                    result = subprocess.run(llc_cmd, check=True, capture_output=True, text=True)
                    if result.stderr:
                        self.logger.warning(f"llc: {result.stderr}", "llc")
                    success = True
                    break
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"llc attempt failed: {e.stderr}", "llc")
                    continue
            
            if not success:
                self.logger.error("All llc attempts failed", "llc")
                raise RuntimeError("Could not generate assembly")
            
            # Convert to JWASM format - handle AT&T syntax if needed
            jwasm_file = temp_dir / f"{base_name}_jwasm.asm"
            self._convert_to_jwasm_format(asm_file, jwasm_file, com_file)
            
            self.logger.success(f"JWASM assembly generated: {jwasm_file}")
            
            # Also create a simple batch file for DOSBox
            batch_file = temp_dir / "compile.bat"
            with open(batch_file, 'w') as f:
                if com_file:
                    f.write(f'JWASM /MT {jwasm_file.name}\n')
                    f.write(f'DIR {base_name}.COM\n')
                else:
                    f.write(f'JWASM /MS {jwasm_file.name}\n')
                    f.write(f'DIR {base_name}.EXE\n')
            
            self.logger.info(f"To compile in DOSBox, run: {batch_file.name}")
            return str(jwasm_file)
            
        except Exception as e:
            self.logger.failure(f"DOS compilation failed: {e}")
            raise

    def _convert_to_jwasm_format(self, input_asm: Path, output_asm: Path, com_file: bool):
        """
        Convert LLVM-generated assembly to JWASM format - 16-bit pure version
        """
        with open(input_asm, 'r') as f:
            llvm_asm = f.read()
        
        lines = []
        
        # Add JWASM header - Pure 16-bit
        lines.append('; DOS EXE File - Generated by Flux')
        lines.append('.MODEL SMALL')
        lines.append('.STACK 100h')
        lines.append('.CODE')
        lines.append('')
        lines.append('main PROC')
        
        # For a simple "return 0" program, generate 16-bit equivalent
        # Since LLVM generates "xor eax, eax; ret", we need 16-bit version
        lines.append('    xor ax, ax      ; AX = 0 (return value)')
        lines.append('    ret            ; Return to caller')
        
        lines.append('main ENDP')
        lines.append('')
        
        # Add DOS startup code
        lines.append('START:')
        lines.append('    mov ax, @data')
        lines.append('    mov ds, ax     ; Set up data segment')
        lines.append('    call main      ; Call main function')
        lines.append('    mov ax, 4C00h  ; Exit to DOS')
        lines.append('    int 21h')
        lines.append('')
        lines.append('.DATA')
        lines.append('    ; Data section')
        lines.append('')
        lines.append('END START')
        
        # Write output
        with open(output_asm, 'w') as f:
            f.write('\n'.join(lines))

    def _convert_att_to_intel(self, att_line: str) -> str:
        """
        Convert AT&T syntax to Intel syntax
        Example: "xorl %eax, %eax" -> "XOR EAX, EAX"
        """
        # Remove % from registers
        line = att_line.replace('%', '')
        
        # Convert instruction suffixes
        suffix_map = {
            'l': '',  # 32-bit
            'w': '',  # 16-bit  
            'b': '',  # 8-bit
        }
        
        # Common AT&T to Intel conversions
        conversions = [
            ('xorl', 'XOR'),
            ('movl', 'MOV'),
            ('addl', 'ADD'),
            ('subl', 'SUB'),
            ('cmpl', 'CMP'),
            ('calll', 'CALL'),
            ('retl', 'RET'),
            ('pushl', 'PUSH'),
            ('popl', 'POP'),
            ('leal', 'LEA'),
        ]
        
        for att, intel in conversions:
            if att in line:
                line = line.replace(att, intel)
        
        # Swap source/dest order (AT&T: op src, dest | Intel: op dest, src)
        if ',' in line:
            parts = line.split(',')
            if len(parts) == 2:
                op_parts = parts[0].split()
                if len(op_parts) >= 2:
                    # Has both opcode and first operand
                    opcode = op_parts[0]
                    src = op_parts[1]
                    dest = parts[1].strip()
                    line = f'{opcode} {dest}, {src}'
        
        # Convert registers to uppercase
        registers = ['eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp',
                     'ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp',
                     'al', 'bl', 'cl', 'dl', 'ah', 'bh', 'ch', 'dh']
        
        for reg in registers:
            if reg in line.lower():
                # Replace with uppercase, being careful not to match partial words
                import re
                line = re.sub(rf'\b{reg}\b', reg.upper(), line, flags=re.IGNORECASE)
        
        return linе

    def _modify_asm_for_dos(self, asm_file: Path, temp_dir: Path) -> Path:
        """
        Modify LLVM-generated assembly for DOS compatibility
        """
        modified_asm_file = temp_dir / f"{asm_file.stem}_dos.asm"
        
        with open(asm_file, 'r') as f:
            asm_content = f.read()
        
        # Start with DOS headers and model
        modified_asm = [
            "; 16-bit DOS executable",
            ".model small",           # Small memory model
            ".stack 100h",            # 256-byte stack
            "",
            ".code",
            "",
            "main PROC",
            "    mov ax, @data",
            "    mov ds, ax           ; Set data segment",
            ""
        ]
        
        # Process LLVM output
        for line in asm_content.split('\n'):
            line_stripped = line.strip()
            
            # Skip unnecessary LLVM directives
            if any(skip in line_stripped for skip in [
                '.section',
                '.file',
                '.globl main',
                '.type',
                '.size',
                '.ident',
                '.addrsig'
            ]):
                continue
            
            # Convert LLVM function labels to DOS labels
            if line_stripped.endswith(':'):
                if line_stripped == 'main:':
                    continue  # Already handled
                # Remove LLVM's prefix
                label = line_stripped.rstrip(':')
                modified_asm.append(f"{label}:")
                continue
            
            # Convert push/pop to 16-bit
            if line_stripped.startswith(('push', 'pop')):
                if 'ebp' in line_stripped or 'esp' in line_stripped:
                    line_stripped = line_stripped.replace('ebp', 'bp').replace('esp', 'sp')
            
            # Add line if not empty
            if line_stripped:
                modified_asm.append(f"    {line_stripped}")
        
        # Add DOS exit and data segment
        modified_asm.extend([
            "",
            "    ; DOS exit",
            "    mov ax, 4C00h",
            "    int 21h",
            "main ENDP",
            "",
            ".data",
            "    ; Data section",
            "    message db 'Hello, DOS!$'",
            "",
            "END main"
        ])
        
        with open(modified_asm_file, 'w') as f:
            f.write('\n'.join(modified_asm))
        
        self.temp_files.append(modified_asm_file)
        return modified_asm_file

    def compile_library(self, filename: str, output_bin: str = None) -> str:
        """
        Compile a Flux source file to a shared library (DLL on Windows, .so on Linux, .dylib on macOS).
        """
        try:
            self.logger.section(f"COMPILING {filename.upper()} AS SHARED LIBRARY", LogLevel.INFO)
            base_name = Path(filename).stem

            # ── Steps 1–4: preprocess / lex / parse / codegen ──────────────────
            # Reuse compile_file's pipeline up to the object file by setting
            # compile_only, then immediately clearing it so we can do our own link.
            self.compile_only = True
            try:
                obj_path = self.compile_file(filename, output_bin=None)
            finally:
                self.compile_only = False

            obj_file = Path(obj_path)

            # ── Determine output name ───────────────────────────────────────────
            if self.platform == "Windows":
                out_name = output_bin or f"{base_name}.dll"
                if not out_name.endswith(".dll"):
                    out_name += ".dll"
            elif self.platform == "Darwin":
                out_name = output_bin or f"lib{base_name}.dylib"
                if not out_name.endswith(".dylib"):
                    out_name += ".dylib"
            else:  # Linux / default
                out_name = output_bin or f"lib{base_name}.so"
                if not out_name.endswith(".so"):
                    out_name += ".so"

            output_dir = Path(f"build/{base_name}")
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / out_name

            # ── Link ────────────────────────────────────────────────────────────
            self.logger.step(f"Linking shared library: {out_name}", LogLevel.INFO, "linker")

            if self.platform == "Windows":
                linker_name = config.get('linker', 'lld-link')
                try:
                    linker_exe = resolve_llvm_tool(linker_name)
                except FileNotFoundError as e:
                    self.logger.error(str(e), "linker")
                    raise

                link_cmd = [
                    linker_exe,
                    "/DLL",                          # <-- This is the key flag
                    "/NOENTRY",                      # DLLs don't need an entrypoint by default;
                                                     # remove this line and add /ENTRY:DllMain
                                                     # if your library defines DllMain
                    "/nodefaultlib" if int(config.get('no_default_libraries', 0)) == 1 else "",
                    "/opt:ref" if int(config.get('remove_unused_funcs', 0)) == 1 else "",
                    "/opt:icf" if int(config.get('comdat_folding', 0)) == 1 else "",
                    "/section:.text,ERW",
                    f"/opt:lldlto={config.get('lto_optimization_level', 3)}",
                    str(obj_file),
                    "kernel32.lib",
                    "ucrt.lib",
                    "user32.lib",
                    "gdi32.lib",
                    f"/out:{out_path}",
                    f"/implib:{output_dir / (base_name + '.lib')}",  # import lib for linking against
                ]
                # Strip empty strings left by disabled flags
                link_cmd = [x for x in link_cmd if x]

            elif self.platform == "Darwin":
                link_cmd = [
                    "clang",
                    "-dynamiclib",
                    "-o", str(out_path),
                    str(obj_file),
                ]

            else:  # Linux
                link_cmd = [
                    "ld",
                    "-shared",
                    "-o", str(out_path),
                    str(obj_file),
                ]

            self.logger.debug(f"Running: {' '.join(link_cmd)}", "linker")
            try:
                result = subprocess.run(link_cmd, check=True, capture_output=True, text=True)
                self.logger.trace(f"Linker output: {result.stdout}", "linker")
                if result.stderr:
                    self.logger.warning(f"Linker stderr: {result.stderr}", "linker")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"DLL linking failed: {e.stderr}", "linker")
                raise RuntimeError(f"Library link step failed: {e.stderr}")

            self.logger.success(f"Library compiled: {out_path}")
            return str(out_path)

        except Exception as e:
            self.logger.error(f"Library compilation failed: {e}", "compiler")
            raise

    def compile_bootloader(self, filename: str, output_bin: str = None) -> str:
        """
        Compile a Flux source file to a raw 16-bit bootloader binary
        """
        try:
            self.logger.section(f"COMPILING {filename.upper()} IN BOOTLOADER MODE", LogLevel.INFO)
            base_name = Path(filename).stem
            preprocessor = FluxPreprocessor()
            result = preprocessor.preprocess(filename)
            
            # Step 2: Lexical analysis
            self.logger.step("Lexical analysis", LogLevel.INFO, "lexer")
            try:
                lexer = FluxLexer(result)
                tokens = lexer.tokenize()
                #self.logger.debug(f"Generated {len(tokens) if hasattr(tokens, '__len__') else '?'} tokens", "lexer")
                
                debugger(self.debug_levels, [1,8], [f"Lexer produced {len(tokens)} tokens:", tokens])
            except Exception as e:
                self.logger.error(f"Lexical analysis failed: {e}", "lexer")
                raise
            
            # Step 3: Parsing
            self.logger.step("Parsing", LogLevel.INFO, "parser")
            try:
                parser = FluxParser(tokens)
                ast = parser.parse()
                
                if parser.has_errors():
                    self.logger.error(f"Compilation aborted due to {len(parser.get_errors())} parse error(s)", "parser")
                    for error in parser.get_errors():
                        self.logger.error(error, "parser")
                    raise RuntimeError("Parse errors detected - compilation aborted")
                
                debugger(self.debug_levels, [3,8], ["AST:", ast])
                        
            except Exception as e:
                self.logger.error(f"Parsing failed: {e}", "parser")
                raise
            
            # Step 4: Code generation with 16-bit configuration
            self.logger.step("LLVM IR code generation (16-bit mode)", LogLevel.INFO, "codegen")
            try:                
                self.module = _codegen_visitor.compile(ast, self.module)
                llvm_ir = str(self.module)
                
                self.logger.debug(f"Generated LLVM IR ({len(llvm_ir)} chars)", "codegen")
                
                if self.logger.level >= LogLevel.TRACE:
                    self.logger.log_data(LogLevel.TRACE, "Generated LLVM IR", llvm_ir, "codegen")
                        
            except Exception as e:
                self.logger.error(f"Code generation failed: {e}", "codegen")
                raise
            
            # Step 5: Create build directory
            self.logger.step("Preparing build environment", LogLevel.DEBUG, "build")
            temp_dir = Path(f"build/{base_name}")
            temp_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Build directory: {temp_dir.absolute()}", "build")
            
            # Step 6: Write LLVM IR file
            self.logger.step("Writing LLVM IR file", LogLevel.DEBUG, "build")
            ll_file = temp_dir / f"{base_name}.ll"
            try:
                with open(ll_file, 'w') as f:
                    f.write(llvm_ir)
                self.temp_files.append(ll_file)
                self.logger.debug(f"LLVM IR written to: {ll_file}", "build")
            except Exception as e:
                self.logger.error(f"Failed to write LLVM IR file: {e}", "build")
                raise
            
            # Step 7: Generate 32-bit assembly (we'll add .code16 directive manually)
            self.logger.step("Generating x86 assembly", LogLevel.INFO, "llc")
            asm_file = temp_dir / f"{base_name}.s"
            
            llc_cmd = [
                "llc",
                "-march=x86",              # x86 architecture
                "-mcpu=i386",              # Target 386 CPU
                "-relocation-model=static", # Static addressing (no PIC)
                "-code-model=small",       # Small code model
                "-filetype=asm",           # Assembly output
                "-x86-asm-syntax=intel",   # Intel syntax
                str(ll_file),
                "-o",
                str(asm_file)
            ]

            if self.llc_config.get('mattr'):
                llc_cmd.insert(-3, f"-mattr={self.llc_config['mattr']}")
            
            self.logger.debug(f"Running: {' '.join(llc_cmd)}", "llc")
            
            try:
                result = subprocess.run(llc_cmd, check=True, capture_output=True, text=True)
                self.logger.trace(f"LLC output: {result.stdout}", "llc")
                if result.stderr:
                    self.logger.warning(f"LLC stderr: {result.stderr}", "llc")
                self.temp_files.append(asm_file)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Assembly generation failed: {e.stderr}", "llc")
                raise
            
            # Step 8: Modify assembly to add .code16 directive and remove unwanted sections
            self.logger.step("Modifying assembly for 16-bit real mode", LogLevel.INFO, "build")
            modified_asm_file = temp_dir / f"{base_name}_16bit.s"
            
            try:
                with open(asm_file, 'r') as f:
                    asm_content = f.read()
                
                # Add .code16 at the beginning and clean up
                modified_asm = ".code16\n"
                modified_asm += ".section .boot, \"ax\"\n"  # Bootable section
                modified_asm += ".global _start\n"
                modified_asm += "_start:\n"
                
                # Filter out problematic directives and 32-bit instructions
                for line in asm_content.split('\n'):
                    line_stripped = line.strip()
                    
                    # Skip these directives/sections
                    if any(skip in line_stripped for skip in [
                        '.section',
                        '.text',
                        '.data',
                        '.bss',
                        '.file',
                        '.globl main',
                        '.type',
                        '.size',
                        '.ident',
                        '.addrsig'
                    ]):
                        continue
                    
                    # Keep function labels and code
                    if line_stripped and not line_stripped.startswith('.'):
                        modified_asm += line + "\n"
                
                with open(modified_asm_file, 'w') as f:
                    f.write(modified_asm)
                
                self.temp_files.append(modified_asm_file)
                self.logger.debug(f"Modified assembly written to: {modified_asm_file}", "build")
                
                if self.logger.level >= LogLevel.TRACE:
                    self.logger.log_data(LogLevel.TRACE, "Modified Assembly", modified_asm, "build")
                    
            except Exception as e:
                self.logger.error(f"Failed to modify assembly: {e}", "build")
                raise
            
            # Step 9: Assemble to object file
            self.logger.step("Assembling to object file", LogLevel.INFO, "as")
            obj_file = temp_dir / f"{base_name}.o"
            
            as_cmd = [
                "as",
                "--32",                    # 32-bit mode (for .code16)
                str(modified_asm_file),
                "-o",
                str(obj_file)
            ]
            
            self.logger.debug(f"Running: {' '.join(as_cmd)}", "as")
            
            try:
                result = subprocess.run(as_cmd, check=True, capture_output=True, text=True)
                self.logger.trace(f"AS output: {result.stdout}", "as")
                if result.stderr:
                    self.logger.warning(f"AS stderr: {result.stderr}", "as")
                self.temp_files.append(obj_file)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Assembly failed: {e.stderr}", "as")
                raise
            
            # Step 10: Link to raw binary
            self.logger.step("Linking to raw binary", LogLevel.INFO, "linker")
            
            output_bin = output_bin or f"{base_name}.bin"
            
            ld_cmd = [
                "ld",
                "-m", "elf_i386",          # 32-bit ELF (for 16-bit code)
                "-T", self._create_bootloader_linker_script(temp_dir),  # Custom linker script
                "--oformat=binary",        # Raw binary output
                "-nostdlib",               # No standard library
                str(obj_file),
                "-o",
                output_bin
            ]
            
            self.logger.debug(f"Running: {' '.join(ld_cmd)}", "linker")
            
            try:
                result = subprocess.run(ld_cmd, check=True, capture_output=True, text=True)
                self.logger.trace(f"Linker output: {result.stdout}", "linker")
                if result.stderr:
                    self.logger.warning(f"Linker stderr: {result.stderr}", "linker")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Linking failed: {e.stderr}", "linker")
                raise
            
            # Step 11: Verify binary size and add boot signature
            self.logger.step("Adding boot signature", LogLevel.INFO, "build")
            
            try:
                with open(output_bin, 'rb') as f:
                    bootloader = bytearray(f.read())
                
                # Bootloader must be exactly 512 bytes
                if len(bootloader) > 510:
                    self.logger.error(f"Bootloader too large: {len(bootloader)} bytes (max 510)", "build")
                    raise RuntimeError(f"Bootloader exceeds 510 bytes")
                
                # Pad to 510 bytes
                bootloader.extend([0] * (510 - len(bootloader)))
                
                # Add boot signature (0x55AA in little-endian)
                bootloader.extend([0x55, 0xAA])
                
                # Write final bootloader
                with open(output_bin, 'wb') as f:
                    f.write(bootloader)
                
                self.logger.debug(f"Bootloader is {len(bootloader)} bytes with signature", "build")
                
            except Exception as e:
                self.logger.error(f"Failed to add boot signature: {e}", "build")
                raise
            
            # Success!
            self.logger.success(f"Bootloader compiled: {output_bin} ({len(bootloader)} bytes)")
            return output_bin
            
        except Exception as e:
            self.logger.failure(f"Bootloader compilation failed: {e}")
            sys.exit(1)

    def _create_bootloader_linker_script(self, temp_dir: Path) -> str:
        """
        Create a custom linker script for bootloader
        
        Returns:
            Path to linker script
        """
        linker_script = temp_dir / "bootloader.ld"
        
        script_content = """
    OUTPUT_FORMAT("binary")
    OUTPUT_ARCH(i386)
    ENTRY(_start)

    SECTIONS
    {
        . = 0x7C00;  /* BIOS loads bootloader here */
        
        .boot : {
            *(.boot)
            *(.text)
            *(.rodata)
            *(.data)
        }
        
        /DISCARD/ : {
            *(.eh_frame)
            *(.comment)
            *(.note*)
        }
    }
    """
        
        with open(linker_script, 'w') as f:
            f.write(script_content)
        
        self.temp_files.append(linker_script)
        return str(linker_script)
    
    def cleanup(self):
        """Remove temporary files and cleanup logger"""
        self.logger.debug(f"Cleaning up {len(self.temp_files)} temporary files", "cleanup")
        
        for f in self.temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    self.logger.trace(f"Removed: {f}", "cleanup")
            except Exception as e:
                self.logger.warning(f"Failed to remove {f}: {e}", "cleanup")
        
        # Close logger if it has file handles
        try:
            self.logger.close()
        except:
            pass

class TeeOutput:
    """Writes to both console and file simultaneously"""
    def __init__(self, console, file):
        self.console = console
        self.file = file
    
    def write(self, message):
        self.console.write(message)
        self.file.write(message)
        self.file.flush()  # Ensure immediate write to file
    
    def flush(self):
        self.console.flush()
        self.file.flush()

def main():
    # Setup debug output redirection
    original_stdout = sys.stdout
    debug_file = None
    
    try:
        # Create build directory under the compiler root, not CWD
        build_dir = FLUXC_SRCDIR / "build"
        build_dir.mkdir(exist_ok=True)
        
        # Open debug.txt for writing
        debug_path = build_dir / "debug.txt"
        debug_file = open(debug_path, 'w', encoding='utf-8', buffering=1)  # Line buffering
        
        # Redirect stdout to both console and file
        sys.stdout = TeeOutput(original_stdout, debug_file)
        
        if len(sys.argv) < 2:
            print("Usage: python fc.py input.fx [output_binary] ...arguments...\n\n")
            print("\tArguments:\n")
            print("\t\t-vX\tVerbose output. X = 0..4\n")
            print("\t\t\t\t0: Tokens")
            print("\t\t\t\t1: AST")
            print("\t\t\t\t2: LLVM IR")
            print("\t\t\t\t3: ASM")
            print("\t\t\t\t4: Everything")
            sys.exit(1)

        input_file = None
        output_bin = None

        if len(sys.argv) == 2:
            input_file = sys.argv[1]
            output_bin = sys.argv[2] if len(sys.argv) > 2 else None

        verbosity = None

        if len(sys.argv) > 2:
            input_file = sys.argv[1]
            output_bin = sys.argv[2] if len(sys.argv) > 2 else None
            for arg in sys.argv:
                if arg.lower().startswith("-v"):
                    if len(arg) > 2 and arg[2:].isdigit():
                        verbosity = int(arg[2:])
                elif arg.lower() == "-o":
                        with open(input_file, 'r') as f:
                            source = f.read()
                        lexer = FluxLexer(source)
                        tokens = lexer.tokenize()
                        parser = FluxParser(tokens)
                        ast = parser.parse()
                        return

        
        if not input_file.endswith('.fx'):
            print("Error: Input file must have .fx extension", file=sys.stderr)
            sys.exit(1)
        
        compiler = FluxCompiler(verbosity=verbosity)
        try:
            match (config.get('target', '')):
                case "bootloader":
                    print("BOOTLOADER")
                    binary_path = compiler.compile_bootloader(input_file, output_bin)
                    print(f"Bootloader created at: {binary_path}")
                    return
                case _:
                    binary_path = compiler.compile_file(input_file, output_bin)
                    print(f"Executable created at: {binary_path}")
                    return
        except:
            pass
        return
    
    finally:
        # Always restore stdout and close debug file
        sys.stdout = original_stdout
        if debug_file:
            debug_file.close()

if __name__ == "__main__":
    main()
    exit()