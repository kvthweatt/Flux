// Author: Karac V. Thweatt
// xml_load.fx - Load a .xml file, parse it, close it, and time each phase.

#import "standard.fx";
#import "allocators.fx";
#import "ffifio.fx";
#import "xml.fx";
#import "timing.fx";

using standard::io::console,
      standard::io::file,
      standard::strings,
      standard::time,
      standard::memory::allocators::stdarena,
      standard::threading,
      xml;

def print_ms(i64 ns) -> void
{
    i64      ms, us;
    byte[64] buf;
    ms = ns_to_ms(ns);
    us = ns_to_us(ns) % 1000;
    i64str(ms, @buf[0]);
    print(@buf[0]);
    print(".\0");
    if (us < 100) { print("0\0"); };
    if (us < 10)  { print("0\0"); };
    i64str(us, @buf[0]);
    print(@buf[0]);
    print(" ms\0");
    return;
};

def print_mbs(i64 bytes, i64 ns) -> void
{
    i64      us, kb_per_s, mbs, mbs_frac;
    byte[64] buf;
    if (ns <= 0) { print("N/A\0"); return; };
    us = ns / 1000;
    if (us <= 0) { us = 1; };
    kb_per_s = (bytes * 1000) / us;
    mbs      = kb_per_s / 1024;
    mbs_frac = (kb_per_s % 1024) * 10 / 1024;
    i64str(mbs, @buf[0]);
    print(@buf[0]);
    print(".\0");
    i64str(mbs_frac, @buf[0]);
    print(@buf[0]);
    print(" MB/s\0");
    return;
};

// Walk element tree and count total nodes and max depth reached.
def count_nodes(XMLNode* node, int depth, int* total, int* max_depth) -> void
{
    XMLNode* child;
    size_t   i, n;
    *total = *total + 1;
    if (depth > *max_depth) { *max_depth = depth; };
    if (node.type != XML_ELEMENT) { return; };
    n = node.children.len;
    i = 0;
    do
    {
        if (i >= n) { break; };
        child = (XMLNode*)node.children.get(i);
        if ((u64)child != 0) { count_nodes(@child, depth + 1, total, max_depth); };
        i++;
    };
    return;
};

def parse_and_report(byte* buf, int buf_len) -> int
{
    XMLNode        root();
    Arena          arena;
    XMLParser      p(buf, buf_len, @arena);
    byte[64]       num_buf;
    byte[4096]     ser_buf;
    size_t         node_cap;
    int            total_nodes, max_depth, ser_len;
    byte*          first_child_tag;
    XMLNode*       first_child;

    // Single arena: worst case ~1 node per 4 bytes of source, 2x headroom,
    // plus source size for string/attr data.
    node_cap = (size_t)((buf_len / 4 + 1) * (sizeof(XMLNode) / sizeof(byte)) * 2)
             + (size_t)buf_len + 1;
    arena_init_sized(@arena, node_cap);

    p.parse(@root);

    if (!p.ok())
    {
        print("ERROR: XML parse failed\n\0");
        arena_destroy(@arena);
        return 1;
    };

    // Root info.
    print("Root type:     \0");
    if (root.is_element())
    {
        print("element\n\0");
        print("Root tag:      \0");
        if ((u64)root.tag != 0)
        {
            // tag_len bytes — not null-terminated in zero-copy mode.
            // Write manually from tag pointer.
            ser_len = 0;
            do
            {
                if (ser_len >= root.tag_len) { break; };
                ser_buf[ser_len] = root.tag[ser_len];
                ser_len = ser_len + 1;
            };
            ser_buf[ser_len] = '\x00';
            print(@ser_buf[0]);
        }
        elif ((u64)root.tag == 0) { print("(none)\0"); };
        print("\n\0");

        print("Attributes:    \0");
        i32str((int)root.attr_count(), @num_buf[0]);
        print(@num_buf[0]);
        print("\n\0");

        print("Direct children: \0");
        i32str((int)root.child_count(), @num_buf[0]);
        print(@num_buf[0]);
        print("\n\0");

        // First child element tag.
        first_child = (XMLNode*)root.children.get(0);
        if ((u64)first_child != 0 & first_child.type == XML_ELEMENT)
        {
            print("First child:   \0");
            ser_len = 0;
            do
            {
                if (ser_len >= first_child.tag_len) { break; };
                ser_buf[ser_len] = first_child.tag[ser_len];
                ser_len = ser_len + 1;
            };
            ser_buf[ser_len] = '\x00';
            print(@ser_buf[0]);
            print("\n\0");
        };

        // Walk tree.
        total_nodes = 0;
        max_depth   = 0;
        count_nodes(@root, 0, @total_nodes, @max_depth);
        print("Total nodes:   \0");
        i32str(total_nodes, @num_buf[0]);
        print(@num_buf[0]);
        print("\n\0");
        print("Max depth:     \0");
        i32str(max_depth, @num_buf[0]);
        print(@num_buf[0]);
        print("\n\0");

        // Round-trip serialize root into fixed buffer sample.
        ser_len = serialize(@root, @ser_buf[0], 0, 4096);
        print("Serialized (first 200 chars):\n  \0");
        ser_buf[200] = '\x00';
        print(@ser_buf[0]);
        print("\n\0");
    }
    elif (root.is_text())    { print("text\n\0");    }
    elif (root.is_comment()) { print("comment\n\0"); }
    elif (root.is_cdata())   { print("cdata\n\0");   }
    elif (root.is_pi())      { print("pi\n\0");      }
    elif (root.is_doctype()) { print("doctype\n\0"); };

    arena_destroy(@arena);
    return 0;
};

def main() -> int
{
    void*    fh;
    int      file_size, bytes_read, result;
    byte*    buf;
    byte[64] num_buf;
    i64      t_start, t_after_load, t_after_parse, load_ns, parse_ns, total_ns;

    t_start = time_now();

    print("Opening test.xml...\n\0");

    fh = fopen("test.xml\0", "rb\0");
    if ((u64)fh == 0)
    {
        print("ERROR: Could not open test.xml\n\0");
        return 1;
    };

    fseek(fh, 0, SEEK_END);
    file_size = ftell(fh);
    fseek(fh, 0, SEEK_SET);

    print("File size: \0");
    i32str(file_size, @num_buf[0]);
    print(@num_buf[0]);
    print(" bytes\n\0");

    buf = (byte*)fmalloc((u64)file_size + 1);
    if ((u64)buf == 0)
    {
        print("ERROR: Out of memory\n\0");
        fclose(fh);
        return 1;
    };

    bytes_read = fread(buf, 1, file_size, fh);
    fclose(fh);
    buf[bytes_read] = (byte)0;

    t_after_load = time_now();

    // Pass bytes_read directly — no strlen in parser.
    result = parse_and_report(buf, bytes_read);

    t_after_parse = time_now();

    ffree((u64)buf);

    load_ns  = t_after_load  - t_start;
    parse_ns = t_after_parse - t_after_load;
    total_ns = t_after_parse - t_start;

    print("\n\0");
    print("Load:  \0"); print_ms(load_ns);  print(" | \0"); print_mbs((i64)bytes_read, load_ns);  print("\n\0");
    print("Parse: \0"); print_ms(parse_ns); print(" | \0"); print_mbs((i64)bytes_read, parse_ns); print("\n\0");
    print("Total: \0"); print_ms(total_ns); print(" | \0"); print_mbs((i64)bytes_read, total_ns); print("\n\0");

    system("pause");

    return result;
};
