# Flux on macOS - Setup Guide

This guide walks you through setting up a clean, effective Flux development environment on macOS. We'll use Homebrew for system packages and `uv` for Python management — the same toolchain the project recommends — plus LLVM for compilation.

## Toolchain Overview

Flux on macOS requires:

1. **Homebrew** - macOS package manager
2. **Python 3.10+** - Runs the Flux compiler
3. **LLVM/Clang** - Compiles LLVM IR to native code and handles linking
4. **llvmlite** - Python bindings to LLVM for code generation
5. **uv** - Fast Python package and environment manager (recommended)
6. **Git** - To clone the Flux repository
7. **Sublime Text** - Your code editor (optional but recommended)

## Quick Start

For the impatient, here's the complete setup:

```bash
# Install Homebrew (skip if already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install system toolchain
brew install python llvm git

# Add Homebrew LLVM to PATH (must take precedence over Apple's bundled clang)
echo 'export PATH="$(brew --prefix llvm)/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc

# Clone Flux
git clone https://github.com/kvthweatt/Flux
cd Flux

# Set up environment and install dependencies via uv
uv sync --extra dev

# Test compilation
uv run python fxc.py tests/test.fx --log-level 3

# Install Sublime Text (optional)
brew install --cask sublime-text
```

Done! Skip to [Verification Steps](#verification-steps) to confirm everything works.

## Detailed Installation

### Homebrew

If you don't already have Homebrew installed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen instructions. On Apple Silicon, Homebrew installs to `/opt/homebrew`; on Intel, to `/usr/local`. The installer will tell you if you need to add anything to your PATH.

### System Packages

```bash
brew install python llvm git
```

**Important — LLVM PATH:** macOS ships with Apple's own `clang`, but Flux requires the full Homebrew LLVM toolchain. Add it to your PATH so it takes precedence:

```bash
echo 'export PATH="$(brew --prefix llvm)/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

If you use bash instead of zsh (uncommon on modern macOS):

```bash
echo 'export PATH="$(brew --prefix llvm)/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
```

### uv (Recommended Package Manager)

The Flux repository ships with `pyproject.toml` and `uv.lock`, making `uv` the cleanest way to manage dependencies:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc
```

Then from inside the cloned repo:

```bash
uv sync --extra dev        # install runtime + development dependencies
```

This automatically creates `.venv/` and installs the correct `llvmlite>=0.43.0` and all dev tools.

**Alternative — plain pip:** If you prefer not to use `uv`:

```bash
pip3 install llvmlite>=0.43.0
```

If you hit permissions issues: `pip3 install --user llvmlite>=0.43.0`

### Sublime Text

```bash
brew install --cask sublime-text
```

**Alternative editors:** VS Code, Vim, Emacs, BBEdit, TextMate, nano — any editor works. See the [Editor Support](#editor-support) section for syntax highlighting options.

### Clone Flux

```bash
git clone https://github.com/kvthweatt/Flux
cd Flux
uv sync --extra dev
```

## Verification Steps

### 1. Check Python

```bash
python3 --version                           # Should show 3.10+
python3 -c "import llvmlite; print('llvmlite OK')"
```

### 2. Check LLVM/Clang

```bash
clang --version        # Should say Homebrew LLVM, NOT Apple clang
llvm-config --version  # Should match clang version
```

If `clang --version` still reports `Apple clang`, the PATH update hasn't applied yet — run `source ~/.zshrc` and retry.

### 3. Check Git

```bash
git --version          # Any recent version is fine
```

### 4. Check uv

```bash
uv --version
uv pip list | grep llvmlite    # Should show llvmlite 0.43+
```

### 5. Test Flux Compilation

```bash
cd Flux
uv run python fxc.py tests/test.fx --log-level 3
# Or without uv:
python3 fxc.py tests/test.fx --log-level 3
```

You should see compilation succeed and an executable created.

## Development Workflow

### Basic Compilation

```bash
cd ~/Flux
uv run python fxc.py examples/hello.fx
./hello
```

Or using the dev helper script the repo provides:

```bash
uv run python scripts/dev.py compile examples/hello.fx
```

### Using uv Run

All compiler invocations work through `uv run` to use the managed environment:

```bash
uv run python fxc.py myprogram.fx          # compile
uv run pytest                              # run tests
uv run python scripts/dev.py clean        # clean build artifacts
```

### Using Sublime Text

**Open a Flux file:**

```bash
subl examples/hello.fx
```

**Open entire project:**

```bash
subl ~/Flux
```

**Build system (optional):**

1. Tools → Build System → New Build System
2. Paste this configuration:

```json
{
    "cmd": ["uv", "run", "python", "fxc.py", "$file"],
    "working_dir": "$folder",
    "selector": "source.flux",
    "file_regex": "^(.+?):(\\d+):(\\d+): (.*)$"
}
```

3. Save as `Flux.sublime-build`
4. Press `Cmd+B` to compile the current file

## Editor Support

The repo ships dedicated editor integration under `editor-support/` and `tree-sitter-flux/`.

### Syntax Highlighting — Sublime Text (Manual)

If you want a quick basic setup without Tree-sitter:

1. Create `~/Library/Application Support/Sublime Text/Packages/User/Flux.sublime-syntax`
2. Add:

```yaml
%YAML 1.2
---
name: Flux
file_extensions: [fx]
scope: source.flux
contexts:
  main:
    - match: '\b(def|object|struct|if|else|while|for|return|import|using|extern|compt|unsigned|data)\b'
      scope: keyword.control.flux
    - match: '\b(int|float|byte|bool|void|this)\b'
      scope: storage.type.flux
    - match: '//.*$'
      scope: comment.line.flux
    - match: '"'
      scope: punctuation.definition.string.begin.flux
      push: string
    - match: '\b\d+\b'
      scope: constant.numeric.flux
  string:
    - meta_scope: string.quoted.double.flux
    - match: '"'
      scope: punctuation.definition.string.end.flux
      pop: true
```

Restart Sublime Text and `.fx` files will have basic highlighting.

### Tree-sitter (Richer Highlighting)

The repo includes `tree-sitter-flux/` for editors that support Tree-sitter (Neovim, Helix, Zed, etc.). Check `editor-support/` for editor-specific instructions.

## Common Issues and Solutions

### "Module 'llvmlite' not found"

```bash
# Check if it's installed in the uv environment
uv pip list | grep llvmlite
# Reinstall
uv sync
# Or for plain pip
pip3 list | grep llvmlite
pip3 install llvmlite>=0.43.0
```

### "Command 'clang' not found" or Wrong Clang

```bash
brew list llvm          # confirm installed
which clang             # should be under /opt/homebrew or /usr/local
clang --version         # should say Homebrew LLVM

# If it still shows Apple clang, re-apply PATH:
echo 'export PATH="$(brew --prefix llvm)/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### "xcrun: error" or Xcode Tools Prompt

Accept the prompt, or install manually:

```bash
xcode-select --install
```

This provides the base system libraries that Homebrew LLVM links against.

### Permission Errors During Compilation

```bash
ls -la
sudo chown -R $USER ~/Flux
```

### uv Environment Issues

```bash
# Remove and recreate the virtual environment
rm -rf .venv
uv sync --extra dev

# Clear uv cache if needed
uv cache clean
```

## Advanced Configuration

### Shell Aliases

Add to `~/.zshrc`:

```bash
alias fluxc='uv run --project ~/Flux python ~/Flux/fxc.py'
alias flux-dev='cd ~/Flux && source .venv/bin/activate'
```

Apply:

```bash
source ~/.zshrc
```

Now:

```bash
fluxc myprogram.fx       # compile from anywhere
```

### Environment Variables

The Flux compiler respects several env vars:

```bash
export FLUX_LOG_LEVEL=3                        # default log level (0–5)
export FLUX_LOG_TIMESTAMP=1                    # enable timestamps
export FLUX_LOG_NO_COLOR=1                     # disable color output
export FLUX_LOG_COMPONENTS=lexer,parser        # filter components
```

Add to `~/.zshrc` to make permanent.

### Build Directory

Flux creates temporary files in `build/`:

- `program.ll` - LLVM IR (human-readable)
- `program.o` - Object file
- `program` - Final executable (no extension on macOS, same as Linux)

Inspect generated IR:

```bash
uv run python fxc.py program.fx
cat build/program.ll
```

### Debugging Compilation

```bash
uv run python fxc.py program.fx --log-level 4 --log-timestamp
```

This shows lexing, parsing, IR generation, Clang invocation, and linking.

## Understanding the Compilation Process

When you run `python fxc.py program.fx`, Flux:

1. **Preprocesses** - Handles macros, strips comments and empty lines, outputs to `build/tmp.fx`
2. **Lexes** - Breaks source into tokens
3. **Parses** - Builds an Abstract Syntax Tree (AST)
4. **Generates Code** - Creates LLVM Intermediate Representation (IR)
5. **Compiles** - Uses Clang to convert IR to object code
6. **Links** - Creates the final executable using macOS system libraries

Like Linux, macOS doesn't need Visual Studio — Homebrew's Clang handles the full pipeline. The only macOS-specific detail is ensuring Homebrew's LLVM is on your PATH ahead of Apple's bundled toolchain.

## Next Steps

Now that your environment is ready:

1. **Learn the language:**
   - Read `docs/learn_flux_intro.md` for a beginner tutorial
   - Read `docs/learn_flux_adept.md` for an intermediate tutorial
   - Reference `docs/Specs/language_specification.md` for the complete spec

2. **Try examples:**
   ```bash
   cd examples
   uv run python ../fxc.py hello.fx && ./hello
   uv run python ../fxc.py bit_fields.fx && ./bit_fields
   ```

3. **Write your first program:**
   ```bash
   subl myprogram.fx
   # Write some Flux code
   uv run python fxc.py myprogram.fx
   ./myprogram
   ```

4. **Explore the standard library:**
   ```bash
   ls src/stdlib/
   ```

5. **Run the test suite:**
   ```bash
   uv run pytest
   ```

6. **Join the community:**
   - [Discord](https://discord.gg/wVAm2E6ymf) - Ask questions, share projects
   - [GitHub](https://github.com/kvthweatt/Flux) - Report issues, contribute

## This Manual Setup Helps You:

- Understand how to compile Flux programs
- Use familiar, standard macOS/Unix tools
- Keep your development environment simple and transparent
- Debug issues effectively when they arise

macOS's Unix foundation aligns naturally with Flux's design. With Homebrew handling the LLVM toolchain and `uv` managing the Python environment, you're running the same stack the project itself uses — clean, reproducible, and easy to debug when something goes wrong.

As Flux matures toward self-hosting, we'll eventually provide a Flux-written installer - demonstrating the language's systems programming capabilities while maintaining this same transparency.

Happy Flux development!
