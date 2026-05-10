// hotpatch_protocol.fx
//
// Shared protocol definitions for the hotpatch server/client demo.
//
// Wire format (all fields little-endian):
//
//   struct PatchPacket
//   {
//       u32  magic;        // 0x48505458 "HPTX" — sanity check
//       u32  patch_size;   // number of bytes in the payload
//       u64  target_rva;   // RVA from client image base to patch site
//                          // (0 = use target_addr directly, for demo)
//       byte[] payload;    // raw machine code bytes, patch_size long
//       byte[32] sig;      // HMAC-SHA256 over payload bytes
//   };
//
// The client reads the header first (16 bytes), allocates a page,
// receives exactly patch_size bytes into it, then receives the 32-byte
// HMAC-SHA256 signature and verifies it before installing the detour.
//
// Signing uses HMAC-SHA256 with a pre-shared 32-byte key known to both
// server and client.  Any tampered or replayed payload will fail the
// MAC check and be rejected before a single byte is executed.

#ifndef HOTPATCH_PROTOCOL
#def HOTPATCH_PROTOCOL 1;

#import "cryptography.fx";

using standard::crypto::hashing::SHA256;

// Magic bytes: "HPTX"
const uint PATCH_MAGIC = 0x48505458,
// Response codes sent server -> client after delivery
           PATCH_ACK   = 0x00000001,   // patch received and applied
           PATCH_NACK  = 0x000000FF;   // something went wrong

// Fixed header size: magic(4) + patch_size(4) + target_rva(8) = 16 bytes
const int PATCH_HEADER_SIZE = 16,

// Maximum payload we'll accept (1 page)
          PATCH_MAX_SIZE    = 4096,

// HMAC-SHA256 signature size in bytes
          HMAC_SIG_SIZE     = 32;

// Hotpatch server port
const u16 HOTPATCH_PORT     = 9900;

// Pre-shared HMAC key — both server and client must agree on this value.
// In production this would be loaded from a secure key store or derived
// via a key-exchange protocol.  For the demo it is embedded at compile time.
const byte[32] HMAC_KEY = [
    0x4B, 0x65, 0x79, 0x46, 0x6C, 0x75, 0x78, 0x48,
    0x6F, 0x74, 0x70, 0x61, 0x74, 0x63, 0x68, 0x53,
    0x69, 0x67, 0x6E, 0x69, 0x6E, 0x67, 0x4B, 0x65,
    0x79, 0x21, 0x40, 0x23, 0x24, 0x25, 0x5E, 0x26
];


struct PatchHeader
{
    u32 magic,
        patch_size;
    u64 target_rva;
};

// Compute HMAC-SHA256(key, xdata) into out[32].
//
// HMAC construction:
//   ipad = key XOR 0x36 repeated
//   opad = key XOR 0x5C repeated
//   HMAC = SHA256(opad || SHA256(ipad || xdata))
def hmac_sha256(byte* key, int key_len, byte* xdata, int xdata_len, byte* out) -> void
{
    // Build padded inner and outer keys (64-byte SHA-256 block size)
    byte[64] ipad_key, opad_key;
    byte[32] inner_hash;
    int i;
    SHA256_CTX inner_ctx, outer_ctx;
    byte k;

    // Zero-pad key into the 64-byte blocks, XOR with ipad/opad constants
    for (i < 64; i++)
    {
        k = (i < key_len) ? key[i] : (byte)0;
        ipad_key[i] = k ^^ (byte)0x36;
        opad_key[i] = k ^^ (byte)0x5C;
    };

    // inner = SHA256(ipad_key || xdata)
    sha256_init(@inner_ctx);
    sha256_update(@inner_ctx, @ipad_key[0], (u64)64);
    sha256_update(@inner_ctx, xdata, (u64)xdata_len);
    sha256_final(@inner_ctx, @inner_hash[0]);

    // out = SHA256(opad_key || inner)
    sha256_init(@outer_ctx);
    sha256_update(@outer_ctx, @opad_key[0], (u64)64);
    sha256_update(@outer_ctx, @inner_hash[0], (u64)32);
    sha256_final(@outer_ctx, out);
};

// Constant-time comparison of two 32-byte buffers.
// Returns true if they are identical, false otherwise.
// Constant-time prevents timing side-channels on the signature check.
def sig_equal(byte* a, byte* b) -> bool
{
    byte diff;
    
    for (int i = 0; i < 32; i++)
    {
        diff = diff | (a[i] ^^ b[i]);
    };
    return diff == 0;
};

#endif;