// Author: Karac V. Thweatt

// xml.fx - XML parse, build, and serialize library.
//
// XMLNode      - element node (element/text/comment/cdata/pi/doctype)
// XMLAttrList  - ordered attribute key/value store with cached key lengths
// XMLChildren  - growable array of void* node pointers
// XMLParser    - arena-backed zero-copy recursive descent parser
// SerializeBuf / serialize_arena - arena-backed serializer
//
// All locals declared at function top. All variables zero-initialized.
// xml_node_free() is used inside XMLNode.__exit() to avoid self-reference.
// Methods that return child nodes return void*; caller casts to XMLNode*.
// Zero-copy strings: tag names, attribute names, and text content without
// escapes point directly into the source buffer. Escaped content is
// decoded into arena memory.

#ifndef FLUX_STANDARD
#import "standard.fx";
#endif;

#ifndef FLUX_STANDARD_ALLOCATORS
#import "allocators.fx";
#endif;

#ifndef FLUX_XML
#def FLUX_XML 1;

namespace xml
{
	const int XML_ELEMENT = 0,
	          XML_TEXT    = 1,
	          XML_COMMENT = 2,
	          XML_CDATA   = 3,
	          XML_PI      = 4,
	          XML_DOCTYPE = 5;

	// =========================================================================
	// XMLChildren - growable void* array of child node pointers
	// =========================================================================

	object XMLChildren
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

		def __expr() -> this
		{
			return this;
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

		// Arena-backed init: buf from arena, no ffree needed.
		def _init_arena(standard::memory::allocators::stdarena::Arena* a) -> void
		{
			this.cap = 8;
			this.buf = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * 8);
			return;
		};

		// Arena-backed grow: old buf abandoned in arena, new buf allocated.
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
	// XMLAttrList - ordered attribute key/value pairs
	// =========================================================================

	object XMLAttrList
	{
		void*  keys, vals, klens, vlens;
		size_t len, cap;

		def __init() -> this
		{
			this.cap   = 8;
			this.keys  = (@)fmalloc(this.cap * 8);
			this.vals  = (@)fmalloc(this.cap * 8);
			this.klens = (@)fmalloc(this.cap * (sizeof(size_t) / 8));
			this.vlens = (@)fmalloc(this.cap * (sizeof(size_t) / 8));
			return this;
		};

		def __exit() -> void
		{
			byte** ks;
			byte** vs;
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
					vs = (byte**)this.vals;
					i  = 0;
					do
					{
						switch (i < this.len)
						{
							case (1)
							{
								switch ((u64)vs[i] != 0)
								{
									case (1) { ffree((u64)vs[i]); }
									default {};
								};
								i++;
							}
							default { break; };
						};
					};
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
			switch ((u64)this.vlens != 0)
			{
				case (1)
				{
					ffree((u64)this.vlens);
					this.vlens = (@)0;
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
			void*  nk, nv, nl, nvl;
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
			nvl = (@)fmalloc(new_cap * (sizeof(size_t) / 8));
			switch ((u64)nvl == 0)
			{
				case (1) { ffree((u64)nk); ffree((u64)nv); ffree((u64)nl); return false; }
				default {};
			};
			memcpy(nk,  this.keys,  this.cap * 8);
			memcpy(nv,  this.vals,  this.cap * 8);
			memcpy(nl,  this.klens, this.cap * (sizeof(size_t) / 8));
			memcpy(nvl, this.vlens, this.cap * (sizeof(size_t) / 8));
			ffree((u64)this.keys);
			ffree((u64)this.vals);
			ffree((u64)this.klens);
			ffree((u64)this.vlens);
			this.keys  = nk;
			this.vals  = nv;
			this.klens = nl;
			this.vlens = nvl;
			this.cap   = new_cap;
			return true;
		};

		// Arena-backed init: all slabs from arena.
		def _init_arena(standard::memory::allocators::stdarena::Arena* a) -> void
		{
			this.cap   = 8;
			this.keys  = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * 8);
			this.vals  = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * 8);
			this.klens = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * (sizeof(size_t) / 8));
			this.vlens = (@)standard::memory::allocators::stdarena::alloc(a, this.cap * (sizeof(size_t) / 8));
			return;
		};

		// Arena-backed grow: old slabs abandoned in arena.
		def _grow_arena(standard::memory::allocators::stdarena::Arena* a) -> bool
		{
			void*  nk, nv, nl, nvl;
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
			nvl = (@)standard::memory::allocators::stdarena::alloc(a, new_cap * (sizeof(size_t) / 8));
			switch ((u64)nvl == 0)
			{
				case (1) { return false; }
				default {};
			};
			memcpy(nk,  this.keys,  this.cap * 8);
			memcpy(nv,  this.vals,  this.cap * 8);
			memcpy(nl,  this.klens, this.cap * (sizeof(size_t) / 8));
			memcpy(nvl, this.vlens, this.cap * (sizeof(size_t) / 8));
			this.keys  = nk;
			this.vals  = nv;
			this.klens = nl;
			this.vlens = nvl;
			this.cap   = new_cap;
			return true;
		};

		// Arena-backed set: key and value copied into arena memory.
		// Duplicate key check uses stored klens — no strlen on existing keys.
		def arena_set(byte* key, byte* val, int vlen, standard::memory::allocators::stdarena::Arena* a) -> bool
		{
			byte**  ks;
			byte**  vs;
			size_t* kl_slab;
			size_t* vl_slab;
			byte*   kc;
			byte*   vc;
			size_t  i, kl;
			int     j;
			bool    match;
			ks      = (byte**)this.keys;
			vs      = (byte**)this.vals;
			kl_slab = (size_t*)this.klens;
			vl_slab = (size_t*)this.vlens;
			kl      = (size_t)standard::strings::strlen(key);
			// Check for duplicate key — update value in place.
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
							case (1)
							{
								// Replace value in arena — old abandoned.
								vc = (byte*)standard::memory::allocators::stdarena::alloc(a, (size_t)(vlen + 1));
								switch ((u64)vc == 0)
								{
									case (1) { return false; }
									default {};
								};
								j = 0;
								do
								{
									switch (j <= vlen)
									{
										case (1) { vc[j] = val[j]; j = j + 1; }
										default { break; };
									};
								};
								vs[i]      = vc;
								vl_slab[i] = (size_t)vlen;
								return true;
							}
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
					vs      = (byte**)this.vals;
					kl_slab = (size_t*)this.klens;
					vl_slab = (size_t*)this.vlens;
				}
				default {};
			};
			kc = (byte*)standard::memory::allocators::stdarena::alloc(a, kl + (size_t)1);
			switch ((u64)kc == 0)
			{
				case (1) { return false; }
				default {};
			};
			vc = (byte*)standard::memory::allocators::stdarena::alloc(a, (size_t)(vlen + 1));
			switch ((u64)vc == 0)
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
			j = 0;
			do
			{
				switch (j <= vlen)
				{
					case (1) { vc[j] = val[j]; j = j + 1; }
					default { break; };
				};
			};
			ks[this.len]      = kc;
			vs[this.len]      = vc;
			kl_slab[this.len] = kl;
			vl_slab[this.len] = (size_t)vlen;
			this.len++;
			return true;
		};

		def get(byte* key) -> byte*
		{
			byte**  ks;
			byte**  vs;
			size_t* kl_slab;
			size_t  i, kl;
			int     j;
			bool    match;
			ks      = (byte**)this.keys;
			vs      = (byte**)this.vals;
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
			return (byte*)0;
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

		def val_at(size_t i) -> byte*
		{
			byte** vs;
			switch (i >= this.len)
			{
				case (1) { return (byte*)0; }
				default {};
			};
			vs = (byte**)this.vals;
			return vs[i];
		};

		def val_len_at(size_t i) -> size_t
		{
			size_t* vl_slab;
			switch (i >= this.len)
			{
				case (1) { return 0; }
				default {};
			};
			vl_slab = (size_t*)this.vlens;
			return vl_slab[i];
		};
	};

	// xml_node_free forward declaration — defined after XMLNode.
	def xml_node_free(void* p) -> void;

	// =========================================================================
	// XMLNode
	// =========================================================================

	object XMLNode
	{
		int         type;
		byte*       tag, text;
		int         tag_len, text_len;
		bool        self_closing;
		XMLAttrList attrs;
		XMLChildren children;

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
				case (XML_ELEMENT)
				{
					n = this.children.len;
					do
					{
						switch (k < n)
						{
							case (1)
							{
								child = this.children.get(k);
								switch ((u64)child != 0)
								{
									case (1) { xml_node_free(child); }
									default {};
								};
								k++;
							}
							default { break; };
						};
					};
					this.children.__exit();
					this.attrs.__exit();
				}
				default {};
			};
			return;
		};

		def __expr() -> this
		{
			return this;
		};

		def is_element() -> bool
		{
			switch (this.type == XML_ELEMENT)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def is_text() -> bool
		{
			switch (this.type == XML_TEXT)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def is_comment() -> bool
		{
			switch (this.type == XML_COMMENT)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def is_cdata() -> bool
		{
			switch (this.type == XML_CDATA)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def is_pi() -> bool
		{
			switch (this.type == XML_PI)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def is_doctype() -> bool
		{
			switch (this.type == XML_DOCTYPE)
			{
				case (1) { return true; }
				default { return false; };
			};
			return false;
		};

		def attr_get(byte* key) -> byte*
		{
			switch (this.type != XML_ELEMENT)
			{
				case (1) { return (byte*)0; }
				default { return this.attrs.get(key); };
			};
			return (byte*)0;
		};

		def attr_has(byte* key) -> bool
		{
			switch (this.type != XML_ELEMENT)
			{
				case (1) { return false; }
				default { return this.attrs.has(key); };
			};
			return false;
		};

		def attr_count() -> size_t
		{
			switch (this.type != XML_ELEMENT)
			{
				case (1) { return 0; }
				default { return this.attrs.len; };
			};
			return 0;
		};

		def child_count() -> size_t
		{
			switch (this.type != XML_ELEMENT)
			{
				case (1) { return 0; }
				default { return this.children.len; };
			};
			return 0;
		};

		def child_get(size_t i) -> void*
		{
			switch (this.type != XML_ELEMENT)
			{
				case (1) { return (@)0; }
				default { return this.children.get(i); };
			};
			return (@)0;
		};

		// Returns first child element whose tag matches key. Returns null if none.
		def child_by_tag(byte* key) -> void*
		{
			XMLNode* child;
			size_t   i, n, kl, cl;
			int      j;
			bool     match;
			switch (this.type != XML_ELEMENT)
			{
				case (1) { return (@)0; }
				default {};
			};
			n  = this.children.len;
			kl = (size_t)standard::strings::strlen(key);
			do
			{
				switch (i < n)
				{
					case (1)
					{
						child = (XMLNode*)this.children.get(i);
						switch ((u64)child != 0 & child.type == XML_ELEMENT)
						{
							case (1)
							{
								cl    = (size_t)child.tag_len;
								match = cl == kl;
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
													switch (child.tag[j] != key[j])
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
									case (1) { return (void*)child; }
									default {};
								};
							}
							default {};
						};
						i++;
					}
					default { break; };
				};
			};
			return (@)0;
		};
	};

	// xml_node_free definition — XMLNode fully defined, safe to use.
	def xml_node_free(void* p) -> void
	{
		XMLNode* n;
		n = (XMLNode*)p;
		n.__exit();
		ffree((u64)p);
		return;
	};

	// =========================================================================
	// XMLParser - arena-backed, zero-copy recursive descent parser
	//
	// Backed by standard::memory::allocators::stdarena::Arena.
	// One arena covers all XMLNode structs and decoded string data.
	// Escape-free names and text content point directly into source buffer —
	// no allocation, no copy. arena_destroy frees everything in O(chunks).
	//
	// Supports: elements, attributes, text, comments, CDATA, PI, DOCTYPE.
	// Does not support: namespaces (ns prefix preserved as part of name),
	// DTD validation, or entity expansion beyond &amp; &lt; &gt; &apos; &quot;
	// =========================================================================

	#def XML_NODE_SLAB_SIZE 64;

	object XMLParser
	{
		byte*                                       src;
		int                                         pos, len, error;
		standard::memory::allocators::stdarena::Arena* arena;
		XMLNode*                                    node_slab;
		int                                         slab_remaining;

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
							case (32) {}   // space
							case (9) {}    // tab
							case (10) {}   // newline
							case (13) {}   // carriage return
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

		// Match a literal string at current pos. Advances past it on match.
		def _match_lit(byte* lit, int lit_len) -> bool
		{
			int i;
			switch (this.pos + lit_len > this.len)
			{
				case (1) { return false; }
				default {};
			};
			do
			{
				switch (i < lit_len)
				{
					case (1)
					{
						switch (this.src[this.pos + i] != lit[i])
						{
							case (1) { return false; }
							default {};
						};
						i = i + 1;
					}
					default { break; };
				};
			};
			this.pos = this.pos + lit_len;
			return true;
		};

		// Check if char is valid XML name-start char (ASCII subset).
		def _is_name_start(char c) -> bool
		{
			switch (c >= 'a' & c <= 'z') { case (1) { return true; } default {}; };
			switch (c >= 'A' & c <= 'Z') { case (1) { return true; } default {}; };
			switch (c == '_' | c == ':') { case (1) { return true; } default {}; };
			return false;
		};

		// Check if char is valid XML name continuation char (ASCII subset).
		def _is_name_char(char c) -> bool
		{
			switch (c >= 'a' & c <= 'z') { case (1) { return true; } default {}; };
			switch (c >= 'A' & c <= 'Z') { case (1) { return true; } default {}; };
			switch (c >= '0' & c <= '9') { case (1) { return true; } default {}; };
			switch (c == '_' | c == ':' | c == '-' | c == '.') { case (1) { return true; } default {}; };
			return false;
		};

		// Read a name (tag or attr name) from current pos.
		// Zero-copy: sets *out to point into src, sets *out_len.
		def _read_name(byte** out, int* out_len) -> bool
		{
			int start;
			switch (!this._is_name_start(this._peek()))
			{
				case (1) { this.error = 1; return false; }
				default {};
			};
			start = this.pos;
			do
			{
				switch (this.pos < this.len & this._is_name_char((char)this.src[this.pos]))
				{
					case (1) { this.pos = this.pos + 1; }
					default { break; };
				};
			};
			*out     = @this.src[start];
			*out_len = this.pos - start;
			return true;
		};

		// Decode XML entity at current pos into a byte. Advances pos past entity.
		// Returns byte written, or '?' on unknown entity.
		def _decode_entity() -> byte
		{
			// pos is currently on '&'. Advance past it.
			this._adv();
			switch (this._match_lit("amp;\0", 4))  { case (1) { return '&';  } default {}; };
			switch (this._match_lit("lt;\0", 3))   { case (1) { return '<';  } default {}; };
			switch (this._match_lit("gt;\0", 3))   { case (1) { return '>';  } default {}; };
			switch (this._match_lit("quot;\0", 5)) { case (1) { return '"';  } default {}; };
			switch (this._match_lit("apos;\0", 5)) { case (1) { return '\''; } default {}; };
			// Unknown or numeric entity: skip to ';' and emit '?'
			do
			{
				switch (this.pos < this.len & (char)this.src[this.pos] != ';')
				{
					case (1) { this.pos = this.pos + 1; }
					default { break; };
				};
			};
			switch ((char)this.src[this.pos] == ';')
			{
				case (1) { this.pos = this.pos + 1; }
				default {};
			};
			return '?';
		};

		// Parse an attribute value enclosed in " or '.
		// Zero-copy when no entities present; arena-decoded otherwise.
		// Sets *out and *out_len. Returns false on error.
		def _parse_attr_value(byte** out, int* out_len) -> bool
		{
			byte* s;
			int   start, slen, j;
			bool  has_entity;
			char  delim, c;
			delim = this._adv();
			switch (delim != '"' & delim != '\'')
			{
				case (1) { this.error = 1; return false; }
				default {};
			};
			start = this.pos;
			// Scan to find end and whether entities are present.
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = (char)this.src[this.pos];
						switch (c == (char)delim) { case (1) { break; } default {}; };
						switch (c == '&') { case (1) { has_entity = true; } default {}; };
						this.pos = this.pos + 1;
						slen     = slen + 1;
					}
					default { break; };
				};
			};
			switch ((char)this.src[this.pos] != (char)delim)
			{
				case (1) { this.error = 1; return false; }
				default {};
			};
			this._adv();
			switch (!has_entity)
			{
				case (1)
				{
					// Zero-copy: point directly into source.
					*out     = @this.src[start];
					*out_len = slen;
					return true;
				}
				default {};
			};
			// Has entities: decode into arena.
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
						switch (c == (char)delim) { case (1) { break; } default {}; };
						switch (c == '&')
						{
							case (1)
							{
								s[j] = this._decode_entity();
								j    = j + 1;
							}
							default
							{
								s[j]     = (byte)c;
								j        = j + 1;
								this.pos = this.pos + 1;
							};
						};
					}
					default { break; };
				};
			};
			s[j]     = '\x00';
			this._adv();  // closing delim
			*out     = s;
			*out_len = j;
			return true;
		};

		def _alloc_node() -> XMLNode*
		{
			XMLNode* child;
			size_t   sz;
			switch (this.slab_remaining == 0)
			{
				case (1)
				{
					sz             = (sizeof(XMLNode) / sizeof(byte)) * (size_t)XML_NODE_SLAB_SIZE;
					this.node_slab = (XMLNode*)standard::memory::allocators::stdarena::alloc(this.arena, sz);
					switch ((u64)this.node_slab == 0)
					{
						case (1) { this.error = 2; return (XMLNode*)0; }
						default {};
					};
					this.slab_remaining = XML_NODE_SLAB_SIZE;
				}
				default {};
			};
			child               = this.node_slab;
			this.node_slab      = (XMLNode*)((u64)this.node_slab + sizeof(XMLNode) / sizeof(byte));
			this.slab_remaining = this.slab_remaining - 1;
			// Zero-initialize — arena memory is uninitialized.
			child.type          = XML_ELEMENT;
			child.tag           = (byte*)0;
			child.text          = (byte*)0;
			child.tag_len       = 0;
			child.text_len      = 0;
			child.self_closing  = false;
			child.attrs.keys    = (@)0;
			child.attrs.vals    = (@)0;
			child.attrs.klens   = (@)0;
			child.attrs.vlens   = (@)0;
			child.attrs.len     = 0;
			child.attrs.cap     = 0;
			child.children.buf  = (@)0;
			child.children.len  = 0;
			child.children.cap  = 0;
			return child;
		};

		// Parse text content between tags.
		// Zero-copy when no entities; arena-decoded otherwise.
		def _parse_text(XMLNode* node) -> bool
		{
			byte* s;
			int   start, slen, j;
			bool  has_entity;
			char  c;
			node.type = XML_TEXT;
			start     = this.pos;
			// Scan to '<' to find extent and detect entities.
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = (char)this.src[this.pos];
						switch (c == '<') { case (1) { break; } default {}; };
						switch (c == '&') { case (1) { has_entity = true; } default {}; };
						this.pos = this.pos + 1;
						slen     = slen + 1;
					}
					default { break; };
				};
			};
			switch (!has_entity)
			{
				case (1)
				{
					node.text     = @this.src[start];
					node.text_len = slen;
					return true;
				}
				default {};
			};
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
						switch (c == '<') { case (1) { break; } default {}; };
						switch (c == '&')
						{
							case (1)
							{
								s[j] = this._decode_entity();
								j    = j + 1;
							}
							default
							{
								s[j]     = (byte)c;
								j        = j + 1;
								this.pos = this.pos + 1;
							};
						};
					}
					default { break; };
				};
			};
			s[j]         = '\x00';
			node.text     = s;
			node.text_len = j;
			return true;
		};

		// Parse <!-- ... --> comment. pos is after '<!--'.
		def _parse_comment(XMLNode* node) -> bool
		{
			int start, slen;
			node.type = XML_COMMENT;
			start     = this.pos;
			// Scan to '-->'
			do
			{
				switch (this.pos + 2 < this.len)
				{
					case (1)
					{
						switch (this.src[this.pos]     == '-' &
						        this.src[this.pos + 1] == '-' &
						        this.src[this.pos + 2] == '>')
						{
							case (1) { break; }
							default
							{
								this.pos = this.pos + 1;
								slen     = slen + 1;
							};
						};
					}
					default { this.error = 1; return false; };
				};
			};
			node.text     = @this.src[start];
			node.text_len = slen;
			this.pos      = this.pos + 3;  // skip '-->'
			return true;
		};

		// Parse <![CDATA[ ... ]]> section. pos is after '<![CDATA['.
		def _parse_cdata(XMLNode* node) -> bool
		{
			int start, slen;
			node.type = XML_CDATA;
			start     = this.pos;
			// Scan to ']]>'
			do
			{
				switch (this.pos + 2 < this.len)
				{
					case (1)
					{
						switch (this.src[this.pos]     == ']' &
						        this.src[this.pos + 1] == ']' &
						        this.src[this.pos + 2] == '>')
						{
							case (1) { break; }
							default
							{
								this.pos = this.pos + 1;
								slen     = slen + 1;
							};
						};
					}
					default { this.error = 1; return false; };
				};
			};
			node.text     = @this.src[start];
			node.text_len = slen;
			this.pos      = this.pos + 3;  // skip ']]>'
			return true;
		};

		// Parse <?...?> processing instruction. pos is after '<?'.
		def _parse_pi(XMLNode* node) -> bool
		{
			int start, slen;
			node.type = XML_PI;
			start     = this.pos;
			// Scan to '?>'
			do
			{
				switch (this.pos + 1 < this.len)
				{
					case (1)
					{
						switch (this.src[this.pos]     == '?' &
						        this.src[this.pos + 1] == '>')
						{
							case (1) { break; }
							default
							{
								this.pos = this.pos + 1;
								slen     = slen + 1;
							};
						};
					}
					default { this.error = 1; return false; };
				};
			};
			node.text     = @this.src[start];
			node.text_len = slen;
			this.pos      = this.pos + 2;  // skip '?>'
			return true;
		};

		// Parse <!DOCTYPE ...>. pos is after '<!DOCTYPE'.
		def _parse_doctype(XMLNode* node) -> bool
		{
			int   start, slen, depth;
			char  c;
			node.type = XML_DOCTYPE;
			this._skip_ws();
			start = this.pos;
			// Scan to matching '>' accounting for nested '[' ']'
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = (char)this.src[this.pos];
						switch (c == '[') { case (1) { depth = depth + 1; } default {}; };
						switch (c == ']') { case (1) { depth = depth - 1; } default {}; };
						switch (c == '>' & depth == 0) { case (1) { break; } default {}; };
						this.pos = this.pos + 1;
						slen     = slen + 1;
					}
					default { this.error = 1; return false; };
				};
			};
			node.text     = @this.src[start];
			node.text_len = slen;
			this.pos      = this.pos + 1;  // skip '>'
			return true;
		};

		// Parse an opening or self-closing element tag.
		// pos is after the initial '<'.
		def _parse_element(XMLNode* node) -> bool
		{
			XMLNode* child;
			byte*    attr_key, attr_val, close_tag;
			int      attr_klen, attr_vlen, close_len;
			char     c;
			node.type = XML_ELEMENT;
			// Read tag name.
			switch (!this._read_name(@node.tag, @node.tag_len))
			{
				case (1) { return false; }
				default {};
			};
			// Initialize attr list and children for this element.
			node.attrs._init_arena(this.arena);
			node.children._init_arena(this.arena);
			// Parse attributes.
			do
			{
				this._skip_ws();
				c = this._peek();
				switch (c == '/' | c == '>')
				{
					case (1) { break; }
					default {};
				};
				switch (c == '\x00')
				{
					case (1) { this.error = 1; return false; }
					default {};
				};
				// Read attr name.
				switch (!this._read_name(@attr_key, @attr_klen))
				{
					case (1) { return false; }
					default {};
				};
				this._skip_ws();
				switch (this._peek() != '=')
				{
					case (1) { this.error = 1; return false; }
					default {};
				};
				this._adv();
				this._skip_ws();
				// Read attr value.
				switch (!this._parse_attr_value(@attr_val, @attr_vlen))
				{
					case (1) { return false; }
					default {};
				};
				// Store into attr list.
				switch (!node.attrs.arena_set(attr_key, attr_val, attr_vlen, this.arena))
				{
					case (1) { this.error = 2; return false; }
					default {};
				};
			};
			// Check for self-closing '/>'
			switch (this._peek() == '/')
			{
				case (1)
				{
					this._adv();
					switch (this._peek() != '>')
					{
						case (1) { this.error = 1; return false; }
						default {};
					};
					this._adv();
					node.self_closing = true;
					return true;
				}
				default {};
			};
			// Consume '>'
			switch (this._peek() != '>')
			{
				case (1) { this.error = 1; return false; }
				default {};
			};
			this._adv();
			// Parse children until matching close tag.
			do
			{
				switch (this.pos < this.len)
				{
					case (1)
					{
						c = this._peek();
						switch (c == '<')
						{
							case (1)
							{
								this._adv();
								c = this._peek();
								// Closing tag?
								switch (c == '/')
								{
									case (1)
									{
										this._adv();
										switch (!this._read_name(@close_tag, @close_len))
										{
											case (1) { return false; }
											default {};
										};
										this._skip_ws();
										switch (this._peek() != '>')
										{
											case (1) { this.error = 1; return false; }
											default {};
										};
										this._adv();
										return true;
									}
									default {};
								};
								// Comment?
								switch (this._match_lit("!--\0", 3))
								{
									case (1)
									{
										child = this._alloc_node();
										switch ((u64)child == 0) { case (1) { return false; } default {}; };
										switch (!this._parse_comment(child)) { case (1) { return false; } default {}; };
										switch (!node.children.push_arena((void*)child, this.arena))
										{
											case (1) { this.error = 2; return false; }
											default {};
										};
										break;
									}
									default {};
								};
								// CDATA?
								switch (this._match_lit("![CDATA[\0", 8))
								{
									case (1)
									{
										child = this._alloc_node();
										switch ((u64)child == 0) { case (1) { return false; } default {}; };
										switch (!this._parse_cdata(child)) { case (1) { return false; } default {}; };
										switch (!node.children.push_arena((void*)child, this.arena))
										{
											case (1) { this.error = 2; return false; }
											default {};
										};
										break;
									}
									default {};
								};
								// PI?
								switch (c == '?')
								{
									case (1)
									{
										this._adv();
										child = this._alloc_node();
										switch ((u64)child == 0) { case (1) { return false; } default {}; };
										switch (!this._parse_pi(child)) { case (1) { return false; } default {}; };
										switch (!node.children.push_arena((void*)child, this.arena))
										{
											case (1) { this.error = 2; return false; }
											default {};
										};
										break;
									}
									default {};
								};
								// Child element.
								child = this._alloc_node();
								switch ((u64)child == 0) { case (1) { return false; } default {}; };
								switch (!this._parse_element(child)) { case (1) { return false; } default {}; };
								switch (!node.children.push_arena((void*)child, this.arena))
								{
									case (1) { this.error = 2; return false; }
									default {};
								};
							}
							default
							{
								// Text content.
								switch (c != '\x00')
								{
									case (1)
									{
										child = this._alloc_node();
										switch ((u64)child == 0) { case (1) { return false; } default {}; };
										switch (!this._parse_text(child)) { case (1) { return false; } default {}; };
										switch (child.text_len > 0)
										{
											case (1)
											{
												switch (!node.children.push_arena((void*)child, this.arena))
												{
													case (1) { this.error = 2; return false; }
													default {};
												};
											}
											default {};
										};
									}
									default {};
								};
							};
						};
					}
					default { break; };
				};
			};
			this.error = 1;
			return false;
		};

		def parse(XMLNode* node) -> bool
		{
			char c;
			do
			{
				this._skip_ws();
				switch (this.pos < this.len & this._peek() == '<')
				{
					case (1)
					{
						this._adv();
						c = this._peek();
						switch (c == '?')
						{
							case (1)
							{
								this._adv();
								XMLNode pi_node;
								this._parse_pi(@pi_node);
								continue;
							}
							default {};
						};
						switch (this._match_lit("!--\0", 3))
						{
							case (1)
							{
								XMLNode cmt_node;
								this._parse_comment(@cmt_node);
								continue;
							}
							default {};
						};
						switch (this._match_lit("!DOCTYPE\0", 8))
						{
							case (1)
							{
								XMLNode dt_node;
								this._parse_doctype(@dt_node);
								continue;
							}
							default {};
						};
						return this._parse_element(node);
					}
					default { break; };
				};
			};
			this.error = 1;
			return false;
		};
	};

	// =========================================================================
	// Serializer — fixed-size buffer
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
					pos      = pos + 1;
					i        = i + 1;
				}
				default { break; };
			};
		};
		buf[pos] = '\x00';
		return pos;
	};

	def _wn(byte* buf, int pos, int cap, byte* src, int n) -> int
	{
		int i;
		do
		{
			switch (i < n & pos < cap - 1)
			{
				case (1)
				{
					buf[pos] = src[i];
					pos      = pos + 1;
					i        = i + 1;
				}
				default { break; };
			};
		};
		buf[pos] = '\x00';
		return pos;
	};

	def _we_text(byte* buf, int pos, int cap, byte* src, int n) -> int
	{
		int  i;
		char c;
		do
		{
			switch (i < n & pos < cap - 1)
			{
				case (1)
				{
					c = (char)src[i];
					switch (c)
					{
						case (38) { pos = _ws(buf, pos, cap, "&amp;\0");  }
						case (60) { pos = _ws(buf, pos, cap, "&lt;\0");   }
						case (62) { pos = _ws(buf, pos, cap, "&gt;\0");   }
						default   { pos = _wc(buf, pos, cap, c);          };
					};
					i = i + 1;
				}
				default { break; };
			};
		};
		return pos;
	};

	def _we_attr(byte* buf, int pos, int cap, byte* src, int n) -> int
	{
		int  i;
		char c;
		do
		{
			switch (i < n & pos < cap - 1)
			{
				case (1)
				{
					c = (char)src[i];
					switch (c)
					{
						case (38) { pos = _ws(buf, pos, cap, "&amp;\0");  }
						case (60) { pos = _ws(buf, pos, cap, "&lt;\0");   }
						case (34) { pos = _ws(buf, pos, cap, "&quot;\0"); }
						default   { pos = _wc(buf, pos, cap, c);          };
					};
					i = i + 1;
				}
				default { break; };
			};
		};
		return pos;
	};

	def serialize(XMLNode* node, byte* buf, int pos, int cap) -> int;

	def serialize(XMLNode* node, byte* buf, int pos, int cap) -> int
	{
		XMLNode* child;
		size_t   k, n, ak;
		byte*    av;
		int      avl;

		switch ((u64)node == 0) { case (1) { return pos; } default {}; };

		switch (node.type)
		{
			case (XML_ELEMENT)
			{
				pos = _wc(buf, pos, cap, '<');
				pos = _wn(buf, pos, cap, node.tag, node.tag_len);
				ak = 0;
				do
				{
					switch (ak < node.attrs.len)
					{
						case (1)
						{
							pos = _wc(buf, pos, cap, ' ');
							pos = _ws(buf, pos, cap, node.attrs.key_at(ak));
							pos = _wc(buf, pos, cap, '=');
							pos = _wc(buf, pos, cap, '"');
							av  = node.attrs.val_at(ak);
							avl = (int)node.attrs.val_len_at(ak);
							pos = _we_attr(buf, pos, cap, av, avl);
							pos = _wc(buf, pos, cap, '"');
							ak++;
						}
						default { break; };
					};
				};
				switch (node.self_closing)
				{
					case (1)
					{
						pos = _ws(buf, pos, cap, "/>\0");
					}
					default
					{
						pos = _wc(buf, pos, cap, '>');
						n = node.children.len;
						do
						{
							switch (k < n)
							{
								case (1)
								{
									child = (XMLNode*)node.children.get(k);
									pos   = serialize(child, buf, pos, cap);
									k++;
								}
								default { break; };
							};
						};
						pos = _ws(buf, pos, cap, "</\0");
						pos = _wn(buf, pos, cap, node.tag, node.tag_len);
						pos = _wc(buf, pos, cap, '>');
					};
				};
			}
			case (XML_TEXT)
			{
				pos = _we_text(buf, pos, cap, node.text, node.text_len);
			}
			case (XML_COMMENT)
			{
				pos = _ws(buf, pos, cap, "<!--\0");
				pos = _wn(buf, pos, cap, node.text, node.text_len);
				pos = _ws(buf, pos, cap, "-->\0");
			}
			case (XML_CDATA)
			{
				pos = _ws(buf, pos, cap, "<![CDATA[\0");
				pos = _wn(buf, pos, cap, node.text, node.text_len);
				pos = _ws(buf, pos, cap, "]]>\0");
			}
			case (XML_PI)
			{
				pos = _ws(buf, pos, cap, "<?\0");
				pos = _wn(buf, pos, cap, node.text, node.text_len);
				pos = _ws(buf, pos, cap, "?>\0");
			}
			case (XML_DOCTYPE)
			{
				pos = _ws(buf, pos, cap, "<!DOCTYPE \0");
				pos = _wn(buf, pos, cap, node.text, node.text_len);
				pos = _wc(buf, pos, cap, '>');
			}
			default {};
		};

		return pos;
	};

	// =========================================================================
	// Arena serializer — grows as needed, no caller pre-sizing required.
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
		byte* nb;
		int   new_cap, i;
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

	def _sb_wn(SerializeBuf* sb, byte* src, int n) -> bool
	{
		int i;
		do
		{
			switch (i < n)
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

	def _sb_we_text(SerializeBuf* sb, byte* src, int n) -> bool
	{
		int  i;
		char c;
		do
		{
			switch (i < n)
			{
				case (1)
				{
					c = (char)src[i];
					switch (c)
					{
						case (38) { switch (!_sb_ws(sb, "&amp;\0"))  { case (1) { return false; } default {}; }; }
						case (60) { switch (!_sb_ws(sb, "&lt;\0"))   { case (1) { return false; } default {}; }; }
						case (62) { switch (!_sb_ws(sb, "&gt;\0"))   { case (1) { return false; } default {}; }; }
						default   { switch (!_sb_wc(sb, c))          { case (1) { return false; } default {}; }; };
					};
					i = i + 1;
				}
				default { break; };
			};
		};
		return true;
	};

	def _sb_we_attr(SerializeBuf* sb, byte* src, int n) -> bool
	{
		int  i;
		char c;
		do
		{
			switch (i < n)
			{
				case (1)
				{
					c = (char)src[i];
					switch (c)
					{
						case (38) { switch (!_sb_ws(sb, "&amp;\0"))  { case (1) { return false; } default {}; }; }
						case (60) { switch (!_sb_ws(sb, "&lt;\0"))   { case (1) { return false; } default {}; }; }
						case (34) { switch (!_sb_ws(sb, "&quot;\0")) { case (1) { return false; } default {}; }; }
						default   { switch (!_sb_wc(sb, c))          { case (1) { return false; } default {}; }; };
					};
					i = i + 1;
				}
				default { break; };
			};
		};
		return true;
	};

	def _serialize_arena_node(XMLNode* node, SerializeBuf* sb) -> bool;

	def _serialize_arena_node(XMLNode* node, SerializeBuf* sb) -> bool
	{
		XMLNode* child;
		size_t   k, n, ak;
		byte*    av;
		int      avl;

		switch ((u64)node == 0) { case (1) { return true; } default {}; };

		switch (node.type)
		{
			case (XML_ELEMENT)
			{
				switch (!_sb_wc(sb, '<')) { case (1) { return false; } default {}; };
				switch (!_sb_wn(sb, node.tag, node.tag_len)) { case (1) { return false; } default {}; };
				ak = 0;
				do
				{
					switch (ak < node.attrs.len)
					{
						case (1)
						{
							switch (!_sb_wc(sb, ' '))                              { case (1) { return false; } default {}; };
							switch (!_sb_ws(sb, node.attrs.key_at(ak)))            { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, '='))                              { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, '"'))                              { case (1) { return false; } default {}; };
							av  = node.attrs.val_at(ak);
							avl = (int)node.attrs.val_len_at(ak);
							switch (!_sb_we_attr(sb, av, avl))                     { case (1) { return false; } default {}; };
							switch (!_sb_wc(sb, '"'))                              { case (1) { return false; } default {}; };
							ak++;
						}
						default { break; };
					};
				};
				switch (node.self_closing)
				{
					case (1)
					{
						switch (!_sb_ws(sb, "/>\0")) { case (1) { return false; } default {}; };
					}
					default
					{
						switch (!_sb_wc(sb, '>')) { case (1) { return false; } default {}; };
						n = node.children.len;
						do
						{
							switch (k < n)
							{
								case (1)
								{
									child = (XMLNode*)node.children.get(k);
									switch (!_serialize_arena_node(child, sb)) { case (1) { return false; } default {}; };
									k++;
								}
								default { break; };
							};
						};
						switch (!_sb_ws(sb, "</\0"))                       { case (1) { return false; } default {}; };
						switch (!_sb_wn(sb, node.tag, node.tag_len))       { case (1) { return false; } default {}; };
						switch (!_sb_wc(sb, '>'))                          { case (1) { return false; } default {}; };
					};
				};
			}
			case (XML_TEXT)
			{
				switch (!_sb_we_text(sb, node.text, node.text_len)) { case (1) { return false; } default {}; };
			}
			case (XML_COMMENT)
			{
				switch (!_sb_ws(sb, "<!--\0"))                       { case (1) { return false; } default {}; };
				switch (!_sb_wn(sb, node.text, node.text_len))       { case (1) { return false; } default {}; };
				switch (!_sb_ws(sb, "-->\0"))                        { case (1) { return false; } default {}; };
			}
			case (XML_CDATA)
			{
				switch (!_sb_ws(sb, "<![CDATA[\0"))                  { case (1) { return false; } default {}; };
				switch (!_sb_wn(sb, node.text, node.text_len))       { case (1) { return false; } default {}; };
				switch (!_sb_ws(sb, "]]>\0"))                        { case (1) { return false; } default {}; };
			}
			case (XML_PI)
			{
				switch (!_sb_ws(sb, "<?\0"))                         { case (1) { return false; } default {}; };
				switch (!_sb_wn(sb, node.text, node.text_len))       { case (1) { return false; } default {}; };
				switch (!_sb_ws(sb, "?>\0"))                         { case (1) { return false; } default {}; };
			}
			case (XML_DOCTYPE)
			{
				switch (!_sb_ws(sb, "<!DOCTYPE \0"))                 { case (1) { return false; } default {}; };
				switch (!_sb_wn(sb, node.text, node.text_len))       { case (1) { return false; } default {}; };
				switch (!_sb_wc(sb, '>'))                            { case (1) { return false; } default {}; };
			}
			default {};
		};

		return true;
	};

	// Serialize node into arena memory. Returns null-terminated string on
	// success, null on OOM. init_cap is initial buffer guess in bytes;
	// 256 is reasonable for most documents.
	def serialize_arena(XMLNode* node, standard::memory::allocators::stdarena::Arena* a, int init_cap) -> byte*
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
