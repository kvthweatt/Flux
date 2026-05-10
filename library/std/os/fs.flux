module std.os.fs

import std.os.path
#ifdef WINDOWS
import std.os.platform.windows as platform
#else
import std.os.platform.unix as platform
#endif

pub def makedirs(path: string, exist_ok: bool = false) -> void {
    if path == "" {
        return
    }

    let parts = path.split(platform.sep())
    let mut current = ""

    for part in parts {
        if part == "" {
            continue
        }

        if current == "" {
            current = part
        } else {
            current = path.join([current, part])
        }

        if !platform.exists(current) {
            platform.mkdir(current, false)
        } else if !exist_ok {
            // If it exists but is not a directory, raise error
            if !platform.isdir(current) {
                panic("Path exists and is not a directory: " + current)
            }
        }
    }
}