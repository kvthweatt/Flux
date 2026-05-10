// Author: Karac V. Thweatt

// redcrypto.fx - Cryptography Library

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_BIG_INTEGERS
#import "bigint.fx";
#endif;

#ifndef FLUX_STANDARD_CRYPTO
#def FLUX_STANDARD_CRYPTO;

namespace standard
{
    namespace crypto
    {
        namespace hashing
        {
            namespace SHA256
            {
                struct SHA256_CTX
                {
                    u32[8] state;           // Hash state
                    byte[64] buffer;        // Message block buffer
                    u64 bitlen;             // Message length in bits
                    u32 buflen;             // Current buffer length
                };

                // SHA-256 constants (first 32 bits of the fractional parts of the cube roots of the first 64 primes)
                u32[64] K = [
                    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5,
                    0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
                    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
                    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
                    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC,
                    0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
                    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7,
                    0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
                    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
                    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
                    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3,
                    0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
                    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5,
                    0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
                    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
                    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2
                ];
                
                // Right rotate
                def rotr(u32 value, u32 n) -> u32
                {
                    return (value >> n) `| (value << (32 - n));
                };
                                
                                // SHA-256 functions
                def ch(u32 x, u32 y, u32 z) -> u32
                {
                    return (x `& y) `^^ (`!x `& z);
                };

                def maj(u32 x, u32 y, u32 z) -> u32
                {
                    return (x `& y) `^^ (x `& z) `^^ (y `& z);
                };

                def sigma0(u32 x) -> u32
                {
                    return rotr(x, 2) `^^ rotr(x, 13) `^^ rotr(x, 22);
                };

                def sigma1(u32 x) -> u32
                {
                    return rotr(x, 6) `^^ rotr(x, 11) `^^ rotr(x, 25);
                };

                def gamma0(u32 x) -> u32
                {
                    return rotr(x, 7) `^^ rotr(x, 18) `^^ (x >> 3);
                };

                def gamma1(u32 x) -> u32
                {
                    return rotr(x, 17) `^^ rotr(x, 19) `^^ (x >> 10);
                };
                
                // Initialize SHA-256 context
                def sha256_init(SHA256_CTX* ctx) -> void
                {
                    // Initial hash values (first 32 bits of the fractional parts of the square roots of the first 8 primes)
                    ctx.state[0] = 0x6A09E667u;
                    ctx.state[1] = 0xBB67AE85u;
                    ctx.state[2] = 0x3C6EF372u;
                    ctx.state[3] = 0xA54FF53Au;
                    ctx.state[4] = 0x510E527Fu;
                    ctx.state[5] = 0x9B05688Cu;
                    ctx.state[6] = 0x1F83D9ABu;
                    ctx.state[7] = 0x5BE0CD19u;
                    
                    ctx.bitlen = 0;
                    ctx.buflen = 0;
                };
                
                // Process a single 512-bit block
                def sha256_transform(SHA256_CTX* ctx, byte* datax) -> void
                {
                    u32[64] W;
                    u32 a, b, c, d, e, f, g, h, t1, t2, i;
                    
                    // Prepare message schedule
                    for (i = 0; i < 16; i++)
                    {
                        W[i] = (((u32)datax[i * 4] & 0xFF) << 24) |
                               (((u32)datax[i * 4 + 1] & 0xFF) << 16) |
                               (((u32)datax[i * 4 + 2] & 0xFF) << 8) |
                               ((u32)datax[i * 4 + 3] & 0xFF);
                    };
                    
                    for (i = 16; i < 64; i++)
                    {
                        W[i] = gamma1(W[i - 2]) + W[i - 7] + gamma0(W[i - 15]) + W[i - 16];
                    };
                    
                    // Initialize working variables
                    a = ctx.state[0];
                    b = ctx.state[1];
                    c = ctx.state[2];
                    d = ctx.state[3];
                    e = ctx.state[4];
                    f = ctx.state[5];
                    g = ctx.state[6];
                    h = ctx.state[7];
                    
                    // Main loop
                    for (i = 0; i < 64; i++)
                    {
                        t1 = h + sigma1(e) + ch(e, f, g) + K[i] + W[i];
                        t2 = sigma0(a) + maj(a, b, c);
                        h = g;
                        g = f;
                        f = e;
                        e = d + t1;
                        d = c;
                        c = b;
                        b = a;
                        a = t1 + t2;
                    };
                    
                    // Update hash state
                    ctx.state[0] += a;
                    ctx.state[1] += b;
                    ctx.state[2] += c;
                    ctx.state[3] += d;
                    ctx.state[4] += e;
                    ctx.state[5] += f;
                    ctx.state[6] += g;
                    ctx.state[7] += h;
                };
                
                // Update SHA-256 with data
                def sha256_update(SHA256_CTX* ctx, byte* datax, u64 len) -> void
                {
                    for (long i; i < len; i++)
                    {
                        ctx.buffer[ctx.buflen] = datax[i];
                        ctx.buflen = ctx.buflen + 1;
                        
                        if (ctx.buflen == 64)
                        {
                            //print("Transforming block\n\0");
                            sha256_transform(ctx, ctx.buffer);
                            ctx.bitlen += 512;
                            ctx.buflen = 0;
                        };
                    };
                };

                def sha256_final(SHA256_CTX* ctx, byte* hash) -> void
                {
                    u32 i = ctx.buflen;

                    // Pad with 0x80
                    ctx.buffer[i] = 0x80;
                    i++;
                    
                    // Pad with zeros, leaving room for length
                    if (ctx.buflen < 56)
                    {
                        while (i < 56)
                        {
                            ctx.buffer[i] = '\0';
                            i++;
                        };
                    }
                    else
                    {
                        while (i < 64)
                        {
                            ctx.buffer[i] = '\0';
                            i++;
                        };
                        sha256_transform(ctx, ctx.buffer);
                        for (i = 0; i < 56; i++)
                        {
                            ctx.buffer[i] = '\0';
                        };
                    };
                    
                    // Append length in bits as 64-bit big-endian
                    ctx.bitlen += ctx.buflen * 8;

                    ctx.buffer[56..63] = (byte[8])(be64)ctx.bitlen;
                    ///
                    ctx.buffer[63] = (byte)(ctx.bitlen);
                    ctx.buffer[62] = (byte)(ctx.bitlen >> 8);
                    ctx.buffer[61] = (byte)(ctx.bitlen >> 16);
                    ctx.buffer[60] = (byte)(ctx.bitlen >> 24);
                    ctx.buffer[59] = (byte)(ctx.bitlen >> 32);
                    ctx.buffer[58] = (byte)(ctx.bitlen >> 40);
                    ctx.buffer[57] = (byte)(ctx.bitlen >> 48);
                    ctx.buffer[56] = (byte)(ctx.bitlen >> 56);
                    ///
                    sha256_transform(ctx, ctx.buffer);
                    
                    // Convert state to byte array (big-endian)
                    hash[0..3]   = (byte[4])(be32)ctx.state[0];
                    hash[4..7]   = (byte[4])(be32)ctx.state[1];
                    hash[8..11]  = (byte[4])(be32)ctx.state[2];
                    hash[12..15] = (byte[4])(be32)ctx.state[3];
                    hash[16..19] = (byte[4])(be32)ctx.state[4];
                    hash[20..23] = (byte[4])(be32)ctx.state[5];
                    hash[24..27] = (byte[4])(be32)ctx.state[6];
                    hash[28..31] = (byte[4])(be32)ctx.state[7];
                };
            }; // SHA256

            namespace SHA384
            {
                struct SHA384_CTX
                {
                    u64[8] state;           // Hash state (8 x 64-bit words)
                    byte[128] buffer;       // Message block buffer (1024-bit block)
                    u64 bitlen_lo;          // Message bit length low 64 bits
                    u64 bitlen_hi;          // Message bit length high 64 bits (for >2^64 bit messages)
                    u32 buflen;             // Current bytes in buffer
                };

                // SHA-512/384 round constants
                // First 64 bits of the fractional parts of the cube roots of the first 80 primes
                const u64[80] K384 = [
                    0x428A2F98D728AE22u, 0x7137449123EF65CDu, 0xB5C0FBCFEC4D3B2Fu, 0xE9B5DBA58189DBBCu,
                    0x3956C25BF348B538u, 0x59F111F1B605D019u, 0x923F82A4AF194F9Bu, 0xAB1C5ED5DA6D8118u,
                    0xD807AA98A3030242u, 0x12835B0145706FBEu, 0x243185BE4EE4B28Cu, 0x550C7DC3D5FFB4E2u,
                    0x72BE5D74F27B896Fu, 0x80DEB1FE3B1696B1u, 0x9BDC06A725C71235u, 0xC19BF174CF692694u,
                    0xE49B69C19EF14AD2u, 0xEFBE4786384F25E3u, 0x0FC19DC68B8CD5B5u, 0x240CA1CC77AC9C65u,
                    0x2DE92C6F592B0275u, 0x4A7484AA6EA6E483u, 0x5CB0A9DCBD41FBD4u, 0x76F988DA831153B5u,
                    0x983E5152EE66DFABu, 0xA831C66D2DB43210u, 0xB00327C898FB213Fu, 0xBF597FC7BEEF0EE4u,
                    0xC6E00BF33DA88FC2u, 0xD5A79147930AA725u, 0x06CA6351E003826Fu, 0x142929670A0E6E70u,
                    0x27B70A8546D22FFCu, 0x2E1B21385C26C926u, 0x4D2C6DFC5AC42AEDu, 0x53380D139D95B3DFu,
                    0x650A73548BAF63DEu, 0x766A0ABB3C77B2A8u, 0x81C2C92E47EDAEE6u, 0x92722C851482353Bu,
                    0xA2BFE8A14CF10364u, 0xA81A664BBC423001u, 0xC24B8B70D0F89791u, 0xC76C51A30654BE30u,
                    0xD192E819D6EF5218u, 0xD69906245565A910u, 0xF40E35855771202Au, 0x106AA07032BBD1B8u,
                    0x19A4C116B8D2D0C8u, 0x1E376C085141AB53u, 0x2748774CDF8EEB99u, 0x34B0BCB5E19B48A8u,
                    0x391C0CB3C5C95A63u, 0x4ED8AA4AE3418ACBu, 0x5B9CCA4F7763E373u, 0x682E6FF3D6B2B8A3u,
                    0x748F82EE5DEFB2FCu, 0x78A5636F43172F60u, 0x84C87814A1F0AB72u, 0x8CC702081A6439ECu,
                    0x90BEFFFA23631E28u, 0xA4506CEBDE82BDE9u, 0xBEF9A3F7B2C67915u, 0xC67178F2E372532Bu,
                    0xCA273ECEEA26619Cu, 0xD186B8C721C0C207u, 0xEADA7DD6CDE0EB1Eu, 0xF57D4F7FEE6ED178u,
                    0x06F067AA72176FBAu, 0x0A637DC5A2C898A6u, 0x113F9804BEF90DAEu, 0x1B710B35131C471Bu,
                    0x28DB77F523047D84u, 0x32CAAB7B40C72493u, 0x3C9EBE0A15C9BEBCu, 0x431D67C49C100D4Cu,
                    0x4CC5D4BECB3E42B6u, 0x597F299CFC657E2Au, 0x5FCB6FAB3AD6FAECu, 0x6C44198C4A475817u
                ];

                // 64-bit right rotate
                def rotr64(u64 value, u64 n) -> u64
                {
                    return (value >> n) `| (value << (64u - n));
                };

                // SHA-512/384 logical functions
                def ch64(u64 x, u64 y, u64 z) -> u64
                {
                    return (x `& y) `^^ (`!x `& z);
                };

                def maj64(u64 x, u64 y, u64 z) -> u64
                {
                    return (x `& y) `^^ (x `& z) `^^ (y `& z);
                };

                // Capital-Sigma functions
                def Sigma0(u64 x) -> u64
                {
                    return rotr64(x, 28u) `^^ rotr64(x, 34u) `^^ rotr64(x, 39u);
                };

                def Sigma1(u64 x) -> u64
                {
                    return rotr64(x, 14u) `^^ rotr64(x, 18u) `^^ rotr64(x, 41u);
                };

                // Lower-sigma (message schedule) functions
                def sigma0_64(u64 x) -> u64
                {
                    return rotr64(x, 1u) `^^ rotr64(x, 8u) `^^ (x >> 7u);
                };

                def sigma1_64(u64 x) -> u64
                {
                    return rotr64(x, 19u) `^^ rotr64(x, 61u) `^^ (x >> 6u);
                };

                // Initialize SHA-384 context
                // IV differs from SHA-512 — these are the SHA-384-specific initial values
                def sha384_init(SHA384_CTX* ctx) -> void
                {
                    ctx.state = [0xCBBB9D5DC1059ED8u,
                                 0x629A292A367CD507u,
                                 0x9159015A3070DD17u,
                                 0x152FECD8F70E5939u,
                                 0x67332667FFC00B31u,
                                 0x8EB44A8768581511u,
                                 0xDB0C2E0D64F98FA7u,
                                 0x47B5481DBEFA4FA4u];

                    ctx.bitlen_lo = 0u;
                    ctx.bitlen_hi = 0u;
                    ctx.buflen = 0u;
                };

                // Process one 1024-bit (128-byte) block
                def sha384_transform(SHA384_CTX* ctx, byte* datax) -> void
                {
                    u64[80] W;
                    u64 a, b, c, d, e, f, g, h, t1, t2;
                    u32 i;

                    // Load message schedule from block (big-endian 64-bit words)
                    for (i = 0; i < 16; i++)
                    {
                        W[i] = ((u64)(datax[i * 8]     & 0xFF) << 56u) |
                               ((u64)(datax[i * 8 + 1] & 0xFF) << 48u) |
                               ((u64)(datax[i * 8 + 2] & 0xFF) << 40u) |
                               ((u64)(datax[i * 8 + 3] & 0xFF) << 32u) |
                               ((u64)(datax[i * 8 + 4] & 0xFF) << 24u) |
                               ((u64)(datax[i * 8 + 5] & 0xFF) << 16u) |
                               ((u64)(datax[i * 8 + 6] & 0xFF) << 8u)  |
                                (u64)(datax[i * 8 + 7] & 0xFF);
                    };

                    for (i = 16; i < 80; i++)
                    {
                        W[i] = sigma1_64(W[i - 2]) + W[i - 7] + sigma0_64(W[i - 15]) + W[i - 16];
                    };

                    a = ctx.state[0];
                    b = ctx.state[1];
                    c = ctx.state[2];
                    d = ctx.state[3];
                    e = ctx.state[4];
                    f = ctx.state[5];
                    g = ctx.state[6];
                    h = ctx.state[7];

                    for (i = 0; i < 80; i++)
                    {
                        t1 = h + Sigma1(e) + ch64(e, f, g) + K384[i] + W[i];
                        t2 = Sigma0(a) + maj64(a, b, c);
                        h = g;
                        g = f;
                        f = e;
                        e = d + t1;
                        d = c;
                        c = b;
                        b = a;
                        a = t1 + t2;
                    };

                    ctx.state[0] += a;
                    ctx.state[1] += b;
                    ctx.state[2] += c;
                    ctx.state[3] += d;
                    ctx.state[4] += e;
                    ctx.state[5] += f;
                    ctx.state[6] += g;
                    ctx.state[7] += h;
                };

                // Feed data into the SHA-384 context
                def sha384_update(SHA384_CTX* ctx, byte* datax, u64 len) -> void
                {
                    u64 i;

                    for (i = 0; i < len; i++)
                    {
                        ctx.buffer[ctx.buflen] = datax[i];
                        ctx.buflen = ctx.buflen + 1u;

                        if (ctx.buflen == 128u)
                        {
                            sha384_transform(ctx, ctx.buffer);
                            // Add 1024 bits to the running length
                            ctx.bitlen_lo += 1024u;
                            if (ctx.bitlen_lo == 0u)
                            {
                                ctx.bitlen_hi += 1u;
                            };
                            ctx.buflen = 0u;
                        };
                    };
                };

                // Finalize and write 48-byte digest to hash
                def sha384_final(SHA384_CTX* ctx, byte* hash) -> void
                {
                    u32 i;
                    u64 total_bits_lo, total_bits_hi;

                    i = ctx.buflen;

                    // Append 0x80 padding byte
                    ctx.buffer[i] = (byte)0x80;
                    i++;

                    // SHA-384/512 reserves the last 16 bytes of the block for the
                    // 128-bit message length. Pad to byte 112 (block size 128 - 16).
                    if (ctx.buflen < 112u)
                    {
                        while (i < 112u)
                        {
                            ctx.buffer[i] = (byte)0;
                            i++;
                        };
                    }
                    else
                    {
                        while (i < 128u)
                        {
                            ctx.buffer[i] = (byte)0;
                            i++;
                        };
                        sha384_transform(ctx, ctx.buffer);
                        for (i = 0; i < 112; i++)
                        {
                            ctx.buffer[i] = (byte)0;
                        };
                    };

                    // Accumulate remaining buffered bytes into bit length
                    total_bits_lo = ctx.bitlen_lo + ((u64)ctx.buflen * 8u);
                    total_bits_hi = ctx.bitlen_hi;
                    if (total_bits_lo < ctx.bitlen_lo)
                    {
                        total_bits_hi += 1u;
                    };

                    // Append 128-bit big-endian length (high 64 bits first)
                    ctx.buffer[112..119] = (byte[8])(be64)total_bits_hi;
                    ctx.buffer[120..127] = (byte[8])(be64)total_bits_lo;

                    sha384_transform(ctx, ctx.buffer);

                    // Write first 6 state words as big-endian bytes (48 bytes total)
                    // State words 6 and 7 are discarded — this is what makes it SHA-384
                    // rather than SHA-512.
                    hash[0..7]   = (byte[8])(be64)ctx.state[0];
                    hash[8..15]  = (byte[8])(be64)ctx.state[1];
                    hash[16..23] = (byte[8])(be64)ctx.state[2];
                    hash[24..31] = (byte[8])(be64)ctx.state[3];
                    hash[32..39] = (byte[8])(be64)ctx.state[4];
                    hash[40..47] = (byte[8])(be64)ctx.state[5];
                };

                // Convenience: hash a single buffer in one call
                def sha384(byte* datax, u64 len, byte* hash) -> void
                {
                    SHA384_CTX ctx;
                    sha384_init(@ctx);
                    sha384_update(@ctx, datax, len);
                    sha384_final(@ctx, hash);
                };

            }; // SHA384

            namespace MD5
            {
                struct MD5_CTX
                {
                    u32[4] state;       // Hash state (A, B, C, D)
                    u64 count;          // Number of bits processed
                    byte[64] buffer;    // Input buffer
                };

                // MD5 constants - sine-based values
                global u32[64] MD5_K = [
                    0xD76AA478, 0xE8C7B756, 0x242070DB, 0xC1BDCEEE,
                    0xF57C0FAF, 0x4787C62A, 0xA8304613, 0xFD469501,
                    0x698098D8, 0x8B44F7AF, 0xFFFF5BB1, 0x895CD7BE,
                    0x6B901122, 0xFD987193, 0xA679438E, 0x49B40821,
                    0xF61E2562, 0xC040B340, 0x265E5A51, 0xE9B6C7AA,
                    0xD62F105D, 0x02441453, 0xD8A1E681, 0xE7D3FBC8,
                    0x21E1CDE6, 0xC33707D6, 0xF4D50D87, 0x455A14ED,
                    0xA9E3E905, 0xFCEFA3F8, 0x676F02D9, 0x8D2A4C8A,
                    0xFFFA3942, 0x8771F681, 0x6D9D6122, 0xFDE5380C,
                    0xA4BEEA44, 0x4BDECFA9, 0xF6BB4B60, 0xBEBFBC70,
                    0x289B7EC6, 0xEAA127FA, 0xD4EF3085, 0x04881D05,
                    0xD9D4D039, 0xE6DB99E5, 0x1FA27CF8, 0xC4AC5665,
                    0xF4292244, 0x432AFF97, 0xAB9423A7, 0xFC93A039,
                    0x655B59C3, 0x8F0CCC92, 0xFFEFF47D, 0x85845DD1,
                    0x6FA87E4F, 0xFE2CE6E0, 0xA3014314, 0x4E0811A1,
                    0xF7537E82, 0xBD3AF235, 0x2AD7D2BB, 0xEB86D391
                ];
                
                // Shift amounts for each round
                global u32[64] MD5_S = [
                    7, 12, 17, 22,  7, 12, 17, 22,  7, 12, 17, 22,  7, 12, 17, 22,
                    5,  9, 14, 20,  5,  9, 14, 20,  5,  9, 14, 20,  5,  9, 14, 20,
                    4, 11, 16, 23,  4, 11, 16, 23,  4, 11, 16, 23,  4, 11, 16, 23,
                    6, 10, 15, 21,  6, 10, 15, 21,  6, 10, 15, 21,  6, 10, 15, 21
                ];
                
                // Left rotate
                def rotl(u32 value, u32 n) -> u32
                {
                    return (value << n) | (value >> (32 - n));
                };
                
                // MD5 auxiliary functions
                def F(u32 x, u32 y, u32 z) -> u32
                {
                    return (x & y) | ((!x) & z);
                };
                
                def G(u32 x, u32 y, u32 z) -> u32
                {
                    return (x & z) | (y & (!z));
                };
                
                def H(u32 x, u32 y, u32 z) -> u32
                {
                    return x ^^ y ^^ z;
                };
                
                def I(u32 x, u32 y, u32 z) -> u32
                {
                    return y ^^ (x | (!z));
                };
                
                // Initialize MD5 context
                def md5_init(MD5_CTX* ctx) -> void
                {
                    ctx.state[0] = (i32)0x67452301;
                    ctx.state[1] = (i32)0xEFCDAB89;
                    ctx.state[2] = (i32)0x98BADCFE;
                    ctx.state[3] = (i32)0x10325476;
                    ctx.count = 0;
                    return;
                };
                
                // Process a single 512-bit block
                def md5_transform(MD5_CTX* ctx, byte* block) -> void
                {
                    u32[16] M;
                    u32 i;
                    u32 A, B, C, D;
                    u32 f_val, g;
                    
                    // Decode block into 16 32-bit words (little-endian)
                    for (i = 0; i < 16; i++)
                    {
                        M[i] = ((u32)(block[i * 4] & 0xFF)) |
                               (((u32)(block[i * 4 + 1] & 0xFF)) << 8) |
                               (((u32)(block[i * 4 + 2] & 0xFF)) << 16) |
                               (((u32)(block[i * 4 + 3] & 0xFF)) << 24);
                    };
                    
                    // Initialize working variables
                    A = ctx.state[0];
                    B = ctx.state[1];
                    C = ctx.state[2];
                    D = ctx.state[3];
                    
                    // Main loop - 64 operations in 4 rounds
                    for (i = 0; i < 64; i++)
                    {
                        if (i < 16)
                        {
                            f_val = F(B, C, D);
                            g = i;
                        }
                        else
                        {
                            if (i < 32)
                            {
                                f_val = G(B, C, D);
                                g = (5 * i + 1) % 16;
                            }
                            else
                            {
                                if (i < 48)
                                {
                                    f_val = H(B, C, D);
                                    g = (3 * i + 5) % 16;
                                }
                                else
                                {
                                    f_val = I(B, C, D);
                                    g = (7 * i) % 16;
                                };
                            };
                        };
                        
                        f_val = f_val + A + MD5_K[i] + M[g];
                        A = D;
                        D = C;
                        C = B;
                        B = B + rotl(f_val, MD5_S[i]);
                    };
                    
                    // Add this chunk's hash to result so far
                    ctx.state[0] += A;
                    ctx.state[1] += B;
                    ctx.state[2] += C;
                    ctx.state[3] += D;
                    return;
                };
                
                // Update MD5 with datax
                def md5_update(MD5_CTX* ctx, byte* datax, u64 len) -> void
                {
                    u32 buffer_index;
                    u32 buffer_space;
                    u64 i;
                    
                    // Compute number of bytes mod 64
                    buffer_index = (u32)((ctx.count >> 3) & 0x3F);
                    
                    // Update bit count
                    ctx.count += len * 8;
                    
                    buffer_space = 64 - buffer_index;
                    
                    // Transform as many times as possible
                    if (len >= buffer_space)
                    {
                        // Fill buffer
                        for (i = 0; i < buffer_space; i++)
                        {
                            ctx.buffer[buffer_index + i] = datax[i];
                        };
                        
                        md5_transform(ctx, ctx.buffer);
                        
                        // Process full blocks
                        i = buffer_space;
                        while (i + 63 < len)
                        {
                            md5_transform(ctx, datax + i);
                            i += 64;
                        };
                        
                        buffer_index = 0;
                    }
                    else
                    {
                        i = 0;
                    };
                    
                    // Buffer remaining input
                    while (i < len)
                    {
                        ctx.buffer[buffer_index] = datax[i];
                        buffer_index++;
                        i++;
                    };
                    return;
                };
                
                // Finalize MD5 hash
                def md5_final(MD5_CTX* ctx, byte* digest) -> void
                {
                    byte[8] bits;
                    u32 index, pad_len;
                    u32 i;
                    
                    // Save number of bits
                    for (i = 0; i < 8; i++)
                    {
                        bits[i] = (byte)((ctx.count >> (i * 8)) & 0xFF);
                    };
                    
                    // Pad to 56 bytes mod 64
                    index = (u32)((ctx.count >> 3) & 0x3F);
                    pad_len = 0;
                    if (index < 56)
                    {
                        pad_len = 56 - index;
                    }
                    else
                    {
                        pad_len = 120 - index;
                    };
                    
                    // Create padding
                    byte[64] padding;
                    padding[0] = (byte)0x80;
                    for (i = 1; i < 64; i++)
                    {
                        padding[i] = '\0';
                    };
                    
                    md5_update(ctx, padding, pad_len);
                    md5_update(ctx, bits, 8);
                    
                    // Store state in digest (little-endian)
                    for (i = 0; i < 4; i++)
                    {
                        digest[i * 4 .. i * 4 + 3] = (byte[4])(le32)ctx.state[i];
                    };
                    return;
                };
            };
        };

        namespace encryption
        {
            namespace AES
            {
                // AES context structure
                struct AES_CTX
                {
                    u32[44] round_keys;     // Expanded key schedule (11 rounds * 4 words)
                    u32 nr;                 // Number of rounds (10 for AES-128)
                };
                
                // AES S-Box (Substitution box)
                const byte[256] SBOX = [
                    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
                    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
                    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
                    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
                    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
                    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
                    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
                    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
                    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
                    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
                    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
                    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
                    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
                    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
                    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
                    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16
                ];
                
                // Inverse S-Box (for decryption)
                const byte[256] INV_SBOX = [
                    0x52, 0x09, 0x6A, 0xD5, 0x30, 0x36, 0xA5, 0x38, 0xBF, 0x40, 0xA3, 0x9E, 0x81, 0xF3, 0xD7, 0xFB,
                    0x7C, 0xE3, 0x39, 0x82, 0x9B, 0x2F, 0xFF, 0x87, 0x34, 0x8E, 0x43, 0x44, 0xC4, 0xDE, 0xE9, 0xCB,
                    0x54, 0x7B, 0x94, 0x32, 0xA6, 0xC2, 0x23, 0x3D, 0xEE, 0x4C, 0x95, 0x0B, 0x42, 0xFA, 0xC3, 0x4E,
                    0x08, 0x2E, 0xA1, 0x66, 0x28, 0xD9, 0x24, 0xB2, 0x76, 0x5B, 0xA2, 0x49, 0x6D, 0x8B, 0xD1, 0x25,
                    0x72, 0xF8, 0xF6, 0x64, 0x86, 0x68, 0x98, 0x16, 0xD4, 0xA4, 0x5C, 0xCC, 0x5D, 0x65, 0xB6, 0x92,
                    0x6C, 0x70, 0x48, 0x50, 0xFD, 0xED, 0xB9, 0xDA, 0x5E, 0x15, 0x46, 0x57, 0xA7, 0x8D, 0x9D, 0x84,
                    0x90, 0xD8, 0xAB, 0x00, 0x8C, 0xBC, 0xD3, 0x0A, 0xF7, 0xE4, 0x58, 0x05, 0xB8, 0xB3, 0x45, 0x06,
                    0xD0, 0x2C, 0x1E, 0x8F, 0xCA, 0x3F, 0x0F, 0x02, 0xC1, 0xAF, 0xBD, 0x03, 0x01, 0x13, 0x8A, 0x6B,
                    0x3A, 0x91, 0x11, 0x41, 0x4F, 0x67, 0xDC, 0xEA, 0x97, 0xF2, 0xCF, 0xCE, 0xF0, 0xB4, 0xE6, 0x73,
                    0x96, 0xAC, 0x74, 0x22, 0xE7, 0xAD, 0x35, 0x85, 0xE2, 0xF9, 0x37, 0xE8, 0x1C, 0x75, 0xDF, 0x6E,
                    0x47, 0xF1, 0x1A, 0x71, 0x1D, 0x29, 0xC5, 0x89, 0x6F, 0xB7, 0x62, 0x0E, 0xAA, 0x18, 0xBE, 0x1B,
                    0xFC, 0x56, 0x3E, 0x4B, 0xC6, 0xD2, 0x79, 0x20, 0x9A, 0xDB, 0xC0, 0xFE, 0x78, 0xCD, 0x5A, 0xF4,
                    0x1F, 0xDD, 0xA8, 0x33, 0x88, 0x07, 0xC7, 0x31, 0xB1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xEC, 0x5F,
                    0x60, 0x51, 0x7F, 0xA9, 0x19, 0xB5, 0x4A, 0x0D, 0x2D, 0xE5, 0x7A, 0x9F, 0x93, 0xC9, 0x9C, 0xEF,
                    0xA0, 0xE0, 0x3B, 0x4D, 0xAE, 0x2A, 0xF5, 0xB0, 0xC8, 0xEB, 0xBB, 0x3C, 0x83, 0x53, 0x99, 0x61,
                    0x17, 0x2B, 0x04, 0x7E, 0xBA, 0x77, 0xD6, 0x26, 0xE1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0C, 0x7D
                ];
                
                // Round constants for key expansion
                const u32[10] RCON = [
                    0x01000000, 0x02000000, 0x04000000, 0x08000000,
                    0x10000000, 0x20000000, 0x40000000, 0x80000000,
                    0x1B000000, 0x36000000
                ];
                
                // Galois Field multiplication by 2
                def gmul2(byte b) -> byte
                {
                    if ((b & 0x80) != 0)
                    {
                        return (byte)((b << 1) ^^ 0x1B);
                    }
                    else
                    {
                        return (byte)(b << 1);
                    };
                    return '\0';
                };
                
                // Galois Field multiplication by 3
                def gmul3(byte b) -> byte
                {
                    return gmul2(b) ^^ b;
                };
                
                // SubBytes transformation
                def sub_bytes(byte* state) -> void
                {
                    u32 i;
                    for (i = 0; i < 16; i++)
                    {
                        state[i] = (byte)(SBOX[(state[i] & 0xFF)] & 0xFF);
                    };
                    return;
                };
                
                // Inverse SubBytes transformation
                def inv_sub_bytes(byte* state) -> void
                {
                    u32 i;
                    for (i = 0; i < 16; i++)
                    {
                        state[i] = (byte)(INV_SBOX[(state[i] & 0xFF)] & 0xFF);
                    };
                    return;
                };
                
                // ShiftRows transformation
                def shift_rows(byte* state) -> void
                {
                    byte temp;
                    
                    // Row 1: shift left by 1
                    temp = state[1];
                    state[1] = state[5];
                    state[5] = state[9];
                    state[9] = state[13];
                    state[13] = temp;
                    
                    // Row 2: shift left by 2
                    temp = state[2];
                    state[2] = state[10];
                    state[10] = temp;
                    temp = state[6];
                    state[6] = state[14];
                    state[14] = temp;
                    
                    // Row 3: shift left by 3
                    temp = state[15];
                    state[15] = state[11];
                    state[11] = state[7];
                    state[7] = state[3];
                    state[3] = temp;
                    return;
                };
                
                // Inverse ShiftRows transformation
                def inv_shift_rows(byte* state) -> void
                {
                    byte temp;
                    
                    // Row 1: shift right by 1
                    temp = state[13];
                    state[13] = state[9];
                    state[9] = state[5];
                    state[5] = state[1];
                    state[1] = temp;
                    
                    // Row 2: shift right by 2
                    temp = state[2];
                    state[2] = state[10];
                    state[10] = temp;
                    temp = state[6];
                    state[6] = state[14];
                    state[14] = temp;
                    
                    // Row 3: shift right by 3
                    temp = state[3];
                    state[3] = state[7];
                    state[7] = state[11];
                    state[11] = state[15];
                    state[15] = temp;
                    return;
                };
                
                // MixColumns transformation
                def mix_columns(byte* state) -> void
                {
                    byte[4] temp;
                    u32 col;
                    
                    // Mix each column
                    for (col = 0; col < 4; col++)
                    {
                        u32 base = col * 4;
                        temp[0..3] = [state[base + 0], state[base + 1], state[base + 2], state[base + 3]];
                        
                        state[base + 0] = gmul2(temp[0]) ^^ gmul3(temp[1]) ^^ temp[2] ^^ temp[3];
                        state[base + 1] = temp[0] ^^ gmul2(temp[1]) ^^ gmul3(temp[2]) ^^ temp[3];
                        state[base + 2] = temp[0] ^^ temp[1] ^^ gmul2(temp[2]) ^^ gmul3(temp[3]);
                        state[base + 3] = gmul3(temp[0]) ^^ temp[1] ^^ temp[2] ^^ gmul2(temp[3]);
                    };
                    return;
                };
                
                // Inverse MixColumns transformation
                def inv_mix_columns(byte* state) -> void
                {
                    byte[4] temp;
                    u32 col;
                    
                    // Mix each column
                    for (col = 0; col < 4; col++)
                    {
                        u32 base = col * 4;
                        temp[0..3] = [state[base + 0], state[base + 1], state[base + 2], state[base + 3]];

                        // Multiply by inverse matrix in GF(2^8)
                        // 0x0E, 0x0B, 0x0D, 0x09
                        state[base + 0] = (byte)(
                            gmul2(gmul2(gmul2(temp[0]))) ^^ gmul2(gmul2(temp[0])) ^^ gmul2(temp[0]) ^^  // 0x0E
                            gmul2(gmul2(gmul2(temp[1]))) ^^ gmul2(temp[1]) ^^ temp[1] ^^                // 0x0B
                            gmul2(gmul2(gmul2(temp[2]))) ^^ gmul2(gmul2(temp[2])) ^^ temp[2] ^^         // 0x0D
                            gmul2(gmul2(gmul2(temp[3]))) ^^ temp[3]                                      // 0x09
                        );
                        
                        state[base + 1] = (byte)(
                            gmul2(gmul2(gmul2(temp[0]))) ^^ temp[0] ^^
                            gmul2(gmul2(gmul2(temp[1]))) ^^ gmul2(gmul2(temp[1])) ^^ gmul2(temp[1]) ^^
                            gmul2(gmul2(gmul2(temp[2]))) ^^ gmul2(temp[2]) ^^ temp[2] ^^
                            gmul2(gmul2(gmul2(temp[3]))) ^^ gmul2(gmul2(temp[3])) ^^ temp[3]
                        );
                        
                        state[base + 2] = (byte)(
                            gmul2(gmul2(gmul2(temp[0]))) ^^ gmul2(gmul2(temp[0])) ^^ temp[0] ^^
                            gmul2(gmul2(gmul2(temp[1]))) ^^ temp[1] ^^
                            gmul2(gmul2(gmul2(temp[2]))) ^^ gmul2(gmul2(temp[2])) ^^ gmul2(temp[2]) ^^
                            gmul2(gmul2(gmul2(temp[3]))) ^^ gmul2(temp[3]) ^^ temp[3]
                        );
                        
                        state[base + 3] = (byte)(
                            gmul2(gmul2(gmul2(temp[0]))) ^^ gmul2(temp[0]) ^^ temp[0] ^^
                            gmul2(gmul2(gmul2(temp[1]))) ^^ gmul2(gmul2(temp[1])) ^^ temp[1] ^^
                            gmul2(gmul2(gmul2(temp[2]))) ^^ temp[2] ^^
                            gmul2(gmul2(gmul2(temp[3]))) ^^ gmul2(gmul2(temp[3])) ^^ gmul2(temp[3])
                        );
                    };
                    return;
                };
                
                // AddRoundKey transformation
                def add_round_key(byte* state, u32* round_key) -> void
                {
                    u32 col;
                    // Each round_key word corresponds to a column
                    for (col = 0; col < 4; col++)
                    {
                        u32 base = col * 4;
                        state[base + 0] = state[base + 0] ^^ (byte)((round_key[col] >> 24) & 0xFF);
                        state[base + 1] = state[base + 1] ^^ (byte)((round_key[col] >> 16) & 0xFF);
                        state[base + 2] = state[base + 2] ^^ (byte)((round_key[col] >> 8) & 0xFF);
                        state[base + 3] = state[base + 3] ^^ (byte)(round_key[col] & 0xFF);
                    };
                    return;
                };
                
                // SubWord - apply S-box to each byte of a word
                def sub_word(u32 word) -> u32
                {
                    return (((u32)(SBOX[((word >> 24) & 0xFF)] & 0xFF)) << 24) |
                           (((u32)(SBOX[((word >> 16) & 0xFF)] & 0xFF)) << 16) |
                           (((u32)(SBOX[((word >> 8) & 0xFF)] & 0xFF)) << 8) |
                           ((u32)(SBOX[(word & 0xFF)] & 0xFF));
                };
                
                // RotWord - rotate word left by 8 bits
                def rot_word(u32 word) -> u32
                {
                    return ((word << 8) | (word >> 24));
                };
                
                // Key expansion for AES-128
                def aes_key_expansion(AES_CTX* ctx, byte* key) -> void
                {
                    u32 i;
                    u32 temp;
                    
                    // First 4 words are the key itself
                    for (i = 0; i < 4; i++)
                    {
                        ctx.round_keys[i] = (((u32)key[i * 4] & 0xFF) << 24) |
                                            (((u32)key[i * 4 + 1] & 0xFF) << 16) |
                                            (((u32)key[i * 4 + 2] & 0xFF) << 8) |
                                            ((u32)key[i * 4 + 3] & 0xFF);
                    };
                    
                    // Generate remaining round keys
                    for (i = 4; i < 44; i++)
                    {
                        temp = ctx.round_keys[i - 1];
                        
                        if ((i % 4) == 0)
                        {
                            temp = sub_word(rot_word(temp)) ^^ RCON[i / 4 - 1];
                        };
                        
                        ctx.round_keys[i] = ctx.round_keys[i - 4] ^^ temp;
                    };
                    
                    ctx.nr = 10;
                    return;
                };
                
                // AES-128 encryption
                def aes_encrypt_block(AES_CTX* ctx, byte* plaintext, byte* ciphertext) -> void
                {
                    byte[16] state;
                    u32 i;
                    u32 round;
                    
                    // Copy plaintext to state
                    for (i = 0; i < 16; i++)
                    {
                        state[i] = plaintext[i];
                    };
                    
                    // Initial round key addition
                    add_round_key(state, @ctx.round_keys[0]);
                    
                    // Main rounds
                    for (round = 1; round < ctx.nr; round++)
                    {
                        sub_bytes(state);
                        shift_rows(state);
                        mix_columns(state);
                        add_round_key(state, @ctx.round_keys[round * 4]);
                    };
                    
                    // Final round (no MixColumns)
                    sub_bytes(state);
                    shift_rows(state);
                    add_round_key(state, @ctx.round_keys[ctx.nr * 4]);
                    
                    // Copy state to ciphertext
                    for (i = 0; i < 16; i++)
                    {
                        ciphertext[i] = state[i];
                    };
                    return;
                };
                
                // AES-128 decryption
                def aes_decrypt_block(AES_CTX* ctx, byte* ciphertext, byte* plaintext) -> void
                {
                    byte[16] state;
                    u32 i;
                    u32 round;
                    
                    // Copy ciphertext to state
                    for (i = 0; i < 16; i++)
                    {
                        state[i] = ciphertext[i];
                    };
                    
                    // Initial round key addition
                    add_round_key(state, @ctx.round_keys[ctx.nr * 4]);
                    
                    // Main rounds in reverse
                    for (round = ctx.nr - 1; round > 0; round--)
                    {
                        inv_shift_rows(state);
                        inv_sub_bytes(state);
                        add_round_key(state, @ctx.round_keys[round * 4]);
                        inv_mix_columns(state);
                    };
                    
                    // Final round (no InvMixColumns)
                    inv_shift_rows(state);
                    inv_sub_bytes(state);
                    add_round_key(state, @ctx.round_keys[0]);
                    
                    // Copy state to plaintext
                    for (i = 0; i < 16; i++)
                    {
                        plaintext[i] = state[i];
                    };
                    return;
                };

                // =====================================================================
                // AES-GCM  (Galois/Counter Mode)
                //
                // Provides authenticated encryption with associated data (AEAD).
                // Supports AES-128 only (matches the AES_CTX key schedule above).
                //
                // GCM builds on two primitives:
                //   CTR mode  -- stream cipher using AES-ECB on an incrementing counter
                //   GHASH     -- polynomial authentication over GF(2^128)
                //
                // The GF(2^128) field uses the reduction polynomial:
                //   x^128 + x^7 + x^2 + x + 1   (0xE1 in the "reflected" representation)
                //
                // Public API:
                //   gcm_init(GCM_CTX*, key[16])
                //   gcm_encrypt(GCM_CTX*, iv[12], aad, aad_len, plain, plain_len, cipher, tag[16])
                //   gcm_decrypt(GCM_CTX*, iv[12], aad, aad_len, cipher, cipher_len, plain, tag[16]) -> int
                //     returns 1 if tag verifies, 0 if tampered
                // =====================================================================

                // GCM context — stores expanded key and the GHASH subkey H
                struct GCM_CTX
                {
                    AES_CTX aes;        // AES-128 key schedule
                    byte[16] H;         // GHASH subkey: AES_K(0^128)
                };

                // ------------------------------------------------------------------
                // ghash_mul: X = X * Y  in GF(2^128)
                //
                // Uses the standard "shift-and-XOR" algorithm with the GCM
                // reduction polynomial 0xE1000000_00000000_00000000_00000000
                // (MSB-first bit ordering as per NIST SP 800-38D).
                //
                // Both X and Y are 16-byte big-endian blocks.
                // Result is written back into X.
                // ------------------------------------------------------------------
                def ghash_mul(byte* X, byte* Y) -> void
                {
                    byte[16] Z, V;
                    int i, j, k;
                    byte lsb;

                    // Z = 0 (result accumulator), V = Y
                    for (i = 0; i < 16; i++)
                    {
                        Z[i] = '\0';
                        V[i] = Y[i];
                    };

                    // Process each bit of X, MSB first
                    for (i = 0; i < 16; i++)
                    {
                        for (j = 7; j >= 0; j--)
                        {
                            // If bit (i*8 + (7-j)) of X is set, Z ^= V
                            if ((((u32)(X[i] & 0xFF) >> j) & 1) != 0)
                            {
                                for (k = 0; k < 16; k++)
                                {
                                    Z[k] = Z[k] ^^ V[k];
                                };
                            };

                            // V = V >> 1 in GF(2^128), then reduce if LSB(V) was 1
                            lsb = V[15] & 1;

                            // Shift V right by one bit (big-endian: byte[0] is MSB)
                            for (k = 15; k > 0; k--)
                            {
                                V[k] = (byte)(((u32)(V[k] & 0xFF) >> 1) | ((u32)(V[k - 1] & 1) << 7));
                            };
                            V[0] = (byte)((u32)(V[0] & 0xFF) >> 1);

                            // If the bit shifted out was 1, XOR with reduction polynomial
                            if (lsb != 0)
                            {
                                V[0] = V[0] ^^ (byte)0xE1;
                            };
                        };
                    };

                    for (i = 0; i < 16; i++)
                    {
                        X[i] = Z[i];
                    };
                    return;
                };

                // ------------------------------------------------------------------
                // ghash: Compute GHASH_H(A) over a sequence of blocks.
                //
                //   H    : 16-byte GHASH subkey
                //   input: byte stream (need not be block-aligned)
                //   len  : byte length of input
                //   tag  : running 16-byte accumulator (in/out)
                //
                // Pads the final partial block with zeros before hashing.
                // ------------------------------------------------------------------
                def ghash_update(byte* H, byte* input, int len, byte* tag) -> void
                {
                    byte[16] block;
                    int i, blocks, rem, b, offset;

                    blocks = len / 16;
                    rem    = len - (blocks * 16);

                    // Full blocks
                    for (b = 0; b < blocks; b++)
                    {
                        offset = b * 16;
                        for (i = 0; i < 16; i++)
                        {
                            tag[i] = tag[i] ^^ input[offset + i];
                        };
                        ghash_mul(tag, H);
                    };

                    // Final partial block (zero-padded)
                    if (rem > 0)
                    {
                        for (i = 0; i < 16; i++)
                        {
                            block[i] = '\0';
                        };
                        offset = blocks * 16;
                        for (i = 0; i < rem; i++)
                        {
                            block[i] = input[offset + i];
                        };
                        for (i = 0; i < 16; i++)
                        {
                            tag[i] = tag[i] ^^ block[i];
                        };
                        ghash_mul(tag, H);
                    };
                    return;
                };

                // ------------------------------------------------------------------
                // gcm_inc32: increment the 32-bit counter in bytes [12..15]
                //            of a 16-byte counter block (big-endian).
                // ------------------------------------------------------------------
                def gcm_inc32(byte* ctr) -> void
                {
                    int i;
                    for (i = 15; i >= 12; i--)
                    {
                        ctr[i] = (byte)(ctr[i] + 1);
                        if (ctr[i] != '\0')
                        {
                            return;
                        };
                    };
                    return;
                };

                // ------------------------------------------------------------------
                // gcm_init: Prepare a GCM_CTX from a 16-byte AES-128 key.
                //
                //   Expands the key schedule and computes H = AES_K(0^128).
                // ------------------------------------------------------------------
                def gcm_init(GCM_CTX* ctx, byte* key) -> void
                {
                    byte[16] zero_block;
                    int i;

                    aes_key_expansion(@ctx.aes, key);

                    for (i = 0; i < 16; i++)
                    {
                        zero_block[i] = '\0';
                    };

                    aes_encrypt_block(@ctx.aes, @zero_block[0], @ctx.H[0]);
                    return;
                };

                // ------------------------------------------------------------------
                // gcm_encrypt: Encrypt and authenticate with AES-128-GCM.
                //
                //   ctx      : initialised GCM_CTX
                //   iv       : 12-byte IV (96-bit nonce, per NIST recommendation)
                //   aad      : additional authenticated data (may be null if aad_len==0)
                //   aad_len  : byte length of aad
                //   plain    : plaintext input
                //   plain_len: byte length of plaintext
                //   cipher   : output buffer for ciphertext (same length as plaintext)
                //   tag      : output buffer for 16-byte authentication tag
                // ------------------------------------------------------------------
                def gcm_encrypt(GCM_CTX* ctx,
                                byte* iv,
                                byte* aad,      int aad_len,
                                byte* plain,    int plain_len,
                                byte* cipher,
                                byte* tag) -> void
                {
                    byte[16] J0, ctr, ks, auth_tag;
                    byte[16] len_block;
                    int i, full_blocks, rem, b, offset;
                    u64 aad_bits, plain_bits;

                    // Build J0 = IV || 0x00000001  (96-bit IV + 32-bit counter = 1)
                    for (i = 0; i < 12; i++)
                    {
                        J0[i] = iv[i];
                    };
                    J0[12..15] = "\x00\x00\x00\x01";

                    // ctr = J0 incremented once for the first keystream block
                    for (i = 0; i < 16; i++)
                    {
                        ctr[i] = J0[i];
                    };
                    gcm_inc32(@ctr[0]);

                    // auth_tag accumulator starts at zero
                    for (i = 0; i < 16; i++)
                    {
                        auth_tag[i] = '\0';
                    };

                    // GHASH over AAD
                    if (aad_len > 0)
                    {
                        ghash_update(@ctx.H[0], aad, aad_len, @auth_tag[0]);
                    };

                    // CTR encryption + GHASH over ciphertext
                    full_blocks = plain_len / 16;
                    rem         = plain_len - (full_blocks * 16);

                    for (b = 0; b < full_blocks; b++)
                    {
                        offset = b * 16;
                        aes_encrypt_block(@ctx.aes, @ctr[0], @ks[0]);
                        gcm_inc32(@ctr[0]);
                        for (i = 0; i < 16; i++)
                        {
                            cipher[offset + i] = plain[offset + i] ^^ ks[i];
                        };
                    };

                    if (rem > 0)
                    {
                        offset = full_blocks * 16;
                        aes_encrypt_block(@ctx.aes, @ctr[0], @ks[0]);
                        for (i = 0; i < rem; i++)
                        {
                            cipher[offset + i] = plain[offset + i] ^^ ks[i];
                        };
                    };

                    // GHASH over ciphertext
                    if (plain_len > 0)
                    {
                        ghash_update(@ctx.H[0], cipher, plain_len, @auth_tag[0]);
                    };

                    // GHASH over lengths: len(AAD) || len(ciphertext) in bits, big-endian 64-bit each
                    aad_bits   = (u64)aad_len   * 8u;
                    plain_bits = (u64)plain_len * 8u;

                    len_block[0..7]  = (byte[8])(be64)aad_bits;
                    len_block[8..15] = (byte[8])(be64)plain_bits;

                    for (i = 0; i < 16; i++)
                    {
                        auth_tag[i] = auth_tag[i] ^^ len_block[i];
                    };
                    ghash_mul(@auth_tag[0], @ctx.H[0]);

                    // tag = GCTR(K, J0, auth_tag) = AES_K(J0) XOR auth_tag
                    aes_encrypt_block(@ctx.aes, @J0[0], @ks[0]);
                    for (i = 0; i < 16; i++)
                    {
                        tag[i] = auth_tag[i] ^^ ks[i];
                    };
                    return;
                };

                // ------------------------------------------------------------------
                // gcm_decrypt: Decrypt and verify with AES-128-GCM.
                //
                //   ctx       : initialised GCM_CTX
                //   iv        : 12-byte IV used during encryption
                //   aad       : additional authenticated data
                //   aad_len   : byte length of aad
                //   cipher    : ciphertext input
                //   cipher_len: byte length of ciphertext
                //   plain     : output buffer for plaintext (same length as ciphertext)
                //   tag       : 16-byte tag to verify against
                //
                // Returns 1 if the tag is valid, 0 if the message has been tampered.
                // The plaintext output is always written; caller must discard it on failure.
                // ------------------------------------------------------------------
                def gcm_decrypt(GCM_CTX* ctx,
                                byte* iv,
                                byte* aad,       int aad_len,
                                byte* cipher,    int cipher_len,
                                byte* plain,
                                byte* tag) -> int
                {
                    byte[16] J0, ctr, ks, auth_tag, expected_tag;
                    byte[16] len_block;
                    int i, full_blocks, rem, b, offset, diff;
                    u64 aad_bits, cipher_bits;

                    // Build J0 = IV || 0x00000001
                    for (i = 0; i < 12; i++)
                    {
                        J0[i] = iv[i];
                    };
                    J0[12..15] = "\x00\x00\x00\x01";

                    // ctr starts at J0+1
                    for (i = 0; i < 16; i++)
                    {
                        ctr[i] = J0[i];
                    };
                    gcm_inc32(@ctr[0]);

                    for (i = 0; i < 16; i++)
                    {
                        auth_tag[i] = '\0';
                    };

                    // GHASH over AAD
                    if (aad_len > 0)
                    {
                        ghash_update(@ctx.H[0], aad, aad_len, @auth_tag[0]);
                    };

                    // GHASH over ciphertext (before decryption)
                    if (cipher_len > 0)
                    {
                        ghash_update(@ctx.H[0], cipher, cipher_len, @auth_tag[0]);
                    };

                    // GHASH over lengths
                    aad_bits    = (u64)aad_len    * 8u;
                    cipher_bits = (u64)cipher_len * 8u;

                    len_block[0..7]  = (byte[8])(be64)aad_bits;
                    len_block[8..15] = (byte[8])(be64)cipher_bits;

                    for (i = 0; i < 16; i++)
                    {
                        auth_tag[i] = auth_tag[i] ^^ len_block[i];
                    };
                    ghash_mul(@auth_tag[0], @ctx.H[0]);

                    // expected_tag = AES_K(J0) XOR auth_tag
                    aes_encrypt_block(@ctx.aes, @J0[0], @ks[0]);
                    for (i = 0; i < 16; i++)
                    {
                        expected_tag[i] = auth_tag[i] ^^ ks[i];
                    };

                    // Constant-time tag comparison (prevent timing side-channels)
                    diff = 0;
                    for (i = 0; i < 16; i++)
                    {
                        diff = diff | ((int)(expected_tag[i] ^^ tag[i]));
                    };

                    // CTR decryption (always performed; caller discards on diff != 0)
                    full_blocks = cipher_len / 16;
                    rem         = cipher_len - (full_blocks * 16);

                    for (b = 0; b < full_blocks; b++)
                    {
                        offset = b * 16;
                        aes_encrypt_block(@ctx.aes, @ctr[0], @ks[0]);
                        gcm_inc32(@ctr[0]);
                        for (i = 0; i < 16; i++)
                        {
                            plain[offset + i] = cipher[offset + i] ^^ ks[i];
                        };
                    };

                    if (rem > 0)
                    {
                        offset = full_blocks * 16;
                        aes_encrypt_block(@ctx.aes, @ctr[0], @ks[0]);
                        for (i = 0; i < rem; i++)
                        {
                            plain[offset + i] = cipher[offset + i] ^^ ks[i];
                        };
                    };

                    return (diff == 0) ? 1 : 0;
                };
            };
        };

        namespace ECDH
        {
            namespace X25519
            {
                // =========================================================================
                // X25519 Elliptic Curve Diffie-Hellman
                //
                // Curve: y² = x³ + 486662x² + x  over  GF(p),  p = 2^255 - 19
                //
                // Uses BigInt arithmetic mod p. p = 2^255 - 19 is represented as a
                // BigInt with 8 uint limbs (256 bits, upper bit always 0 after reduction).
                //
                // Public API:
                //   x25519(out[32], scalar[32], point[32])  -- DH shared secret
                //   x25519_pubkey(out[32], scalar[32])       -- scalar x base point
                // =========================================================================

                // ---- Load/store ----

                // Load 32 little-endian bytes into a BigInt.
                def fe_from_bytes(BigInt* out, byte* src) -> void
                {
                    uint i, j;
                    uint* d = @out.digits[0];
                    for (i = 0; i < 9; i++) { d[i] = 0; };
                    for (i = 0; i < 8; i++)
                    {
                        j = i * 4;
                        d[i] = *(le32*)@src[j];
                    };
                    out.length = 8;
                    out.negative = false;
                    math::bigint::bigint_normalize(out);
                    // Clear high bit (RFC 7748: mask u-coordinate MSB)
                    if (out.length == 8) { d[7] = d[7] & 0x7FFFFFFF; };
                    math::bigint::bigint_normalize(out);
                    return;
                };

                // Store a BigInt to 32 little-endian bytes (already reduced mod p).
                def fe_to_bytes(byte* dst, BigInt* src) -> void
                {
                    uint i, j;
                    uint* d = @src.digits[0];
                    uint word;
                    for (i = 0; i < 8; i++)
                    {
                        j = i * 4;
                        word = (i < src.length) ? d[i] : 0u;
                        dst[j]     = (byte)(word & 0xFF);
                        dst[j + 1] = (byte)((word >> 8)  & 0xFF);
                        dst[j + 2] = (byte)((word >> 16) & 0xFF);
                        dst[j + 3] = (byte)((word >> 24) & 0xFF);
                    };
                    return;
                };

                // ---- Field operations ----
                // All operations reduce mod p where needed.
                // p is built at call time from the known constant.

                def fe_set_p(BigInt* p) -> void
                {
                    // p = 2^255 - 19
                    // = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF ED
                    // In 8 uint limbs LE:
                    //   limbs 0..6: 0xFFFFFFFF
                    //   limb 7:     0x7FFFFFFF
                    // Then subtract 18 from limb 0 (since 2^255 - 19 = 0x7FFF...FFED)
                    // Actually: -19 = 0xFFFF...FFED in the low bits.
                    // 2^255 - 19:
                    //   low 32 bits: 0xFFFFFFED (= 4294967277)
                    //   next 6 words: 0xFFFFFFFF
                    //   top word (bits 224-255): 0x7FFFFFFF
                    uint* pd = @p.digits[0];

                    pd = [0xFFFFFFEDu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu,
                          0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0x7FFFFFFF];

                    p.length = 8;
                    p.negative = false;
                    return;
                };

                def fe_add(BigInt* out, BigInt* a, BigInt* b) -> void
                {
                    BigInt p, tmp;
                    fe_set_p(@p);
                    math::bigint::bigint_add(@tmp, a, b);
                    math::bigint::bigint_mod(out, @tmp, @p);
                    return;
                };

                def fe_sub(BigInt* out, BigInt* a, BigInt* b) -> void
                {
                    BigInt p, tmp;
                    fe_set_p(@p);
                    math::bigint::bigint_sub(@tmp, a, b);
                    // If negative, add p
                    if (tmp.negative)
                    {
                        math::bigint::bigint_add(out, @tmp, @p);
                        // May still be negative if a was 0 and b was large; add p again
                        if (out.negative)
                        {
                            math::bigint::bigint_add(@tmp, out, @p);
                            math::bigint::bigint_copy(out, @tmp);
                        };
                    }
                    else
                    {
                        math::bigint::bigint_mod(out, @tmp, @p);
                    };
                    return;
                };

                def fe_mul(BigInt* out, BigInt* a, BigInt* b) -> void
                {
                    BigInt p, tmp;
                    fe_set_p(@p);
                    math::bigint::bigint_mul(@tmp, a, b);
                    math::bigint::bigint_mod(out, @tmp, @p);
                    return;
                };

                def fe_sq(BigInt* out, BigInt* a) -> void
                {
                    fe_mul(out, a, a);
                    return;
                };

                // Constant-time conditional swap (not truly CT but correct)
                def fe_cswap(BigInt* a, BigInt* b, u64 cond) -> void
                {
                    BigInt tmp;
                    if (cond != 0u)
                    {
                        math::bigint::bigint_copy(@tmp, a);
                        math::bigint::bigint_copy(a, b);
                        math::bigint::bigint_copy(b, @tmp);
                    };
                    return;
                };

                // Invert: out = a^(p-2) mod p  (Fermat's little theorem)
                def fe_invert(BigInt* out, BigInt* a) -> void
                {
                    // p - 2 = 2^255 - 21
                    // Square-and-multiply: standard binary exponentiation
                    BigInt p, exp, base, result, tmp, bit_val, zero;
                    uint i, j;
                    u64 limb;

                    fe_set_p(@p);

                    // exp = p - 2: subtract 2 from p
                    math::bigint::bigint_from_uint(@tmp, 2);
                    math::bigint::bigint_sub(@exp, @p, @tmp);

                    // result = 1
                    math::bigint::bigint_one(@result);
                    math::bigint::bigint_copy(@base, a);

                    // Binary exponentiation: iterate over bits of exp from LSB
                    // exp has 8 uint limbs
                    uint* expd = @exp.digits[0];
                    uint exp_len = exp.length;

                    for (i = 0; i < exp_len; i++)
                    {
                        uint word = expd[i];
                        for (j = 0; j < 32; j++)
                        {
                            if ((word & 1) != 0)
                            {
                                fe_mul(@tmp, @result, @base);
                                math::bigint::bigint_copy(@result, @tmp);
                            };
                            word = word >> 1;
                            fe_sq(@tmp, @base);
                            math::bigint::bigint_copy(@base, @tmp);
                        };
                    };

                    math::bigint::bigint_copy(out, @result);
                    return;
                };

                // ---- Montgomery ladder ----
                def x25519(byte* out, byte* scalar, byte* point) -> void
                {
                    BigInt x1, x2, z2, x3, z3;
                    BigInt A, AA, B, BB, E, C, D, DA, CB, tmp, a24;
                    byte[32] e;
                    u32 i, j;
                    u64 bit, swap;

                    // Clamp scalar
                    while (j < 32) { e[j] = scalar[j]; j++; };
                    e[0]  = e[0]  & (byte)248;
                    e[31] = e[31] & (byte)127;
                    e[31] = e[31] | (byte)64;

                    // Load u-coordinate (mask high bit)
                    fe_from_bytes(@x1, point);

                    // x2 = 1, z2 = 0
                    math::bigint::bigint_one(@x2);
                    math::bigint::bigint_zero(@z2);
                    // x3 = x1, z3 = 1
                    math::bigint::bigint_copy(@x3, @x1);
                    math::bigint::bigint_one(@z3);

                    // a24 = 121665
                    math::bigint::bigint_from_uint(@a24, 121665);

                    i = 254;
                    while (i <= 254)
                    {
                        bit  = (u64)((e[i >> 3] >> (i & 7)) & 1);
                        swap = swap `^^ bit;
                        fe_cswap(@x2, @x3, swap);
                        fe_cswap(@z2, @z3, swap);
                        swap = bit;

                        fe_add(@A,  @x2, @z2);  fe_sq(@AA, @A);
                        fe_sub(@B,  @x2, @z2);  fe_sq(@BB, @B);
                        fe_sub(@E,  @AA, @BB);
                        fe_add(@C,  @x3, @z3);
                        fe_sub(@D,  @x3, @z3);
                        fe_mul(@DA, @D,  @A);
                        fe_mul(@CB, @C,  @B);
                        fe_add(@tmp, @DA, @CB);  fe_sq(@x3, @tmp);
                        fe_sub(@tmp, @DA, @CB);  fe_sq(@z3, @tmp);
                        fe_mul(@z3, @x1, @z3);
                        fe_mul(@x2, @AA, @BB);
                        fe_mul(@tmp, @a24, @E);
                        fe_add(@tmp, @AA, @tmp);
                        fe_mul(@z2, @E, @tmp);

                        switch (i == 0) { case (1) { break; } default {}; };
                        i--;
                    };

                    fe_cswap(@x2, @x3, swap);
                    fe_cswap(@z2, @z3, swap);

                    fe_invert(@z2, @z2);
                    fe_mul(@x2, @x2, @z2);
                    fe_to_bytes(out, @x2);
                    return;
                };

                def x25519_pubkey(byte* out, byte* scalar) -> void
                {
                    byte[32] base;
                    u32 i;
                    i = 0;
                    while (i < 32) { base[i] = (byte)0; i++; };
                    base[0] = (byte)9;
                    x25519(out, scalar, @base[0]);
                    return;
                };

            };  // namespace X25519
        };

        namespace KDF
        {
            namespace HKDF
            {

                #def HKDF_HASHLEN 32;
                #def HKDF_BLOCKLEN 64;

                // ------------------------------------------------------------------
                // Internal: HMAC-SHA256(key[key_len], msg[msg_len]) -> out[32]
                //
                // Laid out inline here so HKDF has no external dependency beyond
                // the SHA-256 primitives already in cryptography.fx.
                // ------------------------------------------------------------------
                def hmac_sha256(byte* key, int key_len,
                                byte* msg, int msg_len,
                                byte* out) -> void
                {
                    byte[64] ipad_key, opad_key;
                    byte[32] inner_hash, hashed_key;
                    SHA256_CTX inner_ctx, outer_ctx, key_ctx;
                    byte* effective_key;
                    int effective_key_len, i;
                    byte k;

                    // RFC 2104 §2: if key is longer than block size, hash it first
                    if (key_len > 64)
                    {
                        SHA256::sha256_init(@key_ctx);
                        SHA256::sha256_update(@key_ctx, key, (u64)key_len);
                        SHA256::sha256_final(@key_ctx, @hashed_key[0]);
                        effective_key = @hashed_key[0];
                        effective_key_len = 32;
                    }
                    else
                    {
                        effective_key = key;
                        effective_key_len = key_len;
                    };

                    for (i = 0; i < 64; i++)
                    {
                        k = (i < effective_key_len) ? effective_key[i] : (byte)0;
                        ipad_key[i] = k ^^ (byte)0x36;
                        opad_key[i] = k ^^ (byte)0x5C;
                    };

                    SHA256::sha256_init(@inner_ctx);
                    SHA256::sha256_update(@inner_ctx, @ipad_key[0], 64);
                    SHA256::sha256_update(@inner_ctx, msg, (u64)msg_len);
                    SHA256::sha256_final(@inner_ctx, @inner_hash[0]);

                    SHA256::sha256_init(@outer_ctx);
                    SHA256::sha256_update(@outer_ctx, @opad_key[0], 64);
                    SHA256::sha256_update(@outer_ctx, @inner_hash[0], 32);
                    SHA256::sha256_final(@outer_ctx, out);
                };

                // ------------------------------------------------------------------
                // HKDF-Extract
                //
                //   PRK = HMAC-SHA256(salt, ikm)
                //
                //   salt     : pointer to salt bytes; may be null
                //   salt_len : byte length of salt; ignored when salt is null
                //   ikm      : input keying material
                //   ikm_len  : byte length of ikm
                //   prk      : output buffer, must be >= 32 bytes
                // ------------------------------------------------------------------
                def hkdf_extract(byte* salt, int salt_len,
                                 byte* ikm,  int ikm_len,
                                 byte* prk) -> void
                {
                    // RFC 5869 §2.2: if salt is not provided, set to HashLen zero bytes
                    byte[32] zero_salt;
                    byte* effective_salt;
                    int effective_salt_len;

                    if (salt == (byte*)0)
                    {
                        effective_salt = @zero_salt[0];
                        effective_salt_len = 32;
                    }
                    else
                    {
                        effective_salt = salt;
                        effective_salt_len = salt_len;
                    };

                    hmac_sha256(effective_salt, effective_salt_len, ikm, ikm_len, prk);
                };

                // ------------------------------------------------------------------
                // HKDF-Expand
                //
                //   OKM = T(1) || T(2) || ... truncated to L bytes
                //   T(i) = HMAC-SHA256(PRK, T(i-1) || info || i)
                //
                //   prk      : pseudorandom key from hkdf_extract (32 bytes)
                //   info     : context-specific info string; may be null
                //   info_len : byte length of info; ignored when info is null
                //   okm      : output key material buffer
                //   okm_len  : requested output length in bytes (<= 8160)
                //
                // Returns 1 on success, 0 if okm_len > 255 * HKDF_HASHLEN.
                // ------------------------------------------------------------------
                def hkdf_expand(byte* prk,
                                byte* info,  int info_len,
                                byte* okm,   int okm_len) -> int
                {
                    // T(i-1): starts empty, then holds the previous 32-byte block
                    byte[32] t_prev, t_cur;
                    // HMAC input: T(i-1) || info || counter_byte
                    // Max size: 32 + info_len + 1 — but info_len is caller-controlled.
                    // We build it on the heap to handle arbitrary info lengths safely.
                    // For TLS 1.3 labels the info is always small (<= ~255 bytes),
                    // so a 320-byte stack buffer is enough and avoids fmalloc.
                    byte[320] hmac_in;
                    int n, i, j, offset, prev_len, copy_len, built;
                    byte counter;

                    if (okm_len > (255 * 32))
                    {
                        return 0;
                    };

                    // n = ceil(okm_len / HashLen)
                    n = (okm_len + 31) / 32;

                    for (i = 1; i <= n; i++)
                    {
                        // Build HMAC input: T(i-1) || info || i
                        built = 0;
                        prev_len = (i == 1) ? 0 : 32;

                        for (j = 0; j < prev_len; j++)
                        {
                            hmac_in[built] = t_prev[j];
                            built = built + 1;
                        };

                        if (info != (byte*)0)
                        {
                            for (j = 0; j < info_len; j++)
                            {
                                hmac_in[built] = info[j];
                                built = built + 1;
                            };
                        };

                        counter = (byte)i;
                        hmac_in[built] = counter;
                        built = built + 1;

                        hmac_sha256(prk, 32, @hmac_in[0], built, @t_cur[0]);

                        // Copy min(32, okm_len - offset) bytes to output
                        copy_len = okm_len - offset;
                        if (copy_len > 32)
                        {
                            copy_len = 32;
                        };

                        for (j = 0; j < copy_len; j++)
                        {
                            okm[offset + j] = t_cur[j];
                        };
                        offset = offset + copy_len;

                        // Promote t_cur -> t_prev for next iteration
                        for (j = 0; j < 32; j++)
                        {
                            t_prev[j] = t_cur[j];
                        };
                    };

                    return 1;
                };

                // ------------------------------------------------------------------
                // Convenience: full HKDF in one call
                //
                //   Combines Extract + Expand.
                //
                //   salt / salt_len : may pass null / 0 to use zero-byte salt
                //   ikm  / ikm_len  : input keying material
                //   info / info_len : context label; may pass null / 0
                //   okm  / okm_len  : output buffer and requested byte count
                //
                // Returns 1 on success, 0 on length violation.
                // ------------------------------------------------------------------
                def hkdf(byte* salt, int salt_len,
                         byte* ikm,  int ikm_len,
                         byte* info, int info_len,
                         byte* okm,  int okm_len) -> int
                {
                    byte[32] prk;

                    hkdf_extract(salt, salt_len, ikm, ikm_len, @prk[0]);
                    return hkdf_expand(@prk[0], info, info_len, okm, okm_len);
                };

            }; // HKDF
        }; // kdf

        namespace ECDSA
        {
            // =========================================================================
            // ECDSA over P-256 (secp256r1 / prime256v1)
            //
            // Curve:  y² = x³ - 3x + b  over  GF(p)
            //
            //   p  = 2^256 - 2^224 + 2^192 + 2^96 - 1
            //   n  = FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
            //   b  = 5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
            //   Gx = 6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
            //   Gy = 4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
            //
            // Public API:
            //   ecdsa_p256_load_scalar(BigInt* out, byte* src_be32)
            //   ecdsa_p256_store_scalar(byte* dst_be32, BigInt* src)
            //   ecdsa_p256_point_mul(BigInt* rx, BigInt* ry, BigInt* k, BigInt* px, BigInt* py)
            //   ecdsa_p256_pubkey(byte* qx32, byte* qy32, byte* privkey32)
            //   ecdsa_p256_sign(byte* sig_r32, byte* sig_s32, byte* privkey32,
            //                   byte* hash32, byte* nonce32) -> bool
            //   ecdsa_p256_verify(byte* sig_r32, byte* sig_s32, byte* pubx32, byte* puby32,
            //                     byte* hash32) -> bool
            //   ecdsa_p256_encode_der(byte* der_out, int* der_len, byte* r32, byte* s32)
            //   ecdsa_p256_decode_der(byte* r32, byte* s32, byte* der_in, int der_len) -> bool
            // =========================================================================

            // ---- Curve constants (global so they are not zero-initialized away) ----

            // p = FFFFFFFF 00000001 00000000 00000000 00000000 FFFFFFFF FFFFFFFF FFFFFFFF
            global uint[8] P256_P = [
                0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0x00000000u,
                0x00000000u, 0x00000000u, 0x00000001u, 0xFFFFFFFFu
            ];

            // n = FFFFFFFF 00000000 FFFFFFFF FFFFFFFF BCE6FAAD A7179E84 F3B9CAC2 FC632551
            global uint[8] P256_N = [
                0xFC632551u, 0xF3B9CAC2u, 0xA7179E84u, 0xBCE6FAADu,
                0xFFFFFFFFu, 0xFFFFFFFFu, 0x00000000u, 0xFFFFFFFFu
            ];

            // b = 5AC635D8 AA3A93E7 B3EBBD55 769886BC 651D06B0 CC53B0F6 3BCE3C3E 27D2604B
            global uint[8] P256_B = [
                0x27D2604Bu, 0x3BCE3C3Eu, 0xCC53B0F6u, 0x651D06B0u,
                0x769886BCu, 0xB3EBBD55u, 0xAA3A93E7u, 0x5AC635D8u
            ];

            // Gx = 6B17D1F2 E12C4247 F8BCE6E5 63A440F2 77037D81 2DEB33A0 F4A13945 D898C296
            global uint[8] P256_GX = [
                0xD898C296u, 0xF4A13945u, 0x2DEB33A0u, 0x77037D81u,
                0x63A440F2u, 0xF8BCE6E5u, 0xE12C4247u, 0x6B17D1F2u
            ];

            // Gy = 4FE342E2 FE1A7F9B 8EE7EB4A 7C0F9E16 2BCE3357 6B315ECE CBB64068 37BF51F5
            global uint[8] P256_GY = [
                0x37BF51F5u, 0xCBB64068u, 0x6B315ECEu, 0x2BCE3357u,
                0x7C0F9E16u, 0x8EE7EB4Au, 0xFE1A7F9Bu, 0x4FE342E2u
            ];

            // ---- Load / store (big-endian 32-byte scalars, per ECDSA convention) ----

            def ecdsa_p256_load_scalar(BigInt* out, byte* src) -> void
            {
                uint i, j;
                uint* d = @out.digits[0];
                for (i = 0; i < 9; i++) { d[i] = 0; };
                // 32 bytes big-endian -> 8 uint32 little-endian limbs
                for (i = 0; i < 8; i++)
                {
                    j = (7 - i) * 4;
                    d[i] = ((uint)src[j]     << 24) |
                           ((uint)src[j + 1] << 16) |
                           ((uint)src[j + 2] << 8)  |
                            (uint)src[j + 3];
                };
                out.length = 8;
                out.negative = false;
                math::bigint::bigint_normalize(out);
                return;
            };

            def ecdsa_p256_store_scalar(byte* dst, BigInt* src) -> void
            {
                uint i, j;
                uint* d = @src.digits[0];
                uint word;
                for (i = 0; i < 8; i++)
                {
                    j = (7 - i) * 4;
                    word = (i < src.length) ? d[i] : 0u;
                    dst[j]     = (byte)((word >> 24) & 0xFF);
                    dst[j + 1] = (byte)((word >> 16) & 0xFF);
                    dst[j + 2] = (byte)((word >> 8)  & 0xFF);
                    dst[j + 3] = (byte)(word & 0xFF);
                };
                return;
            };

            // ---- Field helpers (mod p) ----

            def p256_set_p(BigInt* out) -> void
            {
                uint* d = @out.digits[0];
                uint* s = @P256_P[0];
                uint i;
                for (i = 0; i < 8; i++) { d[i] = s[i]; };
                out.length = 8;
                out.negative = false;
                math::bigint::bigint_normalize(out);
                return;
            };

            def p256_set_n(BigInt* out) -> void
            {
                uint* d = @out.digits[0];
                uint* s = @P256_N[0];
                uint i;
                for (i = 0; i < 8; i++) { d[i] = s[i]; };
                out.length = 8;
                out.negative = false;
                math::bigint::bigint_normalize(out);
                return;
            };

            def p256_fp_add(BigInt* out, BigInt* a, BigInt* b) -> void
            {
                BigInt p, tmp;
                p256_set_p(@p);
                math::bigint::bigint_add(@tmp, a, b);
                math::bigint::bigint_mod(out, @tmp, @p);
                return;
            };

            def p256_fp_sub(BigInt* out, BigInt* a, BigInt* b) -> void
            {
                BigInt p, tmp;
                p256_set_p(@p);
                math::bigint::bigint_sub(@tmp, a, b);
                if (tmp.negative)
                {
                    math::bigint::bigint_add(@tmp, @tmp, @p);
                    if (tmp.negative)
                    {
                        math::bigint::bigint_add(out, @tmp, @p);
                    }
                    else
                    {
                        math::bigint::bigint_copy(out, @tmp);
                    };
                }
                else
                {
                    math::bigint::bigint_mod(out, @tmp, @p);
                };
                return;
            };

            def p256_fp_mul(BigInt* out, BigInt* a, BigInt* b) -> void
            {
                BigInt p, tmp;
                p256_set_p(@p);
                math::bigint::bigint_mul(@tmp, a, b);
                math::bigint::bigint_mod(out, @tmp, @p);
                return;
            };

            def p256_fp_sq(BigInt* out, BigInt* a) -> void
            {
                p256_fp_mul(out, a, a);
                return;
            };

            // Modular inverse in GF(p): out = a^(p-2) mod p  (Fermat's little theorem)
            def p256_fp_inv(BigInt* out, BigInt* a) -> void
            {
                BigInt p, exp, two, tmp;
                uint i, j;
                uint word;
                uint* expd;

                p256_set_p(@p);
                math::bigint::bigint_from_uint(@two, 2);
                math::bigint::bigint_sub(@exp, @p, @two);

                math::bigint::bigint_one(out);
                math::bigint::bigint_copy(@tmp, a);

                expd = @exp.digits[0];
                for (i = 0; i < exp.length; i++)
                {
                    word = expd[i];
                    for (j = 0; j < 32; j++)
                    {
                        if ((word & 1) != 0)
                        {
                            p256_fp_mul(out, out, @tmp);
                        };
                        word = word >> 1;
                        p256_fp_sq(@tmp, @tmp);
                    };
                };
                return;
            };

            // ---- Projective (Jacobian) point arithmetic ----
            //
            // A Jacobian point (X:Y:Z) represents affine (X/Z², Y/Z³).
            // The point at infinity is represented as Z = 0.

            // Point double in Jacobian coordinates over P-256.
            // Algorithm: standard Jacobian doubling for a = -3 curves.
            def p256_point_dbl(BigInt* rx, BigInt* ry, BigInt* rz,
                               BigInt* px, BigInt* py, BigInt* pz) -> void
            {
                // Copy inputs to locals first to handle in-place calls (rx==px etc.)
                BigInt X, Y, Z, t1, t2, t3, t4, t5, three, two;

                // If Z = 0 the point is at infinity, return as-is
                if (math::bigint::bigint_is_zero(pz))
                {
                    math::bigint::bigint_copy(rx, px);
                    math::bigint::bigint_copy(ry, py);
                    math::bigint::bigint_copy(rz, pz);
                    return;
                };

                math::bigint::bigint_copy(@X, px);
                math::bigint::bigint_copy(@Y, py);
                math::bigint::bigint_copy(@Z, pz);

                // Standard Jacobian doubling for a = -3 curve (P-256)
                // Reference: NIST SP 800-186, Appendix D, or
                //   https://hyperelliptic.org/EFD/g1p/auto-shortw-jacobian-3.html#doubling-dbl-2001-b
                //
                // delta = Z^2
                // gamma = Y^2
                // beta  = X * gamma
                // alpha = 3 * (X - delta) * (X + delta)   [uses a=-3]
                // X3    = alpha^2 - 8*beta
                // Z3    = (Y + Z)^2 - gamma - delta
                // Y3    = alpha * (4*beta - X3) - 8*gamma^2
                //
                // t1 = delta = Z^2
                p256_fp_sq(@t1, @Z);
                // t2 = gamma = Y^2
                p256_fp_sq(@t2, @Y);
                // t3 = beta = X * gamma
                p256_fp_mul(@t3, @X, @t2);
                // t4 = X - delta
                p256_fp_sub(@t4, @X, @t1);
                // t5 = X + delta
                p256_fp_add(@t5, @X, @t1);
                // t4 = (X - delta)(X + delta)
                p256_fp_mul(@t4, @t4, @t5);
                // t4 = alpha = 3 * (X - delta)(X + delta)
                math::bigint::bigint_from_uint(@three, 3);
                p256_fp_mul(@t4, @three, @t4);
                // rz = Z3 = (Y + Z)^2 - gamma - delta
                p256_fp_add(@t5, @Y, @Z);
                p256_fp_sq(@t5, @t5);
                p256_fp_sub(@t5, @t5, @t2);
                p256_fp_sub(rz, @t5, @t1);
                // t5 = 8 * beta
                math::bigint::bigint_from_uint(@two, 8);
                p256_fp_mul(@t5, @t3, @two);
                // rx = X3 = alpha^2 - 8*beta
                p256_fp_sq(@t1, @t4);
                p256_fp_sub(rx, @t1, @t5);
                // t3 = 4*beta - X3
                math::bigint::bigint_from_uint(@two, 4);
                p256_fp_mul(@t3, @t3, @two);
                p256_fp_sub(@t3, @t3, rx);
                // t2 = 8 * gamma^2
                p256_fp_sq(@t2, @t2);
                math::bigint::bigint_from_uint(@two, 8);
                p256_fp_mul(@t2, @t2, @two);
                // ry = Y3 = alpha * (4*beta - X3) - 8*gamma^2
                p256_fp_mul(@t3, @t4, @t3);
                p256_fp_sub(ry, @t3, @t2);
                return;
            };

            // Point add in Jacobian coordinates (P + Q, both may be the point at infinity).
            // Uses the standard Jacobian mixed / unified add formula.
            def p256_point_add(BigInt* rx, BigInt* ry, BigInt* rz,
                               BigInt* px, BigInt* py, BigInt* pz,
                               BigInt* qx, BigInt* qy, BigInt* qz) -> void
            {
                // Copy all inputs to locals first to handle in-place calls
                BigInt PX, PY, PZ, QX, QY, QZ;
                BigInt u1, u2, s1, s2, h, r, h2, h3, u1h2, tmp, two;
                BigInt dbl_t1, dbl_t2, dbl_t3, dbl_t4, dbl_three, dbl_two, dbl_t5;

                // Handle infinity inputs
                if (math::bigint::bigint_is_zero(pz))
                {
                    math::bigint::bigint_copy(rx, qx);
                    math::bigint::bigint_copy(ry, qy);
                    math::bigint::bigint_copy(rz, qz);
                    return;
                };
                if (math::bigint::bigint_is_zero(qz))
                {
                    math::bigint::bigint_copy(rx, px);
                    math::bigint::bigint_copy(ry, py);
                    math::bigint::bigint_copy(rz, pz);
                    return;
                };

                math::bigint::bigint_copy(@PX, px);
                math::bigint::bigint_copy(@PY, py);
                math::bigint::bigint_copy(@PZ, pz);
                math::bigint::bigint_copy(@QX, qx);
                math::bigint::bigint_copy(@QY, qy);
                math::bigint::bigint_copy(@QZ, qz);

                math::bigint::bigint_from_uint(@two, 2);

                // u1 = px * qz²
                p256_fp_sq(@tmp, @QZ);
                p256_fp_mul(@u1, @PX, @tmp);
                // u2 = qx * pz²
                p256_fp_sq(@tmp, @PZ);
                p256_fp_mul(@u2, @QX, @tmp);
                // s1 = py * qz³
                p256_fp_sq(@tmp, @QZ);
                p256_fp_mul(@s1, @tmp, @QZ);
                p256_fp_mul(@s1, @PY, @s1);
                // s2 = qy * pz³
                p256_fp_sq(@tmp, @PZ);
                p256_fp_mul(@s2, @tmp, @PZ);
                p256_fp_mul(@s2, @QY, @s2);
                // h = u2 - u1
                p256_fp_sub(@h, @u2, @u1);
                // r = s2 - s1
                p256_fp_sub(@r, @s2, @s1);

                // If h = 0: either equal points (double inline) or P = -Q (return infinity)
                if (math::bigint::bigint_is_zero(@h))
                {
                    if (math::bigint::bigint_is_zero(@r))
                    {
                        // P = Q: inline double (same formula as p256_point_dbl)
                        // dbl_t1=delta, dbl_t2=gamma, dbl_t3=beta, dbl_t4=alpha
                        p256_fp_sq(@dbl_t1, @PZ);
                        p256_fp_sq(@dbl_t2, @PY);
                        p256_fp_mul(@dbl_t3, @PX, @dbl_t2);
                        p256_fp_sub(@dbl_t4, @PX, @dbl_t1);
                        p256_fp_add(@dbl_t5, @PX, @dbl_t1);
                        p256_fp_mul(@dbl_t4, @dbl_t4, @dbl_t5);
                        math::bigint::bigint_from_uint(@dbl_three, 3);
                        p256_fp_mul(@dbl_t4, @dbl_three, @dbl_t4);
                        p256_fp_add(@dbl_t5, @PY, @PZ);
                        p256_fp_sq(@dbl_t5, @dbl_t5);
                        p256_fp_sub(@dbl_t5, @dbl_t5, @dbl_t2);
                        p256_fp_sub(rz, @dbl_t5, @dbl_t1);
                        math::bigint::bigint_from_uint(@dbl_two, 8);
                        p256_fp_mul(@dbl_t5, @dbl_t3, @dbl_two);
                        p256_fp_sq(@dbl_t1, @dbl_t4);
                        p256_fp_sub(rx, @dbl_t1, @dbl_t5);
                        math::bigint::bigint_from_uint(@dbl_two, 4);
                        p256_fp_mul(@dbl_t3, @dbl_t3, @dbl_two);
                        p256_fp_sub(@dbl_t3, @dbl_t3, rx);
                        p256_fp_sq(@dbl_t2, @dbl_t2);
                        math::bigint::bigint_from_uint(@dbl_two, 8);
                        p256_fp_mul(@dbl_t2, @dbl_t2, @dbl_two);
                        p256_fp_mul(@dbl_t3, @dbl_t4, @dbl_t3);
                        p256_fp_sub(ry, @dbl_t3, @dbl_t2);
                    }
                    else
                    {
                        // P = -Q: return infinity
                        math::bigint::bigint_zero(rx);
                        math::bigint::bigint_zero(ry);
                        math::bigint::bigint_zero(rz);
                    };
                    return;
                };

                // h2 = h²,  h3 = h³
                p256_fp_sq(@h2, @h);
                p256_fp_mul(@h3, @h2, @h);
                // u1h2 = u1 * h²
                p256_fp_mul(@u1h2, @u1, @h2);

                // rz = pz * qz * h
                p256_fp_mul(@tmp, pz, qz);
                p256_fp_mul(rz, @tmp, @h);

                // rx = r² - h³ - 2*u1h2
                p256_fp_sq(@tmp, @r);
                p256_fp_sub(rx, @tmp, @h3);
                p256_fp_mul(@tmp, @u1h2, @two);
                p256_fp_sub(rx, rx, @tmp);

                // ry = r*(u1h2 - rx) - s1*h3
                p256_fp_sub(@tmp, @u1h2, rx);
                p256_fp_mul(ry, @r, @tmp);
                p256_fp_mul(@tmp, @s1, @h3);
                p256_fp_sub(ry, ry, @tmp);
                return;
            };

            // Scalar multiplication: R = k * P  (double-and-add, left-to-right)
            // Result returned in affine coordinates (rx, ry); returns false if result
            // is the point at infinity.
            def ecdsa_p256_point_mul(BigInt* rx, BigInt* ry,
                                     BigInt* k,
                                     BigInt* px, BigInt* py) -> bool
            {
                BigInt qx, qy, qz, tx, ty, tz, one, zinv, zinv2, zinv3;
                uint i, j;
                uint word, bit;
                uint* kd;

                math::bigint::bigint_zero(@qx);
                math::bigint::bigint_zero(@qy);
                math::bigint::bigint_zero(@qz);   // infinity

                // tx/ty/tz = input point in Jacobian (Z = 1)
                math::bigint::bigint_copy(@tx, px);
                math::bigint::bigint_copy(@ty, py);
                math::bigint::bigint_one(@tz);

                kd = @k.digits[0];

                // Iterate from MSB of k down to LSB
                i = k.length;
                while (i > 0)
                {
                    i--;
                    word = kd[i];
                    j = 32;
                    while (j > 0)
                    {
                        j--;
                        bit = (word >> j) & 1;

                        // Always double
                        p256_point_dbl(@qx, @qy, @qz, @qx, @qy, @qz);

                        // Conditionally add
                        if (bit != 0)
                        {
                            p256_point_add(@qx, @qy, @qz,
                                           @qx, @qy, @qz,
                                           @tx, @ty, @tz);
                        };
                    };
                };

                // Check for infinity
                if (math::bigint::bigint_is_zero(@qz))
                {
                    math::bigint::bigint_zero(rx);
                    math::bigint::bigint_zero(ry);
                    return false;
                };

                // Convert Jacobian -> affine: x = X*Z^(-2), y = Y*Z^(-3)
                p256_fp_inv(@zinv, @qz);
                p256_fp_sq(@zinv2, @zinv);
                p256_fp_mul(@zinv3, @zinv2, @zinv);
                p256_fp_mul(rx, @qx, @zinv2);
                p256_fp_mul(ry, @qy, @zinv3);
                return true;
            };

            // ---- Public key derivation ----

            // Compute public key Q = d*G from 32-byte big-endian private key.
            // Writes 32-byte big-endian qx and qy.
            def ecdsa_p256_pubkey(byte* qx32, byte* qy32, byte* privkey32) -> bool
            {
                BigInt d, gx, gy, rx, ry;
                uint* gxd, gyd, pgx, pgy;
                uint i;

                ecdsa_p256_load_scalar(@d, privkey32);

                // Load generator directly from little-endian limb arrays
                gxd = @gx.digits[0];
                gyd = @gy.digits[0];
                pgx = @P256_GX[0];
                pgy = @P256_GY[0];
                for (i = 0; i < 8; i++) { gxd[i] = pgx[i]; };
                for (i = 0; i < 8; i++) { gyd[i] = pgy[i]; };
                gx.length = 8; gx.negative = false;
                gy.length = 8; gy.negative = false;
                math::bigint::bigint_normalize(@gx);
                math::bigint::bigint_normalize(@gy);

                if (!ecdsa_p256_point_mul(@rx, @ry, @d, @gx, @gy))
                {
                    return false;
                };

                ecdsa_p256_store_scalar(qx32, @rx);
                ecdsa_p256_store_scalar(qy32, @ry);
                return true;
            };

            // ---- Sign ----

            // Sign a 32-byte hash with a 32-byte big-endian private key and nonce k.
            // nonce32 must be a secret, uniformly random value in [1, n-1].
            // Writes 32-byte big-endian r and s.
            // Returns false if signing fails (r or s is zero — resample nonce).
            def ecdsa_p256_sign(byte* sig_r32, byte* sig_s32,
                                byte* privkey32,
                                byte* hash32,
                                byte* nonce32) -> bool
            {
                BigInt k, d, z, n, gx, gy, rx, ry;
                BigInt r, s, kinv, tmp;
                uint* gxd, gyd, pgx, pgy;
                uint i;

                ecdsa_p256_load_scalar(@k, nonce32);
                ecdsa_p256_load_scalar(@d, privkey32);
                ecdsa_p256_load_scalar(@z, hash32);
                p256_set_n(@n);

                // Load generator
                gxd = @gx.digits[0];
                gyd = @gy.digits[0];
                pgx = @P256_GX[0];
                pgy = @P256_GY[0];
                for (i = 0; i < 8; i++) { gxd[i] = pgx[i]; };
                for (i = 0; i < 8; i++) { gyd[i] = pgy[i]; };
                gx.length = 8; gx.negative = false;
                gy.length = 8; gy.negative = false;
                math::bigint::bigint_normalize(@gx);
                math::bigint::bigint_normalize(@gy);

                // (rx, ry) = k * G
                if (!ecdsa_p256_point_mul(@rx, @ry, @k, @gx, @gy))
                {
                    return false;
                };

                // r = rx mod n
                math::bigint::bigint_mod(@r, @rx, @n);
                if (math::bigint::bigint_is_zero(@r))
                {
                    return false;
                };

                // s = k^(-1) * (z + r*d) mod n
                if (!math::bigint::bigint_modinv(@kinv, @k, @n))
                {
                    return false;
                };

                math::bigint::bigint_mul(@tmp, @r, @d);
                math::bigint::bigint_mod(@tmp, @tmp, @n);
                math::bigint::bigint_add(@tmp, @z, @tmp);
                math::bigint::bigint_mod(@tmp, @tmp, @n);
                math::bigint::bigint_mul(@s, @kinv, @tmp);
                math::bigint::bigint_mod(@s, @s, @n);

                if (math::bigint::bigint_is_zero(@s))
                {
                    return false;
                };

                ecdsa_p256_store_scalar(sig_r32, @r);
                ecdsa_p256_store_scalar(sig_s32, @s);
                return true;
            };

            // ---- Verify ----

            // Verify an ECDSA-P256 signature.
            // pubx32, puby32 : 32-byte big-endian affine public key coordinates.
            // sig_r32, sig_s32 : 32-byte big-endian signature components.
            // hash32 : 32-byte message hash.
            // Returns true if the signature is valid.
            def ecdsa_p256_verify(byte* sig_r32, byte* sig_s32,
                                  byte* pubx32,  byte* puby32,
                                  byte* hash32) -> bool
            {
                BigInt r, s, z, n, qx, qy, gx, gy;
                BigInt sinv, u1, u2;
                BigInt r1x, r1y, r2x, r2y, rx, ry;
                BigInt one, ax, ay, az, bx, by, bz, outx, outy, outz, zinv, zinv2;
                uint* gxd, gyd, pgx, pgy;
                uint i;

                ecdsa_p256_load_scalar(@r, sig_r32);
                ecdsa_p256_load_scalar(@s, sig_s32);
                ecdsa_p256_load_scalar(@z, hash32);
                ecdsa_p256_load_scalar(@qx, pubx32);
                ecdsa_p256_load_scalar(@qy, puby32);
                p256_set_n(@n);

                // Reject r or s outside [1, n-1]
                if (math::bigint::bigint_is_zero(@r)) { return false; };
                if (math::bigint::bigint_is_zero(@s)) { return false; };
                if (math::bigint::bigint_cmp(@r, @n) >= 0) { return false; };
                if (math::bigint::bigint_cmp(@s, @n) >= 0) { return false; };

                // sinv = s^(-1) mod n
                if (!math::bigint::bigint_modinv(@sinv, @s, @n))
                {
                    return false;
                };

                // u1 = z * sinv mod n
                math::bigint::bigint_mul(@u1, @z, @sinv);
                math::bigint::bigint_mod(@u1, @u1, @n);

                // u2 = r * sinv mod n
                math::bigint::bigint_mul(@u2, @r, @sinv);
                math::bigint::bigint_mod(@u2, @u2, @n);

                // Load generator
                gxd = @gx.digits[0];
                gyd = @gy.digits[0];
                pgx = @P256_GX[0];
                pgy = @P256_GY[0];
                for (i = 0; i < 8; i++) { gxd[i] = pgx[i]; };
                for (i = 0; i < 8; i++) { gyd[i] = pgy[i]; };
                gx.length = 8; gx.negative = false;
                gy.length = 8; gy.negative = false;
                math::bigint::bigint_normalize(@gx);
                math::bigint::bigint_normalize(@gy);

                // R1 = u1 * G,  R2 = u2 * Q
                if (!ecdsa_p256_point_mul(@r1x, @r1y, @u1, @gx, @gy)) { return false; };
                if (!ecdsa_p256_point_mul(@r2x, @r2y, @u2, @qx, @qy)) { return false; };

                // R = R1 + R2  (affine add via Jacobian with Z=1)
                math::bigint::bigint_one(@one);
                math::bigint::bigint_copy(@ax, @r1x);
                math::bigint::bigint_copy(@ay, @r1y);
                math::bigint::bigint_one(@az);
                math::bigint::bigint_copy(@bx, @r2x);
                math::bigint::bigint_copy(@by, @r2y);
                math::bigint::bigint_one(@bz);
                p256_point_add(@outx, @outy, @outz,
                               @ax, @ay, @az,
                               @bx, @by, @bz);

                if (math::bigint::bigint_is_zero(@outz)) { return false; };

                // Convert to affine
                p256_fp_inv(@zinv, @outz);
                p256_fp_sq(@zinv2, @zinv);
                p256_fp_mul(@rx, @outx, @zinv2);

                // rx mod n == r?
                math::bigint::bigint_mod(@rx, @rx, @n);
                return (math::bigint::bigint_cmp(@rx, @r) == 0);
            };

            // ---- DER encoding / decoding ----

            // Encode (r, s) as a DER SEQUENCE { INTEGER r, INTEGER s }.
            // der_out must be at least 72 bytes.
            // der_len receives the actual encoded length.
            def ecdsa_p256_encode_der(byte* der_out, int* der_len, byte* r32, byte* s32) -> void
            {
                // Each 32-byte scalar may need a leading 0x00 pad if high bit is set.
                byte[33] rbuf, sbuf;
                int rlen, slen, total, i;

                // Copy r, inserting leading zero if MSB is set
                rlen = 32;
                if ((r32[0] & (byte)0x80) != (byte)0)
                {
                    rbuf[0] = (byte)0;
                    for (i = 0; i < 32; i++) { rbuf[i + 1] = r32[i]; };
                    rlen = 33;
                }
                else
                {
                    for (i = 0; i < 32; i++) { rbuf[i] = r32[i]; };
                };

                // Copy s, inserting leading zero if MSB is set
                slen = 32;
                if ((s32[0] & (byte)0x80) != (byte)0)
                {
                    sbuf[0] = (byte)0;
                    for (i = 0; i < 32; i++) { sbuf[i + 1] = s32[i]; };
                    slen = 33;
                }
                else
                {
                    for (i = 0; i < 32; i++) { sbuf[i] = s32[i]; };
                };

                // SEQUENCE { INTEGER(rbuf[0..rlen-1]), INTEGER(sbuf[0..slen-1]) }
                total = 2 + rlen + 2 + slen;
                int pos;
                der_out[pos] = (byte)0x30;         // SEQUENCE tag
                pos = 1;
                der_out[pos] = (byte)total;
                pos = 2;
                der_out[pos] = (byte)0x02;         // INTEGER tag
                pos = 3;
                der_out[pos] = (byte)rlen;
                pos = 4;
                for (i = 0; i < rlen; i++) { der_out[pos] = rbuf[i]; pos = pos + 1; };
                der_out[pos] = (byte)0x02;         // INTEGER tag
                pos = pos + 1;
                der_out[pos] = (byte)slen;
                pos = pos + 1;
                for (i = 0; i < slen; i++) { der_out[pos] = sbuf[i]; pos = pos + 1; };

                *der_len = 2 + total;
                return;
            };

            // Decode a DER-encoded signature into raw 32-byte big-endian r and s.
            // Returns false if the encoding is malformed.
            def ecdsa_p256_decode_der(byte* r32, byte* s32, byte* der_in, int der_len) -> bool
            {
                int pos, seq_len, tag, ilen, pad, i;

                if (der_len < 8) { return false; };

                // SEQUENCE tag
                if (der_in[pos] != (byte)0x30) { return false; };
                pos = 1;
                seq_len = (int)der_in[pos];
                pos = 2;
                if (seq_len + 2 != der_len) { return false; };

                // First INTEGER (r)
                if (der_in[pos] != (byte)0x02) { return false; };
                pos = pos + 1;
                ilen = (int)der_in[pos];
                pos = pos + 1;
                if (ilen < 1 | ilen > 33) { return false; };

                // Strip optional leading zero pad
                pad = 0;
                if (ilen == 33)
                {
                    if (der_in[pos] != (byte)0) { return false; };
                    pad = 1;
                    ilen = 32;
                    pos = pos + 1;
                };

                // Zero-fill r32 then copy (right-aligned if fewer than 32 bytes)
                for (i = 0; i < 32; i++) { r32[i] = (byte)0; };
                int roff = 32 - ilen;
                for (i = 0; i < ilen; i++) { r32[roff + i] = der_in[pos + i]; };
                pos = pos + ilen;

                // Second INTEGER (s)
                if (der_in[pos] != (byte)0x02) { return false; };
                pos = pos + 1;
                ilen = (int)der_in[pos];
                pos = pos + 1;
                if (ilen < 1 | ilen > 33) { return false; };

                pad = 0;
                if (ilen == 33)
                {
                    if (der_in[pos] != (byte)0) { return false; };
                    pad = 1;
                    ilen = 32;
                    pos = pos + 1;
                };

                for (i = 0; i < 32; i++) { s32[i] = (byte)0; };
                int soff = 32 - ilen;
                for (i = 0; i < ilen; i++) { s32[soff + i] = der_in[pos + i]; };

                return true;
            };

        }; // ECDSA
    };
};


#endif;