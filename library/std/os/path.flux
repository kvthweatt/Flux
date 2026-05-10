module std.os.path

#ifdef WINDOWS
import std.os.platform.windows as platform
#else
import std.os.platform.unix as platform
#endif

pub def join(parts: string[]) -> string {
    let sep = platform.sep()
    let mut result = ""

    for part in parts {
        if part == "" {
            continue
        }

        if result == "" {
            result = part
        } else {
            if !result.ends_with(sep) {
                result += sep
            }
            result += part.trim_start(sep)
        }
    }
    return result
}

pub def basename(path: string) -> string {
    let sep = platform.sep()
    let parts = path.split(sep)
    return parts[-1]
}

pub def dirname(path: string) -> string {
    let sep = platform.sep()
    let parts = path.split(sep)
    if parts.len() <= 1 {
        return "."
    }
    return join(parts[0:-1])
}

pub def normpath(path: string) -> string {
    let sep = platform.sep()
    let mut stack: string[] = []

    for part in path.split(sep) {
        if part == "" || part == "." {
            continue
        } else if part == ".." {
            if stack.len() > 0 {
                stack.pop()
            }
        } else {
            stack.push(part)
        }
    }

    let prefix = path.starts_with(sep) ? sep : ""
    return prefix + join(stack)
}

pub def abspath(path: string) -> string {
    if path.starts_with(platform.sep()) {
        return normpath(path)
    }
    let cwd = platform.getcwd()
    return normpath(join([cwd, path]))
}

pub def splitext(path: string) -> (string, string) {
    let base = basename(path)
    let idx = base.last_index_of(".")
    if idx == -1 {
        return (path, "")
    }

    let root = path[0 : path.len() - (base.len() - idx)]
    let ext = base[idx:]
    return (root, ext)
}