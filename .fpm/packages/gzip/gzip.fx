#ifndef FLUX_GZIP
#def FLUX_GZIP 1;

#import "standard.fx";


///  ---------------------------------------------------------------
  Enumerations
     ---------------------------------------------------------------
///

namespace gzip
{

    enum GzipError
    {
        ERR_OK,
        ERR_BAD_HEADER,
        ERR_BAD_BLOCK,
        ERR_BAD_HUFFMAN,
        ERR_BAD_CRC,
        ERR_BAD_LEN,
        ERR_OOM,
        ERR_OVERFLOW
    };

    enum BlockType
    {
        BTYPE_STORED,
        BTYPE_FIXED,
        BTYPE_DYNAMIC
    };

    enum GzipHeader
    {
        GZIP_ID1        = 0x1F,
        GZIP_ID2        = 0x8B,
        GZIP_CM_DEFLATE = 8,
        GZIP_OS_UNKNOWN = 255,
        GZIP_HDR_SIZE   = 10,
        GZIP_FTR_SIZE   = 8
    };

    enum Lz77Params
    {
        LZ77_WIN_SIZE = 32768,
        LZ77_WIN_MASK = 32767,
        LZ77_MAX_LEN  = 258,
        LZ77_MIN_LEN  = 3,
        LZ77_MAX_DIST = 32768
    };

    enum HashParams
    {
        HASH_SIZE = 65536,
        HASH_MASK = 65535,
        HASH_NIL  = -1
    };

    enum HuffParams
    {
        MAX_BITS   = 15,
        LIT_CODES  = 288,
        DIST_CODES = 30,
        CLEN_CODES = 19
    };


    ///  ---------------------------------------------------------------
      Structs
         ---------------------------------------------------------------
    ///

    struct BitWriter
    {
        byte*  buf;
        size_t cap,
               pos;
        u32    bits;
        int    nbits;
    };

    struct BitReader
    {
        byte*  buf;
        size_t len,
               pos;
        u32    bits;
        int    nbits;
    };

    struct HuffTree
    {
        u16[288] lit_codes,
                 lit_lens;
        u16[30]  dist_codes,
                 dist_lens;
    };

    struct LzMatch
    {
        int len,
            dist;
    };


    ///  ---------------------------------------------------------------
      CRC-32
         ---------------------------------------------------------------
    ///

    global u32[256] g_crc_table;
    global bool     g_crc_ready;

    def crc32_init() -> void
    {
        u32 c;
        int n, k;

        if (g_crc_ready) { return; };
        for (n = 0; n < 256; n++)
        {
            c = (u32)n;
            for (k = 0; k < 8; k++)
            {
                if (c `& 1) { c = 0xEDB88320u `^^ (c >> 1); }
                else        { c = c >> 1; };
            };
            g_crc_table[n] = c;
        };
        g_crc_ready = true;
    };

    def crc32_update(u32 crc, byte* buf, size_t len) -> u32
    {
        u32    c;
        size_t i;

        crc32_init();
        c = crc `^^ 0xFFFFFFFFu;
        for (i = 0; i < len; i++)
        {
            c = g_crc_table[(c `^^ (u32)buf[i]) `& 0xFFu] `^^ (c >> 8);
        };
        return c `^^ 0xFFFFFFFFu;
    };

    def crc32(byte* buf, size_t len) -> u32
    {
        return crc32_update(0u, buf, len);
    };


    ///  ---------------------------------------------------------------
      Bit-stream writer
         ---------------------------------------------------------------
    ///

    def bw_init(BitWriter* bw, byte* buf, size_t cap) -> void
    {
        bw.buf   = buf;
        bw.cap   = cap;
        bw.pos   = 0;
        bw.bits  = 0;
        bw.nbits = 0;
    };

    def bw_flush_byte(BitWriter* bw) -> GzipError
    {
        GzipError errs;

        if (bw.pos >= bw.cap) { return errs.ERR_OVERFLOW; };
        bw.buf[bw.pos] = (byte)(bw.bits `& 0xFFu);
        bw.pos++;
        bw.bits   = bw.bits >> 8;
        bw.nbits -= 8;
        return errs.ERR_OK;
    };

    def bw_write_bits(BitWriter* bw, u32 val, int n) -> GzipError
    {
        GzipError errs;
        GzipError r;

        bw.bits   = bw.bits `| (val << bw.nbits);
        bw.nbits += n;
        while (bw.nbits >= 8)
        {
            r = bw_flush_byte(bw);
            if (r != errs.ERR_OK) { return r; };
        };
        return errs.ERR_OK;
    };

    def bw_flush(BitWriter* bw) -> GzipError
    {
        GzipError errs;
        GzipError r;

        while (bw.nbits > 0)
        {
            r = bw_flush_byte(bw);
            if (r != errs.ERR_OK) { return r; };
        };
        return errs.ERR_OK;
    };

    def bw_write_byte(BitWriter* bw, byte b) -> GzipError
    {
        GzipError errs;
        GzipError r;

        r = bw_flush(bw);
        if (r != errs.ERR_OK) { return r; };
        if (bw.pos >= bw.cap) { return errs.ERR_OVERFLOW; };
        bw.buf[bw.pos] = b;
        bw.pos++;
        return errs.ERR_OK;
    };

    def bw_write_le16(BitWriter* bw, u32 v) -> GzipError
    {
        GzipError errs;
        GzipError r;

        r = bw_write_byte(bw, (byte)( v        `& 0xFFu)); if (r != errs.ERR_OK) { return r; };
        return bw_write_byte(bw, (byte)((v >> 8) `& 0xFFu));
    };

    def bw_write_le32(BitWriter* bw, u32 v) -> GzipError
    {
        GzipError errs;
        GzipError r;

        r = bw_write_byte(bw, (byte)( v          `& 0xFFu)); if (r != errs.ERR_OK) { return r; };
        r = bw_write_byte(bw, (byte)((v >>  8)   `& 0xFFu)); if (r != errs.ERR_OK) { return r; };
        r = bw_write_byte(bw, (byte)((v >> 16)   `& 0xFFu)); if (r != errs.ERR_OK) { return r; };
        return bw_write_byte(bw, (byte)((v >> 24) `& 0xFFu));
    };


    ///  ---------------------------------------------------------------
      Bit-stream reader
         ---------------------------------------------------------------
    ///

    def br_init(BitReader* br, byte* buf, size_t len) -> void
    {
        br.buf   = buf;
        br.len   = len;
        br.pos   = 0;
        br.bits  = 0;
        br.nbits = 0;
    };

    def br_refill(BitReader* br) -> void
    {
        while (br.nbits <= 24 & br.pos < br.len)
        {
            br.bits   = br.bits `| ((u32)br.buf[br.pos] << br.nbits);
            br.nbits += 8;
            br.pos++;
        };
    };

    def br_peek(BitReader* br, int n) -> u32
    {
        br_refill(br);
        return br.bits `& ((1u << n) - 1u);
    };

    def br_read(BitReader* br, int n) -> u32
    {
        u32 v;

        v         = br_peek(br, n);
        br.bits   = br.bits >> n;
        br.nbits -= n;
        return v;
    };

    def br_byte_align(BitReader* br) -> void
    {
        int discard;

        discard   = br.nbits % 8;
        br.bits   = br.bits >> discard;
        br.nbits -= discard;
    };

    def br_read_byte(BitReader* br) -> byte
    {
        br_byte_align(br);
        if (br.pos >= br.len) { return 0; };
        br.pos++;
        return br.buf[br.pos - 1];
    };

    def br_read_le16(BitReader* br) -> u32
    {
        u32 lo, hi;

        lo = (u32)br_read_byte(br);
        hi = (u32)br_read_byte(br);
        return lo `| (hi << 8);
    };

    def br_read_le32(BitReader* br) -> u32
    {
        u32 a, b, c, d;

        a = (u32)br_read_byte(br);
        b = (u32)br_read_byte(br);
        c = (u32)br_read_byte(br);
        d = (u32)br_read_byte(br);
        return a `| (b << 8) `| (c << 16) `| (d << 24);
    };


    ///  ---------------------------------------------------------------
      Huffman — build canonical codes from lengths
         ---------------------------------------------------------------
    ///

    def huff_build(u16* lengths, int nsyms, u16* out_codes) -> GzipError
    {
        GzipError errs;
        int[16]   bl_count;
        int[16]   next_code;
        int       bits, code, n;

        for (n = 0; n < nsyms; n++) { bl_count[lengths[n]]++; };

        code        = 0;
        bl_count[0] = 0;
        for (bits = 1; bits <= 15; bits++)
        {
            code            = (code + bl_count[bits - 1]) << 1;
            next_code[bits] = code;
        };

        for (n = 0; n < nsyms; n++)
        {
            if (lengths[n] != 0)
            {
                out_codes[n] = (u16)next_code[lengths[n]];
                next_code[lengths[n]]++;
            };
        };
        return errs.ERR_OK;
    };


    ///  ---------------------------------------------------------------
      Fixed Huffman tables (RFC 1951 s3.2.6)
         ---------------------------------------------------------------
    ///

    global HuffTree g_fixed_tree;
    global bool     g_fixed_ready;

    def fixed_tree_init() -> void
    {
        int i;

        if (g_fixed_ready) { return; };

        for (i = 0;   i <= 143; i++) { g_fixed_tree.lit_lens[i] = 8; };
        for (i = 144; i <= 255; i++) { g_fixed_tree.lit_lens[i] = 9; };
        for (i = 256; i <= 279; i++) { g_fixed_tree.lit_lens[i] = 7; };
        for (i = 280; i <= 287; i++) { g_fixed_tree.lit_lens[i] = 8; };
        for (i = 0;   i <  30;  i++) { g_fixed_tree.dist_lens[i] = 5; };

        huff_build(@g_fixed_tree.lit_lens[0],  288, @g_fixed_tree.lit_codes[0]);
        huff_build(@g_fixed_tree.dist_lens[0], 30,  @g_fixed_tree.dist_codes[0]);
        g_fixed_ready = true;
    };


    ///  ---------------------------------------------------------------
      Bit-reversal (Huffman codes are sent MSB-first)
         ---------------------------------------------------------------
    ///

    def bit_reverse(u32 v, int n) -> u32
    {
        u32 r;
        int i;

        r = 0;
        for (i = 0; i < n; i++)
        {
            r = (r << 1) `| (v `& 1u);
            v = v >> 1;
        };
        return r;
    };

    def huff_emit_lit(BitWriter* bw, HuffTree* tree, int sym) -> GzipError
    {
        return bw_write_bits(bw,
            bit_reverse((u32)tree.lit_codes[sym], (int)tree.lit_lens[sym]),
            (int)tree.lit_lens[sym]);
    };

    def huff_emit_dist(BitWriter* bw, HuffTree* tree, int sym) -> GzipError
    {
        return bw_write_bits(bw,
            bit_reverse((u32)tree.dist_codes[sym], (int)tree.dist_lens[sym]),
            (int)tree.dist_lens[sym]);
    };


    ///  ---------------------------------------------------------------
      LZ77 length/distance extra-bits tables (RFC 1951)
         ---------------------------------------------------------------
    ///

    global int[29] g_len_base;
    global int[29] g_len_extra;
    global int[30] g_dist_base;
    global int[30] g_dist_extra;
    global bool    g_lz_tables_ready;

    def lz_tables_init() -> void
    {
        int i, base, eb;

        if (g_lz_tables_ready) { return; };

        base = 3;
        eb   = 0;
        for (i = 0; i < 28; i++)
        {
            g_len_base[i]  = base;
            g_len_extra[i] = eb;
            base += 1 << eb;
            if (i >= 4 & (i % 4) == 3) { eb++; };
        };
        g_len_base[28]  = 258;
        g_len_extra[28] = 0;

        base = 1;
        eb   = 0;
        for (i = 0; i < 30; i++)
        {
            g_dist_base[i]  = base;
            g_dist_extra[i] = eb;
            base += 1 << eb;
            if (i >= 1 & (i % 2) == 1) { eb++; };
        };

        g_lz_tables_ready = true;
    };

    def len_to_code(int len) -> int
    {
        int i;

        for (i = 0; i < 28; i++)
        {
            if (len < g_len_base[i + 1]) { return 257 + i; };
        };
        return 285;
    };

    def dist_to_code(int dist) -> int
    {
        int i;

        for (i = 0; i < 29; i++)
        {
            if (dist <= g_dist_base[i + 1]) { return i; };
        };
        return 29;
    };


    ///  ---------------------------------------------------------------
      LZ77 match finder
         ---------------------------------------------------------------
    ///

    def find_match(byte* src, size_t src_len, size_t pos,
                   int* head, int* prev) -> LzMatch
    {
        LzMatch    best;
        Lz77Params lp;
        HashParams hp;
        size_t     limit, mpos, j;
        int        h, chain, cpos;

        best.len  = 0;
        best.dist = 0;

        if (pos + (size_t)lp.LZ77_MIN_LEN > src_len) { return best; };

        h     = (((int)src[pos] << 10) `^^ ((int)src[pos + 1] << 5) `^^ (int)src[pos + 2]) `& hp.HASH_MASK;
        limit = pos > (size_t)lp.LZ77_MAX_DIST ? pos - (size_t)lp.LZ77_MAX_DIST : 0;
        chain = 128;
        cpos  = head[h];

        while (cpos != hp.HASH_NIL & (size_t)cpos >= limit & chain > 0)
        {
            chain--;
            mpos = (size_t)cpos;

            if (src[mpos] == src[pos] & src[mpos + 1] == src[pos + 1])
            {
                j = 2;
                while (j < (size_t)lp.LZ77_MAX_LEN & pos + j < src_len & src[mpos + j] == src[pos + j])
                {
                    j++;
                };
                if ((int)j > best.len)
                {
                    best.len  = (int)j;
                    best.dist = (int)(pos - mpos);
                };
            };
            cpos = prev[(size_t)cpos `& (size_t)lp.LZ77_WIN_MASK];
        };
        return best;
    };


    ///  ---------------------------------------------------------------
      DEFLATE — stored block
         ---------------------------------------------------------------
    ///

    def deflate_stored(BitWriter* bw, byte* src, size_t len) -> GzipError
    {
        GzipError errs;
        GzipError r;
        size_t    i;

        // BFINAL=1 BTYPE=00
        r = bw_write_bits(bw, 1u, 1); if (r != errs.ERR_OK) { return r; };
        r = bw_write_bits(bw, 0u, 2); if (r != errs.ERR_OK) { return r; };
        r = bw_flush(bw);              if (r != errs.ERR_OK) { return r; };

        r = bw_write_le16(bw, (u32)len);                  if (r != errs.ERR_OK) { return r; };
        r = bw_write_le16(bw, (~(u32)len) `& 0xFFFFu);    if (r != errs.ERR_OK) { return r; };

        for (i = 0; i < len; i++)
        {
            r = bw_write_byte(bw, src[i]);
            if (r != errs.ERR_OK) { return r; };
        };
        return errs.ERR_OK;
    };


    ///  ---------------------------------------------------------------
      DEFLATE — fixed Huffman compressed block
         ---------------------------------------------------------------
    ///

    def deflate_fixed(BitWriter* bw, byte* src, size_t src_len) -> GzipError
    {
        GzipError  errs;
        GzipError  r;
        Lz77Params lp;
        HashParams hp;
        LzMatch    m;
        int*       head;
        int*       prev;
        size_t     pos, i;
        int        lsym, lcode, dcode, eb, h;

        fixed_tree_init();
        lz_tables_init();

        head = (int*)fmalloc((size_t)(hp.HASH_SIZE * (sizeof(int) / 8)));
        prev = (int*)fmalloc((size_t)(lp.LZ77_WIN_SIZE * (sizeof(int) / 8)));
        if ((u64)head == 0 | (u64)prev == 0)
        {
            if ((u64)head != 0) { ffree((u64)head); };
            if ((u64)prev != 0) { ffree((u64)prev); };
            return errs.ERR_OOM;
        };
        defer ffree((u64)head);
        defer ffree((u64)prev);

        for (i = 0; i < (size_t)hp.HASH_SIZE;     i++) { head[i] = hp.HASH_NIL; };
        for (i = 0; i < (size_t)lp.LZ77_WIN_SIZE; i++) { prev[i] = hp.HASH_NIL; };

        // BFINAL=1 BTYPE=01
        r = bw_write_bits(bw, 1u, 1); if (r != errs.ERR_OK) { return r; };
        r = bw_write_bits(bw, 1u, 2); if (r != errs.ERR_OK) { return r; };

        pos = 0;
        while (pos < src_len)
        {
            m = find_match(src, src_len, pos, head, prev);

            if (m.len >= lp.LZ77_MIN_LEN)
            {
                lcode = len_to_code(m.len);
                lsym  = lcode - 257;

                r = huff_emit_lit(bw, @g_fixed_tree, lcode);
                if (r != errs.ERR_OK) { return r; };

                eb = g_len_extra[lsym];
                if (eb > 0)
                {
                    r = bw_write_bits(bw, (u32)(m.len - g_len_base[lsym]), eb);
                    if (r != errs.ERR_OK) { return r; };
                };

                dcode = dist_to_code(m.dist);
                r = huff_emit_dist(bw, @g_fixed_tree, dcode);
                if (r != errs.ERR_OK) { return r; };

                eb = g_dist_extra[dcode];
                if (eb > 0)
                {
                    r = bw_write_bits(bw, (u32)(m.dist - g_dist_base[dcode]), eb);
                    if (r != errs.ERR_OK) { return r; };
                };

                for (i = 0; i < (size_t)m.len; i++)
                {
                    h = (((int)src[pos + i] << 10) `^^
                         ((int)src[pos + i + 1] << 5) `^^
                          (int)src[pos + i + 2]) `& hp.HASH_MASK;
                    prev[(pos + i) `& (size_t)lp.LZ77_WIN_MASK] = head[h];
                    head[h] = (int)(pos + i);
                };
                pos += (size_t)m.len;
            }
            else
            {
                r = huff_emit_lit(bw, @g_fixed_tree, (int)src[pos]);
                if (r != errs.ERR_OK) { return r; };

                h = (((int)src[pos] << 10) `^^
                     ((int)src[pos + 1] << 5) `^^
                      (int)src[pos + 2]) `& hp.HASH_MASK;
                prev[pos `& (size_t)lp.LZ77_WIN_MASK] = head[h];
                head[h] = (int)pos;
                pos++;
            };
        };

        // End-of-block symbol 256
        r = huff_emit_lit(bw, @g_fixed_tree, 256);
        if (r != errs.ERR_OK) { return r; };
        return bw_flush(bw);
    };


    ///  ---------------------------------------------------------------
      Inflate — Huffman symbol decoder
         ---------------------------------------------------------------
    ///

    def decode_lit(BitReader* br, HuffTree* tree, int nsyms) -> int
    {
        u32 bits;
        int i, len;

        for (len = 1; len <= 15; len++)
        {
            bits = br_peek(br, len);
            for (i = 0; i < nsyms; i++)
            {
                if ((int)tree.lit_lens[i] == len &
                    (u32)tree.lit_codes[i] == bit_reverse(bits, len))
                {
                    br_read(br, len);
                    return i;
                };
            };
        };
        return -1;
    };

    def decode_dist(BitReader* br, HuffTree* tree) -> int
    {
        u32 bits;
        int i, len;

        for (len = 1; len <= 15; len++)
        {
            bits = br_peek(br, len);
            for (i = 0; i < 30; i++)
            {
                if ((int)tree.dist_lens[i] == len &
                    (u32)tree.dist_codes[i] == bit_reverse(bits, len))
                {
                    br_read(br, len);
                    return i;
                };
            };
        };
        return -1;
    };


    ///  ---------------------------------------------------------------
      Inflate — fixed Huffman block
         ---------------------------------------------------------------
    ///

    def inflate_fixed_block(BitReader* br, byte* dst, size_t dst_cap,
                            size_t* dst_pos) -> GzipError
    {
        GzipError  errs;
        Lz77Params lp;
        int        sym, lsym, dcode, length, dist;
        size_t     i;

        fixed_tree_init();
        lz_tables_init();

        for (;;)
        {
            sym = decode_lit(br, @g_fixed_tree, 288);
            if (sym < 0)    { return errs.ERR_BAD_HUFFMAN; };
            if (sym == 256) { break; };

            if (sym < 256)
            {
                if (*dst_pos >= dst_cap) { return errs.ERR_OVERFLOW; };
                dst[*dst_pos] = (byte)sym;
                *dst_pos += 1;
            }
            else
            {
                lsym   = sym - 257;
                length = g_len_base[lsym] + (int)br_read(br, g_len_extra[lsym]);
                dcode  = decode_dist(br, @g_fixed_tree);
                if (dcode < 0) { return errs.ERR_BAD_HUFFMAN; };
                dist = g_dist_base[dcode] + (int)br_read(br, g_dist_extra[dcode]);

                if ((size_t)dist > *dst_pos) { return errs.ERR_BAD_LEN; };
                for (i = 0; i < (size_t)length; i++)
                {
                    if (*dst_pos >= dst_cap) { return errs.ERR_OVERFLOW; };
                    dst[*dst_pos] = dst[*dst_pos - (size_t)dist];
                    *dst_pos += 1;
                };
            };
        };
        return errs.ERR_OK;
    };


    ///  ---------------------------------------------------------------
      Inflate — stored block
         ---------------------------------------------------------------
    ///

    def inflate_stored_block(BitReader* br, byte* dst, size_t dst_cap,
                             size_t* dst_pos) -> GzipError
    {
        GzipError errs;
        u32       blen, bnlen;
        size_t    i;

        br_byte_align(br);
        blen  = br_read_le16(br);
        bnlen = br_read_le16(br);
        if ((blen `^^ bnlen) != 0xFFFFu) { return errs.ERR_BAD_BLOCK; };

        for (i = 0; i < (size_t)blen; i++)
        {
            if (*dst_pos >= dst_cap) { return errs.ERR_OVERFLOW; };
            dst[*dst_pos] = br_read_byte(br);
            *dst_pos += 1;
        };
        return errs.ERR_OK;
    };


    ///  ---------------------------------------------------------------
      Public API — gzip_compress
         ---------------------------------------------------------------
    ///

    // Compress src into a freshly fmalloc'd GZIP stream at *dst.
    // Caller must ffree(*dst) when done.
    def gzip_compress(byte* src, size_t src_len,
                      byte** dst, size_t* dst_len) -> GzipError
    {
        GzipError  errs;
        GzipError  r;
        GzipHeader gh;
        BitWriter  bw;
        byte*      buf;
        size_t     buf_cap;
        u32        crc;

        buf_cap = src_len + src_len / 8 + 128;
        buf     = (byte*)fmalloc(buf_cap);
        if ((u64)buf == 0) { return errs.ERR_OOM; };

        // --- GZIP header ---
        buf[0] = (byte)gh.GZIP_ID1;
        buf[1] = (byte)gh.GZIP_ID2;
        buf[2] = (byte)gh.GZIP_CM_DEFLATE;
        buf[3] = 0;   // FLG
        buf[4] = 0;   // MTIME[0]
        buf[5] = 0;   // MTIME[1]
        buf[6] = 0;   // MTIME[2]
        buf[7] = 0;   // MTIME[3]
        buf[8] = 0;   // XFL
        buf[9] = (byte)gh.GZIP_OS_UNKNOWN;

        bw_init(@bw, buf + (size_t)gh.GZIP_HDR_SIZE,
                buf_cap - (size_t)gh.GZIP_HDR_SIZE - (size_t)gh.GZIP_FTR_SIZE);

        if (src_len < 32)
        {
            r = deflate_stored(@bw, src, src_len);
        }
        else
        {
            r = deflate_fixed(@bw, src, src_len);
        };

        if (r != errs.ERR_OK) { ffree((u64)buf); return r; };

        // --- GZIP footer: CRC-32 then ISIZE ---
        crc = crc32(src, src_len);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 0] = (byte)( crc           `& 0xFFu);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 1] = (byte)((crc >>  8)    `& 0xFFu);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 2] = (byte)((crc >> 16)    `& 0xFFu);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 3] = (byte)((crc >> 24)    `& 0xFFu);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 4] = (byte)( src_len         `& 0xFFu);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 5] = (byte)((src_len >>  8)  `& 0xFFu);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 6] = (byte)((src_len >> 16)  `& 0xFFu);
        buf[gh.GZIP_HDR_SIZE + bw.pos + 7] = (byte)((src_len >> 24)  `& 0xFFu);

        *dst     = buf;
        *dst_len = (size_t)gh.GZIP_HDR_SIZE + bw.pos + (size_t)gh.GZIP_FTR_SIZE;
        return errs.ERR_OK;
    };


    ///  ---------------------------------------------------------------
      Public API — gzip_decompress
         ---------------------------------------------------------------
    ///

    // Decompress a GZIP stream into a freshly fmalloc'd buffer at *dst.
    // Caller must ffree(*dst) when done.
    def gzip_decompress(byte* src, size_t src_len,
                        byte** dst, size_t* dst_len) -> GzipError
    {
        GzipError  errs;
        GzipError  r;
        GzipHeader gh;
        BitReader  br;
        byte*      out;
        size_t     out_cap,
                   out_pos,
                   footer_off;
        u32        crc_stored, crc_actual,
                   isize_stored,
                   bfinal, btype;
        int        flg, xlen, hdr_pos;

        if (src_len < (size_t)(gh.GZIP_HDR_SIZE + gh.GZIP_FTR_SIZE)) { return errs.ERR_BAD_HEADER; };
        if (src[0] != (byte)gh.GZIP_ID1        |
            src[1] != (byte)gh.GZIP_ID2        |
            src[2] != (byte)gh.GZIP_CM_DEFLATE) { return errs.ERR_BAD_HEADER; };

        flg     = (int)src[3];
        hdr_pos = gh.GZIP_HDR_SIZE;

        if (flg `& 4)
        {
            xlen     = (int)src[hdr_pos] `| ((int)src[hdr_pos + 1] << 8);
            hdr_pos += 2 + xlen;
        };
        if (flg `& 8)  { while (src[hdr_pos] != 0) { hdr_pos++; }; hdr_pos++; };
        if (flg `& 16) { while (src[hdr_pos] != 0) { hdr_pos++; }; hdr_pos++; };
        if (flg `& 2)  { hdr_pos += 2; };

        out_cap = src_len * 4 + 256;
        out     = (byte*)fmalloc(out_cap);
        if ((u64)out == 0) { return errs.ERR_OOM; };
        out_pos = 0;

        br_init(@br, src + (size_t)hdr_pos,
                src_len - (size_t)hdr_pos - (size_t)gh.GZIP_FTR_SIZE);

        for (;;)
        {
            bfinal = br_read(@br, 1);
            btype  = br_read(@br, 2);

            switch (btype)
            {
                case (0)
                {
                    r = inflate_stored_block(@br, out, out_cap, @out_pos);
                }
                case (1)
                {
                    r = inflate_fixed_block(@br, out, out_cap, @out_pos);
                }
                default
                {
                    ffree((u64)out);
                    return errs.ERR_BAD_BLOCK;
                };
            };

            if (r != errs.ERR_OK) { ffree((u64)out); return r; };
            if (bfinal)           { break; };
        };

        // Verify footer
        footer_off   = src_len - (size_t)gh.GZIP_FTR_SIZE;
        crc_stored   = (u32)src[footer_off + 0]
                    `| ((u32)src[footer_off + 1] << 8)
                    `| ((u32)src[footer_off + 2] << 16)
                    `| ((u32)src[footer_off + 3] << 24);
        isize_stored = (u32)src[footer_off + 4]
                    `| ((u32)src[footer_off + 5] << 8)
                    `| ((u32)src[footer_off + 6] << 16)
                    `| ((u32)src[footer_off + 7] << 24);

        crc_actual = crc32(out, out_pos);
        if (crc_actual != crc_stored | (u32)out_pos != isize_stored)
        {
            ffree((u64)out);
            return errs.ERR_BAD_CRC;
        };

        *dst     = out;
        *dst_len = out_pos;
        return errs.ERR_OK;
    };
};

#endif;
