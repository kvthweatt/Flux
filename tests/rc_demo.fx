// Author: Karac V. Thweatt
//
// rc_demo.fx - Raycasting Library Demo
//
// Renders an interactive 2.5D raycasted world using raycasting.fx.
// The render runs on a background thread so the window stays live
// during frame composition; the finished frame is uploaded to an
// OpenGL texture and blitted full-screen each tick.
//
// Controls:
//   W / S         - Move forward / backward
//   A / D         - Strafe left / right
//   LEFT / RIGHT  - Turn left / right
//   1             - Scene: Castle Courtyard
//   2             - Scene: Neon Dungeon
//   3             - Scene: Open Arena
//   ESC           - Quit
//

#import "standard.fx", "windows.fx", "opengl.fx", "threading.fx", "atomics.fx", "raycasting.fx";

using standard::system::windows;
using standard::math;
using standard::memory::allocators::stdheap;
using standard::threading;
using standard::atomic;
using raycaster;

// ============================================================================
// CONSTANTS
// ============================================================================

global i32 g_img_w = 800,
           g_img_h = 450;

#def MAP_W       24;
#def MAP_H       24;
#def SPRITE_CAP  64;

// ============================================================================
// RENDER WORKER — runs rc_render() on a background thread
// ============================================================================

struct RCWorkOrder
{
    RCScene* scene;
    u32*     pixels;
    volatile i32 done;   // 0 = in progress, 1 = finished
};

global RCWorkOrder g_work;

def rc_worker(void* arg) -> void*
{
    rc_camera_sync(g_work.scene.cam, g_work.scene.player);
    rc_render(g_work.scene, g_work.pixels);
    store32(@g_work.done, 1);
    return (void*)0;
};

// ============================================================================
// PROCEDURAL TEXTURE GENERATORS
// Returns a heap-allocated u32[w*h] pixel array (caller frees)
// ============================================================================

// Stone-brick pattern: dark mortar lines + noisy face
def gen_tex_stone(i32 w, i32 h) -> u32*
{
    u32*  px;
    u32   grey;
    i32   x, y, bx, by, hv,
          row_offset;
    float nx, ny, noise, brightness;
    u32   c;

    px = (u32*)fmalloc((size_t)(w * h * (i32)(sizeof(u32) / 8)));

    while (y < h)
    {
        // Alternate brick rows by half a brick width
        row_offset = (y / 8) & 1 ? w / 4 : 0;

        x = 0;
        while (x < w)
        {
            bx = (x + row_offset) % w;
            by = y % 8;

            // Mortar: 1 pixel border inside each 16×8 brick
            if (bx % 16 == 0 | by == 0)
            {
                c = (u32)0xFF303030;
            }
            else
            {
                // Simple value noise via bit-hash
                hv = (x * 1619 + y * 31337 + x * y * 509) & 0x3F;
                brightness = 0.42 + (float)hv / 255.0;
                grey = (u32)(brightness * 160.0);
                c = (u32)0xFF000000 | (grey << 16) | (grey << 8) | grey;
            };

            px[y * w + x] = c;
            x++;
        };
        y++;
    };

    return px;
};

// Wood-plank pattern: horizontal grain lines
def gen_tex_wood(i32 w, i32 h) -> u32*
{
    u32*  px;
    u32  ri, gi, bi;
    i32   x, y, grain;
    float t, r, g, b, plank_t;

    px = (u32*)fmalloc((size_t)(w * h * (i32)(sizeof(u32) / 8)));

    while (y < h)
    {
        x = 0;
        while (x < w)
        {
            grain = (x * 127 + y * 53) & 0x1F;
            plank_t = (float)(y % 16) / 16.0;
            r = 0.55 + plank_t * 0.15 + (float)grain / 512.0;
            g = 0.30 + plank_t * 0.10 + (float)grain / 768.0;
            b = 0.10;
            ri = (u32)(clamp(r, 0.0, 1.0) * 255.0);
            gi = (u32)(clamp(g, 0.0, 1.0) * 255.0);
            bi = (u32)(clamp(b, 0.0, 1.0) * 255.0);
            px[y * w + x] = (u32)0xFF000000 | (ri << 16) | (gi << 8) | bi;
            x++;
        };
        y++;
    };

    return px;
};

// Neon-grid pattern: dark background with bright cyan/magenta grid lines
def gen_tex_neon(i32 w, i32 h) -> u32*
{
    u32* px;
    u32 c, dark;
    i32  x, y, panel_x, panel_y, hv;
    bool hline, vline;

    px = (u32*)fmalloc((size_t)(w * h * (i32)(sizeof(u32) / 8)));

    while (y < h)
    {
        x = 0;
        while (x < w)
        {
            hline = (y % 16 == 0) | (y % 16 == 1);
            vline = (x % 16 == 0) | (x % 16 == 1);

            if (hline & vline) { c = (u32)0xFFFFFFFF; }
            elif (hline)        { c = (u32)0xFF00FFFF; }   // cyan
            elif (vline)        { c = (u32)0xFFFF00FF; }   // magenta
            else
            {
                // Dark tiled panel with slight variation
                panel_x = x / 16;
                panel_y = y / 16;
                hv = (panel_x * 73 + panel_y * 131) & 0xFF;
                dark = (u32)(10 + (hv & 0x0F));
                c = (u32)0xFF000000 | (dark << 8);          // very dark green tint
            };

            px[y * w + x] = c;
            x++;
        };
        y++;
    };

    return px;
};

// Grass-and-dirt floor
def gen_tex_grass(i32 w, i32 h) -> u32*
{
    u32* px;
    u32  ri, gi, bi;
    i32  x, y, hv;
    float r, g, b;

    px = (u32*)fmalloc((size_t)(w * h * (i32)(sizeof(u32) / 8)));

    while (y < h)
    {
        x = 0;
        while (x < w)
        {
            hv = (x * 1021 + y * 6271 + x * y * 37) & 0x3F;
            g = 0.30 + (float)hv / 255.0;
            r = g * 0.5;
            b = g * 0.3;
            ri = (u32)(r * 255.0);
            gi = (u32)(g * 255.0);
            bi = (u32)(b * 255.0);
            px[y * w + x] = (u32)0xFF000000 | (ri << 16) | (gi << 8) | bi;
            x++;
        };
        y++;
    };

    return px;
};

// Simple pillar sprite (white circle on magenta key)
def gen_tex_pillar(i32 w, i32 h) -> u32*
{
    u32*  px;
    u32   c, v;
    i32   x, y;
    float fx, fy, cx, cy, dist, shade;

    px = (u32*)fmalloc((size_t)(w * h * (i32)(sizeof(u32) / 8)));

    cx = (float)w * 0.5;
    cy = (float)h * 0.5;

    while (y < h)
    {
        x = 0;
        while (x < w)
        {
            fx   = (float)x - cx;
            fy   = (float)y - cy;
            dist = sqrt(fx * fx + fy * fy);

            if (dist < (float)w * 0.38)
            {
                // Pillar body — vertical shading
                shade = 1.0 - (fx / ((float)w * 0.38)) * 0.5;
                shade = clamp(shade, 0.0, 1.0);
                v = (u32)(shade * 220.0);
                c = (u32)0xFF000000 | (v << 16) | (v << 8) | v;
            }
            else
            {
                c = (u32)0xFFFF00FF;   // magenta = transparent key
            };

            px[y * w + x] = c;
            x++;
        };
        y++;
    };

    return px;
};

// Torch sprite — small orange flame on magenta key
def gen_tex_torch(i32 w, i32 h) -> u32*
{
    u32*  px;
    u32   c, ri, gi;
    i32   x, y;
    float fx, fy, cx, intensity, max_r,
          t, r, g, b;

    px = (u32*)fmalloc((size_t)(w * h * (i32)(sizeof(u32) / 8)));

    cx = (float)w * 0.5;

    while (y < h)
    {
        x = 0;
        while (x < w)
        {
            fx = (float)x - cx;
            fy = (float)y;

            // Flame shape: tapers toward top, widest at bottom 60%
            max_r = (float)w * 0.35 * ((float)(h - y) / (float)h);
            if (abs(fx) < max_r & fy > (float)h * 0.15)
            {
                // Gradient: yellow at base → orange → red at tip
                t   = 1.0 - (fy / (float)h);
                r   = 1.0;
                g   = 0.6 - t * 0.5;
                b   = 0.0;
                ri = (u32)(r * 255.0);
                gi = (u32)(clamp(g, 0.0, 1.0) * 255.0);
                c = (u32)0xFF000000 | (ri << 16) | (gi << 8);
            }
            else
            {
                c = (u32)0xFFFF00FF;   // transparent
            };

            px[y * w + x] = c;
            x++;
        };
        y++;
    };

    return px;
};

// ============================================================================
// SCENE BUILDERS
// ============================================================================

// Helper: surround the map border with solid walls
def border_walls(RCMap* m, i32 tex, u32 tint) -> void
{
    i32 x, y;
    while (x < m.width)
    {
        rc_map_set_solid(m, x, 0,          tex, tint);
        rc_map_set_solid(m, x, m.height-1, tex, tint);
        x++;
    };
    y = 1;
    while (y < m.height - 1)
    {
        rc_map_set_solid(m, 0,         y, tex, tint);
        rc_map_set_solid(m, m.width-1, y, tex, tint);
        y++;
    };
};

// ---- Scene 1: Castle Courtyard ----
// Stone walls, wood accents, grass floor, sky, pillar sprites
def build_scene_castle(RCMap*            m,
                       RCPlayer*         p,
                       RCCamera*         cam,
                       RCTexturePalette* pal,
                       RCSprite*         sprites,
                       i32*              sprite_count,
                       RCSky*            sky) -> void
{
    i32 x, y;
    u32* tex_px;
    RCTile t;

    // ---- Textures ----
    // Slot 1: stone
    tex_px = gen_tex_stone(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 2: wood
    tex_px = gen_tex_wood(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 3: grass floor
    tex_px = gen_tex_grass(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 4: pillar sprite
    tex_px = gen_tex_pillar(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 5: torch sprite
    tex_px = gen_tex_torch(32, 64);
    rc_palette_add(pal, tex_px, 32, 64);

    // ---- Map ----
    m.floor_color = (u32)0xFF304020;
    m.ceil_color  = (u32)0xFF708090;

    // All floor cells use grass (tex 3) and stone ceiling (tex 1)
    while (y < MAP_H)
    {
        x = 0;
        while (x < MAP_W)
        {
            t.flags     = RC_TILE_EMPTY;
            t.tex_wall  = 0;
            t.tex_floor = 3;
            t.tex_ceil  = 0;
            t.tint      = 0;
            rc_map_set(m, x, y, t);
            x++;
        };
        y++;
    };

    // Border: stone walls
    border_walls(m, 1, 0);

    // Inner layout: cross-shaped corridors with wood doors
    // Horizontal wall
    x = 4;
    while (x < 20)
    {
        if (x != 12) { rc_map_set_solid(m, x, 8, 1, 0); };
        x++;
    };

    // Vertical wall
    y = 4;
    while (y < 20)
    {
        if (y != 12) { rc_map_set_solid(m, 12, y, 1, 0); };
        y++;
    };

    // Corner rooms — wood accent walls
    rc_map_set_solid(m,  6,  6, 2, 0);
    rc_map_set_solid(m,  7,  6, 2, 0);
    rc_map_set_solid(m,  6,  7, 2, 0);

    rc_map_set_solid(m, 17,  6, 2, 0);
    rc_map_set_solid(m, 16,  6, 2, 0);
    rc_map_set_solid(m, 17,  7, 2, 0);

    rc_map_set_solid(m,  6, 17, 2, 0);
    rc_map_set_solid(m,  7, 17, 2, 0);
    rc_map_set_solid(m,  6, 16, 2, 0);

    rc_map_set_solid(m, 17, 17, 2, 0);
    rc_map_set_solid(m, 16, 17, 2, 0);
    rc_map_set_solid(m, 17, 16, 2, 0);

    // ---- Player ----
    rc_player_init(p, 2.5, 2.5, 0.0);

    // ---- Camera ----
    rc_camera_init(cam, 66.0, g_img_w, g_img_h, 18.0);

    // ---- Sky ----
    sky.color_top     = (u32)0xFF87CEEB;
    sky.color_horizon = (u32)0xFFD0E8F0;

    // ---- Sprites: pillars at corridor intersections, torches on walls ----
    *sprite_count = 0;

    // Pillar sprites (tex slot 4 = index 4)
    float[4] px_arr = [9.5, 14.5, 9.5, 14.5];
    float[4] py_arr = [9.5, 9.5, 14.5, 14.5];
    i32 si;
    while (si < 4)
    {
        sprites[*sprite_count].world_x = px_arr[si];
        sprites[*sprite_count].world_y = py_arr[si];
        sprites[*sprite_count].tex_idx = 4;
        sprites[*sprite_count].scale   = 1.0;
        sprites[*sprite_count].tint    = 0;
        (*sprite_count)++;
        si++;
    };

    // Torch sprites along outer walls (tex slot 5 = index 5)
    float[8] tx_arr = [1.5, 22.5, 1.5, 22.5, 6.5, 17.5, 6.5, 17.5];
    float[8] ty_arr = [6.5,  6.5, 17.5, 17.5, 1.5,  1.5, 22.5, 22.5];
    si = 0;
    while (si < 8)
    {
        sprites[*sprite_count].world_x = tx_arr[si];
        sprites[*sprite_count].world_y = ty_arr[si];
        sprites[*sprite_count].tex_idx = 5;
        sprites[*sprite_count].scale   = 0.6;
        sprites[*sprite_count].tint    = (u32)0x40FF8800;  // warm orange tint
        (*sprite_count)++;
        si++;
    };
};

// ---- Scene 2: Neon Dungeon ----
// Neon grid walls, dark floor/ceiling, glowing pillar sprites
def build_scene_neon(RCMap*            m,
                     RCPlayer*         p,
                     RCCamera*         cam,
                     RCTexturePalette* pal,
                     RCSprite*         sprites,
                     i32*              sprite_count,
                     RCSky*            sky) -> void
{
    i32 x, y;
    u32* tex_px;
    RCTile t;

    // Slot 1: neon grid
    tex_px = gen_tex_neon(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 2: pillar (reused)
    tex_px = gen_tex_pillar(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    m.floor_color = (u32)0xFF080810;
    m.ceil_color  = (u32)0xFF080810;

    // All cells empty
    while (y < MAP_H)
    {
        x = 0;
        while (x < MAP_W)
        {
            t.flags     = RC_TILE_EMPTY;
            t.tex_wall  = 0;
            t.tex_floor = 0;
            t.tex_ceil  = 0;
            t.tint      = 0;
            rc_map_set(m, x, y, t);
            x++;
        };
        y++;
    };

    // Border: neon walls, cyan tint
    border_walls(m, 1, (u32)0x3000FFFF);

    // Maze-like internal walls (neon, alternating tints)
    i32 wx = 2, wy = 8;
    // Horizontal bars
    while (wx < 10)
    {
        rc_map_set_solid(m, wx, 5,  1, (u32)0x2000FFFF);
        rc_map_set_solid(m, wx, 18, 1, (u32)0x20FF00FF);
        wx++;
    };
    wx = 14;
    while (wx < 22)
    {
        rc_map_set_solid(m, wx, 5,  1, (u32)0x20FF00FF);
        rc_map_set_solid(m, wx, 18, 1, (u32)0x2000FFFF);
        wx++;
    };

    // Vertical bars
    wy = 8;
    while (wy < 16)
    {
        rc_map_set_solid(m,  6, wy, 1, (u32)0x2000FF88);
        rc_map_set_solid(m, 17, wy, 1, (u32)0x20FF8800);
        wy++;
    };

    // Central room walls
    rc_map_set_solid(m, 10, 10, 1, (u32)0x30FFFFFF);
    rc_map_set_solid(m, 11, 10, 1, (u32)0x30FFFFFF);
    rc_map_set_solid(m, 13, 10, 1, (u32)0x30FFFFFF);
    rc_map_set_solid(m, 10, 13, 1, (u32)0x30FFFFFF);
    rc_map_set_solid(m, 11, 13, 1, (u32)0x30FFFFFF);
    rc_map_set_solid(m, 13, 13, 1, (u32)0x30FFFFFF);

    rc_player_init(p, 2.5, 2.5, 0.0);
    rc_camera_init(cam, 72.0, g_img_w, g_img_h, 20.0);

    // No sky — keep dark ceiling color
    sky.color_top     = (u32)0xFF080810;
    sky.color_horizon = (u32)0xFF080810;

    // Glowing pillar sprites (tex 2, cyan tint)
    *sprite_count = 0;
    float[6] sx = [12.0, 5.5, 18.5, 5.5, 18.5, 12.0];
    float[6] sy = [12.0, 11.5, 11.5, 11.5, 11.5, 5.5];
    i32 si;
    while (si < 6)
    {
        sprites[*sprite_count].world_x = sx[si];
        sprites[*sprite_count].world_y = sy[si];
        sprites[*sprite_count].tex_idx = 2;
        sprites[*sprite_count].scale   = 0.8;
        sprites[*sprite_count].tint    = (u32)0x5000FFCC;  // cyan glow
        (*sprite_count)++;
        si++;
    };
};

// ---- Scene 3: Open Arena ----
// Stone outer ring, open centre, lots of pillar and torch sprites
def build_scene_arena(RCMap*            m,
                      RCPlayer*         p,
                      RCCamera*         cam,
                      RCTexturePalette* pal,
                      RCSprite*         sprites,
                      i32*              sprite_count,
                      RCSky*            sky) -> void
{
    i32 x, y;
    u32* tex_px;
    RCTile t;

    // Slot 1: stone wall
    tex_px = gen_tex_stone(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 2: grass floor
    tex_px = gen_tex_grass(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 3: pillar
    tex_px = gen_tex_pillar(64, 64);
    rc_palette_add(pal, tex_px, 64, 64);

    // Slot 4: torch
    tex_px = gen_tex_torch(32, 64);
    rc_palette_add(pal, tex_px, 32, 64);

    m.floor_color = (u32)0xFF304020;
    m.ceil_color  = (u32)0xFF87CEEB;

    // Grass floor everywhere
    while (y < MAP_H)
    {
        x = 0;
        while (x < MAP_W)
        {
            t.flags     = RC_TILE_EMPTY;
            t.tex_wall  = 0;
            t.tex_floor = 2;
            t.tex_ceil  = 0;
            t.tint      = 0;
            rc_map_set(m, x, y, t);
            x++;
        };
        y++;
    };

    // Border: stone
    border_walls(m, 1, 0);

    // Inner octagonal ring of pillars — simulated via blocked cells
    // Four short walls at diagonal corners
    i32 wc = 4;
    while (wc < 7)
    {
        rc_map_set_solid(m, wc, 4,       1, 0);
        rc_map_set_solid(m, 4,  wc,      1, 0);
        rc_map_set_solid(m, MAP_W-1-wc, 4,       1, 0);
        rc_map_set_solid(m, MAP_W-5,    wc,      1, 0);
        rc_map_set_solid(m, wc,         MAP_H-5, 1, 0);
        rc_map_set_solid(m, 4,          MAP_H-1-wc, 1, 0);
        rc_map_set_solid(m, MAP_W-1-wc, MAP_H-5, 1, 0);
        rc_map_set_solid(m, MAP_W-5,    MAP_H-1-wc, 1, 0);
        wc++;
    };

    rc_player_init(p, 12.0, 12.0, 0.78);  // start centre, face NE
    rc_camera_init(cam, 70.0, g_img_w, g_img_h, 22.0);

    sky.color_top     = (u32)0xFF4488DD;
    sky.color_horizon = (u32)0xFFAADDFF;

    *sprite_count = 0;

    // Pillar ring (tex 3)
    float[8] px_ring = [8.0, 12.0, 16.0, 19.5, 16.0, 12.0, 8.0, 4.5];
    float[8] py_ring = [4.5,  4.5,  4.5,  8.0, 19.5, 19.5, 19.5, 12.0];
    i32 si;
    while (si < 8)
    {
        sprites[*sprite_count].world_x = px_ring[si];
        sprites[*sprite_count].world_y = py_ring[si];
        sprites[*sprite_count].tex_idx = 3;
        sprites[*sprite_count].scale   = 1.2;
        sprites[*sprite_count].tint    = 0;
        (*sprite_count)++;
        si++;
    };

    // Torch ring (tex 4) — between pillars
    float[8] tx_ring = [10.0, 14.0, 18.0, 18.0, 14.0, 10.0,  6.0,  6.0];
    float[8] ty_ring = [ 4.5,  4.5,  6.5, 17.5, 19.5, 19.5, 17.5,  6.5];
    si = 0;
    while (si < 8)
    {
        sprites[*sprite_count].world_x = tx_ring[si];
        sprites[*sprite_count].world_y = ty_ring[si];
        sprites[*sprite_count].tex_idx = 4;
        sprites[*sprite_count].scale   = 0.5;
        sprites[*sprite_count].tint    = (u32)0x50FF6600;
        (*sprite_count)++;
        si++;
    };
};

// ============================================================================
// SCENE LIFECYCLE HELPERS
// ============================================================================

def scene_free_palette(RCTexturePalette* pal) -> void
{
    rc_palette_free(pal);
    rc_palette_init(pal, 16);
};

// ============================================================================
// MAIN
// ============================================================================

def main() -> int
{
    // ---- Pixel buffer ----
    size_t buf_bytes;
    u32*   pixels;
    buf_bytes = (size_t)(g_img_w * g_img_h * (i32)(sizeof(u32) / 8));
    pixels    = (u32*)fmalloc(buf_bytes);
    memset((void*)pixels, 0, buf_bytes);

    // ---- Window and GL context ----
    Window win("Flux Raycaster - WASD/Arrows move  1/2/3 change scene  ESC quit\0",
               g_img_w, g_img_h, CW_USEDEFAULT, CW_USEDEFAULT);
    SetForegroundWindow(win.handle);

    GLContext gl(win.device_context);
    gl.load_extensions();

    // ---- Render texture ----
    int tex_id;
    tex_id = 0;
    glGenTextures(1, @tex_id);
    glBindTexture(GL_TEXTURE_2D, tex_id);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA,
                 g_img_w, g_img_h, 0,
                 0x80E1, GL_UNSIGNED_BYTE, (void*)pixels);

    // ---- Scene data ----
    RCMap             map;
    RCPlayer          player;
    RCCamera          cam;
    RCTexturePalette  palette;
    RCSky             sky;
    RCSprite[SPRITE_CAP] sprites;
    i32               sprite_count;
    RCScene           scene;

    rc_map_init(@map, MAP_W, MAP_H);
    rc_palette_init(@palette, 16);
    sprite_count = 0;

    build_scene_castle(@map, @player, @cam, @palette, @sprites[0], @sprite_count, @sky);
    rc_scene_init(@scene, @map, @player, @cam, @palette, @sky);
    rc_scene_set_sprites(@scene, @sprites[0], sprite_count);
    scene.passes = RC_PASS_ALL;

    i32 current_scene = 1;

    // ---- Input state ----
    bool key_w_prev, key_s_prev, key_a_prev, key_d_prev;
    bool key_left_prev, key_right_prev;
    bool key1_prev, key2_prev, key3_prev;
    bool key_w_now, key_s_now, key_a_now, key_d_now;
    bool key_left_now, key_right_now;
    bool key1_now, key2_now, key3_now;

    key_w_prev = false;  key_s_prev = false;
    key_a_prev = false;  key_d_prev = false;
    key_left_prev = false; key_right_prev = false;
    key1_prev = false; key2_prev = false; key3_prev = false;

    // ---- Render thread state ----
    Thread render_thread;
    bool   thread_active;
    thread_active = false;

    // ---- Frame loop vars ----
    RECT    client_rect;
    int     cur_w, cur_h;
    Matrix4 ortho;
    i32     new_scene;
    bool    need_resize;
    size_t  new_buf_bytes;

    // Kick the first frame
    g_work.scene  = @scene;
    g_work.pixels = pixels;
    store32(@g_work.done, 0);
    thread_create(@rc_worker, (void*)0, @render_thread);
    thread_active = true;

    float forward, strafe, turn;

    while (win.process_messages())
    {
        if ((GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0) { PostQuitMessage(0); };

        // ---- Keyboard input ----
        key_w_now     = (GetAsyncKeyState(0x57) & 0x8000) != 0;  // W
        key_s_now     = (GetAsyncKeyState(0x53) & 0x8000) != 0;  // S
        key_a_now     = (GetAsyncKeyState(0x41) & 0x8000) != 0;  // A
        key_d_now     = (GetAsyncKeyState(0x44) & 0x8000) != 0;  // D
        key_left_now  = (GetAsyncKeyState(VK_LEFT)  & 0x8000) != 0;
        key_right_now = (GetAsyncKeyState(VK_RIGHT) & 0x8000) != 0;
        key1_now      = (GetAsyncKeyState(0x31) & 0x8000) != 0;
        key2_now      = (GetAsyncKeyState(0x32) & 0x8000) != 0;
        key3_now      = (GetAsyncKeyState(0x33) & 0x8000) != 0;

        // Movement — only applied when no render is in flight (next frame start)
        forward = 0.0;
        strafe  = 0.0;
        turn    = 0.0;

        if (key_w_now)     { forward  =  player.move_speed; };
        if (key_s_now)     { forward  = -player.move_speed; };
        if (key_a_now)     { strafe   = -player.move_speed; };
        if (key_d_now)     { strafe   =  player.move_speed; };
        if (key_left_now)  { turn     = -player.turn_speed; };
        if (key_right_now) { turn     =  player.turn_speed; };

        if (forward != 0.0 | strafe != 0.0) { rc_player_move(@player, @map, forward, strafe); };
        if (turn    != 0.0)                  { rc_player_turn(@player, turn); };

        key_w_prev     = key_w_now;
        key_s_prev     = key_s_now;
        key_a_prev     = key_a_now;
        key_d_prev     = key_d_now;
        key_left_prev  = key_left_now;
        key_right_prev = key_right_now;

        // ---- Scene switch (on rising edge) ----
        new_scene = 0;
        if (key1_now & !key1_prev) { new_scene = 1; };
        if (key2_now & !key2_prev) { new_scene = 2; };
        if (key3_now & !key3_prev) { new_scene = 3; };

        key1_prev = key1_now;
        key2_prev = key2_now;
        key3_prev = key3_now;

        if (new_scene != 0 & new_scene != current_scene)
        {
            // Wait for any in-flight render to complete
            if (thread_active)
            {
                thread_join(@render_thread);
                thread_active = false;
            };

            // Tear down old scene resources
            rc_map_free(@map);
            scene_free_palette(@palette);
            sprite_count = 0;

            // Re-init map
            rc_map_init(@map, MAP_W, MAP_H);

            switch (new_scene)
            {
                case (1)
                {
                    build_scene_castle(@map, @player, @cam, @palette, @sprites[0], @sprite_count, @sky);
                }
                case (2)
                {
                    build_scene_neon(@map, @player, @cam, @palette, @sprites[0], @sprite_count, @sky);
                }
                case (3)
                {
                    build_scene_arena(@map, @player, @cam, @palette, @sprites[0], @sprite_count, @sky);
                }
                default
                {
                    build_scene_castle(@map, @player, @cam, @palette, @sprites[0], @sprite_count, @sky);
                };
            };

            rc_scene_init(@scene, @map, @player, @cam, @palette, @sky);
            rc_scene_set_sprites(@scene, @sprites[0], sprite_count);
            scene.passes = RC_PASS_ALL;

            current_scene = new_scene;

            // Clear the pixel buffer so there's no stale image flash
            memset((void*)pixels, 0, buf_bytes);
            glBindTexture(GL_TEXTURE_2D, tex_id);
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, g_img_w, g_img_h,
                            0x80E1, GL_UNSIGNED_BYTE, (void*)pixels);
        };

        // ---- Window resize detection ----
        GetClientRect(win.handle, @client_rect);
        cur_w = client_rect.right  - client_rect.left;
        cur_h = client_rect.bottom - client_rect.top;
        if (cur_h == 0) { cur_h = 1; };

        need_resize = (cur_w != g_img_w) | (cur_h != g_img_h);
        if (need_resize)
        {
            if (thread_active)
            {
                thread_join(@render_thread);
                thread_active = false;
            };

            ffree((u64)pixels);
            g_img_w       = (i32)cur_w;
            g_img_h       = (i32)cur_h;
            new_buf_bytes = (size_t)(g_img_w * g_img_h * (i32)(sizeof(u32) / 8));
            buf_bytes     = new_buf_bytes;
            pixels        = (u32*)fmalloc(buf_bytes);
            memset((void*)pixels, 0, buf_bytes);

            // Rebuild camera for new aspect ratio
            cam.screen_w = g_img_w;
            cam.screen_h = g_img_h;
            cam.half_h   = (float)g_img_h * 0.5;
            cam.proj_dist = ((float)g_img_w * 0.5) / tan(cam.fov_h * 0.5);

            glDeleteTextures(1, @tex_id);
            glGenTextures(1, @tex_id);
            glBindTexture(GL_TEXTURE_2D, tex_id);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA,
                         g_img_w, g_img_h, 0,
                         0x80E1, GL_UNSIGNED_BYTE, (void*)pixels);
        };

        // ---- Check if render thread finished; if so, upload + re-dispatch ----
        if (thread_active)
        {
            if (load32(@g_work.done) != 0)
            {
                // Frame done — upload to GPU
                glBindTexture(GL_TEXTURE_2D, tex_id);
                glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, g_img_w, g_img_h,
                                0x80E1, GL_UNSIGNED_BYTE, (void*)pixels);
                thread_join(@render_thread);
                thread_active = false;
            };
        };

        if (!thread_active)
        {
            // Kick next frame
            g_work.scene  = @scene;
            g_work.pixels = pixels;
            store32(@g_work.done, 0);
            thread_create(@rc_worker, (void*)0, @render_thread);
            thread_active = true;
        };

        // ---- Blit texture to screen ----
        glViewport(0, 0, cur_w, cur_h);
        gl.set_clear_color(0.0, 0.0, 0.0, 1.0);
        gl.clear();

        glMatrixMode(GL_PROJECTION);
        glLoadIdentity();
        mat4_ortho(0.0, 1.0, 0.0, 1.0, -1.0, 1.0, @ortho);
        glLoadMatrixf(@ortho.m[0]);

        glMatrixMode(GL_MODELVIEW);
        glLoadIdentity();

        glEnable(GL_TEXTURE_2D);
        glBindTexture(GL_TEXTURE_2D, tex_id);
        glColor3f(1.0, 1.0, 1.0);

        glBegin(GL_QUADS);
            glTexCoord2f(0.0, 1.0);  glVertex2f(0.0, 0.0);
            glTexCoord2f(1.0, 1.0);  glVertex2f(1.0, 0.0);
            glTexCoord2f(1.0, 0.0);  glVertex2f(1.0, 1.0);
            glTexCoord2f(0.0, 0.0);  glVertex2f(0.0, 1.0);
        glEnd();

        glDisable(GL_TEXTURE_2D);

        gl.present();
    };

    // ---- Shutdown ----
    if (thread_active)
    {
        thread_join(@render_thread);
    };

    rc_map_free(@map);
    rc_palette_free(@palette);
    ffree((u64)pixels);
    gl.__exit();
    win.__exit();

    return 0;
};
