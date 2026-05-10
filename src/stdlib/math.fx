#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_MATH
#def FLUX_STANDARD_MATH 1;
#endif;

namespace standard
{
    namespace math
    {
        const i8 PI8 = 3;
        const i16 PI16 = 3;
        const i32 PI32 = 3;
        const i64 PI64 = 3;
        const float PIF = 3.14159f;
        const double PID = 3.14159;
        
        const i8 E8 = 2;
        const i16 E16 = 2;
        const i32 E32 = 2;
        const i64 E64 = 2;
        const float EF = 2.71828f;
        const double ED = 2.71828;

        const float PI_F = 3.14159f;
        const double PI_D = 3.14159;
        const float E_F = 2.71828f;
        const double E_D = 2.71828;
        const float TAU_F = 6.28318f;
        const double TAU_D = 6.28318;
        const float PHI_F = 1.61803f;
        const double PHI_D = 1.61803;

        struct Face  { int   a, b, c;    };
        struct Edge  { int   a, b;       };
        struct POINT { int   x, y;       };

        struct Complex
        {
            double re,
                   im;
        };

        def abs(i8 x) -> i8
        {
            if (x < 0) {return -x;};
            return x;
        };
        
        def abs(i16 x) -> i16
        {
            if (x < 0) {return -x;};
            return x;
        };
        
        def abs(i32 x) -> i32
        {
            if (x < 0) {return -x;};
            return x;
        };
        
        def abs(i64 x) -> i64
        {
            if (x < 0) {return -x;};
            return x;
        };

        def abs(float x) -> float
        {
            if (x < 0.0f) {return -x;};
            return x;
        };

        def abs(double x) -> double
        {
            if (x < 0.0) {return -x;};
            return x;
        };

        def min(i8 a, i8 b) -> i8
        {
            if (a < b) {return a;};
            return b;
        };
        
        def min(i16 a, i16 b) -> i16
        {
            if (a < b) {return a;};
            return b;
        };
        
        def min(i32 a, i32 b) -> i32
        {
            if (a < b) {return a;};
            return b;
        };
        
        def min(i64 a, i64 b) -> i64
        {
            if (a < b) {return a;};
            return b;
        };

        def min(float a, float b) -> float
        {
            if (a < b) {return a;};
            return b;
        };

        def min(double a, double b) -> double
        {
            if (a < b) {return a;};
            return b;
        };

        def max(i8 a, i8 b) -> i8
        {
            if (a > b) {return a;};
            return b;
        };
        
        def max(i16 a, i16 b) -> i16
        {
            if (a > b) {return a;};
            return b;
        };
        
        def max(i32 a, i32 b) -> i32
        {
            if (a > b) {return a;};
            return b;
        };
        
        def max(i64 a, i64 b) -> i64
        {
            if (a > b) {return a;};
            return b;
        };

        def max(float a, float b) -> float
        {
            if (a > b) {return a;};
            return b;
        };

        def max(double a, double b) -> double
        {
            if (a > b) {return a;};
            return b;
        };

        def clamp(i8 value, i8 low, i8 high) -> i8
        {
            if (value < low) {return low;};
            if (value > high) {return high;};
            return value;
        };
        
        def clamp(i16 value, i16 low, i16 high) -> i16
        {
            if (value < low) {return low;};
            if (value > high) {return high;};
            return value;
        };
        
        def clamp(i32 value, i32 low, i32 high) -> i32
        {
            if (value < low) {return low;};
            if (value > high) {return high;};
            return value;
        };
        
        def clamp(i64 value, i64 low, i64 high) -> i64
        {
            if (value < low) {return low;};
            if (value > high) {return high;};
            return value;
        };
        
        def clamp(float value, float low, float high) -> float
        {
            if (value < low) {return low;};
            if (value > high) {return high;};
            return value;
        };

        def clamp(double value, double low, double high) -> double
        {
            if (value < low) {return low;};
            if (value > high) {return high;};
            return value;
        };

        def sqrt(i8 x) -> i8
        {
            if (x <= 0) {return 0;};
            i8 y = x >> 1;
            i8 prev_y;
            while (true)
            {
                prev_y = y;
                y = (y + x / y) >> 1;
                if (y >= prev_y) {break;};
            };
            return y;
        };
        
        def sqrt(i16 x) -> i16
        {
            if (x <= 0) {return 0;};
            i16 y = x >> 1;
            i16 prev_y;
            while (true)
            {
                prev_y = y;
                y = (y + x / y) >> 1;
                if (y >= prev_y) {break;};
            };
            return y;
        };
        
        def sqrt(i32 x) -> i32
        {
            if (x <= 0) {return 0;};
            i32 y = x >> 1;
            i32 prev_y;
            while (true)
            {
                prev_y = y;
                y = (y + x / y) >> 1;
                if (y >= prev_y) {break;};
            };
            return y;
        };
        
        def sqrt(i64 x) -> i64
        {
            if (x <= 0) {return 0;};
            i64 y = x >> 1;
            i64 prev_y;
            while (true)
            {
                prev_y = y;
                y = (y + x / y) >> 1;
                if (y >= prev_y) {break;};
            };
            return y;
        };
        
        def sqrt(float x) -> float
        {
            if (x <= 0.0f) {return 0.0f;};
            float y = x * 0.5f;
            float prev_y;
            for (i32 i = 0; i < 20; i++)
            {
                prev_y = y;
                y = (y + x / y) * 0.5f;
                if (abs(y - prev_y) < 0.000001f) {break;};
            };
            return y;
        };
        
        def sqrt(double x) -> double
        {
            if (x <= 0.0) {return 0.0;};
            double y = x * 0.5;
            double prev_y;
            for (i32 i = 0; i < 40; i++)
            {
                prev_y = y;
                y = (y + x / y) * 0.5;
                if (abs(y - prev_y) < 0.000000000000001) {break;};
            };
            return y;
        };

        def cbrt(float x) -> float
        {
            if (x == 0.0f) {return 0.0f;};
            float y = x > 0.0f ? x / 3.0f : -(-x / 3.0f);
            float prev_y;
            for (i32 i = 0; i < 20; i++)
            {
                prev_y = y;
                y = (2.0f * y + x / (y * y)) / 3.0f;
                if (abs(y - prev_y) < 0.000001f) {break;};
            };
            return y;
        };

        def cbrt(double x) -> double
        {
            if (x == 0.0) {return 0.0;};
            double y = x > 0.0 ? x / 3.0 : -(-x / 3.0);
            double prev_y;
            for (i32 i = 0; i < 40; i++)
            {
                prev_y = y;
                y = (2.0 * y + x / (y * y)) / 3.0;
                if (abs(y - prev_y) < 0.000000000000001) {break;};
            };
            return y;
        };

        def pow(float base, float exp) -> float
        {
            return base ^ exp;
        };

        def pow(double base, double exp) -> double
        {
            return base ^ exp;
        };

        def hypot(float x, float y) -> float
        {
            float ax = abs(x);
            float ay = abs(y);
            if (ax > ay)
            {
                float r = ay / ax;
                return ax * sqrt(1.0f + r * r);
            };
            if (ay > 0.0f)
            {
                float r = ax / ay;
                return ay * sqrt(1.0f + r * r);
            };
            return 0.0f;
        };

        def hypot(double x, double y) -> double
        {
            double ax = abs(x);
            double ay = abs(y);
            if (ax > ay)
            {
                double r = ay / ax;
                return ax * sqrt(1.0 + r * r);
            };
            if (ay > 0.0)
            {
                double r = ax / ay;
                return ay * sqrt(1.0 + r * r);
            };
            return 0.0;
        };

        def factorial(i8 n) -> i8
        {
            if (n <= 1) {return 1;};
            i8 result = 1;
            for (i8 i = 2; i <= n; i++) {result *= i;};
            return result;
        };
        
        def factorial(i16 n) -> i16
        {
            if (n <= 1) {return 1;};
            i16 result = 1;
            for (i16 i = 2; i <= n; i++) {result *= i;};
            return result;
        };
        
        def factorial(i32 n) -> i32
        {
            if (n <= 1) {return 1;};
            i32 result = 1;
            for (i32 i = 2; i <= n; i++) {result *= i;};
            return result;
        };
        
        def factorial(i64 n) -> i64
        {
            if (n <= 1) {return 1;};
            i64 result = 1;
            for (i64 i = 2; i <= n; i++) {result *= i;};
            return result;
        };

        def gcd(i8 a, i8 b) -> i8
        {
            i8 temp;
            while (b != 0)
            {
                temp = b;
                b = a % b;
                a = temp;
            };
            return a;
        };
        
        def gcd(i16 a, i16 b) -> i16
        {
            i16 temp;
            while (b != 0)
            {
                temp = b;
                b = a % b;
                a = temp;
            };
            return a;
        };
        
        def gcd(i32 a, i32 b) -> i32
        {
            i32 temp;
            while (b != 0)
            {
                temp = b;
                b = a % b;
                a = temp;
            };
            return a;
        };
        
        def gcd(i64 a, i64 b) -> i64
        {
            i64 temp;
            while (b != 0)
            {
                temp = b;
                b = a % b;
                a = temp;
            };
            return a;
        };

        def lcm(i8 a, i8 b) -> i8
        {
            if (a == 0 | b == 0) {return 0;};
            return abs(a * b) / gcd(a, b);
        };
        
        def lcm(i16 a, i16 b) -> i16
        {
            if (a == 0 | b == 0) {return 0;};
            return abs(a * b) / gcd(a, b);
        };
        
        def lcm(i32 a, i32 b) -> i32
        {
            if (a == 0 | b == 0) {return 0;};
            return abs(a * b) / gcd(a, b);
        };
        
        def lcm(i64 a, i64 b) -> i64
        {
            if (a == 0 | b == 0) {return 0;};
            return abs(a * b) / gcd(a, b);
        };

        def floor(float x) -> float
        {
            i64 int_part = (i64)x;
            if (x >= 0.0f | x == (float)int_part) {return (float)int_part;};
            return (float)(int_part - 1);
        };
        
        def floor(double x) -> double
        {
            i64 int_part = (i64)x;
            if (x >= 0.0 | x == (double)int_part) {return (double)int_part;};
            return (double)(int_part - 1);
        };

        def ceil(float x) -> float
        {
            i64 int_part = (i64)x;
            if (x <= 0.0f | x == (float)int_part) {return (float)int_part;};
            return (float)(int_part + 1);
        };
        
        def ceil(double x) -> double
        {
            i64 int_part = (i64)x;
            if (x <= 0.0 | x == (double)int_part) {return (double)int_part;};
            return (double)(int_part + 1);
        };

        def round(float x) -> float
        {
            if (x >= 0.0f) {return floor(x + 0.5f);};
            return ceil(x - 0.5f);
        };
        
        def round(double x) -> double
        {
            if (x >= 0.0) {return floor(x + 0.5);};
            return ceil(x - 0.5);
        };

        def trunc(float x) -> float
        {
            return (float)((i64)x);
        };
        
        def trunc(double x) -> double
        {
            return (double)((i64)x);
        };

        def floor(i8 x) -> i8 { return x; };
        def floor(i16 x) -> i16 { return x; };
        def floor(i32 x) -> i32 { return x; };
        def floor(i64 x) -> i64 { return x; };
        
        def ceil(i8 x) -> i8 { return x; };
        def ceil(i16 x) -> i16 { return x; };
        def ceil(i32 x) -> i32 { return x; };
        def ceil(i64 x) -> i64 { return x; };
        
        def round(i8 x) -> i8 { return x; };
        def round(i16 x) -> i16 { return x; };
        def round(i32 x) -> i32 { return x; };
        def round(i64 x) -> i64 { return x; };

        def sin(float x) -> float
        {
            float y = x;
            while (y > PI_F) { y -= 2.0f * PI_F; };
            while (y < -PI_F) { y += 2.0f * PI_F; };
            float x2 = y * y;
            float result = y;
            float term = y;
            for (i32 i = 1; i <= 6; i++)
            {
                term *= -x2 / (float)((2 * i) * (2 * i + 1));
                result += term;
            };
            return result;
        };

        def sin(double x) -> double
        {
            double y = x;
            while (y > PI_D) { y -= 2.0 * PI_D; };
            while (y < -PI_D) { y += 2.0 * PI_D; };
            double x2 = y * y;
            double result = y;
            double term = y;
            for (i32 i = 1; i <= 10; i++)
            {
                term *= -x2 / (double)((2 * i) * (2 * i + 1));
                result += term;
            };
            return result;
        };

        def cos(float x) -> float
        {
            return sin(PI_F * 0.5f - x);
        };

        def cos(double x) -> double
        {
            return sin(PI_D * 0.5 - x);
        };

        def tan(float x) -> float
        {
            float c = cos(x);
            if (abs(c) < 0.000001f) {return 0.0f;};
            return sin(x) / c;
        };

        def tan(double x) -> double
        {
            double c = cos(x);
            if (abs(c) < 0.000000000001) {return 0.0;};
            return sin(x) / c;
        };

        def asin(float x) -> float
        {
            if (x >= 1.0f) {return PI_F * 0.5f;};
            if (x <= -1.0f) {return -PI_F * 0.5f;};
            return atan(x / sqrt(1.0f - x * x));
        };

        def asin(double x) -> double
        {
            if (x >= 1.0) {return PI_D * 0.5;};
            if (x <= -1.0) {return -PI_D * 0.5;};
            return atan(x / sqrt(1.0 - x * x));
        };

        def acos(float x) -> float
        {
            return PI_F * 0.5f - asin(x);
        };

        def acos(double x) -> double
        {
            return PI_D * 0.5 - asin(x);
        };

        def atan(float x) -> float
        {
            bool neg = x < 0.0f;
            if (neg) { x = -x; };
            bool recip = x > 1.0f;
            if (recip) { x = 1.0f / x; };
            float x2 = x * x;
            float r = x * (1.0f
                - x2 * (0.33333f
                - x2 * (0.2f
                - x2 * (0.14286f
                - x2 * (0.11111f
                - x2 * (0.08976f
                - x2 * (0.06004f)))))));
            if (recip) { r = PI_F * 0.5f - r; };
            if (neg) { r = -r; };
            return r;
        };

        def atan(double x) -> double
        {
            bool neg = x < 0.0;
            if (neg) { x = -x; };
            bool recip = x > 1.0;
            if (recip) { x = 1.0 / x; };
            double x2 = x * x;
            double r = x * (1.0
                - x2 * (0.33333
                - x2 * (0.2
                - x2 * (0.14286
                - x2 * (0.11111
                - x2 * (0.08976
                - x2 * (0.06004)))))));
            if (recip) { r = PI_D * 0.5 - r; };
            if (neg) { r = -r; };
            return r;
        };

        def atan2(float y, float x) -> float
        {
            if (x > 0.0f) {return atan(y / x);};
            if (x < 0.0f)
            {
                if (y >= 0.0f) {return atan(y / x) + PI_F;};
                return atan(y / x) - PI_F;
            };
            if (y > 0.0f) {return PI_F * 0.5f;};
            if (y < 0.0f) {return -PI_F * 0.5f;};
            return 0.0f;
        };

        def atan2(double y, double x) -> double
        {
            if (x > 0.0) {return atan(y / x);};
            if (x < 0.0)
            {
                if (y >= 0.0) {return atan(y / x) + PI_D;};
                return atan(y / x) - PI_D;
            };
            if (y > 0.0) {return PI_D * 0.5;};
            if (y < 0.0) {return -PI_D * 0.5;};
            return 0.0;
        };

        def sinh(float x) -> float
        {
            float e = exp(x);
            return (e - 1.0f / e) * 0.5f;
        };

        def sinh(double x) -> double
        {
            double e = exp(x);
            return (e - 1.0 / e) * 0.5;
        };

        def cosh(float x) -> float
        {
            float e = exp(x);
            return (e + 1.0f / e) * 0.5f;
        };

        def cosh(double x) -> double
        {
            double e = exp(x);
            return (e + 1.0 / e) * 0.5;
        };

        def tanh(float x) -> float
        {
            float e2 = exp(2.0f * x);
            return (e2 - 1.0f) / (e2 + 1.0f);
        };

        def tanh(double x) -> double
        {
            double e2 = exp(2.0 * x);
            return (e2 - 1.0) / (e2 + 1.0);
        };

        def asinh(float x) -> float
        {
            return log(x + sqrt(x * x + 1.0f));
        };

        def asinh(double x) -> double
        {
            return log(x + sqrt(x * x + 1.0));
        };

        def acosh(float x) -> float
        {
            if (x < 1.0f) {return 0.0f;};
            return log(x + sqrt(x * x - 1.0f));
        };

        def acosh(double x) -> double
        {
            if (x < 1.0) {return 0.0;};
            return log(x + sqrt(x * x - 1.0));
        };

        def atanh(float x) -> float
        {
            if (x <= -1.0f | x >= 1.0f) {return 0.0f;};
            return 0.5f * log((1.0f + x) / (1.0f - x));
        };

        def atanh(double x) -> double
        {
            if (x <= -1.0 | x >= 1.0) {return 0.0;};
            return 0.5 * log((1.0 + x) / (1.0 - x));
        };

        def degrees(float rad) -> float
        {
            return rad * (180.0f / PI_F);
        };

        def degrees(double rad) -> double
        {
            return rad * (180.0 / PI_D);
        };

        def radians(float deg) -> float
        {
            return deg * (PI_F / 180.0f);
        };

        def radians(double deg) -> double
        {
            return deg * (PI_D / 180.0);
        };

        def exp(float x) -> float
        {
            if (x > 88.0f) {return 3.40282e38f;};
            if (x < -87.0f) {return 0.0f;};
            float result = 1.0f;
            float term = 1.0f;
            for (i32 i = 1; i <= 15; i++)
            {
                term *= x / (float)i;
                result += term;
                if (abs(term) < 0.000001f) {break;};
            };
            return result;
        };

        def exp(double x) -> double
        {
            if (x > 709.0) {return 1.79769e308;};
            if (x < -708.0) {return 0.0;};
            double result = 1.0;
            double term = 1.0;
            for (i32 i = 1; i <= 25; i++)
            {
                term *= x / (double)i;
                result += term;
                if (abs(term) < 0.000000000000001) {break;};
            };
            return result;
        };

        def expm1(float x) -> float
        {
            if (abs(x) < 0.1f)
            {
                float result = x;
                float term = x;
                for (i32 i = 2; i <= 8; i++)
                {
                    term *= x / (float)i;
                    result += term;
                };
                return result;
            };
            return exp(x) - 1.0f;
        };

        def expm1(double x) -> double
        {
            if (abs(x) < 0.1)
            {
                double result = x;
                double term = x;
                for (i32 i = 2; i <= 15; i++)
                {
                    term *= x / (double)i;
                    result += term;
                };
                return result;
            };
            return exp(x) - 1.0;
        };

        def log(float x) -> float
        {
            if (x <= 0.0f) {return 0.0f;};
            if (x == 1.0f) {return 0.0f;};
            float m = x;
            i32 e = 0;
            while (m >= 2.0f)
            {
                m *= 0.5f;
                e++;
            };
            while (m < 1.0f)
            {
                m *= 2.0f;
                e--;
            };
            float t = (m - 1.0f) / (m + 1.0f);
            float t2 = t * t;
            float term = t;
            float result = t;
            for (i32 i = 1; i <= 10; i++)
            {
                term *= t2;
                result += term / (float)(2 * i + 1);
            };
            return 2.0f * result + (float)e * 0.69315f;
        };

        def log(double x) -> double
        {
            if (x <= 0.0) {return 0.0;};
            if (x == 1.0) {return 0.0;};
            double m = x;
            i32 e = 0;
            while (m >= 2.0)
            {
                m *= 0.5;
                e++;
            };
            while (m < 1.0)
            {
                m *= 2.0;
                e--;
            };
            double t = (m - 1.0) / (m + 1.0);
            double t2 = t * t;
            double term = t;
            double result = t;
            for (i32 i = 1; i <= 25; i++)
            {
                term *= t2;
                double add = term / (double)(2 * i + 1);
                result += add;
                if (abs(add) < 0.0000000000000001) {break;};
            };
            return 2.0 * result + (double)e * 0.69315;
        };

        def log1p(float x) -> float
        {
            if (abs(x) < 0.1f)
            {
                float result = x;
                float term = x;
                float xn = x;
                for (i32 i = 2; i <= 10; i++)
                {
                    xn *= -x;
                    term = xn / (float)i;
                    result += term;
                };
                return result;
            };
            return log(1.0f + x);
        };

        def log1p(double x) -> double
        {
            if (abs(x) < 0.1)
            {
                double result = x;
                double term = x;
                double xn = x;
                for (i32 i = 2; i <= 20; i++)
                {
                    xn *= -x;
                    term = xn / (double)i;
                    result += term;
                };
                return result;
            };
            return log(1.0 + x);
        };

        def log2(float x) -> float
        {
            return log(x) * 1.44270f;
        };

        def log2(double x) -> double
        {
            return log(x) * 1.44270;
        };

        def log10(float x) -> float
        {
            return log(x) * 0.43429f;
        };

        def log10(double x) -> double
        {
            return log(x) * 0.43429;
        };

        def erf(float x) -> float
        {
            float sign = x < 0.0f ? -1.0f : 1.0f,
                  a = abs(x),
                  t = 1.0f / (1.0f + 0.32759f * a),
                  t2 = t * t,
                  t3 = t2 * t,
                  t4 = t2 * t2,
                  t5 = t4 * t,
                  result = 1.0f - (0.25483f * t - 0.28450f * t2 + 1.42141f * t3 - 1.45315f * t4 + 1.06141f * t5) * exp(-a * a);
            return sign * result;
        };

        def erf(double x) -> double
        {
            double sign = x < 0.0 ? -1.0 : 1.0,
                   a = abs(x),
                   t = 1.0 / (1.0 + 0.32759 * a),
                   t2 = t * t,
                   t3 = t2 * t,
                   t4 = t2 * t2,
                   t5 = t4 * t,
                   result = 1.0 - (0.25483 * t - 0.28450 * t2 + 1.42141 * t3 - 1.45315 * t4 + 1.06141 * t5) * exp(-a * a);
            return sign * result;
        };

        def erfc(float x) -> float
        {
            return 1.0f - erf(x);
        };

        def erfc(double x) -> double
        {
            return 1.0 - erf(x);
        };

        def tgamma(float x) -> float
        {
            if (x <= 0.0f)
            {
                if (x == floor(x)) {return 0.0f;};
                return PI_F / (sin(PI_F * x) * tgamma(1.0f - x));
            };
            float p[8] = {676.52037f, -1259.13916f, 771.32343f, -176.61503f, 12.50734f, -0.13857f, 0.00001f, 0.00000f};
            float z = x - 1.0f;
            float y = 1.00000f;
            for (i32 i = 0; i < 8; i++) { y += p[i] / (z + (float)i + 1.0f); };
            float t = z + 7.5f;
            return sqrt(2.0f * PI_F) * pow(t, z + 0.5f) * exp(-t) * y;
        };

        def tgamma(double x) -> double
        {
            if (x <= 0.0)
            {
                if (x == floor(x)) {return 0.0;};
                return PI_D / (sin(PI_D * x) * tgamma(1.0 - x));
            };
            double p[8] = {676.52037, -1259.13916, 771.32343, -176.61503, 12.50734, -0.13857, 0.00001, 0.00000};
            double z = x - 1.0;
            double y = 1.00000;
            for (i32 i = 0; i < 8; i++) { y += p[i] / (z + (double)i + 1.0); };
            double t = z + 7.5;
            return sqrt(2.0 * PI_D) * pow(t, z + 0.5) * exp(-t) * y;
        };

        def lgamma(float x) -> float
        {
            return log(tgamma(x));
        };

        def lgamma(double x) -> double
        {
            return log(tgamma(x));
        };

        def lerp(i8 a, i8 b, float t) -> i8
        {
            return (i8)((float)a + (float)(b - a) * t);
        };
        
        def lerp(i16 a, i16 b, float t) -> i16
        {
            return (i16)((float)a + (float)(b - a) * t);
        };
        
        def lerp(i32 a, i32 b, float t) -> i32
        {
            return (i32)((float)a + (float)(b - a) * t);
        };

        def lerp(i64 a, i64 b, float t) -> i64
        {
            return (i64)((float)a + (float)(b - a) * t);
        };
        
        def lerp(float a, float b, float t) -> float
        {
            return a + (b - a) * t;
        };

        def lerp(double a, double b, double t) -> double
        {
            return a + (b - a) * t;
        };

        def sign(i8 x) -> i8
        {
            if (x > 0) {return 1;};
            if (x < 0) {return -1;};
            return 0;
        };
        
        def sign(i16 x) -> i16
        {
            if (x > 0) {return 1;};
            if (x < 0) {return -1;};
            return 0;
        };
        
        def sign(i32 x) -> i32
        {
            if (x > 0) {return 1;};
            if (x < 0) {return -1;};
            return 0;
        };
        
        def sign(i64 x) -> i64
        {
            if (x > 0) {return 1;};
            if (x < 0) {return -1;};
            return 0;
        };

        def sign(float x) -> float
        {
            if (x > 0.0f) {return 1.0f;};
            if (x < 0.0f) {return -1.0f;};
            return 0.0f;
        };

        def sign(double x) -> double
        {
            if (x > 0.0) {return 1.0;};
            if (x < 0.0) {return -1.0;};
            return 0.0;
        };

        def copysign(float mag, float sgn) -> float
        {
            if (sgn < 0.0f) {return -abs(mag);};
            return abs(mag);
        };

        def copysign(double mag, double sgn) -> double
        {
            if (sgn < 0.0) {return -abs(mag);};
            return abs(mag);
        };

        def fmod(float x, float y) -> float
        {
            if (y == 0.0f) {return 0.0f;};
            float n = floor(x / y);
            return x - n * y;
        };

        def fmod(double x, double y) -> double
        {
            if (y == 0.0) {return 0.0;};
            double n = floor(x / y);
            return x - n * y;
        };

        def frexp(float x, i32* exp) -> (float, i32)
        {
            if (x == 0.0f) {*exp = 0; return 0.0f;};
            i32 e = 0;
            float m = abs(x);
            if (m >= 1.0f) {while (m >= 1.0f) {m *= 0.5f; e++;};}
            else {while (m < 0.5f) {m *= 2.0f; e--;};};
            *exp = e;
            return copysign(m, x);
        };

        def frexp(double x, i32* exp) -> (double, i32)
        {
            if (x == 0.0) {*exp = 0; return 0.0;};
            i32 e = 0;
            double m = abs(x);
            if (m >= 1.0) {while (m >= 1.0) {m *= 0.5; e++;};}
            else {while (m < 0.5) {m *= 2.0; e--;};};
            *exp = e;
            return copysign(m, x);
        };

        def ldexp(float x, i32 exp) -> float
        {
            return x * pow(2.0f, (float)exp);
        };

        def ldexp(double x, i32 exp) -> double
        {
            return x * pow(2.0, (double)exp);
        };

        def modf(float x, float* intpart) -> (float, float)
        {
            *intpart = trunc(x);
            return x - *intpart;
        };

        def modf(double x, double* intpart) -> (double, double)
        {
            *intpart = trunc(x);
            return x - *intpart;
        };

        def fabs(float x) -> float
        {
            return abs(x);
        };

        def fabs(double x) -> double
        {
            return abs(x);
        };

        def fma(float x, float y, float z) -> float
        {
            return x * y + z;
        };

        def fma(double x, double y, double z) -> double
        {
            return x * y + z;
        };

        def isfinite(float x) -> bool
        {
            return x == x & x - x == 0.0f;
        };

        def isfinite(double x) -> bool
        {
            return x == x & x - x == 0.0;
        };

        def isinf(float x) -> bool
        {
            return x != x | x - x != 0.0f;
        };

        def isinf(double x) -> bool
        {
            return x != x | x - x != 0.0;
        };

        def isnan(float x) -> bool
        {
            return x != x;
        };

        def isnan(double x) -> bool
        {
            return x != x;
        };

        def nextafter(float x, float y) -> float
        {
            if (x == y) {return x;};
            if (isnan(x) | isnan(y)) {return x;};
            if (!isfinite(x)) {return x;};
            i32 ix = *(i32*)@x;
            if ((x < y) == (x > 0.0f)) {ix++;} else {ix--;};
            return *(float*)@ix;
        };

        def nextafter(double x, double y) -> double
        {
            if (x == y) {return x;};
            if (isnan(x) | isnan(y)) {return x;};
            if (!isfinite(x)) {return x;};
            i64 ix = *(i64*)@x;
            if ((x < y) == (x > 0.0)) {ix++;} else {ix--;};
            return *(double*)@ix;
        };

        def ulp(float x) -> float
        {
            return nextafter(x, 3.40282e38f) - x;
        };

        def ulp(double x) -> double
        {
            return nextafter(x, 1.79769e308) - x;
        };

        def popcount(byte x) -> byte
        {
            x -= (x >> 1) & 0x55;
            x = (x & 0x33) + ((x >> 2) & 0x33);
            x = (x + (x >> 4)) & 0x0F;
            return x;
        };

        def popcount(i8 x) -> i8
        {
            i8 u = x;
            u -= (u >> 1) & 0x55;
            u = (u & 0x33) + ((u >> 2) & 0x33);
            u = (u + (u >> 4)) & 0x0F;
            return u;
        };

        def popcount(u16 x) -> u16
        {
            x -= (x >> 1) & 0x5555;
            x = (x & 0x3333) + ((x >> 2) & 0x3333);
            x = (x + (x >> 4)) & 0x0F0F;
            x = (x + (x >> 8)) & 0x00FF;
            return x;
        };

        def popcount(i16 x) -> i16
        {
            i16 u = x;
            u -= (u >> 1) & 0x5555;
            u = (u & 0x3333) + ((u >> 2) & 0x3333);
            u = (u + (u >> 4)) & 0x0F0F;
            u = (u + (u >> 8)) & 0x00FF;
            return u;
        };

        def popcount(u32 x) -> u32
        {
            x -= (x >> 1) & 0x55555555;
            x = (x & 0x33333333) + ((x >> 2) & 0x33333333);
            x = (x + (x >> 4)) & 0x0F0F0F0F;
            x += x >> 8;
            x += x >> 16;
            return x & 0x3F;
        };

        def popcount(i32 x) -> i32
        {
            i32 u = x;
            u -= (u >> 1) & 0x55555555;
            u = (u & 0x33333333) + ((u >> 2) & 0x33333333);
            u = (u + (u >> 4)) & 0x0F0F0F0F;
            u += u >> 8;
            u += u >> 16;
            return u & 0x3F;
        };

        def popcount(u64 x) -> u64
        {
            x -= (x >> 1) & 0x5555555555555555;
            x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333);
            x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0F;
            x += x >> 8;
            x += x >> 16;
            x += x >> 32;
            return x & 0x7F;
        };

        def popcount(i64 x) -> i64
        {
            i64 u = x;
            u -= (u >> 1) & 0x5555555555555555;
            u = (u & 0x3333333333333333) + ((u >> 2) & 0x3333333333333333);
            u = (u + (u >> 4)) & 0x0F0F0F0F0F0F0F0F;
            u += u >> 8;
            u += u >> 16;
            u += u >> 32;
            return u & 0x7F;
        };

        def reverse_bits(byte x) -> byte
        {
            x = ((x & 0xF0) >> 4) | ((x & 0x0F) << 4);
            x = ((x & 0xCC) >> 2) | ((x & 0x33) << 2);
            x = ((x & 0xAA) >> 1) | ((x & 0x55) << 1);
            return x;
        };

        def reverse_bits(i8 x) -> i8
        {
            i8 u = x;
            u = ((u & 0xF0) >> 4) | ((u & 0x0F) << 4);
            u = ((u & 0xCC) >> 2) | ((u & 0x33) << 2);
            u = ((u & 0xAA) >> 1) | ((u & 0x55) << 1);
            return u;
        };

        def reverse_bits(u16 x) -> u16
        {
            x = ((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8);
            x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4);
            x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2);
            x = ((x & 0xAAAA) >> 1) | ((x & 0x5555) << 1);
            return x;
        };

        def reverse_bits(i16 x) -> i16
        {
            i16 u = x;
            u = ((u & 0xFF00) >> 8) | ((u & 0x00FF) << 8);
            u = ((u & 0xF0F0) >> 4) | ((u & 0x0F0F) << 4);
            u = ((u & 0xCCCC) >> 2) | ((u & 0x3333) << 2);
            u = ((u & 0xAAAA) >> 1) | ((u & 0x5555) << 1);
            return u;
        };

        def reverse_bits(u32 x) -> u32
        {
            x = ((x & 0xFFFF0000) >> 16) | ((x & 0x0000FFFF) << 16);
            x = ((x & 0xFF00FF00) >> 8) | ((x & 0x00FF00FF) << 8);
            x = ((x & 0xF0F0F0F0) >> 4) | ((x & 0x0F0F0F0F) << 4);
            x = ((x & 0xCCCCCCCC) >> 2) | ((x & 0x33333333) << 2);
            x = ((x & 0xAAAAAAAA) >> 1) | ((x & 0x55555555) << 1);
            return x;
        };

        def reverse_bits(i32 x) -> i32
        {
            i32 u = x;
            u = ((u & 0xFFFF0000) >> 16) | ((u & 0x0000FFFF) << 16);
            u = ((u & 0xFF00FF00) >> 8) | ((u & 0x00FF00FF) << 8);
            u = ((u & 0xF0F0F0F0) >> 4) | ((u & 0x0F0F0F0F) << 4);
            u = ((u & 0xCCCCCCCC) >> 2) | ((u & 0x33333333) << 2);
            u = ((u & 0xAAAAAAAA) >> 1) | ((u & 0x55555555) << 1);
            return u;
        };

        def reverse_bits(u64 x) -> u64
        {
            x = ((x & 0xFFFFFFFF00000000) >> 32) | ((x & 0x00000000FFFFFFFF) << 32);
            x = ((x & 0xFFFF0000FFFF0000) >> 16) | ((x & 0x0000FFFF0000FFFF) << 16);
            x = ((x & 0xFF00FF00FF00FF00) >> 8) | ((x & 0x00FF00FF00FF00FF) << 8);
            x = ((x & 0xF0F0F0F0F0F0F0F0) >> 4) | ((x & 0x0F0F0F0F0F0F0F0F) << 4);
            x = ((x & 0xCCCCCCCCCCCCCCCC) >> 2) | ((x & 0x3333333333333333) << 2);
            x = ((x & 0xAAAAAAAAAAAAAAAA) >> 1) | ((x & 0x5555555555555555) << 1);
            return x;
        };

        def reverse_bits(i64 x) -> i64
        {
            i64 u = x;
            u = ((u & 0xFFFFFFFF00000000) >> 32) | ((u & 0x00000000FFFFFFFF) << 32);
            u = ((u & 0xFFFF0000FFFF0000) >> 16) | ((u & 0x0000FFFF0000FFFF) << 16);
            u = ((u & 0xFF00FF00FF00FF00) >> 8) | ((u & 0x00FF00FF00FF00FF) << 8);
            u = ((u & 0xF0F0F0F0F0F0F0F0) >> 4) | ((u & 0x0F0F0F0F0F0F0F0F) << 4);
            u = ((u & 0xCCCCCCCCCCCCCCCC) >> 2) | ((u & 0x3333333333333333) << 2);
            u = ((u & 0xAAAAAAAAAAAAAAAA) >> 1) | ((u & 0x5555555555555555) << 1);
            return u;
        };
    };
};