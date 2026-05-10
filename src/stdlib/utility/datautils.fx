// Author: Karac V. Thweatt

// ============================================================================
// Low-level byte writers
// ============================================================================

// Write a 6-byte RIP-relative indirect JMP at `dst`:
//   FF 25 00 00 00 00   JMP QWORD PTR [RIP+0]
// The 8-byte target address must be written at dst+6 by the caller.
def write_jmp_indirect(ulong dst) -> void
{
    byte* p = (byte*)dst;
    byte[] template = [0xFF, 0x25, 0x00, 0x00, 0x00, 0x00];
    for (int i = 0; i < 6; i++)
    {
        p[i] = template[i];
    };
};

// Write an 8-byte absolute address at `dst` in little-endian order.
def write_addr64(ulong dst, ulong addr) -> void
{
    byte* p = (@)dst,
          a = (@)addr;
    for (int i = 0; i < 8; i++)
    {
        p[i] = a[i];
    };
};

// Copy `n` bytes from `src` to `dst`.
def copy_bytes(ulong dst, ulong src, int n) -> void
{
    byte* d = (@)dst,
          s = (@)src;
    for (int i = 0; i < n; i++)
    {
        d[i] = s[i];
    };
};

// Compare two byte arrays. Returns 1 if equal, 0 otherwise.
def bytes_eq(byte* a, byte* b, int len) -> int
{
    int i;
    for (i = 0; i < len; i++)
    {
        if (a[i] != b[i])
        {
            return 0;
        };
    };
    return 1;
};

// Fill a buffer with a repeating byte value.
def fill_buf(byte* buf, int len, byte val) -> void
{
    int i;
    for (i = 0; i < len; i++)
    {
        buf[i] = val;
    };
};
