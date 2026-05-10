#import "standard.fx", "math.fx", "vectors.fx", "windows.fx", "opengl.fx", "threading.fx", "decimal.fx";

using standard::io::console,
      standard::system::windows,
      standard::math,
      standard::vectors,
      standard::atomic,
      standard::threading,
      math::decimal;

// ============================================================================
// Mandelbrot Set - OpenGL Viewer
// W = zoom in, S = zoom out
// A/D = pan X,  Up/Down = pan Y
//
// Hybrid arbitrary-precision + perturbation theory renderer:
//   - cx, cy, zoom held as 32-digit Decimal - no precision loss at any depth
//   - One reference orbit computed in Decimal at the screen centre each frame,
//     stored as double pairs (sufficient once converted from the exact value)
//   - Every other pixel runs as a double delta dz from that orbit:
//       dz[n+1] = (2*Z[n] + dz[n])*dz[n] + dc
//     where dc = pixel_coord_double - ref_double is a tiny offset
//   - Glitched or orbit-exhausted pixels fall back to full double precision
//   - Perturbation disabled while moving (coarse grid + reduced iters makes
//     full precision fast enough, avoids large-dc glitch artifacts)
// ============================================================================

const int WIN_W        = 900,
          WIN_H        = 900,
          MAX_ITER     = 32768,  // Hard ceiling - scales dynamically with zoom depth
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
//  Full double-precision Mandelbrot fallback
//  Used during navigation and as glitch/exhaustion fallback during perturbation
// ============================================================================

def mandelbrot_double(double x0, double y0, int max_iter) -> int
{
    double x, y, xx, yy, xtemp, cx, cy, q;
    int iter;

    // Cardioid and period-2 bulb check
    cx = x0 - 0.25;
    cy = y0;
    q  = cx * cx + cy * cy;
    if (q * (q + cx) < cy * cy * 0.25) { return max_iter; };
    cx = x0 + 1.0;
    if (cx * cx + cy * cy < 0.0625) { return max_iter; };

    x    = 0.0;
    y    = 0.0;
    iter = 0;

    while (iter < max_iter)
    {
        xx = x * x;
        yy = y * y;
        if (xx + yy > 4.0) { return iter; };
        xtemp = xx - yy + x0;
        y     = 2.0 * x * y + y0;
        x     = xtemp;
        iter++;
    };

    return iter;
};

// ============================================================================
//  Fast double-precision reference orbit
//  Used when zoom >= 1e-15 where double is sufficient.
//  Identical structure to compute_reference_orbit but avoids all Decimal cost.
// ============================================================================

heap double* g_ref_zr = (double*)0,
             g_ref_zi = (double*)0;
int          g_ref_len = 0;

def compute_reference_orbit_double(double cx, double cy, int max_iter) -> void
{
    if ((u64)g_ref_zr != (u64)0) { ffree((u64)g_ref_zr); };
    if ((u64)g_ref_zi != (u64)0) { ffree((u64)g_ref_zi); };

    g_ref_zr  = (double*)fmalloc((size_t)(max_iter * 8));
    g_ref_zi  = (double*)fmalloc((size_t)(max_iter * 8));
    g_ref_len = 0;

    double zr, zi, zr2, zi2, ztemp;
    zr = 0.0;
    zi = 0.0;

    int n;
    n = 0;
    while (n < max_iter)
    {
        g_ref_zr[n] = zr;
        g_ref_zi[n] = zi;

        zr2 = zr * zr;
        zi2 = zi * zi;
        if (zr2 + zi2 > 4.0)
        {
            g_ref_len = n;
            return;
        };

        ztemp = zr2 - zi2 + cx;
        zi    = 2.0 * zr * zi + cy;
        zr    = ztemp;
        n++;
    };

    g_ref_len = max_iter;
    return;
};

// ============================================================================
//  Reference orbit - computed once per stationary frame at the screen centre
//  using full Decimal arithmetic, then stored as double pairs.
//  The conversion to double is exact enough for the delta recurrence since
//  dz is always a small offset and Z[n] only needs to be accurate to double.
// ============================================================================

def compute_reference_orbit(Decimal* cx, Decimal* cy, int max_iter) -> void
{
    if ((u64)g_ref_zr != (u64)0) { ffree((u64)g_ref_zr); };
    if ((u64)g_ref_zi != (u64)0) { ffree((u64)g_ref_zi); };

    g_ref_zr  = (double*)fmalloc((size_t)(max_iter * 8));
    g_ref_zi  = (double*)fmalloc((size_t)(max_iter * 8));
    g_ref_len = 0;

    Decimal zr, zi, zr2, zi2, ztemp, tmp, four;
    decimal_zero(@zr);
    decimal_zero(@zi);
    decimal_from_string(@four, "4\0");

    int n;
    n = 0;
    while (n < max_iter)
    {
        // Store Z[n] as double - precision sufficient for delta recurrence
        g_ref_zr[n] = decimal_to_double(@zr);
        g_ref_zi[n] = decimal_to_double(@zi);

        // Escape check in Decimal
        decimal_mul(@zr2, @zr, @zr);
        decimal_mul(@zi2, @zi, @zi);
        decimal_add(@tmp, @zr2, @zi2);
        if (decimal_cmp(@tmp, @four) > 0)
        {
            g_ref_len = n;
            return;
        };

        // ztemp = zr*zr - zi*zi + cx
        decimal_sub(@tmp, @zr2, @zi2);
        decimal_add(@ztemp, @tmp, cx);
        // zi = 2*zr*zi + cy
        decimal_mul(@tmp, @zr, @zi);
        decimal_add(@zi, @tmp, @tmp);
        decimal_add(@zi, @zi, cy);
        // zr = ztemp
        decimal_copy(@zr, @ztemp);

        n++;
    };

    g_ref_len = max_iter;
    return;
};

// ============================================================================
//  Perturbation iteration for one pixel
//
//  ref_cr/ci  = reference centre as double (converted from Decimal)
//  dcr/dci    = pixel offset from reference in double
//
//  Recurrence:  dz[n+1] = (2*Z[n] + dz[n])*dz[n] + dc
//
//  Loop order per iteration:
//    1. Glitch check |dz| >= |Z| -> fallback (skip at n=0 where Z=(0,0))
//    2. Escape test on Z[n] + dz[n] (reliable since |dz| < |Z|)
//    3. Advance dz
// ============================================================================

def mandelbrot_perturb(double ref_cr, double ref_ci, double dcr, double dci, int max_iter) -> int
{
    double dzr, dzi, dzr_new, dzi_new,
           zr, zi, zmod2, dzmod2, tr, ti;
    int n;

    dzr = 0.0;
    dzi = 0.0;
    n   = 0;

    while (n < g_ref_len)
    {
        zr = g_ref_zr[n];
        zi = g_ref_zi[n];

        // Glitch check: |dz| >= |Z| means the approximation has broken down.
        // Must check before the escape test - a large dz can produce a false
        // escape on the reconstructed value even for interior pixels.
        // Skip n==0 where Z[0]=(0,0) would always trigger.
        if (n > 0)
        {
            zmod2  = zr * zr + zi * zi;
            dzmod2 = dzr * dzr + dzi * dzi;
            if (dzmod2 >= zmod2)
            {
                return mandelbrot_double(ref_cr + dcr, ref_ci + dci, max_iter);
            };
        };

        // Escape test on reconstructed full value Z[n] + dz[n].
        // Only reached when |dz| < |Z|, so the reconstruction is reliable.
        tr = zr + dzr;
        ti = zi + dzi;
        if (tr * tr + ti * ti > 4.0) { return n; };

        // dz' = (2*Z[n] + dz[n])*dz[n] + dc  =>  dz[n+1]
        //   real part: (2*zr + dzr)*dzr - (2*zi + dzi)*dzi + dcr
        //   imag part: (2*zr + dzr)*dzi + (2*zi + dzi)*dzr + dci
        tr      = 2.0 * zr + dzr;
        ti      = 2.0 * zi + dzi;
        dzr_new = tr * dzr - ti * dzi + dcr;
        dzi_new = tr * dzi + ti * dzr + dci;
        dzr = dzr_new;
        dzi = dzi_new;

        n++;
    };

    // Reference orbit exhausted before pixel escaped - fall back to full precision
    return mandelbrot_double(ref_cr + dcr, ref_ci + dci, max_iter);
};

// Map iteration count to an RGB color using a smooth palette
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

    // t in [0,1] across one 256-step cycle - always positive
    // palette_offset rotates the color band over time for a breathing animation
    t = (double)(iter % 256) / 255.0 + palette_offset;
    t = t - (double)(int)t;

    // 5-stop palette for deep contrast:
    // 0.00 - 0.20: black -> deep purple
    // 0.20 - 0.45: deep purple -> electric blue
    // 0.45 - 0.65: electric blue -> bright teal/cyan
    // 0.65 - 0.85: bright teal -> deep gold
    // 0.85 - 1.00: deep gold -> crimson -> fades back to black (matches t=0 for seamless wrap)
    if (t < 0.2)
    {
        s = t / 0.2;
        *r = s * 0.45;
        *g = 0.0;
        *b = s * 0.6;
    }
    elif (t < 0.45)
    {
        s = (t - 0.2) / 0.25;
        *r = 0.45 - s * 0.45;
        *g = s * 0.05;
        *b = 0.6 + s * 0.4;
    }
    elif (t < 0.65)
    {
        s = (t - 0.45) / 0.2;
        *r = s * 0.05;
        *g = s * 0.9;
        *b = 1.0;
    }
    elif (t < 0.85)
    {
        s = (t - 0.65) / 0.2;
        *r = 0.05 + s * 0.85;
        *g = 0.9 - s * 0.5;
        *b = 1.0 - s * 1.0;
    }
    else
    {
        // Fade from deep gold/crimson back to black so the wrap joins t=0 smoothly
        s = (t - 0.85) / 0.15;
        *r = 0.9 - s * 0.9;
        *g = 0.4 - s * 0.4;
        *b = 0.0;
    };

    return;
};

extern def !! GetTickCount()       -> DWORD;

// ============================================================================
//  Pixel buffer - heap allocated, non-overlapping writes by workers
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
           use_perturb,     // 1 = perturbation path, 0 = full double precision
           need_decimal;    // 1 = pixel coords need Decimal, 0 = double is sufficient
    Decimal x_min,
            y_min,
            x_range, y_range;
    double  ref_cr,         // Reference centre as double (for dc computation)
            ref_ci,
            // Double equivalents of view bounds - used when need_decimal == 0
            x_min_d,
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
    // ── Decimal path ─────────────────────────────────────────
    // Pixel coordinates computed in Decimal to avoid catastrophic
    // cancellation at deep zoom where double mantissa is exhausted.
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
                    // ── Fast double path ─────────────────────────────────────
                    // Pixel coordinates computed entirely in double; no Decimal
                    // overhead.  Safe while zoom >= double_limit (~1e-15).
                    fx_d = sl.x_min_d + sl.x_range_d * ((double)col + 0.5) / (double)sl.cols;
                    fy_d = sl.y_min_d + sl.y_range_d * ((double)row + 0.5) / (double)sl.rows;
                }
                else
                {
                    // fx = x_min + x_range * (col + 0.5) / cols
                    decimal_from_i64(@col_d, (i64)col);
                    decimal_add(@tmp, @col_d, @half);
                    decimal_mul(@tmp2, @sl.x_range, @tmp);
                    decimal_div(@tmp, @tmp2, @cols_d);
                    decimal_add(@fx, @sl.x_min, @tmp);

                    // fy = y_min + y_range * (row + 0.5) / rows
                    decimal_from_i64(@row_d, (i64)row);
                    decimal_add(@tmp, @row_d, @half);
                    decimal_mul(@tmp2, @sl.y_range, @tmp);
                    decimal_div(@tmp, @tmp2, @rows_d);
                    decimal_add(@fy, @sl.y_min, @tmp);

                    fx_d = decimal_to_double(@fx);
                    fy_d = decimal_to_double(@fy);
                };

                if (sl.use_perturb == 1)
                {
                    // Convert pixel coord to double and compute delta from reference
                    iter = mandelbrot_perturb(sl.ref_cr, sl.ref_ci,
                                             fx_d - sl.ref_cr, fy_d - sl.ref_ci,
                                             sl.dyn_max_iter);
                }
                else
                {
                    // Full double precision path (navigation or interior reference)
                    iter = mandelbrot_double(fx_d, fy_d, sl.dyn_max_iter);
                };

                g_iters[idx] = iter;
            }
            else
            {
                // Color-only pass: reuse cached iteration count
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

    // ── Query core count ──────────────────────────────────
    SYSTEM_INFO_PARTIAL sysinfo;
    GetSystemInfo((void*)@sysinfo);
    int num_threads = (int)sysinfo.dwNumberOfProcessors;
    if (num_threads < 1)           { num_threads = 1; };
    if (num_threads > MAX_THREADS) { num_threads = MAX_THREADS; };

    print("Logical cores: \0");
    print(num_threads);
    print("\n\0");
    print("Decimal precision: \0"); print(precision); print(" digits\n\0");

    Window win("Mandelbrot Set [Decimal 32 + Perturbation] - W/S: Zoom  A/D: Pan X  Up/Down: Pan Y\0", 100, 100, WIN_W, WIN_H);
    GLContext gl(win.device_context);

    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();

    glDisable(GL_DEPTH_TEST);

    // ── Texture setup ─────────────────────────────────────
    glEnable(GL_TEXTURE_2D);
    i32 tex_id;
    glGenTextures(1, @tex_id);
    glBindTexture(GL_TEXTURE_2D, tex_id);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

    // View parameters as Decimals for full 28-digit precision
    Decimal cx, cy, zoom, half_zoom,
            x_min, y_min, x_range, y_range,
            tmp, tmp2, tmp3,
            zoom_delta, pan_delta,

    // Zoom threshold sentinels
    // Hysteresis band prevents flickering at the double/Decimal boundary:
    //   decimal_enter : zoom-in  crossing - switch double->Decimal at 1e-14
    //   decimal_exit  : zoom-out crossing - switch Decimal->double at 1e-13
    // The 10x gap means a single direction of travel cannot cause oscillation.
            thresh1, thresh2, thresh3,
            decimal_enter, decimal_exit;
    decimal_from_string(@thresh1,       "1\0");
    decimal_from_string(@thresh2,       "0.01\0");
    decimal_from_string(@thresh3,       "0.0001\0");
    decimal_from_string(@decimal_enter, "0.00000000000001\0");   // 1e-14  enter Decimal mode
    decimal_from_string(@decimal_exit,  "0.0000000000001\0");    // 1e-13  leave Decimal mode

    decimal_from_string(@cx,   "-0.5\0");
    decimal_from_string(@cy,   "0\0");
    decimal_from_string(@zoom, "3\0");


    float zoom_speed, pan_speed, dt;
    double palette_time,
           palette_offset,
           ref_cr, ref_ci,
           x_min_d, y_min_d, x_range_d, y_range_d;
    int tile,
        dyn_max_iter,
        prev_dyn_max_iter,
        cols, rows,
        cur_w, cur_h,
        rows_per_thread, t,
        use_perturb;
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
        // Delta time
        t_now  = GetTickCount();
        dt     = (float)(t_now - t_last) / 1000.0;
        t_last = t_now;
        if (dt > 0.1) { dt = 0.1; };

        // Advance palette rotation time - 0.12 cycles/second for a gentle breathing effect
        palette_time = palette_time + (double)dt * 0.12;

        // Keep palette_time in [0,1) to prevent precision loss over long sessions
        if (palette_time >= 1.0) { palette_time = palette_time - 1.0; };

        palette_offset = palette_time;

        // Query actual client area each frame so resize/maximize works
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

        // Detect if any movement key is held for adaptive quality
        moving = ((w_state  `& 0x8000) != 0) |
                 ((s_state  `& 0x8000) != 0) |
                 ((a_state  `& 0x8000) != 0) |
                 ((d_state  `& 0x8000) != 0) |
                 ((up_state `& 0x8000) != 0) |
                 ((dn_state `& 0x8000) != 0);

        // Any navigation invalidates the cached reference orbit
        if (moving) { ref_dirty = true; };

        // Coarser tile + fewer iters while navigating, full quality when still
        tile = moving ? TILE_MOVING : TILE_STILL;

        cols = cur_w / tile;
        rows = cur_h / tile;
        if (cols < 1) { cols = 1; };
        if (rows < 1) { rows = 1; };

        // Scale max iterations with zoom depth.
        // At shallow zoom a small budget is fine; as we zoom in detail requires
        // more iterations to resolve.  Formula: 200 * decades_of_zoom, where
        // decades = -log10(zoom).  This gives ~200 at zoom=1, ~1200 at zoom=1e-5,
        // ~4000 at zoom=1e-15, etc., clamped to [128, MAX_ITER].
        //
        // We approximate -log10(zoom) from the Decimal exponent:
        //   zoom is stored as coeff * 10^exp.  The number of leading zeros
        //   (depth in decades) is roughly -(exp + coeff_digits - 1).
        //   A simpler proxy: just use the staircase for coarse tiers and let
        //   the exponent field give us the fine depth.
        {
            // Read the raw exponent of zoom.  For zoom = a * 10^e,
            // depth_decades ~ -(e + digit_count - 1).  We cap at 40 decades
            // (matches 28-digit Decimal precision with headroom).
            zoom_exp    = zoom.exponent;
            zoom_digits = decimal_bigint_digit_count(@zoom.coefficient);
            depth       = -(zoom_exp + zoom_digits - 1);
            if (depth < 0)  { depth = 0;  };
            if (depth > 40) { depth = 40; };
            // 200 iterations per decade of zoom depth, minimum 128
            dyn_max_iter = 128 + depth * 200;
            if (dyn_max_iter > MAX_ITER) { dyn_max_iter = MAX_ITER; };
        };
        // While moving, halve the iteration budget on top of tile coarsening
        if (moving) { dyn_max_iter = dyn_max_iter >> 1; };

        // If the iteration budget changed the cached iter values are no longer
        // comparable against the new max (interior pixels stored as old max will
        // be misidentified as escaped, producing black screens and palette noise).
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
            // Floor at 10^-27 so we never underflow the precision
            decimal_from_string(@tmp, "0.000000000000000000000000001\0");
            if (decimal_cmp(@zoom, @tmp) < 0)
            {
                decimal_copy(@zoom, @tmp);
            };
        };

        // Zoom out: zoom /= (1 - zoom_speed * dt)  -- exact inverse of zoom-in
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

        // Pan left: cx -= zoom * pan_speed * dt
        if ((a_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_sub(@cx, @cx, @tmp);
        };

        // Pan right: cx += zoom * pan_speed * dt
        if ((d_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_add(@cx, @cx, @tmp);
        };

        // Pan up: cy -= zoom * pan_speed * dt
        if ((up_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_sub(@cy, @cy, @tmp);
        };

        // Pan down: cy += zoom * pan_speed * dt
        if ((dn_state `& 0x8000) != 0)
        {
            decimal_from_i64(@tmp2, (i64)(pan_speed * dt * 1000000f));
            decimal_from_string(@tmp3, "1000000\0");
            decimal_div(@pan_delta, @tmp2, @tmp3);
            decimal_mul(@tmp, @zoom, @pan_delta);
            decimal_add(@cy, @cy, @tmp);
        };

        // ── Reallocate pixel buffer if tile count changed ─
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
            // Only skip fractal recompute when stationary and the reference orbit
            // is clean.  A dirty ref means the arithmetic mode may have changed
            // (double/Decimal boundary crossing) so cached iters must be discarded.
            recolor_only = !moving & !ref_dirty;
        };

        // ── Compute view parameters in Decimal ───────────────────────────────
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

        // ── Recompute reference orbit when view has changed ──────────────────
        // Only for stationary frames; moving always uses full double precision.
        //
        // Hysteresis prevents flickering at the double/Decimal boundary:
        //   Zooming in:  switch to Decimal when zoom crosses below decimal_enter (1e-14)
        //   Zooming out: switch back to double only when zoom rises above decimal_exit (1e-13)
        // If the mode actually changes, invalidate the reference orbit immediately so
        // it is recomputed under the correct arithmetic on the very next still frame.
        {
            was_decimal = need_decimal;
            if (!need_decimal)
            {
                // Currently in double mode - enter Decimal if zoom dropped below enter threshold
                if (decimal_cmp(@zoom, @decimal_enter) < 0)
                {
                    need_decimal = true;
                };
            }
            else
            {
                // Currently in Decimal mode - leave only when zoom rises above exit threshold
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

        if (ref_dirty & !moving)
        {
            ref_cr = decimal_to_double(@cx);
            ref_ci = decimal_to_double(@cy);
            if (need_decimal)
            {
                // Decimal reference orbit - exact centre at any depth
                compute_reference_orbit(@cx, @cy, dyn_max_iter);
            }
            else
            {
                // Fast double reference orbit - sufficient above 1e-15
                compute_reference_orbit_double(ref_cr, ref_ci, dyn_max_iter);
            };
            ref_dirty    = false;
            recolor_only = false;
        };

        // Use perturbation only when stationary and the reference orbit escaped.
        // If ref is interior (g_ref_len == dyn_max_iter) every delta also runs to
        // max_iter producing a black blob - disable and fall back to full precision.
        use_perturb = (!moving & g_ref_len > 0 & g_ref_len < dyn_max_iter) ? 1 : 0;

        // ── Partition rows across threads and launch ──────────────────────────
        rows_per_thread = rows / num_threads;
        if (rows_per_thread < 1) { rows_per_thread = 1; };

        // Pre-convert view bounds to double once for the fast path
        x_min_d   = decimal_to_double(@x_min);
        y_min_d   = decimal_to_double(@y_min);
        x_range_d = decimal_to_double(@x_range);
        y_range_d = decimal_to_double(@y_range);

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
            g_slices[t].use_perturb    = use_perturb;
            g_slices[t].need_decimal   = need_decimal ? 1 : 0;
            decimal_copy(@g_slices[t].x_min,   @x_min);
            decimal_copy(@g_slices[t].y_min,   @y_min);
            decimal_copy(@g_slices[t].x_range, @x_range);
            decimal_copy(@g_slices[t].y_range, @y_range);
            g_slices[t].x_min_d        = x_min_d;
            g_slices[t].y_min_d        = y_min_d;
            g_slices[t].x_range_d      = x_range_d;
            g_slices[t].y_range_d      = y_range_d;
            g_slices[t].ref_cr         = ref_cr;
            g_slices[t].ref_ci         = ref_ci;
            g_slices[t].palette_offset = palette_offset;

            thread_create(@worker, (void*)@g_slices[t], @threads[t]);
            t++;
        };

        // ── Wait for all workers ──────────────────────────
        t = 0;
        while (t < num_threads)
        {
            thread_join(@threads[t]);
            t++;
        };

        gl.set_clear_color(0.0, 0.0, 0.0, 1.0);
        gl.clear();

        // ── Upload pixel buffer as texture and draw one fullscreen quad ───────
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

    // ── Cleanup ───────────────────────────────────────────
    if (g_pixels != 0) { ffree((u64)g_pixels); };
    if (g_iters  != 0) { ffree((u64)g_iters);  };
    if (g_ref_zr != 0) { ffree((u64)g_ref_zr); };
    if (g_ref_zi != 0) { ffree((u64)g_ref_zi); };

    glDeleteTextures(1, @tex_id);

    gl.__exit();
    win.__exit();

    return 0;
};
