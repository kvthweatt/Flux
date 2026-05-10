// Author: Karac V. Thweatt

// reduuid.fx - UUID Generation Library
// Supports UUID versions 1, 4, and 7

#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#ifndef FLUX_STANDARD_UUID
#def FLUX_STANDARD_UUID 1;

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_RANDOM
#import "random.fx";
#endif;

struct UUID
{
    byte[16] bytes;
};

namespace standard
{
    namespace uuid
    {
        // ============ UUID FORMATTING ============
        
        // Convert UUID to string format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        def uuid_to_string(UUID* uuid, byte* buffer) -> void
        {
            byte[16] hex_chars = [
                '0', '1', '2', '3', '4', '5', '6', '7',
                '8', '9', 'a', 'b', 'c', 'd', 'e', 'f'
            ];
            
            int pos;
            byte b;
            
            // Format: 8-4-4-4-12
            for (int i = 0; i < 16; i++)
            {
                b = uuid.bytes[i];
                buffer[pos] = hex_chars[(b >> 4) & 0x0F];
                pos++;
                buffer[pos] = hex_chars[b & 0x0F];
                pos++;
                
                // Add hyphens at appropriate positions
                if (i == 3 | i == 5 | i == 7 | i == 9)
                {
                    buffer[pos] = (byte)'-';
                    pos++;
                };
            };
            
            buffer[pos] = (byte)0;
        };
        
        // Convert UUID to uppercase string
        def uuid_to_string_upper(UUID* uuid, byte* buffer) -> void
        {
            byte[16] hex_chars = [
                '0', '1', '2', '3', '4', '5', '6', '7',
                '8', '9', 'A', 'B', 'C', 'D', 'E', 'F'
            ];
            
            int pos;
            byte b;
            
            // Format: 8-4-4-4-12
            for (int i = 0; i < 16; i++)
            {
                b = uuid.bytes[i];
                buffer[pos] = hex_chars[(b >> 4) & 0x0F];
                pos++;
                buffer[pos] = hex_chars[b & 0x0F];
                pos++;
                
                // Add hyphens at appropriate positions
                if (i == 3 | i == 5 | i == 7 | i == 9)
                {
                    buffer[pos] = (byte)'-';
                    pos++;
                };
            };
            
            buffer[pos] = (byte)0;
        };
        
        // Convert UUID to compact hex string (no hyphens)
        def uuid_to_hex(UUID* uuid, byte* buffer) -> void
        {
            byte[16] hex_chars = [
                '0', '1', '2', '3', '4', '5', '6', '7',
                '8', '9', 'a', 'b', 'c', 'd', 'e', 'f'
            ];
            
            int pos;
            byte b;
            
            for (int i = 0; i < 16; i++)
            {
                b = uuid.bytes[i];
                buffer[pos] = hex_chars[(b >> 4) & 0x0F];
                pos++;
                buffer[pos] = hex_chars[b & 0x0F];
                pos++;
            };
            
            buffer[pos] = (byte)0;
        };
        
        // ============ UUID VERSION 4 (Random) ============
        // Most common UUID type - fully random
        
        def uuid_v4(UUID* uuid, PCG32* rng) -> void
        {
            // Generate 16 random bytes
            standard::random::random_bytes(rng, uuid.bytes, (u64)16);
            
            // Set version to 4 (bits 12-15 of time_hi_and_version)
            uuid.bytes[6] = (uuid.bytes[6] & (byte)0x0F) | (byte)0x40;
            
            // Set variant to RFC 4122 (bits 6-7 of clock_seq_hi_and_reserved)
            uuid.bytes[8] = (uuid.bytes[8] & (byte)0x3F) | (byte)0x80;
        };
        
        // Generate UUID v4 with global RNG
        def uuid_v4_quick(UUID* uuid) -> void
        {
            // Ensure global RNG is initialized
            if (!global_rng_initialized)
            {
                standard::random::init_random();
            };
            
            uuid_v4(uuid, @global_rng);
        };
        
        // ============ UUID VERSION 7 (Time-ordered) ============
        // Newest UUID version - sortable by creation time
        
        def uuid_v7(UUID* uuid, PCG32* rng) -> void
        {
            // Get current timestamp from RDTSC
            u64 timestamp = standard::random::get_rdtsc();
            
            // Use top 48 bits for timestamp (milliseconds would be better but we use RDTSC)
            // In a real implementation, you'd use actual Unix time in milliseconds
            
            // Timestamp (48 bits) - bytes 0-5
            uuid.bytes[0] = (byte)((timestamp >> 40) & 0xFF);
            uuid.bytes[1] = (byte)((timestamp >> 32) & 0xFF);
            uuid.bytes[2] = (byte)((timestamp >> 24) & 0xFF);
            uuid.bytes[3] = (byte)((timestamp >> 16) & 0xFF);
            uuid.bytes[4] = (byte)((timestamp >> 8) & 0xFF);
            uuid.bytes[5] = (byte)(timestamp & 0xFF);
            
            // Version and random bytes (bytes 6-7)
            u32 rand1 = standard::random::pcg32_next(rng);
            uuid.bytes[6] = (byte)((rand1 >> 8) & 0x0F) | (byte)0x70;  // Version 7
            uuid.bytes[7] = (byte)(rand1 & 0xFF);
            
            // Variant and random bytes (bytes 8-15)
            u32 rand2 = standard::random::pcg32_next(rng);
            uuid.bytes[8] = (byte)((rand2 >> 24) & 0x3F) | (byte)0x80;  // Variant
            uuid.bytes[9] = (byte)((rand2 >> 16) & 0xFF);
            uuid.bytes[10] = (byte)((rand2 >> 8) & 0xFF);
            uuid.bytes[11] = (byte)(rand2 & 0xFF);
            
            // More random bytes
            u32 rand3 = standard::random::pcg32_next(rng);
            uuid.bytes[12] = (byte)((rand3 >> 24) & 0xFF);
            uuid.bytes[13] = (byte)((rand3 >> 16) & 0xFF);
            uuid.bytes[14] = (byte)((rand3 >> 8) & 0xFF);
            uuid.bytes[15] = (byte)(rand3 & 0xFF);
        };
        
        // Generate UUID v7 with global RNG
        def uuid_v7_quick(UUID* uuid) -> void
        {
            if (!global_rng_initialized)
            {
                standard::random::init_random();
            };
            
            uuid_v7(uuid, @global_rng);
        };
        
        // ============ UUID VERSION 1 (Time-based with MAC) ============
        // Classic time-based UUID (less secure, includes MAC address)
        
        def uuid_v1(UUID* uuid, PCG32* rng) -> void
        {
            // Get timestamp
            u64 timestamp = standard::random::get_rdtsc();
            
            // UUID v1 uses 60-bit timestamp + 100-nanosecond intervals since Oct 15, 1582
            // We'll use RDTSC as a proxy for timestamp
            
            // time_low (4 bytes)
            uuid.bytes[0] = (byte)((timestamp >> 24) & 0xFF);
            uuid.bytes[1] = (byte)((timestamp >> 16) & 0xFF);
            uuid.bytes[2] = (byte)((timestamp >> 8) & 0xFF);
            uuid.bytes[3] = (byte)(timestamp & 0xFF);
            
            // time_mid (2 bytes)
            uuid.bytes[4] = (byte)((timestamp >> 40) & 0xFF);
            uuid.bytes[5] = (byte)((timestamp >> 32) & 0xFF);
            
            // time_hi_and_version (2 bytes)
            uuid.bytes[6] = (byte)(((timestamp >> 56) & 0x0F) | 0x10);  // Version 1
            uuid.bytes[7] = (byte)((timestamp >> 48) & 0xFF);
            
            // clock_seq_hi_and_reserved (1 byte)
            u32 clock_seq = standard::random::pcg32_next(rng);
            uuid.bytes[8] = (byte)(((clock_seq >> 8) & 0x3F) | 0x80);  // Variant
            
            // clock_seq_low (1 byte)
            uuid.bytes[9] = (byte)(clock_seq & 0xFF);
            
            // node (6 bytes) - normally MAC address, we use random
            u32 node1 = standard::random::pcg32_next(rng);
            u32 node2 = standard::random::pcg32_next(rng);
            uuid.bytes[10] = (byte)((node1 >> 24) & 0xFF);
            uuid.bytes[11] = (byte)((node1 >> 16) & 0xFF);
            uuid.bytes[12] = (byte)((node1 >> 8) & 0xFF);
            uuid.bytes[13] = (byte)(node1 & 0xFF);
            uuid.bytes[14] = (byte)((node2 >> 24) & 0xFF);
            uuid.bytes[15] = (byte)((node2 >> 16) & 0xFF);
        };
        
        // Generate UUID v1 with global RNG
        def uuid_v1_quick(UUID* uuid) -> void
        {
            if (!global_rng_initialized)
            {
                standard::random::init_random();
            };
            
            uuid_v1(uuid, @global_rng);
        };
        
        // ============ NIL UUID ============
        // All zeros UUID (00000000-0000-0000-0000-000000000000)
        
        def uuid_nil(UUID* uuid) -> void
        {
            for (int i = 0; i < 16; i++)
            {
                uuid.bytes[i] = (byte)0;
            };
        };
        
        // ============ UUID COMPARISON ============
        
        // Compare two UUIDs for equality
        def uuid_equals(UUID* a, UUID* b) -> bool
        {
            for (int i = 0; i < 16; i++)
            {
                if (a.bytes[i] != b.bytes[i])
                {
                    return false;
                };
            };
            return true;
        };
        
        // Check if UUID is nil
        def uuid_is_nil(UUID* uuid) -> bool
        {
            for (int i = 0; i < 16; i++)
            {
                if (uuid.bytes[i] != (byte)0)
                {
                    return false;
                };
            };
            return true;
        };
        
        // Get UUID version
        def uuid_version(UUID* uuid) -> int
        {
            return (int)((uuid.bytes[6] >> 4) & 0x0F);
        };
        
        // ============ UUID UTILITIES ============
        
        // Copy UUID
        def uuid_copy(UUID* dest, UUID* src) -> void
        {
            for (int i = 0; i < 16; i++)
            {
                dest.bytes[i] = src.bytes[i];
            };
        };
        
        // Generate multiple UUIDs at once
        def uuid_generate_batch_v4(UUID* uuids, int count, PCG32* rng) -> void
        {
            for (int i = 0; i < count; i++)
            {
                uuid_v4(@uuids[i], rng);
            };
        };
        
        // ============ NAMESPACE UUID (for v3/v5) ============
        // Predefined namespace UUIDs from RFC 4122
        
        // DNS namespace: 6ba7b810-9dad-11d1-80b4-00c04fd430c8
        global const UUID UUID_NAMESPACE_DNS = {
            bytes = [
                0x6B, 0xA7, 0xB8, 0x10,
                0x9D, 0xAD,
                0x11, 0xD1,
                0x80, 0xB4,
                0x00, 0xC0, 0x4F, 0xD4, 0x30, 0xC8
            ]
        };
        
        // URL namespace: 6ba7b811-9dad-11d1-80b4-00c04fd430c8
        global const UUID UUID_NAMESPACE_URL = {
            bytes = [
                0x6B, 0xA7, 0xB8, 0x11,
                0x9D, 0xAD,
                0x11, 0xD1,
                0x80, 0xB4,
                0x00, 0xC0, 0x4F, 0xD4, 0x30, 0xC8
            ]
        };
        
        // OID namespace: 6ba7b812-9dad-11d1-80b4-00c04fd430c8
        global const UUID UUID_NAMESPACE_OID = {
            bytes = [
                0x6B, 0xA7, 0xB8, 0x12,
                0x9D, 0xAD,
                0x11, 0xD1,
                0x80, 0xB4,
                0x00, 0xC0, 0x4F, 0xD4, 0x30, 0xC8
            ]
        };
        
        // X.500 namespace: 6ba7b814-9dad-11d1-80b4-00c04fd430c8
        global const UUID UUID_NAMESPACE_X500 = {
            bytes = [
                0x6B, 0xA7, 0xB8, 0x14,
                0x9D, 0xAD,
                0x11, 0xD1,
                0x80, 0xB4,
                0x00, 0xC0, 0x4F, 0xD4, 0x30, 0xC8
            ]
        };
    };
};

using standard::uuid;

#endif;
