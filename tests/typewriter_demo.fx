// typewriter_demo.fx
// Typewriter animation stepping through:
//   1. macro macNZ
//   2. contract ctNonZero
//   3. contract ctGreaterThanZero
//   4. operator overload with contracts
//   5. def main() usage example

#import "standard.fx";
#import "console.fx";

using standard::io::console;

// ============================================================================
// type_char — write one char at (x,y), advance cursor, sleep.
// ============================================================================

def type_char(Console* con, i16* x, i16* y, byte ch, i16 attr, i16 w) -> void
{
    if (ch == (byte)'\n')
    {
        *x = (i16)0;
        *y = (i16)(*y + (i16)1);
        Sleep(20);
        return;
    };

    byte[2] buf;
    buf[0] = ch;
    buf[1] = (byte)0;
    con.write_at_colored(*x, *y, attr, @buf[0]);

    *x = (i16)(*x + (i16)1);
    if (*x >= w)
    {
        *x = (i16)0;
        *y = (i16)(*y + (i16)1);
    };

    Sleep(38);
};

// ============================================================================
// type_str — type a null-terminated token with one attribute.
// ============================================================================

def type_str(Console* con, i16* x, i16* y, byte* src, i16 attr, i16 w) -> void
{
    int i = 0;
    while (src[i] != (byte)0)
    {
        type_char(con, x, y, src[i], attr, w);
        i = i + 1;
    };
};

// ============================================================================
// wait_key — show hint at cy+1, pause, clear hint, advance cy by 1.
// ============================================================================

def wait_key(Console* con, i16* cx, i16* cy) -> void
{
    i16 hint_y = (i16)(*cy + (i16)1);
    con.write_at_colored((i16)0, hint_y, (i16)0x0008, "  [press any key]");
    con.cursor_set((i16)0, hint_y);
    con.cursor_visible(true);
    con.set_attr((i16)0x0007);

    system("pause > nul");

    con.cursor_visible(false);
    con.clear_line(hint_y);

    // blank separator line before next block
    *cy = (i16)(*cy + (i16)1);
    *cx = (i16)0;
};

// ============================================================================
// main
// ============================================================================

def main() -> int
{
    Console con;
    con.__init();

    i64* handle_ptr = (i64*)@con;
    handle_ptr[0] = WIN_STDOUT_HANDLE;
    con.refresh_size();

    i16 w = con.get_width();

    con.cursor_visible(false);
    con.clear_screen();

    i16 COL_KEYWORD = (i16)0x000B;  // cyan
    i16 COL_NAME    = (i16)0x000E;  // yellow
    i16 COL_PUNCT   = (i16)0x000F;  // white
    i16 COL_STRING  = (i16)0x000A;  // green
    i16 COL_PARAM   = (i16)0x000D;  // magenta
    i16 COL_COMMENT = (i16)0x0008;  // dark gray
    i16 COL_TYPE    = (i16)0x000C;  // red
    i16 COL_DEFAULT = (i16)0x0007;  // gray

    i16 cx = (i16)0,
        cy = (i16)0;

    // =========================================================================
    // Phase 1: macro macNZ(x) { x != 0 };
    // =========================================================================

    type_str(@con, @cx, @cy, "macro",  COL_KEYWORD, w);
    type_str(@con, @cx, @cy, " macNZ", COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "x",      COL_PARAM,   w);
    type_str(@con, @cx, @cy, ")",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",     COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "{",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n    ", COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "x",      COL_PARAM,   w);
    type_str(@con, @cx, @cy, " != ",   COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "0",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",     COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "};",     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",     COL_DEFAULT, w);

    wait_key(@con, @cx, @cy);

    // =========================================================================
    // Phase 2: contract ctNonZero(a,b) { ... };
    // =========================================================================

    type_str(@con, @cx, @cy, "contract",   COL_KEYWORD, w);
    type_str(@con, @cx, @cy, " ctNonZero", COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",          COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "a",          COL_PARAM,   w);
    type_str(@con, @cx, @cy, ",",          COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "b",          COL_PARAM,   w);
    type_str(@con, @cx, @cy, ")",          COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n{\n    ",  COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "assert",                COL_KEYWORD, w);
    type_str(@con, @cx, @cy, "(",                     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "macNZ",                 COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",                     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "a",                     COL_PARAM,   w);
    type_str(@con, @cx, @cy, "), ",                   COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\"a must be nonzero\"", COL_STRING,  w);
    type_str(@con, @cx, @cy, ");",                    COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n    ",                COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "assert",                COL_KEYWORD, w);
    type_str(@con, @cx, @cy, "(",                     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "macNZ",                 COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",                     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "b",                     COL_PARAM,   w);
    type_str(@con, @cx, @cy, "), ",                   COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\"b must be nonzero\"", COL_STRING,  w);
    type_str(@con, @cx, @cy, ");",                    COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",                    COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "};",                    COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",                    COL_DEFAULT, w);

    wait_key(@con, @cx, @cy);

    // =========================================================================
    // Phase 3: contract ctGreaterThanZero(a,b) { ... };
    // =========================================================================

    type_str(@con, @cx, @cy, "contract",            COL_KEYWORD, w);
    type_str(@con, @cx, @cy, " ctGreaterThanZero",  COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",                   COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "a",                   COL_PARAM,   w);
    type_str(@con, @cx, @cy, ",",                   COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "b",                   COL_PARAM,   w);
    type_str(@con, @cx, @cy, ")",                   COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n{\n    ",            COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "assert",                          COL_KEYWORD, w);
    type_str(@con, @cx, @cy, "(",                               COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "a",                               COL_PARAM,   w);
    type_str(@con, @cx, @cy, " > ",                             COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "0",                               COL_PUNCT,   w);
    type_str(@con, @cx, @cy, ", ",                              COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\"a must be greater than zero\"", COL_STRING,  w);
    type_str(@con, @cx, @cy, ");",                              COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n    ",                          COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "assert",                          COL_KEYWORD, w);
    type_str(@con, @cx, @cy, "(",                               COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "b",                               COL_PARAM,   w);
    type_str(@con, @cx, @cy, " > ",                             COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "0",                               COL_PUNCT,   w);
    type_str(@con, @cx, @cy, ", ",                              COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\"b must be greater than zero\"", COL_STRING,  w);
    type_str(@con, @cx, @cy, ");",                              COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",                              COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "};",                              COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",                              COL_DEFAULT, w);

    wait_key(@con, @cx, @cy);

    // =========================================================================
    // Phase 4: operator<T,K> (T t, K k)[+] -> int
    //          :     ctNonZero(c, d),
    //          ctGreaterThanZero(e, f)
    //          { return t + k; };
    // =========================================================================

    type_str(@con, @cx, @cy, "operator",          COL_KEYWORD, w);
    type_str(@con, @cx, @cy, "<",                 COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "T",                 COL_TYPE,    w);
    type_str(@con, @cx, @cy, ", ",                COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "K",                 COL_TYPE,    w);
    type_str(@con, @cx, @cy, ">",                 COL_PUNCT,   w);
    type_str(@con, @cx, @cy, " (",                COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "T",                 COL_TYPE,    w);
    type_str(@con, @cx, @cy, " t",                COL_PARAM,   w);
    type_str(@con, @cx, @cy, ", ",                COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "K",                 COL_TYPE,    w);
    type_str(@con, @cx, @cy, " k",                COL_PARAM,   w);
    type_str(@con, @cx, @cy, ")[",                COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "+",                 COL_KEYWORD, w);
    type_str(@con, @cx, @cy, "] ",                COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "->",                COL_PUNCT,   w);
    type_str(@con, @cx, @cy, " int",              COL_TYPE,    w);
    type_str(@con, @cx, @cy, "\n",                COL_DEFAULT, w);
    // contract line 1
    type_str(@con, @cx, @cy, ":",                       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "     ctNonZero",           COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",                       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "  c",                     COL_PARAM,   w);
    type_str(@con, @cx, @cy, ",   ",                    COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "d",                       COL_PARAM,   w);
    type_str(@con, @cx, @cy, "),",                      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, " // works on arity and position, not identifier name.",
                                                           COL_COMMENT, w);
    type_str(@con, @cx, @cy, "\n",                      COL_DEFAULT, w);
    // contract line 2
    type_str(@con, @cx, @cy, "ctGreaterThanZero",       COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",                       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "e",                       COL_PARAM,   w);
    type_str(@con, @cx, @cy, ",   ",                    COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "f",                       COL_PARAM,   w);
    type_str(@con, @cx, @cy, ")",                       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",                      COL_DEFAULT, w);
    // body
    type_str(@con, @cx, @cy, "{\n    ",                 COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "return",                  COL_KEYWORD, w);
    type_str(@con, @cx, @cy, " t",                      COL_PARAM,   w);
    type_str(@con, @cx, @cy, " + ",                     COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "k",                       COL_PARAM,   w);
    type_str(@con, @cx, @cy, ";\n",                     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "};",                      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",                      COL_DEFAULT, w);

    wait_key(@con, @cx, @cy);

    // =========================================================================
    // Phase 5: def main() -> int { ... };
    // =========================================================================

    type_str(@con, @cx, @cy, "def",     COL_KEYWORD, w);
    type_str(@con, @cx, @cy, " main",   COL_NAME,    w);
    type_str(@con, @cx, @cy, "()",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, " ->",     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, " int",    COL_TYPE,    w);
    type_str(@con, @cx, @cy, "\n{\n    ", COL_DEFAULT, w);

    // myStru<int> ms = {10,20};
    type_str(@con, @cx, @cy, "myStru",  COL_NAME,    w);
    type_str(@con, @cx, @cy, "<",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "int",     COL_TYPE,    w);
    type_str(@con, @cx, @cy, ">",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, " ms",     COL_PARAM,   w);
    type_str(@con, @cx, @cy, " = ",     COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "{",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "10",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, ",",       COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "20",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "};",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n\n    ", COL_DEFAULT, w);

    // int x = foo(ms, 3);
    type_str(@con, @cx, @cy, "int",     COL_TYPE,    w);
    type_str(@con, @cx, @cy, " x",      COL_PARAM,   w);
    type_str(@con, @cx, @cy, " = ",     COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "foo",     COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "ms",      COL_PARAM,   w);
    type_str(@con, @cx, @cy, ", ",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "3",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, ");",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n\n    ", COL_DEFAULT, w);

    // i32 y = bar(ms, 3);
    type_str(@con, @cx, @cy, "i32",     COL_TYPE,    w);
    type_str(@con, @cx, @cy, " y",      COL_PARAM,   w);
    type_str(@con, @cx, @cy, " = ",     COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "bar",     COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "ms",      COL_PARAM,   w);
    type_str(@con, @cx, @cy, ", ",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "3",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, ");",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n\n    ", COL_DEFAULT, w);

    // println(x + y);
    type_str(@con, @cx, @cy, "println", COL_NAME,    w);
    type_str(@con, @cx, @cy, "(",       COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "x",       COL_PARAM,   w);
    type_str(@con, @cx, @cy, " + ",     COL_DEFAULT, w);
    type_str(@con, @cx, @cy, "y",       COL_PARAM,   w);
    type_str(@con, @cx, @cy, ");",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n\n    ", COL_DEFAULT, w);

    // return 0;
    type_str(@con, @cx, @cy, "return",  COL_KEYWORD, w);
    type_str(@con, @cx, @cy, " 0",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, ";\n",     COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "};",      COL_PUNCT,   w);
    type_str(@con, @cx, @cy, "\n",      COL_DEFAULT, w);

    // =========================================================================
    // Done
    // =========================================================================

    con.set_attr((i16)0x0007);
    con.cursor_set(cx, cy);
    con.cursor_visible(true);

    return 0;
};
