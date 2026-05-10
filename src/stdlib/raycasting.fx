// raycasting.fx - Flux 2.5D Raycasting Library
//
// A tile-based raycaster in the style of Wolfenstein 3D / DOOM, built
// following the conventions of raytracing.fx (same stdlib imports,
// same Vec3/math layers, same u32 pixel-buffer output contract).
//
// ARCHITECTURE:
//   Unlike the path tracer this library casts one ray *per screen column*
//   (not per pixel).  The world is a 2D grid of integer tile IDs; the
//   renderer extrudes each wall to full screen height and shades it by
//   distance.  Floors and ceilings are drawn with a separate per-pixel
//   ray for optional texture mapping.
//
// COORDINATE SYSTEM:
//   +X = East, +Y = North (map row increases South).
//   Player angle 0 = facing East, increases counter-clockwise.
//
// PRIMITIVES / FEATURES:
//   RC_MAP_*         - Map cell flags (solid, door, transparent)
//   RCMap            - 2D grid of tile IDs + texture palette
//   RCPlayer         - Position, angle, movement speed
//   RCCamera         - FOV, projection plane, view distance
//   RCSprite         - Billboard objects sorted by distance
//   RCSky            - Optional cylindrical sky color gradient
//   rc_cast_walls()  - DDA wall raycasting, returns depth buffer
//   rc_cast_floor()  - Floor/ceiling per-pixel ray fill
//   rc_cast_sprites()- Billboard sprite projection
//   rc_render()      - Composite all passes into a u32 pixel buffer
//
// USAGE:
//   #import "raycasting.fx";
//   using raycaster;
//
//   RCMap   map;    rc_map_init(@map, 24, 24);
//   RCPlayer player; rc_player_init(@player, 2.5, 2.5, 0.0);
//   RCCamera cam;   rc_camera_init(@cam, 66.0, 320, 240, 16.0);
//   // fill map tiles ...
//   u32* buf = (u32*)fmalloc((size_t)(320 * 240 * (i32)(sizeof(u32) / 8)));
//   rc_render(@map, @player, @cam, buf);
//   rc_map_free(@map);
//

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_MATH
#import "math.fx";
#endif;

#ifndef FLUX_STANDARD_VECTORS
#import "vectors.fx";
#endif;

#ifndef FLUX_STANDARD_MEMORY
#import "memory.fx";
#endif;

#ifndef FLUX_STANDARD_ALLOCATORS
#import "allocators.fx";
#endif;

#ifndef FLUX_RAYCASTING
#def FLUX_RAYCASTING 1;

using standard::vectors;
using standard::math;
using standard::memory::allocators::stdheap;

// ============================================================================
// CONSTANTS
// ============================================================================

#def RC_EPSILON         0.0001;       // Floating-point guard
#def RC_INF             1000000000.0; // Effective infinity
#def RC_PI              3.14159265358979323846;
#def RC_TWO_PI          6.28318530717958647692;
#def RC_HALF_PI         1.57079632679489661923;

// Tile type flags (ORable)
#def RC_TILE_EMPTY      0;
#def RC_TILE_SOLID      1;
#def RC_TILE_DOOR       2;   // Penetrable at midpoint along ray
#def RC_TILE_TRANS      4;   // Transparent wall (tinted, not blocking)

// Wall face identifiers (which side of a tile was hit)
#def RC_FACE_NONE       0;
#def RC_FACE_X_POS      1;   // Ray hit the +X face (came from -X)
#def RC_FACE_X_NEG      2;
#def RC_FACE_Y_POS      3;
#def RC_FACE_Y_NEG      4;

// Render pass flags for rc_render()
#def RC_PASS_SKY        1;
#def RC_PASS_WALLS      2;
#def RC_PASS_FLOOR      4;
#def RC_PASS_SPRITES    8;
#def RC_PASS_ALL        15;

// Maximum sprites per scene
#def RC_MAX_SPRITES     256;

// Shade steps for distance fog (0 = full bright, RC_SHADE_STEPS-1 = darkest)
#def RC_SHADE_STEPS     32;

// ============================================================================
// STRUCTS
// ============================================================================

// Single map cell
struct RCTile
{
    i32  flags,       // RC_TILE_* combination
         tex_wall,    // Texture index for wall faces (0 = untextured)
         tex_floor,   // Texture index for floor
         tex_ceil;    // Texture index for ceiling
    u32  tint;        // 0xAARRGGBB override color (0 = use tex color)
};

// 2D map grid
struct RCMap
{
    RCTile* cells;    // Row-major: cells[y * width + x]
    i32     width, height;
    u32     floor_color,  // Default floor color (0xAARRGGBB)
            ceil_color;   // Default ceiling color
};

// A single 32-bit ARGB texture mip-0 surface
struct RCTexture
{
    u32* pixels;   // width * height u32 values
    i32  width, height;
};

// Texture palette — up to 64 named slots
struct RCTexturePalette
{
    RCTexture* slots;
    i32        count, cap;
};

// Player / camera entity in world space
struct RCPlayer
{
    float pos_x,     // World X (fractional tile units)
          pos_y,     // World Y
          angle,     // Facing angle in radians (0 = +X axis)
          move_speed,
          turn_speed;
};

// Projection camera — pure render parameters
struct RCCamera
{
    float fov_h;      // Horizontal field of view (degrees)
    i32   screen_w, screen_h;
    float view_dist,  // Max render distance in tile units
          proj_dist,  // Precomputed: (screen_w/2) / tan(fov_h/2)
          half_h,     // screen_h / 2.0
          plane_x,    // Projection plane vector (perpendicular to dir)
          plane_y,
          dir_x,      // Current view direction (derived from player angle)
          dir_y;
};

// Per-column result from the DDA wall pass
struct RCWallHit
{
    float dist,       // Perpendicular (corrected) distance to wall
          wall_u;     // Horizontal texture coordinate [0,1]
    i32   tile_x,     // Map cell that was hit
          tile_y,
          face,       // RC_FACE_* constant
          tex_idx,    // Resolved texture index
          tint,       // Resolved tint color
          draw_top,   // Screen-space top of wall strip
          draw_bot;   // Screen-space bottom of wall strip
};

// A billboard sprite in the world
struct RCSprite
{
    float world_x, world_y;
    i32   tex_idx;
    float scale;      // 1.0 = 1 tile wide/tall
    u32   tint;       // 0 = no tint
    float dist_sq;    // Filled by sort pass
};

// Optional sky descriptor (cylindrical gradient)
struct RCSky
{
    u32 color_top,    // Zenith color
        color_horizon;
};

// Full scene container passed to rc_render()
struct RCScene
{
    RCMap*            map;
    RCPlayer*         player;
    RCCamera*         cam;
    RCTexturePalette* palette;    // May be null (untextured mode)
    RCSprite*         sprites;
    i32               sprite_count;
    RCSky*            sky;        // May be null (use map ceiling color)
    i32               passes;     // RC_PASS_* flags
};

// ============================================================================
// NAMESPACE raycaster
// ============================================================================

namespace raycaster
{
    // =========================================================================
    // color HELPERS
    // =========================================================================

    // Unpack 0xAARRGGBB into float components [0,1]
    def color_unpack(u32 argb, float* r, float* g, float* b) -> void
    {
        *r = (float)((argb >> 16) & 0xFFu) / 255.0;
        *g = (float)((argb >>  8) & 0xFFu) / 255.0;
        *b = (float)( argb        & 0xFFu) / 255.0;
    };

    // Pack float RGB [0,1] back to 0xAARRGGBB (fully opaque)
    def color_pack(float r, float g, float b) -> u32
    {
        u32 ri, gi, bi;
        ri = (u32)(clamp(r, 0.0, 1.0) * 255.0);
        gi = (u32)(clamp(g, 0.0, 1.0) * 255.0);
        bi = (u32)(clamp(b, 0.0, 1.0) * 255.0);
        return (u32)0xFF000000 | (ri << 16) | (gi << 8) | bi;
    };

    // Scale a packed color by a float factor (distance shading)
    def color_scale(u32 argb, float factor) -> u32
    {
        float r, g, b;
        color_unpack(argb, @r, @g, @b);
        return color_pack(r * factor, g * factor, b * factor);
    };

    // Lerp between two packed colors
    def color_lerp(u32 a, u32 b, float t) -> u32
    {
        float ar, ag, ab_f, br, bg, bb_f;
        color_unpack(a, @ar, @ag, @ab_f);
        color_unpack(b, @br, @bg, @bb_f);
        return color_pack(ar + (br - ar) * t,
                           ag + (bg - ag) * t,
                           ab_f + (bb_f - ab_f) * t);
    };

    // Tint a base color with an overlay (alpha-blend using overlay alpha)
    def color_tint(u32 base, u32 tint) -> u32
    {
        float alpha, br, bg, bb, tr, tg, tb;
        alpha = (float)((tint >> 24) & 0xFFu) / 255.0;
        if (alpha < RC_EPSILON) { return base; };
        color_unpack(base, @br, @bg, @bb);
        color_unpack(tint, @tr, @tg, @tb);
        return color_pack(br + (tr - br) * alpha,
                           bg + (tg - bg) * alpha,
                           bb + (tb - bb) * alpha);
    };

    // Distance fog factor: 1.0 at distance 0, 0.0 at view_dist
    def fog_factor(float dist, float view_dist) -> float
    {
        float f;
        f = 1.0 - (dist / view_dist);
        if (f < 0.0) { f = 0.0; };
        if (f > 1.0) { f = 1.0; };
        return f;
    };

    // =========================================================================
    // MAP API
    // =========================================================================

    def rc_map_init(RCMap* m, i32 width, i32 height) -> void
    {
        size_t bytes;
        i32    i, total;

        total = width * height;
        bytes = (size_t)(total * (i32)(sizeof(RCTile) / 8));

        m.cells       = (RCTile*)fmalloc(bytes);
        m.width       = width;
        m.height      = height;
        m.floor_color = 0xFF404040;
        m.ceil_color  = 0xFF808080;

        // Zero-initialise all cells (empty, no texture, no tint)
        while (i < total)
        {
            m.cells[i].flags     = RC_TILE_EMPTY;
            m.cells[i].tex_wall  = 0;
            m.cells[i].tex_floor = 0;
            m.cells[i].tex_ceil  = 0;
            m.cells[i].tint      = 0;
            i++;
        };
    };

    def rc_map_free(RCMap* m) -> void
    {
        ffree((u64)m.cells);
        m.cells  = (RCTile*)0;
        m.width  = 0;
        m.height = 0;
    };

    // Safe cell accessor — returns empty tile for out-of-bounds queries
    def rc_map_get(RCMap* m, i32 x, i32 y) -> RCTile
    {
        RCTile empty;
        empty.flags    = RC_TILE_EMPTY;
        empty.tex_wall = 0;
        empty.tex_floor = 0;
        empty.tex_ceil  = 0;
        empty.tint      = 0;

        if (x < 0 | x >= m.width | y < 0 | y >= m.height) { return empty; };
        return *m.cells[y * m.width + x];
    };

    def rc_map_set(RCMap* m, i32 x, i32 y, RCTile tile) -> void
    {
        if (x < 0 | x >= m.width | y < 0 | y >= m.height) { return; };
        m.cells[y * m.width + x] = tile;
    };

    // Helper: set a solid wall cell quickly
    def rc_map_set_solid(RCMap* m, i32 x, i32 y, i32 tex, u32 tint) -> void
    {
        RCTile t;
        t.flags    = RC_TILE_SOLID;
        t.tex_wall = tex;
        t.tex_floor = 0;
        t.tex_ceil  = 0;
        t.tint      = tint;
        rc_map_set(m, x, y, t);
    };

    // =========================================================================
    // PLAYER & CAMERA API
    // =========================================================================

    def rc_player_init(RCPlayer* p, float x, float y, float angle) -> void
    {
        p.pos_x     = x;
        p.pos_y     = y;
        p.angle     = angle;
        p.move_speed = 0.004;
        p.turn_speed = 0.001;
    };

    def rc_camera_init(RCCamera* cam, float fov_deg, i32 sw, i32 sh, float view_dist) -> void
    {
        float fov_rad, half_fov;

        fov_rad  = fov_deg * (RC_PI / 180.0);
        half_fov = fov_rad * 0.5;

        cam.fov_h     = fov_rad;
        cam.screen_w  = sw;
        cam.screen_h  = sh;
        cam.view_dist = view_dist;
        cam.proj_dist = ((float)sw * 0.5) / tan(half_fov);
        cam.half_h    = (float)sh * 0.5;

        // dir and plane are updated by rc_camera_sync() each frame
        cam.dir_x   = 1.0;
        cam.dir_y   = 0.0;
        cam.plane_x = 0.0;
        cam.plane_y = tan(half_fov);
    };

    // Sync camera direction + projection plane from player angle.
    // Call once per frame before rc_render().
    def rc_camera_sync(RCCamera* cam, RCPlayer* p) -> void
    {
        float a, half_fov;
        a        = p.angle;
        half_fov = cam.fov_h * 0.5;
        cam.dir_x   = cos(a);
        cam.dir_y   = sin(a);
        // Projection plane is perpendicular to dir, length = tan(half_fov)
        cam.plane_x = -sin(a) * tan(half_fov);
        cam.plane_y =  cos(a) * tan(half_fov);
    };

    // Simple player movement helpers
    def rc_player_move(RCPlayer* p, RCMap* m, float forward, float strafe) -> void
    {
        float nx, ny, dx, dy, cos_a, sin_a;
        RCTile t;

        cos_a = cos(p.angle);
        sin_a = sin(p.angle);

        // Forward/backward along facing direction
        dx = cos_a * forward - sin_a * strafe;
        dy = sin_a * forward + cos_a * strafe;

        nx = p.pos_x + dx;
        ny = p.pos_y + dy;

        t = rc_map_get(m, (i32)nx, (i32)p.pos_y);
        if ((t.flags & RC_TILE_SOLID) == 0) { p.pos_x = nx; };

        t = rc_map_get(m, (i32)p.pos_x, (i32)ny);
        if ((t.flags & RC_TILE_SOLID) == 0) { p.pos_y = ny; };
    };

    def rc_player_turn(RCPlayer* p, float delta_rad) -> void
    {
        p.angle += delta_rad;
        // Wrap to [0, 2*PI)
        while (p.angle >= RC_TWO_PI) { p.angle -= RC_TWO_PI; };
        while (p.angle <  0.0)       { p.angle += RC_TWO_PI; };
    };

    // =========================================================================
    // TEXTURE PALETTE API
    // =========================================================================

    def rc_palette_init(RCTexturePalette* pal, i32 initial_cap) -> void
    {
        size_t bytes;
        bytes       = (size_t)(initial_cap * (i32)(sizeof(RCTexture) / 8));
        pal.slots   = (RCTexture*)fmalloc(bytes);
        pal.count   = 0;
        pal.cap     = initial_cap;
    };

    def rc_palette_free(RCTexturePalette* pal) -> void
    {
        i32 i;
        i = 0;
        while (i < pal.count)
        {
            if ((u64)pal.slots[i].pixels != (u64)0)
            {
                ffree((u64)pal.slots[i].pixels);
            };
            i++;
        };
        ffree((u64)pal.slots);
        pal.slots = (RCTexture*)0;
        pal.count = 0;
    };

    // Add a texture; returns slot index (0-based). Caller owns pixels.
    def rc_palette_add(RCTexturePalette* pal, u32* pixels, i32 w, i32 h) -> i32
    {
        RCTexture* new_buf;
        size_t     new_bytes;
        i32        idx;

        if (pal.count >= pal.cap)
        {
            pal.cap   = pal.cap * 2;
            new_bytes = (size_t)(pal.cap * (i32)(sizeof(RCTexture) / 8));
            new_buf   = (RCTexture*)fmalloc(new_bytes);
            memcpy((void*)new_buf, (void*)pal.slots,
                   (size_t)(pal.count * (i32)(sizeof(RCTexture) / 8)));
            ffree((u64)pal.slots);
            pal.slots = new_buf;
        };

        idx = pal.count;
        pal.slots[idx].pixels = pixels;
        pal.slots[idx].width  = w;
        pal.slots[idx].height = h;
        pal.count++;
        return idx;
    };

    // Sample a texture at normalised [0,1] UV with nearest-neighbour filtering
    def rc_tex_sample(RCTexture* tex, float u, float v) -> u32
    {
        i32 tx, ty;
        float fu, fv;

        // Tile and clamp
        fu = u - (float)(i32)u;
        fv = v - (float)(i32)v;
        if (fu < 0.0) { fu += 1.0; };
        if (fv < 0.0) { fv += 1.0; };

        tx = (i32)(fu * (float)tex.width);
        ty = (i32)(fv * (float)tex.height);

        if (tx >= tex.width)  { tx = tex.width  - 1; };
        if (ty >= tex.height) { ty = tex.height - 1; };

        return tex.pixels[ty * tex.width + tx];
    };

    // =========================================================================
    // DDA WALL RAYCASTER
    // rc_cast_walls() fills a caller-supplied RCWallHit[] (one entry per column)
    // and the float depth_buf[] (perpendicular distances, for sprite clipping).
    // =========================================================================

    def rc_cast_walls(RCMap*            m,
                      RCCamera*         cam,
                      RCPlayer*         p,
                      RCWallHit*        hits,       // [screen_w]
                      float*            depth_buf) -> void  // [screen_w]
    {
        i32   col, map_x, map_y, step_x, step_y, hit_face;
        float ray_dir_x, ray_dir_y;
        float delta_dist_x, delta_dist_y;
        float side_dist_x, side_dist_y;
        float perp_dist, wall_u;
        float cam_x;  // camera space x: -1 (left) to +1 (right)
        bool  hit_solid;
        i32   draw_start, draw_end, line_height;
        RCTile tile;

        col = 0;
        while (col < cam.screen_w)
        {
            // -----------------------------------------------------------------
            // 1. Compute ray direction for this column
            // -----------------------------------------------------------------
            cam_x = 2.0 * ((float)col / (float)cam.screen_w) - 1.0;

            ray_dir_x = cam.dir_x + cam.plane_x * cam_x;
            ray_dir_y = cam.dir_y + cam.plane_y * cam_x;

            // Current map cell the player stands in
            map_x = (i32)p.pos_x;
            map_y = (i32)p.pos_y;

            // -----------------------------------------------------------------
            // 2. DDA step sizes
            // -----------------------------------------------------------------
            // delta_dist: distance ray travels between consecutive X or Y grid lines
            if (abs(ray_dir_x) < RC_EPSILON)
            {
                delta_dist_x = RC_INF;
            }
            else
            {
                delta_dist_x = abs(1.0 / ray_dir_x);
            };

            if (abs(ray_dir_y) < RC_EPSILON)
            {
                delta_dist_y = RC_INF;
            }
            else
            {
                delta_dist_y = abs(1.0 / ray_dir_y);
            };

            // Step direction and initial side distances
            if (ray_dir_x < 0.0)
            {
                step_x      = -1;
                side_dist_x = (p.pos_x - (float)map_x) * delta_dist_x;
            }
            else
            {
                step_x      = 1;
                side_dist_x = ((float)(map_x + 1) - p.pos_x) * delta_dist_x;
            };

            if (ray_dir_y < 0.0)
            {
                step_y      = -1;
                side_dist_y = (p.pos_y - (float)map_y) * delta_dist_y;
            }
            else
            {
                step_y      = 1;
                side_dist_y = ((float)(map_y + 1) - p.pos_y) * delta_dist_y;
            };

            // -----------------------------------------------------------------
            // 3. DDA march
            // -----------------------------------------------------------------
            hit_solid = false;
            hit_face  = RC_FACE_NONE;
            perp_dist = RC_INF;

            while (!hit_solid)
            {
                if (side_dist_x < side_dist_y)
                {
                    side_dist_x += delta_dist_x;
                    map_x       += step_x;
                    hit_face     = (step_x > 0) ? RC_FACE_X_NEG : RC_FACE_X_POS;
                }
                else
                {
                    side_dist_y += delta_dist_y;
                    map_y       += step_y;
                    hit_face     = (step_y > 0) ? RC_FACE_Y_NEG : RC_FACE_Y_POS;
                };

                tile = rc_map_get(m, map_x, map_y);

                if (tile.flags & RC_TILE_SOLID)
                {
                    hit_solid = true;
                };

                // Stop if we've exceeded the view distance
                if (hit_face == RC_FACE_X_POS | hit_face == RC_FACE_X_NEG)
                {
                    perp_dist = (side_dist_x - delta_dist_x);
                }
                else
                {
                    perp_dist = (side_dist_y - delta_dist_y);
                };

                if (perp_dist > cam.view_dist) { hit_solid = true; };
            };

            // -----------------------------------------------------------------
            // 4. Perpendicular (fish-eye corrected) distance
            // -----------------------------------------------------------------
            if (hit_face == RC_FACE_X_POS | hit_face == RC_FACE_X_NEG)
            {
                perp_dist = side_dist_x - delta_dist_x;
            }
            else
            {
                perp_dist = side_dist_y - delta_dist_y;
            };

            depth_buf[col] = perp_dist;

            // -----------------------------------------------------------------
            // 5. Compute wall texture U coordinate
            // -----------------------------------------------------------------
            if (hit_face == RC_FACE_X_POS | hit_face == RC_FACE_X_NEG)
            {
                wall_u = p.pos_y + perp_dist * ray_dir_y;
            }
            else
            {
                wall_u = p.pos_x + perp_dist * ray_dir_x;
            };
            wall_u -= (float)(i32)wall_u;  // fractional part

            // -----------------------------------------------------------------
            // 6. Projected wall strip height
            // -----------------------------------------------------------------
            if (perp_dist < RC_EPSILON) { perp_dist = RC_EPSILON; };
            line_height = (i32)(cam.proj_dist / perp_dist);

            draw_start = (i32)(cam.half_h - (float)line_height * 0.5);
            draw_end   = (i32)(cam.half_h + (float)line_height * 0.5);

            if (draw_start < 0)           { draw_start = 0; };
            if (draw_end   >= cam.screen_h) { draw_end = cam.screen_h - 1; };

            // -----------------------------------------------------------------
            // 7. Store result
            // -----------------------------------------------------------------
            hits[col].dist     = perp_dist;
            hits[col].wall_u   = wall_u;
            hits[col].tile_x   = map_x;
            hits[col].tile_y   = map_y;
            hits[col].face     = hit_face;
            hits[col].tex_idx  = tile.tex_wall;
            hits[col].tint     = tile.tint;
            hits[col].draw_top = draw_start;
            hits[col].draw_bot = draw_end;

            col++;
        };
    };

    // =========================================================================
    // FLOOR / CEILING RAYCASTER
    // Fills pixels above and below each wall strip using planar projection.
    // =========================================================================

    def rc_cast_floor(RCMap*    m,
                      RCCamera* cam,
                      RCPlayer* p,
                      RCWallHit* hits,
                      RCTexturePalette* palette,  // may be null
                      u32*      buf) -> void
    {
        i32   row, col, cell_x, cell_y;
        float row_dist, floor_x, floor_y, step_x, step_y;
        float tex_u, tex_v;
        float shade;
        u32   floor_col, ceil_col;
        RCTile tile;
        float left_ray_x, left_ray_y, right_ray_x, right_ray_y;
        float pos_z;  // half screen_h (eye height = 0.5)

        pos_z = cam.half_h;

        while (row < cam.screen_h)
        {
            // Rays for leftmost and rightmost columns
            left_ray_x  = cam.dir_x - cam.plane_x;
            left_ray_y  = cam.dir_y - cam.plane_y;
            right_ray_x = cam.dir_x + cam.plane_x;
            right_ray_y = cam.dir_y + cam.plane_y;

            // Is this row above (ceiling) or below (floor) the horizon?
            if (row < (i32)pos_z)
            {
                // ---- Ceiling ----
                // Horizontal distance to ceiling at this scanline
                if ((i32)pos_z - row == 0) { row++; continue; };
                row_dist = pos_z / (pos_z - (float)row);

                // Step along floor ray for each column
                step_x = row_dist * (right_ray_x - left_ray_x) / (float)cam.screen_w;
                step_y = row_dist * (right_ray_y - left_ray_y) / (float)cam.screen_w;

                floor_x = p.pos_x + row_dist * left_ray_x;
                floor_y = p.pos_y + row_dist * left_ray_y;

                shade = fog_factor(row_dist, cam.view_dist);

                col = 0;
                while (col < cam.screen_w)
                {
                    cell_x = (i32)floor_x;
                    cell_y = (i32)floor_y;
                    tile   = rc_map_get(m, cell_x, cell_y);

                    if (palette != (RCTexturePalette*)0 & tile.tex_ceil > 0 &
                        tile.tex_ceil <= palette.count)
                    {
                        tex_u    = floor_x - (float)cell_x;
                        tex_v    = floor_y - (float)cell_y;
                        ceil_col = rc_tex_sample(@palette.slots[tile.tex_ceil - 1], tex_u, tex_v);
                    }
                    else
                    {
                        ceil_col = m.ceil_color;
                    };

                    if (tile.tint != 0) { ceil_col = color_tint(ceil_col, tile.tint); };
                    ceil_col = color_scale(ceil_col, shade);

                    buf[row * cam.screen_w + col] = ceil_col;

                    floor_x += step_x;
                    floor_y += step_y;
                    col++;
                };
            }
            else
            {
                // ---- Floor ----
                if (row - (i32)pos_z == 0) { row++; continue; };
                row_dist = pos_z / ((float)row - pos_z);

                step_x = row_dist * (right_ray_x - left_ray_x) / (float)cam.screen_w;
                step_y = row_dist * (right_ray_y - left_ray_y) / (float)cam.screen_w;

                floor_x = p.pos_x + row_dist * left_ray_x;
                floor_y = p.pos_y + row_dist * left_ray_y;

                shade = fog_factor(row_dist, cam.view_dist);

                col = 0;
                while (col < cam.screen_w)
                {
                    cell_x  = (i32)floor_x;
                    cell_y  = (i32)floor_y;
                    tile    = rc_map_get(m, cell_x, cell_y);

                    if (palette != (RCTexturePalette*)0 & tile.tex_floor > 0 &
                        tile.tex_floor <= palette.count)
                    {
                        tex_u      = floor_x - (float)cell_x;
                        tex_v      = floor_y - (float)cell_y;
                        floor_col  = rc_tex_sample(@palette.slots[tile.tex_floor - 1], tex_u, tex_v);
                    }
                    else
                    {
                        floor_col = m.floor_color;
                    };

                    if (tile.tint != 0) { floor_col = color_tint(floor_col, tile.tint); };
                    floor_col = color_scale(floor_col, shade);

                    buf[row * cam.screen_w + col] = floor_col;

                    floor_x += step_x;
                    floor_y += step_y;
                    col++;
                };
            };

            row++;
        };
    };

    // =========================================================================
    // SKY PASS
    // Fills the upper half of the buffer with a vertical gradient if sky != null.
    // =========================================================================

    def rc_draw_sky(RCSky* sky, RCCamera* cam, u32* buf) -> void
    {
        i32   row, col, half;
        float t;
        u32   sky_col;

        half = (i32)cam.half_h;
        row  = 0;
        while (row < half)
        {
            t       = (float)row / (float)half;
            sky_col = color_lerp(sky.color_top, sky.color_horizon, t);
            col     = 0;
            while (col < cam.screen_w)
            {
                buf[row * cam.screen_w + col] = sky_col;
                col++;
            };
            row++;
        };
    };

    // =========================================================================
    // WALL STRIP DRAW PASS
    // Iterates the precomputed hits[] and writes textured (or solid) strips.
    // =========================================================================

    def rc_draw_walls(RCCamera*        cam,
                      RCWallHit*       hits,
                      RCTexturePalette* palette,
                      u32*             buf) -> void
    {
        i32   col, y, tex_y, tex_h;
        float shade, v_step, v_pos, tex_v, tex_u;
        u32   wall_col;
        RCTexture* tex;

        while (col < cam.screen_w)
        {
            shade = fog_factor(hits[col].dist, cam.view_dist);

            // Decide pixel source: texture or solid tint/grey
            tex = (RCTexture*)0;
            if (palette != (RCTexturePalette*)0 & hits[col].tex_idx > 0 &
                hits[col].tex_idx <= palette.count)
            {
                tex = @palette.slots[hits[col].tex_idx - 1];
                tex_h = tex.height;
            }
            else
            {
                tex_h = 64;  // Dummy height for fallback color
            };

            // Vertical texture step per screen pixel
            v_step = (float)tex_h / (float)(hits[col].draw_bot - hits[col].draw_top + 1);
            v_pos  = 0.0;

            tex_u = hits[col].wall_u;

            // Darken X-axis faces slightly for visual depth cue
            if (hits[col].face == RC_FACE_X_POS | hits[col].face == RC_FACE_X_NEG)
            {
                shade *= 0.7;
            };

            y = hits[col].draw_top;
            while (y <= hits[col].draw_bot)
            {
                if (tex != (RCTexture*)0)
                {
                    tex_v    = v_pos / (float)tex_h;
                    wall_col = rc_tex_sample(tex, tex_u, tex_v);
                }
                else
                {
                    // No texture — use tint or a default grey
                    wall_col = hits[col].tint != 0 ? hits[col].tint : (u32)0xFFAAAAAA;
                };

                if (hits[col].tint != 0 & tex != (RCTexture*)0)
                {
                    wall_col = color_tint(wall_col, hits[col].tint);
                };

                wall_col = color_scale(wall_col, shade);
                buf[y * cam.screen_w + col] = wall_col;

                v_pos += v_step;
                y++;
            };

            col++;
        };
    };

    // =========================================================================
    // SPRITE PROJECTION & DRAW
    // Sprites are sorted back-to-front, then projected and drawn respecting
    // the depth buffer produced by rc_cast_walls().
    // =========================================================================

    // Compute squared distance from player to each sprite (for sort key)
    def rc_sprite_distances(RCSprite* sprites, i32 count, RCPlayer* p) -> void
    {
        i32   i;
        float dx, dy;
        i = 0;
        while (i < count)
        {
            dx = sprites[i].world_x - p.pos_x;
            dy = sprites[i].world_y - p.pos_y;
            sprites[i].dist_sq = dx * dx + dy * dy;
            i++;
        };
    };

    // Insertion sort sprites[] by dist_sq descending (painter's order)
    def rc_sprite_sort(RCSprite* sprites, i32 count) -> void
    {
        i32      i, j;
        RCSprite tmp;
        i = 1;
        while (i < count)
        {
            tmp = sprites[i];
            j   = i - 1;
            while (j >= 0 & sprites[j].dist_sq < tmp.dist_sq)
            {
                sprites[j + 1] = sprites[j];
                j--;
            };
            sprites[j + 1] = tmp;
            i++;
        };
    };

    def rc_draw_sprites(RCCamera*         cam,
                        RCPlayer*         p,
                        RCSprite*         sprites,
                        i32               sprite_count,
                        float*            depth_buf,
                        RCTexturePalette* palette,
                        u32*              buf) -> void
    {
        i32   s, x, y,
              sprite_screen_x,
              sprite_height, sprite_width,
              draw_start_y, draw_end_y,
              draw_start_x, draw_end_x,
              tex_x, tex_y;
        float sprite_x, sprite_y,
              inv_det, transform_x, transform_y,
              v_move_screen,
              tex_u, tex_v,
              shade, det;
        u32   sprite_col;
        RCTexture* tex;

        // inv_det: inverse of camera determinant (for transform)
        det     = cam.plane_x * cam.dir_y - cam.dir_x * cam.plane_y;
        inv_det = 1.0 / (det + RC_EPSILON);

        // Sort sprites back to front
        rc_sprite_distances(sprites, sprite_count, p);
        rc_sprite_sort(sprites, sprite_count);

        while (s < sprite_count)
        {
            // Translate sprite relative to camera
            sprite_x = sprites[s].world_x - p.pos_x;
            sprite_y = sprites[s].world_y - p.pos_y;

            // Transform into camera space
            transform_x = inv_det * (cam.dir_y * sprite_x - cam.dir_x * sprite_y);
            transform_y = inv_det * (-cam.plane_y * sprite_x + cam.plane_x * sprite_y);

            // Behind the camera
            if (transform_y <= 0.0) { s++; continue; };

            // Screen X of sprite centre
            sprite_screen_x = (i32)(((float)cam.screen_w * 0.5) *
                              (1.0 + transform_x / transform_y));

            // Projected dimensions
            sprite_height = (i32)(abs(cam.proj_dist / transform_y) * sprites[s].scale);
            sprite_width  = sprite_height;

            v_move_screen = 0.0;

            draw_start_y = (i32)(cam.half_h - (float)sprite_height * 0.5 + v_move_screen);
            draw_end_y   = (i32)(cam.half_h + (float)sprite_height * 0.5 + v_move_screen);

            if (draw_start_y < 0)             { draw_start_y = 0; };
            if (draw_end_y   >= cam.screen_h)  { draw_end_y = cam.screen_h - 1; };

            draw_start_x = sprite_screen_x - sprite_width  / 2;
            draw_end_x   = sprite_screen_x + sprite_width  / 2;

            if (draw_start_x < 0)             { draw_start_x = 0; };
            if (draw_end_x   >= cam.screen_w)  { draw_end_x = cam.screen_w - 1; };

            // Resolve texture
            tex = (RCTexture*)0;
            if (palette != (RCTexturePalette*)0 & sprites[s].tex_idx > 0 &
                sprites[s].tex_idx <= palette.count)
            {
                tex = @palette.slots[sprites[s].tex_idx - 1];
            };

            shade = fog_factor(sqrt(sprites[s].dist_sq), cam.view_dist);

            x = draw_start_x;
            while (x <= draw_end_x)
            {
                // Depth test: skip if wall is closer
                if (transform_y >= depth_buf[x]) { x++; continue; };

                tex_u = (float)(x - (sprite_screen_x - sprite_width / 2)) /
                        (float)(sprite_width + 1);

                y = draw_start_y;
                while (y <= draw_end_y)
                {
                    tex_v = (float)(y - draw_start_y) / (float)(sprite_height + 1);

                    if (tex != (RCTexture*)0)
                    {
                        sprite_col = rc_tex_sample(tex, tex_u, tex_v);
                        // Treat pure magenta (0xFFFF00FF) as transparent
                        if ((sprite_col & (u32)0x00FFFFFF) == (u32)0x00FF00FF)
                        {
                            y++;
                            continue;
                        };
                    }
                    else
                    {
                        sprite_col = sprites[s].tint != 0 ? sprites[s].tint : (u32)0xFFFFFFFF;
                    };

                    if (sprites[s].tint != 0 & tex != (RCTexture*)0)
                    {
                        sprite_col = color_tint(sprite_col, sprites[s].tint);
                    };

                    sprite_col = color_scale(sprite_col, shade);
                    buf[y * cam.screen_w + x] = sprite_col;

                    y++;
                };
                x++;
            };

            s++;
        };
    };

    // =========================================================================
    // MAIN RENDER ENTRY POINT
    // buf must be caller-allocated: screen_w * screen_h * sizeof(u32) bytes.
    // rc_camera_sync() must be called before this if the player has moved.
    // =========================================================================

    def rc_render(RCScene* scene, u32* buf) -> void
    {
        RCWallHit* hits;
        float*     depth_buf;
        size_t     hit_bytes, depth_bytes;
        i32        sw;

        sw = scene.cam.screen_w;

        // Allocate per-column intermediate buffers on the heap
        hit_bytes   = (size_t)(sw * (i32)(sizeof(RCWallHit) / 8));
        depth_bytes = (size_t)(sw * (i32)(sizeof(float)     / 8));

        hits      = (RCWallHit*)fmalloc(hit_bytes);
        depth_buf = (float*)fmalloc(depth_bytes);

        // --- Sky / ceiling background ---
        if ((scene.passes & RC_PASS_SKY) & scene.sky != (RCSky*)0)
        {
            rc_draw_sky(scene.sky, scene.cam, buf);
        };

        // --- Floor & ceiling planar pass ---
        if (scene.passes & RC_PASS_FLOOR)
        {
            rc_cast_floor(scene.map, scene.cam, scene.player, hits, scene.palette, buf);
        };

        // --- Wall DDA pass ---
        if (scene.passes & RC_PASS_WALLS)
        {
            rc_cast_walls(scene.map, scene.cam, scene.player, hits, depth_buf);
            rc_draw_walls(scene.cam, hits, scene.palette, buf);
        }
        else
        {
            // Even if walls are disabled, fill depth_buf to infinity for sprites
            i32 ci;
            ci = 0;
            while (ci < sw)
            {
                depth_buf[ci] = RC_INF;
                ci++;
            };
        };

        // --- Sprite pass ---
        if ((scene.passes & RC_PASS_SPRITES) &
            scene.sprites != (RCSprite*)0 &
            scene.sprite_count > 0)
        {
            rc_draw_sprites(scene.cam, scene.player,
                            scene.sprites, scene.sprite_count,
                            depth_buf, scene.palette, buf);
        };

        ffree((u64)hits);
        ffree((u64)depth_buf);
    };

    // =========================================================================
    // CONVENIENCE SCENE BUILDER
    // =========================================================================

    // Initialise an RCScene with safe defaults (all passes enabled, no sprites).
    def rc_scene_init(RCScene*          scene,
                      RCMap*            map,
                      RCPlayer*         player,
                      RCCamera*         cam,
                      RCTexturePalette* palette,
                      RCSky*            sky) -> void
    {
        scene.map          = map;
        scene.player       = player;
        scene.cam          = cam;
        scene.palette      = palette;
        scene.sprites      = (RCSprite*)0;
        scene.sprite_count = 0;
        scene.sky          = sky;
        scene.passes       = RC_PASS_ALL;
    };

    // Set sprite array (not owned — caller manages lifetime)
    def rc_scene_set_sprites(RCScene* scene, RCSprite* sprites, i32 count) -> void
    {
        scene.sprites      = sprites;
        scene.sprite_count = count;
    };

};  // namespace raycaster

#endif;
