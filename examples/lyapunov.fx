#import "standard.fx", "math.fx", "vectors.fx", "windows.fx", "opengl.fx", "threading.fx";

using standard::io::console,
      standard::system::windows,
      standard::math,
      standard::vectors,
      standard::atomic,
      standard::threading;

// ============================================================================
// Lyapunov Fractal - OpenGL Viewer
// W = zoom in, S = zoom out
// A/D = pan X,  Up/Down = pan Y
//
// Each pixel (a, b) represents two growth rates for the logistic map:
//   x_{n+1} = r_n * x_n * (1 - x_n)
// where r_n alternates between a and b according to a sequence string
// (e.g. "AABAB").  The Lyapunov exponent is:
//   lambda = (1/N) * sum( ln|r_n * (1 - 2*x_n)| )
//
// lambda < 0  =>  stable/periodic  (coloured blue)
// lambda > 0  =>  chaotic          (coloured red/yellow)
// lambda == 0 =>  boundary
//
// The classic "Zircon City" image uses sequence "BBBBBBAAAAAA" with
// a in [2,4], b in [2,4].
// ============================================================================

const int WIN_W       = 900,
          WIN_H       = 900,
          TILE_STILL  = 1,
          TILE_MOVING = 4,
          MAX_THREADS = 64,
          WARMUP_ITER = 200,   // Discard initial transient
          LYAP_ITER   = 1000,  // Iterations used to compute the exponent

          VK_W    = 0x57,
          VK_S    = 0x53,
          VK_A    = 0x41,
          VK_D    = 0x44,
          VK_UP   = 0x26,
          VK_DOWN = 0x28;

// ============================================================================
//  Sequence string - change this to get different Lyapunov images.
//  'A' uses the x-axis parameter (a), 'B' uses the y-axis parameter (b).
//  Classic sequences:
//    "AB"          - simplest, symmetric
//    "AABAB"       - Markus-Lyapunov original
//    "BBBBBBAAAAAA"- "Zircon City"
//    "ABABAB"      - hexagonal structures
// ============================================================================

const int SEQ_MAX = 64;

// Sequence stored as a global byte array; seq_len holds its length.
// Default: "AABAB"
byte[64] g_seq    = ['A', 'A', 'B', 'A', 'B',
                      0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
                      0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
                      0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
                      0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
                      0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
                      0,   0,   0,   0,   0,   0,   0,   0,   0];
int g_seq_len = 5;

// ============================================================================
//  Core computation: Lyapunov exponent for parameters (a, b)
//
//  Returns the exponent as a double.  The caller maps this to colour.
//  Returns 1e9 as a sentinel if x diverges (hits 0 or 1 exactly,
//  making the log term -inf).
// ============================================================================

def lyapunov(double a, double b, int warmup_iter, int lyap_iter) -> double
{
    double x, r, deriv, lsum;
    int n, seq_idx;

    x       = 0.5;   // Standard starting point
    lsum    = 0.0;
    seq_idx = 0;

    // Warm-up: let the orbit settle before measuring
    n = 0;
    while (n < WARMUP_ITER)
    {
        r = (g_seq[seq_idx] == 'A') ? a : b;
        seq_idx++;
        if (seq_idx >= g_seq_len) { seq_idx = 0; };
        x = r * x * (1.0 - x);
        n++;
    };

    // Accumulate ln|r * (1 - 2x)| = ln|df/dx|
    n = 0;
    while (n < LYAP_ITER)
    {
        r = (g_seq[seq_idx] == 'A') ? a : b;
        seq_idx++;
        if (seq_idx >= g_seq_len) { seq_idx = 0; };

        deriv = r * (1.0 - 2.0 * x);
        if (deriv < 0.0) { deriv = -deriv; };

        // x has collapsed to a fixed point - deriv underflows to exactly 0.0,
        // log(0) would be -inf, so treat as maximally stable and bail out.
        if (deriv == 0.0)
        {
            return -30.0;
        };

        lsum = lsum + log(deriv);
        x    = r * x * (1.0 - x);

        // Orbit has escaped [0,1] - divergent, colour as chaotic boundary
        if (x <= 0.0 | x >= 1.0)
        {
            return 1000000000.0;
        };

        n++;
    };

    return lsum / (double)LYAP_ITER;
};

// ============================================================================
//  Colour mapping
//
//  lambda < 0: stable  - deep blue (very stable) through cyan (near boundary)
//  lambda > 0: chaotic - yellow (mild chaos) through deep red (strong chaos)
//  lambda ~  0: boundary - white flash
//  Divergent sentinel: black
// ============================================================================

def lyap_to_color(double lambda, double* r, double* g, double* b) -> void
{
    double t, s;

    // Divergent / undefined
    if (lambda > 100000000.0)
    {
        *r = 0.0;
        *g = 0.0;
        *b = 0.0;
        return;
    };

    // Boundary flash
    if (lambda > -0.01 & lambda < 0.01)
    {
        *r = 1.0;
        *g = 1.0;
        *b = 1.0;
        return;
    };

    if (lambda < 0.0)
    {
        // Stable: blue (near 0) -> deep navy (very negative)
        // Clamp lambda to [-10, 0]
        t = -lambda;
        if (t > 10.0) { t = 10.0; };
        t = t / 10.0;   // 0 = near boundary, 1 = very stable

        // Near boundary: bright cyan; deeply stable: dark navy
        s  = t;
        *r = 0.0;
        *g = (1.0 - s) * 0.85;
        *b = 0.4 + (1.0 - s) * 0.6;
    }
    else
    {
        // Chaotic: gold/yellow (mild) -> deep red (strong)
        // Clamp lambda to [0, 3]
        t = lambda;
        if (t > 3.0) { t = 3.0; };
        t = t / 3.0;   // 0 = mild, 1 = strong chaos

        if (t < 0.5)
        {
            // Yellow -> orange
            s  = t / 0.5;
            *r = 1.0;
            *g = 1.0 - s * 0.55;
            *b = 0.0;
        }
        else
        {
            // Orange -> deep red
            s  = (t - 0.5) / 0.5;
            *r = 1.0 - s * 0.3;
            *g = 0.45 - s * 0.45;
            *b = 0.0;
        };
    };

    return;
};

extern def !! GetTickCount() -> DWORD;

// ============================================================================
//  Pixel buffer
// ============================================================================

heap float* g_pixels = (float*)0;
heap int*   g_iters  = (int*)0;   // Unused for Lyapunov but kept for structural parity
int g_cols = 0,
    g_rows = 0;

// ============================================================================
//  Work descriptor per thread
//  Pixel coords map directly: x-axis = parameter a, y-axis = parameter b.
// ============================================================================

struct WorkSlice
{
    int    row_start,
           row_end,
           cols, rows,
           tile,
           recolor_only,
           warmup_iter,    // transient discard count
           lyap_iter;      // accumulation count
    double x_min, x_max,   // range of parameter a
           y_min, y_max;   // range of parameter b
};

WorkSlice[64] g_slices;

// ============================================================================
//  Worker thread
// ============================================================================

def worker(void* arg) -> void*
{
    WorkSlice* sl = (WorkSlice*)arg;

    int row, col, idx;
    double a, b, lambda, r, gv, bv;

    row = sl.row_start;
    while (row < sl.row_end)
    {
        col = 0;
        while (col < sl.cols)
        {
            if (sl.recolor_only == 0)
            {
                // Map pixel to (a, b) parameter space
                a = sl.x_min + (sl.x_max - sl.x_min) * ((double)col + 0.5) / (double)sl.cols;
                b = sl.y_min + (sl.y_max - sl.y_min) * ((double)row + 0.5) / (double)sl.rows;

                lambda = lyapunov(a, b, sl.warmup_iter, sl.lyap_iter);

                // Reuse g_iters to cache the raw exponent bits for recolor passes
                // Store as raw IEEE 754 bits via pointer cast
                idx = row * sl.cols + col;
                ((double*)g_iters)[idx] = lambda;
            }
            else
            {
                idx    = row * sl.cols + col;
                lambda = ((double*)g_iters)[idx];
            };

            lyap_to_color(lambda, @r, @gv, @bv);

            idx = (row * sl.cols + col) * 3;
            g_pixels[idx]     = (float)r;
            g_pixels[idx + 1] = (float)gv;
            g_pixels[idx + 2] = (float)bv;

            col++;
        };
        row++;
    };

    return (void*)0;
};

def main() -> int
{
    print("Lyapunov fractal\n\0");
    print("Sequence: \0");
    int si;
    si = 0;
    while (si < g_seq_len) { print(g_seq[si]); si++; };
    print("\n\0");
    print("W/S: zoom  A/D: pan X  Up/Down: pan Y\n\0");

    SYSTEM_INFO_PARTIAL sysinfo;
    GetSystemInfo((void*)@sysinfo);
    int num_threads = (int)sysinfo.dwNumberOfProcessors;
    if (num_threads < 1)           { num_threads = 1; };
    if (num_threads > MAX_THREADS) { num_threads = MAX_THREADS; };

    Window win("Lyapunov Fractal [AABAB] - W/S: Zoom  A/D: Pan X  Up/Down: Pan Y\0", 100, 100, WIN_W, WIN_H);
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

    // ── View: parameter space a in [2,4], b in [2,4] ─────────────────────────
    // Both parameters must stay in (0, 4] for the logistic map to be bounded.
    double cx, cy, zoom, aspect, x_min, x_max, y_min, y_max, y_half;
    cx   = 3.0;
    cy   = 3.0;
    zoom = 2.0;   // half-width of the view window

    float zoom_speed, pan_speed, dt;
    int tile, cols, rows, cur_w, cur_h, rows_per_thread, t,
        warmup_iter, lyap_iter;
    bool moving, recolor_only, view_dirty;
    DWORD t_now, t_last;
    RECT client_rect;
    WORD w_state, s_state, a_state, d_state, up_state, dn_state;

    Thread[64] threads;

    view_dirty = true;
    zoom_speed = 0.3;
    pan_speed  = 0.05;
    t_last     = GetTickCount();

    while (win.process_messages())
    {
        t_now  = GetTickCount();
        dt     = (float)(t_now - t_last) / 1000.0;
        t_last = t_now;
        if (dt > 0.1) { dt = 0.1; };

        GetClientRect(win.handle, @client_rect);
        cur_w = client_rect.right  - client_rect.left;
        cur_h = client_rect.bottom - client_rect.top;
        if (cur_w < 1) { cur_w = 1; };
        if (cur_h < 1) { cur_h = 1; };

        glViewport(0, 0, cur_w, cur_h);

        w_state  = GetAsyncKeyState(VK_W);
        s_state  = GetAsyncKeyState(VK_S);
        a_state  = GetAsyncKeyState(VK_A);
        d_state  = GetAsyncKeyState(VK_D);
        up_state = GetAsyncKeyState(VK_UP);
        dn_state = GetAsyncKeyState(VK_DOWN);

        moving = ((w_state  `& 0x8000) != 0) |
                 ((s_state  `& 0x8000) != 0) |
                 ((a_state  `& 0x8000) != 0) |
                 ((d_state  `& 0x8000) != 0) |
                 ((up_state `& 0x8000) != 0) |
                 ((dn_state `& 0x8000) != 0);

        if (moving) { view_dirty = true; };

        tile = moving ? TILE_MOVING : TILE_STILL;

        // Reduce iteration budget while navigating for interactive frame rates.
        // Still: 200 warmup + 1000 accumulation.  Moving: 50 warmup + 200 accumulation.
        warmup_iter = moving ? 50   : 200;
        lyap_iter   = moving ? 200  : 1000;

        cols = cur_w / tile;
        rows = cur_h / tile;
        if (cols < 1) { cols = 1; };
        if (rows < 1) { rows = 1; };

        // Zoom in
        if ((w_state `& 0x8000) != 0)
        {
            zoom = zoom * (1.0 - (double)(zoom_speed * dt));
            if (zoom < 0.000001) { zoom = 0.000001; };
        };

        // Zoom out - clamp so we don't leave [0,4] bounds
        if ((s_state `& 0x8000) != 0)
        {
            zoom = zoom / (1.0 - (double)(zoom_speed * dt));
            if (zoom > 2.0) { zoom = 2.0; };
        };

        // Pan left
        if ((a_state `& 0x8000) != 0)
        {
            cx = cx - zoom * (double)(pan_speed * dt);
        };

        // Pan right
        if ((d_state `& 0x8000) != 0)
        {
            cx = cx + zoom * (double)(pan_speed * dt);
        };

        // Pan up
        if ((up_state `& 0x8000) != 0)
        {
            cy = cy - zoom * (double)(pan_speed * dt);
        };

        // Pan down
        if ((dn_state `& 0x8000) != 0)
        {
            cy = cy + zoom * (double)(pan_speed * dt);
        };

        // Clamp centre so view stays within logistic map bounds [0+eps, 4]
        if (cx - zoom < 0.01) { cx = 0.01 + zoom; };
        if (cx + zoom > 4.0)  { cx = 4.0  - zoom; };
        if (cy - zoom < 0.01) { cy = 0.01 + zoom; };
        if (cy + zoom > 4.0)  { cy = 4.0  - zoom; };

        // Reallocate buffer if tile grid changed
        // g_iters reused as double[cols*rows] cache for lambda values
        if (cols != g_cols | rows != g_rows)
        {
            if (g_pixels != 0) { ffree((u64)g_pixels); };
            if (g_iters  != 0) { ffree((u64)g_iters);  };
            g_pixels = (float*)fmalloc((cols * rows * 3 * 4));
            g_iters  = (int*)fmalloc((cols * rows * 8));   // 8 bytes per double
            g_cols   = cols;
            g_rows   = rows;
            recolor_only = false;
        }
        else
        {
            recolor_only = !view_dirty;
        };

        if (!moving) { view_dirty = false; };

        aspect = (double)cur_h / (double)cur_w;
        x_min  = cx - zoom;
        x_max  = cx + zoom;
        y_half = zoom * aspect;
        y_min  = cy - y_half;
        y_max  = cy + y_half;

        rows_per_thread = rows / num_threads;
        if (rows_per_thread < 1) { rows_per_thread = 1; };

        t = 0;
        while (t < num_threads)
        {
            g_slices[t].row_start    = t * rows_per_thread;
            g_slices[t].row_end      = (t == num_threads - 1)
                                       ? rows
                                       : (t + 1) * rows_per_thread;
            g_slices[t].cols         = cols;
            g_slices[t].rows         = rows;
            g_slices[t].tile         = tile;
            g_slices[t].recolor_only = recolor_only ? 1 : 0;
            g_slices[t].warmup_iter  = warmup_iter;
            g_slices[t].lyap_iter    = lyap_iter;
            g_slices[t].x_min        = x_min;
            g_slices[t].x_max        = x_max;
            g_slices[t].y_min        = y_min;
            g_slices[t].y_max        = y_max;

            thread_create(@worker, (void*)@g_slices[t], @threads[t]);
            t++;
        };

        t = 0;
        while (t < num_threads)
        {
            thread_join(@threads[t]);
            t++;
        };

        gl.set_clear_color(0.0, 0.0, 0.0, 1.0);
        gl.clear();

        glBindTexture(GL_TEXTURE_2D, tex_id);
        glTexImage2D(GL_TEXTURE_2D, 0, (i32)GL_RGB, cols, rows, 0,
                     (i32)GL_RGB, (i32)GL_FLOAT, (void*)g_pixels);

        glBegin(GL_QUADS);
        glTexCoord2f(0.0, 1.0); glVertex2f(-1.0, -1.0);
        glTexCoord2f(1.0, 1.0); glVertex2f( 1.0, -1.0);
        glTexCoord2f(1.0, 0.0); glVertex2f( 1.0,  1.0);
        glTexCoord2f(0.0, 0.0); glVertex2f(-1.0,  1.0);
        glEnd();

        gl.present();
    };

    if (g_pixels != 0) { ffree((u64)g_pixels); };
    if (g_iters  != 0) { ffree((u64)g_iters);  };

    glDeleteTextures(1, @tex_id);
    gl.__exit();
    win.__exit();

    return 0;
};
