module std.os.env

#ifdef WINDOWS
import std.os.platform.windows as platform
#else
import std.os.platform.unix as platform
#endif

pub def getenv(key: string, default_value: string = "") -> string {
    let value = platform.getenv(key)
    if value == "" {
        return default_value
    }
    return value
}

pub def setenv(key: string, value: string) -> void {
    platform.setenv(key, value)
}

pub def unsetenv(key: string) -> void {
    platform.unsetenv(key)
}

pub def environ() -> map[string, string] {
    return platform.environ()
}