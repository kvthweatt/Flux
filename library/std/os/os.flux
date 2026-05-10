module std.os

import std.os.fs
import std.os.path
import std.os.env

// Platform-specific bindings
#ifdef WINDOWS
import std.os.platform.windows as platform
#else
import std.os.platform.unix as platform
#endif

// ----- Current Working Directory -----
pub def getcwd() -> string {
    return platform.getcwd()
}

pub def chdir(path: string) -> void {
    platform.chdir(path)
}

// ----- Directory Listing -----
pub def listdir(path: string = ".") -> string[] {
    return platform.listdir(path)
}

// ----- Directory Operations -----
pub def mkdir(path: string, parents: bool = false, exist_ok: bool = false) -> void {
    if parents {
        fs.makedirs(path, exist_ok)
    } else {
        platform.mkdir(path, exist_ok)
    }
}

pub def makedirs(path: string, exist_ok: bool = false) -> void {
    fs.makedirs(path, exist_ok)
}

pub def rmdir(path: string) -> void {
    platform.rmdir(path)
}

// ----- File Operations -----
pub def remove(path: string) -> void {
    platform.remove(path)
}

pub def rename(src: string, dst: string) -> void {
    platform.rename(src, dst)
}

pub def replace(src: string, dst: string) -> void {
    platform.replace(src, dst)
}

// ----- File Tests -----
pub def exists(path: string) -> bool {
    return platform.exists(path)
}

pub def isfile(path: string) -> bool {
    return platform.isfile(path)
}

pub def isdir(path: string) -> bool {
    return platform.isdir(path)
}

pub def getsize(path: string) -> u64 {
    return platform.getsize(path)
}

// ----- Environment Variables -----
pub def getenv(key: string, default_value: string = "") -> string {
    return env.getenv(key, default_value)
}

pub def setenv(key: string, value: string) -> void {
    env.setenv(key, value)
}

pub def unsetenv(key: string) -> void {
    env.unsetenv(key)
}

pub def environ() -> map[string, string] {
    return env.environ()
}

// ----- Path Utilities -----
pub def join(parts: string[]) -> string {
    return path.join(parts)
}

pub def basename(p: string) -> string {
    return path.basename(p)
}

pub def dirname(p: string) -> string {
    return path.dirname(p)
}

pub def abspath(p: string) -> string {
    return path.abspath(p)
}

pub def normpath(p: string) -> string {
    return path.normpath(p)
}

pub def splitext(p: string) -> (string, string) {
    return path.splitext(p)
}