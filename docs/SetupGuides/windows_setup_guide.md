# Flux on Windows - Setup Guide

This guide helps you understand and configure your Windows development environment for Flux. Rather than providing automated scripts, we believe in helping you understand each component and make informed choices about your setup.

## Toolchain

Flux compilation on Windows involves several components working together:

1. **Python 3.13+** - Runs the Flux compiler itself
2. **LLVM v21** - Full LLVM pipeline
- if your LLVM does not come with `llc`, you will need **MSYS2 MinGW64** for `llc`
- Enter MSYS2 MINGw64 and run `pacman -S mingw-w64-x86_64-llvm`, this will give you `llc`
3. **Clang v21** - Compiles LLVM IR to object files
- if `lld` or `lld-link` fails to link, Flux falls back to `clang` to link the object file(s)
4. **Visual Studio/MSVC** - Provides a linker and the Windows SDK
5. **llvmlite** - Python bindings to LLVM for code generation

## Component Installation

### Python 3.13+
- Download from [python.org](https://www.python.org/downloads/)
- Ensure it's added to your PATH during installation
- Verify: `python --version`

### LLVM/Clang both at least v21
Choose one of these methods:

**Option 1: Official LLVM (Recommended)**
```
winget install LLVM.LLVM
winget install clang
```

**Option 2: Manual Installation**
- Download from [LLVM Releases](https://github.com/llvm/llvm-project/releases)
- Install to a standard location like `C:\Program Files\LLVM`
- Add `C:\Program Files\LLVM\bin` to your PATH

**Option 3: Package Manager**
```
# If you use Chocolatey
choco install llvm

# If you use Scoop
scoop install llvm
```

### Visual Studio Insaller
----
- If you already have VS installed:

<img width="1259" height="699" alt="image" src="https://github.com/user-attachments/assets/b0d85075-a92e-4e2b-a06f-7b65b6491d87" />


- Select **modify**

<img width="1227" height="483" alt="image" src="https://github.com/user-attachments/assets/9516be90-7f7c-4bfb-b2a5-c772cfa49c3c" />

- Select **Individual components**

- Scroll down until you see **Compilers, build tools, and runtimes**

<img width="599" height="158" alt="image" src="https://github.com/user-attachments/assets/a14b5913-707b-415e-92b7-be2bb13a67af" />

- Select **MSVC v143** based on your architecture.

<img width="493" height="187" alt="image" src="https://github.com/user-attachments/assets/c79a512a-b0f6-4ee7-8a89-6676a3442d15" />

- Scroll down to **SDKs, libraries, and frameworks** and select the appropriate **C++ ATL for latest build tools** based on your architecture, matching the MSCV version you selected.
----
- If you do not already have VS installed, install it and include the steps for if you did.

**Visual Studio Build Tools (Minimal):**
If you prefer a lighter installation:
- Download "Build Tools for Visual Studio"
- Install the "Visual C++ build tools" package

----

### Python Dependencies
```powershell
pip install llvmlite==0.44.0 dataclasses
```

## Verification Steps

### 1. Check Python
```
python --version                    # Should show 3.8+
python -c "import llvmlite; print('llvmlite OK')"
```

### 2. Check Clang
```
clang --version
clang --print-targets | findstr x86_64  # Should show x86_64 targets
```

### 3. Check LLVM
```
llc --version
```
- If this fails, you'll need step 3.5

### 3.5 Install LLVM toolchain for MSYS2
If you had to install MSYS2, follow these steps:
- Inside MSYS2 MinGW64, run `pacman -S mingw-w64-x86_64-llvm`
- Add `C:\mingw64\mingw64\bin` to your system or user `PATH` environment variable.

### 4. Create `FLUXC_SRCDIR` as an environment variable
Set it to wherever you installed Flux, where the compiler entrypoint `fxc.py` lives.

### 4. Test Flux Compilation
From a command prompt:
```
cd C:\path\to\Flux
python fxc.py tests\test.fx
```

## Common Issues and Solutions

### "Clang: warning: unable to find a Visual Studio installation"
**Cause:** Clang can't locate MSVC tools for linking.

**Solutions:**
1. Run Flux from a **Visual Studio Developer Command Prompt**
2. Ensure Visual Studio includes the "Desktop development with C++" workload
3. Verify environment variables are set: `echo $env:VCINSTALLDIR`

### "Module `llvmlite` not found"
**Cause:** Python dependencies not installed.

**Solutions:**
1. Install with: `pip install llvmlite==0.41.0`
2. If using multiple Python versions, ensure you're using the right pip
3. Try: `python -m pip install llvmlite==0.41.0`

### Permission Errors
**Cause:** Insufficient permissions for installation or compilation.

**Solutions:**
1. Run terminals as Administrator when installing tools
2. Ensure you have write permissions to your Flux directory
3. Check Windows Defender or antivirus isn't blocking operations

## Development Workflow

### Recommended Terminal Setup
1. Use **Command Prompt** (Recommended) or **PowerShell** (Not Recommended)
2. These terminals automatically configure environment variables for MSVC tools
3. Available through: Start Menu -> Visual Studio -> Developer Command Prompt

### Environment Variables
When properly configured, you should see these environment variables:
- `VCINSTALLDIR` - Points to Visual Studio installation
- `WindowsSdkDir` - Points to Windows SDK
- `PATH` - Includes LLVM, Python, and MSVC tools
- `FLUXC_SRCDIR` - Your Flux installation where `fxc.py` lives

### Compilation Process Understanding
When you run `python fxc.py program.fx`, Flux:
1. **Lexes** your Flux source code into tokens
2. **Parses** tokens into an Abstract Syntax Tree (AST)
3. **Generates** LLVM Intermediate Representation (IR)
4. **Compiles** IR to object file using Clang
5. **Links** object file to executable using MSVC linker

## Advanced Configuration

### Custom LLVM Installation
If you have LLVM installed in a non-standard location, Flux will automatically search:
- `C:\Program Files\LLVM\bin\clang.exe`
- `clang.exe` (if in PATH)
- `clang` (Unix-style name)

You can also set a custom configuration in `config\flux_config.cfg`

### Building
Flux creates temporary files in `build/` directory:
- `program.ll` - LLVM IR code
- `program.o` - Object file
- `program.exe` - Final executable (Windows)

### Debugging Compilation Issues
Enable detailed logging to understand what's happening:
```
python fxc.py program.fx --log-level 4 --log-timestamp
```

This shows exactly which tools are being called and their output.

## Next Steps

Once your environment is working:
1. Try compiling the examples in `examples\` and tests in `tests\`
2. Read the language specification in `docs\`
3. Explore the standard library in `src\stdlib\`
4. Write your first Flux program!

As Flux matures, we'll eventually provide a self-hosted installer written in Flux itself - demonstrating the language's capabilities while maintaining transparency about what's being installed.

Happy Flux development!