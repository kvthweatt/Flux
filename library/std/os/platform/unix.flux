module std.os.platform.unix

extern "C" {
    fn getcwd(buf: *u8, size: usize) -> *u8
    fn chdir(path: *u8) -> i32
    fn mkdir(path: *u8, mode: u32) -> i32
    fn rmdir(path: *u8) -> i32
    fn unlink(path: *u8) -> i32
    fn rename(old: *u8, new: *u8) -> i32
    fn stat(path: *u8, st: *Stat) -> i32
    fn getenv(name: *u8) -> *u8
    fn setenv(name: *u8, value: *u8, overwrite: i32) -> i32
    fn unsetenv(name: *u8) -> i32
}

pub def sep() -> string { return "/" }

// Simplified implementations (real runtime would include proper memory handling)

pub def getcwd() -> string {
    let buf = alloc(4096)
    if getcwd(buf, 4096) == null {
        panic("getcwd failed")
    }
    return string_from_c(buf)
}

pub def chdir(path: string) -> void {
    if chdir(c_str(path)) != 0 {
        panic("chdir failed: " + path)
    }
}

pub def mkdir(path: string, exist_ok: bool) -> void {
    if mkdir(c_str(path), 0o755) != 0 && !exist_ok {
        panic("mkdir failed: " + path)
    }
}

pub def rmdir(path: string) -> void {
    if rmdir(c_str(path)) != 0 {
        panic("rmdir failed: " + path)
    }
}

pub def remove(path: string) -> void {
    if unlink(c_str(path)) != 0 {
        panic("remove failed: " + path)
    }
}

pub def rename(src: string, dst: string) -> void {
    if rename(c_str(src), c_str(dst)) != 0 {
        panic("rename failed")
    }
}

pub def replace(src: string, dst: string) -> void {
    rename(src, dst)
}

// File tests and environment functions would follow similar patterns.