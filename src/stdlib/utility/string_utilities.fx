// Author: Karac V. Thweatt

// Additional String Manipulation Utilities
// Fresh snippet - pick and choose what you want

#ifndef FLUX_STANDARD_STRINGS
#def FLUX_STANDARD_STRINGS 1;

namespace standard
{
    namespace strings
    {
        extern
        {
            def !!
                strcmp(byte* x, byte* y) -> int,
                printf(byte* x, byte* y) -> void,
                strncpy(byte* dest, byte* src, size_t n) -> byte*,
                strcat(byte* dest, byte* src) -> byte*,
                strncat(byte* dest, byte* src, size_t n) -> byte*,
                strncmp(byte* s1, byte* s2, size_t n) -> int,
                strtok(byte* str, byte* delim) -> byte*,
                strtok_s(byte* str, byte* delim, byte** saveptr) -> byte*,
                _strdup(byte* str) -> byte*;
        };

        def strlen(byte* ps) -> int
        {
            int c;
            byte* ch;
            do
            {
                ch = ps++;

                switch (*ch)
                {
                    case (0) { break; }
                    default {};
                };

                c++;
            };
            return c;
        };

        def strstr(byte* haystack, byte* needle) -> byte*
        {
            byte* h, n;
            if (*needle == 0) { return haystack; };
            for (;;)
            {
                if (*haystack == 0) { return (byte*)0; };
                h = haystack;
                n = needle;
                while (*h != 0 & *n != 0 & *h == *n)
                {
                    h = h + 1;
                    n = n + 1;
                };
                if (*n == 0) { return haystack; };
                haystack = haystack + 1;
            };
            return haystack;
        };

        def strchr(byte* str, int c) -> byte*
        {
            for (;;)
            {
                if (*str == c) { return str; };
                if (*str == 0) { return (byte*)0; };
                str = str + 1;
            };
            return (byte*)0;
        };

        def strcpy(noopstr dest, noopstr src) -> noopstr
        {
            size_t i;
            while (src[i] != 0)
            {
                dest[i] = src[i];
                i++;
            };
            dest[i] = (byte)0;
            return dest;
        };

        def i16str(i16 value, byte* buffer) -> i16
        {
            if (value == 0)
            {
                buffer[0] = (byte)48;
                buffer[1] = (byte)0;
                return 1;
            };

            bool is_negative;
            if (value < (i16)0)
            {
                is_negative = true;
                value = -value;
            };

            i16 pos = (i16)0;
            byte[8] temp;

            while (value > (i16)0)
            {
                temp[pos] = (byte)((value % (i16)10) + (i16)48);
                value = value / (i16)10;
                pos++;
            };

            i16 write_pos = (i16)0;
            if (is_negative)
            {
                buffer[0] = (byte)45;
                write_pos = (i16)1;
            };

            i16 i = pos - (i16)1;
            while (i >= (i16)0)
            {
                buffer[write_pos] = temp[i];
                write_pos++;
                i--;
            };

            buffer[write_pos] = (byte)0;
            return write_pos;
        };

        def i32str(i32 value, byte* buffer) -> i32
        {
            if (value == 0)
            {
                buffer[0] = (byte)48; // '0'
                buffer[1] = (byte)0;  // null terminator
                return 1;
            };
            
            i32 is_negative = 0;
            if (value < 0)
            {
                is_negative = 1;
                value = -value;
            };
            
            // Convert to string in reverse
            i32 pos = 0;
            byte[32] temp;
            
            while (value > 0)
            {
                temp[pos] = (byte)((value % 10) + 48); // Convert digit to ASCII
                value = value / 10;
                pos++;
            };
            
            // Add negative sign if needed
            i32 write_pos = 0;
            if (is_negative == 1)
            {
                buffer[0] = (byte)45; // '-' // cannot store i32 to i8*: mismatching types without (byte)
                write_pos = 1;
            };
            
            // Copy reversed string to buffer
            i32 i = pos - 1;
            while (i >= 0)
            {
                buffer[write_pos] = temp[i];
                write_pos++;
                i--;
            };
            
            buffer[write_pos] = (byte)0; // null terminator
            return write_pos;
        };

        def i64str(i64 value, byte* buffer) -> i64
        {
            if (value == (i64)0)
            {
                buffer[0] = (byte)48; // '0'
                buffer[1] = (byte)0;  // null terminator
                return 1;
            };
            
            i64 is_negative = (i64)0;
            if (value < (i64)0)
            {
                is_negative = (i64)1;
                value = -value;
            };
            
            // Convert to string in reverse
            i64 pos = (i64)0;
            byte[32] temp;
            
            while (value > (i64)0)
            {
                temp[pos] = (byte)((value % (i64)10) + (i64)48); // Convert digit to ASCII
                value = value / (i64)10;
                pos++;
            };
            
            // Add negative sign if needed
            i64 write_pos = 0;
            if (is_negative == (i64)1)
            {
                buffer[0] = (byte)45; // '-'
                write_pos = (i64)1;
            };
            
            // Copy reversed string to buffer
            i64 i = pos - (i64)1;
            while (i >= (i64)0)
            {
                buffer[write_pos] = temp[i];
                write_pos++;
                i--;
            };
            
            buffer[write_pos] = (byte)0; // null terminator
            return write_pos;
        };

        def u16str(u16 value, byte* buffer) -> u16
        {
            if (value == (u16)0)
            {
                buffer[0] = (byte)48;
                buffer[1] = (byte)0;
                return (u16)1;
            };

            u16 pos = (u16)0;
            byte[8] temp;

            while (value > (u16)0)
            {
                temp[pos] = (byte)((value % (u16)10) + (u16)48);
                value = value / (u16)10;
                pos++;
            };

            u16 write_pos = (u16)0;
            u16 i = pos;
            while (i > (u16)0)
            {
                i--;
                buffer[write_pos] = temp[i];
                write_pos++;
            };

            buffer[write_pos] = (byte)0;
            return write_pos;
        };

        def u32str(u32 value, byte* buffer) -> u32
        {
            if (value == (u32)0)
            {
                buffer[0] = (byte)48; // '0'
                buffer[1] = (byte)0;  // null terminator
                return (u32)1;
            };
            
            // Convert to string in reverse
            u32 pos = (u32)0;
            byte[32] temp;
            
            while (value > (u32)0)
            {
                temp[pos] = (byte)((value % (u32)10) + (u32)48);
                value = value / (u32)10;
                pos++;
            };
            
            // Copy reversed string to buffer
            u32 write_pos = (u32)0;
            u32 i = pos;  // Start at pos, not pos - 1
            while (i > (u32)0)  // Check i > 0 instead of i >= 0
            {
                i--;  // Decrement first
                buffer[write_pos] = temp[i];
                write_pos++;
            };
            
            buffer[write_pos] = (byte)0; // null terminator
            return write_pos;
        };

        def u64str(u64 value, byte* buffer) -> u64
        {
            if (value == (u64)0)
            {
                buffer[0] = (byte)48; // '0'
                buffer[1] = (byte)0;  // null terminator
                return (u64)1;
            };
            
            // Convert to string in reverse
            u64 pos = (u64)0;
            byte[32] temp;
            
            // Use != 0 instead of > 0 to avoid signed comparison issues
            while (value != (u64)0)
            {
                temp[pos] = (byte)((value % (u64)10) + (u64)48); // Convert digit to ASCII
                value = value / (u64)10;
                pos++;
            };
            
            // Copy reversed string to buffer
            u64 write_pos = (u64)0;
            u64 remaining = pos;  // Track how many digits remain

            while (remaining != (u64)0)
            {
                remaining--;  // Decrement BEFORE using as index
                buffer[write_pos] = temp[remaining];
                write_pos++;
            };
            
            buffer[write_pos] = (byte)0; // null terminator
            return write_pos;
        };

        def str2i32(byte* str) -> int
        {
            int result, i, digit;
            int sign = 1;
            byte c;
            while (str[i] == 32 | str[i] == 9 | str[i] == 10 | str[i] == 13)
            {
                i++;
            };
            if (str[i] == 45)  
            {
                sign = -1;
                i++;
            }
            elif (str[i] == 43)  
            {
                i++;
            };
            while (str[i] != 0)
            {
                c = str[i];
                if (c >= 48 & c <= 57)
                {
                    digit = (int)(c - 48);
                    result = result * 10 + digit;
                }
                else
                {
                    break;
                };
                i++;
            };
            return result * sign;
        };

        // Convert string to unsigned 32-bit integer
        // Returns 0 if string is invalid or negative
        def str2u32(byte* str) -> uint
        {
            uint result, digit;
            int i;
            byte c;
            
            // Skip leading whitespace
            while (str[i] == 32 | str[i] == 9 | str[i] == 10 | str[i] == 13)
            {
                i++;
            };
            
            // Skip '+' if present, return 0 if '-' present
            if (str[i] == 45)  // '-'
            {
                return 0;  // Negative not allowed for unsigned
            }
            elif (str[i] == 43)  // '+'
            {
                i++;
            };
            
            // Convert digits
            while (str[i] != 0)
            {
                c = str[i];
                
                // Check if character is a digit
                if (c >= 48 & c <= 57)
                {
                    digit = (uint)(c - 48);
                    result = result * 10 + digit;
                }
                else
                {
                    // Non-digit character, stop parsing
                    break;
                };
                
                i++;
            };
            
            return result;
        };

        // Convert string to signed 64-bit integer
        // Returns 0 if string is invalid
        def str2i64(byte* str) -> i64
        {
            i64 result, digit;
            i64 sign = 1;
            int i;
            byte c;
            
            // Skip leading whitespace
            while (str[i] == 32 | str[i] == 9 | str[i] == 10 | str[i] == 13)
            {
                i++;
            };
            
            // Check for sign
            if (str[i] == 45)  // '-'
            {
                sign = (i64)-1;
                i++;
            }
            elif (str[i] == 43)  // '+'
            {
                i++;
            };
            
            // Convert digits
            while (str[i] != 0)
            {
                c = str[i];
                
                // Check if character is a digit
                if (c >= 48 & c <= 57)
                {
                    digit = (i64)(c - 48);
                    result = result * 10 + digit;
                }
                else
                {
                    // Non-digit character, stop parsing
                    break;
                };
                
                i++;
            };
            
            return result * sign;
        };

        // Convert string to unsigned 64-bit integer
        // Returns 0 if string is invalid or negative
        def str2u64(byte* str) -> u64
        {
            u64 result, digit;
            int i;
            byte c;
            
            // Skip leading whitespace
            while (str[i] == 32 | str[i] == 9 | str[i] == 10 | str[i] == 13)
            {
                i++;
            };
            
            // Skip '+' if present, return 0 if '-' present
            if (str[i] == 45)  // '-'
            {
                return 0;  // Negative not allowed for unsigned
            }
            elif (str[i] == 43)  // '+'
            {
                i++;
            };
            
            // Convert digits
            while (str[i] != 0)
            {
                c = str[i];
                
                // Check if character is a digit
                if (c >= 48 & c <= 57)
                {
                    digit = (u64)(c - 48);
                    result = result * 10 + digit;
                }
                else
                {
                    // Non-digit character, stop parsing
                    break;
                };
                
                i++;
            };
            
            return result;
        };

        // Convert float to string with specified precision
        // Returns number of characters written (excluding null terminator)
        def float2str(float value, byte* buffer, i32 precision) -> i32
        {
            i32 write_pos, i;
            
            // Handle negative numbers
            if (value < 0.0)
            {
                buffer[0] = 45; // '-'
                write_pos = 1;
                value = -value;
            };
            
            // Handle zero case
            if (value == 0.0)
            {
                buffer[write_pos] = 48; // '0'
                buffer[write_pos + 1] = 46; // '.'
                
                while (i < precision)
                {
                    buffer[write_pos + 2 + i] = 48; // '0'
                    i++;
                };
                
                buffer[write_pos + 2 + precision] = 0;
                return write_pos + 1 + precision;
            };
            
            // Extract integer part
            i32 int_part = int(value);
            
            // Extract fractional part
            float fractional = value - float(int_part);
            
            // Multiply fractional by 10^precision without helper function
            i32 frac_multiplier = 1,
                j;
            while (j < precision)
            {
                frac_multiplier = frac_multiplier * 10;
                j++;
            };
            
            // Calculate fractional part with rounding
            float scaled_frac = fractional * (float)frac_multiplier;
            i32 frac_part = (i32)(scaled_frac + 0.5);
            
            // Handle overflow from rounding (e.g., 0.999 becomes 1.00)
            if (frac_part >= frac_multiplier)
            {
                int_part = int_part + 1;
                frac_part = 0;
                
                // If int_part became 10, 100, etc., adjust
                if (int_part % 10 == 0 & precision > 0)
                {
                    // Simple adjustment for common cases
                    // Full general solution would be more complex
                };
            };
            
            // Convert integer part to string
            if (int_part == 0)
            {
                buffer[write_pos] = (byte)48; // '0'
                write_pos = write_pos + 1;
            }
            else
            {
                // Convert integer part in reverse
                byte[32] int_temp;
                i32 temp_pos,
                    temp_int = int_part;
                
                while (temp_int > 0)
                {
                    int_temp[temp_pos] = (byte)((temp_int % 10) + 48);
                    temp_int = temp_int / 10;
                    temp_pos++;
                };
                
                // Copy integer part to buffer
                i32 k = temp_pos - 1;
                while (k >= 0)
                {
                    buffer[write_pos] = int_temp[k];
                    write_pos = write_pos + 1;
                    k--;
                };
            };
            
            // Add decimal point if precision > 0
            if (precision > 0)
            {
                buffer[write_pos] = (byte)46; // '.'
                write_pos = write_pos + 1;
                
                // Convert fractional part to string with leading zeros
                if (frac_part == 0)
                {
                    i32 m = 0;
                    while (m < precision)
                    {
                        buffer[write_pos] = (byte)48; // '0'
                        write_pos = write_pos + 1;
                        m++;
                    };
                }
                else
                {
                    // Build fractional part in reverse
                    byte[32] frac_temp;
                    i32 frac_digits = 0;
                    i32 temp_frac = frac_part;
                    
                    while (temp_frac > 0)
                    {
                        frac_temp[frac_digits] = (byte)((temp_frac % 10) + 48);
                        temp_frac = temp_frac / 10;
                        frac_digits++;
                    };
                    
                    // Add leading zeros if needed
                    i32 leading_zeros = precision - frac_digits;
                    i32 n = 0;
                    while (n < leading_zeros)
                    {
                        buffer[write_pos] = (byte)48; // '0'
                        write_pos = write_pos + 1;
                        n++;
                    };
                    
                    // Copy fractional digits in reverse (to get correct order)
                    i32 p = frac_digits - 1;
                    while (p >= 0)
                    {
                        buffer[write_pos] = frac_temp[p];
                        write_pos = write_pos + 1;
                        p--;
                    };
                };
            };
            
            // Add null terminator
            buffer[write_pos] = (byte)0;
            return write_pos;
        };

        def dbl2str(double value, byte* buffer, i32 precision) -> i32
        {
            i32 write_pos = 0;
            
            // Handle negative numbers
            if (value < (double)0.0)
            {
                buffer[0] = '\x45'; // '-'
                write_pos = 1;
                value = -value;
            };
            
            // Handle zero case
            if (value == (double)0.0)
            {
                buffer[write_pos] = (byte)48; // '0'
                buffer[write_pos + 1] = (byte)46; // '.'
                
                i32 i = 0;
                while (i < precision)
                {
                    buffer[write_pos + 2 + i] = (byte)48; // '0'
                    i++;
                };
                
                buffer[write_pos + 2 + precision] = (byte)0;
                return write_pos + 1 + precision;
            };
            
            // Extract integer part
            i64 int_part = (i64)value;
            
            // Extract fractional part
            double fractional = value - double(int_part);
            
            // Multiply fractional by 10^precision without helper function
            i64 frac_multiplier = (i64)1;
            i32 j = 0;
            while (j < precision)
            {
                frac_multiplier = frac_multiplier * (i64)10;
                j++;
            };
            
            // Calculate fractional part with rounding
            double scaled_frac = fractional * double(frac_multiplier);
            i64 frac_part = (i64)(scaled_frac + double(0.5));
            
            // Handle overflow from rounding (e.g., 0.999 becomes 1.00)
            if (frac_part >= frac_multiplier)
            {
                int_part = int_part + (i64)1;
                frac_part = (i64)0;
                
                // If int_part became 10, 100, etc., adjust
                if (int_part % (i64)10 == (i64)0 & precision > 0)
                {
                    // Simple adjustment for common cases
                    // Full general solution would be more complex
                };
            };
            
            // Convert integer part to string
            if (int_part == (i64)0)
            {
                buffer[write_pos] = (byte)48; // '0'
                write_pos = write_pos + 1;
            }
            else
            {
                // Convert integer part in reverse
                byte[32] int_temp;
                i32 temp_pos = 0;
                i64 temp_int = int_part;
                
                while (temp_int > (i64)0)
                {
                    int_temp[temp_pos] = (byte)((temp_int % (i64)10) + (i64)48);
                    temp_int = temp_int / (i64)10;
                    temp_pos++;
                };
                
                // Copy integer part to buffer
                i32 k = temp_pos - 1;
                while (k >= 0)
                {
                    buffer[write_pos] = int_temp[k];
                    write_pos = write_pos + 1;
                    k--;
                };
            };
            
            // Add decimal point if precision > 0
            if (precision > 0)
            {
                buffer[write_pos] = (byte)46; // '.'
                write_pos = write_pos + 1;
                
                // Convert fractional part to string with leading zeros
                if (frac_part == (i64)0)
                {
                    i32 m = 0;
                    while (m < precision)
                    {
                        buffer[write_pos] = (byte)48; // '0'
                        write_pos = write_pos + 1;
                        m++;
                    };
                }
                else
                {
                    // Build fractional part in reverse
                    byte[32] frac_temp;
                    i32 frac_digits = 0;
                    i64 temp_frac = frac_part;
                    
                    while (temp_frac > (i64)0)
                    {
                        frac_temp[frac_digits] = (byte)((temp_frac % (i64)10) + (i64)48);
                        temp_frac = temp_frac / (i64)10;
                        frac_digits++;
                    };
                    
                    // Add leading zeros if needed
                    i32 leading_zeros = precision - frac_digits;
                    i32 n = 0;
                    while (n < leading_zeros)
                    {
                        buffer[write_pos] = (byte)48; // '0'
                        write_pos = write_pos + 1;
                        n++;
                    };
                    
                    // Copy fractional digits in reverse (to get correct order)
                    i32 p = frac_digits - 1;
                    while (p >= 0)
                    {
                        buffer[write_pos] = frac_temp[p];
                        write_pos = write_pos + 1;
                        p--;
                    };
                };
            };
            
            // Add null terminator
            buffer[write_pos] = (byte)0;
            return write_pos;
        };

        // ===== CHARACTER CLASSIFICATION =====
        
        namespace helpers
        {
            def is_whitespace(char c) -> bool
            {
                return c == ' ' | c == '\t' | c == '\n' | c == '\r';
            };
            
            def is_digit(char c) -> bool
            {
                return c >= '0' & c <= '9';
            };
            
            def is_alpha(char c) -> bool
            {
                return (c >= 'a' & c <= 'z') | (c >= 'A' & c <= 'Z');
            };

            def is_upper(char c) -> bool
            {
                return c >= 'A' & c <= 'Z';
            };

            def is_lower(char c) -> bool
            {
                return c >= 'a' & c <= 'z';
            };
            
            def is_alnum(char c) -> bool
            {
                return is_alpha(c) | is_digit(c);
            };
            
            def is_hex_digit(char c) -> bool
            {
                return is_digit(c) | (c >= 'a' & c <= 'f') | (c >= 'A' & c <= 'F');
            };
            
            def is_identifier_start(char c) -> bool
            {
                return is_alpha(c) | c == '_';
            };
            
            def is_identifier_char(char c) -> bool
            {
                return is_alnum(c) | c == '_';
            };
            
            def is_newline(char c) -> bool
            {
                return c == '\n' | c == '\r';
            };
            
            
            // ===== CHARACTER CONVERSION =====
            
            def to_lower(char c) -> char
            {
                if (c >= 'A' & c <= 'Z')
                {
                    return c + 32;
                };
                return c;
            };
            
            def to_upper(char c) -> char
            {
                if (c >= 'a' & c <= 'z')
                {
                    return c - 32;
                };
                return c;
            };
            
            def char_to_digit(char c) -> int
            {
                if (c >= '0' & c <= '9')
                {
                    return c - '0';
                };
                return -1;
            };
            
            def hex_to_int(char c) -> int
            {
                if (c >= '0' & c <= '9')
                {
                    return c - '0';
                };
                if (c >= 'a' & c <= 'f')
                {
                    return 10 + (c - 'a');
                };
                if (c >= 'A' & c <= 'F')
                {
                    return 10 + (c - 'A');
                };
                return -1;
            };
            
            
            // ===== STRING SEARCHING =====
            
            // Find first occurrence of character
            // Returns index or -1 if not found
            def find_char(byte* str, char ch, int start_pos) -> int
            {
                for (int i = start_pos; str[i] != 0; i = i + 1)
                {
                    if (str[i] == ch)
                    {
                        return i;
                    };
                };
                return -1;
            };
            
            // Find last occurrence of character
            def find_char_last(byte* str, char ch) -> int
            {
                int last = -1;
                for (int i; str[i] != 0; i = i + 1)
                {
                    if (str[i] == ch)
                    {
                        last = i;
                    };
                };
                return last;
            };
            
            // Find first occurrence of any character from set
            def find_any(byte* str, byte* char_set, int start_pos) -> int
            {
                for (int i = start_pos; str[i] != 0; i = i + 1)
                {
                    for (int j; char_set[j] != 0; j = j + 1)
                    {
                        if (str[i] == char_set[j])
                        {
                            return i;
                        };
                    };
                };
                return -1;
            };
            
            // Find substring
            // Returns index or -1 if not found
            def find_substring(byte* str, byte* substr, int start_pos) -> int
            {
                int str_len, substr_len;
                bool match = true;
                while (str[str_len] != 0) { str_len = str_len + 1; };
                while (substr[substr_len] != 0) { substr_len = substr_len + 1; };
                
                if (substr_len == 0)
                {
                    return start_pos;
                };
                
                for (int i = start_pos; i <= str_len - substr_len; i = i + 1)
                {
                    for (int j; j < substr_len; j = j + 1)
                    {
                        if (str[i + j] != substr[j])
                        {
                            match = false;
                            break;
                        };
                    };
                    if (match)
                    {
                        return i;
                    };
                };
                return -1;
            };
            
            
            // ===== STRING TRIMMING =====
            
            // Skip leading whitespace, return new start position
            def skip_whitespace(byte* str, int pos) -> int
            {
                while (str[pos] != 0 & is_whitespace(str[pos]))
                {
                    pos = pos + 1;
                };
                return pos;
            };
            
            // Trim whitespace in-place from end (by writing null terminator)
            def trim_end(byte* str) -> void
            {
                int len = 0;
                while (str[len] != 0) { len = len + 1; };
                
                while (len > 0 & is_whitespace(str[len - 1]))
                {
                    len = len - 1;
                };
                str[len] = (byte)0;
                return;
            };
            
            
            // ===== STRING COMPARISON =====
            
            // Compare n characters
            def compare_n(byte* s1, byte* s2, int n) -> int
            {
                for (int i = 0; i < n; i = i + 1)
                {
                    if (s1[i] != s2[i])
                    {
                        return s1[i] - s2[i];
                    };
                    if (s1[i] == 0)
                    {
                        return 0;
                    };
                };
                return 0;
            };
            
            // Case-insensitive compare
            def compare_ignore_case(byte* s1, byte* s2) -> int
            {
                int i;
                char c1, c2;
                while (s1[i] != 0 & s2[i] != 0)
                {
                    c1 = to_lower(s1[i]);
                    c2 = to_lower(s2[i]);
                    if (c1 != c2)
                    {
                        return c1 - c2;
                    };
                    i = i + 1;
                };
                return to_lower(s1[i]) - to_lower(s2[i]);
            };
            
            // Check if string starts with prefix
            def starts_with(byte* str, byte* prefix) -> bool
            {
                int i;
                while (prefix[i] != 0)
                {
                    if (str[i] != prefix[i])
                    {
                        return false;
                    };
                    i = i + 1;
                };
                return true;
            };
            
            // Check if string ends with suffix
            def ends_with(byte* str, byte* suffix) -> bool
            {
                int str_len, suffix_len;
                while (str[str_len] != 0) { str_len = str_len + 1; };
                while (suffix[suffix_len] != 0) { suffix_len = suffix_len + 1; };
                
                if (suffix_len > str_len)
                {
                    return false;
                };
                
                int offset = str_len - suffix_len;
                for (int i = 0; i < suffix_len; i = i + 1)
                {
                    if (str[offset + i] != suffix[i])
                    {
                        return false;
                    };
                };
                return true;
            };
        };
        
        // ===== STRING COPYING/MANIPULATION =====
        namespace manip
        {
            // Copy string (allocates new buffer)
            def copy_string(byte* src) -> byte*
            {
                int len = 0;
                while (src[len] != 0) { len = len + 1; };
                
                byte* dest = fmalloc((u64)len + 1);
                if (dest == 0)
                {
                    return (byte*)0;
                };
                
                for (int i = 0; i <= len; i = i + 1)
                {
                    dest[i] = src[i];
                };
                
                return dest;
            };

            // Copy n characters (allocates new buffer with null terminator)
            def copy_n(byte* src, int n) -> byte*
            {
                byte* dest = fmalloc((u64)n + 1);
                if (dest == 0)
                {
                    return (byte*)0;
                };
                
                for (int i = 0; i < n & src[i] != 0; i = i + 1)
                {
                    dest[i] = src[i];
                };
                dest[n] = (byte)0;
                
                return dest;
            };
            
            // Extract substring (allocates new buffer)
            def substring(byte* str, int start, int length) -> byte*
            {
                byte* result = fmalloc((u64)length + 1);
                if (result == 0)
                {
                    return (byte*)0;
                };
                
                for (int i = 0; i < length & str[start + i] != 0; i = i + 1)
                {
                    result[i] = (byte)str[start + i];
                };
                result[length] = (byte)0;
                
                return result;
            };
            
            // Concatenate two strings (allocates new buffer)
            def concat(byte* s1, byte* s2) -> byte*
            {
                int len1 = 0;
                while (s1[len1] != 0) { len1 = len1 + 1; };
                
                int len2 = 0;
                while (s2[len2] != 0) { len2 = len2 + 1; };
                
                byte* result = fmalloc((u64)len1 + len2 + 1);
                if (result == 0)
                {
                    return (byte*)0;
                };
                
                for (int i = 0; i < len1; i = i + 1)
                {
                    result[i] = s1[i];
                };
                for (int i = 0; i < len2; i = i + 1)
                {
                    result[len1 + i] = s2[i];
                };
                result[len1 + len2] = (byte)0;
                
                return result;
            };
        };
        
        
        // ===== STRING PARSING =====
        
        // Parse integer from string
        // Returns the parsed value, updates *end_pos to position after last digit
        def parse_int(byte* str, int start_pos, int* end_pos) -> int
        {
            int pos = helpers::skip_whitespace(str, start_pos);
            
            bool negative = false;
            if (str[pos] == '-')
            {
                negative = true;
                pos = pos + 1;
            }
            elif (str[pos] == '+')
            {
                pos = pos + 1;
            };
            
            int value = 0;
            while (helpers::is_digit(str[pos]))
            {
                value = value * 10 + (str[pos] - '0');
                pos = pos + 1;
            };
            
            *end_pos = pos;
            
            if (negative)
            {
                return -value;
            };
            return value;
        };
        
        // Parse hex integer (expects 0x prefix)
        def parse_hex(byte* str, int start_pos, int* end_pos) -> int
        {
            int pos = helpers::skip_whitespace(str, start_pos);
            
            // Skip 0x prefix
            if (str[pos] == '0' & (str[pos + 1] == 'x' | str[pos + 1] == 'X'))
            {
                pos = pos + 2;
            };
            
            int value, digit;
            while (helpers::is_hex_digit(str[pos]))
            {
                digit = helpers::hex_to_int(str[pos]);
                value = value * 16 + digit;
                pos = pos + 1;
            };
            
            *end_pos = pos;
            return value;
        };
        
        
        // ===== LINE/WORD OPERATIONS =====
        
        // Count lines in string
        def count_lines(byte* str) -> int
        {
            int count;
            for (int i; str[i] != 0; i = i + 1)
            {
                if (str[i] == '\n')
                {
                    count = count + 1;
                };
            };
            // Add 1 if string doesn't end with newline and isn't empty
            if (count > 0 | str[0] != 0)
            {
                count = count + 1;
            };
            return count;
        };
        
        // Get line at specific index (0-based)
        // Returns allocated string or null
        // Caller must free returned string
        def get_line(byte* str, int line_num) -> byte*
        {
            int current_line = 0;
            int line_start = 0;
            
            // Find start of target line
            for (int i = 0; str[i] != 0; i = i + 1)
            {
                if (current_line == line_num)
                {
                    line_start = i;
                    break;
                };
                if (str[i] == '\n')
                {
                    current_line = current_line + 1;
                };
            };
            
            if (current_line != line_num)
            {
                return (byte*)0; // Line not found
            };
            
            // Find end of line
            int line_end = line_start;
            while (str[line_end] != 0 & str[line_end] != '\n')
            {
                line_end = line_end + 1;
            };
            
            // Copy line
            int line_len = line_end - line_start;
            return manip::substring(str, line_start, line_len);
        };
        
        // Count words (whitespace-separated)
        def count_words(byte* str) -> int
        {
            int count = 0;
            bool in_word = false;
            
            for (int i = 0; str[i] != 0; i = i + 1)
            {
                if (helpers::is_whitespace(str[i]))
                {
                    in_word = false;
                }
                elif (!in_word)
                {
                    in_word = true;
                    count = count + 1;
                };
            };
            
            return count;
        };

        
        // ===== REPLACEMENT =====
        
        // Replace first occurrence of 'find' with 'replace'
        // Returns new allocated string
        def replace_first(byte* str, byte* find, byte* replace) -> byte*
        {
            int pos = helpers::find_substring(str, find, 0);
            if (pos == -1)
            {
                return manip::copy_string(str);
            };
            
            int str_len = 0;
            while (str[str_len] != 0) { str_len = str_len + 1; };
            
            int find_len = 0;
            while (find[find_len] != 0) { find_len = find_len + 1; };
            
            int replace_len = 0;
            while (replace[replace_len] != 0) { replace_len = replace_len + 1; };
            
            int new_len = str_len - find_len + replace_len;
            byte* result = fmalloc((u64)new_len + 1);
            if (result == 0)
            {
                return (byte*)0;
            };
            
            // Copy before match
            for (int i = 0; i < pos; i = i + 1)
            {
                result[i] = str[i];
            };
            
            // Copy replacement
            for (int i = 0; i < replace_len; i = i + 1)
            {
                result[pos + i] = replace[i];
            };
            
            // Copy after match
            for (int i = pos + find_len; i <= str_len; i = i + 1)
            {
                result[i - find_len + replace_len] = str[i];
            };
            
            return result;
        };
        
        
        // ===== TOKENIZATION HELPERS (for lexer) =====
        namespace tokenization
        {
            // Skip until character found or end of string
            def skip_until(byte* str, int pos, char ch) -> int
            {
                while (str[pos] != 0 & str[pos] != ch)
                {
                    pos = pos + 1;
                };
                return pos;
            };
            
            // Skip while condition is true
            def skip_while_digit(byte* str, int pos) -> int
            {
                while (str[pos] != 0 & helpers::is_digit(str[pos]))
                {
                    pos = pos + 1;
                };
                return pos;
            };
            
            def skip_while_alnum(byte* str, int pos) -> int
            {
                while (str[pos] != 0 & helpers::is_alnum(str[pos]))
                {
                    pos = pos + 1;
                };
                return pos;
            };
            
            def skip_while_identifier(byte* str, int pos) -> int
            {
                while (str[pos] != 0 & helpers::is_identifier_char(str[pos]))
                {
                    pos = pos + 1;
                };
                return pos;
            };
            
            // Match at position (doesn't advance, just checks)
            def match_at(byte* str, int pos, byte* pattern) -> bool
            {
                int i = 0;
                while (pattern[i] != 0)
                {
                    if (str[pos + i] != pattern[i])
                    {
                        return false;
                    };
                    i = i + 1;
                };
                return true;
            };
        };
    };
};

def find_last_substring(byte* str, byte* substr) -> int
{
    if (str == 0 | substr == 0)
    {
        return -1;
    };
    
    int str_len = standard::strings::strlen(str);
    int sub_len = standard::strings::strlen(substr);
    
    if (sub_len == 0)
    {
        return str_len;  // Empty substring found at end
    };
    
    if (sub_len > str_len)
    {
        return -1;
    };
    
    // Start from the end and work backwards
    bool found = true;
    for (int i = str_len - sub_len; i >= 0; i = i - 1)
    {
        found = true;
        
        // Check if substring matches at position i
        for (int j = 0; j < sub_len; j = j + 1)
        {
            if (str[i + j] != substr[j])
            {
                found = false;
                break;
            };
        };
        
        if (found)
        {
            return i;
        };
    };
    
    return -1;
};

def find_last_char(byte* str, char ch) -> int
{
    if (str == 0)
    {
        return -1;
    };
    
    int len = standard::strings::strlen(str);
    
    // Start from the end and work backwards
    for (int i = len - 1; i >= 0; i = i - 1)
    {
        if ((char)str[i] == ch)
        {
            return i;
        };
    };
    
    return -1;
};

def count_substring(byte* str, byte* substr) -> int
{
    if (str == 0 | substr == 0)
    {
        return 0;
    };
    
    int str_len = standard::strings::strlen(str);
    int sub_len = standard::strings::strlen(substr);
    
    if (sub_len == 0 | sub_len > str_len)
    {
        return 0;
    };
    
    int count = 0;
    int pos = 0;
    
    bool found = true;
    while (pos <= str_len - sub_len)
    {
        found = true;
        // Check if substring matches at current position
        for (int j = 0; j < sub_len; j = j + 1)
        {
            if (str[pos + j] != substr[j])
            {
                found = false;
                break;
            };
        };
        
        if (found)
        {
            count = count + 1;
            pos = pos + sub_len;  // Move past this occurrence to avoid overlapping
        }
        else
        {
            pos = pos + 1;  // Move to next character
        };
    };
    
    return count;
};

def !!strstr(byte* haystack, byte* needle) -> byte*
{
    // Handle null inputs
    if (haystack == 0 | needle == 0)
    {
        return (byte*)0;
    };
    
    // Empty needle matches at the beginning
    if (needle[0] == 0)
    {
        return haystack;
    };
    
    // Get first character of needle for quick rejection
    byte first_char = needle[0];
    
    // Get needle length
    int needle_len = 0;
    while (needle[needle_len] != 0)
    {
        needle_len = needle_len + 1;
    };
    
    // Special case: single character needle
    if (needle_len == 1)
    {
        for (int i; haystack[i] != 0; i = i + 1)
        {
            if (haystack[i] == first_char)
            {
                return haystack + i;
            };
        };
        return (byte*)0;
    };
    
    // Multi-character needle search
    int h;
    bool match = true;
    while (haystack[h] != 0)
    {
        // Quick first-character check
        if (haystack[h] == first_char)
        {
            // Check remaining characters
            match = true;            
            for (int n = 1; n < needle_len; n = n + 1)
            {
                if (haystack[h + n] == 0)
                {
                    // Ran out of haystack
                    return (byte*)0;
                };
                
                if (haystack[h + n] != needle[n])
                {
                    match = false;
                    break;
                };
            };
            
            if (match)
            {
                return haystack + h;
            };
        };
        
        h = h + 1;
    };
    
    return (byte*)0;
};

#endif;