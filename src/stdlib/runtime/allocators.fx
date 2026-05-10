// Author: Karac V. Thweatt

// allocators.fx - Flux Custom Memory Allocators
//
//
// Default Standard Heap Allocator:
    // Segregated free lists by size class for O(1) small alloc/free.
    // Bump pointer fast path carves from slab frontier.
    // Large allocations (>4096) get a dedicated OS slab, released on ffree.
    // Block metadata lives in a separate table slab (open-addressed hash map
    // keyed by user pointer). The table slab is itself an entry in the table.
    // No inline headers user data blocks are completely pure.
    // No zeroing (Flux zero-inits at language level).
    // No coalescing (fragments are reusable as-is per Flux memory model).
    // Slabs acquired directly from OS: 4MB -> 8MB -> 16MB -> 32MB -> 64MB cap.
    // Zero OS memory consumed until first fmalloc call.
//
//

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_ALLOCATORS
#def FLUX_STANDARD_ALLOCATORS 1;

// OS primitives 

#ifdef __WINDOWS__
extern
{
    def !!
        VirtualAlloc(u64, size_t, u32, u32) -> u64,
        VirtualFree(u64, size_t, u32)       -> bool;
};
#endif;

#ifdef __LINUX__
extern
{
    def !!
        mmap(u64, size_t, int, int, int, i64) -> u64,
        munmap(u64, size_t)                   -> int;
};
#endif;

#ifdef __MACOS__
extern
{
    def !!
        mmap(u64, size_t, int, int, int, i64) -> u64,
        munmap(u64, size_t)                   -> int;
};
#endif;

// Size classes
//
//  Index:  0    1    2    3    4    5     6     7     8
//  Bytes: 16   32   64  128  256  512  1024  2048  4096
//  >4096 = large, gets its own dedicated OS slab.

// Block kinds
//
//  BLOCK_SMALL  (0): size field holds size class index (0-8), block is live
//  BLOCK_LARGE  (1): size field holds exact byte count requested
//  BLOCK_TABLE  (2): this entry describes a table slab itself
//  BLOCK_BINNED (3): small block on the free list; entry kept so slab pointer
//                    is authoritative on reuse — no slab scan needed

// Block table entry
//
//  key  : user pointer (null = empty slot)
//  size : size class index for small; byte count for large/table
//  kind : 0=small 1=large 2=table
//  slab : pointer to the OS slab that owns this block (for large/table)

struct BlockEntry
{
    u64    key;
    size_t size;
    u64    kind;
    u64    slab;
};

// Slab descriptor

struct Slab
{
    u64    base;
    size_t capacity,frontier,used;
    Slab*  next;
};

// Free list node (lives in the free block's own memory)

struct FreeNode
{
    FreeNode* next;
};

// Ring allocator result (returned by stdring::allocate)
//
//  ptr     : pointer to the allocated region (never null unless size > capacity)
//  wrapped : true if the write pointer wrapped around and overwrote old data

struct RingAllocResult
{
    u64*  ptr;
    bool  wrapped;
};

#def NP_BLOCKENTRY (BlockEntry*)0; // Null block entry pointer
#def NP_FREENODE   (FreeNode*)0;   // Null free node pointer
#def NP_SLAB       (Slab*)0;       // Null slab pointer

#def SLAB_HEADER_SIZE 40;
#def SLAB_ENTRY_SIZE  32;

namespace standard
{
    namespace memory
    {
        namespace allocators
        {
            namespace stdheap
            {
                // Globals
                Slab*       g_slab_head      = NP_SLAB;
                size_t      g_next_slab_size = 4194304;   // 4 MB
                size_t      g_slab_size_cap  = 67108864;  // 64 MB
                size_t      g_large_used     = 0;         // live large-block count

                // Block table: open-addressed hash map, stored in its own OS slab
                BlockEntry* g_table          = NP_BLOCKENTRY;
                size_t      g_table_cap      = 0;   // entry capacity
                size_t      g_table_count    = 0;   // live entries
                size_t      g_table_slab_cap = 0;   // byte size of table OS slab

                // Segregated free list bins (indices 0-8)
                FreeNode*[9] g_bins;

                // OS helpers

                def heap_os_alloc(size_t bytes) -> u64
                {
                    #ifdef __WINDOWS__
                    return VirtualAlloc(0, bytes, 0x3000, 0x04);
                    #endif;
                    #ifdef __LINUX__
                    u64* p = mmap(0, bytes, 3, 0x22, -1, 0);
                    switch ((size_t)p == (size_t)U64MAXVAL) { case (1) { return (u64)0; } default {}; };
                    return (u64)p;
                    #endif;
                    #ifdef __MACOS__
                    u64* p = mmap(0, bytes, 3, 0x1002, -1, 0);
                    switch ((size_t)p == (size_t)U64MAXVAL) { case (1) { return (u64)0; } default {}; };
                    return (u64)p;
                    #endif;
                };

                def heap_os_free(u64 ptr, size_t bytes) -> void
                {
                    #ifdef __WINDOWS__
                    VirtualFree(ptr, 0, (u32)0x8000);
                    #endif;
                    #ifdef __LINUX__
                    munmap(ptr, bytes);
                    #endif;
                    #ifdef __MACOS__
                    munmap(ptr, bytes);
                    #endif;
                };

                def size_class(size_t size) -> size_t
                {
                    // Fast reject for large blocks (>4096)
                    switch (size > 4096) { case (1) { return (size_t)9; } default {}; };

                    // Classes map to power-of-two ceilings: 16,32,64,128,256,512,1024,2048,4096
                    // which are 1<<4 through 1<<12.
                    // Round size up to the nearest class ceiling, then find the position
                    // of its highest set bit via successive halving (no inline asm).
                    // bit_pos(16)=4 -> class 0, bit_pos(4096)=12 -> class 8.

                    // Round size up to the smallest class ceiling >= size.
                    // Equivalent to: s = size <= 16 ? 16 : next_pow2_ceil(size) clamped to 4096.
                    // We compute via: s-1, then fill all lower bits, then +1.
                    size_t s = size - 1;
                    s |= (s >> 1);
                    s |= (s >> 2);
                    s |= (s >> 4);
                    s |= (s >> 8);
                    s += 1;
                    // s is now the next power of two >= size (or size itself if already pow2).
                    // Clamp to 16 minimum.
                    switch (s < 16) { case (1) { s = 16; } default {}; };

                    // Find bit position of s (which is a power of two) via right-shifts.
                    // We know s is in [16..4096] = [1<<4..1<<12].
                    size_t bit, tmp = s;
                    switch (tmp >> 8  != 0) { case (1) { bit += 8;  tmp >>= 8;  } default {}; };
                    switch (tmp >> 4  != 0) { case (1) { bit += 4;  tmp >>= 4;  } default {}; };
                    switch (tmp >> 2  != 0) { case (1) { bit += 2;  tmp >>= 2;  } default {}; };
                    switch (tmp >> 1  != 0) { case (1) { bit += 1;              } default {}; };

                    // bit is the index of the highest set bit (4..12).
                    // class = bit - 4  maps [4..12] -> [0..8].
                    return bit - 4;
                };

                def class_block_size(size_t cls) -> size_t
                {
                    switch (cls)
                    {
                        case (0) { return 16;   }
                        case (1) { return 32;   }
                        case (2) { return 64;   }
                        case (3) { return 128;  }
                        case (4) { return 256;  }
                        case (5) { return 512;  }
                        case (6) { return 1024; }
                        case (7) { return 2048; }
                        case (8) { return 4096; }
                        default  { return 4096; };
                    };
                    return 0;
                };

                def bin_pop(size_t cls) -> FreeNode*
                {
                    switch (cls > 8) { case (1) { return NP_FREENODE; } default {}; };
                    FreeNode* n = g_bins[cls];
                    switch (n != NP_FREENODE) { case (1) { g_bins[cls] = n.next; } default {}; };
                    return n;
                };

                def bin_push(size_t cls, FreeNode* node) -> void
                {
                    switch (cls > 8) { case (1) { return; } default {}; };
                    node.next = g_bins[cls];
                    g_bins[cls] = node;
                };

                // Block table

                // Hash a pointer to a table slot index
                def table_hash(u64 ptr, size_t cap) -> size_t
                {
                    // All pointers are 16-byte aligned so bits 0-3 are always zero.
                    // Shift them out first, then mix with a 64-bit Fibonacci multiplier
                    // for strong avalanche in 3 ops instead of 5.
                    size_t h = (size_t)ptr >> (size_t)4;
                    h = h * 0x9E3779B97F4A7C15;
                    h = h `^^ (h >> (size_t)32);
                    return h & (cap - (size_t)1);
                };

                // Insert into a raw table buffer (used by both insert and grow)
                def table_raw_insert(BlockEntry* tbl, size_t cap,
                                     u64 key, size_t size, u64 kind, u64 slab) -> void
                {
                    size_t idx = table_hash(key, cap);
                    while (tbl[idx].key != 0)
                    {
                        idx = (idx + 1) & (cap - 1);
                    };
                    tbl[idx].key  = key;
                    tbl[idx].size = size;
                    tbl[idx].kind = kind;
                    tbl[idx].slab = slab;
                };

                // Grow the table slab when load factor exceeds 0.5
                def table_grow() -> bool
                {
                    size_t new_cap  = g_table_cap * 2;
                    size_t new_bytes = new_cap * SLAB_ENTRY_SIZE;

                    u64 raw = heap_os_alloc(new_bytes);
                    switch (raw == 0)
                    {
                        case (1) { return false; }
                        default  {};
                    };

                    // Zero the new table (table entries must start null)
                    byte* p = (byte*)raw;
                    size_t i, j;
                    while (i < new_bytes)
                    {
                        p[i] = '\0';
                        i++;
                    };

                    BlockEntry* new_tbl = (BlockEntry*)raw;

                    g_table_count = 0;

                    // Rehash all existing entries into the new table
                    while (j < g_table_cap)
                    {
                        switch (g_table[j].key != 0)
                        {
                            case (1)
                            {
                                table_raw_insert(new_tbl, new_cap,
                                                 g_table[j].key,
                                                 g_table[j].size,
                                                 g_table[j].kind,
                                                 g_table[j].slab);
                                g_table_count++;
                            }
                            default {};
                        };
                        j++;
                    };

                    // Remove the stale BLOCK_TABLE entry for the old slab that was
                    // rehashed into new_tbl, then release the old slab.
                    u64 old_tbl_addr = (u64)g_table;
                    size_t rm_idx = table_hash(old_tbl_addr, new_cap),
                           rm_hole, rm_next,
                           rm_natural;
                    bool rm_found, rm_shift, rm_in_range;
                    while (new_tbl[rm_idx].key != 0)
                    {
                        switch (new_tbl[rm_idx].key == old_tbl_addr)
                        {
                            case (1)
                            {
                                new_tbl[rm_idx].key = 0;
                                g_table_count--;
                                // Backward-shift deletion to close the gap
                                rm_hole = rm_idx;
                                rm_next = (rm_idx + 1) & (new_cap - 1);
                                while (new_tbl[rm_next].key != 0)
                                {
                                    rm_natural = table_hash(new_tbl[rm_next].key, new_cap);
                                    switch (rm_hole < rm_next)
                                    {
                                        case (1)
                                        {
                                            switch (rm_natural > rm_hole)
                                            {
                                                case (1)
                                                {
                                                    switch (rm_natural <= rm_next)
                                                    {
                                                        case (1) { rm_in_range = true; }
                                                        default  { rm_in_range = false; };
                                                    };
                                                }
                                                default { rm_in_range = false; };
                                            };
                                            switch (rm_in_range)
                                            {
                                                case (1) { rm_shift = false; }
                                                default  { rm_shift = true; };
                                            };
                                        }
                                        default
                                        {
                                            switch (rm_natural > rm_hole)
                                            {
                                                case (1) { rm_in_range = true; }
                                                default
                                                {
                                                    switch (rm_natural <= rm_next)
                                                    {
                                                        case (1) { rm_in_range = true; }
                                                        default  { rm_in_range = false; };
                                                    };
                                                };
                                            };
                                            switch (rm_in_range)
                                            {
                                                case (1) { rm_shift = false; }
                                                default  { rm_shift = true; };
                                            };
                                        };
                                    };
                                    switch (rm_shift)
                                    {
                                        case (1)
                                        {
                                            new_tbl[rm_hole].key  = new_tbl[rm_next].key;
                                            new_tbl[rm_hole].size = new_tbl[rm_next].size;
                                            new_tbl[rm_hole].kind = new_tbl[rm_next].kind;
                                            new_tbl[rm_hole].slab = new_tbl[rm_next].slab;
                                            new_tbl[rm_next].key  = 0;
                                            rm_hole = rm_next;
                                        }
                                        default {};
                                    };
                                    rm_next = (rm_next + 1) & (new_cap - 1);
                                };
                                rm_found = true;
                            }
                            default {};
                        };
                        switch (rm_found) { case (1) { break; } default {}; };
                        rm_idx = (rm_idx + 1) & (new_cap - 1);
                    };

                    heap_os_free((u64)g_table, g_table_slab_cap);

                    g_table          = new_tbl;
                    g_table_cap      = new_cap;
                    g_table_slab_cap = new_bytes;

                    // Record this table slab as an entry in itself
                    table_raw_insert(g_table,
                                     g_table_cap,
                                     raw,
                                     new_bytes,
                                     2,
                                     raw);
                    g_table_count++;

                    return true;
                };

                // Initialise the table on first use
                def table_init() -> bool
                {
                    size_t initial_cap   = 1024;
                    size_t initial_bytes = initial_cap * SLAB_ENTRY_SIZE;

                    u64 raw = heap_os_alloc(initial_bytes);
                    switch (raw == 0)
                    {
                        case (1) { return false; }
                        default  {};
                    };

                    // Zero the table
                    byte* p = (byte*)raw;
                    size_t i;
                    while (i < initial_bytes)
                    {
                        p[i] = 0;
                        i++;
                    };

                    g_table          = (BlockEntry*)raw;
                    g_table_cap      = initial_cap;
                    g_table_count    = 0;
                    g_table_slab_cap = initial_bytes;

                    // Record this table slab as an entry in itself
                    table_raw_insert(g_table,
                                     g_table_cap,
                                     raw,
                                     initial_bytes,
                                     2,
                                     raw);
                    g_table_count++;

                    return true;
                };

                def table_insert(u64 key, size_t size, u64 kind, u64 slab) -> bool
                {
                    if (g_table == NP_BLOCKENTRY)
                    {
                        if (!table_init()) { return false; };
                    };

                    // Grow if load > 50%
                    if (g_table_count * 2 >= g_table_cap)
                    {
                            switch (!table_grow()) { case (1) { return false; } default {}; };
                    };

                    table_raw_insert(g_table, g_table_cap, key, size, kind, slab);
                    g_table_count++;
                    return true;
                };

                def table_find(u64 key) -> BlockEntry*
                {
                    switch (g_table == NP_BLOCKENTRY) { case (1) { return NP_BLOCKENTRY; } default {}; };

                    size_t idx = table_hash(key, g_table_cap);
                    while (g_table[idx].key != 0)
                    {
                        switch (g_table[idx].key == key)
                        {
                            case (1) { return @g_table[idx]; }
                            default  {};
                        };
                        idx = (idx + 1) & (g_table_cap - 1);
                    };
                    return NP_BLOCKENTRY;
                };

                def table_remove(u64 key) -> void
                {
                    switch (g_table == NP_BLOCKENTRY) { case (1) { return; } default {}; };

                    size_t idx = table_hash(key, g_table_cap),
                           hole, next, natural;
                    bool should_shift, in_range;
                    while (g_table[idx].key != 0)
                    {
                        switch (g_table[idx].key == key)
                        {
                            case (1)
                            {
                                // Tombstone: clear key, leave rest for Robin Hood probe chain
                                g_table[idx].key = 0;
                                g_table_count--;

                                // Backward-shift deletion: slide each following entry one slot
                                // back if its natural home is at or before the vacant slot,
                                // stopping when we reach an empty slot or wrap all the way around.
                                hole = idx;
                                next = (idx + 1) & (g_table_cap - 1);
                                while (g_table[next].key != 0)
                                {
                                    natural = table_hash(g_table[next].key, g_table_cap);
                                    // Determine whether this entry belongs at or before the hole.
                                    // We need to account for wrap-around: entry should shift back
                                    // if the hole is between its natural slot and its current slot.
                                    // Shift this entry back to fill the hole if its natural
                                    // home is NOT strictly between hole (exclusive) and next
                                    // (inclusive) in the forward/non-wrapping direction.
                                    // In other words: do NOT shift only when hole < natural <= next.
                                    // When the probe run wraps (next < hole), the non-shift region
                                    // is hole < natural (and natural did not wrap past 0) -- i.e.
                                    // natural > hole && natural <= next is impossible when next < hole
                                    // so instead: no-shift when natural > hole && next >= natural is
                                    // replaced by: no-shift when !(natural <= hole || natural > next).
                                    switch (hole < next)
                                    {
                                        case (1)
                                        {
                                            // Normal (non-wrapping) run: shift unless hole < natural <= next
                                            switch (natural > hole)
                                            {
                                                case (1)
                                                {
                                                    switch (natural <= next)
                                                    {
                                                        case (1) { in_range = true; }
                                                        default  { in_range = false; };
                                                    };
                                                }
                                                default { in_range = false; };
                                            };
                                            switch (in_range)
                                            {
                                                case (1) { should_shift = false; }
                                                default  { should_shift = true; };
                                            };
                                        }
                                        default
                                        {
                                            // Wrapping run (next < hole): shift unless natural is in
                                            // (hole, cap) union [0, next] -- i.e. natural > hole OR natural <= next
                                            switch (natural > hole)
                                            {
                                                case (1) { in_range = true; }
                                                default
                                                {
                                                    switch (natural <= next)
                                                    {
                                                        case (1) { in_range = true; }
                                                        default  { in_range = false; };
                                                    };
                                                };
                                            };
                                            switch (in_range)
                                            {
                                                case (1) { should_shift = false; }
                                                default  { should_shift = true; };
                                            };
                                        };
                                    };
                                    switch (should_shift)
                                    {
                                        case (1)
                                        {
                                            g_table[hole].key  = g_table[next].key;
                                            g_table[hole].size = g_table[next].size;
                                            g_table[hole].kind = g_table[next].kind;
                                            g_table[hole].slab = g_table[next].slab;
                                            g_table[next].key  = 0;
                                            hole = next;
                                        }
                                        default {};
                                    };
                                    next = (next + 1) & (g_table_cap - 1);
                                };
                                return;
                            }
                            default {};
                        };
                        idx = (idx + 1) & (g_table_cap - 1);
                    };
                };

                def heap_new_slab(size_t min_capacity) -> Slab*
                {
                    size_t sz = g_next_slab_size;
                    size_t header_size = (SLAB_HEADER_SIZE + 15) & `!15;
                    switch (min_capacity + header_size > sz)
                    {
                        case (1) { sz = min_capacity + header_size; }
                        default  {};
                    };

                    u64 raw = heap_os_alloc(sz);
                    switch (raw == 0) { case (1) { return NP_SLAB; } default {}; };

                    Slab* slab    = (Slab*)raw;
                    slab.base     = raw;
                    slab.capacity = sz;
                    slab.frontier = header_size;
                    slab.used     = 0;
                    slab.next     = g_slab_head;
                    g_slab_head   = slab;

                    // Advance exponential growth
                    size_t next = g_next_slab_size * 2;
                    switch (next > g_slab_size_cap)
                    {
                        case (1) { next = g_slab_size_cap; }
                        default  {};
                    };
                    g_next_slab_size = next;

                    return slab;
                };

                def bump_alloc(size_t bytes) -> u64
                {
                    Slab* slab = g_slab_head;
                    bool b = slab == NP_SLAB;
                    if (b) { return 0; };
                    bool ret = ((slab != NP_SLAB) & (slab.frontier + bytes <= slab.capacity));
                    u64 ptr       = (u64)((byte*)slab.base + slab.frontier);
                    slab.frontier = slab.frontier + bytes;
                    return ptr * ret;
                };

                def fmalloc_fast(size_t cls) -> u64
                {
                    FreeNode* head = g_bins[cls];
                    if (head == NP_FREENODE) { return 0; };
                    g_bins[cls] = head.next;
                    return (u64)head;
                };

                // Public API

                def fmalloc(size_t size) -> u64
                {
                    if (size is void) { return size; };

                    // Fast path: bypass size_class() for the three most common sizes.
                    // Each branch resolves cls and the bin head as constants, so no
                    // switch dispatch overhead inside fmalloc_fast.
                    if (size <= 32)
                    {
                        if (size > 16)   // exactly class 1 (17..32 bytes)
                        {
                            u64 fast = fmalloc_fast(1);
                            if (fast != void) { return fast; };
                            // Bin empty: fall through to bump path with cls already known.
                            size_t cls = 1;
                            u64 ptr = bump_alloc(32);
                            if (ptr is void)
                            {
                                    if (heap_new_slab(32) is NP_SLAB) { return 0; };
                                    ptr = bump_alloc(32);
                                    if (ptr is void) { return 0; };
                            };

                            if (!table_insert(ptr, cls, 0, (u64)g_slab_head))
                            {
                                return 0;
                            };
                            g_slab_head.used++;
                            return ptr;
                        };
                    };

                    if (size <= 64)
                    {
                        if (size > 32)   // exactly class 2 (33..64 bytes)
                        {
                            u64 fast = fmalloc_fast(2);
                            if (fast != void) { return fast; };
                            size_t cls = 2;
                            u64 ptr = bump_alloc(64);
                            if (ptr is void)
                            {
                                if (heap_new_slab(64) is NP_SLAB) { return 0; };
                                ptr = bump_alloc(64);
                                if (ptr is void) { return 0; };
                            };

                            if (!table_insert(ptr, cls, 0, (u64)g_slab_head))
                            {
                                return 0;
                            };
                            g_slab_head.used++;
                            return ptr;
                        };
                    };

                    if (size <= 128)
                    {
                        if (size > 64)   // exactly class 3 (65..128 bytes)
                        {
                            u64 fast = fmalloc_fast(3);
                            if (fast != 0) { return fast; };
                            size_t cls = 3;
                            u64 ptr = bump_alloc(128);
                            if (ptr is void)
                            {
                                    if (heap_new_slab(128) == NP_SLAB) { return 0; };
                                    ptr = bump_alloc(128);
                                    if (ptr is void) { return 0; };
                            };
                            if (!table_insert(ptr, cls, 0, (u64)g_slab_head))
                            {
                                return 0;
                            };
                            g_slab_head.used++;
                            return ptr;
                        };
                    };

                    // Slow path: all other sizes go through the full size_class() dispatch.
                    size_t cls = size_class(size);

                    switch (cls == 9)
                    {
                        case (1)
                        {
                            // Large: dedicated OS slab, no bump involvement
                            u64 raw = heap_os_alloc(size);
                            switch (raw == 0) { case (1) { return 0; } default {}; };

                            // slab field stores OS allocation size so ffree can release correctly
                            switch (!table_insert(raw, size, 1, size))
                            {
                                case (1)
                                {
                                    heap_os_free(raw, size);
                                    return 0;
                                }
                                default {};
                            };

                            g_large_used++;
                            return raw;
                        }
                        default {};
                    };

                    // Small: try free list bin first — return directly, no table_find needed.
                    FreeNode* node = bin_pop(cls);
                    switch (node != NP_FREENODE)
                    {
                        case (1) { return (u64)node; }
                        default  {};
                    };

                    // Bump allocate from current slab
                    size_t block = class_block_size(cls);
                    u64 ptr = bump_alloc(block);
                    switch (ptr is void)
                    {
                        case (1)
                        {
                            switch (heap_new_slab(block) == NP_SLAB) { case (1) { return 0; } default {}; };
                            ptr = bump_alloc(block);
                            switch (ptr is void) { case (1) { return 0; } default {}; };
                        }
                        default {};
                    };

                    switch (!table_insert(ptr, cls, 0, (u64)g_slab_head))
                    {
                        case (1) { return 0; }
                        default  {};
                    };

                    g_slab_head.used++;
                    return ptr;
                };

                def fmalloc(ulong size) -> u64
                {
                    return fmalloc((size_t)size);
                };

                def ffree(u64 ptr) -> void
                {
                    switch (ptr is void) { case (1) { return; } default {}; };

                    BlockEntry* entry = table_find(ptr);
                    switch (entry == NP_BLOCKENTRY) { case (1) { return; } default {}; };

                    u64    kind = entry.kind;
                    size_t size = entry.size;
                    u64    slab = entry.slab;

                    switch (kind == 1)
                    {
                        case (1)
                        {
                            // Large block: remove from table, release OS memory.
                            table_remove(ptr);
                            g_large_used--;
                            heap_os_free(ptr, (size_t)slab);
                            return;
                        }
                        default {};
                    };

                    // Small block: mark BLOCK_BINNED and return to bin.
                    // Table entry stays alive so coalesce_heap can find the owning slab.
                    entry.kind = (u64)3;
                    bin_push(size, (FreeNode*)ptr);
                };

                def ffree(byte* ptr) -> void
                {
                    ffree((u64)ptr);
                };

                def frealloc(u64 ptr, size_t new_size) -> u64
                {
                    switch (ptr is void) { case (1) { return fmalloc(new_size); } default {}; };
                    switch (new_size == 0) { case (1) { ffree(ptr); return 0; } default {}; };

                    BlockEntry* entry = table_find(ptr);
                    switch (entry == NP_BLOCKENTRY) { case (1) { return 0; } default {}; };

                    u64    kind    = entry.kind,
                           new_ptr;
                    size_t old_size = entry.size,
                           copy_size,
                           i;

                    byte* src, dst;

                    bool same, shrink, has_reuse;

                    FreeNode* reuse;
                    Slab* old_owner, new_owner, ws;

                    switch (kind == 1)
                    {
                        case (1)
                        {
                            // Large block: same size, no move needed
                            same = old_size == new_size;
                            switch (same)
                            {
                                case (1) { return ptr; }
                                default  {};
                            };
                            // Shrinking or growing: fall through to move path below.
                            // Shrinking releases excess OS memory; growing gets more.
                        }
                        default
                        {
                            size_t old_cls = old_size;
                            size_t new_cls = size_class(new_size);

                            // Same class: fits as-is, no move
                            same = new_cls == old_cls;
                            switch (same) { case (1) { return ptr; } default {}; };

                            // Shrinking to a smaller class: data fits in current block, no move needed
                            shrink = new_cls < old_cls;
                            switch (shrink) { case (1) { return ptr; } default {}; };

                            // Growing: check if the target bin has a free block before bumping
                            copy_size = class_block_size(old_cls);
                            switch (new_size < copy_size) { case (1) { copy_size = new_size; } default {}; };

                            reuse = bin_pop(new_cls);
                            has_reuse = reuse != NP_FREENODE;
                            switch (has_reuse)
                            {
                                case (1)
                                {
                                    new_ptr = (u64)reuse;
                                    BlockEntry* reuse_entry = table_find(new_ptr);
                                    switch (reuse_entry != NP_BLOCKENTRY)
                                    {
                                        case (1)
                                        {
                                            new_owner = (Slab*)reuse_entry.slab;
                                            reuse_entry.size = new_cls;
                                            reuse_entry.kind = 0;  // BLOCK_SMALL: mark live
                                            switch (new_owner != NP_SLAB)
                                            {
                                                case (1) { new_owner.used++; }
                                                default  {};
                                            };
                                        }
                                        default {};
                                    };
                                    src = (byte*)ptr;
                                    dst = (byte*)new_ptr;
                                    while (i < copy_size) { dst[i] = src[i]; i++; };
                                    old_owner = (Slab*)entry.slab;
                                    switch (old_owner != NP_SLAB)
                                    {
                                        case (1) { switch (old_owner.used > 0) { case (1) { old_owner.used--; } default {}; }; }
                                        default  {};
                                    };
                                    entry.kind = (u64)3;   // BLOCK_BINNED
                                    bin_push(old_cls, (FreeNode*)ptr);
                                    return new_ptr;
                                }
                                default {};
                            };

                            // No free block in bin, bump allocate, copy, free old
                            new_ptr = fmalloc(new_size);
                            switch (new_ptr is void) { case (1) { return 0; } default {}; };
                            src = (byte*)ptr;
                            dst = (byte*)new_ptr;
                            i = 0;
                            while (i < copy_size) { dst[i] = src[i]; i++; };
                            ffree(ptr);
                            return new_ptr;
                        };
                    };

                    // Large block growing or shrinking to small: must move
                    new_ptr = fmalloc(new_size);
                    switch (new_ptr is void) { case (1) { return 0; } default {}; };
                    src = (byte*)ptr;
                    dst = (byte*)new_ptr;
                    copy_size = old_size;
                    switch (new_size < old_size) { case (1) { copy_size = new_size; } default {}; };
                    i = 0;
                    while (i < copy_size) { dst[i] = src[i]; i++; };
                    ffree(ptr);
                    return new_ptr;
                };

                // Walk all small-block slabs and release any whose used counter
                // has reached zero back to the OS.  Free-list nodes belonging to
                // released slabs are removed from their bins before the slab is
                // freed so dangling pointers are never left in the bins.
                def coalesce_heap() -> void
                {
                    size_t bin_idx;

                    u64 addr;

                    Slab* slab = g_slab_head,
                          prev, next;

                    FreeNode* node, node_next, keep_head, keep_tail,
                              reinsert, reinsert_next;

                    while (slab != NP_SLAB)
                    {
                        next = slab.next;

                        switch (slab.used == 0)
                        {
                            case (1)
                            {
                                // Purge every free-list node that lives inside this slab
                                // from all nine bins.
                                while (bin_idx <= 8)
                                {
                                    node = bin_pop(bin_idx);
                                    keep_head = NP_FREENODE;
                                    keep_tail = NP_FREENODE;

                                    while (node != NP_FREENODE)
                                    {
                                        addr = (u64)node;
                                        node_next = node.next;

                                        switch (addr >= slab.base & addr < slab.base + (u64)slab.capacity)
                                        {
                                            // Node is inside the slab being released: discard it.
                                            case (1) {}
                                            default
                                            {
                                                // Node belongs to a different slab: keep it.
                                                node.next = NP_FREENODE;
                                                switch (keep_tail == NP_FREENODE)
                                                {
                                                    case (1)
                                                    {
                                                        keep_head = node;
                                                        keep_tail = node;
                                                    }
                                                    default
                                                    {
                                                        keep_tail.next = node;
                                                        keep_tail      = node;
                                                    };
                                                };
                                            };
                                        };

                                        node = node_next;
                                    };

                                    // Re-push survivors back into the bin in order.
                                    reinsert = keep_head;
                                    while (reinsert != NP_FREENODE)
                                    {
                                        reinsert_next = reinsert.next;
                                        bin_push(bin_idx, reinsert);
                                        reinsert = reinsert_next;
                                    };

                                    bin_idx++;
                                };

                                // Unlink the slab from the chain.
                                switch (prev == NP_SLAB)
                                {
                                    case (1) { g_slab_head = next; }
                                    default  { prev.next   = next; };
                                };

                                heap_os_free(slab.base, slab.capacity);
                            }
                            default
                            {
                                prev = slab;
                            };
                        };

                        slab = next;
                    };
                };

                // Returns a fragmentation estimate in the range [0.0, 1.0].
                // The value is the ratio of free (binned) small-block bytes plus
                // live large-block count to total tracked capacity.
                // 0.0 means no fragmentation, 1.0 means entirely fragmented.
                def check_fragmentation() -> float
                {
                    // Sum usable capacity and live bytes across all small slabs.
                    size_t total_capacity, total_used,
                           usable, committed,
                           all_used, used_bytes, free_bytes;

                    Slab* slab = g_slab_head;

                    while (slab != NP_SLAB)
                    {
                        // Usable capacity excludes the slab header.
                        usable = slab.capacity - SLAB_HEADER_SIZE;
                        total_capacity += usable;
                        // used counts live small blocks; free bytes = usable - used*avg_block
                        // We track used as a block count not byte count, so we use
                        // frontier as a proxy for committed bytes instead.
                        total_used += slab.used;
                        slab = slab.next;
                    };

                    switch (total_capacity == 0)
                    {
                        case (1)
                        {
                            // No slabs yet; include large blocks if any.
                            switch (g_large_used > 0)
                            {
                                case (1) { return 1.0; }
                                default  { return 0.0; };
                            };
                        }
                        default {};
                    };

                    // free_blocks = frontier bytes committed minus live blocks.
                    // Fragmentation rises as free blocks accumulate relative to
                    // total committed space.  Large blocks are live so they do
                    // not contribute free bytes but are added to used.
                    slab = g_slab_head;
                    while (slab != NP_SLAB)
                    {
                        committed += slab.frontier - SLAB_HEADER_SIZE;
                        slab = slab.next;
                    };

                    all_used = total_used + g_large_used;

                    switch (committed == 0)
                    {
                        case (1) { return 0.0; }
                        default  {};
                    };

                    // free_bytes = committed space that has been bumped but is
                    // currently sitting in a bin waiting to be reused.
                    // We approximate: each used block occupies at least 16 bytes
                    // (smallest class), free = committed - used*16 clamped to 0.
                    used_bytes = all_used * 16;
                    switch (used_bytes > committed)
                    {
                        case (1) { used_bytes = committed; }
                        default  {};
                    };
                    free_bytes = committed - used_bytes;

                    return float(free_bytes) / float(committed);
                };

            };

            namespace stdstack
            {
                // ===== STACK ALLOCATOR =====
                object StackAllocator
                {
                    byte* buffer;
                    size_t capacity, offset;
                    
                    def __init(size_t size) -> this
                    {
                        this.capacity = size;
                        this.offset = 0;
                        this.buffer = (byte*)stdheap::fmalloc(size);
                        return this;
                    };
                    
                    def __exit() -> void
                    {
                        switch (this.buffer != 0)
                        {
                            case (true)
                            {
                                stdheap::ffree((u64)this.buffer);
                            }
                            default {};
                        };
                    };

                    def __expr() -> u64
                    {
                        return (u64)@this.buffer;
                    };
                    
                    def allocate(size_t size) -> void_ptr
                    {
                        bool b = (this.offset + size) > this.capacity;
                        switch (b)
                        {
                            case (true)
                            {
                                return STDLIB_GVP;
                            }
                            default
                            {
                                u64* ptr = (void_ptr)(this.buffer + this.offset);
                                this.offset += size;
                                return ptr;
                            };
                        };
                        return STDLIB_GVP;
                    };
                    
                    def reset() -> void
                    {
                        this.offset = 0;
                    };
                    
                    def get_used() -> size_t
                    {
                        return this.offset;
                    };
                    
                    def get_available() -> size_t
                    {
                        return this.capacity - this.offset;
                    };
                    
                    def get_capacity() -> size_t
                    {
                        return this.capacity;
                    };
                };
            };

            namespace stdpool
            {
                // ===== POOL ALLOCATOR =====
                //
                // Fixed-size block pool backed by a single stdheap allocation.
                // All blocks are the same size (block_size), carved at init.
                // A free list threaded through the blocks themselves gives O(1)
                // alloc and free.
                // allocate() returns null when all blocks are in use.
                // Individual blocks are returned via deallocate(void_ptr ptr).
                // __exit() releases the backing buffer back to stdheap.

                object PoolAllocator
                {
                    byte*     buffer;
                    size_t    block_size, block_count;
                    FreeNode* free_head;

                    def __init(size_t bsize, size_t bcount) -> this
                    {
                        // Enforce a minimum block size large enough to hold a
                        // FreeNode pointer so the free list can live in-place.
                        size_t actual_bsize = bsize;
                        FreeNode* node;
                        switch (actual_bsize < 8)
                        {
                            case (1) { actual_bsize = 8; }
                            default  {};
                        };

                        this.block_size  = actual_bsize;
                        this.block_count = bcount;
                        this.buffer      = (byte*)stdheap::fmalloc(actual_bsize * bcount);
                        this.free_head   = NP_FREENODE;

                        // Build the free list by threading every block together.
                        switch (this.buffer != (byte*)0)
                        {
                            case (1)
                            {
                                size_t i = bcount;
                                while (i > 0)
                                {
                                    i--;
                                    node = (FreeNode*)(this.buffer + i * actual_bsize);
                                    node.next      = this.free_head;
                                    this.free_head = node;
                                };
                            }
                            default {};
                        };

                        return this;
                    };

                    def __exit() -> void
                    {
                        switch (this.buffer != (byte*)0)
                        {
                            case (1)
                            {
                                stdheap::ffree((u64)@this.buffer);
                            }
                            default {};
                        };
                    };

                    def __expr() -> u64
                    {
                        return (u64)@this.buffer;
                    };

                    // Returns a pointer to a free block, or null if the pool is
                    // exhausted.
                    def allocate() -> void_ptr
                    {
                        switch (this.free_head == NP_FREENODE)
                        {
                            case (1) { return (void_ptr)0; }
                            default  {};
                        };

                        FreeNode* node = this.free_head;
                        this.free_head = node.next;
                        return (void_ptr)node;
                    };

                    // Return a previously allocated block back to the pool.
                    // Passing a pointer not belonging to this pool is undefined
                    // behaviour.
                    def deallocate(void_ptr ptr) -> void
                    {
                        switch (ptr is void)
                        {
                            case (1) { return; }
                            default  {};
                        };

                        FreeNode* node = (FreeNode*)ptr;
                        node.next      = this.free_head;
                        this.free_head = node;
                    };

                    def get_block_size() -> size_t
                    {
                        return this.block_size;
                    };

                    def get_block_count() -> size_t
                    {
                        return this.block_count;
                    };

                    // Returns the number of blocks currently available.
                    def get_free_count() -> size_t
                    {
                        size_t    count;
                        FreeNode* node  = this.free_head;
                        while (node != NP_FREENODE)
                        {
                            count++;
                            node = node.next;
                        };
                        return count;
                    };
                };
            };

            namespace stdarena
            {
                // ===== ARENA ALLOCATOR =====
                //
                // Bump-pointer allocator over a linked chain of OS-backed chunks.
                // Designed to match the aggression of stdheap:
                //
                //   alloc  : aligned bump -- _align8 inlined, flat single-level
                //            switch, no per-alloc accounting write.
                //   free   : no-op -- individual frees are unsupported by design.
                //   reset  : walk chunk chain, reset all offsets to ARENA_HDR.
                //   destroy: walk chunk chain, stdheap::ffree each chunk base.
                //   mark   : snapshot current chunk + offset for cheap scope rewind.
                //   rewind : restore to a previously saved mark, bulk-freeing any
                //            chunks allocated after the mark.
                //
                // Chunk growth mirrors the heap slab schedule:
                //   default_chunk: 1 MB initial
                //   cap          : 64 MB per chunk maximum
                //   growth       : doubles each new chunk until cap
                //
                // All allocations are 8-byte aligned via (size + 7) & ~7, inlined.
                // No per-alloc accounting -- total_allocated removed entirely.
                // Zero OS memory consumed until first alloc call.
                // Backed entirely by stdheap::fmalloc / stdheap::ffree.

                // Chunk header -- lives at the base of each chunk allocation.
                // User data follows immediately after the header.

                struct ArenaChunk
                {
                    ArenaChunk* next;
                    size_t      capacity;
                    size_t      offset;
                };

                // sizeof(ArenaChunk) = 24 bytes; padded to 32 for alignment.
                #def ARENA_HDR (size_t)32;

                // Saved position -- used by arena_mark / arena_rewind.
                struct ArenaMark
                {
                    ArenaChunk* chunk;
                    size_t      offset;
                };

                // Top-level arena descriptor.
                // total_allocated removed -- no hot-path accounting write.
                struct Arena
                {
                    ArenaChunk* head;
                    size_t      next_chunk_size;
                    size_t      chunk_size_cap;
                };

                #def ARENA_DEFAULT_CHUNK  (size_t)1048576;
                #def ARENA_CHUNK_SIZE_CAP (size_t)67108864;

                // Allocate a new chunk of at least min_bytes usable space.
                // Cold path only -- called when the current chunk is full.
                def _new_chunk(Arena* a, size_t min_bytes) -> bool
                {
                    size_t      need, sz;
                    ArenaChunk* chunk;
                    u64         raw;
                    need = min_bytes + ARENA_HDR;
                    sz   = a.next_chunk_size;
                    switch (need > sz) { case (1) { sz = need; } default {}; };
                    raw = stdheap::fmalloc(sz);
                    switch (raw == 0) { case (1) { return false; } default {}; };
                    chunk          = (ArenaChunk*)raw;
                    chunk.next     = a.head;
                    chunk.capacity = sz;
                    chunk.offset   = ARENA_HDR;
                    a.head         = chunk;
                    sz = a.next_chunk_size * 2;
                    switch (sz > a.chunk_size_cap) { case (1) { sz = a.chunk_size_cap; } default {}; };
                    a.next_chunk_size = sz;
                    return true;
                };

                // Initialise an arena. No memory consumed until first alloc.
                def arena_init(Arena* a) -> void
                {
                    a.head            = (ArenaChunk*)0;
                    a.next_chunk_size = ARENA_DEFAULT_CHUNK;
                    a.chunk_size_cap  = ARENA_CHUNK_SIZE_CAP;
                };

                // Initialise with a custom first chunk size.
                def arena_init_sized(Arena* a, size_t first_chunk) -> void
                {
                    a.head            = (ArenaChunk*)0;
                    a.next_chunk_size = first_chunk;
                    a.chunk_size_cap  = ARENA_CHUNK_SIZE_CAP;
                };

                // Allocate sz bytes. Always 8-byte aligned. Returns null on OOM.
                // _align8 inlined. No tracking write.
                // Outer switch guards null head; inner switch is the bounds check.
                def alloc(Arena* a, size_t sz) -> void*
                {
                    size_t      aligned, new_offset;
                    ArenaChunk* c;
                    u64         ptr;
                    aligned = (sz + (size_t)7) & (`!7);
                    c       = a.head;
                    switch ((u64)c != 0)
                    {
                        case (1)
                        {
                            new_offset = c.offset + aligned;
                            switch (new_offset <= c.capacity)
                            {
                                case (1)
                                {
                                    ptr      = (u64)c + (u64)c.offset;
                                    c.offset = new_offset;
                                    return (void*)ptr;
                                }
                                default {};
                            };
                        }
                        default {};
                    };
                    switch (!_new_chunk(a, aligned)) { case (1) { return (void*)0; } default {}; };
                    c        = a.head;
                    ptr      = (u64)c + (u64)c.offset;
                    c.offset = c.offset + aligned;
                    return (void*)ptr;
                };

                // Allocate sz bytes, zero before returning.
                def alloc_zero(Arena* a, size_t sz) -> void*
                {
                    void*  p;
                    byte*  b;
                    size_t i;
                    p = alloc(a, sz);
                    switch ((u64)p == 0) { case (1) { return (void*)0; } default {}; };
                    b = (byte*)p;
                    while (i < sz) { b[i] = 0; i++; };
                    return p;
                };

                // Copy sz bytes from src into arena memory.
                def alloc_copy(Arena* a, void* src, size_t sz) -> void*
                {
                    void*  p;
                    byte*  d, s;
                    size_t i;
                    p = alloc(a, sz);
                    switch ((u64)p == 0) { case (1) { return (void*)0; } default {}; };
                    d = (byte*)p;
                    s = (byte*)src;
                    while (i < sz) { d[i] = s[i]; i++; };
                    return p;
                };

                // Copy a null-terminated string into the arena (including the null).
                def alloc_str(Arena* a, byte* src) -> byte*
                {
                    size_t n;
                    byte*  p;
                    while (src[n] != 0) { n++; };
                    n++;
                    p = (byte*)alloc(a, n);
                    switch ((u64)p == 0) { case (1) { return (byte*)0; } default {}; };
                    n = 0;
                    while (src[n] != 0) { p[n] = src[n]; n++; };
                    p[n] = 0;
                    return p;
                };

                // Save the current bump position.
                def arena_mark(Arena* a) -> ArenaMark
                {
                    ArenaMark   m;
                    ArenaChunk* h;
                    h        = a.head;
                    m.chunk  = h;
                    switch ((u64)h != 0)
                    {
                        case (1) { m.offset = h.offset; }
                        default  { m.offset = 0; };
                    };
                    return m;
                };

                // Rewind to a saved mark. Frees any chunks allocated after it.
                def arena_rewind(Arena* a, ArenaMark* m) -> void
                {
                    ArenaChunk* c, target, next;
                    target = m.chunk;
                    c      = a.head;
                    while ((u64)c != (u64)target & (u64)c != 0)
                    {
                        next = c.next;
                        stdheap::ffree((u64)c);
                        c = next;
                    };
                    a.head = target;
                    switch ((u64)target != 0) { case (1) { target.offset = m.offset; } default {}; };
                };

                // Reset all chunks to empty. Keeps OS memory for reuse.
                def arena_reset(Arena* a) -> void
                {
                    ArenaChunk* c;
                    c = a.head;
                    while ((u64)c != 0)
                    {
                        c.offset = ARENA_HDR;
                        c = c.next;
                    };
                };

                // Release all chunks back to stdheap. Arena is empty after this.
                def arena_destroy(Arena* a) -> void
                {
                    ArenaChunk* c, next;
                    c = a.head;
                    while ((u64)c != 0)
                    {
                        next = c.next;
                        stdheap::ffree((u64)c);
                        c = next;
                    };
                    a.head = (ArenaChunk*)0;
                };

                // Total bytes consumed across all live chunks (excluding headers).
                // Computes used as committed minus remaining free space in head chunk.
                def arena_used(Arena* a) -> size_t
                {
                    ArenaChunk* c;
                    size_t      total;
                    c     = a.head;
                    total = 0;
                    while ((u64)c != 0)
                    {
                        total = total + c.offset - ARENA_HDR;
                        c     = c.next;
                    };
                    return total;
                };

                // Total bytes committed across all live chunks (excluding headers).
                def arena_committed(Arena* a) -> size_t
                {
                    ArenaChunk* c;
                    size_t      total;
                    c     = a.head;
                    total = 0;
                    while ((u64)c != 0)
                    {
                        total = total + c.capacity - ARENA_HDR;
                        c     = c.next;
                    };
                    return total;
                };

            };

            namespace stdring
            {
                // ===== RING (CIRCULAR) ALLOCATOR =====
                //
                // Fixed-capacity FIFO bump allocator backed by a single stdheap
                // allocation.  The write pointer advances on each allocate() call
                // and wraps back to the start when it would exceed the capacity,
                // overwriting the oldest data.
                //
                // allocate() returns a RingAllocResult* (backed by a small
                // per-call descriptor stored in the ring buffer itself ahead of
                // the user data):
                //   ptr     - pointer to the usable region
                //   wrapped - true if the write pointer wrapped this call
                //
                // If size > capacity (request can never fit) both ptr and
                // wrapped carry null/false and the descriptor pointer itself is
                // null.
                //
                // __exit() releases the backing buffer back to stdheap.

                object RingAllocator
                {
                    byte*            buffer;
                    size_t           capacity, write_pos;
                    RingAllocResult* rallocresult;

                    def __init(size_t size) -> this
                    {
                        this.capacity     = size;
                        this.write_pos    = 0;
                        this.buffer       = (byte*)stdheap::fmalloc(size);
                        this.rallocresult = (RingAllocResult*)stdheap::fmalloc(16);
                        return this;
                    };

                    def __exit() -> void
                    {
                        switch (this.buffer != (byte*)0)
                        {
                            case (1)
                            {
                                stdheap::ffree((u64)@this.buffer);
                            }
                            default {};
                        };
                        switch (this.rallocresult != (RingAllocResult*)0)
                        {
                            case (1)
                            {
                                stdheap::ffree((u64)@this.rallocresult);
                            }
                            default {};
                        };
                    };

                    def __expr() -> u64
                    {
                        return (u64)@this.buffer;
                    };

                    // Allocate `size` bytes from the ring.
                    // Returns a pointer to the persistent rallocresult member
                    // describing the outcome.  The result is valid until the
                    // next call to allocate().
                    // Returns null if size > capacity (can never fit).
                    def allocate(size_t size) -> RingAllocResult*
                    {
                        // Request can never fit in the buffer at all.
                        switch (size > this.capacity)
                        {
                            case (1) { return (RingAllocResult*)0; }
                            default  {};
                        };

                        bool wrapped = false;

                        // Check if we need to wrap.
                        switch (this.write_pos + size > this.capacity)
                        {
                            case (1)
                            {
                                this.write_pos = 0;
                                wrapped        = true;
                            }
                            default {};
                        };

                        // The user region is carved directly from the buffer.
                        u64* user_ptr   = (void_ptr)(this.buffer + this.write_pos);
                        this.write_pos  += size;

                        this.rallocresult.ptr     = user_ptr;
                        this.rallocresult.wrapped = wrapped;

                        return this.rallocresult;
                    };

                    def get_capacity() -> size_t
                    {
                        return this.capacity;
                    };

                    def get_write_pos() -> size_t
                    {
                        return this.write_pos;
                    };

                    def reset() -> void
                    {
                        this.write_pos = 0;
                    };
                };
            };
        };
    };
};

#endif;