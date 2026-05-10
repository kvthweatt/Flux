import os
from pathlib import Path
from typing import Set, Dict, Optional, List

FLUXC_SRCDIR = Path(os.environ.get("FLUXC_SRCDIR", Path(__file__).parent)).resolve()

class FXPreprocessor:
    def __init__(self, source_file, compiler_constants=None):
        self.source_file = source_file
        self.processed_files: Set[str] = set()
        self.output_lines = []
        self.constants: Dict[str, str] = {}
        self.lib_dirs: List[str] = []
        # Maps each output line index (0-based) -> (filename, local_line_number 1-based)
        self.line_map: List[tuple] = []

        if compiler_constants:
            self.constants.update(compiler_constants)
    
    def process(self) -> str:
        """Main processing pipeline"""
        # Step 1: Process all imports and build content in memory
        self._process_file(self.source_file)
        
        # Step 2: Build combined source
        combined_source = '\n'.join(self.output_lines)
        
        # Step 4: Keep replacing constants until no more replacements occur
        replaced = True
        iteration = 0
        while replaced:
            iteration += 1
            print(f"[PREPROCESSOR] constant substitution passes: {iteration}")
            replaced = False
            lines = combined_source.split('\n')
            new_lines = []
            
            for line in lines:
                new_line = self._substitute_constants(line)
                if new_line != line:
                    replaced = True
                new_lines.append(new_line)
            
            combined_source = '\n'.join(new_lines)
        ending = "es." if iteration > 1 else "."
        print(f"[PREPROCESSOR] Completed after {iteration} constant pass{ending}")
        
        # Step 5: Write to build/tmp.fx
        build_dir = Path("build")
        build_dir.mkdir(exist_ok=True)
        output_file = build_dir / "tmp.fx"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(combined_source)
        
        print(f"[PREPROCESSOR] Generated: {output_file}")
        print(f"[PREPROCESSOR] Processed {len(self.processed_files)} file(s)")
        
        return combined_source
    
    def _strip_comments(self, content: str) -> str:
        """Strip all comments from content: // and /// ... ///
        String literals (double or single quoted) are passed through unchanged
        so that URLs like https:// inside strings are not treated as comments."""
        result = []
        i = 0
        n = len(content)

        while i < n:
            c = content[i]

            # ── String literal: skip over it intact ──────────────────────────
            if c == '"' or c == "'":
                quote = c
                result.append(c)
                i += 1
                while i < n:
                    sc = content[i]
                    result.append(sc)
                    if sc == '\\' and i + 1 < n:
                        # Escaped character — consume both chars so an escaped
                        # quote doesn't end the string prematurely.
                        i += 1
                        result.append(content[i])
                    elif sc == quote:
                        break
                    i += 1
                i += 1
                continue

            # ── Block comment: /// ... /// ────────────────────────────────────
            if i + 2 < n and c == '/' and content[i+1] == '/' and content[i+2] == '/':
                i += 3
                while i < n:
                    if i + 2 < n and content[i] == '/' and content[i+1] == '/' and content[i+2] == '/':
                        i += 3
                        break
                    i += 1
                continue

            # ── Line comment: // ──────────────────────────────────────────────
            if i + 1 < n and c == '/' and content[i+1] == '/':
                while i < n and content[i] != '\n':
                    i += 1
                continue

            # ── Regular character ─────────────────────────────────────────────
            result.append(c)
            i += 1

        return ''.join(result)
    
    def _resolve_path(self, filepath: str) -> Optional[Path]:
        """Resolve import path"""
        path = Path(filepath)
        
        # If it exists as given, return it
        if path.exists():
            return path
        
        # Try relative to current directory
        cwd = FLUXC_SRCDIR
        
        # Common locations to check
        locations = [
            filepath,
            cwd / "src" / "stdlib" / filepath,
            cwd / "src" / "stdlib" / "runtime" / filepath,
            cwd / "src" / "stdlib" / "functions" / filepath,
            cwd / "src" / "stdlib" / "builtins" / filepath,
            cwd / "src" / "stdlib" / "utility" / filepath
        ]
        
        # Search all package subfolders under CWD/.fpm/packages/ recursively
        fpm_packages_dir = Path.cwd() / ".fpm" / "packages"
        if fpm_packages_dir.is_dir():
            for package_dir in sorted(fpm_packages_dir.iterdir()):
                if package_dir.is_dir():
                    # Direct match inside the package root
                    locations.append(package_dir / filepath)
                    # Also search all subdirectories within the package recursively
                    for sub_dir in sorted(package_dir.rglob("*")):
                        if sub_dir.is_dir():
                            locations.append(sub_dir / filepath)
        
        # Also search any directories added via #dir
        for lib_dir in self.lib_dirs:
            locations.append(Path(lib_dir) / filepath)
        
        for location in locations:
            loc_path = Path(location)
            if loc_path.exists():
                return loc_path
        
        return None
    
    def _process_file(self, filepath: str):
        """Process a file and its imports"""
        resolved_path = self._resolve_path(filepath)
        
        if not resolved_path:
            raise FileNotFoundError(f"Could not find import: {filepath}")
        
        # Avoid circular imports
        abs_path = str(resolved_path.resolve())
        if abs_path in self.processed_files:
            return
        
        self.processed_files.add(abs_path)
        print(f"[PREPROCESSOR] Processing: {filepath}")
        
        # Read the file and strip comments immediately
        with open(resolved_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Strip all comments before processing
        content = self._strip_comments(content)
        
        # Enforce semicolons on directives before processing
        for lineno, raw_line in enumerate(content.splitlines(), start=1):
            s = raw_line.strip()
            if s.startswith("#import") or s.startswith("#warn") or s.startswith("#stop") or s.startswith("#def") or s.startswith("#dir"):
                if not s.endswith(';'):
                    directive = s.split()[0]
                    raise SyntaxError(f"[PREPROCESSOR] {directive} directive missing semicolon in {filepath} at line {lineno}")
        
        # Process line by line, tracking current file and local line number
        lines = content.splitlines()
        prev_current_file = getattr(self, '_current_file', None)
        prev_current_lines = getattr(self, '_current_lines', None)
        self._current_file = str(resolved_path)
        self._current_lines = lines
        i = 0
        while i < len(lines):
            self._current_local_lineno = i + 1  # 1-based
            i = self._process_line(lines, i)
        self._current_file = prev_current_file
        self._current_lines = prev_current_lines
    
    def _process_line(self, lines: List[str], i: int) -> int:
        """Process a single line, return next line index"""
        line = lines[i]
        
        # Skip empty lines (we'll handle removal at the end)
        if not line.strip():
            return i + 1
        
        stripped = line.strip()
        
        # Check for #dir
        if stripped.startswith("#dir"):
            if not stripped.rstrip().endswith(';'):
                raise SyntaxError(f"[PREPROCESSOR] #dir directive missing semicolon at line {i + 1}")
            start_idx = line.find('"')
            if start_idx != -1:
                end_idx = line.find('"', start_idx + 1)
                if end_idx != -1:
                    dir_path = line[start_idx + 1:end_idx]
                    # Normalize: replace backslashes with forward slashes
                    dir_path = dir_path.replace('\\', '/')
                    if dir_path not in self.lib_dirs:
                        self.lib_dirs.append(dir_path)
                        print(f"[PREPROCESSOR] Added library directory: {dir_path}")
            return i + 1
        
        # Check for #def
        if stripped.startswith("#def"):
            # Find the semicolon
            semicolon_pos = line.find(';')
            if semicolon_pos == -1:
                semicolon_pos = len(line)
            
            # Extract the part up to semicolon
            constant_line = line[:semicolon_pos].strip()
            
            parts = constant_line.split()
            if len(parts) >= 3:
                constant_name = parts[1]
                # Join the rest as the value (skip #def and constant_name)
                constant_value = ' '.join(parts[2:]).strip()
                
                # Remove any trailing semicolon if it's still there
                if constant_value.endswith(';'):
                    constant_value = constant_value.rstrip(';').strip()
                    
                self.constants[constant_name] = constant_value
                print(f"[PREPROCESSOR] Defined constant: {constant_name} = {constant_value}")
            return i + 1
        
        # Check for #ifdef
        if stripped.startswith("#ifdef"):
            parts = line.split()
            if len(parts) >= 2:
                constant_name = parts[1]
                return self._process_conditional_block(lines, i, constant_name, False)
        
        # Check for #ifndef
        if stripped.startswith("#ifndef"):
            parts = line.split()
            if len(parts) >= 2:
                constant_name = parts[1]
                return self._process_conditional_block(lines, i, constant_name, True)
        
        # Check for import
        if stripped.startswith("#import"):
            if not stripped.rstrip().endswith(';'):
                raise SyntaxError(f"[PREPROCESSOR] #import directive missing semicolon at line {i + 1}")
            # Extract all quoted filenames
            import_files = []
            
            # Find all quoted strings in the line (comments already stripped)
            start_idx = line.find('"')
            while start_idx != -1:
                end_idx = line.find('"', start_idx + 1)
                if end_idx != -1:
                    import_file = line[start_idx + 1:end_idx].strip()
                    import_files.append(import_file)
                    start_idx = line.find('"', end_idx + 1)
                else:
                    break
            
            # Process each import file in order
            for import_file in import_files:
                self._process_file(import_file)
            
            return i + 1
        
        # Check for #warn
        if stripped.startswith("#warn"):
            if not stripped.rstrip().endswith(';'):
                raise SyntaxError(f"[PREPROCESSOR] #warn directive missing semicolon at line {i + 1}")
            start_idx = line.find('"')
            if start_idx != -1:
                end_idx = line.find('"', start_idx + 1)
                if end_idx != -1:
                    message = line[start_idx + 1:end_idx]
                    print(f"[PREPROCESSOR] {message}")
            return i + 1
        
        # Check for #stop
        if stripped.startswith("#stop"):
            if not stripped.rstrip().endswith(';'):
                raise SyntaxError(f"[PREPROCESSOR] #stop directive missing semicolon at line {i + 1}")
            start_idx = line.find('"')
            if start_idx != -1:
                end_idx = line.find('"', start_idx + 1)
                if end_idx != -1:
                    message = line[start_idx + 1:end_idx]
                    print(f"[PREPROCESSOR] {message}")
            print("Compilation failed, preprocessor stopped by constant.")
            raise SystemExit(1)
        
        # Check for #endif - skip it
        if stripped.startswith("#endif;"):
            return i + 1
        
        # Check for #else - skip it (handled in conditional processing)
        if stripped == "#else":
            return i + 1
        
        # Regular line - do constant substitution
        processed_line = self._substitute_constants(line)
        self.line_map.append((getattr(self, '_current_file', self.source_file), self._current_local_lineno))
        self.output_lines.append(processed_line)
        return i + 1
    
    def _process_conditional_block(self, lines: List[str], start_i: int, constant_name: str, is_ifndef: bool) -> int:
        """Process an #ifdef/#ifndef block and return next line index after #endif"""
        # Get constant value
        constant_value = self.constants.get(constant_name)
        
        # Evaluate condition
        if is_ifndef:
            condition_true = constant_value is None or constant_value == '0'
        else:
            condition_true = constant_value is not None and constant_value != '0'
        i = start_i + 1
        depth = 1
        in_else = False
        else_seen = False
        
        # Store lines that should be included, paired with their original local line numbers
        lines_to_include = []
        origins_to_include = []  # parallel list: local line number (1-based) for each entry
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Handle nested conditionals
            if stripped.startswith("#ifdef") or stripped.startswith("#ifndef"):
                depth += 1
            
            # Check for #else at our depth level
            if stripped == "#else" and depth == 1:
                if else_seen:
                    raise SyntaxError("Multiple #else directives in same conditional block")
                else_seen = True
                in_else = True
                i += 1
                continue
            
            # Check for #endif
            if stripped.startswith("#endif;"):
                depth -= 1
                if depth == 0:
                    # End of our block - process collected lines
                    if lines_to_include:
                        j = 0
                        while j < len(lines_to_include):
                            self._current_local_lineno = origins_to_include[j]
                            j = self._process_line(lines_to_include, j)
                    return i + 1
            
            # Collect lines based on condition
            if depth > 1:
                # Inside nested block - always include
                if (condition_true and not in_else) or (not condition_true and in_else):
                    lines_to_include.append(line)
                    origins_to_include.append(i + 1)
            else:
                # Our depth level
                if (condition_true and not in_else) or (not condition_true and in_else):
                    lines_to_include.append(line)
                    origins_to_include.append(i + 1)
            
            i += 1
        
        raise SyntaxError(f"Unclosed conditional block starting at line {start_i + 1}")
    
    def _substitute_constants(self, line: str) -> str:
        """Simple constant substitution - replace constant names with their values"""
        if not line or line.strip() == ';':
            return line
        
        # Split line into tokens, preserving whitespace structure
        result_parts = []
        in_quotes = False
        current_token = ""
        
        for char in line:
            if char == '"':
                in_quotes = not in_quotes
                current_token += char
            elif char.isspace() or char in '.,;:()[]{}+-*/%=!<>|&^~':
                # End of token
                if current_token:
                    # Check if token is a constant
                    if not in_quotes and current_token in self.constants:
                        # Get constant value and strip trailing semicolon if present
                        constant_value = self.constants[current_token]
                        # Remove trailing semicolon if it's at the end
                        if constant_value.endswith(';'):
                            constant_value = constant_value.rstrip(';').strip()
                        result_parts.append(constant_value)
                    else:
                        result_parts.append(current_token)
                    current_token = ""
                result_parts.append(char)
            else:
                current_token += char
        
        # Handle last token
        if current_token:
            if not in_quotes and current_token in self.constants:
                constant_value = self.constants[current_token]
                # Remove trailing semicolon if it's at the end
                if constant_value.endswith(';'):
                    constant_value = constant_value.rstrip(';').strip()
                result_parts.append(constant_value)
            else:
                result_parts.append(current_token)
        
        return ''.join(result_parts)


# Usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python preprocessor.py <source_file.fx>")
        sys.exit(1)
    
    preprocessor = FXPreprocessor(sys.argv[1])
    preprocessor.process()