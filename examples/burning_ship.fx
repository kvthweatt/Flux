#import "standard.fx", "math.fx", "vectors.fx", "windows.fx", "opengl.fx", "threading.fx", "decimal.fx";

using standard::io::console,
      standard::system::windows,
      standard::math,
      standard::vectors,
      standard::atomic,
      standard::threading,
      math::decimal;

// ============================================================================
// Burning Ship Fractal - OpenGL Viewer
// W = zoom in, S = zoom out
// A/D = pan X,  Up/Down = pan Y
//
// Iteration:  z_{n+1} = (|Re(z_n)| + i|Im(z_n)|)^2 + c
//
// Unlike the Mandelbrot set the absolute-value fold in the Burning Ship
// iteration is non-analytic, so perturbation theory does not apply cleanly.
// All pixels are rendered with full double precision (or Decimal for the
// pixel-coordinate computation at extreme zoom).
// ============================================================================

const int WIN_W        = 900,
          WIN_H        = 900,
          MAX_ITER     = 32768,
          TILE_STILL   = 1,
          TILE_MOVING  = 4,
          MAX_THREADS  = 64,

          VK_W    = 0x57,
          VK_S    = 0x53,
          VK_A    = 0x41,
          VK_D    = 0x44,
          VK_UP   = 0x26,
          VK_DOWN = 0x28;

// ============================================================================
//  Full double-precision Burning Ship iteration
//
//  z_{n+1} = (|x| + i|y|)^2 + c
//           = (x^2 - y^2 + cx) + i(2|x||y| + cy)
//
//  Note: the absolute values are applied to x and y *before* squaring,
//  which is equivalent to reflecting the orbit into the first quadrant
//  at every step.  This produces the characteristic ship / flame shape.
// ============================================================================

def burning_ship_double(double x0, double y0, int max_iter) -> int
{
    double x, y, xx, yy, xtemp;
    int iter;

    x    = 0.0;
    y    = 0.0;
    iter = 0;

    while (iter < max_iter)
    {
        xx = x * x;
        yy = y * y;
        if (xx + yy > 4.0) { return iter; };

        // Apply absolute value then iterate:
        //   x' = |x|^2 - |y|^2 + x0  (= x^2 - y^2 + x0, abs has no effect on squares)
        //   y' = 2*|x|*|y| + y0       (abs matters here - always non-negative product)
        if (x < 0.0) { x = -x; };
        if (y < 0.0) { y = -y; };

        xtemp = xx - yy + x0;
        y     = 2.0 * x * y + y0;
        x     = xtemp;
        iter++;
    };

    return iter;
};

// ============================================================================
//  Map iteration count to a fiery RGB colour
//  Palette: black -> deep red -> orange -> bright yellow -> white corona
// ============================================================================

def iter_to_color(int iter, int max_iter, double palette_offset, double* r, double* g, double* b) -> void
{
    double t, s;

    if (iter == max_iter)
    {
        // Inside the set - black
        *r = 0.0;
        *g = 0.0;
        *b = 0.0;
        return;
    };

    t = (double)(iter % 256) / 255.0 + palette_offset;
    t = t - (double)(int)t;

    // 5-stop fiery palette:
    // 0.00 - 0.15: black -> deep crimson
    // 0.15 - 0.35: deep crimson -> bright red
    // 0.35 - 0.55: bright red -> deep orange
    // 0.55 - 0.75: deep orange -> bright gold/yellow
    // 0.75 - 1.00: bright gold -> pale white corona -> fades to black
    if (t < 0.15)
    {
        s  = t / 0.15;
        *r = s * 0.6;
        *g = 0.0;
        *b = 0.0;
    }
    elif (t < 0.35)
    {
        s  = (t - 0.15) / 0.2;
        *r = 0.6 + s * 0.4;
        *g = s * 0.05;
        *b = 0.0;
    }
    elif (t < 0.55)
    {
        s  = (t - 0.35) / 0.2;
        *r = 1.0;
        *g = 0.05 + s * 0.55;
        *b = 0.0;
    }
    elif (t < 0.75)
    {
        s  = (t - 0.55) / 0.2;
        *r = 1.0;
        *g = 0.6 + s * 0.4;
        *b = s * 0.3;
    }
    else
    {
        // White corona fading back to black for seamless wrap
        s  = (t - 0.75) / 0.25;
        *r = 1.0 - s * 1.0;
        *g = 1.0 - s * 1.0;
        *b = 0.3 - s * 0.3;
    };

    return;
};

extern def !! GetTickCount() -> DWORD;

// ============================================================================
//  Pixel buffer
// ============================================================================

heap float* g_pixels = (float*)0;
heap int*   g_iters  = (int*)0;
int g_cols = 0,
    g_rows = 0;

// ============================================================================
//  Work descriptor per thread
// ============================================================================

struct WorkSlice
{
    int    row_start,
           row_end,
           cols, rows,
           dyn_max_iter,
           tile,
           recolor_only,
           need_decimal;
    Decimal x_min,
            y_min,
            x_range, y_range;
    double  x_min_d,
            y_min_d,
            x_range_d,
            y_range_d,
            palette_offset;
};

WorkSlice[64] g_slices;

// ============================================================================
//  Worker thread
// ============================================================================

def worker(void* arg) -> void*
{
    WorkSlice* sl = (WorkSlice*)arg;

    int row, col, iter, idx;
    double r, gv, b,
           fx_d, fy_d;

    singinit Decimal fx, fy,
                     col_d, row_d,
                     cols_d, rows_d,
                     half, tmp, tmp2;

    decimal_from_string(@half,   "0.5\0");
    decimal_from_i64(@cols_d, (i64)sl.cols);
    decimal_from_i64(@rows_d, (i64)sl.rows);

    row = sl.row_start;
    while (row < sl.row_end)
    {
        col = 0;
        while (col < sl.cols)
        {
            idx = row * sl.cols + col;

            if (sl.recolor_only == 0)
            {
                if (sl.need_decimal == 0)
                {
                    // Fast double path
                    fx_d = sl.x_min_d + sl.x_range_d * ((double)col + 0.5) / (double)sl.cols;
                    fy_d = sl.y_min_d + sl.y_range_d * ((double)row + 0.5) / (double)sl.rows;
                }
                else
                {
                    // High-precision Decimal pixel coordinate
                    decimal_from_i64(@col_d, (i64)col);
                    decimal_add(@tmp, @col_d, @half);
                    decimal_mul(@tmp2, @sl.x_range, @tmp);
                    decimal_div(@tmp, @tmp2, @cols_d);
                    decimal_add(@fx, @sl.x_min, @tmp);

                    decimal_from_i64(@row_d, (i64)row);
                    decimal_add(@tmp, @row_d, @half);
                    decimal_mul(@tmp2, @sl.y_range, @tmp);
                    decimal_div(@tmp, @tmp2, @rows_d);
                    decimal_add(@fy, @sl.y_min, @tmp);

                    fx_d = decimal_to_double(@fx);
                    fy_d = decimal_to_double(@fy);
                };

                // Always full double precision - no perturbation for Burning Ship
                iter = burning_ship_double(fx_d, fy_d, sl.dyn_max_iter);
                g_iters[idx] = iter;
            }
            else
            {
                iter = g_iters[idx];
            };

            iter_to_color(iter, sl.dyn_max_iter, sl.palette_offset, @r, @gv, @b);

            idx = idx * 3;
            g_pixels[idx]     = (float)r;
            g_pixels[idx + 1] = (float)gv;
            g_pixels[idx + 2] = (float)b;

            col++;
        };
        row++;
    };

    return (void*)0;
};

def main() -> int
{
    int precision = 32;
    decimal_set_precision(precision);

    SYSTEM_INFO_PARTIAL sysinfo;
    GetSystemInfo((void*)@sysinfo);
    int num_threads = (int)sysinfo.dwNumberOfProcessors;
    if (num_threads < 1)           { num_threads = 1; };
    if (num_threads > MAX_THREADS) { num_threads = MAX_THREADS; };

    print("Logical cores: \0");
    print(num_threads);
    print("\n\0");
    print("Decimal precision: \0"); print(precision); print(" digits\n\0");

    Window win("Burning Ship Fractal [Decimal 32] - W/S: Zoom  A/D: Pan X  Up/Down: Pan Y\0", 100, 100, WIN_W, WIN_H);
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

    // ── View parameters ──────────────────────────────────────────────────────
    // Centre on (-0.5, -0.5) which places the main ship body in view.
    // The fractal extends roughly x in [-2.5, 1.5], y in [-2.0, 0.5].
    Decimal cx, cy, zoom, half_zoom,
            x_min, y_min, x_range, y_range,
            tmp, tmp2, tmp3,
            zoom_delta, pan_delta,
            decimal_enter, decimal_exit;

    decimal_from_string(@decimal_enter, "0.00000000000001\0");   // 1e-14
    decimal_from_string(@decimal_exit,  "0.0000000000001\0");    // 1e-13

    // Default view: ship centred, zoom = 4 covers the full extent
    decimal_from_string(@cx,   "-0.5\0");
    decimal_from_string(@cy,   "-0.5\0");
    decimal_from_string(@zoom, "4\0");

    float zoom_speed, pan_speed, dt;
    double palette_time,
           palette_offset,
           x_min_d, y_min_d, x_range_d, y_range_d;
    int tile,
        dyn_max_iter,
        prev_dyn_max_iter,
        cols, rows,
        cur_w, cur_h,
        rows_per_thread, t;
    bool moving, recolor_only,
         ref_dirty,
         need_decimal, was_decimal;
    DWORD t_now,
          t_last;
    RECT client_rect;
    WORD w_state, s_state, a_state, d_state,
         up_state, dn_state;

    i32 zoom_exp, zoom_digits, depth;

    Thread[64] threads;

    ref_dirty = true;

    zoom_speed = 0.3;
    pan_speed  = 0.05;

    t_last = GetTickCount();

    while (win.process_messages())
    {
        t_now  = GetTickCount();
        dt     = (float)(t_now - t_last) / 1000.0;
        t_last = t_now;
        if (dt > 0.1) { dt = 0.1; };

        palette_time = palette_time + (double)dt * 0.10;
        if (palette_time >= 1.0) { palette_time = palette_time - 1.0; };
        palette_offset = palette_time;

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

        if (moving) { ref_dirty = true; };

        tile = moving ? TILE_MOVING : TILE_STILL;

        cols = cur_w / tile;
        rows = cur_h / tile;
        if (cols < 1) { cols = 1; };
        if (rows < 1) { rows = 1; };

        // Dynamic iteration budget scaled with zoom depth
        {
            zoom_exp    = zoom.exponent;
            zoom_digits = decimal_bigint_digit_count(@zoom.coefficient);
            depth       = -(zoom_exp + zoom_digits - 1);
            if (depth < 0)  { depth = 0;  };
            if (depth > 40) { depth = 40; };
            dyn_max_iter = 128 + depth * 200;
            if (dyn_max_iter > MAX_ITER) { dyn_max_iter = MAX_ITER; };
        };
        if (moving) { dyn_max_iter = dyn_max_iter >> 1; };

        if (dyn_max_iter != prev_dyn_max_iter)
        {
            ref_dirty = true;
            prev_dyn_max_iter = dyn_max_iter;
        };

        // Zoom in: zoom *= (1 - zoom_speed * dt)
        if ((w_state `& 0x8000) != 0)
        {
            decimal_from_string(@tmp, "1\0");
            decimal_from_i64(@tmp2, (i64)(zoom_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@zoom_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @zoom_delta);
            decimal_sub(@zoom, @zoom, @tmp);
            decimal_from_string(@tmp, "0.000000000000000000000000001\0");
            if (decimal_cmp(@zoom, @tmp) < 0)
            {
                decimal_copy(@zoom, @tmp);
            };
        };

        // Zoom out: zoom /= (1 - zoom_speed * dt)
        if ((s_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(zoom_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@zoom_delta, @tmp2, @tmp3);
            decimal_from_string(@tmp, "1\0");
            decimal_sub(@tmp, @tmp, @zoom_delta);
            decimal_div(@tmp2, @zoom, @tmp);
            decimal_copy(@zoom, @tmp2);
            decimal_from_string(@tmp, "8\0");
            if (decimal_cmp(@zoom, @tmp) > 0)
            {
                decimal_copy(@zoom, @tmp);
            };
        };

        // Pan left
        if ((a_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_sub(@cx, @cx, @tmp);
        };

        // Pan right
        if ((d_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_add(@cx, @cx, @tmp);
        };

        // Pan up
        if ((up_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_sub(@cy, @cy, @tmp);
        };

        // Pan down
        if ((dn_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_add(@cy, @cy, @tmp);
        };

        // Reallocate pixel buffer if tile count changed
        if (cols != g_cols | rows != g_rows)
        {
            if (g_pixels != 0) { ffree((u64)g_pixels); };
            if (g_iters  != 0) { ffree((u64)g_iters);  };
            g_pixels = (float*)fmalloc((cols * rows * 3 * 4));
            g_iters  = (int*)fmalloc((cols * rows * 4));
            g_cols   = cols;
            g_rows   = rows;
            recolor_only = false;
        }
        else
        {
            recolor_only = !moving & !ref_dirty;
        };

        // ── Compute view bounds in Decimal ───────────────────────────────────
        decimal_from_string(@tmp, "0.5\0");
        decimal_mul(@half_zoom, @zoom, @tmp);

        decimal_sub(@x_min, @cx, @half_zoom);

        decimal_from_i64(@tmp,  (i64)cur_h);
        decimal_from_i64(@tmp2, (i64)cur_w);
        decimal_mul(@tmp3,   @zoom, @tmp);
        decimal_div(@y_range, @tmp3, @tmp2);

        decimal_from_string(@tmp, "0.5\0");
        decimal_mul(@tmp2, @y_range, @tmp);
        decimal_sub(@y_min, @cy, @tmp2);

        decimal_copy(@x_range, @zoom);

        // ── Switch double / Decimal arithmetic with hysteresis ───────────────
        {
            was_decimal = need_decimal;
            if (!need_decimal)
            {
                if (decimal_cmp(@zoom, @decimal_enter) < 0)
                {
                    need_decimal = true;
                };
            }
            else
            {
                if (decimal_cmp(@zoom, @decimal_exit) > 0)
                {
                    need_decimal = false;
                };
            };
            if (need_decimal != was_decimal)
            {
                ref_dirty = true;
            };
        };

        if (ref_dirty & !moving) { ref_dirty = false; };

        // Pre-convert view bounds to double for the fast path
        x_min_d   = decimal_to_double(@x_min);
        y_min_d   = decimal_to_double(@y_min);
        x_range_d = decimal_to_double(@x_range);
        y_range_d = decimal_to_double(@y_range);

        // ── Partition rows across threads and launch ──────────────────────────
        rows_per_thread = rows / num_threads;
        if (rows_per_thread < 1) { rows_per_thread = 1; };

        t = 0;
        while (t < num_threads)
        {
            g_slices[t].row_start      = t * rows_per_thread;
            g_slices[t].row_end        = (t == num_threads - 1)
                                         ? rows
                                         : (t + 1) * rows_per_thread;
            g_slices[t].cols           = cols;
            g_slices[t].rows           = rows;
            g_slices[t].dyn_max_iter   = dyn_max_iter;
            g_slices[t].tile           = tile;
            g_slices[t].recolor_only   = recolor_only ? 1 : 0;
            g_slices[t].need_decimal   = need_decimal ? 1 : 0;
            decimal_copy(@g_slices[t].x_min,   @x_min);
            decimal_copy(@g_slices[t].y_min,   @y_min);
            decimal_copy(@g_slices[t].x_range, @x_range);
            decimal_copy(@g_slices[t].y_range, @y_range);
            g_slices[t].x_min_d        = x_min_d;
            g_slices[t].y_min_d        = y_min_d;
            g_slices[t].x_range_d      = x_range_d;
            g_slices[t].y_range_d      = y_range_d;
            g_slices[t].palette_offset = palette_offset;

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

    // ── Cleanup ───────────────────────────────────────────────────────────────
    if (g_pixels != 0) { ffree((u64)g_pixels); };
    if (g_iters  != 0) { ffree((u64)g_iters);  };

    glDeleteTextures(1, @tex_id);

    gl.__exit();
    win.__exit();

    return 0;
};
