// Author: Karac V. Thweatt

#import "bigint.fx";

#ifndef FLUX_DECIMALS
#def FLUX_DECIMALS 1;

// ---------------------------------------------------------------------------
// Decimal  --  arbitrary-precision base-10 floating-point
//
// Representation
//   value = (-1)^negative  *  coefficient  *  10^exponent
//
//   coefficient : BigInt, always non-negative (sign is in `negative`)
//   exponent    : int   - negative means digits to the right of the decimal
//                         point (e.g. coeff=314, exp=-2  =>  3.14)
//   negative    : bool  - mirrors the sign; zero is always positive
//
// Default maximum precision: 1024 significant decimal digits.
// ---------------------------------------------------------------------------

// Number of decimal digits the coefficient may carry before rounding.
// Callers may override by writing decimal_set_precision() before any
// arithmetic.  The value must be >= 1.
int DECIMAL_PRECISION = 28;

struct Decimal
{
    BigInt coefficient;     // unsigned magnitude
    int    exponent;        // power of ten (may be negative)
    bool   negative;        // sign flag
};

namespace math
{
    namespace decimal
    {
        // ---------------------------------------------------------------
        // Precision control
        // ---------------------------------------------------------------

        def decimal_set_precision(i32 prec) -> void
        {
            if (prec < 1)
            {
                prec = 1;
            };
            DECIMAL_PRECISION = prec;
            return;
        };

        def decimal_get_precision() -> i32
        {
            return DECIMAL_PRECISION;
        };

        // ---------------------------------------------------------------
        // Internal helpers
        // ---------------------------------------------------------------

        // Count decimal digits in a BigInt (number of significant digits).
        // Returns at least 1 even for zero.
        def decimal_bigint_digit_count(BigInt* n) -> i32
        {
            if (math::bigint::bigint_is_zero(n))
            {
                return 1;
            };

            // One pass: divide by 10^9 chunks, count digits from the chunks.
            BigInt work,
                   divisor,
                   quot,
                   rem;

            math::bigint::bigint_copy(@work, n);
            work.negative = false;
            math::bigint::bigint_from_uint(@divisor, 1000000000);

            u32* rem_d = @rem.digits[0];

            i32 count     = 0;
            u32 last_chunk = 0;
            bool first    = true;

            while (!math::bigint::bigint_is_zero(@work))
            {
                math::bigint::bigint_divmod(@quot, @rem, @work, @divisor);
                last_chunk = rem_d[0];
                math::bigint::bigint_copy(@work, @quot);
                count = count + 9;
                first = false;
            };

            if (first)
            {
                return 1;
            };

            // `count` over-counts the leading chunk by up to 8.
            // Subtract the leading zeros in last_chunk.
            count = count - 9;
            if (last_chunk == 0)
            {
                count = count + 1;
            }
            else
            {
                u32 cv = last_chunk;
                while (cv > 0)
                {
                    count++;
                    cv = cv / 10;
                };
            };

            if (count < 1) { count = 1; };
            return count;
        };

        // Multiply coefficient by 10^n  (n >= 0)
        // Uses chunks of up to 10^9 (fits in a single uint) to minimise
        // the number of bigint_mul calls.
        def decimal_coeff_scale_up(BigInt* coeff, i32 n) -> void
        {
            if (n <= 0)
            {
                return;
            };

            BigInt ten,
                   pow10,
                   tmp;
            math::bigint::bigint_from_uint(@ten, 10);

            // Compute 10^n using bigint_pow_uint (fast exponentiation)
            math::bigint::bigint_pow_uint(@pow10, @ten, (uint)n);
            math::bigint::bigint_mul(@tmp, coeff, @pow10);
            math::bigint::bigint_copy(coeff, @tmp);
            return;
        };

        // Divide coefficient by 10^n, rounding half-up (n >= 0)
        def decimal_coeff_scale_down(BigInt* coeff, i32 n) -> void
        {
            if (n <= 0)
            {
                return;
            };

            // Compute 10^n once, then do a single divmod + half-up round.
            // This avoids n sequential bigint divisions for large n.
            BigInt ten,
                   pow10,
                   tmp,
                   rem,
                   two_rem,
                   two,
                   one,
                   rounded;
            math::bigint::bigint_from_uint(@ten, 10);
            math::bigint::bigint_pow_uint(@pow10, @ten, (uint)n);
            math::bigint::bigint_divmod(@tmp, @rem, coeff, @pow10);

            // Half-up rounding: if 2*rem >= 10^n, round up
            math::bigint::bigint_from_uint(@two, 2);
            math::bigint::bigint_mul(@two_rem, @rem, @two);
            if (math::bigint::bigint_cmp_abs(@two_rem, @pow10) >= 0)
            {
                math::bigint::bigint_one(@one);
                math::bigint::bigint_add(@rounded, @tmp, @one);
                math::bigint::bigint_copy(coeff, @rounded);
            }
            else
            {
                math::bigint::bigint_copy(coeff, @tmp);
            };
            return;
        };

        // Remove trailing decimal zeros from coefficient, adjusting exponent.
        // E.g. coeff=1230, exp=-3  =>  coeff=123, exp=-2
        def decimal_trim_zeros(Decimal* d) -> void
        {
            BigInt chunk_div,
                   quot,
                   rem;

            // Fast path: strip trailing zeros 9 at a time using 10^9 chunks,
            // then fall through to single-digit stripping for the remainder.
            math::bigint::bigint_from_uint(@chunk_div, 1000000000);
            u32* rem_d = @rem.digits[0];

            while (!math::bigint::bigint_is_zero(@d.coefficient))
            {
                math::bigint::bigint_divmod(@quot, @rem, @d.coefficient, @chunk_div);
                if (rem_d[0] != 0)
                {
                    break;
                };
                math::bigint::bigint_copy(@d.coefficient, @quot);
                d.exponent = d.exponent + 9;
            };

            // Now strip remaining single trailing zeros
            BigInt ten;
            math::bigint::bigint_from_uint(@ten, 10);

            while (!math::bigint::bigint_is_zero(@d.coefficient))
            {
                math::bigint::bigint_divmod(@quot, @rem, @d.coefficient, @ten);
                if (rem_d[0] != 0)
                {
                    break;
                };
                math::bigint::bigint_copy(@d.coefficient, @quot);
                d.exponent = d.exponent + 1;
            };
            return;
        };

        // Apply precision limit: if coefficient has more than DECIMAL_PRECISION
        // digits, scale it down and raise exponent accordingly.
        def decimal_apply_precision(Decimal* d) -> void
        {
            // Fast upper bound check first
            i32 limbs = (i32)d.coefficient.length;
            i32 upper_bound = limbs * 10;  // 10 decimal digits per 32-bit limb
            if (upper_bound <= DECIMAL_PRECISION)
            {
                return;  // Definitely within precision, skip expensive count
            };
            // Only do the expensive exact count when we might be over
            i32 digits = decimal_bigint_digit_count(@d.coefficient);
            i32 excess = digits - DECIMAL_PRECISION;
            if (excess > 0)
            {
                decimal_coeff_scale_down(@d.coefficient, excess);
                d.exponent = d.exponent + excess;
            };
            if (math::bigint::bigint_is_zero(@d.coefficient))
            {
                d.negative = false;
            };
            return;
        };

        // Align two decimals to the same exponent (the smaller one).
        // Both coefficients are scaled up so neither loses information.
        // After this call both d1 and d2 share the same exponent.
        def decimal_align(Decimal* d1, Decimal* d2) -> void
        {
            if (d1.exponent == d2.exponent)
            {
                return;
            };

            // Maximum digits a BigInt can hold: 128 limbs * 9 digits each
            i32 max_digits = 1152;

            if (d1.exponent > d2.exponent)
            {
                // d1 has larger exponent: need to scale d1 up (or d2 down)
                i32 diff = d1.exponent - d2.exponent;
                i32 d1_digits = decimal_bigint_digit_count(@d1.coefficient);
                i32 headroom = max_digits - d1_digits;
                if (diff <= headroom)
                {
                    // Safe: scale d1 up
                    decimal_coeff_scale_up(@d1.coefficient, diff);
                    d1.exponent = d2.exponent;
                }
                else
                {
                    // diff too large: scale d1 up as much as safe, then
                    // scale d2 down the rest (dropping low-order digits)
                    if (headroom > 0)
                    {
                        decimal_coeff_scale_up(@d1.coefficient, headroom);
                        d1.exponent = d1.exponent - headroom;
                    };
                    i32 remaining = d1.exponent - d2.exponent;
                    decimal_coeff_scale_down(@d2.coefficient, remaining);
                    d2.exponent = d1.exponent;
                };
            }
            else
            {
                // d2 has larger exponent: need to scale d2 up (or d1 down)
                i32 diff = d2.exponent - d1.exponent,
                    d2_digits = decimal_bigint_digit_count(@d2.coefficient),
                    headroom = max_digits - d2_digits;
                if (diff <= headroom)
                {
                    // Safe: scale d2 up
                    decimal_coeff_scale_up(@d2.coefficient, diff);
                    d2.exponent = d1.exponent;
                }
                else
                {
                    // diff too large: scale d2 up as much as safe, then
                    // scale d1 down the rest
                    if (headroom > 0)
                    {
                        decimal_coeff_scale_up(@d2.coefficient, headroom);
                        d2.exponent = d2.exponent - headroom;
                    };
                    i32 remaining = d2.exponent - d1.exponent;
                    decimal_coeff_scale_down(@d1.coefficient, remaining);
                    d1.exponent = d2.exponent;
                };
            };
            return;
        };

        // ---------------------------------------------------------------
        // Initialisation
        // ---------------------------------------------------------------

        // Initialise to zero
        def decimal_zero(Decimal* d) -> void
        {
            math::bigint::bigint_zero(@d.coefficient);
            d.exponent = 0;
            d.negative = false;
            return;
        };

        // Initialise to one
        def decimal_one(Decimal* d) -> void
        {
            math::bigint::bigint_one(@d.coefficient);
            d.exponent = 0;
            d.negative = false;
            return;
        };

        // Copy
        def decimal_copy(Decimal* dest, Decimal* src) -> void
        {
            math::bigint::bigint_copy(@dest.coefficient, @src.coefficient);
            dest.exponent = src.exponent;
            dest.negative = src.negative;
            return;
        };

        // Create from a signed 64-bit integer
        def decimal_from_i64(Decimal* d, i64 value) -> void
        {
            if (value < 0)
            {
                d.negative = true;
                // Negate carefully to avoid overflow of i64 min
                u64 abs_val = (u64)(-(value + 1)) + 1;
                math::bigint::bigint_from_u64(@d.coefficient, abs_val);
            }
            else
            {
                d.negative = false;
                math::bigint::bigint_from_u64(@d.coefficient, (u64)value);
            };
            d.exponent = 0;
            return;
        };

        // Create from a u64 value
        def decimal_from_u64(Decimal* d, u64 value) -> void
        {
            math::bigint::bigint_from_u64(@d.coefficient, value);
            d.exponent = 0;
            d.negative = false;
            return;
        };

        // Create from a decimal string, e.g. "-3.14", "1E+10", "0.001"
        // Supports: optional leading '-' or '+', digits, optional '.', optional
        //           'e'/'E' followed by optional '+'/'-' and digits.
        def decimal_from_string(Decimal* d, byte* s) -> void
        {
            decimal_zero(d);

            // --- parse sign ---
            i32 idx = 0;
            bool neg = false;
            if (s[idx] == '-')
            {
                neg = true;
                idx++;
            }
            elif (s[idx] == '+')
            {
                idx++;
            };

            // --- parse integer and fractional parts ---
            // Accumulate digits in chunks of up to 9 (fits in a u32) and
            // call bigint_mul/add once per chunk to minimise bigint operations.
            i32 frac_digits = 0;      // digits after the dot
            bool in_frac    = false;

            BigInt chunk_mul,
                   chunk_bi,
                   tmp;
            math::bigint::bigint_zero(@d.coefficient);

            u32 chunk_acc;    // native accumulator for current chunk
            i32 chunk_size;   // how many digits are in chunk_acc
            byte ch;

            while (s[idx] != 0 & s[idx] != 'e' & s[idx] != 'E')
            {
                ch = s[idx];
                if (ch == '.')
                {
                    in_frac = true;
                    idx++;
                    continue;
                };

                if (ch < '0' | ch > '9')
                {
                    // Unexpected character – stop
                    break;
                };

                chunk_acc  = chunk_acc * 10 + (u32)(ch - '0');
                chunk_size = chunk_size + 1;

                if (in_frac)
                {
                    frac_digits++;
                };

                // Flush a full chunk of 9 digits into the BigInt coefficient.
                if (chunk_size == 9)
                {
                    math::bigint::bigint_from_uint(@chunk_mul, 1000000000);
                    math::bigint::bigint_mul(@tmp, @d.coefficient, @chunk_mul);
                    math::bigint::bigint_from_uint(@chunk_bi, chunk_acc);
                    math::bigint::bigint_add(@d.coefficient, @tmp, @chunk_bi);
                    chunk_acc  = 0;
                    chunk_size = 0;
                };

                idx++;
            };

            // Flush any remaining partial chunk
            if (chunk_size > 0)
            {
                // pow10 for partial chunk
                u32 partial_pow = 1;
                i32 pi;
                for (pi = 0; pi < chunk_size; pi++)
                {
                    partial_pow = partial_pow * 10;
                };
                math::bigint::bigint_from_uint(@chunk_mul, partial_pow);
                math::bigint::bigint_mul(@tmp, @d.coefficient, @chunk_mul);
                math::bigint::bigint_from_uint(@chunk_bi, chunk_acc);
                math::bigint::bigint_add(@d.coefficient, @tmp, @chunk_bi);
            };

            // exponent so far: -frac_digits (each fractional digit divides by 10)
            d.exponent = -frac_digits;

            // --- parse optional exponent ---
            if (s[idx] == 'e' | s[idx] == 'E')
            {
                idx++;
                bool exp_neg = false;
                if (s[idx] == '-')
                {
                    exp_neg = true;
                    idx++;
                }
                elif (s[idx] == '+')
                {
                    idx++;
                };

                i32 exp_val = 0;
                while (s[idx] != 0)
                {
                    ch = s[idx];
                    if (ch < '0' | ch > '9')
                    {
                        break;
                    };
                    exp_val = exp_val * 10 + (i32)(ch - '0');
                    idx++;
                };

                if (exp_neg)
                {
                    d.exponent = d.exponent - exp_val;
                }
                else
                {
                    d.exponent = d.exponent + exp_val;
                };
            };

            // --- sign ---
            if (math::bigint::bigint_is_zero(@d.coefficient))
            {
                d.negative = false;
            }
            else
            {
                d.negative = neg;
            };

            decimal_apply_precision(d);
            return;
        };

        // ---------------------------------------------------------------
        // Predicates
        // ---------------------------------------------------------------

        def decimal_is_zero(Decimal* d) -> bool
        {
            return math::bigint::bigint_is_zero(@d.coefficient);
        };

        def decimal_is_negative(Decimal* d) -> bool
        {
            return d.negative & !decimal_is_zero(d);
        };

        def decimal_is_positive(Decimal* d) -> bool
        {
            return !d.negative & !decimal_is_zero(d);
        };

        // ---------------------------------------------------------------
        // Comparison
        // ---------------------------------------------------------------

        // Compare magnitudes only (ignores sign).
        // Returns: -1, 0, or 1
        def decimal_cmp_abs(Decimal* a, Decimal* b) -> i32
        {
            // Make aligned copies so we can compare coefficients
            Decimal ta, tb;
            decimal_copy(@ta, a);
            decimal_copy(@tb, b);
            decimal_align(@ta, @tb);
            return math::bigint::bigint_cmp_abs(@ta.coefficient, @tb.coefficient);
        };

        // Signed compare.  Returns: -1 if a < b, 0 if a == b, 1 if a > b
        def decimal_cmp(Decimal* a, Decimal* b) -> i32
        {
            bool az = decimal_is_zero(a),
                 bz = decimal_is_zero(b);

            if (az & bz) { return 0; };

            if (a.negative & !b.negative) { return -1; };
            if (!a.negative & b.negative) { return 1; };

            i32 abs_cmp = decimal_cmp_abs(a, b);

            if (!a.negative)
            {
                return abs_cmp;
            };
            // Both negative: larger absolute value is the smaller number
            return -abs_cmp;
        };

        // ---------------------------------------------------------------
        // Arithmetic
        // ---------------------------------------------------------------

        // result = a + b
        def decimal_add(Decimal* result, Decimal* a, Decimal* b) -> void
        {
            Decimal ta,
                    tb;
            decimal_copy(@ta, a);
            decimal_copy(@tb, b);
            decimal_align(@ta, @tb);

            decimal_zero(result);
            result.exponent = ta.exponent;

            if (ta.negative == tb.negative)
            {
                // Same sign: add magnitudes
                math::bigint::bigint_add_abs(@result.coefficient, @ta.coefficient, @tb.coefficient);
                result.negative = ta.negative;
            }
            else
            {
                // Different signs: subtract smaller from larger
                i32 cmp = math::bigint::bigint_cmp_abs(@ta.coefficient, @tb.coefficient);
                if (cmp == 0)
                {
                    // Result is zero
                    math::bigint::bigint_zero(@result.coefficient);
                    result.negative = false;
                }
                elif (cmp > 0)
                {
                    math::bigint::bigint_sub_abs(@result.coefficient, @ta.coefficient, @tb.coefficient);
                    result.negative = ta.negative;
                }
                else
                {
                    math::bigint::bigint_sub_abs(@result.coefficient, @tb.coefficient, @ta.coefficient);
                    result.negative = tb.negative;
                };
            };

            if (math::bigint::bigint_is_zero(@result.coefficient))
            {
                result.negative = false;
            };

            decimal_apply_precision(result);
            return;
        };

        // result = a - b
        def decimal_sub(Decimal* result, Decimal* a, Decimal* b) -> void
        {
            Decimal neg_b;
            decimal_copy(@neg_b, b);
            if (!decimal_is_zero(@neg_b))
            {
                neg_b.negative = !b.negative;
            };
            decimal_add(result, a, @neg_b);
            return;
        };

        // result = a * b
        def decimal_mul(Decimal* result, Decimal* a, Decimal* b) -> void
        {
            decimal_zero(result);
            result.exponent = a.exponent + b.exponent;

            math::bigint::bigint_mul(@result.coefficient, @a.coefficient, @b.coefficient);

            if (a.negative == b.negative)
            {
                result.negative = false;
            }
            else
            {
                result.negative = true;
            };

            if (math::bigint::bigint_is_zero(@result.coefficient))
            {
                result.negative = false;
            };

            decimal_apply_precision(result);
            return;
        };

        // result = a / b   (to DECIMAL_PRECISION significant digits)
        // Division is performed by scaling the dividend so the quotient has
        // at least DECIMAL_PRECISION significant digits, then rounding.
        def decimal_div(Decimal* result, Decimal* a, Decimal* b) -> void
        {
            decimal_zero(result);

            if (decimal_is_zero(b))
            {
                // Division by zero – leave result as zero (caller should check)
                return;
            };

            if (decimal_is_zero(a))
            {
                return;
            };

            Decimal scaled_a;
            BigInt quot,
                   rem,
                   two_rem,
                   two,
                   one,
                   rounded;

            // We need the integer quotient (scaled_a.coeff / b.coeff) to have
            // at least DECIMAL_PRECISION significant digits.  The number of
            // digits in the quotient is approximately:
            //   digits(a.coeff) - digits(b.coeff) + scale_up
            // Solve for scale_up:
            //   scale_up = DECIMAL_PRECISION + guard - digits(a) + digits(b)
            // But also cap so that digits(a) + scale_up <= max_digits (1152).
            i32 guard      = 4,
                max_digits = 1152,
                digits_a   = decimal_bigint_digit_count(@a.coefficient),
                digits_b   = decimal_bigint_digit_count(@b.coefficient),
                scale_up   = DECIMAL_PRECISION + guard - digits_a + digits_b,
                cap        = max_digits - digits_a;
            if (scale_up > cap)
            {
                scale_up = cap;
            };
            if (scale_up < 0)
            {
                scale_up = 0;
            };

            decimal_copy(@scaled_a, a);
            decimal_coeff_scale_up(@scaled_a.coefficient, scale_up);
            // The new exponent accounts for the scaling
            i32 new_exp = a.exponent - b.exponent - scale_up;

            math::bigint::bigint_divmod(@quot, @rem, @scaled_a.coefficient, @b.coefficient);

            // Round half-up using the remainder
            // If 2*rem >= b.coefficient, round up
            math::bigint::bigint_from_uint(@two, 2);
            math::bigint::bigint_mul(@two_rem, @rem, @two);
            if (math::bigint::bigint_cmp_abs(@two_rem, @b.coefficient) >= 0)
            {
                math::bigint::bigint_one(@one);
                math::bigint::bigint_add(@rounded, @quot, @one);
                math::bigint::bigint_copy(@quot, @rounded);
            };

            math::bigint::bigint_copy(@result.coefficient, @quot);
            result.exponent = new_exp;

            if (a.negative == b.negative)
            {
                result.negative = false;
            }
            else
            {
                result.negative = true;
            };

            if (math::bigint::bigint_is_zero(@result.coefficient))
            {
                result.negative = false;
            };

            decimal_apply_precision(result);
            return;
        };

        // result = a % b   (remainder: result = a - (a // b) * b)
        def decimal_mod(Decimal* result, Decimal* a, Decimal* b) -> void
        {
            if (decimal_is_zero(b))
            {
                decimal_zero(result);
                return;
            };

            Decimal quot;
            decimal_zero(@quot);
            decimal_div(@quot, a, b);

            // Truncate to integer (remove fractional part of quotient)
            if (quot.exponent < 0)
            {
                // Scale coefficient down to remove fractional digits
                i32 remove = -quot.exponent;
                decimal_coeff_scale_down(@quot.coefficient, remove);
                quot.exponent = 0;
            };

            Decimal prod;
            decimal_mul(@prod, @quot, b);

            decimal_sub(result, a, @prod);
            return;
        };

        // result = base ^ exp   (exp is a non-negative i32)
        def decimal_pow_int(Decimal* result, Decimal* base, i32 exp) -> void
        {
            if (exp < 0)
            {
                // Negative exponent: compute 1 / base^|exp|
                Decimal pos_result;
                decimal_pow_int(@pos_result, base, -exp);
                Decimal one;
                decimal_one(@one);
                decimal_div(result, @one, @pos_result);
                return;
            };

            Decimal cur_base;
            Decimal tmp;
            decimal_copy(@cur_base, base);
            decimal_one(result);

            if (exp == 0) { return; };

            i32 e = exp;
            while (e > 0)
            {
                if ((e & 1) != 0)
                {
                    decimal_mul(@tmp, result, @cur_base);
                    decimal_copy(result, @tmp);
                };
                e = e >> 1;
                if (e > 0)
                {
                    decimal_mul(@tmp, @cur_base, @cur_base);
                    decimal_copy(@cur_base, @tmp);
                };
            };
            return;
        };

        // Negate: result = -a
        def decimal_neg(Decimal* result, Decimal* a) -> void
        {
            decimal_copy(result, a);
            if (!decimal_is_zero(result))
            {
                result.negative = !a.negative;
            };
            return;
        };

        // Absolute value: result = |a|
        def decimal_abs(Decimal* result, Decimal* a) -> void
        {
            decimal_copy(result, a);
            result.negative = false;
            return;
        };

        // Round to `places` decimal places (half-up)
        def decimal_round(Decimal* result, Decimal* a, i32 places) -> void
        {
            decimal_copy(result, a);

            // target exponent is -places
            i32 target_exp = -places;
            if (result.exponent >= target_exp)
            {
                // Already at or above target precision, nothing to do
                return;
            };

            // We need to remove (target_exp - result.exponent) digits
            i32 remove = target_exp - result.exponent;
            decimal_coeff_scale_down(@result.coefficient, remove);
            result.exponent = target_exp;

            if (math::bigint::bigint_is_zero(@result.coefficient))
            {
                result.negative = false;
            };
            return;
        };

        // Truncate toward zero to `places` decimal places
        def decimal_truncate(Decimal* result, Decimal* a, i32 places) -> void
        {
            decimal_copy(result, a);

            i32 target_exp = -places;
            if (result.exponent >= target_exp)
            {
                return;
            };

            i32 remove = target_exp - result.exponent;

            // Compute 10^remove once and do a single divmod (pure truncation, no rounding).
            BigInt ten,
                   pow10,
                   tmp,
                   rem;
            math::bigint::bigint_from_uint(@ten, 10);
            math::bigint::bigint_pow_uint(@pow10, @ten, (uint)remove);
            math::bigint::bigint_divmod(@tmp, @rem, @result.coefficient, @pow10);
            math::bigint::bigint_copy(@result.coefficient, @tmp);

            result.exponent = target_exp;

            if (math::bigint::bigint_is_zero(@result.coefficient))
            {
                result.negative = false;
            };
            return;
        };

        // Floor: largest integer <= a
        def decimal_floor(Decimal* result, Decimal* a) -> void
        {
            decimal_truncate(result, a, 0);
            // If original was negative and we discarded a fractional part,
            // subtract 1
            if (a.negative & !decimal_is_zero(a))
            {
                // Check if truncation removed anything
                Decimal expanded;
                decimal_copy(@expanded, result);
                if (expanded.exponent < a.exponent)
                {
                    // There was a fractional part
                    Decimal one;
                    decimal_one(@one);
                    Decimal tmp;
                    decimal_sub(@tmp, result, @one);
                    decimal_copy(result, @tmp);
                };
            };
            return;
        };

        // Ceiling: smallest integer >= a
        def decimal_ceil(Decimal* result, Decimal* a) -> void
        {
            decimal_truncate(result, a, 0);
            // If original was positive and we discarded a fractional part,
            // add 1
            if (!a.negative & !decimal_is_zero(a))
            {
                // Check if truncation removed anything
                Decimal restored;
                decimal_copy(@restored, result);
                if (restored.exponent < a.exponent)
                {
                    Decimal one;
                    decimal_one(@one);
                    Decimal tmp;
                    decimal_add(@tmp, result, @one);
                    decimal_copy(result, @tmp);
                };
            };
            return;
        };

        // ---------------------------------------------------------------
        // Square root  (Newton–Raphson, converges to DECIMAL_PRECISION digits)
        // ---------------------------------------------------------------
        def decimal_sqrt(Decimal* result, Decimal* a) -> void
        {
            // Declare all locals first so they land in the IR entry block
            Decimal x;
            Decimal two;
            Decimal quot;
            Decimal sum;
            Decimal x_new;

            if (a.negative)
            {
                // Square root of negative number undefined – return zero
                decimal_zero(result);
                return;
            };

            if (decimal_is_zero(a))
            {
                decimal_zero(result);
                return;
            };

            // Initial guess: 1
            decimal_one(@x);

            // x_{n+1} = (x_n + a / x_n) / 2
            decimal_from_i64(@two, 2);

            i32 max_iter = DECIMAL_PRECISION + 10;
            i32 iter;
            for (iter = 0; iter < max_iter; iter++)
            {
                // quot = a / x
                decimal_div(@quot, a, @x);

                // sum = x + quot
                decimal_add(@sum, @x, @quot);

                // x_new = sum / 2
                decimal_div(@x_new, @sum, @two);

                // Check convergence: if x_new == x, we're done
                if (decimal_cmp(@x_new, @x) == 0)
                {
                    decimal_copy(result, @x_new);
                    return;
                };

                decimal_copy(@x, @x_new);
            };

            decimal_copy(result, @x);
            return;
        };

        // ---------------------------------------------------------------
        // Conversion to primitive types
        // ---------------------------------------------------------------

        // Convert a Decimal to the nearest representable double.
        // Strategy:
        //   1. Extract the coefficient into a double accumulator via
        //      base-10^9 chunks (same approach as decimal_print).
        //   2. Scale by 10^exponent using repeated multiply/divide,
        //      clamped to [-308, +308] to stay in double range.
        //   3. Apply sign.
        def decimal_to_double(Decimal* d) -> double
        {
            if (math::bigint::bigint_is_zero(@d.coefficient))
            {
                return 0.0;
            };

            // Step 1: collect base-10^9 chunks of the coefficient.
            // Cap at 4 chunks (36 digits) - more than enough for 28-digit precision.
            BigInt work, divisor, quot, rem;
            math::bigint::bigint_copy(@work, @d.coefficient);
            work.negative = false;
            math::bigint::bigint_from_uint(@divisor, 1000000000);
            u32* rem_d = @rem.digits[0];

            u32[4] chunks;
            i32 num_chunks = 0;
            while (!math::bigint::bigint_is_zero(@work) & num_chunks < 4)
            {
                math::bigint::bigint_divmod(@quot, @rem, @work, @divisor);
                chunks[num_chunks] = rem_d[0];
                num_chunks++;
                math::bigint::bigint_copy(@work, @quot);
            };

            if (num_chunks == 0)
            {
                return 0.0;
            };

            // Step 2: build double from chunks, most-significant first.
            // result = result * 1e9 + chunk[i]
            double result = 0.0;
            double chunk_scale = 1000000000.0;
            i32 ci = num_chunks;
            while (ci > 0)
            {
                ci--;
                result = result * chunk_scale + (double)chunks[ci];
            };

            // Step 3: apply the decimal exponent.
            // Clamp to [-308, +308] to stay within double range.
            i32 exp = d.exponent,
                remaining,
                step;
            double factor;
            if (exp > 308)  { exp = 308;  };
            if (exp < -308) { exp = -308; };

            if (exp > 0)
            {
                remaining = exp;
                while (remaining > 0)
                {
                    if (remaining >= 9)      { step = 9; factor = 1000000000.0; }
                    elif (remaining >= 8)    { step = 8; factor = 100000000.0;  }
                    elif (remaining >= 7)    { step = 7; factor = 10000000.0;   }
                    elif (remaining >= 6)    { step = 6; factor = 1000000.0;    }
                    elif (remaining >= 5)    { step = 5; factor = 100000.0;     }
                    elif (remaining >= 4)    { step = 4; factor = 10000.0;      }
                    elif (remaining >= 3)    { step = 3; factor = 1000.0;       }
                    elif (remaining >= 2)    { step = 2; factor = 100.0;        }
                    else                     { step = 1; factor = 10.0;         };
                    result    = result * factor;
                    remaining = remaining - step;
                };
            }
            elif (exp < 0)
            {
                remaining = -exp;
                while (remaining > 0)
                {
                    if (remaining >= 9)      { step = 9; factor = 1000000000.0; }
                    elif (remaining >= 8)    { step = 8; factor = 100000000.0;  }
                    elif (remaining >= 7)    { step = 7; factor = 10000000.0;   }
                    elif (remaining >= 6)    { step = 6; factor = 1000000.0;    }
                    elif (remaining >= 5)    { step = 5; factor = 100000.0;     }
                    elif (remaining >= 4)    { step = 4; factor = 10000.0;      }
                    elif (remaining >= 3)    { step = 3; factor = 1000.0;       }
                    elif (remaining >= 2)    { step = 2; factor = 100.0;        }
                    else                     { step = 1; factor = 10.0;         };
                    result    = result / factor;
                    remaining = remaining - step;
                };
            };

            // Step 4: apply sign.
            if (d.negative)
            {
                result = -result;
            };

            return result;
        };

        // ---------------------------------------------------------------
        // Output / formatting
        // ---------------------------------------------------------------

        // Print a Decimal in standard notation, e.g. -3.14, 0, 100
        // Uses scientific notation only when the exponent would be extreme.
        def decimal_print(Decimal* d) -> void
        {
            if (decimal_is_zero(d))
            {
                print("0\0");
                return;
            };

            if (d.negative)
            {
                print("-\0");
            };

            // Print the coefficient as a decimal string
            // We collect digits via bigint_print_decimal then reconstruct
            // the decimal point position.
            //
            // Strategy: collect the coefficient digit string into a buffer,
            // then insert the decimal point based on exponent.
            //
            // We need a char buffer large enough for DECIMAL_PRECISION + some overhead.
            // We use a fixed 1300-byte local buffer (covers precision up to 1024 well).

            byte[1300] buf;
            i32 buf_len = 0;

            // Fill buf with decimal digits of coefficient (most-sig first)
            // by using repeated division by 10^9 chunks (same as bigint_print_decimal)
            BigInt work;
            BigInt divisor;
            BigInt quot;
            BigInt rem;
            math::bigint::bigint_copy(@work, @d.coefficient);
            work.negative = false;
            math::bigint::bigint_from_uint(@divisor, 1000000000);
            u32* rem_d = @rem.digits[0];

            // Collect base-10^9 chunks (least-significant first)
            u32[145] chunks;
            i32 num_chunks = 0;

            while (!math::bigint::bigint_is_zero(@work))
            {
                math::bigint::bigint_divmod(@quot, @rem, @work, @divisor);
                chunks[num_chunks] = rem_d[0];
                num_chunks++;
                math::bigint::bigint_copy(@work, @quot);
            };

            // Build digit string into buf (most-significant chunk first)
            i32 c = num_chunks,
                td_count, ti, dg;
            u32 power = 100000000,
                chunk_val,
                cv, cv2;
            byte[9] tmp_digits;
            while (c > 0)
            {
                c--;
                chunk_val = chunks[c];
                if (c == num_chunks - 1)
                {
                    // First chunk: no leading zeros
                    if (chunk_val == 0)
                    {
                        buf[buf_len] = '0';
                        buf_len++;
                    }
                    else
                    {
                        // Determine how many digits this chunk has
                        cv = chunk_val;
                        while (cv > 0)
                        {
                            tmp_digits[td_count] = (byte)('0' + (cv % 10));
                            td_count++;
                            cv = cv / 10;
                        };
                        // Reverse into buf
                        ti = td_count;
                        while (ti > 0)
                        {
                            ti--;
                            buf[buf_len] = tmp_digits[ti];
                            buf_len++;
                        };
                    };
                }
                else
                {
                    // Subsequent chunks: always exactly 9 digits
                    cv2 = chunk_val;
                    for (dg = 0; dg < 9; dg++)
                    {
                        buf[buf_len] = (byte)('0' + (cv2 / power));
                        cv2 = cv2 % power;
                        power = power / 10;
                        buf_len++;
                    };
                };
            };

            if (buf_len == 0)
            {
                buf[0] = '0';
                buf_len = 1;
            };

            // Now insert the decimal point.
            // value = coefficient * 10^exponent
            // The coefficient string has `buf_len` digits.
            // The decimal point sits at position (buf_len + exponent) from the left.
            // i.e. there are (buf_len + exponent) digits before the dot.
            i32 int_digits = buf_len + d.exponent;

            if (d.exponent >= 0)
            {
                // Pure integer or trailing zeros: print digits then zeros
                for (int pi; pi < buf_len; pi++)
                {
                    print(buf[pi]);
                };
                for (int zi; zi < d.exponent; zi++)
                {
                    print('0');
                };
            }
            elif (int_digits <= 0)
            {
                // All digits are fractional: 0.000...digits
                print("0.\0");
                i32 lead_zeros = -int_digits;
                for (int lz; lz < lead_zeros; lz++)
                {
                    print('0');
                };
                for (int di; di < buf_len; di++)
                {
                    print(buf[di]);
                };
            }
            else
            {
                // Mixed: some integer digits, some fractional
                for (int mi; mi < int_digits; mi++)
                {
                    print(buf[mi]);
                };
                print('.');
                for (mi = int_digits; mi < buf_len; mi++)
                {
                    print(buf[mi]);
                };
            };

            return;
        };

        // Print in engineering / scientific notation: [-]d.dddEexp
        def decimal_print_sci(Decimal* d) -> void
        {
            if (decimal_is_zero(d))
            {
                print("0E+0\0");
                return;
            };

            if (d.negative)
            {
                print("-\0");
            };

            // Collect digit buffer same as decimal_print
            byte[1300] buf;
            i32 buf_len, c, dg,
                num_chunks,
                td_count, cv, ti;
            u32 chunk_val, cv2,
                power = 100000000;
            u32[145] chunks;
            BigInt work,
                   divisor,
                   quot,
                   rem;
            math::bigint::bigint_copy(@work, @d.coefficient);
            work.negative = false;
            math::bigint::bigint_from_uint(@divisor, 1000000000);
            u32* rem_d = @rem.digits[0];


            while (!math::bigint::bigint_is_zero(@work))
            {
                math::bigint::bigint_divmod(@quot, @rem, @work, @divisor);
                chunks[num_chunks] = rem_d[0];
                num_chunks++;
                math::bigint::bigint_copy(@work, @quot);
            };

            byte[9] tmp_digits;

            c = num_chunks;
            while (c > 0)
            {
                c--;
                chunk_val = chunks[c];
                if (c == num_chunks - 1)
                {
                    if (chunk_val == 0)
                    {
                        buf[buf_len] = '0';
                        buf_len++;
                    }
                    else
                    {
                        cv = chunk_val;
                        while (cv > 0)
                        {
                            tmp_digits[td_count] = (byte)('0' + (cv % 10));
                            td_count++;
                            cv = cv / 10;
                        };
                        ti = td_count;
                        while (ti > 0)
                        {
                            ti--;
                            buf[buf_len] = tmp_digits[ti];
                            buf_len++;
                        };
                    };
                }
                else
                {
                    cv2 = chunk_val;
                    for (dg = 0; dg < 9; dg++)
                    {
                        buf[buf_len] = (byte)('0' + (cv2 / power));
                        cv2 = cv2 % power;
                        power = power / 10;
                        buf_len++;
                    };
                };
            };

            if (buf_len == 0)
            {
                buf[0] = '0';
                buf_len = 1;
            };

            // Print first digit
            print(buf[0]);

            // Print remaining digits after '.'
            if (buf_len > 1)
            {
                print('.');
                for (int di = 1; di < buf_len; di++)
                {
                    print(buf[di]);
                };
            };

            // Exponent = (buf_len - 1) + d.exponent
            i32 sci_exp = (buf_len - 1) + d.exponent;
            print('E');
            if (sci_exp >= 0)
            {
                print('+');
                print((int)sci_exp);
            }
            else
            {
                print('-');
                print((int)(-sci_exp));
            };

            return;
        };

    }; // namespace decimal
}; // namespace math

#endif; // FLUX_DECIMAL