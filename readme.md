<h1 align="center">Flux</h1>

<h2 align="center"><i>A general purpose, statically typed, compiled language with first-class data manipulation.</i></h2>

<p align="center">
    <img width="512" height="512" alt="image" src="https://github.com/user-attachments/assets/58da57a7-1924-48a2-ba29-c2040d9343eb" />
</p>

## What is Flux?

Flux is a new programming language that combines the performance and power of C with the readability of Python.   
Flux resembles the C-family of languages.  
It is neither C, nor a derivative of C.  
It has a fundamentally different type system while still being C ABI compatible.

## What does it look like?
- Here's an example of shifting and masking, unavoidable in other languages turned into a one-liner in Flux
<p align="center">
<img width="800" height="449" alt="FluxRefactor-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/21ef2566-f213-4e08-b601-780b45eba2e7" />
</p>

**Characteristics:**
- Unique type system with endianness and alignment baked into types
- Manual memory management
- Compiler that stays out of your way
- First class data manipulation features
- Consistent grammar and syntax constructs throughout
- Rich operator collection with distinct bitwise set
- Everything stack allocated unless otherwise specified
- Everything is zero initialized on declaration unless otherwise specified
- Custom infix operator support
- Templates without SFINAE or noise at call sites
- Opt-in ownership without a borrow checker
- Designed so you don't need to repeat yourself so much when coding


## Design Philosophy

Flux follows a "high-trust" model:
- The language provides powerful tools
- The programmer is responsible for using them correctly
- Explicit is better than implicit
- Performance and control over safety guarantees

## Ideal Use Cases

Flux is well-suited for:
- **Embedded systems** - Direct hardware register access
- **Network protocols** - Zero-copy packet parsing
- **File format handling** - Binary data interpretation
- **Game engines** - Memory-efficient entity systems
- **Device drivers** - Memory-mapped I/O
- **Performance-critical code** - When you need C-level control

## Current Status

Flux is in active development. The syntax and grammar will not change. The [standard library](https://github.com/kvthweatt/FluxLang/tree/main/src/stdlib) is the current focus.

**What exists:**
- [Language Specification](https://github.com/kvthweatt/FluxLang/blob/main/docs/Specs/language_specification.md)
- [Keyword Reference](https://github.com/kvthweatt/FluxLang/blob/main/docs/keyword_reference.md)
- A Flux [Style Guide](https://github.com/kvthweatt/FluxLang/blob/main/docs/style_guide.md)
- Tutorials for [Beginner](https://github.com/kvthweatt/FluxLang/blob/main/docs/learn_flux_intro.md) and [Adept](https://github.com/kvthweatt/FluxLang/blob/main/docs/learn_flux_adept.md) Programmers
- Base compiler ✅
- An LSP ✅
- A Package Manager (FPM) ✅

**What's being built:**
- Standard Library (expanding the existing)
- Build Tooling
- IDE

## Getting Involved

- **Discord:** [Join the Flux community](https://discord.gg/wVAm2E6ymf)
- **Contribute:** The project welcomes contributors
- **Feedback:** Share your thoughts on language design

## Learning Resources

- **[Language Specification](docs/Specs/language_specification.md)** - Complete language reference  
- **[Getting Started Guide](docs/learn_flux_intro.md)** - Tutorial for new users  
- **[Examples](examples/)** - Real-world Flux programs  
- **[Windows Setup Guide](docs/SetupGuides/windows_setup_guide.md)**  
- **[Linux Setup Guide](docs/SetupGuides/linux_setup_guide.md)** 

## Requirements:
- Python v3.12 or higher
- LLVM v21 or higher

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=kvthweatt/FluxLang&type=date&legend=top-left)](https://www.star-history.com/#kvthweatt/FluxLang&type=date&legend=top-left)


## Example: Complete Program

```
#import "standard.fx";

struct Packet
{
    data{8} type;
    data{16} length;
    data{32} timestamp;
};

def main() -> int
{
    byte[7] bytes = [0x01, 0x00, 0x20, 0x5F, 0x12, 0x34, 0x56];
    Packet pkt from bytes;
    
    println(f"Type: {int(pkt.type)}");
    println(f"Length: {pkt.length}");
    println(f"Time: {pkt.timestamp}");
    
    return 0;
};
```

**Note:** Flux is a systems programming language that assumes you understand memory management and low-level programming concepts. If you're new to systems programming, work through the tutorial documentation carefully.

## 🤝 **Contributing**

Flux is actively developed and approaching self-hosting.  

**Current Status:** Working compiler, real programs running.  
There are still some small compiler issues here and there.

## ⚖️ **License**

Copyright (C) 2024 Karac Von Thweatt. All rights reserved.