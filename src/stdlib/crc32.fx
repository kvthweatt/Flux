// crc32.fx — CRC32 library (IEEE 802.3, reflected polynomial 0xEDB88320)

#ifndef FLUX_STANDARD_STRINGS
#import "string_utilities.fx";
#endif;

using standard::strings;

namespace crc32
{
    def compute(byte* buf, uint length) -> uint
    {
        uint[256] table;
        uint crc, idx, entry;

        // Build lookup table
        for (uint t; t < 256u; t++)
        {
            entry = t;

            for (int bit; bit < 8; bit++)
            {
                if (entry `& 1u)
                {
                    entry = (entry >> 1) `^^ 0xEDB88320u;
                }
                else
                {
                    entry = entry >> 1;
                };
            };

            table[t] = entry;
        };

        // Compute CRC
        crc = 0xFFFFFFFFu;

        for (uint j; j < length; j++)
        {
            idx = (crc `^^ ((uint)buf[j] `& 0xFFu)) `& 0xFFu;
            crc = (crc >> 8) `^^ table[idx];
        };

        return crc `^^ 0xFFFFFFFFu;
    };

    def of_string(byte* str) -> uint
    {
        return compute(str, strlen(str));
    };
};
