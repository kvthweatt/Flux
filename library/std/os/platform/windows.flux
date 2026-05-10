module std.os.platform.windows

extern "C" {
    fn _getcwd(buf: *u8, size: i32) -> *u8
    fn _chdir(path: *u8) -> i32
    fn _mkdir(path: *u8) -> i32
    fn _rmdir(path: *u8) -> i32
    fn remove(path: *u8) -> i32
    fn rename(old: *u8, new: *u8) -> i32
    fn getenv(name: *u8) -> *u8
    fn _putenv(env: *u8) -> i32
}

pub def sep() -> string { return "\\" }

pub def getcwd() -> string {
    let buf = alloc(4096)
    if _getcwd(buf, 4096) == null {
        panic("getcwd failed")
    }
    return string_from_c(buf)
}

pub def chdir(path: string) -> void {
    if _chdir(c_str(path)) != 0 {
        panic("chdir failed: " + path)
    }
}

pub def mkdir(path: string, exist_ok: bool) -> void {
    if _mkdir(c_str(path)) != 0 && !exist_ok {
        panic("mkdir failed: " + path)
    }
}

pub def rmdir(path: string) -> void {
    if _rmdir(c_str(path)) != 0 {
        panic("rmdir failed: " + path)
    }
}

pub def remove(path: string) -> void {
    if remove(c_str(path)) != 0 {
        panic("remove failed: " + path)
    }
}

pub def rename(src: string, dst: string) -> void {
    if rename(c_str(src), c_str(dst)) != 0 {
        panic("rename failed")
    }
}