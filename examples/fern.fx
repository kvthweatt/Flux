#import "standard.fx", "math.fx", "windows.fx", "opengl.fx", "threading.fx";

using standard::io::console,
      standard::system::windows,
      standard::math,
      standard::atomic,
      standard::threading;

// ============================================================================
// Barnsley Fern - Infinite IFS Fractal - OpenGL Viewer
// Discovered by Michael Barnsley (1988)
//
// Four affine transforms chosen by weighted probability each iteration:
//
//   f1 (p=0.01): stem
//     x' =  0.00*x + 0.00*y + 0.00
//     y' =  0.00*x + 0.16*y + 0.00
//
//   f2 (p=0.85): successive leaflets (main body)
//     x' =  0.85*x + 0.04*y + 0.00
//     y' = -0.04*x + 0.85*y + 1.60
//
//   f3 (p=0.07): largest left leaflet
//     x' =  0.20*x - 0.26*y + 0.00
//     y' =  0.23*x + 0.22*y + 1.60
//
//   f4 (p=0.07): largest right leaflet
//     x' = -0.15*x + 0.28*y + 0.00
//     y' =  0.26*x + 0.24*y + 0.44
//
// "Infinite" because we iterate forever - each new point refines the fern
// without bound.  The pixel buffer accumulates hit counts and is renormalized
// each frame for a smooth density render.
//
// Controls:
//   W / S        = zoom in / out
//   A / D        = pan left / right
//   Up / Down    = pan up / down
//   R            = reset view
//   +/-          = more / fewer iterations per frame
// ============================================================================

const int WIN_W                 = 900,
          WIN_H                 = 900,
          MAX_THREADS           = 64,
          BASE_ITERS_PER_THREAD = 200000;

extern def !! GetTickCount() -> DWORD;

// ============================================================================
// Simple xorshift64 PRNG - one per thread to avoid contention
// ============================================================================

def xorshift64(ulong* state) -> ulong
{
    ulong x;
    x = *state;
    x = x ^^ (x << 13);
    x = x ^^ (x >> 7);
    x = x ^^ (x << 17);
    *state = x;
    return x;
};

def rand_double(ulong* state) -> double
{
    ulong r = xorshift64(state);
    return (double)(r >> 11) / 9007199254740992.0;
};

// ============================================================================
// IFS transform selection and application
//
// Cumulative probability thresholds:
//   f1: [0.00, 0.01)
//   f2: [0.01, 0.86)
//   f3: [0.86, 0.93)
//   f4: [0.93, 1.00)
// ============================================================================

def apply_ifs(double x, double y, double r, double* nx, double* ny) -> void
{
    if (r < 0.01)
    {
        *nx = 0.0;
        *ny = 0.16 * y;
    }
    elif (r < 0.86)
    {
        *nx =  0.85 * x + 0.04 * y;
        *ny = -0.04 * x + 0.85 * y + 1.60;
    }
    elif (r < 0.93)
    {
        *nx =  0.20 * x - 0.26 * y;
        *ny =  0.23 * x + 0.22 * y + 1.60;
    }
    else
    {
        *nx = -0.15 * x + 0.28 * y;
        *ny =  0.26 * x + 0.24 * y + 0.44;
    };
};

// ============================================================================
// Shared hit-count buffer + pixel output buffer
// ============================================================================

heap int*   g_hits   = (int*)0;
heap float* g_pixels = (float*)0;

// ============================================================================
// Work descriptor per thread
// ============================================================================

struct WorkSlice
{
    int    iters;
    double cx, cy,
           zoom;
    ulong  rng_seed;
};

WorkSlice[64] g_slices;

// ============================================================================
// Worker thread
// ============================================================================

def worker(void* arg) -> void*
{
    WorkSlice* sl = (WorkSlice*)arg;
    ulong rng = sl.rng_seed;

    double x, y, nx, ny, r;
    int px, py, idx;

    x = 0.0;
    y = 0.0;

    // Burn off transient
    for (int warm = 0; warm < 20; warm++)
    {
        r = rand_double(@rng);
        apply_ifs(x, y, r, @nx, @ny);
        x = nx;
        y = ny;
    };

    double world_left, world_bottom;
    world_left   = sl.cx - sl.zoom * (double)WIN_W * 0.5;
    world_bottom = sl.cy - sl.zoom * (double)WIN_H * 0.5;

    int i = 0;
    while (i < sl.iters)
    {
        r = rand_double(@rng);
        apply_ifs(x, y, r, @nx, @ny);
        x = nx;
        y = ny;

        px = (int)((x - world_left)   / sl.zoom);
        py = WIN_H - 1 - (int)((y - world_bottom) / sl.zoom);

        if (px >= 0 & px < WIN_W & py >= 0 & py < WIN_H)
        {
            idx = py * WIN_W + px;
            fetch_add32(@g_hits[idx], 1);
        };

        i++;
    };

    return (void*)0;
};

// ============================================================================
// Density -> colour
// Log-density: t = log(1 + hits) / log(1 + max_hits)
// Palette: black -> deep green -> bright green -> yellow-green -> white tip
// ============================================================================

def density_to_color(int hits, int max_hits, float* r, float* g, float* b) -> void
{
    if (hits == 0 | max_hits == 0)
    {
        *r = 0.0;
        *g = 0.0;
        *b = 0.0;
        return;
    };

    float t = (float)(log((double)hits + 1.0) / log((double)max_hits + 1.0));
    float s;

    if (t < 0.4)
    {
        s  = t / 0.4;
        *r = 0.0;
        *g = s * 0.45;
        *b = 0.0;
    }
    elif (t < 0.7)
    {
        s  = (t - 0.4) / 0.3;
        *r = s * 0.15;
        *g = 0.45 + s * 0.55;
        *b = s * 0.1;
    }
    elif (t < 0.9)
    {
        s  = (t - 0.7) / 0.2;
        *r = 0.15 + s * 0.75;
        *g = 1.0;
        *b = 0.1 - s * 0.1;
    }
    else
    {
        s  = (t - 0.9) / 0.1;
        *r = 0.9 + s * 0.1;
        *g = 1.0;
        *b = s * 1.0;
    };
};

// ============================================================================
// Main
// ============================================================================

def main() -> int
{
    SYSTEM_INFO_PARTIAL sysinfo;
    GetSystemInfo((void*)@sysinfo);
    int num_threads = (int)sysinfo.dwNumberOfProcessors;
    if (num_threads < 1)           { num_threads = 1; };
    if (num_threads > MAX_THREADS) { num_threads = MAX_THREADS; };

    print("Logical cores: \0");
    print(num_threads);
    print("\n\0");

    g_hits   = (int*)fmalloc((WIN_W * WIN_H * 4));
    g_pixels = (float*)fmalloc((WIN_W * WIN_H * 3 * 4));

    for (int zi = 0; zi < WIN_W * WIN_H; zi++) { g_hits[zi] = 0; };

    Window win("Barnsley Fern [IFS] - W/S: Zoom  A/D/Up/Down: Pan  R: Reset  +/-: Density\0", 100, 100, WIN_W, WIN_H);
    GLContext gl(win.device_context);

    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    glDisable(GL_DEPTH_TEST);

    glEnable(GL_TEXTURE_2D);
    i32 tex_id;
    glGenTextures(1, @tex_id);
    glBindTexture(GL_TEXTURE_2D, tex_id);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

    double cx, cy, zoom;
    cx   =  0.0;
    cy   =  5.0;
    zoom =  10.0 / (double)WIN_H;

    float zoom_speed, pan_speed, dt;
    zoom_speed = 1.5;
    pan_speed  = 0.6;

    int iters_per_thread = BASE_ITERS_PER_THREAD;

    DWORD t_now, t_last;
    t_last = GetTickCount();

    WORD w_state, s_state, a_state, d_state,
         up_state, dn_state,
         r_state, r_prev,
         plus_state, plus_prev,
         minus_state, minus_prev;

    r_prev     = 0;
    plus_prev  = 0;
    minus_prev = 0;

    Thread[64] threads;

    ulong base_seed = (ulong)GetTickCount();

    while (win.process_messages())
    {
        t_now  = GetTickCount();
        dt     = (float)(t_now - t_last) / 1000.0;
        t_last = t_now;
        if (dt > 0.1) { dt = 0.1; };

        w_state     = GetAsyncKeyState(VK_W);
        s_state     = GetAsyncKeyState(VK_S);
        a_state     = GetAsyncKeyState(VK_A);
        d_state     = GetAsyncKeyState(VK_D);
        up_state    = GetAsyncKeyState(VK_UP);
        dn_state    = GetAsyncKeyState(VK_DOWN);
        r_state     = GetAsyncKeyState(VK_R);
        plus_state  = GetAsyncKeyState(VK_OEM_PLUS);
        minus_state = GetAsyncKeyState(VK_OEM_MINUS);

        bool view_changed;
        view_changed = false;

        if ((w_state `& 0x8000) != 0)
        {
            zoom = zoom * (1.0 - (double)zoom_speed * (double)dt);
            if (zoom < 0.000000001) { zoom = 0.000000001; };
            view_changed = true;
        };

        if ((s_state `& 0x8000) != 0)
        {
            zoom = zoom * (1.0 + (double)zoom_speed * (double)dt);
            view_changed = true;
        };

        if ((a_state `& 0x8000) != 0)
        {
            cx = cx - zoom * (double)WIN_W * (double)pan_speed * (double)dt;
            view_changed = true;
        };

        if ((d_state `& 0x8000) != 0)
        {
            cx = cx + zoom * (double)WIN_W * (double)pan_speed * (double)dt;
            view_changed = true;
        };

        if ((up_state `& 0x8000) != 0)
        {
            cy = cy + zoom * (double)WIN_H * (double)pan_speed * (double)dt;
            view_changed = true;
        };

        if ((dn_state `& 0x8000) != 0)
        {
            cy = cy - zoom * (double)WIN_H * (double)pan_speed * (double)dt;
            view_changed = true;
        };

        if (((r_state `& 0x8000) != 0) `& ((r_prev `& 0x8000) == 0))
        {
            cx   =  0.0;
            cy   =  5.0;
            zoom =  10.0 / (double)WIN_H;
            view_changed = true;
        };
        r_prev = r_state;

        if (((plus_state `& 0x8000) != 0) `& ((plus_prev `& 0x8000) == 0))
        {
            iters_per_thread = iters_per_thread + 100000;
            print("iters/thread: \0");
            print(iters_per_thread);
            print("\n\0");
        };
        plus_prev = plus_state;

        if (((minus_state `& 0x8000) != 0) `& ((minus_prev `& 0x8000) == 0))
        {
            iters_per_thread = iters_per_thread - 100000;
            if (iters_per_thread < 10000) { iters_per_thread = 10000; };
            print("iters/thread: \0");
            print(iters_per_thread);
            print("\n\0");
        };
        minus_prev = minus_state;

        if (view_changed)
        {
            for (int ci = 0; ci < WIN_W * WIN_H; ci++) { g_hits[ci] = 0; };
        };

        base_seed = base_seed ^^ (ulong)t_now;

        for (int t = 0; t < num_threads; t++)
        {
            g_slices[t].iters    = iters_per_thread;
            g_slices[t].cx       = cx;
            g_slices[t].cy       = cy;
            g_slices[t].zoom     = zoom;
            g_slices[t].rng_seed = base_seed ^^ ((ulong)t * 0x9E3779B97F4A7C15);
            thread_create(@worker, (void*)@g_slices[t], @threads[t]);
        };

        for (int t = 0; t < num_threads; t++)
        {
            thread_join(@threads[t]);
        };

        int max_hits = 0;
        for (int pi = 0; pi < WIN_W * WIN_H; pi++)
        {
            if (g_hits[pi] > max_hits) { max_hits = g_hits[pi]; };
        };

        float r, g, b;
        for (int pi = 0; pi < WIN_W * WIN_H; pi++)
        {
            density_to_color(g_hits[pi], max_hits, @r, @g, @b);
            g_pixels[pi * 3]     = r;
            g_pixels[pi * 3 + 1] = g;
            g_pixels[pi * 3 + 2] = b;
        };

        gl.set_clear_color(0.0, 0.0, 0.0, 1.0);
        gl.clear();

        glBindTexture(GL_TEXTURE_2D, tex_id);
        glTexImage2D(GL_TEXTURE_2D, 0, (i32)GL_RGB, WIN_W, WIN_H, 0,
                     (i32)GL_RGB, (i32)GL_FLOAT, (void*)g_pixels);

        glBegin(GL_QUADS);
        glTexCoord2f(0.0, 1.0); glVertex2f(-1.0, -1.0);
        glTexCoord2f(1.0, 1.0); glVertex2f( 1.0, -1.0);
        glTexCoord2f(1.0, 0.0); glVertex2f( 1.0,  1.0);
        glTexCoord2f(0.0, 0.0); glVertex2f(-1.0,  1.0);
        glEnd();

        gl.present();
    };

    if (g_hits   != 0) { ffree((u64)g_hits);   };
    if (g_pixels != 0) { ffree((u64)g_pixels); };

    glDeleteTextures(1, @tex_id);
    gl.__exit();
    win.__exit();

    return 0;
};
