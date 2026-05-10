// Author: Karac V. Thweatt

// Flux Collections Library
// Provides dynamic, generic collection types for the reduced specification.

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_MEMORY
#import "memory.fx";
#endif;

#ifndef FLUX_STANDARD_COLLECTIONS
#def FLUX_STANDARD_COLLECTIONS 1;

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // Dynamic Array
        // A heap-allocated, dynamically resizing array of fixed-size elements.
        // Elements are stored as raw bytes; the caller is responsible for casting.
        // elem_size: size in bytes of each element, passed at construction time.
        // Capacity doubles when full (2x growth strategy).
        //
        // Usage example:
        //   Array arr((size_t)4);          // array of 4-byte (int) elements
        //   int x = 42;
        //   arr.push(@x);
        //   int* p = (int*)arr.get((size_t)0);
        //   int val = *p;
        // ============================================================================

        #def ARRAY_INITIAL_CAPACITY 8;

        trait BaseSTDArrayTraits
        {
            def _grow() -> bool,
                _ptr(size_t) -> byte*,
                len() -> size_t,
                push(void* src) -> bool,
                pop(void* dst) -> bool,
                get(size_t i) -> void*,
                set(size_t i, void* src) -> bool,
                insert(size_t i, void* src) -> bool,
                remove(size_t i) -> bool,
                clear() -> void,
                contains(void* src) -> bool;
        };

        BaseSTDArrayTraits
        object Array
        {
            void*  buf;
            size_t len,
                   capacity,
                   elem_size;

            // Construct an empty Array for elements of elem_size bytes.
            def __init(size_t elem_size) -> this
            {
                this.elem_size = elem_size;
                this.len       = 0;
                this.capacity  = (size_t)ARRAY_INITIAL_CAPACITY;
                this.buf       = malloc(this.capacity * elem_size);
                return this;
            };

            // Free the backing buffer.
            def __exit() -> void
            {
                if (this.buf != STDLIB_GVP)
                {
                    free(this.buf);
                    this.buf = STDLIB_GVP;
                };
                return;
            };

            def __expr() -> Array*
            {
                return this;
            };

            // ----------------------------------------------------------------
            // Internal: grow capacity by 2x. Returns false on alloc failure.
            // ----------------------------------------------------------------
            def _grow() -> bool
            {
                size_t new_cap = this.capacity * 2;
                void*  new_buf = realloc(this.buf, new_cap * this.elem_size);
                if (new_buf == STDLIB_GVP)
                {
                    return false;
                };
                this.buf      = new_buf;
                this.capacity = new_cap;
                return true;
            };

            // ----------------------------------------------------------------
            // Internal: return byte pointer to element at index i (no bounds check).
            // ----------------------------------------------------------------
            def _ptr(size_t i) -> byte*
            {
                return (byte*)this.buf + i * this.elem_size;
            };

            // ----------------------------------------------------------------
            // len() - number of elements currently stored.
            // ----------------------------------------------------------------
            def len() -> size_t
            {
                return this.len;
            };

            // ----------------------------------------------------------------
            // push(src) - append a copy of the element pointed to by src.
            // Returns false if allocation fails.
            // ----------------------------------------------------------------
            def push(void* src) -> bool
            {
                if (this.len >= this.capacity)
                {
                    if (!this._grow())
                    {
                        return false;
                    };
                };
                memcpy(this._ptr(this.len), src, this.elem_size);
                this.len++;
                return true;
            };

            // ----------------------------------------------------------------
            // pop(dst) - copy the last element into dst and shrink len by 1.
            // Returns false if the array is empty.
            // ----------------------------------------------------------------
            def pop(void* dst) -> bool
            {
                if (this.len == 0)
                {
                    return false;
                };
                this.len--;
                memcpy(dst, this._ptr(this.len), this.elem_size);
                return true;
            };

            // ----------------------------------------------------------------
            // get(i) - return a pointer to element i in the backing buffer.
            // Returns null if i is out of range. Caller casts to their type.
            // ----------------------------------------------------------------
            def get(size_t i) -> void*
            {
                if (i >= this.len)
                {
                    return STDLIB_GVP;
                };
                return (void*)this._ptr(i);
            };

            // ----------------------------------------------------------------
            // set(i, src) - overwrite element i with a copy of the value at src.
            // Returns false if i is out of range.
            // ----------------------------------------------------------------
            def set(size_t i, void* src) -> bool
            {
                if (i >= this.len)
                {
                    return false;
                };
                memcpy(this._ptr(i), src, this.elem_size);
                return true;
            };

            // ----------------------------------------------------------------
            // insert(i, src) - insert element at index i, shifting everything
            // from i onward one position to the right.
            // Returns false if i > len or allocation fails.
            // ----------------------------------------------------------------
            def insert(size_t i, void* src) -> bool
            {
                if (i > this.len)
                {
                    return false;
                };
                if (this.len >= this.capacity)
                {
                    if (!this._grow())
                    {
                        return false;
                    };
                };
                // Shift elements [i .. len) one slot to the right.
                if (i < this.len)
                {
                    size_t n = (this.len - i) * this.elem_size;
                    memmove(this._ptr(i + 1), this._ptr(i), n);
                };
                memcpy(this._ptr(i), src, this.elem_size);
                this.len++;
                return true;
            };

            // ----------------------------------------------------------------
            // remove(i) - remove the element at index i, shifting everything
            // after it one position to the left.
            // Returns false if i is out of range.
            // ----------------------------------------------------------------
            def remove(size_t i) -> bool
            {
                if (i >= this.len)
                {
                    return false;
                };
                this.len--;
                if (i < this.len)
                {
                    size_t n = (this.len - i) * this.elem_size;
                    memmove(this._ptr(i), this._ptr(i + 1), n);
                };
                return true;
            };

            // ----------------------------------------------------------------
            // clear() - reset length to zero. Does not free or shrink the buffer.
            // ----------------------------------------------------------------
            def clear() -> void
            {
                this.len = 0;
                return;
            };

            // ----------------------------------------------------------------
            // contains(src) - linear scan; returns true if any element compares
            // equal to the value pointed to by src (byte-for-byte comparison).
            // ----------------------------------------------------------------
            def contains(void* src) -> bool
            {
                size_t i;
                while (i < this.len)
                {
                    if (memcmp(this._ptr(i), (byte*)src, this.elem_size) == 0)
                    {
                        return true;
                    };
                    i++;
                };
                return false;
            };
        };
    };

    namespace collections
    {
        // -------------------------------------------------------------------------
        // Internal bucket structs
        // -------------------------------------------------------------------------

        struct HMBucket
        {
            u64   key_hash;
            byte* key;
            void* value;
            u64   psl;
        };

        struct HMIBucket
        {
            u64   key_hash, key;
            void* value;
            u64   psl;
        };

        // -------------------------------------------------------------------------
        // Hash functions
        // -------------------------------------------------------------------------

        // FNV-1a 64-bit for string keys
        def hm_hash_str(byte* key) -> u64
        {
            u64 hash = 14695981039346656037u,
                prime = 1099511628211u;
            int i;

            while (key[i] != 0)
            {
                hash = hash xor key[i];
                hash = hash * prime;
                i = i + 1;
            };
            // Ensure hash != 0 (reserved for empty slots)
            if (hash == 0)
            {
                hash = 1;
            };
            return hash;
        };

        // Murmur-inspired mix for integer keys
        def hm_hash_u64(u64 key) -> u64
        {
            u64 h = key;
            h = h xor (h >> 33);
            h = h * 18397679294719823053u;
            h = h xor (h >> 33);
            h = h * 14181476777654086739u;
            h = h xor (h >> 33);
            if (h == 0)
            {
                h = 1;
            };
            return h;
        };

        // -------------------------------------------------------------------------
        // String comparison helper
        // -------------------------------------------------------------------------

        def hm_str_eq(byte* a, byte* b) -> bool
        {
            int i;
            while (true)
            {
                if (a[i] != b[i])
                {
                    return false;
                };
                if (a[i] == 0)
                {
                    return true;
                };
                i = i + 1;
            };
            return false;
        };

        // -------------------------------------------------------------------------
        // String key copy helper (allocates new buffer)
        // -------------------------------------------------------------------------

        def hm_str_dup(byte* src) -> byte*
        {
            int len, i;
            while (src[len] != 0)
            {
                len = len + 1;
            };
            byte* dst = (byte*)stdheap::fmalloc(len + 1);
            while (i < len)
            {
                dst[i] = src[i];
                i = i + 1;
            };
            dst[len] = 0;
            return dst;
        };

        trait BaseSTDHashMapTraits
        {
            def _insert_nocopy(u64 hash, byte* key, void* value) -> void,
                _resize() -> void,
                hm_get(byte* key) -> void*,
                hm_set(byte* key, void* value) -> void,
                hm_has(byte* key) -> bool,
                hm_remove(byte* key) -> bool,
                hm_count() -> u64,
                hm_capacity() -> u64;
        };

        BaseSTDHashMapTraits
        object HashMap
        {
            HMBucket* buckets;
            u64       count,
                      cap;

            def __init(u64 initial_cap) -> this
            {
                // Round up to next power of two, minimum 16
                u64 c = 16, i;
                while (c < initial_cap)
                {
                    c = c * 2;
                };
                this.cap     = c;
                this.count   = 0;
                u64 nbytes   = c * 32; // sizeof(HMBucket) = 32
                this.buckets = (HMBucket*)stdheap::fmalloc(nbytes);
                // Zero all buckets (key_hash == 0 means empty)
                while (i < c)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = (byte*)0;
                    this.buckets[i].value    = (void*)0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };
                return this;
            };

            def __exit() -> void
            {
                // Free all duplicated key strings
                u64 i;
                while (i < this.cap)
                {
                    if (this.buckets[i].key_hash != 0)
                    {
                        stdheap::ffree((u64)this.buckets[i].key);
                    };
                    i = i + 1;
                };
                stdheap::ffree((u64)this.buckets);
            };

            def __expr() -> HashMap*
            {
                return this;
            };

            // Internal: insert without copying key (used during resize)
            def _insert_nocopy(u64 hash, byte* key, void* value) -> void
            {
                u64 mask = this.cap - 1;
                u64 idx  = hash & mask,
                    psl;
                HMBucket* slot;
                HMBucket  tmp;

                HMBucket insert_bkt;
                insert_bkt.key_hash = hash;
                insert_bkt.key      = key;
                insert_bkt.value    = value;
                insert_bkt.psl      = psl;

                while (true)
                {
                    slot = this.buckets + idx;

                    // Empty slot: place here
                    if (slot.key_hash == 0)
                    {
                        slot.key_hash = insert_bkt.key_hash;
                        slot.key      = insert_bkt.key;
                        slot.value    = insert_bkt.value;
                        slot.psl      = insert_bkt.psl;
                        this.count    = this.count + 1;
                        return;
                    };

                    // Same key: update value
                    if (slot.key_hash == insert_bkt.key_hash)
                    {
                        if (hm_str_eq(slot.key, insert_bkt.key))
                        {
                            slot.value = insert_bkt.value;
                            return;
                        };
                    };

                    // Robin hood: steal from rich slot
                    if (slot.psl < insert_bkt.psl)
                    {
                        // Swap insert_bkt with slot
                        tmp.key_hash       = slot.key_hash;
                        tmp.key            = slot.key;
                        tmp.value          = slot.value;
                        tmp.psl            = slot.psl;

                        slot.key_hash      = insert_bkt.key_hash;
                        slot.key           = insert_bkt.key;
                        slot.value         = insert_bkt.value;
                        slot.psl           = insert_bkt.psl;

                        insert_bkt.key_hash = tmp.key_hash;
                        insert_bkt.key      = tmp.key;
                        insert_bkt.value    = tmp.value;
                        insert_bkt.psl      = tmp.psl;
                    };

                    idx = (idx + 1) & mask;
                    insert_bkt.psl = insert_bkt.psl + 1;
                };
            };

            // Internal: grow and rehash
            def _resize() -> void
            {
                u64 old_cap   = this.cap,
                    new_cap   = old_cap * 2,
                    nbytes    = new_cap * 32,
                    i;
                HMBucket* old_buckets = this.buckets;

                this.buckets  = (HMBucket*)stdheap::fmalloc(nbytes);
                this.cap      = new_cap;
                this.count    = 0;

                while (i < new_cap)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = (byte*)0;
                    this.buckets[i].value    = (void*)0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };

                i = 0;
                while (i < old_cap)
                {
                    if (old_buckets[i].key_hash != 0)
                    {
                        this._insert_nocopy(
                            old_buckets[i].key_hash,
                            old_buckets[i].key,
                            old_buckets[i].value
                        );
                    };
                    i = i + 1;
                };

                stdheap::ffree((u64)old_buckets);
            };

            // Insert or update a key-value pair.
            def hm_set(byte* key, void* value) -> void
            {
                // Resize if load > 75%
                // count * 4 > cap * 3  <=>  load > 0.75
                if (this.count * 4 > this.cap * 3)
                {
                    this._resize();
                };

                u64 hash = hm_hash_str(key);
                u64 mask = this.cap - 1;
                u64 idx  = hash & mask,
                    psl;
                HMBucket* slot;
                HMBucket insert_bkt, tmp;
                insert_bkt.key_hash = hash;
                insert_bkt.key      = hm_str_dup(key);
                insert_bkt.value    = value;
                insert_bkt.psl      = psl;

                while (true)
                {
                    slot = this.buckets + idx;

                    // Empty slot
                    if (slot.key_hash == 0)
                    {
                        slot.key_hash = insert_bkt.key_hash;
                        slot.key      = insert_bkt.key;
                        slot.value    = insert_bkt.value;
                        slot.psl      = insert_bkt.psl;
                        this.count    = this.count + (u64)1;
                        return;
                    };

                    // Existing key: update, free the new dup
                    if (slot.key_hash == insert_bkt.key_hash)
                    {
                        if (hm_str_eq(slot.key, insert_bkt.key))
                        {
                            stdheap::ffree((u64)insert_bkt.key);
                            slot.value = insert_bkt.value;
                            return;
                        };
                    };

                    // Robin hood swap
                    if (slot.psl < insert_bkt.psl)
                    {
                        tmp.key_hash       = slot.key_hash;
                        tmp.key            = slot.key;
                        tmp.value          = slot.value;
                        tmp.psl            = slot.psl;

                        slot.key_hash      = insert_bkt.key_hash;
                        slot.key           = insert_bkt.key;
                        slot.value         = insert_bkt.value;
                        slot.psl           = insert_bkt.psl;

                        insert_bkt.key_hash = tmp.key_hash;
                        insert_bkt.key      = tmp.key;
                        insert_bkt.value    = tmp.value;
                        insert_bkt.psl      = tmp.psl;
                    };

                    idx = (idx + (u64)1) & mask;
                    insert_bkt.psl = insert_bkt.psl + (u64)1;
                };
            };

            // Retrieve value for key. Returns NULL if not found.
            def hm_get(byte* key) -> void*
            {
                u64 hash = hm_hash_str(key),
                    mask = this.cap - 1,
                    idx  = hash & mask,
                    psl;
                HMBucket slot;

                while (true)
                {
                    slot = this.buckets + idx;

                    if (slot.key_hash == 0)
                    {
                        return (void*)0;
                    };

                    if (slot.psl < psl)
                    {
                        // Robin hood invariant: can't be further than this
                        return (void*)0;
                    };

                    if (slot.key_hash == hash)
                    {
                        if (hm_str_eq(slot.key, key))
                        {
                            return slot.value;
                        };
                    };

                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return (void*)0;
            };

            // Check if a key exists.
            def hm_has(byte* key) -> bool
            {
                return this.hm_get(key) != (void*)0;
            };

            // Remove a key. Returns true if it was present.
            def hm_remove(byte* key) -> bool
            {
                u64 hash = hm_hash_str(key),
                    mask = this.cap - 1,
                    idx  = hash & mask,
                    psl,
                    cur, next;
                HMBucket* slot, nx, cr;

                while (true)
                {
                    slot = this.buckets + idx;

                    if (slot.key_hash == 0)
                    {
                        return false;
                    };

                    if (slot.psl < psl)
                    {
                        return false;
                    };

                    if (slot.key_hash == hash)
                    {
                        if (hm_str_eq(slot.key, key))
                        {
                            // Free the duplicated key
                            stdheap::ffree((u64)slot.key);
                            slot.key_hash = 0;
                            slot.key      = (byte*)0;
                            slot.value    = (void*)0;
                            slot.psl      = 0;
                            this.count    = this.count - 1;

                            // Backward shift deletion to maintain robin hood invariant
                            cur  = idx;
                            next = (idx + 1) & mask;
                            while (true)
                            {
                                nx = this.buckets + next;
                                if (nx.key_hash == 0 | nx.psl == 0)
                                {
                                    break;
                                };
                                cr = this.buckets + cur;
                                cr.key_hash = nx.key_hash;
                                cr.key      = nx.key;
                                cr.value    = nx.value;
                                cr.psl      = nx.psl - 1;
                                nx.key_hash = 0;
                                nx.key      = (byte*)0;
                                nx.value    = (void*)0;
                                nx.psl      = 0;
                                cur  = next;
                                next = (next + 1) & mask;
                            };

                            return true;
                        };
                    };

                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return false;
            };

            def hm_count() -> u64
            {
                return this.count;
            };

            def hm_capacity() -> u64
            {
                return this.cap;
            };
        };

        // -------------------------------------------------------------------------
        // HashMapInt (u64 keys)
        // -------------------------------------------------------------------------

        trait BaseSTDHashMapIntTraits
        {
            def _insert_raw(u64 hash, u64 key, void* value) -> void,
                _resize() -> void,
                hmi_get(u64 key) -> void*,
                hmi_set(u64 key, void* value) -> void,
                hmi_has(u64 key) -> bool,
                hmi_remove(u64 key) -> bool,
                hmi_count() -> u64,
                hmi_capacity() -> u64;
        };

        BaseSTDHashMapIntTraits
        object HashMapInt
        {
            HMIBucket* buckets;
            u64        count,
                       cap;

            def __init(u64 initial_cap) -> this
            {
                u64 c = 16;
                u64 nbytes = c * 32, // sizeof(HMIBucket) = 32
                    i;
                while (c < initial_cap)
                {
                    c = c * 2;
                };
                this.cap     = c;
                this.count   = 0;
                this.buckets = (HMIBucket*)stdheap::fmalloc(nbytes);
                while (i < c)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = 0;
                    this.buckets[i].value    = (void*)0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };
                return this;
            };

            def __exit() -> void
            {
                stdheap::ffree((u64)this.buckets);
            };

            def __expr() -> HashMapInt*
            {
                return this;
            };

            def _insert_raw(u64 hash, u64 key, void* value) -> void
            {
                u64 mask = this.cap - 1;
                u64 idx  = hash & mask;

                HMIBucket ins, tmp;
                HMIBucket* slot;
                ins.key_hash = hash;
                ins.key      = key;
                ins.value    = value;
                ins.psl      = 0;

                while (true)
                {
                    slot = this.buckets + idx;

                    if (slot.key_hash == 0)
                    {
                        slot.key_hash = ins.key_hash;
                        slot.key      = ins.key;
                        slot.value    = ins.value;
                        slot.psl      = ins.psl;
                        this.count    = this.count + 1;
                        return;
                    };

                    if (slot.key_hash == ins.key_hash & slot.key == ins.key)
                    {
                        slot.value = ins.value;
                        return;
                    };

                    if (slot.psl < ins.psl)
                    {
                        tmp.key_hash  = slot.key_hash;
                        tmp.key       = slot.key;
                        tmp.value     = slot.value;
                        tmp.psl       = slot.psl;

                        slot.key_hash = ins.key_hash;
                        slot.key      = ins.key;
                        slot.value    = ins.value;
                        slot.psl      = ins.psl;

                        ins.key_hash  = tmp.key_hash;
                        ins.key       = tmp.key;
                        ins.value     = tmp.value;
                        ins.psl       = tmp.psl;
                    };

                    idx    = (idx + 1) & mask;
                    ins.psl = ins.psl + 1;
                };
            };

            def _resize() -> void
            {
                u64 old_cap     = this.cap;
                u64 new_cap   = old_cap * 2;
                u64 nbytes    = new_cap * 32,
                    i;
                HMIBucket* old_buckets = this.buckets;

                this.buckets  = (HMIBucket*)stdheap::fmalloc(nbytes);
                this.cap      = new_cap;
                this.count    = 0;

                while (i < new_cap)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = 0;
                    this.buckets[i].value    = (void*)0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };

                i = 0;
                while (i < old_cap)
                {
                    if (old_buckets[i].key_hash != 0)
                    {
                        this._insert_raw(
                            old_buckets[i].key_hash,
                            old_buckets[i].key,
                            old_buckets[i].value
                        );
                    };
                    i = i + 1;
                };

                stdheap::ffree((u64)old_buckets);
            };

            def hmi_set(u64 key, void* value) -> void
            {
                if (this.count * (u64)4 > this.cap * (u64)3)
                {
                    this._resize();
                };
                u64 hash = hm_hash_u64(key);
                this._insert_raw(hash, key, value);
            };

            def hmi_get(u64 key) -> void*
            {
                u64 hash = hm_hash_u64(key),
                    mask = this.cap - 1,
                    idx  = hash & mask,
                    psl;
                HMIBucket slot;

                while (true)
                {
                    slot = this.buckets + idx;

                    if (slot.key_hash == 0)
                    {
                        return (void*)0;
                    };

                    if (slot.psl < psl)
                    {
                        return (void*)0;
                    };

                    if (slot.key_hash == hash & slot.key == key)
                    {
                        return slot.value;
                    };

                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return (void*)0;
            };

            def hmi_has(u64 key) -> bool
            {
                return this.hmi_get(key) != (void*)0;
            };

            def hmi_remove(u64 key) -> bool
            {
                u64 hash = hm_hash_u64(key),
                    mask = this.cap - (u64)1,
                    idx  = hash & mask,
                    psl,
                    cur, next;

                HMIBucket* slot, nx, cr;

                while (true)
                {
                    slot = this.buckets + idx;

                    if (slot.key_hash == 0)
                    {
                        return false;
                    };

                    if (slot.psl < psl)
                    {
                        return false;
                    };

                    if (slot.key_hash == hash & slot.key == key)
                    {
                        slot.key_hash = 0;
                        slot.key      = 0;
                        slot.value    = (void*)0;
                        slot.psl      = 0;
                        this.count    = this.count - 1;

                        // Backward shift deletion
                        cur  = idx;
                        next = (idx + 1) & mask;
                        while (true)
                        {
                            nx = this.buckets + next;
                            if (nx.key_hash == 0 | nx.psl == 0)
                            {
                                break;
                            };
                            cr = this.buckets + cur;
                            cr.key_hash = nx.key_hash;
                            cr.key      = nx.key;
                            cr.value    = nx.value;
                            cr.psl      = nx.psl - 1;
                            nx.key_hash = 0;
                            nx.key      = 0;
                            nx.value    = (void*)0;
                            nx.psl      = 0;
                            cur  = next;
                            next = (next + 1) & mask;
                        };

                        return true;
                    };

                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return false;
            };

            def hmi_count() -> u64
            {
                return this.count;
            };

            def hmi_capacity() -> u64
            {
                return this.cap;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // LinkedList
        // Doubly-linked list backed by a fixed-capacity node pool.
        // The pool is a single slab allocated at __init time; nodes are carved from
        // it via a free-list.  No per-push malloc, no per-pop free, no alloc/free
        // inside any loop.
        //
        // pool_cap: maximum number of nodes the list can hold (set at __init).
        //
        // Usage example:
        //   LinkedList list((size_t)64);
        //   int x = 42;
        //   LLNode* n = list.push_back(@x);
        //   void*   v = list.pop_front();
        // ============================================================================

        struct LLNode
        {
            LLNode* prev,
                    next;
            void*   value;
        };

        trait BaseSTDLinkedListTraits
        {
            def push_front(void* value) -> LLNode*,
                push_back(void* value)  -> LLNode*,
                pop_front()             -> void*,
                pop_back()              -> void*,
                peek_front()            -> void*,
                peek_back()             -> void*,
                remove_node(LLNode* n)  -> void*,
                ll_len()                -> size_t,
                ll_clear()              -> void;
        };

        BaseSTDLinkedListTraits
        object LinkedList
        {
            LLNode* pool,      // backing slab: pool_cap * sizeof(LLNode) bytes
                    freelist,  // head of the free-list threaded through unused nodes
                    head,
                    tail;
            size_t  pool_cap,
                    len;

            // Construct a list with a fixed node pool of pool_cap entries.
            // One fmalloc here; no further allocations ever.
            def __init(size_t pool_cap) -> this
            {
                this.pool_cap = pool_cap;
                this.len      = 0;
                this.head     = (LLNode*)STDLIB_GVP;
                this.tail     = (LLNode*)STDLIB_GVP;
                // sizeof(LLNode) = 24 (prev:8, next:8, value:8)
                this.pool     = (LLNode*)stdheap::fmalloc(pool_cap * 24);
                // Thread free-list through all nodes; next pointer serves as link.
                // All locals must be declared at function top.
                size_t i = 0;
                LLNode* node, nx;
                while (i < pool_cap)
                {
                    node = this.pool + i;
                    if (i + 1 < pool_cap)
                    {
                        nx = this.pool + (i + 1);
                    }
                    else
                    {
                        nx = (LLNode*)STDLIB_GVP;
                    };
                    node.next  = nx;
                    node.prev  = (LLNode*)STDLIB_GVP;
                    node.value = STDLIB_GVP;
                    i = i + 1;
                };
                this.freelist = this.pool;
                return this;
            };

            // Free the pool slab.  One ffree; no loop.
            def __exit() -> void
            {
                stdheap::ffree((u64)this.pool);
                this.pool     = (LLNode*)STDLIB_GVP;
                this.freelist = (LLNode*)STDLIB_GVP;
                this.head     = (LLNode*)STDLIB_GVP;
                this.tail     = (LLNode*)STDLIB_GVP;
                this.len      = 0;
                return;
            };

            def __expr() -> LinkedList*
            {
                return this;
            };

            // ----------------------------------------------------------------
            // push_front(value) - prepend. Returns node ptr or STDLIB_GVP if full.
            // ----------------------------------------------------------------
            def push_front(void* value) -> LLNode*
            {
                if (this.freelist == (LLNode*)STDLIB_GVP)
                {
                    return (LLNode*)STDLIB_GVP;
                };
                LLNode* n     = this.freelist;
                this.freelist = n.next;
                n.prev        = (LLNode*)STDLIB_GVP;
                n.next        = this.head;
                n.value       = value;
                if (this.head != (LLNode*)STDLIB_GVP)
                {
                    this.head.prev = n;
                }
                else
                {
                    this.tail = n;
                };
                this.head = n;
                this.len  = this.len + 1;
                return n;
            };

            // ----------------------------------------------------------------
            // push_back(value) - append. Returns node ptr or STDLIB_GVP if full.
            // ----------------------------------------------------------------
            def push_back(void* value) -> LLNode*
            {
                if (this.freelist == (LLNode*)STDLIB_GVP)
                {
                    return (LLNode*)STDLIB_GVP;
                };
                LLNode* n     = this.freelist;
                this.freelist = n.next;
                n.prev        = this.tail;
                n.next        = (LLNode*)STDLIB_GVP;
                n.value       = value;
                if (this.tail != (LLNode*)STDLIB_GVP)
                {
                    this.tail.next = n;
                }
                else
                {
                    this.head = n;
                };
                this.tail = n;
                this.len  = this.len + 1;
                return n;
            };

            // ----------------------------------------------------------------
            // pop_front() - remove head, return its value. Returns STDLIB_GVP if empty.
            // ----------------------------------------------------------------
            def pop_front() -> void*
            {
                if (this.head == (LLNode*)STDLIB_GVP)
                {
                    return STDLIB_GVP;
                };
                LLNode* n   = this.head;
                void*   val = n.value;
                this.head   = n.next;
                if (this.head != (LLNode*)STDLIB_GVP)
                {
                    this.head.prev = (LLNode*)STDLIB_GVP;
                }
                else
                {
                    this.tail = (LLNode*)STDLIB_GVP;
                };
                // Return node to free-list
                n.next        = this.freelist;
                n.prev        = (LLNode*)STDLIB_GVP;
                n.value       = STDLIB_GVP;
                this.freelist = n;
                this.len      = this.len - 1;
                return val;
            };

            // ----------------------------------------------------------------
            // pop_back() - remove tail, return its value. Returns STDLIB_GVP if empty.
            // ----------------------------------------------------------------
            def pop_back() -> void*
            {
                if (this.tail == (LLNode*)STDLIB_GVP)
                {
                    return STDLIB_GVP;
                };
                LLNode* n   = this.tail;
                void*   val = n.value;
                this.tail   = n.prev;
                if (this.tail != (LLNode*)STDLIB_GVP)
                {
                    this.tail.next = (LLNode*)STDLIB_GVP;
                }
                else
                {
                    this.head = (LLNode*)STDLIB_GVP;
                };
                // Return node to free-list
                n.next        = this.freelist;
                n.prev        = (LLNode*)STDLIB_GVP;
                n.value       = STDLIB_GVP;
                this.freelist = n;
                this.len      = this.len - 1;
                return val;
            };

            // ----------------------------------------------------------------
            // peek_front() - head value without removal. STDLIB_GVP if empty.
            // ----------------------------------------------------------------
            def peek_front() -> void*
            {
                if (this.head == (LLNode*)STDLIB_GVP)
                {
                    return STDLIB_GVP;
                };
                return this.head.value;
            };

            // ----------------------------------------------------------------
            // peek_back() - tail value without removal. STDLIB_GVP if empty.
            // ----------------------------------------------------------------
            def peek_back() -> void*
            {
                if (this.tail == (LLNode*)STDLIB_GVP)
                {
                    return STDLIB_GVP;
                };
                return this.tail.value;
            };

            // ----------------------------------------------------------------
            // remove_node(n) - unlink a node and return to free-list.
            // Returns the value stored in the node.
            // ----------------------------------------------------------------
            def remove_node(LLNode* n) -> void*
            {
                void* val = n.value;
                if (n.prev != (LLNode*)STDLIB_GVP)
                {
                    n.prev.next = n.next;
                }
                else
                {
                    this.head = n.next;
                };
                if (n.next != (LLNode*)STDLIB_GVP)
                {
                    n.next.prev = n.prev;
                }
                else
                {
                    this.tail = n.prev;
                };
                n.next        = this.freelist;
                n.prev        = (LLNode*)STDLIB_GVP;
                n.value       = STDLIB_GVP;
                this.freelist = n;
                this.len      = this.len - 1;
                return val;
            };

            // ----------------------------------------------------------------
            // ll_len() - number of nodes currently in the list.
            // ----------------------------------------------------------------
            def ll_len() -> size_t
            {
                return this.len;
            };

            // ----------------------------------------------------------------
            // ll_clear() - return all live nodes to free-list. No alloc/free.
            // ----------------------------------------------------------------
            def ll_clear() -> void
            {
                LLNode* cur = this.head, nxt;
                while (cur != (LLNode*)STDLIB_GVP)
                {
                    nxt           = cur.next;
                    cur.next      = this.freelist;
                    cur.prev      = (LLNode*)STDLIB_GVP;
                    cur.value     = STDLIB_GVP;
                    this.freelist = cur;
                    cur           = nxt;
                };
                this.head = (LLNode*)STDLIB_GVP;
                this.tail = (LLNode*)STDLIB_GVP;
                this.len  = 0;
                return;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // Stack
        // LIFO stack backed by LinkedList pool.
        // stack_push/stack_pop/stack_peek are O(1), no alloc.
        //
        // Usage example:
        //   Stack s((size_t)64);
        //   int x = 7;
        //   s.stack_push(@x);
        //   void* v = s.stack_pop();
        // ============================================================================

        trait BaseSTDStackTraits
        {
            def stack_push(void* value) -> bool,
                stack_pop()             -> void*,
                stack_peek()            -> void*,
                stack_len()             -> size_t,
                stack_empty()           -> bool;
        };

        BaseSTDStackTraits
        object Stack
        {
            LinkedList ll;

            def __init(size_t cap) -> this
            {
                this.ll.__init(cap);
                return this;
            };

            def __exit() -> void
            {
                this.ll.__exit();
                return;
            };

            def __expr() -> Stack*
            {
                return this;
            };

            def stack_push(void* value) -> bool
            {
                LLNode* n = this.ll.push_back(value);
                return n != (LLNode*)STDLIB_GVP;
            };

            def stack_pop() -> void*
            {
                return this.ll.pop_back();
            };

            def stack_peek() -> void*
            {
                return this.ll.peek_back();
            };

            def stack_len() -> size_t
            {
                return this.ll.ll_len();
            };

            def stack_empty() -> bool
            {
                return this.ll.ll_len() == 0;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // Queue
        // FIFO queue backed by LinkedList pool.
        // enqueue/dequeue/queue_peek are O(1), no alloc.
        //
        // Usage example:
        //   Queue q((size_t)64);
        //   int x = 3;
        //   q.enqueue(@x);
        //   void* v = q.dequeue();
        // ============================================================================

        trait BaseSTDQueueTraits
        {
            def enqueue(void* value) -> bool,
                dequeue()            -> void*,
                queue_peek()         -> void*,
                queue_len()          -> size_t,
                queue_empty()        -> bool;
        };

        BaseSTDQueueTraits
        object Queue
        {
            LinkedList ll;

            def __init(size_t cap) -> this
            {
                this.ll.__init(cap);
                return this;
            };

            def __exit() -> void
            {
                this.ll.__exit();
                return;
            };

            def __expr() -> Queue*
            {
                return this;
            };

            def enqueue(void* value) -> bool
            {
                LLNode* n = this.ll.push_back(value);
                return n != (LLNode*)STDLIB_GVP;
            };

            def dequeue() -> void*
            {
                return this.ll.pop_front();
            };

            def queue_peek() -> void*
            {
                return this.ll.peek_front();
            };

            def queue_len() -> size_t
            {
                return this.ll.ll_len();
            };

            def queue_empty() -> bool
            {
                return this.ll.ll_len() == 0;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // Deque  (double-ended queue)
        // Ring-buffer backed deque with fixed capacity set at construction time.
        // push_front, push_back, pop_front, pop_back are all O(1), no alloc.
        // The backing buffer holds void* pointers (one per slot).
        // When the buffer is full, push operations return false.
        //
        // Usage example:
        //   Deque dq((size_t)32);
        //   int x = 5;
        //   dq.dq_push_back(@x);
        //   void* v = dq.dq_pop_front();
        // ============================================================================

        #def DEQUE_DEFAULT_CAPACITY 16;

        trait BaseSTDDequeTraits
        {
            def dq_push_front(void* value) -> bool,
                dq_push_back(void* value)  -> bool,
                dq_pop_front()             -> void*,
                dq_pop_back()              -> void*,
                dq_peek_front()            -> void*,
                dq_peek_back()             -> void*,
                dq_len()                   -> size_t,
                dq_full()                  -> bool,
                dq_empty()                 -> bool,
                dq_clear()                 -> void;
        };

        BaseSTDDequeTraits
        object Deque
        {
            void** buf;
            size_t cap,
                   head,
                   tail,
                   len;

            // One fmalloc at init; no further alloc ever.
            def __init(size_t cap) -> this
            {
                this.cap  = cap;
                this.head = 0;
                this.tail = 0;
                this.len  = 0;
                this.buf  = (void**)stdheap::fmalloc(cap * 8);
                return this;
            };

            def __exit() -> void
            {
                if (this.buf != (void**)STDLIB_GVP)
                {
                    stdheap::ffree((u64)this.buf);
                    this.buf = (void**)STDLIB_GVP;
                };
                return;
            };

            def __expr() -> Deque*
            {
                return this;
            };

            def dq_push_back(void* value) -> bool
            {
                if (this.len == this.cap)
                {
                    return false;
                };
                this.buf[this.tail] = value;
                this.tail = (this.tail + 1) % this.cap;
                this.len  = this.len + 1;
                return true;
            };

            def dq_push_front(void* value) -> bool
            {
                if (this.len == this.cap)
                {
                    return false;
                };
                this.head           = (this.head + this.cap - 1) % this.cap;
                this.buf[this.head] = value;
                this.len            = this.len + 1;
                return true;
            };

            def dq_pop_front() -> void*
            {
                if (this.len == 0)
                {
                    return STDLIB_GVP;
                };
                void* val = this.buf[this.head];
                this.head = (this.head + 1) % this.cap;
                this.len  = this.len - 1;
                return val;
            };

            def dq_pop_back() -> void*
            {
                if (this.len == 0)
                {
                    return STDLIB_GVP;
                };
                this.tail = (this.tail + this.cap - 1) % this.cap;
                void* val = this.buf[this.tail];
                this.len  = this.len - 1;
                return val;
            };

            def dq_peek_front() -> void*
            {
                if (this.len == 0)
                {
                    return STDLIB_GVP;
                };
                return (void*)this.buf[this.head];
            };

            def dq_peek_back() -> void*
            {
                if (this.len == 0)
                {
                    return STDLIB_GVP;
                };
                size_t idx = (this.tail + this.cap - 1) % this.cap;
                return (void*)this.buf[idx];
            };

            def dq_len() -> size_t
            {
                return this.len;
            };

            def dq_full() -> bool
            {
                return this.len == this.cap;
            };

            def dq_empty() -> bool
            {
                return this.len == 0;
            };

            def dq_clear() -> void
            {
                this.head = 0;
                this.tail = 0;
                this.len  = 0;
                return;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // RingBuffer
        // Fixed-capacity circular buffer for raw bytes.
        // write() copies bytes in; read() copies bytes out.
        // One fmalloc at init; no further alloc.  All loops move bytes only.
        //
        // Usage example:
        //   RingBuffer rb((size_t)1024);
        //   byte buf[4];
        //   rb.rb_write((byte*)@buf, (size_t)4);
        //   rb.rb_read((byte*)@buf, (size_t)4);
        // ============================================================================

        trait BaseSTDRingBufferTraits
        {
            def rb_write(byte* src, size_t n) -> size_t,
                rb_read(byte* dst, size_t n)  -> size_t,
                rb_peek(byte* dst, size_t n)  -> size_t,
                rb_skip(size_t n)             -> size_t,
                rb_available()                -> size_t,
                rb_free_space()               -> size_t,
                rb_empty()                    -> bool,
                rb_full()                     -> bool,
                rb_clear()                    -> void;
        };

        BaseSTDRingBufferTraits
        object RingBuffer
        {
            byte*  buf;
            size_t cap,
                   head,
                   tail,
                   used;

            def __init(size_t cap) -> this
            {
                this.cap  = cap;
                this.head = 0;
                this.tail = 0;
                this.used = 0;
                this.buf  = (byte*)stdheap::fmalloc(cap);
                return this;
            };

            def __exit() -> void
            {
                if (this.buf != (byte*)STDLIB_GVP)
                {
                    stdheap::ffree((u64)this.buf);
                    this.buf = (byte*)STDLIB_GVP;
                };
                return;
            };

            def __expr() -> RingBuffer*
            {
                return this;
            };

            def rb_write(byte* src, size_t n) -> size_t
            {
                size_t space = this.cap - this.used,
                       i;
                if (n > space)
                {
                    n = space;
                };
                while (i < n)
                {
                    this.buf[this.tail] = src[i];
                    this.tail = (this.tail + 1) % this.cap;
                    i = i + 1;
                };
                this.used = this.used + n;
                return n;
            };

            def rb_read(byte* dst, size_t n) -> size_t
            {
                size_t i;
                if (n > this.used)
                {
                    n = this.used;
                };
                while (i < n)
                {
                    dst[i] = this.buf[this.head];
                    this.head = (this.head + 1) % this.cap;
                    i = i + 1;
                };
                this.used = this.used - n;
                return n;
            };

            def rb_peek(byte* dst, size_t n) -> size_t
            {
                size_t i, pos = this.head;
                if (n > this.used)
                {
                    n = this.used;
                };
                while (i < n)
                {
                    dst[i] = this.buf[pos];
                    pos = (pos + 1) % this.cap;
                    i   = i + 1;
                };
                return n;
            };

            def rb_skip(size_t n) -> size_t
            {
                if (n > this.used)
                {
                    n = this.used;
                };
                this.head = (this.head + n) % this.cap;
                this.used = this.used - n;
                return n;
            };

            def rb_available() -> size_t
            {
                return this.used;
            };

            def rb_free_space() -> size_t
            {
                return this.cap - this.used;
            };

            def rb_empty() -> bool
            {
                return this.used == 0;
            };

            def rb_full() -> bool
            {
                return this.used == this.cap;
            };

            def rb_clear() -> void
            {
                this.head = 0;
                this.tail = 0;
                this.used = 0;
                return;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // HashSet  (string keys)
        // Open-addressed robin-hood hash set.
        // Keys are stored in a flat key-pool slab allocated once at __init.
        // A bump pointer carves space for each new key; no per-key malloc.
        // __exit frees two slabs (buckets + key pool) — no loop, no per-key free.
        //
        // key_pool_bytes: total bytes reserved for key storage.
        //
        // Usage example:
        //   HashSet hs((u64)16, (u64)1024);
        //   hs.set_add("hello");
        //   bool found = hs.set_has("hello");
        //   hs.set_remove("hello");
        // ============================================================================

        struct HSBucket
        {
            u64   key_hash;
            byte* key;
            u64   psl;
        };

        trait BaseSTDHashSetTraits
        {
            def _hs_probe(u64 hash, byte* key)  -> void,
                _hs_resize()                    -> void,
                set_add(byte* key)              -> void,
                set_has(byte* key)              -> bool,
                set_remove(byte* key)           -> bool,
                set_count()                     -> u64,
                set_capacity()                  -> u64;
        };

        BaseSTDHashSetTraits
        object HashSet
        {
            HSBucket* buckets;
            byte*     key_pool;
            u64       count,
                      cap,
                      key_pool_cap,
                      key_pool_used;

            // init: allocate bucket array and key pool in two fmallocs; no loops.
            def __init(u64 initial_cap, u64 key_pool_bytes) -> this
            {
                u64 c = 16, i;
                while (c < initial_cap)
                {
                    c = c * 2;
                };
                this.cap           = c;
                this.count         = 0;
                this.key_pool_cap  = key_pool_bytes;
                this.key_pool_used = 0;
                this.buckets       = (HSBucket*)stdheap::fmalloc(c * 24);
                this.key_pool      = (byte*)stdheap::fmalloc(key_pool_bytes);
                while (i < c)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = (byte*)0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };
                return this;
            };

            // exit: two frees, no loop.
            def __exit() -> void
            {
                stdheap::ffree((u64)this.buckets);
                stdheap::ffree((u64)this.key_pool);
                this.buckets  = (HSBucket*)STDLIB_GVP;
                this.key_pool = (byte*)STDLIB_GVP;
                return;
            };

            def __expr() -> HashSet*
            {
                return this;
            };

            // Internal: carve a copy of key from the pool (bump alloc, no malloc).
            // Returns pointer into pool, or STDLIB_GVP if pool is full.
            def _hs_pool_dup(byte* src) -> byte*
            {
                u64   slen;
                byte* p    = src;
                while (p[slen] != 0)
                {
                    slen = slen + 1;
                };
                slen = slen + 1; // include null terminator
                if (this.key_pool_used + slen > this.key_pool_cap)
                {
                    return (byte*)STDLIB_GVP;
                };
                byte* dst = this.key_pool + this.key_pool_used;
                u64   i;
                while (i < slen)
                {
                    dst[i] = src[i];
                    i = i + 1;
                };
                this.key_pool_used = this.key_pool_used + slen;
                return dst;
            };

            // Internal: robin-hood insert of an already-pooled key.
            // No alloc/free anywhere in this function.
            def _hs_probe(u64 hash, byte* key) -> void
            {
                u64 mask = this.cap - 1;
                u64 idx  = hash & mask,
                    psl;
                HSBucket ins, tmp;
                HSBucket* slot;
                ins.key_hash = hash;
                ins.key      = key;
                ins.psl      = 0;
                while (true)
                {
                    slot = this.buckets + idx;
                    if (slot.key_hash == 0)
                    {
                        slot.key_hash = ins.key_hash;
                        slot.key      = ins.key;
                        slot.psl      = ins.psl;
                        this.count    = this.count + 1;
                        return;
                    };
                    if (slot.key_hash == ins.key_hash)
                    {
                        if (hm_str_eq(slot.key, ins.key))
                        {
                            return;
                        };
                    };
                    if (slot.psl < ins.psl)
                    {
                        tmp.key_hash  = slot.key_hash;
                        tmp.key       = slot.key;
                        tmp.psl       = slot.psl;
                        slot.key_hash = ins.key_hash;
                        slot.key      = ins.key;
                        slot.psl      = ins.psl;
                        ins.key_hash  = tmp.key_hash;
                        ins.key       = tmp.key;
                        ins.psl       = tmp.psl;
                    };
                    idx = (idx + 1) & mask;
                    ins.psl = ins.psl + 1;
                    psl     = psl + 1;
                };
                return;
            };

            // resize: one fmalloc before the loop, one ffree after. No alloc in loop.
            def _hs_resize() -> void
            {
                u64 old_cap      = this.cap;
                u64 new_cap      = old_cap * 2;
                HSBucket* old_bk = this.buckets;
                u64 i            = 0;
                this.buckets     = (HSBucket*)stdheap::fmalloc(new_cap * 24);
                this.cap         = new_cap;
                this.count       = 0;
                while (i < new_cap)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = (byte*)0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };
                i = 0;
                while (i < old_cap)
                {
                    if (old_bk[i].key_hash != 0)
                    {
                        this._hs_probe(old_bk[i].key_hash, old_bk[i].key);
                    };
                    i = i + 1;
                };
                stdheap::ffree((u64)old_bk);
                return;
            };

            def set_add(byte* key) -> void
            {
                u64   hash = hm_hash_str(key);
                byte* pooled;
                if (this.count * 4 > this.cap * 3)
                {
                    this._hs_resize();
                };
                pooled = this._hs_pool_dup(key);
                if (pooled == (byte*)STDLIB_GVP)
                {
                    return;
                };
                this._hs_probe(hash, pooled);
                return;
            };

            def set_has(byte* key) -> bool
            {
                u64 hash = hm_hash_str(key),
                    mask = this.cap - 1,
                    idx  = hash & mask,
                    psl  = 0;
                HSBucket* slot;
                while (true)
                {
                    slot = this.buckets + idx;
                    if (slot.key_hash == 0)
                    {
                        return false;
                    };
                    if (slot.psl < psl)
                    {
                        return false;
                    };
                    if (slot.key_hash == hash)
                    {
                        if (hm_str_eq(slot.key, key))
                        {
                            return true;
                        };
                    };
                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return false;
            };

            // remove: backward-shift deletion. No alloc/free anywhere.
            // Keys remain in the pool (pool is not compacted on remove).
            def set_remove(byte* key) -> bool
            {
                u64 hash = hm_hash_str(key),
                    mask = this.cap - 1;
                u64 idx  = hash & mask,
                    psl  = 0,
                    cur, next;
                HSBucket* slot, nx, cr;
                while (true)
                {
                    slot = this.buckets + idx;
                    if (slot.key_hash == 0)
                    {
                        return false;
                    };
                    if (slot.psl < psl)
                    {
                        return false;
                    };
                    if (slot.key_hash == hash)
                    {
                        if (hm_str_eq(slot.key, key))
                        {
                            slot.key_hash = 0;
                            slot.key      = (byte*)0;
                            slot.psl      = 0;
                            this.count    = this.count - 1;
                            cur  = idx;
                            next = (idx + 1) & mask;
                            while (true)
                            {
                                nx = this.buckets + next;
                                if (nx.key_hash == 0 | nx.psl == 0)
                                {
                                    break;
                                };
                                cr = this.buckets + cur;
                                cr.key_hash = nx.key_hash;
                                cr.key      = nx.key;
                                cr.psl      = nx.psl - 1;
                                nx.key_hash = 0;
                                nx.key      = (byte*)0;
                                nx.psl      = 0;
                                cur  = next;
                                next = (next + 1) & mask;
                            };
                            return true;
                        };
                    };
                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return false;
            };

            def set_count() -> u64
            {
                return this.count;
            };

            def set_capacity() -> u64
            {
                return this.cap;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // HashSetInt  (u64 keys)
        // Robin-hood hash set for integer keys.
        // No string pool needed; __exit is a single ffree.
        //
        // Usage example:
        //   HashSetInt hsi((u64)16);
        //   hsi.seti_add((u64)42);
        //   bool found = hsi.seti_has((u64)42);
        //   hsi.seti_remove((u64)42);
        // ============================================================================

        struct HSIBucket
        {
            u64 key_hash, key, psl;
        };

        trait BaseSTDHashSetIntTraits
        {
            def _hsib_probe(u64 hash, u64 key) -> void,
                _hsib_resize()                 -> void,
                seti_add(u64 key)              -> void,
                seti_has(u64 key)              -> bool,
                seti_remove(u64 key)           -> bool,
                seti_count()                   -> u64,
                seti_capacity()                -> u64;
        };

        BaseSTDHashSetIntTraits
        object HashSetInt
        {
            HSIBucket* buckets;
            u64        count,
                       cap;

            def __init(u64 initial_cap) -> this
            {
                u64 c = 16, i;
                while (c < initial_cap)
                {
                    c = c * 2;
                };
                this.cap     = c;
                this.count   = 0;
                this.buckets = (HSIBucket*)stdheap::fmalloc(c * 24);
                while (i < c)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = 0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };
                return this;
            };

            def __exit() -> void
            {
                stdheap::ffree((u64)this.buckets);
                this.buckets = (HSIBucket*)STDLIB_GVP;
                return;
            };

            def __expr() -> HashSetInt*
            {
                return this;
            };

            // No alloc/free in this function.
            def _hsib_probe(u64 hash, u64 key) -> void
            {
                u64 mask = this.cap - 1;
                u64 idx  = hash & mask;
                HSIBucket ins, tmp;
                HSIBucket* slot;
                ins.key_hash = hash;
                ins.key      = key;
                ins.psl      = 0;
                while (true)
                {
                    slot = this.buckets + idx;
                    if (slot.key_hash == 0)
                    {
                        slot.key_hash = ins.key_hash;
                        slot.key      = ins.key;
                        slot.psl      = ins.psl;
                        this.count    = this.count + 1;
                        return;
                    };
                    if (slot.key_hash == ins.key_hash & slot.key == ins.key)
                    {
                        return;
                    };
                    if (slot.psl < ins.psl)
                    {
                        tmp.key_hash  = slot.key_hash;
                        tmp.key       = slot.key;
                        tmp.psl       = slot.psl;
                        slot.key_hash = ins.key_hash;
                        slot.key      = ins.key;
                        slot.psl      = ins.psl;
                        ins.key_hash  = tmp.key_hash;
                        ins.key       = tmp.key;
                        ins.psl       = tmp.psl;
                    };
                    idx     = (idx + 1) & mask;
                    ins.psl = ins.psl + 1;
                };
                return;
            };

            // One fmalloc before loops, one ffree after. No alloc in loops.
            def _hsib_resize() -> void
            {
                u64 old_cap       = this.cap;
                u64 new_cap       = old_cap * 2,
                    i;
                HSIBucket* old_bk = this.buckets;
                this.buckets      = (HSIBucket*)stdheap::fmalloc(new_cap * 24);
                this.cap          = new_cap;
                this.count        = 0;
                while (i < new_cap)
                {
                    this.buckets[i].key_hash = 0;
                    this.buckets[i].key      = 0;
                    this.buckets[i].psl      = 0;
                    i = i + 1;
                };
                i = 0;
                while (i < old_cap)
                {
                    if (old_bk[i].key_hash != 0)
                    {
                        this._hsib_probe(old_bk[i].key_hash, old_bk[i].key);
                    };
                    i = i + 1;
                };
                stdheap::ffree((u64)old_bk);
                return;
            };

            def seti_add(u64 key) -> void
            {
                u64 hash = hm_hash_u64(key);
                if (this.count * (u64)4 > this.cap * (u64)3)
                {
                    this._hsib_resize();
                };
                this._hsib_probe(hash, key);
                return;
            };

            def seti_has(u64 key) -> bool
            {
                u64 hash = hm_hash_u64(key),
                    mask = this.cap - 1;
                u64 idx  = hash & mask,
                    psl  = 0;
                HSIBucket* slot;
                while (true)
                {
                    slot = this.buckets + idx;
                    if (slot.key_hash == 0)
                    {
                        return false;
                    };
                    if (slot.psl < psl)
                    {
                        return false;
                    };
                    if (slot.key_hash == hash & slot.key == key)
                    {
                        return true;
                    };
                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return false;
            };

            def seti_remove(u64 key) -> bool
            {
                u64 hash = hm_hash_u64(key),
                    mask = this.cap - 1;
                u64 idx  = hash & mask,
                    psl  = 0,
                    cur, next;
                HSIBucket* slot, nx, cr;
                while (true)
                {
                    slot = this.buckets + idx;
                    if (slot.key_hash == 0)
                    {
                        return false;
                    };
                    if (slot.psl < psl)
                    {
                        return false;
                    };
                    if (slot.key_hash == hash & slot.key == key)
                    {
                        slot.key_hash = 0;
                        slot.key      = 0;
                        slot.psl      = 0;
                        this.count    = this.count - 1;
                        cur  = idx;
                        next = (idx + 1) & mask;
                        while (true)
                        {
                            nx = this.buckets + next;
                            if (nx.key_hash == 0 | nx.psl == 0)
                            {
                                break;
                            };
                            cr = this.buckets + cur;
                            cr.key_hash = nx.key_hash;
                            cr.key      = nx.key;
                            cr.psl      = nx.psl - 1;
                            nx.key_hash = 0;
                            nx.key      = 0;
                            nx.psl      = 0;
                            cur  = next;
                            next = (next + 1) & mask;
                        };
                        return true;
                    };
                    idx = (idx + 1) & mask;
                    psl = psl + 1;
                };
                return false;
            };

            def seti_count() -> u64
            {
                return this.count;
            };

            def seti_capacity() -> u64
            {
                return this.cap;
            };
        };
    };
};

namespace standard
{
    namespace collections
    {
        // ============================================================================
        // MinHeap  (priority queue, smallest value at top)
        // Binary min-heap backed by a flat Array of void* pointers.
        // A user-supplied comparator determines ordering.
        //
        // Comparator signature:  def my_cmp(void* a, void* b) -> int
        //   Return < 0 if a has higher priority (comes before b).
        //   Return   0 if equal.
        //   Return > 0 if b has higher priority.
        //
        // heap_push O(log n), heap_pop O(log n), heap_peek O(1).
        // The function pointer local is declared at function top, outside all loops.
        //
        // Usage example:
        //   def int_cmp(void* a, void* b) -> int { return *(int*)a - *(int*)b; };
        //   MinHeap h;
        //   h.__init(@int_cmp);
        //   int x = 3, y = 1;
        //   h.heap_push(@x);
        //   h.heap_push(@y);
        //   void* top = h.heap_pop(); // points to y (value 1)
        // ============================================================================

        trait BaseSTDMinHeapTraits
        {
            def heap_push(void* value) -> bool,
                heap_pop()             -> void*,
                heap_peek()            -> void*,
                heap_len()             -> size_t,
                heap_empty()           -> bool,
                heap_clear()           -> void;
        };

        BaseSTDMinHeapTraits
        object MinHeap
        {
            Array  elems;   // stores void* pointers, elem_size = 8
            void*  cmp_fn;  // comparator stored as void*

            def __init(void* cmp) -> this
            {
                this.elems.__init((size_t)8);
                this.cmp_fn = cmp;
                return this;
            };

            def __exit() -> void
            {
                this.elems.__exit();
                return;
            };

            def __expr() -> MinHeap*
            {
                return this;
            };

            // ----------------------------------------------------------------
            // heap_push(value) - insert and sift up.
            // fp declared at function top, outside the sift loop.
            // ----------------------------------------------------------------
            def heap_push(void* value) -> bool
            {
                // All locals at function top.
                def{}* cmp(void*, void*) -> int = this.cmp_fn;
                size_t i, parent;
                void** pslot, islot;
                void*  pval, ival, tmp;
                if (!this.elems.push(@value))
                {
                    return false;
                };
                i = this.elems.len - 1;
                while (i > 0)
                {
                    parent = (i - 1) / 2;
                    pslot  = (void**)this.elems.get(parent);
                    islot  = (void**)this.elems.get(i);
                    pval   = *pslot;
                    ival   = *islot;
                    if (cmp(pval, ival) <= 0)
                    {
                        break;
                    };
                    *pslot = ival;
                    *islot = pval;
                    i      = parent;
                };
                return true;
            };

            // ----------------------------------------------------------------
            // heap_pop() - remove and return minimum.
            // All fp locals and temporaries declared at function top.
            // ----------------------------------------------------------------
            def heap_pop() -> void*
            {
                // All locals at function top.
                def{}* cmp(void*, void*) -> int = this.cmp_fn;
                size_t n, i, lft, rgt, smallest;
                void** root_slot,
                       last_slot,
                       lslot,
                       rslot,
                       sslot,
                       islot;
                void*  res, tmp;
                n = this.elems.len;
                if (n == 0)
                {
                    return STDLIB_GVP;
                };
                root_slot        = (void**)this.elems.get(0);
                res              = *root_slot;
                last_slot        = (void**)this.elems.get(n - 1);
                *root_slot       = *last_slot;
                this.elems.len   = this.elems.len - 1;
                n                = this.elems.len;
                while (true)
                {
                    lft      = i * 2 + 1;
                    rgt      = i * 2 + 2;
                    smallest = i;
                    if (lft < n)
                    {
                        lslot = (void**)this.elems.get(lft);
                        sslot = (void**)this.elems.get(smallest);
                        if (cmp(*lslot, *sslot) < 0)
                        {
                            smallest = lft;
                        };
                    };
                    if (rgt < n)
                    {
                        rslot = (void**)this.elems.get(rgt);
                        sslot = (void**)this.elems.get(smallest);
                        if (cmp(*rslot, *sslot) < 0)
                        {
                            smallest = rgt;
                        };
                    };
                    if (smallest == i)
                    {
                        break;
                    };
                    islot    = (void**)this.elems.get(i);
                    sslot    = (void**)this.elems.get(smallest);
                    tmp      = *islot;
                    *islot   = *sslot;
                    *sslot   = tmp;
                    i        = smallest;
                };
                return res;
            };

            def heap_peek() -> void*
            {
                void** slot;
                if (this.elems.len == 0)
                {
                    return STDLIB_GVP;
                };
                slot = (void**)this.elems.get(0);
                return *slot;
            };

            def heap_len() -> size_t
            {
                return this.elems.len;
            };

            def heap_empty() -> bool
            {
                return this.elems.len == 0;
            };

            def heap_clear() -> void
            {
                this.elems.clear();
                return;
            };
        };
    };
};

#endif;
