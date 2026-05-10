// Author: Karac V. Thweatt

#ifndef FLUX_STANDARD_MATH
#import "math.fx";
#endif;

#ifndef FLUX_BIG_INTEGERS
#def FLUX_BIG_INTEGERS 1;

struct BigInt
{
    uint[128] digits;    // Can hold up to 4096 bits (128 * 32)
    uint length;         // Number of uint digits actually used
    bool negative;      // Sign: false = positive, true = negative
};

namespace math
{
    namespace bigint
    {
        def print_u64_decimal(u64 value) -> void,
            bigint_shl(BigInt* result, BigInt* a, uint n) -> void;

        // Initialize a BigInt to zero
        def bigint_zero(BigInt* num) -> void
        {
            uint* nd = @num.digits[0];
            uint i;
            uint old_len = num.length;
            if (old_len < 1) { old_len = 1; };
            for (i = 0; i < old_len; i++)
            {
                nd[i] = 0;
            };
            num.length = 1;
            num.negative = false;
            return;
        };
        
        // Initialize a BigInt to one
        def bigint_one(BigInt* num) -> void
        {
            uint* nd = @num.digits[0];
            uint i;
            uint old_len = num.length;
            if (old_len < 1) { old_len = 1; };
            nd[0] = 1;
            for (i = 1; i < old_len; i++)
            {
                nd[i] = 0;
            };
            num.length = 1;
            num.negative = false;
            return;
        };
        
        // Create a BigInt from a uint value
        def bigint_from_uint(BigInt* num, uint value) -> void
        {
            uint* nd = @num.digits[0];
            uint i;
            uint old_len = num.length;
            if (old_len < 1) { old_len = 1; };
            nd[0] = value;
            for (i = 1; i < old_len; i++)
            {
                nd[i] = 0;
            };
            num.length = 1;
            num.negative = false;
            return;
        };
        
        // Create a BigInt from a u64 value
        def bigint_from_u64(BigInt* num, u64 value) -> void
        {
            uint* nd = @num.digits[0];
            uint i;
            uint old_len = num.length;
            if (old_len < 2) { old_len = 2; };
            nd[0] = (uint)(value & 0xFFFFFFFF);
            nd[1] = (uint)(value >> 32);
            for (i = 2; i < old_len; i++)
            {
                nd[i] = 0;
            };
            if (nd[1] != 0)
            {
                num.length = 2;
            }
            else
            {
                num.length = 1;
            };
            num.negative = false;
            return;
        };
        
        // Check if BigInt is zero
        def bigint_is_zero(BigInt* num) -> bool
        {
            uint* nd = @num.digits[0];
            if (num.length == 1)
            {
                if (nd[0] == 0)
                {
                    return true;
                };
            };
            return false;
        };
        
        // Check if BigInt is one
        def bigint_is_one(BigInt* num) -> bool
        {
            uint* nd = @num.digits[0];
            if (num.negative)
            {
                return false;
            };
            
            if (num.length == 1)
            {
                if (nd[0] == 1)
                {
                    return true;
                };
            };
            
            return false;
        };
        
        // Print a single hex digit
        def print_hex_digit(uint digit) -> void
        {
            if (digit < 10)
            {
                standard::io::console::print((byte)('0' + digit));
            }
            else
            {
                standard::io::console::print((byte)('a' + (digit - 10)));
            };
            return;
        };
        
        // Print BigInt in hexadecimal format (for debugging)
        def bigint_print_hex(BigInt* num) -> void
        {
            uint* nd = @num.digits[0];
            if (num.negative)
            {
                standard::io::console::print("-\0");
            };
            
            standard::io::console::print("0x\0");
            
            // Print from most significant to least significant
            uint digit, j, nibble;
            uint i = num.length;
            while (i > 0)
            {
                i--;
                
                digit = nd[i];
                
                // Print all 8 hex digits for this uint
                for (j = 0; j < 8; j++)
                {
                    nibble = (digit >> (28 - j * 4)) & 0xF;
                    print_hex_digit(nibble);
                };
                
                // Add separator between digits for readability
                if (i > 0)
                {
                    standard::io::console::print("_\0");
                };
            };
            
            return;
        };
        
        // Print BigInt in decimal format (simple version - converts to decimal string)
        // Note: This is a simplified version that only works for small numbers
        // We'll implement full decimal conversion later with division
        def bigint_print(BigInt* num) -> void
        {
            if (num.negative)
            {
                standard::io::console::print("-\0");
            };
            
            // For now, only handle numbers that fit in u64
            if (num.length > 2)
            {
                standard::io::console::print("[Large number - use hex print]\0");
                return;
            };
            
            uint* nd = @num.digits[0];
            u64 value;
            if (num.length == 2)
            {
                value = ((u64)nd[1] << 32) | (u64)nd[0];
            }
            else
            {
                value = (u64)nd[0];
            };
            
            // Print as u64
            print_u64_decimal(value);
            
            return;
        };
        
        // Copy one BigInt to another
        def bigint_copy(BigInt* dest, BigInt* src) -> void
        {
            uint* dd = @dest.digits[0];
            uint* sd = @src.digits[0];
            uint i;
            uint src_len  = src.length;
            uint dest_len = dest.length;
            // Copy the active limbs
            for (i = 0; i < src_len; i++)
            {
                dd[i] = sd[i];
            };
            // Zero any limbs dest had beyond src's length
            if (dest_len > src_len)
            {
                for (i = src_len; i < dest_len; i++)
                {
                    dd[i] = 0;
                };
            };
            dest.length   = src_len;
            dest.negative = src.negative;
            return;
        };

        // Normalize: remove leading zero digits, ensure length >= 1
        def bigint_normalize(BigInt* num) -> void
        {
            uint* nd = @num.digits[0];
            uint top_idx;
            while (num.length > 1)
            {
                top_idx = num.length - 1;
                if (nd[top_idx] == 0)
                {
                    num.length--;
                }
                else
                {
                    break;
                };
            };
            // If the value is zero, clear sign
            if (num.length == 1)
            {
                if (nd[0] == 0)
                {
                    num.negative = false;
                };
            };
            return;
        };

        // Compare absolute values of two BigInts
        // Returns: -1 if |a| < |b|, 0 if equal, 1 if |a| > |b|
        def bigint_cmp_abs(BigInt* a, BigInt* b) -> int
        {
            uint* ad = @a.digits[0],
                 bd = @b.digits[0];
            if (a.length > b.length) { return 1; };
            if (a.length < b.length) { return -1; };

            // Same length - compare from most significant
            uint i = a.length;
            while (i > 0)
            {
                i--;
                if (ad[i] > bd[i]) { return 1; };
                if (ad[i] < bd[i]) { return -1; };
            };
            return 0;
        };

        // Compare two BigInts (signed)
        // Returns: -1 if a < b, 0 if equal, 1 if a > b
        def bigint_cmp(BigInt* a, BigInt* b) -> int
        {
            // Both zero
            if (bigint_is_zero(a) & bigint_is_zero(b)) { return 0; };

            // Sign-based shortcuts
            if (a.negative & !b.negative) { return -1; };
            if (!a.negative & b.negative) { return 1; };

            // Same sign
            if (!a.negative)
            {
                return bigint_cmp_abs(a, b);
            };
            // Both negative: larger absolute value means smaller overall
            return bigint_cmp_abs(b, a);
        };

        // Add absolute values: result = |a| + |b|  (sign not set here)
        def bigint_add_abs(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            u64 carry = 0;
            uint max_len;
            if (a.length > b.length)
            {
                max_len = a.length;
            }
            else
            {
                max_len = b.length;
            };

            uint* rd = @result.digits[0],
                 ad = @a.digits[0],
                 bd = @b.digits[0];
            uint i = 0;
            u64 sum;
            while ((i < max_len | carry != 0) & i < 128)
            {
                sum = carry;
                if (i < a.length)
                {
                    sum = sum + (u64)ad[i];
                };
                if (i < b.length)
                {
                    sum = sum + (u64)bd[i];
                };
                rd[i] = (uint)(sum & 0xFFFFFFFF);
                carry = (sum >> 32) & 0xFFFFFFFF;
                i++;
            };
            result.length = i;
            bigint_normalize(result);
            return;
        };

        // Subtract absolute values: result = |a| - |b|  (assumes |a| >= |b|, sign not set)
        def bigint_sub_abs(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            uint* rd = @result.digits[0],
                 ad = @a.digits[0],
                 bd = @b.digits[0];
            i64 borrow = 0;
            uint i;
            i64 diff;
            for (i = 0; i < a.length; i++)
            {
                diff = (i64)ad[i] - borrow;
                if (i < b.length)
                {
                    diff = diff - (i64)bd[i];
                };
                if (diff < 0)
                {
                    rd[i] = (uint)(diff + (i64)4294967296);
                    borrow = 1;
                }
                else
                {
                    rd[i] = (uint)diff;
                    borrow = 0;
                };
            };
            result.length = a.length;
            bigint_normalize(result);
            return;
        };

        // Add: result = a + b  (signed)
        def bigint_add(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            // Clear result
            bigint_zero(result);

            if (a.negative == b.negative)
            {
                // Same sign: add magnitudes, keep sign
                bigint_add_abs(result, a, b);
                result.negative = a.negative;
            }
            else
            {
                // Different signs: subtract smaller magnitude from larger
                int cmp;
                cmp = bigint_cmp_abs(a, b);
                if (cmp == 0)
                {
                    // Result is zero
                    bigint_zero(result);
                }
                elif (cmp > 0)
                {
                    bigint_sub_abs(result, a, b);
                    result.negative = a.negative;
                }
                else
                {
                    bigint_sub_abs(result, b, a);
                    result.negative = b.negative;
                };
            };
            bigint_normalize(result);
            return;
        };

        // Subtract: result = a - b  (signed)
        def bigint_sub(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            // Negate b's sign temporarily via a copy
            BigInt neg_b;
            bigint_copy(@neg_b, b);
            if (bigint_is_zero(@neg_b))
            {
                neg_b.negative = false;
            }
            else
            {
                neg_b.negative = !b.negative;
            };
            bigint_add(result, a, @neg_b);
            return;
        };

        // Schoolbook multiply: result = a * b  (unsigned magnitudes)
        def bigint_mul_schoolbook(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            bigint_zero(result);

            if (bigint_is_zero(a) | bigint_is_zero(b))
            {
                return;
            };

            uint* rd = @result.digits[0],
                 ad = @a.digits[0],
                 bd = @b.digits[0];
            uint i, j, k, res_len;
            u64 carry, prod;
            for (i = 0; i < a.length; i++)
            {
                carry = 0;
                for (j = 0; j < b.length; j++)
                {
                    prod = (u64)rd[i + j] + carry + (u64)ad[i] * (u64)bd[j];
                    rd[i + j] = (uint)(prod & 0xFFFFFFFF);
                    carry = prod >> 32;
                };
                k = i + b.length;
                while (carry != 0 & k < 128)
                {
                    prod = (u64)rd[k] + carry;
                    rd[k] = (uint)(prod & 0xFFFFFFFF);
                    carry = prod >> 32;
                    k++;
                };
                if (k > res_len) { res_len = k; };
            };
            result.length = res_len;
            bigint_normalize(result);
            return;
        };

        // Karatsuba multiply: result = a * b  (unsigned magnitudes)
        // Assumes a.length >= b.length and both non-zero, length >= KARATSUBA_THRESHOLD.
        def bigint_mul_karatsuba(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            // Threshold where Karatsuba beats schoolbook (tune if needed)
            const uint KARATSUBA_THRESHOLD = 16;

            // For small sizes, fall back to schoolbook
            if (a.length < KARATSUBA_THRESHOLD | b.length < KARATSUBA_THRESHOLD)
            {
                bigint_mul_schoolbook(result, a, b);
                return;
            };

            // Ensure a is the longer operand
            BigInt aa, bb;
            if (a.length < b.length)
            {
                bigint_copy(@aa, b);
                bigint_copy(@bb, a);
            }
            else
            {
                bigint_copy(@aa, a);
                bigint_copy(@bb, b);
            };

            uint n = aa.length,
                 m = n >> 1;  // split point

            // Split aa into a0 (low m limbs) and a1 (high)
            BigInt a0, a1, b0, b1;
            bigint_zero(@a0);
            bigint_zero(@a1);
            bigint_zero(@b0);
            bigint_zero(@b1);

            uint* aad = @aa.digits[0],
                  bbd = @bb.digits[0],
                  a0d = @a0.digits[0],
                  a1d = @a1.digits[0],
                  b0d = @b0.digits[0],
                  b1d = @b1.digits[0];

            // a0, b0: low m limbs
            for (uint i; i < m; i++)
            {
                a0d[i] = aad[i];
                b0d[i] = (i < bb.length) ? bbd[i] : 0;
            };
            a0.length = m;
            b0.length = (bb.length > m) ? m : bb.length;
            bigint_normalize(@a0);
            bigint_normalize(@b0);

            // a1, b1: high limbs
            uint a1_len = (aa.length > m) ? (aa.length - m) : 0,
                 b1_len = (bb.length > m) ? (bb.length - m) : 0;
            
            for (i = 0; i < a1_len; i++)
            {
                a1d[i] = aad[m + i];
            };
            for (i = 0; i < b1_len; i++)
            {
                b1d[i] = bbd[m + i];
            };
            a1.length = a1_len;
            b1.length = b1_len;
            bigint_normalize(@a1);
            bigint_normalize(@b1);

            // z0 = a0 * b0
            BigInt z0, z1, z2;
            bigint_zero(@z0);
            bigint_zero(@z1);
            bigint_zero(@z2);

            bigint_mul_karatsuba(@z0, @a0, @b0);

            // z2 = a1 * b1
            if (!bigint_is_zero(@a1) & !bigint_is_zero(@b1))
            {
                bigint_mul_karatsuba(@z2, @a1, @b1);
            };

            // (a0 + a1), (b0 + b1)
            BigInt a_sum, b_sum;
            bigint_zero(@a_sum);
            bigint_zero(@b_sum);
            bigint_add(@a_sum, @a0, @a1);
            bigint_add(@b_sum, @b0, @b1);

            // z1 = (a0 + a1)*(b0 + b1) - z0 - z2
            BigInt z1_tmp;
            bigint_zero(@z1_tmp);
            bigint_mul_karatsuba(@z1_tmp, @a_sum, @b_sum);

            BigInt tmp;
            bigint_zero(@tmp);
            bigint_add(@tmp, @z0, @z2);
            bigint_sub(@z1, @z1_tmp, @tmp);  // z1 = z1_tmp - (z0 + z2)

            // result = z2 * B^(2m) + z1 * B^m + z0
            bigint_zero(result);

            BigInt z1_shift, z2_shift;
            bigint_zero(@z1_shift);
            bigint_zero(@z2_shift);

            // shift by m limbs = m*32 bits
            bigint_shl(@z1_shift, @z1, m * 32);
            bigint_shl(@z2_shift, @z2, m * 64); // 2m limbs

            BigInt acc;
            bigint_zero(@acc);
            bigint_add(@acc, @z0, @z1_shift);
            bigint_add(result, @acc, @z2_shift);
            bigint_normalize(result);
            return;
        };

        // Multiply: result = a * b  (signed, uses Karatsuba for large operands)
        def bigint_mul(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            bigint_zero(result);

            if (bigint_is_zero(a) | bigint_is_zero(b))
            {
                return;
            };

            // Work on magnitudes via Karatsuba+schoolbook
            BigInt abs_a, abs_b;
            bigint_copy(@abs_a, a);
            bigint_copy(@abs_b, b);
            abs_a.negative = false;
            abs_b.negative = false;

            bigint_mul_karatsuba(result, @abs_a, @abs_b);

            // Set sign
            if (a.negative == b.negative)
            {
                result.negative = false;
            }
            else
            {
                result.negative = true;
            };

            if (bigint_is_zero(result))
            {
                result.negative = false;
            };
            return;
        };


        // Shift left by one bit in-place
        def bigint_shift_left_1(BigInt* num) -> void
        {
            uint* nd = @num.digits[0];
            uint carry,
                 new_carry,
                 len;
            for (uint i; i < num.length; i++)
            {
                new_carry = nd[i] >> 31;
                nd[i] = (nd[i] << 1) | carry;
                carry = new_carry;
            };
            if (carry != 0)
            {
                len = num.length;
                if (len < 128)
                {
                    nd[len] = carry;
                    num.length++;
                };
            };
            return;
        };

        // Shift right by one bit in-place
        def bigint_shift_right_1(BigInt* num) -> void
        {
            uint* nd = @num.digits[0];
            uint carry,
                 new_carry,
                 i = num.length;
            while (i > 0)
            {
                i--;
                new_carry = nd[i] & 1;
                nd[i] = (nd[i] >> 1) | (carry << 31);
                carry = new_carry;
            };
            bigint_normalize(num);
            return;
        };

        // Shift left by n bits: result = a << n
        def bigint_shl(BigInt* result, BigInt* a, uint n) -> void
        {
            bigint_copy(result, a);
            if (n == 0) { return; };

            uint* rd = @result.digits[0];

            // Word-at-a-time shift for the bulk
            uint word_shift = n / 32,
                 bit_shift  = n % 32,
                 old_len, new_len,
                 i,
                 src_idx,
                 carry, new_carry;

            if (word_shift > 0)
            {
                // Move existing limbs up by word_shift positions
                old_len = result.length;
                new_len = old_len + word_shift;
                if (new_len > 128) { new_len = 128; };
                i = new_len;
                while (i > word_shift)
                {
                    i--;
                    src_idx = i - word_shift;
                    rd[i] = rd[src_idx];
                };
                // Zero the low word_shift limbs
                for (uint j; j < word_shift; j++)
                {
                    rd[j] = 0;
                };
                result.length = new_len;
            };

            // Remaining bit shift (0..31) in a single pass
            if (bit_shift > 0)
            {
                for (i = 0; i < result.length; i++)
                {
                    new_carry = rd[i] >> (32 - bit_shift);
                    rd[i] = (rd[i] << bit_shift) | carry;
                    carry = new_carry;
                };
                if (carry != 0 & result.length < 128)
                {
                    rd[result.length] = carry;
                    result.length++;
                };
            };

            bigint_normalize(result);
            return;
        };

        // Shift right by n bits: result = a >> n
        def bigint_shr(BigInt* result, BigInt* a, uint n) -> void
        {
            bigint_copy(result, a);
            if (n == 0) { return; };

            uint* rd = @result.digits[0];

            // Word-at-a-time shift for the bulk
            uint word_shift = n / 32,
                 bit_shift  = n % 32,
                 new_len, i,
                 carry, new_carry;

            if (word_shift > 0)
            {
                if (word_shift >= result.length)
                {
                    bigint_zero(result);
                    return;
                };
                new_len = result.length - word_shift;
                for (i; i < new_len; i++)
                {
                    rd[i] = rd[i + word_shift];
                };
                // Zero the vacated high limbs
                for (i = new_len; i < result.length; i++)
                {
                    rd[i] = 0;
                };
                result.length = new_len;
            };

            // Remaining bit shift (0..31) in a single pass
            if (bit_shift > 0)
            {
                i = result.length;
                while (i > 0)
                {
                    i--;
                    new_carry = rd[i] << (32 - bit_shift);
                    rd[i] = (rd[i] >> bit_shift) | carry;
                    carry = new_carry;
                };
            };

            bigint_normalize(result);
            return;
        };

        // Divide: quotient = a / b, remainder = a % b  (unsigned magnitudes, signs set after)
        // Uses word-at-a-time division with single-limb fast path.
        def bigint_divmod(BigInt* quotient, BigInt* remainder, BigInt* a, BigInt* b) -> void
        {
            // Declare all locals first so they land in the IR entry block
            BigInt abs_a,
                   abs_b,
                   rem,
                   quot,
                   shifted_b,
                   tmp;

            bigint_zero(quotient);
            bigint_zero(remainder);

            if (bigint_is_zero(b))
            {
                return;
            };

            if (bigint_cmp_abs(a, b) < 0)
            {
                bigint_copy(remainder, a);
                remainder.negative = false;
                return;
            };

            bigint_copy(@abs_a, a);
            abs_a.negative = false;
            bigint_copy(@abs_b, b);
            abs_b.negative = false;

            uint* abs_b_d = @abs_b.digits[0];

            // ── Fast path: single-limb divisor ──────────────────────────
            if (abs_b.length == 1)
            {
                uint* abs_a_d = @abs_a.digits[0],
                      quot_d  = @quot.digits[0],
                      rem_d;
                u64   divisor = (u64)abs_b_d[0],
                      rem64, cur;
                bigint_zero(@quot);

                uint qi = abs_a.length;
                while (qi > 0)
                {
                    qi--;
                    cur = (rem64 << 32) | (u64)abs_a_d[qi];
                    quot_d[qi] = (uint)(cur / divisor);
                    rem64      = cur % divisor;
                };
                quot.length = abs_a.length;
                bigint_normalize(@quot);

                bigint_zero(@rem);
                rem_d = @rem.digits[0];
                rem_d[0]   = (uint)rem64;
                rem.length = 1;
                bigint_normalize(@rem);

                bigint_copy(quotient, @quot);
                bigint_copy(remainder, @rem);

                if (a.negative == b.negative) { quotient.negative  = false; }
                else                          { quotient.negative  = true;  };
                remainder.negative = a.negative;
                if (bigint_is_zero(quotient))  { quotient.negative  = false; };
                if (bigint_is_zero(remainder)) { remainder.negative = false; };
                return;
            };

            // ── Multi-limb: shift-and-subtract, one word at a time ───────
            // We align abs_b to the top of abs_a, subtract whole words worth
            // of shifted divisor rather than one bit at a time.
            bigint_zero(@rem);
            bigint_zero(@quot);

            uint* quot_d = @quot.digits[0];

            // Determine the bit length of abs_a
            uint* abs_a_d2 = @abs_a.digits[0],
                  rem_d;
            uint top_word  = abs_a_d2[abs_a.length - 1],
                 top_bits, bit,
                 bp = 31,
                 total_bits,
                 word_idx, bit_idx, the_bit,
                 q_word, q_bit;
            while (bp > 0)
            {
                if (((top_word >> bp) & 1) != 0) { break; };
                bp--;
            };
            total_bits = (abs_a.length - 1) * 32 + bp;

            rem_d = @rem.digits[0];

            // Process from MSB down, one bit at a time but with early-out
            // on remainder size to keep the inner loop short.
            bit = total_bits;
            do
            {
                bigint_shift_left_1(@rem);

                word_idx = bit / 32;
                bit_idx  = bit % 32;
                the_bit  = (abs_a_d2[word_idx] >> bit_idx) & 1;
                if (the_bit != 0)
                {
                    rem_d[0] = rem_d[0] | 1;
                };

                if (bigint_cmp_abs(@rem, @abs_b) >= 0)
                {
                    bigint_sub_abs(@rem, @rem, @abs_b);
                    q_word = bit / 32;
                    q_bit  = bit % 32;
                    quot_d[q_word] = quot_d[q_word] | (1 << q_bit);
                    if (q_word + 1 > quot.length)
                    {
                        quot.length = q_word + 1;
                    };
                };

                if (bit == 0) { break; };
                bit--;
            }
            while (true);

            bigint_normalize(@quot);
            bigint_normalize(@rem);

            bigint_copy(quotient, @quot);
            bigint_copy(remainder, @rem);

            if (a.negative == b.negative) { quotient.negative  = false; }
            else                          { quotient.negative  = true;  };
            remainder.negative = a.negative;
            if (bigint_is_zero(quotient))  { quotient.negative  = false; };
            if (bigint_is_zero(remainder)) { remainder.negative = false; };
            return;
        };

        // Divide: result = a / b
        def bigint_div(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            BigInt rem;
            bigint_divmod(result, @rem, a, b);
            return;
        };

        // Modulo: result = a % b
        def bigint_mod(BigInt* result, BigInt* a, BigInt* b) -> void
        {
            BigInt quot;
            bigint_divmod(@quot, result, a, b);
            return;
        };

        // Power: result = base ^ exp  (exp is a non-negative uint for simplicity)
        def bigint_pow_uint(BigInt* result, BigInt* base, uint exp) -> void
        {
            // Declare all locals first so they land in the IR entry block
            BigInt cur_base,
                   tmp;

            bigint_copy(@cur_base, base);
            bigint_one(result);

            if (exp == 0) { return; };

            uint e = exp;
            while (e > 0)
            {
                if ((e & 1) != 0)
                {
                    bigint_mul(@tmp, result, @cur_base);
                    bigint_copy(result, @tmp);
                };
                e = e >> 1;
                if (e > 0)
                {
                    bigint_mul(@tmp, @cur_base, @cur_base);
                    bigint_copy(@cur_base, @tmp);
                };
            };
            return;
        };

        // Modular exponentiation: result = base ^ exp mod m
        // Uses left-to-right binary (square-and-multiply) with reduction at each step.
        // Handles zero exponent, zero base, and zero modulus (returns zero).
        def bigint_modpow(BigInt* result, BigInt* base, BigInt* exp, BigInt* m) -> void
        {
            BigInt cur_base,
                   tmp,
                   rem;

            bigint_one(result);

            if (bigint_is_zero(m))
            {
                bigint_zero(result);
                return;
            };

            if (bigint_is_zero(exp))
            {
                // 0^0 = 1 by convention; any base^0 = 1
                return;
            };

            // Reduce base mod m once upfront
            bigint_mod(@cur_base, base, m);

            uint* expd = @exp.digits[0];
            uint exp_len = exp.length,
                 word;

            for (uint i; i < exp_len; i++)
            {
                word = expd[i];
                for (uint j; j < 32; j++)
                {
                    if ((word & 1) != 0)
                    {
                        bigint_mul(@tmp, result, @cur_base);
                        bigint_mod(result, @tmp, m);
                    };
                    word = word >> 1;
                    bigint_mul(@tmp, @cur_base, @cur_base);
                    bigint_mod(@cur_base, @tmp, m);
                };
            };

            return;
        };

        // Modular inverse: result = a^(-1) mod m
        // Uses the extended Euclidean algorithm.
        // Returns false if the inverse does not exist (gcd(a, m) != 1), true on success.
        // result is set to zero when inverse does not exist.
        def bigint_modinv(BigInt* result, BigInt* a, BigInt* m) -> bool
        {
            BigInt old_r, r,
                   old_s, s,
                   quot, tmp, tmp2;

            bigint_zero(result);

            if (bigint_is_zero(m))
            {
                return false;
            };

            // Reduce a mod m first so we work with a value in [0, m)
            bigint_mod(@old_r, a, m);
            old_r.negative = false;

            bigint_copy(@r, m);
            r.negative = false;

            // old_s = 1, s = 0
            bigint_one(@old_s);
            bigint_zero(@s);

            while (!bigint_is_zero(@r))
            {
                // quot = old_r / r,  tmp = old_r % r
                bigint_divmod(@quot, @tmp, @old_r, @r);

                // (old_r, r) = (r, old_r - quot * r)
                bigint_copy(@old_r, @r);
                bigint_copy(@r, @tmp);

                // (old_s, s) = (s, old_s - quot * s)
                bigint_mul(@tmp2, @quot, @s);
                bigint_sub(@tmp, @old_s, @tmp2);
                bigint_copy(@old_s, @s);
                bigint_copy(@s, @tmp);
            };

            // old_r now holds gcd(a, m)
            if (!bigint_is_one(@old_r))
            {
                // gcd != 1, no inverse exists
                return false;
            };

            // old_s is the Bezout coefficient; reduce into [0, m)
            if (old_s.negative)
            {
                bigint_add(@tmp, @old_s, m);
                // May still be negative if multiple additions needed
                while (tmp.negative)
                {
                    bigint_add(@old_s, @tmp, m);
                    bigint_copy(@tmp, @old_s);
                };
                bigint_mod(result, @tmp, m);
            }
            else
            {
                bigint_mod(result, @old_s, m);
            };

            return true;
        };

        // Convert u64 to decimal string and print it
        def print_u64_decimal(u64 value) -> void
        {
            if (value == 0)
            {
                standard::io::console::print("0\0");
                return;
            };

            // Max u64 is 20 decimal digits
            byte[21] buf;
            uint idx, pos;
            idx = 0;

            // Repeatedly divide by 10 using only uint arithmetic to avoid
            // signed division of u64 (compiler emits sdiv/srem for u64).
            // We implement 64-bit division-by-10 manually:
            //   high = value >> 32,  low = value & 0xFFFFFFFF
            //   q_high = high / 10,  r_high = high % 10
            //   combined = (r_high << 32) | low
            //   q_low = combined / 10,  remainder = combined % 10
            //   quotient = (q_high << 32) | q_low
            u64 v = value;
            uint lo, hi, r_hi, q_hi, q_lo, rem;
            u64 combined;
            while (v != 0)
            {
                hi  = (uint)(v >> 32);
                lo  = (uint)(v & 0xFFFFFFFF);
                q_hi = hi / 10;
                r_hi = hi % 10;
                combined = ((u64)r_hi << 32) | (u64)lo;
                // combined fits in 34 bits (r_hi < 10, so combined < 10 * 2^32 + 2^32 < 2^36)
                // divide combined by 10 using u64 arithmetic on a value known < 2^36
                // Since combined < 2^36, the high 32 bits of combined are < 16, safe to use uint
                q_lo = (uint)(combined / 10);
                rem  = (uint)(combined % 10);
                buf[idx] = (byte)('0' + rem);
                idx++;
                v = ((u64)q_hi << 32) | (u64)q_lo;
            };

            // Print reversed
            pos = idx;
            while (pos > 0)
            {
                pos--;
                standard::io::console::print(buf[pos]);
            };
            return;
        };

        // Print BigInt in decimal - full version using repeated division by 10^9
        def bigint_print_decimal(BigInt* num) -> void
        {
            // Declare all locals first so they land in the IR entry block
            BigInt divisor,
                   work,
                   quot,
                   rem;

            if (num.negative)
            {
                standard::io::console::print("-\0");
            };

            if (bigint_is_zero(num))
            {
                standard::io::console::print("0\0");
                return;
            };

            // Collect decimal chunks (base 10^9 = 1,000,000,000)
            // A 4096-bit number needs at most ceil(4096 * log10(2)) ~ 1234 digits, so ~138 chunks of 9
            uint[140] chunks;
            uint num_chunks = 0;

            bigint_from_uint(@divisor, 1000000000);

            bigint_copy(@work, num);
            work.negative = false;

            // Pointer to rem digits for safe element read
            uint* rem_d = @rem.digits[0];

            while (!bigint_is_zero(@work))
            {
                bigint_divmod(@quot, @rem, @work, @divisor);
                // rem_d[0] holds the remainder (0..999999999)
                chunks[num_chunks] = rem_d[0];
                num_chunks++;
                bigint_copy(@work, @quot);
            };

            // Print from most significant chunk
            uint c, d,
                 chunk_val,
                 digits_needed,
                 power,
                 digit_val;
            c = num_chunks;
            while (c > 0)
            {
                c--;
                if (c == num_chunks - 1)
                {
                    // First chunk: print without leading zeros
                    print_u64_decimal((u64)chunks[c]);
                }
                else
                {
                    // Remaining chunks: always print exactly 9 digits with leading zeros
                    chunk_val = chunks[c];
                    digits_needed = 9;
                    power = 100000000; // 10^8
                    for (d = 0; d < digits_needed; d++)
                    {
                        digit_val = chunk_val / power;
                        standard::io::console::print((byte)('0' + digit_val));
                        chunk_val = chunk_val % power;
                        power = power / 10;
                    };
                };
            };
            return;
        };
    };
};

#endif; // FLUX_BIG_INTEGERS