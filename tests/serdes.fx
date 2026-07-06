#import <standard.fx>;

using standard::io::console;

// Schema: field names and their types, defined once
comptime
{
    byte*[] field_types = ["float", "float", "float", "float"],
            field_names = ["x", "y", "z", "w"];
    int     field_count = 4;

    compiler.io.console.print("test?");

    // Emit the struct itself
    emitflux
    {
        struct Vec4
        {
            comptime
            {
                for (int fidx = 0; fidx < field_count; fidx++)
                {
                    emitflux
                    {
                        ~$f"{field_types[fidx]} {field_names[fidx]}";
                    };
                };
            };
        };
    };

    // Emit a zero() constructor
    emitflux
    {
        def vec4_zero() -> Vec4
        {
            Vec4 v;
            comptime
            {
                for (int fidx = 0; fidx < field_count; fidx++)
                {
                    emitflux
                    {
                        ~$f"v.{field_names[fidx]}" = 0.0f;
                    };
                };
            };
            return v;
        };
    };

    // Emit a pack-to-float-array function
    emitflux
    {
        def vec4_pack(Vec4 v, float* out) -> void
        {
            comptime
            {
                for (int fidx = 0; fidx < field_count; fidx++)
                {
                    emitflux
                    {
                        ~$f"out[{fidx}] = v.{field_names[fidx]};";
                    };
                };
            };
        };
    };

    // Emit an unpack-from-float-array function
    emitflux
    {
        def vec4_unpack(float* src) -> Vec4
        {
            Vec4 v;
            comptime
            {
                for (int fidx = 0; fidx < field_count; fidx++)
                {
                    emitflux
                    {
                        ~$f"v.{field_names[fidx]} = src[{fidx}];";
                    };
                };
            };
            return v;
        };
    };

    // Emit a println for debug printing
    emitflux
    {
        def vec4_print(Vec4 v) -> void
        {
            comptime
            {
                for (int fidx = 0; fidx < field_count; fidx++)
                {
                    emitflux
                    {
                        ~$"println(f\"{v.field_names[fidx]} = {field_names[fidx]}\");";
                    };
                };
            };
        };
    };
};

def main() -> int
{
    Vec4 a = {x = 1.0f, y = 2.0f, z = 3.0f, w = 4.0f};

    println("Pack/unpack round-trip:\0");
    float[4] buf;
    vec4_pack(a, @buf[0]);

    Vec4 b = vec4_unpack(@buf[0]);
    vec4_print(b);

    return 0;
};
