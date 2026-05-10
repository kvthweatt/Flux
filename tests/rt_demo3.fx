// Author: Karac V. Thweatt
//
// rt_demo.fx - Raytracing Library Demo (Multithreaded)
//
// Renders a 3D scene using raytracing.fx progressively.
// One batch of tiles per frame — one tile per thread — so all cores
// stay saturated while the window remains live between batches.
//
// Controls:
//   1   - Classic scene (diffuse, metal, glass spheres)
//   2   - Metal showcase (gold, silver, copper + checkerboard grid)
//   3   - Emissive light sources scene
//   ESC - Quit
//

#import "standard.fx", "windows.fx", "opengl.fx", "threading.fx", "atomics.fx", "raytracing.fx";

using standard::system::windows;
using standard::math;
using standard::memory::allocators::stdheap;
using standard::threading;
using standard::atomic;
using raytracer;

extern def !!glPixelStorei(int, int) -> void;

#def GL_UNPACK_ROW_LENGTH 0x0CF2;

// ============================================================================
// CONSTANTS
// ============================================================================

global i32 g_img_w = 800,
           g_img_h = 450;
#def SAMPLES     64;
#def DEPTH       8;
#def MAX_THREADS 64;
#def MAX_TILES   4096;   // 800x450 @ tile=32: ~375 tiles; 1080p: ~1020; safe upper bound

// Shared work-queue globals.
// g_total_tiles and the slice array are written once (main thread) before
// any worker launches, so no synchronization is needed for those reads.
// g_next_tile is incremented atomically by each worker to claim a tile.
global i32          g_total_tiles = 0;
global volatile i32 g_next_tile   = 0;

// ============================================================================
// WORK SLICE — one per tile, pre-filled before threads are spawned
// ============================================================================

struct RTWorkSlice
{
    RTScene*  scene;
    RTCamera* cam;
    u32*      pixels;
    i32       tile_x,
              tile_y,
              tw, th,
              img_w, img_h,
              samples, depth;
    u64       seed;
};

RTWorkSlice[4096] g_rt_slices;

// ============================================================================
// WORKER — each thread loops, atomically claiming tiles until all are done
// ============================================================================

def rt_worker(void* arg) -> void*
{
    PCG32 rng;
    i32   idx;

    for (;;)
    {
        // Atomically grab the next unclaimed tile index.
        // fetch_add32 returns the OLD value, so that is our exclusive index.
        idx = fetch_add32(@g_next_tile, 1);
        if (idx >= g_total_tiles) { break; };

        RTWorkSlice* sl = @g_rt_slices[idx];
        pcg32_seed(@rng, sl.seed, (u64)(sl.tile_x + 1));

        rt_render_tile(sl.scene, sl.cam, sl.pixels,
                       sl.tile_x, sl.tile_y,
                       sl.tw,     sl.th,
                       sl.img_w,  sl.img_h,
                       sl.samples, sl.depth,
                       @rng);
    };

    return (void*)0;
};

// ============================================================================
// SCENE BUILDERS
// ============================================================================

def build_scene_classic(RTScene* s, RTCamera* cam) -> void
{
    rt_scene_add_plane(s, vec3(0.0, 1.0, 0.0), 0.0,
                       mat_lambertian(vec3(0.5, 0.5, 0.5)));

    rt_scene_add_sphere(s, vec3(-1.2, 0.5, -2.5), 0.5,
                        mat_lambertian(vec3(0.8, 0.2, 0.1)));

    rt_scene_add_sphere(s, vec3(0.0, 0.5, -2.0), 0.5,
                        mat_dielectric(1.5));
    rt_scene_add_sphere(s, vec3(0.0, 0.5, -2.0), -0.45,
                        mat_dielectric(1.5));

    rt_scene_add_sphere(s, vec3(1.2, 0.5, -2.5), 0.5,
                        mat_metal(vec3(0.8, 0.6, 0.2), 0.05));

    rt_scene_add_sphere(s, vec3(-2.2, 0.25, -4.0), 0.25,
                        mat_lambertian(vec3(0.2, 0.7, 0.3)));
    rt_scene_add_sphere(s, vec3(-0.6, 0.25, -4.2), 0.25,
                        mat_lambertian(vec3(0.9, 0.8, 0.1)));
    rt_scene_add_sphere(s, vec3( 0.8, 0.25, -4.0), 0.25,
                        mat_metal(vec3(0.7, 0.7, 0.9), 0.3));
    rt_scene_add_sphere(s, vec3( 2.1, 0.25, -3.8), 0.25,
                        mat_lambertian(vec3(0.3, 0.3, 0.9)));
    rt_scene_add_sphere(s, vec3(-1.5, 0.25, -5.5), 0.25,
                        mat_lambertian(vec3(0.9, 0.4, 0.7)));
    rt_scene_add_sphere(s, vec3( 1.5, 0.25, -5.5), 0.25,
                        mat_metal(vec3(0.9, 0.5, 0.1), 0.15));

    rt_scene_add_sphere(s, vec3(0.0, 1.0, -7.0), 1.0,
                        mat_lambertian(vec3(0.4, 0.4, 0.8)));

    rt_camera_init(cam,
                   vec3(0.0, 1.2, 1.5),
                   vec3(0.0, 0.4, -2.0),
                   vec3(0.0, 1.0, 0.0),
                   50.0,
                   (float)g_img_w / (float)g_img_h,
                   0.04,
                   3.6);
};

def build_scene_metals(RTScene* s, RTCamera* cam) -> void
{
    i32   gx, gz;
    float fx, fz;

    rt_scene_add_plane(s, vec3(0.0, 1.0, 0.0), 0.0,
                       mat_lambertian(vec3(0.6, 0.55, 0.5)));

    rt_scene_add_sphere(s, vec3(-2.0, 0.7, -3.0), 0.7,
                        mat_metal(vec3(1.0, 0.78, 0.34), 0.0));
    rt_scene_add_sphere(s, vec3(0.0, 0.7, -3.5), 0.7,
                        mat_metal(vec3(0.9, 0.9, 0.95), 0.4));
    rt_scene_add_sphere(s, vec3(2.0, 0.7, -3.0), 0.7,
                        mat_metal(vec3(0.95, 0.64, 0.54), 0.15));

    rt_scene_add_sphere(s, vec3(-1.0, 0.3, -1.8), 0.3,
                        mat_dielectric(1.5));
    rt_scene_add_sphere(s, vec3(-1.0, 0.3, -1.8), -0.27,
                        mat_dielectric(1.5));
    rt_scene_add_sphere(s, vec3( 1.0, 0.3, -1.8), 0.3,
                        mat_dielectric(1.8));

    gx = -4;
    while (gx <= 4)
    {
        gz = -8;
        while (gz <= -1)
        {
            fx = (float)gx * 0.9;
            fz = (float)gz * 0.9;
            if ((gx + gz) & 1)
            {
                rt_scene_add_sphere(s, vec3(fx, 0.12, fz), 0.12,
                                    mat_metal(vec3(0.8, 0.8, 0.85), 0.05));
            }
            else
            {
                rt_scene_add_sphere(s, vec3(fx, 0.12, fz), 0.12,
                                    mat_lambertian(vec3(0.2, 0.2, 0.25)));
            };
            gz++;
        };
        gx++;
    };

    rt_camera_init(cam,
                   vec3(0.0, 2.0, 2.5),
                   vec3(0.0, 0.5, -2.5),
                   vec3(0.0, 1.0, 0.0),
                   55.0,
                   (float)g_img_w / (float)g_img_h,
                   0.05,
                   5.0);
};

def build_scene_lights(RTScene* s, RTCamera* cam) -> void
{
    rt_scene_add_plane(s, vec3(0.0, 1.0, 0.0), 0.0,
                       mat_lambertian(vec3(0.08, 0.08, 0.08)));

    rt_scene_add_sphere(s, vec3(0.0, 0.0, -8.0), 4.5,
                        mat_lambertian(vec3(0.15, 0.15, 0.2)));

    rt_scene_add_sphere(s, vec3(-1.8, 1.2, -3.0), 0.4,
                        mat_emissive(vec3(1.0, 0.4, 0.1), 8.0));
    rt_scene_add_sphere(s, vec3( 0.0, 1.5, -2.5), 0.4,
                        mat_emissive(vec3(0.4, 0.7, 1.0), 8.0));
    rt_scene_add_sphere(s, vec3( 1.8, 1.2, -3.0), 0.4,
                        mat_emissive(vec3(0.5, 1.0, 0.3), 8.0));

    rt_scene_add_sphere(s, vec3(0.0, 6.0, -2.5), 2.5,
                        mat_emissive(vec3(1.0, 0.95, 0.9), 1.5));

    rt_scene_add_sphere(s, vec3(-1.0, 0.35, -1.5), 0.35,
                        mat_lambertian(vec3(0.85, 0.85, 0.85)));
    rt_scene_add_sphere(s, vec3( 1.0, 0.35, -1.5), 0.35,
                        mat_metal(vec3(0.9, 0.9, 0.9), 0.02));
    rt_scene_add_sphere(s, vec3( 0.0, 0.35, -1.2), 0.35,
                        mat_dielectric(1.5));

    rt_scene_add_sphere(s, vec3(-2.4, 0.15, -2.5), 0.15,
                        mat_metal(vec3(0.95, 0.95, 0.95), 0.0));
    rt_scene_add_sphere(s, vec3( 0.0, 0.15, -2.0), 0.15,
                        mat_metal(vec3(0.95, 0.95, 0.95), 0.0));
    rt_scene_add_sphere(s, vec3( 2.4, 0.15, -2.5), 0.15,
                        mat_metal(vec3(0.95, 0.95, 0.95), 0.0));

    rt_camera_init(cam,
                   vec3(0.0, 1.5, 2.0),
                   vec3(0.0, 0.8, -2.0),
                   vec3(0.0, 1.0, 0.0),
                   60.0,
                   (float)g_img_w / (float)g_img_h,
                   0.0,
                   1.0);
};

// ============================================================================
// MAIN
// ============================================================================

def main() -> int
{
    // ---- Query core count ----
    SYSTEM_INFO_PARTIAL sysinfo;
    GetSystemInfo((void*)@sysinfo);
    i32 num_threads;
    num_threads = (i32)sysinfo.dwNumberOfProcessors;
    if (num_threads < 1)            { num_threads = 1; };
    if (num_threads > MAX_THREADS)  { num_threads = MAX_THREADS; };

    // ---- Pixel buffer ----
    size_t   buf_bytes;
    u32*     pixels;
    buf_bytes = (size_t)(g_img_w * g_img_h * (i32)(sizeof(u32) / 8));
    pixels    = (u32*)fmalloc(buf_bytes);

    // ---- Window and GL context ----
    Window win("Flux Raytracer - 1/2/3 change scene  ESC quit\0",
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

    // ---- Scene ----
    RTScene  scene;
    RTCamera cam;
    rt_scene_init(@scene, 64);
    build_scene_classic(@scene, @cam);
    bvh_build(@scene);

    // ---- Thread pool (fixed size: one thread per core, persistent) ----
    Thread[64] threads;

    // ---- Tile state ----
    bool rendering;
    rendering = true;

    // ---- Frame loop vars ----
    RECT    client_rect;
    int     cur_w, cur_h;
    Matrix4 ortho;
    bool    key1_prev, key2_prev, key3_prev,
            key1_now,  key2_now,  key3_now;
    i32     new_scene, current_scene;
    i32     t, tile_x, tile_y, tw, th;
    u64     tile_seed;
    bool    need_resize;
    size_t  new_buf_bytes;

    key1_prev     = false;
    key2_prev     = false;
    key3_prev     = false;
    current_scene = 1;
    new_scene     = 0;
    need_resize   = false;

    while (win.process_messages())
    {
        if ((GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0) { PostQuitMessage(0); };

        // ---- Scene switch ----
        key1_now = (GetAsyncKeyState(0x31) & 0x8000) != 0;
        key2_now = (GetAsyncKeyState(0x32) & 0x8000) != 0;
        key3_now = (GetAsyncKeyState(0x33) & 0x8000) != 0;

        new_scene = 0;
        if (key1_now & !key1_prev) { new_scene = 1; };
        if (key2_now & !key2_prev) { new_scene = 2; };
        if (key3_now & !key3_prev) { new_scene = 3; };

        key1_prev = key1_now;
        key2_prev = key2_now;
        key3_prev = key3_now;

        if (new_scene != 0 & new_scene != current_scene)
        {
            rt_scene_free(@scene);
            rt_scene_init(@scene, 64);

            switch (new_scene)
            {
                case (1) { build_scene_classic(@scene, @cam); }
                case (2) { build_scene_metals(@scene, @cam); }
                case (3) { build_scene_lights(@scene, @cam); }
                default  { build_scene_classic(@scene, @cam); };
            };

            bvh_build(@scene);
            current_scene = new_scene;

            memset((void*)pixels, 0, buf_bytes);
            glBindTexture(GL_TEXTURE_2D, tex_id);
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, g_img_w, g_img_h,
                            0x80E1, GL_UNSIGNED_BYTE, (void*)pixels);

            rendering = true;
        };

        // ---- Dispatch all tiles across all threads — work-queue style ----
        if (rendering)
        {
            // Build the full tile list upfront
            g_total_tiles = 0;
            tile_x = 0;
            tile_y = 0;
            while (tile_y < g_img_h)
            {
                tw = g_img_w - tile_x;
                th = g_img_h - tile_y;
                if (tw > RT_TILE_SIZE) { tw = RT_TILE_SIZE; };
                if (th > RT_TILE_SIZE) { th = RT_TILE_SIZE; };

                tile_seed = (u64)(tile_y * 65537 + tile_x * 131);

                t = g_total_tiles;
                g_rt_slices[t].scene   = @scene;
                g_rt_slices[t].cam     = @cam;
                g_rt_slices[t].pixels  = pixels;
                g_rt_slices[t].tile_x  = tile_x;
                g_rt_slices[t].tile_y  = tile_y;
                g_rt_slices[t].tw      = tw;
                g_rt_slices[t].th      = th;
                g_rt_slices[t].img_w   = g_img_w;
                g_rt_slices[t].img_h   = g_img_h;
                g_rt_slices[t].samples = SAMPLES;
                g_rt_slices[t].depth   = DEPTH;
                g_rt_slices[t].seed    = tile_seed;
                g_total_tiles++;

                tile_x += RT_TILE_SIZE;
                if (tile_x >= g_img_w)
                {
                    tile_x  = 0;
                    tile_y += RT_TILE_SIZE;
                };
            };

            // Reset the atomic counter so workers start from tile 0
            store32(@g_next_tile, 0);

            // Spawn exactly num_threads workers — each pulls tiles until none remain
            t = 0;
            while (t < num_threads)
            {
                thread_create(@rt_worker, (void*)0, @threads[t]);
                t++;
            };

            // Single join barrier — no intermediate stalls
            t = 0;
            while (t < num_threads)
            {
                thread_join(@threads[t]);
                t++;
            };

            // Upload the entire buffer in one shot
            glBindTexture(GL_TEXTURE_2D, tex_id);
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, g_img_w, g_img_h,
                            0x80E1, GL_UNSIGNED_BYTE, (void*)pixels);

            rendering = false;
        };

        // ---- Blit texture to screen ----
        GetClientRect(win.handle, @client_rect);
        cur_w = client_rect.right  - client_rect.left;
        cur_h = client_rect.bottom - client_rect.top;
        if (cur_h == 0) { cur_h = 1; };

        // ---- Detect window resize — reallocate buffer and restart render ----
        need_resize = (cur_w != g_img_w) | (cur_h != g_img_h);
        if (need_resize)
        {
            ffree((u64)pixels);
            g_img_w      = (i32)cur_w;
            g_img_h      = (i32)cur_h;
            new_buf_bytes = (size_t)(g_img_w * g_img_h * (i32)(sizeof(u32) / 8));
            buf_bytes    = new_buf_bytes;
            pixels       = (u32*)fmalloc(buf_bytes);
            memset((void*)pixels, 0, buf_bytes);

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

            rt_scene_free(@scene);
            rt_scene_init(@scene, 64);

            switch (current_scene)
            {
                case (1) { build_scene_classic(@scene, @cam); }
                case (2) { build_scene_metals(@scene, @cam); }
                case (3) { build_scene_lights(@scene, @cam); }
                default  { build_scene_classic(@scene, @cam); };
            };

            bvh_build(@scene);
            rendering = true;
        };

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

    rt_scene_free(@scene);
    ffree((u64)pixels);
    gl.__exit();
    win.__exit();

    return 0;
};
