// Author: Karac V. Thweatt

// json.fx - JSON parse, build, and serialize library.
//
// JSONNode      - tagged value node (null/bool/int/float/string/array/object)
// JSONArray     - growable array of void* node pointers
// JSONObject    - ordered key/value store with cached key lengths
// JSONParser    - arena-backed zero-copy recursive descent parser
// SerializeBuf / serialize_arena - arena-backed serializer
//
// All locals declared at function top. All variables zero-initialized.
// node_free() is used inside JSONNode.__exit() to avoid self-reference.
// Methods that return child nodes return void*; caller casts to JSONNode*.
// Zero-copy strings: use as_string_view() for parsed data; as_string() only
// valid for strings set via set_string() or set_string_arena().

#ifndef FLUX_STANDARD
#import "standard.fx";
#endif;

#ifndef FLUX_STANDARD_ALLOCATORS
#import "allocators.fx";
#endif;

#ifndef FLUX_JSON
#def FLUX_JSON 1;

namespace json
{
	const int JSON_NULL   = 0,
	          JSON_BOOL   = 1,
	          JSON_INT    = 2,
	          JSON_FLOAT  = 3,
	          JSON_STRING = 4,
	          JSON_ARRAY  = 5,
	          JSON_OBJECT = 6;

	// =========================================================================
	// JSONArray - growable void* array
	// =========================================================================

	object JSONArray
	{
		void*  buf;
		size_t len, cap;

		def __init() -> this
		{
			this.cap = 8;
			this.buf = (@)fmalloc(this.cap * 8);
			return this;
		};

		def __exit() -> void
		{
			switch ((u64)this.buf != 0)
			{
				case (1)
				{
					ffree((u64)this.buf);
					this.buf = (@)0;
				}
				default {};
			};
			return;
		};

		def __expr() -> u64
		{
			return (u64)this.buf;
		};

		def _grow() -> bool
		{
			void*  nb;
			size_t new_cap;
			new_cap = this.cap * 2;
			nb      = (@)fmalloc(new_cap * 8);
			switch ((u64)nb == 0)
			{
				case (1) { return false; }
				default {};
			};
			memcpy(nb, this.buf, this.cap * 8);
			ffree((u64)this.buf);
			this.buf = nb;
			this.cap = new_cap;
			return true;
		};

		// Arena-backed init: allocates buf from arena, no ffree needed.
		def _init_arena(standard::memory::allocators::stdarena::Arena* a) -> void
		{
			this.cap = 8;
			this.buf = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * 8);
			return;
		};

		// Arena-backed grow: old buf is abandoned in arena, new buf allocated.
		def _grow_arena(standard::memory::allocators::stdarena::Arena* a) -> bool
		{
			void*  nb;
			size_t new_cap;
			new_cap = this.cap * 2;
			nb      = (@)standard::memory::allocators::stdarena::alloc(a, new_cap * 8);
			switch ((u64)nb == 0)
			{
				case (1) { return false; }
				default {};
			};
			memcpy(nb, this.buf, this.cap * 8);
			this.buf = nb;
			this.cap = new_cap;
			return true;
		};

		def push_arena(void* node, standard::memory::allocators::stdarena::Arena* a) -> bool
		{
			void** slot;
			switch (this.len >= this.cap)
			{
				case (1)
				{
					switch (!this._grow_arena(a))
					{
						case (1) { return false; }
						default {};
					};
				}
				default {};
			};
			slot  = (void**)this.buf + this.len;
			*slot = node;
			this.len++;
			return true;
		};

		def push(void* node) -> bool
		{
			void** slot;
			switch (this.len >= this.cap)
			{
				case (1)
				{
					switch (!this._grow())
					{
						case (1) { return false; }
						default {};
					};
				}
				default {};
			};
			slot  = (void**)this.buf + this.len;
			*slot = node;
			this.len++;
			return true;
		};

		def get(size_t i) -> void*
		{
			void** slot;
			switch (i >= this.len)
			{
				case (1) { return (@)0; }
				default {};
			};
			slot = (void**)this.buf + i;
			return *slot;
		};
	};

	// =========================================================================
	// JSONObject - ordered key/value pairs, keys heap-copied
	// =========================================================================

	object JSONObject
	{
		void*  keys, vals, klens;
		size_t len, cap;

		def __init() -> this
		{
			this.cap   = 8;
			this.keys  = (@)fmalloc(this.cap * 8);
			this.vals  = (@)fmalloc(this.cap * 8);
			this.klens = (@)fmalloc(this.cap * (sizeof(size_t) / 8));
			return this;
		};

		def __exit() -> void
		{
			byte** ks;
			size_t i;
			switch ((u64)this.keys != 0)
			{
				case (1)
				{
					ks = (byte**)this.keys;
					do
					{
						switch (i < this.len)
						{
							case (1)
							{
								switch ((u64)ks[i] != 0)
								{
									case (1) { ffree((u64)ks[i]); }
									default {};
								};
								i++;
							}
							default { break; };
						};
					};
					ffree((u64)this.keys);
					this.keys = (@)0;
				}
				default {};
			};
			switch ((u64)this.vals != 0)
			{
				case (1)
				{
					ffree((u64)this.vals);
					this.vals = (@)0;
				}
				default {};
			};
			switch ((u64)this.klens != 0)
			{
				case (1)
				{
					ffree((u64)this.klens);
					this.klens = (@)0;
				}
				default {};
			};
			return;
		};

		def __expr() -> this
		{
			return this;
		};

		def _grow() -> bool
		{
			void*  nk, nv, nl;
			size_t new_cap;
			new_cap = this.cap * 2;
			nk      = (@)fmalloc(new_cap * 8);
			switch ((u64)nk == 0)
			{
				case (1) { return false; }
				default {};
			};
			nv = (@)fmalloc(new_cap * 8);
			switch ((u64)nv == 0)
			{
				case (1) { ffree((u64)nk); return false; }
				default {};
			};
			nl = (@)fmalloc(new_cap * (sizeof(size_t) / 8));
			switch ((u64)nl == 0)
			{
				case (1) { ffree((u64)nk); ffree((u64)nv); return false; }
				default {};
			};
			memcpy(nk, this.keys,  this.cap * 8);
			memcpy(nv, this.vals,  this.cap * 8);
			memcpy(nl, this.klens, this.cap * (sizeof(size_t) / 8));
			ffree((u64)this.keys);
			ffree((u64)this.vals);
			ffree((u64)this.klens);
			this.keys  = nk;
			this.vals  = nv;
			this.klens = nl;
			this.cap   = new_cap;
			return true;
		};

		// Arena-backed init: keys, vals, and klens slabs from arena.
		def _init_arena(standard::memory::allocators::stdarena::Arena* a) -> void
		{
			this.cap   = 8;
			this.keys  = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * 8);
			this.vals  = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * 8);
			this.klens = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * (sizeof(size_t) / 8));
			return;
		};

		// Arena-backed grow: old slabs abandoned in arena.
		def _grow_arena(standard::memory::allocators::stdarena::Arena* a) -> bool
		{
			void*  nk, nv, nl;
			size_t new_cap;
			new_cap = this.cap * 2;
			nk      = (@)standard::memory::allocators::stdarena::alloc(a, new_cap * 8);
			switch ((u64)nk == 0)
			{
				case (1) { return false; }
				default {};
			};
			nv = (@)standard::memory::allocators::stdarena::alloc(a, new_cap * 8);
			switch ((u64)nv == 0)
			{
				case (1) { return false; }
				default {};
			};
			nl = (@)standard::memory::allocators::stdarena::alloc(a, new_cap * (sizeof(size_t) / 8));
			switch ((u64)nl == 0)
			{
				case (1) { return false; }
				default {};
			};
			memcpy(nk, this.keys,  this.cap * 8);
			memcpy(nv, this.vals,  this.cap * 8);
			memcpy(nl, this.klens, this.cap * (sizeof(size_t) / 8));
			this.keys  = nk;
			this.vals  = nv;
			this.klens = nl;
			this.cap   = new_cap;
			return true;
		};

		// Arena-backed set: key is copied into arena memory, no ffree on key.
		// Duplicate key check uses stored klens — no strlen on existing keys.
		def arena_set(byte* key, void* val, standard::memory::allocators::stdarena::Arena* a) -> bool
		{
			byte**   ks;
			void**   vs;
			size_t*  kl_slab;
			byte*    kc;
			size_t   i, kl;
			int      j;
			bool     match;
			ks      = (byte**)this.keys;
			vs      = (void**)this.vals;
			kl_slab = (size_t*)this.klens;
			kl      = (size_t)standard::strings::strlen(key);
			do
			{
				switch (i < this.len)
				{
					case (1)
					{
						match = kl_slab[i] == kl;
						switch (match)
						{
							case (1)
							{
								j = 0;
								do
								{
									switch (j < (int)kl)
									{
										case (1)
										{
											switch (ks[i][j] != key[j])
											{
												case (1) { match = false; break; }
												default {};
											};
											j = j + 1;
										}
										default { break; };
									};
								};
							}
							default {};
						};
						switch (match)
						{
							case (1) { vs[i] = val; return true; }
							default {};
						};
						i++;
					}
					default { break; };
				};
			};
			switch (this.len >= this.cap)
			{
				case (1)
				{
					switch (!this._grow_arena(a))
					{
						case (1) { return false; }
						default {};
					};
					ks      = (byte**)this.keys;
					vs      = (void**)this.vals;
					kl_slab = (size_t*)this.klens;
				}
				default {};
			};
			kc = (byte*)standard::memory::allocators::stdarena::alloc(a, kl + (size_t)1);
			switch ((u64)kc == 0)
			{
				case (1) { return false; }
				default {};
			};
			j = 0;
			do
			{
				switch (j <= (int)kl)
				{
					case (1) { kc[j] = key[j]; j = j + 1; }
					default { break; };
				};
			};
			ks[this.len]      = kc;
			vs[this.len]      = val;
			kl_slab[this.len] = kl;
			this.len++;
			return true;
		};

		def set(byte* key, void* val) -> bool
		{
			byte**  ks;
			void**  vs;
			size_t* kl_slab;
			byte*   kc;
			size_t  i, kl;
			int     j;
			bool    match;
			ks      = (byte**)this.keys;
			vs      = (void**)this.vals;
			kl_slab = (size_t*)this.klens;
			kl      = (size_t)standard::strings::strlen(key);
			do
			{
				switch (i < this.len)
				{
					case (1)
					{
						match = kl_slab[i] == kl;
						switch (match)
						{
							case (1)
							{
								j = 0;
								do
								{
									switch (j < (int)kl)
									{
										case (1)
										{
											switch (ks[i][j] != key[j])
											{
												case (1) { match = false; break; }
												default {};
											};
											j = j + 1;
										}
										default { break; };
									};
								};
							}
							default {};
						};
						switch (match)
						{
							case (1) { vs[i] = val; return true; }
							default {};
						};
						i++;
					}
					default { break; };
				};
			};
			switch (this.len >= this.cap)
			{
				case (1)
				{
					switch (!this._grow())
					{
						case (1) { return false; }
						default {};
					};
					ks      = (byte**)this.keys;
					vs      = (void**)this.vals;
					kl_slab = (size_t*)this.klens;
				}
				default {};
			};
			kc = (byte*)fmalloc((u64)(kl + (size_t)1));
			switch ((u64)kc == 0)
			{
				case (1) { return false; }
				default {};
			};
			j = 0;
			do
			{
				switch (j <= (int)kl)
				{
					case (1) { kc[j] = key[j]; j = j + 1; }
					default { break; };
				};
			};
			ks[this.len]      = kc;
			vs[this.len]      = val;
			kl_slab[this.len] = kl;
			this.len++;
			return true;
		};

		def get(byte* key) -> void*
		{
			byte**  ks;
			void**  vs;
			size_t* kl_slab;
			size_t  i, kl;
			int     j;
			bool    match;
			ks      = (byte**)this.keys;
			vs      = (void**)this.vals;
			kl_slab = (size_t*)this.klens;
			kl      = (size_t)standard::strings::strlen(key);
			do
			{
				switch (i < this.len)
				{
					case (1)
					{
						match = kl_slab[i] == kl;
						switch (match)
						{
							case (1)
							{
								j = 0;
								do
								{
									switch (j < (int)kl)
									{
										case (1)
										{
											switch (ks[i][j] != key[j])
											{
												case (1) { match = false; break; }
												default {};
											};
											j = j + 1;
										}
										default { break; };
									};
								};
							}
							default {};
						};
						switch (match)
						{
							case (1) { return vs[i]; }
							default {};
						};
						i++;
					}
					default { break; };
				};
			};
			return (@)0;
		};

		def has(byte* key) -> bool
		{
			switch ((u64)this.get(key) != 0)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def key_at(size_t i) -> byte*
		{
			byte** ks;
			switch (i >= this.len)
			{
				case (1) { return (byte*)0; }
				default {};
			};
			ks = (byte**)this.keys;
			return ks[i];
		};

		def val_at(size_t i) -> void*
		{
			void** vs;
			switch (i >= this.len)
			{
				case (1) { return (@)0; }
				default {};
			};
			vs = (void**)this.vals;
			return vs[i];
		};
	};

	// node_free forward declaration — defined after JSONNode.
	def node_free(void* p) -> void;

	// =========================================================================
	// JSONNode
	// =========================================================================

	object JSONNode
	{
		int    type;
		bool   b, s_owned;
		i64    i;
		double f;
		byte*  s;
		int    slen;
		JSONArray  arr;
		JSONObject obj;

		def __init() -> this
		{
			return this;
		};

		def __exit() -> void
		{
			void*  child;
			size_t k, n;
			switch (this.type)
			{
				case (JSON_STRING)
				{
					switch (this.s_owned & (u64)this.s != 0)
					{
						case (1)
						{
							ffree((u64)this.s);
							this.s = (byte*)0;
						}
						default {};
					};
				}
				case (JSON_ARRAY)
				{
					n = this.arr.len;
					do
					{
						switch (k < n)
						{
							case (1)
							{
								child = this.arr.get(k);
								switch ((u64)child != 0)
								{
									case (1) { node_free(child); }
									default {};
								};
								k++;
							}
							default { break; };
						};
					};
					this.arr.__exit();
				}
				case (JSON_OBJECT)
				{
					n = this.obj.len;
					do
					{
						switch (k < n)
						{
							case (1)
							{
								child = this.obj.val_at(k);
								switch ((u64)child != 0)
								{
									case (1) { node_free(child); }
									default {};
								};
								k++;
							}
							default { break; };
						};
					};
					this.obj.__exit();
				}
				default {};
			};
			return;
		};

		def __expr() -> this
		{
			return this;
		};

		def is_null()   -> bool
		{
			switch (this.type == JSON_NULL)
			{
				case (1) { return true; }
				default { return false; };
			};
			return true;
		};
		def is_bool()   -> bool
		{
			switch (this.type == JSON_BOOL)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};
		def is_int()    -> bool
		{
			switch (this.type == JSON_INT)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};
		def is_float()  -> bool
		{
			switch (this.type == JSON_FLOAT)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};
		def is_string() -> bool
		{
			switch (this.type == JSON_STRING)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};
		def is_array()  -> bool
		{
			switch (this.type == JSON_ARRAY)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};
		def is_object() -> bool
		{
			switch (this.type == JSON_OBJECT)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def set_null() -> void
		{
			this.type = JSON_NULL;
			return;
		};

		def set_bool(bool v) -> void
		{
			this.type = JSON_BOOL;
			this.b    = v;
			return;
		};

		def set_int(i64 v) -> void
		{
			this.type = JSON_INT;
			this.i    = v;
			return;
		};

		def set_float(double v) -> void
		{
			this.type = JSON_FLOAT;
			this.f    = v;
			return;
		};

		def set_string(byte* src) -> bool
		{
			byte* kc;
			int   n, j;
			n  = standard::strings::strlen(src);
			kc = (byte*)fmalloc((u64)(n + 1));
			switch ((u64)kc == 0)
			{
				case (1) { return false; }
				default {};
			};
			j = 0;
			do
			{
				switch (j <= n)
				{
					case (1) { kc[j] = src[j]; j = j + 1; }
					default { break; };
				};
			};
			switch (this.s_owned & (u64)this.s != 0)
			{
				case (1) { ffree((u64)this.s); }
				default {};
			};
			this.s       = kc;
			this.slen    = n;
			this.s_owned = true;
			this.type    = JSON_STRING;
			return true;
		};

		def set_string_arena(byte* src, standard::memory::allocators::stdarena::Arena* a) -> bool
		{
			byte* kc;
			int   n, j;
			n  = standard::strings::strlen(src);
			kc = (byte*)standard::memory::allocators::stdarena::alloc(a, (size_t)(n + 1));
			switch ((u64)kc == 0)
			{
				case (1) { return false; }
				default {};
			};
			j = 0;
			do
			{
				switch (j <= n)
				{
					case (1) { kc[j] = src[j]; j = j + 1; }
					default { break; };
				};
			};
			// arena strings are not individually freed — skip the old free check
			this.s       = kc;
			this.slen    = n;
			this.s_owned = false;
			this.type    = JSON_STRING;
			return true;
		};

		def set_array() -> void
		{
			this.type = JSON_ARRAY;
			this.arr.__init();
			return;
		};

		def set_object() -> void
		{
			this.type = JSON_OBJECT;
			this.obj.__init();
			return;
		};

		def set_array_arena(standard::memory::allocators::stdarena::Arena* a) -> void
		{
			this.type = JSON_ARRAY;
			this.arr._init_arena(a);
			return;
		};

		def set_object_arena(standard::memory::allocators::stdarena::Arena* a) -> void
		{
			this.type = JSON_OBJECT;
			this.obj._init_arena(a);
			return;
		};

		def as_bool() -> bool
		{
			switch (this.type)
			{
				case (JSON_BOOL) { return this.b; }
				case (JSON_INT)  { return this.i != 0; }
				default { return false; };
			};
			return false;
		};

		def as_int() -> i64
		{
			switch (this.type)
			{
				case (JSON_INT)   { return this.i; }
				case (JSON_FLOAT) { return (i64)this.f; }
				case (JSON_BOOL)
				{
					switch (this.b)
					{
						case (1) { return 1; }
						default { return 0; };
					};
				}
				default { return 0; };
			};
			return 0;
		};

		def as_float() -> double
		{
			switch (this.type)
			{
				case (JSON_FLOAT) { return this.f; }
				case (JSON_INT)   { return (double)this.i; }
				default { return 0.0d; };
			};
			return 0.0d;
		};

		def as_string() -> byte*
		{
			switch (this.type == JSON_STRING)
			{
				case (1) { return this.s; }
				default { return (byte*)0; };
			};
			return (byte*)0;
		};

		// Returns pointer and byte length for both owned and zero-copy strings.
		// Use this in preference to as_string() when working with parsed data.
		def as_string_view(byte** out, int* out_len) -> bool
		{
			switch (this.type != JSON_STRING)
			{
				case (1) { return false; }
				default {};
			};
			*out     = this.s;
			*out_len = this.slen;
			return true;
		};

		def array_push_new() -> void*
		{
			void* child;
			switch (this.type != JSON_ARRAY)
			{
				case (1) { return (@)0; }
				default {};
			};
			child = (@)fmalloc(sizeof(JSONNode) / 8);
			switch ((u64)child == 0)
			{
				case (1) { return (@)0; }
				default {};
			};
			((JSONNode*)child).__init();
			switch (!this.arr.push(child))
			{
				case (1)
				{
					((JSONNode*)child).__exit();
					ffree((u64)child);
					return (@)0;
				}
				default {};
			};
			return child;
		};

		def array_push_new_arena(standard::memory::allocators::stdarena::Arena* a) -> void*
		{
			JSONNode* child;
			size_t    sz;
			switch (this.type != JSON_ARRAY)
			{
				case (1) { return (@)0; }
				default {};
			};
			sz    = sizeof(JSONNode) / sizeof(byte);
			child = (JSONNode*)standard::memory::allocators::stdarena::alloc(a, sz);
			switch ((u64)child == 0)
			{
				case (1) { return (@)0; }
				default {};
			};
			child.__init();
			switch (!this.arr.push_arena((void*)child, a))
			{
				case (1) { return (@)0; }
				default {};
			};
			return (void*)child;
		};

		def array_len() -> size_t
		{
			switch (this.type != JSON_ARRAY)
			{
				case (1) { return 0; }
				default { return this.arr.len; };
			};
			return 0;
		};

		def array_get(size_t i) -> void*
		{
			switch (this.type != JSON_ARRAY)
			{
				case (1) { return (@)0; }
				default { return this.arr.get(i); };
			};
			return (@)0;
		};

		def object_set_new(byte* key) -> void*
		{
			void* child;
			switch (this.type != JSON_OBJECT)
			{
				case (1) { return (@)0; }
				default {};
			};
			child = (@)fmalloc(sizeof(JSONNode) / 8);
			switch ((u64)child == 0)
			{
				case (1) { return (@)0; }
				default {};
			};
			((JSONNode*)child).__init();
			switch (!this.obj.set(key, child))
			{
				case (1)
				{
					((JSONNode*)child).__exit();
					ffree((u64)child);
					return (@)0;
				}
				default {};
			};
			return child;
		};

		def object_set_new_arena(byte* key, standard::memory::allocators::stdarena::Arena* a) -> void*
		{
			JSONNode* child;
			size_t    sz;
			switch (this.type != JSON_OBJECT)
			{
				case (1) { return (@)0; }
				default {};
			};
			sz    = sizeof(JSONNode) / sizeof(byte);
			child = (JSONNode*)standard::memory::allocators::stdarena::alloc(a, sz);
			switch ((u64)child == 0)
			{
				case (1) { return (@)0; }
				default {};
			};
			child.__init();
			switch (!this.obj.arena_set(key, (void*)child, a))
			{
				case (1) { return (@)0; }
				default {};
			};
			return (void*)child;
		};

		def object_get(byte* key) -> void*
		{
			switch (this.type != JSON_OBJECT)
			{
				case (1) { return (@)0; }
				default { return this.obj.get(key); };
			};
			return (@)0;
		};

		def object_has(byte* key) -> bool
		{
			switch (this.type != JSON_OBJECT)
			{
				case (1) { return false; }
				default { return this.obj.has(key); };
			};
			return false;
		};

		def object_len() -> size_t
		{
			switch (this.type != JSON_OBJECT)
			{
				case (1) { return 0; }
				default { return this.obj.len; };
			};
			return 0;
		};

		def object_key_at(size_t i) -> byte*
		{
			switch (this.type != JSON_OBJECT)
			{
				case (1) { return (byte*)0; }
				default { return this.obj.key_at(i); };
			};
			return (byte*)0;
		};

		def object_val_at(size_t i) -> void*
		{
			switch (this.type != JSON_OBJECT)
			{
				case (1) { return (@)0; }
				default { return this.obj.val_at(i); };
			};
			return (@)0;
		};
	};

	// node_free definition — now JSONNode is fully defined, safe to use.
	def node_free(void* p) -> void
	{
		JSONNode* n;
		n = (JSONNode*)p;
		n.__exit();
		ffree((u64)p);
		return;
	};

	// =========================================================================
	// JSONParser - arena-backed, zero-copy recursive descent parser
	//
	// Backed by standard::memory::allocators::stdarena::Arena.
	// One arena covers both JSONNode structs and escaped string data.
	// Escape-free strings and keys point directly into the source buffer —
	// no allocation, no copy. arena_destroy frees everything in O(chunks)
	// regardless of node count.
	// =========================================================================

	#def NODE_SLAB_SIZE 64;

	object JSONParser
	{
		byte*                                       src;
		int                                         pos, len, error;
		standard::memory::allocators::stdarena::Arena* arena;
		JSONNode*                                   node_slab;
		int                                         slab_remaining;

		// text_len must be the byte length of text (e.g. bytes_read from fread).
		// No strlen call -- caller provides the length.
		def __init(byte* text, int text_len, standard::memory::allocators::stdarena::Arena* a) -> this
		{
			this.src   = text;
			this.len   = text_len;
			this.arena = a;
			return this;
		};

		def __exit() -> void
		{
			return;
		};

		def __expr() -> this
		{
			return this;
		};

		def ok() -> bool
		{
			switch (this.error == 0)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def _skip_ws() -> void
		{
			char c;
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = (char)this.src[this.pos];
						switch (c)
						{
							case (32) {}  // space
							case (9) {}   // tab
							case (10) {}  // newline
							case (13) {}  // carriage return
							default { break; };
						};
						this.pos = this.pos + 1;
					}
					default { break; };
				};
			};
			return;
		};

		def _peek() -> char
		{
			switch (this.pos >= this.len)
			{
				case (1) { return '\x00'; }
				default { return (char)this.src[this.pos]; };
			};
			return '\x00';
		};

		def _adv() -> char
		{
			char c;
			switch (this.pos >= this.len)
			{
				case (1) { return '\x00'; }
				default {};
			};
			c        = (char)this.src[this.pos];
			this.pos = this.pos + 1;
			return c;
		};

		def _parse_string(JSONNode* node) -> bool
		{
			byte* s;
			int   start, slen, j;
			bool  has_escape;
			char  c;
			this._adv();
			start = this.pos;
			// Scan to find end and whether escapes are present.
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = (char)this.src[this.pos];
						switch (c)
						{
							case (34) { break; }  // "
							case (92)  // \
							{
								has_escape = true;
								this.pos = this.pos + 1;
							}
							default {};
						};
						this.pos = this.pos + 1;
						slen     = slen + 1;
					}
					default { break; };
				};
			};
			switch (this._peek() != '"')
			{
				case (1) { this.error = 1; return false; }
				default {};
			};
			this._adv();
			switch (!has_escape)
			{
				case (1)
				{
					// Zero-copy: point directly into source buffer.
					node.s       = @this.src[start];
					node.slen    = slen;
					node.s_owned = false;
					node.type    = JSON_STRING;
					return true;
				}
				default {};
			};
			// Has escapes: allocate into arena and decode.
			s = (byte*)standard::memory::allocators::stdarena::alloc(this.arena, (size_t)(slen + 1));
			switch ((u64)s == 0)
			{
				case (1) { this.error = 2; return false; }
				default {};
			};
			this.pos = start;
			j = 0;
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = (char)this.src[this.pos];
						switch (c)
						{
							case (34) { break; }  // "
							case (92)  // \
							{
								this.pos = this.pos + 1;
								c = (char)this.src[this.pos];
								switch (c)
								{
									case (34) { s[j] = '"';  }
									case (92) { s[j] = '\\'; }
									case (110) { s[j] = '\n'; }
									case (114) { s[j] = '\r'; }
									case (116) { s[j] = '\t'; }
									default   { s[j] = (byte)c; };
								};
							}
							default { s[j] = (byte)c; };
						};
						this.pos = this.pos + 1;
						j = j + 1;
					}
					default { break; };
				};
			};
			s[j]         = '\x00';
			this._adv();
			node.s       = s;
			node.slen    = j;
			node.s_owned = false;
			node.type    = JSON_STRING;
			return true;
		};

		def _parse_number(JSONNode* node) -> bool
		{
			bool   is_float, neg;
			i64    iv;
			double fv, fdiv;
			char   c;
			c = this._peek();
			switch (c == '-')
			{
				case (1) { neg = true; this._adv(); }
				default {};
			};
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = (char)this.src[this.pos];
						switch (c >= '0' & c <= '9')
						{
							case (1)
							{
								iv = iv * 10 + (c - '0');
								this.pos = this.pos + 1;
							}
							default { break; };
						};
					}
					default { break; };
				};
			};
			switch (this._peek() == '.')
			{
				case (1)
				{
					is_float = true;
					fdiv     = 1.0;
					fv       = (double)iv;
					this._adv();
					do
					{
						switch (this.pos < this.len)
						{
							case (1)
							{
								c = (char)this.src[this.pos];
								switch (c >= '0' & c <= '9')
								{
									case (1)
									{
										fdiv = fdiv * 10.0;
										fv   = fv + (double)(c - '0') / fdiv;
										this.pos = this.pos + 1;
									}
									default { break; };
								};
							}
							default { break; };
						};
					};
				}
				default {};
			};
			switch (is_float)
			{
				case (1) { node.set_float(neg ? -fv : fv); }
				default  { node.set_int(neg ? -iv : iv);   };
			};
			return true;
		};

		def _parse_value(JSONNode* node) -> bool;

		def _alloc_child() -> JSONNode*
		{
			JSONNode* child;
			size_t    sz;
			switch (this.slab_remaining == 0)
			{
				case (1)
				{
					sz             = (sizeof(JSONNode) / sizeof(byte)) * (size_t)NODE_SLAB_SIZE;
					this.node_slab = (JSONNode*)standard::memory::allocators::stdarena::alloc(this.arena, sz);
					switch ((u64)this.node_slab == 0)
					{
						case (1) { this.error = 2; return (JSONNode*)0; }
						default {};
					};
					this.slab_remaining = NODE_SLAB_SIZE;
				}
				default {};
			};
			child               = this.node_slab;
			this.node_slab      = (JSONNode*)((u64)this.node_slab + sizeof(JSONNode) / sizeof(byte));
			this.slab_remaining = this.slab_remaining - 1;
			// Zero-initialize — arena memory is uninitialized
			child.type      = JSON_NULL;
			child.b         = false;
			child.s_owned   = false;
			child.i         = 0;
			child.f         = 0.0;
			child.s         = (byte*)0;
			child.slen      = 0;
			child.arr.buf   = (@)0;
			child.arr.len   = 0;
			child.arr.cap   = 0;
			child.obj.keys  = (@)0;
			child.obj.vals  = (@)0;
			child.obj.klens = (@)0;
			child.obj.len   = 0;
			child.obj.cap   = 0;
			return child;
		};

		def _parse_array(JSONNode* node) -> bool
		{
			JSONNode* child;
			node.set_array_arena(this.arena);
			this._adv();
			this._skip_ws();
			switch (this._peek() == ']')
			{
				case (1) { this._adv(); return true; }
				default {};
			};
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						child = this._alloc_child();
						switch ((u64)child == 0)
						{
							case (1) { return false; }
							default {};
						};
						switch (!node.arr.push_arena((void*)child, this.arena))
						{
							case (1) { this.error = 2; return false; }
							default {};
						};
						switch (!this._parse_value(child))
						{
							case (1) { return false; }
							default {};
						};
						this._skip_ws();
						switch (this._peek() == ']')
						{
							case (1) { this._adv(); return true; }
							default {};
						};
						switch (this._peek() != ',')
						{
							case (1) { this.error = 1; return false; }
							default {};
						};
						this._adv();
						this._skip_ws();
					}
					default { break; };
				};
			};
			this.error = 1;
			return false;
		};

		def _parse_object(JSONNode* node) -> bool
		{
			JSONNode* child;
			byte*     kc;
			byte**    ks;
			void**    vs;
			size_t*   kl_slab;
			int       key_start, kl, j, resume_pos;
			bool      key_escape;
			char      c;
			node.set_object_arena(this.arena);
			this._adv();
			this._skip_ws();
			switch (this._peek() == '}')
			{
				case (1) { this._adv(); return true; }
				default {};
			};
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						this._skip_ws();
						switch (this._peek() != '"')
						{
							case (1) { this.error = 1; return false; }
							default {};
						};
						this._adv();
						key_start  = this.pos;
						kl         = 0;
						key_escape = false;
						do
						{
							switch (this.pos < this.len)
							{
								case (1)
								{
									c = (char)this.src[this.pos];
									switch (c)
									{
										case (34) { break; }  // "
										case (92)  // \
										{
											key_escape = true;
											this.pos = this.pos + 1;
										}
										default {};
									};
									this.pos = this.pos + 1;
									kl       = kl + 1;
								}
								default { break; };
							};
						};
						switch (this._peek() != '"')
						{
							case (1) { this.error = 1; return false; }
							default {};
						};
						this._adv();
						this._skip_ws();
						switch (this._peek() != ':')
						{
							case (1) { this.error = 1; return false; }
							default {};
						};
						this._adv();
						this._skip_ws();
						// Save position — value parse starts here.
						resume_pos = this.pos;
						child = this._alloc_child();
						switch ((u64)child == 0)
						{
							case (1) { return false; }
							default {};
						};
						switch (!key_escape)
						{
							case (1)
							{
								// Zero-copy key: point directly into source.
								kc = @this.src[key_start];
							}
							default
							{
								// Key has escapes: decode into arena buffer.
								kc = (byte*)standard::memory::allocators::stdarena::alloc(this.arena, (size_t)(kl + 1));
								switch ((u64)kc == 0)
								{
									case (1) { this.error = 2; return false; }
									default {};
								};
								this.pos = key_start;
								j = 0;
								do
								{
									switch (this.pos < this.len)
									{
										case (1)
										{
											c = (char)this.src[this.pos];
											switch (c)
											{
												case (34) { break; }  // "
												case (92)  // \
												{
													this.pos = this.pos + 1;
													c = (char)this.src[this.pos];
													switch (c)
													{
														case (34) { kc[j] = '"';  }
														case (92) { kc[j] = '\\'; }
														case (110) { kc[j] = '\n'; }
														case (114) { kc[j] = '\r'; }
														case (116) { kc[j] = '\t'; }
														default   { kc[j] = (byte)c; };
													};
												}
												default { kc[j] = (byte)c; };
											};
											this.pos = this.pos + 1;
											j = j + 1;
										}
										default { break; };
									};
								};
								kc[j] = '\x00';
								kl     = j;
								// Restore position to after ':' for value parse.
								this.pos = resume_pos;
							};
						};
						// Push directly into obj — arena-backed grow, no ffree
						switch (node.obj.len >= node.obj.cap)
						{
							case (1)
							{
								switch (!node.obj._grow_arena(this.arena))
								{
									case (1) { this.error = 2; return false; }
									default {};
								};
							}
							default {};
						};
						ks      = (byte**)node.obj.keys;
						vs      = (void**)node.obj.vals;
						kl_slab = (size_t*)node.obj.klens;
						ks[node.obj.len]      = kc;
						vs[node.obj.len]      = (void*)child;
						kl_slab[node.obj.len] = (size_t)kl;
						node.obj.len++;
						switch (!this._parse_value(child))
						{
							case (1) { return false; }
							default {};
						};
						this._skip_ws();
						switch (this._peek() == '}')
						{
							case (1) { this._adv(); return true; }
							default {};
						};
						switch (this._peek() != ',')
						{
							case (1) { this.error = 1; return false; }
							default {};
						};
						this._adv();
					}
					default { break; };
				};
			};
			this.error = 1;
			return false;
		};

		def _parse_value(JSONNode* node) -> bool
		{
			char c;
			this._skip_ws();
			c = this._peek();
			switch (c)
			{
				case (34) { return this._parse_string(node); }  // "
				case (91) { return this._parse_array(node);  }  // [
				case (123) { return this._parse_object(node); } // {
				case (116) { this.pos = this.pos + 4; node.set_bool(true);  return true; } // t
				case (102) { this.pos = this.pos + 5; node.set_bool(false); return true; } // f
				case (110) { this.pos = this.pos + 4; node.set_null();      return true; } // n
				case (45) {}   // -
				case (48) {}   // 0
				case (49) {}   // 1
				case (50) {}   // 2
				case (51) {}   // 3
				case (52) {}   // 4
				case (53) {}   // 5
				case (54) {}   // 6
				case (55) {}   // 7
				case (56) {}   // 8
				case (57) {}   // 9
				default { this.error = 1; return false; };
			};
			return this._parse_number(node);
		};

		def parse(JSONNode* node) -> bool
		{
			return this._parse_value(node);
		};
	};

	// =========================================================================
	// Serializer
	// =========================================================================

	def _wc(byte* buf, int pos, int cap, char c) -> int
	{
		switch (pos < cap - 1)
		{
			case (1) { buf[pos] = (byte)c; pos = pos + 1; }
			default {};
		};
		buf[pos] = '\x00';
		return pos;
	};

	def _ws(byte* buf, int pos, int cap, byte* src) -> int
	{
		int i;
		do
		{
			switch (src[i] != '\x00' & pos < cap - 1)
			{
				case (1)
				{
					buf[pos] = src[i];
					pos = pos + 1;
					i   = i + 1;
				}
				default { break; };
			};
		};
		buf[pos] = '\x00';
		return pos;
	};

	def _we(byte* buf, int pos, int cap, byte* src) -> int
	{
		int  i;
		char c;
		do
		{
			switch (src[i] != '\x00')
			{
				case (1)
				{
					c = (char)src[i];
					switch (c)
					{
						case (34) {}  // "
						case (92) {}  // \
						case (10) {}  // \n
						case (13) {}  // \r
						case (9) {}   // \t
						default
						{
							pos = _wc(buf, pos, cap, c);
							break;
						};
					};
					switch (c)
					{
						case (34)  // "
						{
							pos = _wc(buf, pos, cap, '\\');
							pos = _wc(buf, pos, cap, '"');
						}
						case (92)  // \
						{
							pos = _wc(buf, pos, cap, '\\');
							pos = _wc(buf, pos, cap, '\\');
						}
						case (10)  // \n
						{
							pos = _wc(buf, pos, cap, '\\');
							pos = _wc(buf, pos, cap, 'n');
						}
						case (13)  // \r
						{
							pos = _wc(buf, pos, cap, '\\');
							pos = _wc(buf, pos, cap, 'r');
						}
						case (9)   // \t
						{
							pos = _wc(buf, pos, cap, '\\');
							pos = _wc(buf, pos, cap, 't');
						}
						default {};
					};
					i = i + 1;
				}
				default { break; };
			};
		};
		return pos;
	};

	def serialize(JSONNode* node, byte* buf, int pos, int cap) -> int
	{
		byte[32]  num_buf;
		size_t    k, n;
		JSONNode* child;

		switch ((u64)node == 0)
		{
			case (1) { return _ws(buf, pos, cap, "null\0"); }
			default {};
		};

		switch (node.type)
		{
			case (JSON_NULL) { pos = _ws(buf, pos, cap, "null\0"); }
			case (JSON_BOOL)
			{
				switch (node.b)
				{
					case (1) { pos = _ws(buf, pos, cap, "true\0"); }
					default  { pos = _ws(buf, pos, cap, "false\0"); };
				};
			}
			case (JSON_INT)
			{
				standard::strings::i64str(node.i, @num_buf[0]);
				pos = _ws(buf, pos, cap, @num_buf[0]);
			}
			case (JSON_FLOAT)
			{
				standard::strings::dbl2str(node.f, @num_buf[0], 6);
				pos = _ws(buf, pos, cap, @num_buf[0]);
			}
			case (JSON_STRING)
			{
				pos = _wc(buf, pos, cap, '"');
				pos = _we(buf, pos, cap, node.s);
				pos = _wc(buf, pos, cap, '"');
			}
			case (JSON_ARRAY)
			{
				n   = node.arr.len;
				pos = _wc(buf, pos, cap, '[');
				do
				{
					switch (k < n)
					{
						case (1)
						{
							switch (k > 0)
							{
								case (1) { pos = _wc(buf, pos, cap, ','); }
								default {};
							};
							child = (JSONNode*)node.arr.get(k);
							pos   = serialize(child, buf, pos, cap);
							k++;
						}
						default { break; };
					};
				};
				pos = _wc(buf, pos, cap, ']');
			}
			case (JSON_OBJECT)
			{
				n   = node.obj.len;
				pos = _wc(buf, pos, cap, '{');
				do
				{
					switch (k < n)
					{
						case (1)
						{
							switch (k > 0)
							{
								case (1) { pos = _wc(buf, pos, cap, ','); }
								default {};
							};
							pos   = _wc(buf, pos, cap, '"');
							pos   = _we(buf, pos, cap, node.obj.key_at(k));
							pos   = _wc(buf, pos, cap, '"');
							pos   = _wc(buf, pos, cap, ':');
							child = (JSONNode*)node.obj.val_at(k);
							pos   = serialize(child, buf, pos, cap);
							k++;
						}
						default { break; };
					};
				};
				pos = _wc(buf, pos, cap, '}');
			}
			default {};
		};

		return pos;
	};

	// =========================================================================
	// Arena serializer - grows as needed, no caller pre-sizing required.
	//
	// serialize_arena writes node into an arena-backed buffer that doubles
	// when full. Returns a null-terminated byte* owned by the arena, or
	// null on OOM. The caller does not free the result — arena_destroy
	// releases it along with all other parse/build allocations.
	// =========================================================================

	struct SerializeBuf
	{
		byte*                                       buf;
		int                                         pos, cap;
		standard::memory::allocators::stdarena::Arena* arena;
	};

	def _sb_init(SerializeBuf* sb, standard::memory::allocators::stdarena::Arena* a, int init_cap) -> bool
	{
		sb.buf   = (byte*)standard::memory::allocators::stdarena::alloc(a, (size_t)init_cap);
		sb.cap   = init_cap;
		sb.arena = a;
		switch ((u64)sb.buf == 0)
		{
			case (1) { return false; }
			default { return true; };
		};
		return false;
	};

	def _sb_grow(SerializeBuf* sb) -> bool
	{
		byte*  nb;
		int    new_cap, i;
		new_cap = sb.cap * 2;
		nb      = (byte*)standard::memory::allocators::stdarena::alloc(sb.arena, (size_t)new_cap);
		switch ((u64)nb == 0)
		{
			case (1) { return false; }
			default {};
		};
		do
		{
			switch (i < sb.pos)
			{
				case (1) { nb[i] = sb.buf[i]; i = i + 1; }
				default { break; };
			};
		};
		sb.buf = nb;
		sb.cap = new_cap;
		return true;
	};

	def _sb_wc(SerializeBuf* sb, char c) -> bool
	{
		switch (sb.pos >= sb.cap - 1)
		{
			case (1)
			{
				switch (!_sb_grow(sb))
				{
					case (1) { return false; }
					default {};
				};
			}
			default {};
		};
		sb.buf[sb.pos] = (byte)c;
		sb.pos = sb.pos + 1;
		return true;
	};

	def _sb_ws(SerializeBuf* sb, byte* src) -> bool
	{
		int i;
		do
		{
			switch (src[i] != '\x00')
			{
				case (1)
				{
					switch (!_sb_wc(sb, (char)src[i]))
					{
						case (1) { return false; }
						default {};
					};
					i = i + 1;
				}
				default { break; };
			};
		};
		return true;
	};

	def _sb_we(SerializeBuf* sb, byte* src) -> bool
	{
		int  i;
		char c;
		do
		{
			switch (src[i] != '\x00')
			{
				case (1)
				{
					c = (char)src[i];
					switch (c)
					{
						case (34) {}  // "
						case (92) {}  // \
						case (10) {}  // \n
						case (13) {}  // \r
						case (9) {}   // \t
						default
						{
							switch (!_sb_wc(sb, c)) { case (1) { return false; } default {}; };
							break;
						};
					};
					switch (c)
					{
						case (34)  // "
						{
							switch (!_sb_wc(sb, '\\')) { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, '"'))  { case (1) { return false; } default {}; };
						}
						case (92)  // \
						{
							switch (!_sb_wc(sb, '\\')) { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, '\\')) { case (1) { return false; } default {}; };
						}
						case (10)  // \n
						{
							switch (!_sb_wc(sb, '\\')) { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, 'n'))  { case (1) { return false; } default {}; };
						}
						case (13)  // \r
						{
							switch (!_sb_wc(sb, '\\')) { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, 'r'))  { case (1) { return false; } default {}; };
						}
						case (9)   // \t
						{
							switch (!_sb_wc(sb, '\\')) { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, 't'))  { case (1) { return false; } default {}; };
						}
						default {};
					};
					i = i + 1;
				}
				default { break; };
			};
		};
		return true;
	};

	def _serialize_arena_node(JSONNode* node, SerializeBuf* sb) -> bool;

	def _serialize_arena_node(JSONNode* node, SerializeBuf* sb) -> bool
	{
		byte[32]  num_buf;
		size_t    k, n;
		JSONNode* child;

		switch ((u64)node == 0)
		{
			case (1) { return _sb_ws(sb, "null\0"); }
			default {};
		};

		switch (node.type)
		{
			case (JSON_NULL) { switch (!_sb_ws(sb, "null\0"))  { case (1) { return false; } default {}; }; }
			case (JSON_BOOL)
			{
				switch (node.b)
				{
					case (1) { switch (!_sb_ws(sb, "true\0"))  { case (1) { return false; } default {}; }; }
					default  { switch (!_sb_ws(sb, "false\0")) { case (1) { return false; } default {}; }; };
				};
			}
			case (JSON_INT)
			{
				standard::strings::i64str(node.i, @num_buf[0]);
				switch (!_sb_ws(sb, @num_buf[0])) { case (1) { return false; } default {}; };
			}
			case (JSON_FLOAT)
			{
				standard::strings::dbl2str(node.f, @num_buf[0], 6);
				switch (!_sb_ws(sb, @num_buf[0])) { case (1) { return false; } default {}; };
			}
			case (JSON_STRING)
			{
				switch (!_sb_wc(sb, '"'))         { case (1) { return false; } default {}; };
				switch (!_sb_we(sb, node.s))      { case (1) { return false; } default {}; };
				switch (!_sb_wc(sb, '"'))         { case (1) { return false; } default {}; };
			}
			case (JSON_ARRAY)
			{
				n = node.arr.len;
				switch (!_sb_wc(sb, '[')) { case (1) { return false; } default {}; };
				do
				{
					switch (k < n)
					{
						case (1)
						{
							switch (k > 0)
							{
								case (1) { switch (!_sb_wc(sb, ',')) { case (1) { return false; } default {}; }; }
								default {};
							};
							child = (JSONNode*)node.arr.get(k);
							switch (!_serialize_arena_node(child, sb))
							{
								case (1) { return false; }
								default {};
							};
							k++;
						}
						default { break; };
					};
				};
				switch (!_sb_wc(sb, ']')) { case (1) { return false; } default {}; };
			}
			case (JSON_OBJECT)
			{
				n = node.obj.len;
				switch (!_sb_wc(sb, '{')) { case (1) { return false; } default {}; };
				do
				{
					switch (k < n)
					{
						case (1)
						{
							switch (k > 0)
							{
								case (1) { switch (!_sb_wc(sb, ',')) { case (1) { return false; } default {}; }; }
								default {};
							};
							switch (!_sb_wc(sb, '"'))                    { case (1) { return false; } default {}; };
							switch (!_sb_we(sb, node.obj.key_at(k)))     { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, '"'))                    { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, ':'))                    { case (1) { return false; } default {}; };
							child = (JSONNode*)node.obj.val_at(k);
							switch (!_serialize_arena_node(child, sb))
							{
								case (1) { return false; }
								default {};
							};
							k++;
						}
						default { break; };
					};
				};
				switch (!_sb_wc(sb, '}')) { case (1) { return false; } default {}; };
			}
			default {};
		};

		return true;
	};

	// Serialize node into arena memory. Returns null-terminated string on
	// success, null on OOM. init_cap is the initial buffer guess in bytes;
	// 256 is a reasonable default for most documents.
	def serialize_arena(JSONNode* node, standard::memory::allocators::stdarena::Arena* a, int init_cap) -> byte*
	{
		SerializeBuf sb;
		switch (!_sb_init(@sb, a, init_cap))
		{
			case (1) { return (byte*)0; }
			default {};
		};
		switch (!_serialize_arena_node(node, @sb))
		{
			case (1) { return (byte*)0; }
			default {};
		};
		sb.buf[sb.pos] = '\x00';
		return sb.buf;
	};

};

#endif;