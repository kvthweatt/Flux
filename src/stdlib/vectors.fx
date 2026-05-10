// Author: Karac V. Thweatt

// redvectors.fx - 3D and 4D Vector Mathematics Library

#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_MATH
#import "math.fx";
#endif;

#ifndef FLUX_STANDARD_VECTORS
#def FLUX_STANDARD_VECTORS 1;

namespace standard
{
    namespace vectors
    {
        // ===== 3D VECTOR =====
        struct Vec3
        {
            float x, y, z;
        };
        
        // ===== 4D VECTOR =====
        struct Vec4
        {
            float x, y, z, w;
        };
        
        // ===== VEC3 CONSTRUCTORS =====
        def vec3(float x, float y, float z) -> Vec3
        {
            Vec3 result = {x, y, z};
            return result;
        };
        
        def vec3_zero() -> Vec3
        {
            Vec3 result = {x = 0.0, y = 0.0, z = 0.0};
            return result;
        };
        
        def vec3_one() -> Vec3
        {
            Vec3 result = {x = 1.0, y = 1.0, z = 1.0};
            return result;
        };
        
        def vec3_up() -> Vec3
        {
            Vec3 result = {x = 0.0, y = 1.0, z = 0.0};
            return result;
        };
        
        def vec3_down() -> Vec3
        {
            Vec3 result = {x = 0.0, y = -1.0, z = 0.0};
            return result;
        };
        
        def vec3_left() -> Vec3
        {
            Vec3 result = {x = -1.0, y = 0.0, z = 0.0};
            return result;
        };
        
        def vec3_right() -> Vec3
        {
            Vec3 result = {x = 1.0, y = 0.0, z = 0.0};
            return result;
        };
        
        def vec3_forward() -> Vec3
        {
            Vec3 result = {x = 0.0, y = 0.0, z = 1.0};
            return result;
        };
        
        def vec3_back() -> Vec3
        {
            Vec3 result = {x = 0.0, y = 0.0, z = -1.0};
            return result;
        };
        
        // ===== VEC4 CONSTRUCTORS =====
        def vec4(float x, float y, float z, float w) -> Vec4
        {
            Vec4 result = {x, y, z, w};
            return result;
        };
        
        def vec4_zero() -> Vec4
        {
            Vec4 result = {x = 0.0, y = 0.0, z = 0.0, w = 0.0};
            return result;
        };
        
        def vec4_one() -> Vec4
        {
            Vec4 result = {x = 1.0, y = 1.0, z = 1.0, w = 1.0};
            return result;
        };
        
        def vec4_from_vec3(Vec3 v, float w) -> Vec4
        {
            Vec4 result = {v.x, v.y, v.z, w};
            return result;
        };
        
        // ===== VEC3 ARITHMETIC =====
        def vec3_add(Vec3 a, Vec3 b) -> Vec3
        {
            Vec3 result = {a.x + b.x, a.y + b.y, a.z + b.z};
            return result;
        };
        
        def vec3_sub(Vec3 a, Vec3 b) -> Vec3
        {
            Vec3 result = {a.x - b.x, a.y - b.y, a.z - b.z};
            return result;
        };
        
        def vec3_mul(Vec3 v, float scalar) -> Vec3
        {
            Vec3 result = {v.x * scalar, v.y * scalar, v.z * scalar};
            return result;
        };
        
        def vec3_div(Vec3 v, float scalar) -> Vec3
        {
            Vec3 result = {v.x / scalar, v.y / scalar, v.z / scalar};
            return result;
        };
        
        def vec3_negate(Vec3 v) -> Vec3
        {
            Vec3 result = {-v.x, -v.y, -v.z};
            return result;
        };
        
        def vec3_scale(Vec3 a, Vec3 b) -> Vec3
        {
            Vec3 result = {a.x * b.x, a.y * b.y, a.z * b.z};
            return result;
        };
        
        // ===== VEC4 ARITHMETIC =====
        def vec4_add(Vec4 a, Vec4 b) -> Vec4
        {
            Vec4 result = {a.x + b.x, a.y + b.y, a.z + b.z, a.w + b.w};
            return result;
        };
        
        def vec4_sub(Vec4 a, Vec4 b) -> Vec4
        {
            Vec4 result = {a.x - b.x, a.y - b.y, a.z - b.z, a.w - b.w};
            return result;
        };
        
        def vec4_mul(Vec4 v, float scalar) -> Vec4
        {
            Vec4 result = {v.x * scalar, v.y * scalar, v.z * scalar, v.w * scalar};
            return result;
        };
        
        def vec4_div(Vec4 v, float scalar) -> Vec4
        {
            Vec4 result = {v.x / scalar, v.y / scalar, v.z / scalar, v.w / scalar};
            return result;
        };
        
        def vec4_negate(Vec4 v) -> Vec4
        {
            Vec4 result = {-v.x, -v.y, -v.z, -v.w};
            return result;
        };
        
        def vec4_scale(Vec4 a, Vec4 b) -> Vec4
        {
            Vec4 result = {a.x * b.x, a.y * b.y, a.z * b.z, a.w * b.w};
            return result;
        };
        
        // ===== VEC3 DOT PRODUCT =====
        def vec3_dot(Vec3 a, Vec3 b) -> float
        {
            return a.x * b.x + a.y * b.y + a.z * b.z;
        };
        
        // ===== VEC4 DOT PRODUCT =====
        def vec4_dot(Vec4 a, Vec4 b) -> float
        {
            return a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;
        };
        
        // ===== VEC3 CROSS PRODUCT =====
        def vec3_cross(Vec3 a, Vec3 b) -> Vec3
        {
            Vec3 result;
            result.x = a.y * b.z - a.z * b.y;
            result.y = a.z * b.x - a.x * b.z;
            result.z = a.x * b.y - a.y * b.x;
            return result;
        };
        
        // ===== VEC3 LENGTH AND NORMALIZATION =====
        def vec3_length_squared(Vec3 v) -> float
        {
            return v.x * v.x + v.y * v.y + v.z * v.z;
        };
        
        def vec3_length(Vec3 v) -> float
        {
            return sqrt(vec3_length_squared(v));
        };
        
        def vec3_normalize(Vec3 v) -> Vec3
        {
            float len = vec3_length(v);
            if (len < 0.000001)
            {
                return vec3_zero();
            };
            return vec3_div(v, len);
        };
        
        def vec3_distance(Vec3 a, Vec3 b) -> float
        {
            return vec3_length(vec3_sub(a, b));
        };
        
        def vec3_distance_squared(Vec3 a, Vec3 b) -> float
        {
            return vec3_length_squared(vec3_sub(a, b));
        };
        
        // ===== VEC4 LENGTH AND NORMALIZATION =====
        def vec4_length_squared(Vec4 v) -> float
        {
            return v.x * v.x + v.y * v.y + v.z * v.z + v.w * v.w;
        };
        
        def vec4_length(Vec4 v) -> float
        {
            return sqrt(vec4_length_squared(v));
        };
        
        def vec4_normalize(Vec4 v) -> Vec4
        {
            float len = vec4_length(v);
            if (len < 0.000001)
            {
                return vec4_zero();
            };
            return vec4_div(v, len);
        };
        
        def vec4_distance(Vec4 a, Vec4 b) -> float
        {
            return vec4_length(vec4_sub(a, b));
        };
        
        def vec4_distance_squared(Vec4 a, Vec4 b) -> float
        {
            return vec4_length_squared(vec4_sub(a, b));
        };
        
        // ===== VEC3 INTERPOLATION =====
        def vec3_lerp(Vec3 a, Vec3 b, float t) -> Vec3
        {
            Vec3 result;
            result.x = lerp(a.x, b.x, t);
            result.y = lerp(a.y, b.y, t);
            result.z = lerp(a.z, b.z, t);
            return result;
        };
        
        def vec3_slerp(Vec3 a, Vec3 b, float t) -> Vec3
        {
            float dot_product = vec3_dot(a, b);
            
            // Clamp dot product
            if (dot_product < -1.0)
            {
                dot_product = -1.0;
            };
            if (dot_product > 1.0)
            {
                dot_product = 1.0;
            };
            
            float theta = acos(dot_product) * t;
            
            Vec3 relative = vec3_sub(b, vec3_mul(a, dot_product));
            relative = vec3_normalize(relative);
            
            Vec3 result = vec3_add(
                vec3_mul(a, cos(theta)),
                vec3_mul(relative, sin(theta))
            );
            
            return result;
        };
        
        // ===== VEC4 INTERPOLATION =====
        def vec4_lerp(Vec4 a, Vec4 b, float t) -> Vec4
        {
            Vec4 result;
            result.x = lerp(a.x, b.x, t);
            result.y = lerp(a.y, b.y, t);
            result.z = lerp(a.z, b.z, t);
            result.w = lerp(a.w, b.w, t);
            return result;
        };
        
        // ===== VEC3 COMPARISON =====
        def vec3_equals(Vec3 a, Vec3 b) -> bool
        {
            return abs(a.x - b.x) < 0.000001 & 
                   abs(a.y - b.y) < 0.000001 & 
                   abs(a.z - b.z) < 0.000001;
        };
        
        def vec3_equals_epsilon(Vec3 a, Vec3 b, float epsilon) -> bool
        {
            return abs(a.x - b.x) < epsilon & 
                   abs(a.y - b.y) < epsilon & 
                   abs(a.z - b.z) < epsilon;
        };
        
        // ===== VEC4 COMPARISON =====
        def vec4_equals(Vec4 a, Vec4 b) -> bool
        {
            return abs(a.x - b.x) < 0.000001 & 
                   abs(a.y - b.y) < 0.000001 & 
                   abs(a.z - b.z) < 0.000001 & 
                   abs(a.w - b.w) < 0.000001;
        };
        
        def vec4_equals_epsilon(Vec4 a, Vec4 b, float epsilon) -> bool
        {
            return abs(a.x - b.x) < epsilon & 
                   abs(a.y - b.y) < epsilon & 
                   abs(a.z - b.z) < epsilon & 
                   abs(a.w - b.w) < epsilon;
        };
        
        // ===== VEC3 PROJECTIONS =====
        def vec3_project(Vec3 v, Vec3 onto) -> Vec3
        {
            float dot = vec3_dot(v, onto);
            float len_sq = vec3_length_squared(onto);
            if (len_sq < 0.000001)
            {
                return vec3_zero();
            };
            return vec3_mul(onto, dot / len_sq);
        };
        
        def vec3_reject(Vec3 v, Vec3 xfrom) -> Vec3
        {
            return vec3_sub(v, vec3_project(v, xfrom));
        };
        
        def vec3_reflect(Vec3 v, Vec3 normal) -> Vec3
        {
            float dot = vec3_dot(v, normal);
            return vec3_sub(v, vec3_mul(normal, 2.0 * dot));
        };
        
        // ===== VEC4 PROJECTIONS =====
        def vec4_project(Vec4 v, Vec4 onto) -> Vec4
        {
            float dot = vec4_dot(v, onto);
            float len_sq = vec4_length_squared(onto);
            if (len_sq < 0.000001)
            {
                return vec4_zero();
            };
            return vec4_mul(onto, dot / len_sq);
        };
        
        def vec4_reject(Vec4 v, Vec4 xfrom) -> Vec4
        {
            return vec4_sub(v, vec4_project(v, xfrom));
        };
        
        def vec4_reflect(Vec4 v, Vec4 normal) -> Vec4
        {
            float dot = vec4_dot(v, normal);
            return vec4_sub(v, vec4_mul(normal, 2.0 * dot));
        };
        
        // ===== VEC3 ANGLE CALCULATIONS =====
        def vec3_angle(Vec3 a, Vec3 b) -> float
        {
            float dot = vec3_dot(a, b);
            float len_product = vec3_length(a) * vec3_length(b);
            
            if (len_product < 0.000001)
            {
                return 0.0;
            };
            
            float cos_angle = dot / len_product;
            
            // Clamp to valid range
            if (cos_angle < -1.0)
            {
                cos_angle = -1.0;
            };
            if (cos_angle > 1.0)
            {
                cos_angle = 1.0;
            };
            
            return acos(cos_angle);
        };
        
        // ===== VEC4 ANGLE CALCULATIONS =====
        def vec4_angle(Vec4 a, Vec4 b) -> float
        {
            float dot = vec4_dot(a, b);
            float len_product = vec4_length(a) * vec4_length(b);
            
            if (len_product < 0.000001)
            {
                return 0.0;
            };
            
            float cos_angle = dot / len_product;
            
            // Clamp to valid range
            if (cos_angle < -1.0)
            {
                cos_angle = -1.0;
            };
            if (cos_angle > 1.0)
            {
                cos_angle = 1.0;
            };
            
            return acos(cos_angle);
        };
        
        // ===== VEC3 MIN/MAX =====
        def vec3_min(Vec3 a, Vec3 b) -> Vec3
        {
            Vec3 result;
            result.x = min(a.x, b.x);
            result.y = min(a.y, b.y);
            result.z = min(a.z, b.z);
            return result;
        };
        
        def vec3_max(Vec3 a, Vec3 b) -> Vec3
        {
            Vec3 result;
            result.x = max(a.x, b.x);
            result.y = max(a.y, b.y);
            result.z = max(a.z, b.z);
            return result;
        };
        
        def vec3_clamp(Vec3 v, Vec3 min_v, Vec3 max_v) -> Vec3
        {
            Vec3 result;
            result.x = clamp(v.x, min_v.x, max_v.x);
            result.y = clamp(v.y, min_v.y, max_v.y);
            result.z = clamp(v.z, min_v.z, max_v.z);
            return result;
        };
        
        // ===== VEC4 MIN/MAX =====
        def vec4_min(Vec4 a, Vec4 b) -> Vec4
        {
            Vec4 result;
            result.x = min(a.x, b.x);
            result.y = min(a.y, b.y);
            result.z = min(a.z, b.z);
            result.w = min(a.w, b.w);
            return result;
        };
        
        def vec4_max(Vec4 a, Vec4 b) -> Vec4
        {
            Vec4 result;
            result.x = max(a.x, b.x);
            result.y = max(a.y, b.y);
            result.z = max(a.z, b.z);
            result.w = max(a.w, b.w);
            return result;
        };
        
        def vec4_clamp(Vec4 v, Vec4 min_v, Vec4 max_v) -> Vec4
        {
            Vec4 result;
            result.x = clamp(v.x, min_v.x, max_v.x);
            result.y = clamp(v.y, min_v.y, max_v.y);
            result.z = clamp(v.z, min_v.z, max_v.z);
            result.w = clamp(v.w, min_v.w, max_v.w);
            return result;
        };
        
        // ===== VEC3 COMPONENT ACCESS =====
        def vec3_get_x(Vec3 v) -> float
        {
            return v.x;
        };
        
        def vec3_get_y(Vec3 v) -> float
        {
            return v.y;
        };
        
        def vec3_get_z(Vec3 v) -> float
        {
            return v.z;
        };
        
        def vec3_set_x(Vec3* v, float x) -> void
        {
            v.x = x;
        };
        
        def vec3_set_y(Vec3* v, float y) -> void
        {
            v.y = y;
        };
        
        def vec3_set_z(Vec3* v, float z) -> void
        {
            v.z = z;
        };
        
        // ===== VEC4 COMPONENT ACCESS =====
        def vec4_get_x(Vec4 v) -> float
        {
            return v.x;
        };
        
        def vec4_get_y(Vec4 v) -> float
        {
            return v.y;
        };
        
        def vec4_get_z(Vec4 v) -> float
        {
            return v.z;
        };
        
        def vec4_get_w(Vec4 v) -> float
        {
            return v.w;
        };
        
        def vec4_set_x(Vec4* v, float x) -> void
        {
            v.x = x;
        };
        
        def vec4_set_y(Vec4* v, float y) -> void
        {
            v.y = y;
        };
        
        def vec4_set_z(Vec4* v, float z) -> void
        {
            v.z = z;
        };
        
        def vec4_set_w(Vec4* v, float w) -> void
        {
            v.w = w;
        };
        
        // ===== VEC3 ROTATION HELPERS =====
        def vec3_rotate_x(Vec3 v, float angle) -> Vec3
        {
            float c = cos(angle);
            float s = sin(angle);
            
            Vec3 result;
            result.x = v.x;
            result.y = v.y * c - v.z * s;
            result.z = v.y * s + v.z * c;
            return result;
        };
        
        def vec3_rotate_y(Vec3 v, float angle) -> Vec3
        {
            float c = cos(angle);
            float s = sin(angle);
            
            Vec3 result;
            result.x = v.x * c + v.z * s;
            result.y = v.y;
            result.z = -v.x * s + v.z * c;
            return result;
        };
        
        def vec3_rotate_z(Vec3 v, float angle) -> Vec3
        {
            float c = cos(angle);
            float s = sin(angle);
            
            Vec3 result;
            result.x = v.x * c - v.y * s;
            result.y = v.x * s + v.y * c;
            result.z = v.z;
            return result;
        };
        
        // ===== VEC3 BARYCENTRIC =====
        def vec3_barycentric(Vec3 a, Vec3 b, Vec3 c, float u, float v) -> Vec3
        {
            float w = 1.0 - u - v;
            Vec3 result;
            result.x = w * a.x + u * b.x + v * c.x;
            result.y = w * a.y + u * b.y + v * c.y;
            result.z = w * a.z + u * b.z + v * c.z;
            return result;
        };
        
        // ===== VEC3 TRIPLE PRODUCT =====
        def vec3_triple_product(Vec3 a, Vec3 b, Vec3 c) -> float
        {
            return vec3_dot(a, vec3_cross(b, c));
        };
        
        // ===== VEC3 ABSOLUTE =====
        def vec3_abs(Vec3 v) -> Vec3
        {
            Vec3 result;
            result.x = abs(v.x);
            result.y = abs(v.y);
            result.z = abs(v.z);
            return result;
        };
        
        // ===== VEC4 ABSOLUTE =====
        def vec4_abs(Vec4 v) -> Vec4
        {
            Vec4 result;
            result.x = abs(v.x);
            result.y = abs(v.y);
            result.z = abs(v.z);
            result.w = abs(v.w);
            return result;
        };

        // ============================================================================
        // 3D MATH
        // ============================================================================

        def rotate_x(Vec3* v, float s, float c) -> Vec3
        {
            Vec3 r;
            r.x = v.x;
            r.y = v.y * c - v.z * s;
            r.z = v.y * s + v.z * c;
            return r;
        };

        def rotate_y(Vec3* v, float s, float c) -> Vec3
        {
            Vec3 r;
            r.x =  v.x * c + v.z * s;
            r.y =  v.y;
            r.z = (v.x * (0.0 - s)) + v.z * c;
            return r;
        };

        def rotate_z(Vec3* v, float s, float c) -> Vec3
        {
            Vec3 r;
            r.x = v.x * c - v.y * s;
            r.y = v.x * s + v.y * c;
            r.z = v.z;
            return r;
        };

        def project(Vec3* v, int cx, int cy, float fov, float cam_z) -> POINT
        {
            float dz = v.z + cam_z;
            POINT p;
            if (dz < 0.001)
            {
                p.x = cx;
                p.y = cy;
                return p;
            };
            p.x = cx + (int)(v.x * fov / dz);
            p.y = cy - (int)(v.y * fov / dz);
            return p;
        };
    };
};

#endif;
