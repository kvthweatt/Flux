///
 plasma_pong.fx
 Plasma Pong by Steve Taylor (Partial Clone) - click and hold to emit jets of plasma!
 OpenGL texture pipeline, fmalloc/ffree, double-precision Navier-Stokes
 Optimizations:
   - Persistent thread pool with semaphore dispatch + memory fences
   - Red-black Gauss-Seidel (fully parallel per color pass)
   - Parallel project (divergence + gradient loops threaded)
   - Concurrent vx/vy diffuse (dispatched together, not sequentially)
   - Fused decay+pixel pass
   - Row ranges computed once at startup
   - Division replaced with multiply where possible
   - set_bnd deferred to end of lin_solve iteration loop
///

#import "standard.fx", "math.fx", "vectors.fx", "windows.fx", "opengl.fx", "threading.fx";

using standard::math,
      standard::vectors,
      standard::system::windows,
      standard::threading,
      standard::atomic;

// ============================================================================
// SIMULATION CONSTANTS
// ============================================================================

// All simulation constants as #def - zero global memory loads in hot paths
#def SIM_W     256;
#def SIM_H     192;
#def ITER      20;
#def VISCOSITY 0.001;
#def DIFFUSION 0.0001;
#def DT        0.1;
#def DECAY     0.9998;
#def INV255    0.00392156862745098;

const int    WIN_W        = 1024,
             WIN_H        = 768,
             MAX_THREADS  = 64;

// GUI button geometry - parallelogram with ~110 degree slanted sides
// Slant: top edge shifted right by BTN_SLANT px, bottom edge shifted left
#def BTN_W     220;
#def BTN_H      52;
#def BTN_SLANT  18;

// ============================================================================
// FIELD STORAGE
// ============================================================================

heap double* g_dens      = (double*)0,
             g_dens_prev = (double*)0,
             g_vx        = (double*)0,
             g_vy        = (double*)0,
             g_vx_prev   = (double*)0,
             g_vy_prev   = (double*)0;

// Upload buffers - floats for GL texture upload (solver uses double internally)
// g_dens_tex: 1 float per cell for GL_LUMINANCE upload
// g_vel_tex:  2 floats per cell (vx, vy) for GL_LUMINANCE_ALPHA upload
heap float*  g_dens_tex = (float*)0,
             g_vel_tex  = (float*)0;

// ============================================================================
// PARTICLE SYSTEM
// ============================================================================

#def MAX_PARTICLES 7500;

heap float* g_part_x = (float*)0,   // particle x in grid coords [0, SIM_W)
            g_part_y = (float*)0;   // particle y in grid coords [0, SIM_H)

global int g_rand_seed = 12345;

// ============================================================================
// THREAD POOL
// ============================================================================

const int PHASE_LINSOLVE_RED   = 0,
          PHASE_LINSOLVE_BLACK = 1,
          PHASE_ADVECT         = 2,
          PHASE_PROJECT_DIV    = 3,
          PHASE_PROJECT_GRAD   = 4,
          PHASE_DECAY          = 5,
          PHASE_EXIT           = 6;

// Hot fields written every dispatch - kept together for cache locality
// Cold fields (row_start/row_end) set once at startup, never change
struct WorkSlice
{
    // Cold - set once at startup
    int     row_start,
            row_end,
    // Hot - written each dispatch
            phase,
            ls_color;
    double* ls_x, ls_x0;
    double  ls_a, ls_c_inv;
    double* adv_dst,
            adv_src,
            adv_u,
            adv_v,
            proj_u,
            proj_v,
            proj_p,
            proj_div;
    double  proj_hx,
            proj_hy,
            proj_hx_inv,
            proj_hy_inv;
    // decay - passed as param to avoid global pointer reload
    double* dp_dens;
};

WorkSlice[64]  g_slices, g_slices2;
Thread[64]     g_threads, g_threads2;
Semaphore      g_work_sem, g_done_sem, g_work_sem2, g_done_sem2;
int g_num_threads    = 1,
    g_rows_per_thread = 1;

// ============================================================================
// MOUSE / WINDOW STATE
// ============================================================================

global bool mouse_down = false;
global int  mouse_x    = 0,
            mouse_y    = 0,
            mouse_px   = 0,
            mouse_py   = 0;

global int  cur_w      = WIN_W,
            cur_h      = WIN_H;

global int g_palette    = 0;
global int g_game_state = 0;   // 0 = main menu, 1 = playing, 2 = quit dialog
global int g_prev_state = 0;   // state to restore when dismissing quit dialog

// Smoothed injection velocity - exponential moving average of mouse delta
global double g_smooth_vx = 0.0,
              g_smooth_vy = 0.0;

// ============================================================================
// PADDLE STATE
// ============================================================================

#def PADDLE_X       4;        // grid x position of player paddle (left side)
#def PADDLE_X_CPU   (SIM_W - 6);  // grid x position of CPU paddle (right side)
#def PADDLE_HALF_H  14;       // half-height in grid cells
#def PADDLE_JET_STR 40.0;
#def PADDLE_DENS    400.0;
#def CPU_SPEED      1.5;      // max grid cells per frame the CPU paddle can move

global int    g_paddle_gy     = 96;   // player paddle center in grid coords
global int    g_cpu_paddle_gy = 96;   // CPU paddle center in grid coords
global bool   g_jetting       = false;
global bool   g_sucking       = false;
global float  g_suck_charge   = 0.0;  // accumulates while holding right click

// ============================================================================
// BALL STATE
// ============================================================================

#def BALL_RADIUS    8.0;      // screen pixels
#def BALL_FLUID_K   2.0;     // fluid velocity influence scale - low for heavy feel
#def BALL_DRAG      0.99;    // per-frame velocity damping
#def BALL_BOUNCE    0.72;     // wall bounce restitution (top/bottom)

global float g_ball_x  = -1.0,  // -1 = needs reset on first gameplay frame
             g_ball_y  = 0.0,
             g_ball_vx = 0.0,
             g_ball_vy = 0.0;

// ============================================================================
// GAME SCORE STATE
// ============================================================================

global int g_lives = 3;
global int g_level = 1;

def btn_hit_test(int mx, int my, int cx, int cy) -> bool,
    btn_hit_test_ex(int, int, int, int, int, int) -> bool,
    draw_parallelogram_btn(int, int, int, int, int, float, float) -> void,
    text_width(byte*, int) -> int,
    draw_text(byte*, int, int, int, float, float) -> void,
    draw_quit_dialog(int, int) -> void,
    paddle_update() -> void,
    cpu_paddle_update() -> void,
    draw_paddle(int, int, int, int) -> void,
    ball_reset(int, int) -> void,
    ball_update(int, int) -> void,
    draw_ball(int, int) -> void,
    draw_hud(int, int) -> void,
    inject_vorticity() -> void,
    vorticity_confinement(double*, double*) -> void;

// ============================================================================
// WINDOW PROCEDURE
// ============================================================================

def FluidWindowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) -> LRESULT
{
    int nx, ny,
        click_x, click_y;

    if (msg == WM_CLOSE)      { DestroyWindow(hwnd); return 0; };
    if (msg == WM_DESTROY)    { PostQuitMessage(0);  return 0; };
    if (msg == WM_ERASEBKGND) { return 1; };

    if (msg == WM_PAINT)
    {
        PAINTSTRUCT ps;
        BeginPaint(hwnd, @ps);
        EndPaint(hwnd, @ps);
        return 0;
    };

    if (msg == WM_LBUTTONDOWN)
    {
        click_x = (int)(lParam & 0xFFFF);
        click_y = (int)((lParam >> 16) & 0xFFFF);

        if (g_game_state == 0)
        {
            // Menu: check Start Game button hit
            if (btn_hit_test(click_x, click_y, cur_w / 2, cur_h / 2))
            {
                g_lives      = 3;
                g_level      = 1;
                g_ball_x     = -1.0;
                g_game_state = 1;
            };
            return 0;
        };

        if (g_game_state == 2)
        {
            // Quit dialog: Yes button at center-left, No button at center-right
            // Draw btn cy-50 (bottom-origin) = lower on screen = click cy+50 (top-origin)
            if (btn_hit_test_ex(click_x, click_y, cur_w / 2 - 80, cur_h / 2 + 50, BTN_W / 4, BTN_H / 2))
            {
                PostQuitMessage(0);
            };
            if (btn_hit_test_ex(click_x, click_y, cur_w / 2 + 80, cur_h / 2 + 50, BTN_W / 4, BTN_H / 2))
            {
                g_game_state = g_prev_state;
            };
            return 0;
        };

        mouse_down = true;
        if (g_game_state == 1) { g_jetting = true; };
        mouse_px   = click_x;
        mouse_py   = click_y;
        mouse_x    = mouse_px;
        mouse_y    = mouse_py;
        return 0;
    };

    if (msg == WM_LBUTTONUP)
    {
        mouse_down = false;
        g_jetting  = false;
        return 0;
    };

    if (msg == WM_RBUTTONDOWN)
    {
        if (g_game_state == 1)
        {
            g_sucking     = true;
            g_jetting     = false;
            g_suck_charge = 0.0;
        };
        return 0;
    };

    if (msg == WM_RBUTTONUP)
    {
        g_sucking = false;
        return 0;
    };

    if (msg == WM_MOUSEMOVE)
    {
        nx       = (int)(lParam & 0xFFFF);
        ny       = (int)((lParam >> 16) & 0xFFFF);
        mouse_px = mouse_x;
        mouse_py = mouse_y;
        mouse_x  = nx;
        mouse_y  = ny;
        return 0;
    };

    if (msg == WM_KEYDOWN)
    {
        if (wParam == 0x1B)  // VK_ESCAPE
        {
            if (g_game_state != 2)
            {
                g_prev_state  = g_game_state;
                g_game_state  = 2;
                g_jetting     = false;
                g_sucking     = false;
                g_suck_charge = 0.0;
            };
            return 0;
        };
        if (wParam == 0x31) { g_palette = 0; return 0; };
        if (wParam == 0x32) { g_palette = 1; return 0; };
        if (wParam == 0x33) { g_palette = 2; return 0; };
        if (wParam == 0x34) { g_palette = 3; return 0; };
        if (wParam == 0x35) { g_palette = 4; return 0; };
        if (wParam == 0x36) { g_palette = 5; return 0; };
        if (wParam == 0x37) { g_palette = 6; return 0; };
        if (wParam == 0x38) { g_palette = 7; return 0; };
        if (wParam == 0x39) { g_palette = 8; return 0; };
        if (wParam == 0x30) { g_palette = 9; return 0; };
        return 0;
    };

    return DefWindowProcA(hwnd, msg, wParam, lParam);
};

// ============================================================================
// HELPER: flat index - manually expanded in hot loops to avoid call overhead
// ============================================================================

def IX(int x, int y) -> int
{
    return y * SIM_W + x;
};

// ============================================================================
// BOUNDARY CONDITIONS
// ============================================================================

def set_bnd(int b, double* x) -> void
{
    int i;

    for (i = 1; i < SIM_H - 1; i++)
    {
        if (b == 1)
        {
            x[i * SIM_W]              = (0.0 - x[i * SIM_W + 1]);
            x[i * SIM_W + SIM_W - 1]  = (0.0 - x[i * SIM_W + SIM_W - 2]);
        }
        else
        {
            x[i * SIM_W]              = x[i * SIM_W + 1];
            x[i * SIM_W + SIM_W - 1]  = x[i * SIM_W + SIM_W - 2];
        };
    };

    for (i = 1; i < SIM_W - 1; i++)
    {
        if (b == 2)
        {
            x[i]                       = (0.0 - x[i + SIM_W]);
            x[(SIM_H-1) * SIM_W + i]   = (0.0 - x[(SIM_H-2) * SIM_W + i]);
        }
        else
        {
            x[i]                       = x[i + SIM_W];
            x[(SIM_H-1) * SIM_W + i]   = x[(SIM_H-2) * SIM_W + i];
        };
    };

    x[0]                          = 0.5 * (x[1]           + x[SIM_W]);
    x[SIM_W - 1]                  = 0.5 * (x[SIM_W - 2]   + x[SIM_W + SIM_W - 1]);
    x[(SIM_H-1) * SIM_W]          = 0.5 * (x[(SIM_H-1) * SIM_W + 1]       + x[(SIM_H-2) * SIM_W]);
    x[(SIM_H-1) * SIM_W + SIM_W-1]= 0.5 * (x[(SIM_H-1) * SIM_W + SIM_W-2] + x[(SIM_H-2) * SIM_W + SIM_W-1]);

    return;
};

// ============================================================================
// WORKER BAND FUNCTIONS
// ============================================================================

def linsolve_band(int row_start, int row_end, int color,
                  double* x, double* x0, double a, double c_inv) -> void
{
    int jstart,
        jend,
        i_start,
        i, j,
        base;     // j * SIM_W - row base offset

    jstart = row_start;
    jend   = row_end;
    if (jstart < 1)       { jstart = 1;       };
    if (jend   > SIM_H-1) { jend   = SIM_H-1; };

    for (j = jstart; j < jend; j++)
    {
        base    = j * SIM_W;
        i_start = 1 + ((j + color + 1) & 1);
        i       = i_start;
        while (i < SIM_W - 1)
        {
            x[base + i] = (x0[base + i] + a * (x[base + i - 1] + x[base + i + 1] +
                                                x[base + i - SIM_W] + x[base + i + SIM_W])) * c_inv;
            i = i + 2;
        };
    };
    return;
};

def advect_band(int row_start, int row_end,
                double* d, double* d0, double* u, double* v) -> void
{
    double dt0x,
           dt0y,
           max_x,
           max_y,
           bx,
           by,
           s0,
           s1,
           t0,
           t1;
    int jstart, jend,
        i,  j,
        i0, j0,
        i1, j1,
        base, base00, base01;

    dt0x  = DT * (double)(SIM_W - 2);
    dt0y  = DT * (double)(SIM_H - 2);
    max_x = (double)(SIM_W - 2) + 0.5;
    max_y = (double)(SIM_H - 2) + 0.5;

    jstart = row_start;
    jend   = row_end;
    if (jstart < 1)       { jstart = 1;       };
    if (jend   > SIM_H-1) { jend   = SIM_H-1; };

    for (j = jstart; j < jend; j++)
    {
        base = j * SIM_W;
        for (i = 1; i < SIM_W - 1; i++)
        {
            bx = (double)i - dt0x * u[base + i];
            by = (double)j - dt0y * v[base + i];

            if (bx < 0.5)   { bx = 0.5;   };
            if (bx > max_x) { bx = max_x; };
            if (by < 0.5)   { by = 0.5;   };
            if (by > max_y) { by = max_y; };

            i0 = (int)bx;
            j0 = (int)by;
            i1 = i0 + 1;
            j1 = j0 + 1;

            s1 = bx - (double)i0;
            s0 = 1.0 - s1;
            t1 = by - (double)j0;
            t0 = 1.0 - t1;

            base00 = j0 * SIM_W;
            base01 = j1 * SIM_W;

            d[base + i] = s0 * (t0 * d0[base00 + i0] + t1 * d0[base01 + i0]) +
                           s1 * (t0 * d0[base00 + i1] + t1 * d0[base01 + i1]);
        };
    };
    return;
};

// Compute divergence and zero pressure - parallel
def project_div_band(int row_start, int row_end,
                     double* u, double* v, double* p, double* div,
                     double hx, double hy) -> void
{
    int jstart, jend,
        i, j,
        base;

    jstart = row_start;
    jend   = row_end;
    if (jstart < 1)       { jstart = 1;       };
    if (jend   > SIM_H-1) { jend   = SIM_H-1; };

    for (j = jstart; j < jend; j++)
    {
        base = j * SIM_W;
        for (i = 1; i < SIM_W - 1; i++)
        {
            div[base + i] = (0.0 - 0.5) * (hx * (u[base + i + 1] - u[base + i - 1]) +
                                             hy * (v[base + i + SIM_W] - v[base + i - SIM_W]));
            p[base + i]   = 0.0;
        };
    };
    return;
};

// Subtract pressure gradient - parallel, division replaced with multiply
def project_grad_band(int row_start, int row_end,
                      double* u, double* v, double* p,
                      double hx_inv, double hy_inv) -> void
{
    int jstart, jend,
        i, j,
        base;

    jstart = row_start;
    jend   = row_end;
    if (jstart < 1)       { jstart = 1;       };
    if (jend   > SIM_H-1) { jend   = SIM_H-1; };

    for (j = jstart; j < jend; j++)
    {
        base = j * SIM_W;
        for (i = 1; i < SIM_W - 1; i++)
        {
            u[base + i] -= 0.5 * (p[base + i + 1]      - p[base + i - 1])      * hx_inv;
            v[base + i] -= 0.5 * (p[base + i + SIM_W]  - p[base + i - SIM_W])  * hy_inv;
        };
    };
    return;
};

// Decay only - shader does color mapping on GPU
def decay_band(int row_start, int row_end, double* dens) -> void
{
    int i, j, base;
    double d;

    for (j = row_start; j < row_end; j++)
    {
        base = j * SIM_W;
        for (i = 0; i < SIM_W; i++)
        {
            d = dens[base + i] * DECAY;
            if (d < 0.0001) { d = 0.0; };
            dens[base + i] = d;
        };
    };
    return;
};

// Convert double fields to float upload buffers for GL texture upload
// ============================================================================
// PARTICLE SYSTEM - update only, rendering done by GPU point sprites
// ============================================================================

def fast_rand() -> int
{
    g_rand_seed = g_rand_seed * 1664525 + 1013904223;
    return g_rand_seed & 0x7FFFFFFF;
};

def particles_init() -> void
{
    int i;
    for (i = 0; i < MAX_PARTICLES; i++)
    {
        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        g_part_x[i] = (float)(g_rand_seed & 0x7FFFFFFF) / (float)0x7FFFFFFF * (float)SIM_W;
        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        g_part_y[i] = (float)(g_rand_seed & 0x7FFFFFFF) / (float)0x7FFFFFFF * (float)SIM_H;
    };
    return;
};

def particles_update() -> void
{
    int   i, pi, pj;
    float px,
          py,
          vx,
          vy;

    for (i = 0; i < MAX_PARTICLES; i++)
    {
        px = g_part_x[i];
        py = g_part_y[i];

        pi = (int)px;
        pj = (int)py;

        if (pi < 1)       { pi = 1;       };
        if (pi > SIM_W-2) { pi = SIM_W-2; };
        if (pj < 1)       { pj = 1;       };
        if (pj > SIM_H-2) { pj = SIM_H-2; };

        vx = (float)(g_vx[pj * SIM_W + pi] * 15.0);
        vy = (float)(g_vy[pj * SIM_W + pi] * 15.0);

        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        vx = vx + (float)((g_rand_seed & 0xFF) - 128) * 0.001;
        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        vy = vy + (float)((g_rand_seed & 0xFF) - 128) * 0.001;

        px = px + vx;
        py = py + vy;

        if (px < 0.0)           { px = px + (float)SIM_W; };
        if (px >= (float)SIM_W) { px = px - (float)SIM_W; };
        if (py < 0.0)           { py = py + (float)SIM_H; };
        if (py >= (float)SIM_H) { py = py - (float)SIM_H; };

        g_part_x[i] = px;
        g_part_y[i] = py;
    };
    return;
};

// ============================================================================
// PERSISTENT WORKER
// ============================================================================

def worker(void* arg) -> void*
{
    WorkSlice* sl;
    sl = (WorkSlice*)arg;

    while (true)
    {
        semaphore_wait(@g_work_sem);
        load_fence();

        if (sl.phase == PHASE_EXIT) { return (void*)0; };

        if (sl.phase == PHASE_LINSOLVE_RED | sl.phase == PHASE_LINSOLVE_BLACK)
        {
            linsolve_band(sl.row_start, sl.row_end, sl.ls_color,
                          sl.ls_x, sl.ls_x0, sl.ls_a, sl.ls_c_inv);
        }
        elif (sl.phase == PHASE_ADVECT)
        {
            advect_band(sl.row_start, sl.row_end,
                        sl.adv_dst, sl.adv_src, sl.adv_u, sl.adv_v);
        }
        elif (sl.phase == PHASE_PROJECT_DIV)
        {
            project_div_band(sl.row_start, sl.row_end,
                             sl.proj_u, sl.proj_v, sl.proj_p, sl.proj_div,
                             sl.proj_hx, sl.proj_hy);
        }
        elif (sl.phase == PHASE_PROJECT_GRAD)
        {
            project_grad_band(sl.row_start, sl.row_end,
                              sl.proj_u, sl.proj_v, sl.proj_p,
                              sl.proj_hx_inv, sl.proj_hy_inv);
        }
        elif (sl.phase == PHASE_DECAY)
        {
            decay_band(sl.row_start, sl.row_end, sl.dp_dens);
        };

        semaphore_post(@g_done_sem);
    };

    return (void*)0;
};

def worker2(void* arg) -> void*
{
    WorkSlice* sl;
    sl = (WorkSlice*)arg;

    while (true)
    {
        semaphore_wait(@g_work_sem2);
        load_fence();

        if (sl.phase == PHASE_EXIT) { return (void*)0; };

        if (sl.phase == PHASE_LINSOLVE_RED | sl.phase == PHASE_LINSOLVE_BLACK)
        {
            linsolve_band(sl.row_start, sl.row_end, sl.ls_color,
                          sl.ls_x, sl.ls_x0, sl.ls_a, sl.ls_c_inv);
        }
        elif (sl.phase == PHASE_ADVECT)
        {
            advect_band(sl.row_start, sl.row_end,
                        sl.adv_dst, sl.adv_src, sl.adv_u, sl.adv_v);
        }
        elif (sl.phase == PHASE_PROJECT_DIV)
        {
            project_div_band(sl.row_start, sl.row_end,
                             sl.proj_u, sl.proj_v, sl.proj_p, sl.proj_div,
                             sl.proj_hx, sl.proj_hy);
        }
        elif (sl.phase == PHASE_PROJECT_GRAD)
        {
            project_grad_band(sl.row_start, sl.row_end,
                              sl.proj_u, sl.proj_v, sl.proj_p,
                              sl.proj_hx_inv, sl.proj_hy_inv);
        }
        elif (sl.phase == PHASE_DECAY)
        {
            decay_band(sl.row_start, sl.row_end, sl.dp_dens);
        };

        semaphore_post(@g_done_sem2);
    };

    return (void*)0;
};

def dispatch_linsolve2(int color, double* x, double* x0, double a, double c_inv) -> void
{
    int t;

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices2[t].phase    = color == 0 ? PHASE_LINSOLVE_RED : PHASE_LINSOLVE_BLACK;
        g_slices2[t].ls_x     = x;
        g_slices2[t].ls_x0    = x0;
        g_slices2[t].ls_a     = a;
        g_slices2[t].ls_c_inv = c_inv;
        g_slices2[t].ls_color = color;
    };
    store_fence();
    for (t = 0; t < g_num_threads; t++) { semaphore_post(@g_work_sem2); };
    return;
};

def collect2() -> void
{
    int t;
    for (t = 0; t < g_num_threads; t++) { semaphore_wait(@g_done_sem2); };
    return;
};

def dispatch_linsolve_post(int color, double* x, double* x0, double a, double c_inv) -> void
{
    int t;

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].phase    = color == 0 ? PHASE_LINSOLVE_RED : PHASE_LINSOLVE_BLACK;
        g_slices[t].ls_x     = x;
        g_slices[t].ls_x0    = x0;
        g_slices[t].ls_a     = a;
        g_slices[t].ls_c_inv = c_inv;
        g_slices[t].ls_color = color;
    };
    store_fence();
    for (t = 0; t < g_num_threads; t++) { semaphore_post(@g_work_sem); };
    return;
};

def collect1() -> void
{
    int t;
    for (t = 0; t < g_num_threads; t++) { semaphore_wait(@g_done_sem); };
    return;
};

def dispatch_linsolve(int color, double* x, double* x0, double a, double c_inv) -> void
{
    int t;

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].phase    = color == 0 ? PHASE_LINSOLVE_RED : PHASE_LINSOLVE_BLACK;
        g_slices[t].ls_x     = x;
        g_slices[t].ls_x0    = x0;
        g_slices[t].ls_a     = a;
        g_slices[t].ls_c_inv = c_inv;
        g_slices[t].ls_color = color;
    };
    store_fence();
    for (t = 0; t < g_num_threads; t++) { semaphore_post(@g_work_sem); };
    for (t = 0; t < g_num_threads; t++) { semaphore_wait(@g_done_sem); };
    return;
};

def dispatch_advect(double* dst, double* src, double* u, double* v) -> void
{
    int t;

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].phase   = PHASE_ADVECT;
        g_slices[t].adv_dst = dst;
        g_slices[t].adv_src = src;
        g_slices[t].adv_u   = u;
        g_slices[t].adv_v   = v;
    };
    store_fence();
    for (t = 0; t < g_num_threads; t++) { semaphore_post(@g_work_sem); };
    for (t = 0; t < g_num_threads; t++) { semaphore_wait(@g_done_sem); };
    return;
};

def dispatch_project_div(double* u, double* v, double* p, double* div,
                          double hx, double hy) -> void
{
    int t;

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].phase    = PHASE_PROJECT_DIV;
        g_slices[t].proj_u   = u;
        g_slices[t].proj_v   = v;
        g_slices[t].proj_p   = p;
        g_slices[t].proj_div = div;
        g_slices[t].proj_hx  = hx;
        g_slices[t].proj_hy  = hy;
    };
    store_fence();
    for (t = 0; t < g_num_threads; t++) { semaphore_post(@g_work_sem); };
    for (t = 0; t < g_num_threads; t++) { semaphore_wait(@g_done_sem); };
    return;
};

def dispatch_project_grad(double* u, double* v, double* p,
                           double hx_inv, double hy_inv) -> void
{
    int t;

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].phase       = PHASE_PROJECT_GRAD;
        g_slices[t].proj_u      = u;
        g_slices[t].proj_v      = v;
        g_slices[t].proj_p      = p;
        g_slices[t].proj_hx_inv = hx_inv;
        g_slices[t].proj_hy_inv = hy_inv;
    };
    store_fence();
    for (t = 0; t < g_num_threads; t++) { semaphore_post(@g_work_sem); };
    for (t = 0; t < g_num_threads; t++) { semaphore_wait(@g_done_sem); };
    return;
};

def dispatch_decay() -> void
{
    int t;

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].phase   = PHASE_DECAY;
        g_slices[t].dp_dens = g_dens;
    };
    store_fence();
    for (t = 0; t < g_num_threads; t++) { semaphore_post(@g_work_sem); };
    for (t = 0; t < g_num_threads; t++) { semaphore_wait(@g_done_sem); };
    return;
};

// Convert double fields to float upload buffers - single-threaded, cheap
def upload_textures() -> void
{
    int   i, n, vidx;
    float d, scale;

    scale = 4.0;
    n     = SIM_W * SIM_H;

    for (i = 0; i < n; i++)
    {
        d = (float)(g_dens[i] * INV255);
        if (d > 1.0) { d = 1.0; };
        g_dens_tex[i] = d;

        vidx = i * 2;
        g_vel_tex[vidx]     = (float)(g_vx[i] * scale) + 0.5;
        g_vel_tex[vidx + 1] = (float)(g_vy[i] * scale) + 0.5;
    };
    return;
};

// ============================================================================
// RED-BLACK LIN_SOLVE - set_bnd deferred to end of all iterations
// ============================================================================

def lin_solve_parallel(int b, double* x, double* x0, double a, double c) -> void
{
    double c_inv;
    int k;

    c_inv = 1.0 / c;

    for (k = 0; k < ITER; k++)
    {
        dispatch_linsolve(0, x, x0, a, c_inv);
        dispatch_linsolve(1, x, x0, a, c_inv);
        // set_bnd only on final iteration - intermediate boundaries
        // don't need to be exact for convergence
        if (k == ITER - 1) { set_bnd(b, x); };
    };
    return;
};

// ============================================================================
// DIFFUSE
// ============================================================================

def diffuse(int b, double* x, double* x0, double diff) -> void
{
    double a;
    a = DT * diff * (double)(SIM_W - 2) * (double)(SIM_H - 2);
    lin_solve_parallel(b, x, x0, a, 1.0 + 4.0 * a);
    return;
};

// ============================================================================
// PROJECT - divergence and gradient passes both threaded
// ============================================================================

def project(double* u, double* v, double* p, double* div) -> void
{
    double hx, hy, hx_inv, hy_inv;

    hx     = 1.0 / (double)(SIM_W - 2);
    hy     = 1.0 / (double)(SIM_H - 2);
    hx_inv = (double)(SIM_W - 2);   // 1/hx = SIM_W-2
    hy_inv = (double)(SIM_H - 2);   // 1/hy = SIM_H-2

    dispatch_project_div(u, v, p, div, hx, hy);
    set_bnd(0, div);
    set_bnd(0, p);
    lin_solve_parallel(0, p, div, 1.0, 4.0);
    dispatch_project_grad(u, v, p, hx_inv, hy_inv);
    set_bnd(1, u);
    set_bnd(2, v);
    return;
};

// ============================================================================
// LIN_SOLVE ON POOL2
// ============================================================================

def lin_solve_parallel2(int b, double* x, double* x0, double a, double c) -> void
{
    double c_inv;
    int k;

    c_inv = 1.0 / c;

    for (k = 0; k < ITER; k++)
    {
        dispatch_linsolve2(0, x, x0, a, c_inv);
        collect2();
        dispatch_linsolve2(1, x, x0, a, c_inv);
        collect2();
        if (k == ITER - 1) { set_bnd(b, x); };
    };
    return;
};

// ============================================================================
// CONCURRENT DIFFUSE - runs two independent fields across both pools at once
// ============================================================================

def diffuse_concurrent(int b1, double* x1, double* x10, double diff1,
                        int b2, double* x2, double* x20, double diff2) -> void
{
    double a1, a2,
           c_inv1, c_inv2;
    int k;

    a1     = DT * diff1 * (double)(SIM_W - 2) * (double)(SIM_H - 2);
    a2     = DT * diff2 * (double)(SIM_W - 2) * (double)(SIM_H - 2);
    c_inv1 = 1.0 / (1.0 + 4.0 * a1);
    c_inv2 = 1.0 / (1.0 + 4.0 * a2);

    for (k = 0; k < ITER; k++)
    {
        // Red pass: post both pools simultaneously, then collect both
        dispatch_linsolve_post(0, x1, x10, a1, c_inv1);
        dispatch_linsolve2(0, x2, x20, a2, c_inv2);
        collect1();
        collect2();

        // Black pass: same
        dispatch_linsolve_post(1, x1, x10, a1, c_inv1);
        dispatch_linsolve2(1, x2, x20, a2, c_inv2);
        collect1();
        collect2();

        if (k == ITER - 1)
        {
            set_bnd(b1, x1);
            set_bnd(b2, x2);
        };
    };
    return;
};

// ============================================================================
// VELOCITY STEP
// vx and vy diffuse run concurrently across both thread pools
// ============================================================================

// ============================================================================
// VORTICITY INJECTION - scatter random curl eddies into velocity field
// ============================================================================

def inject_vorticity() -> void
{
    int    k, cx, cy, sign, r;
    double str;

    // 14 vortex seeds per frame, random position and sign
    k = 0;
    while (k < 14)
    {
        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        cx   = 2 + (g_rand_seed & 0xFF) % (SIM_W - 4);

        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        cy   = 2 + (g_rand_seed & 0xFF) % (SIM_H - 4);

        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        sign = ((g_rand_seed >> 8) & 1) == 0 ? 1 : (0 - 1);

        g_rand_seed = g_rand_seed * 1664525 + 1013904223;
        r    = 2 + (g_rand_seed & 0x3);          // radius 2..5
        str  = 0.08 + (double)((g_rand_seed >> 4) & 0xF) * 0.012;

        // Curl injection: tangential velocity around (cx,cy)
        // Left/right of center get +/- vy; above/below get -/+ vx
        if (cx - r >= 1 & cx + r <= SIM_W - 2 &
            cy - r >= 1 & cy + r <= SIM_H - 2)
        {
            g_vy[IX(cx - r, cy)] += (double)sign * str;
            g_vy[IX(cx + r, cy)] -= (double)sign * str;
            g_vx[IX(cx, cy + r)] -= (double)sign * str;
            g_vx[IX(cx, cy - r)] += (double)sign * str;

            // Second ring for wider eddy body
            g_vy[IX(cx - 1, cy)] += (double)sign * str * 0.5;
            g_vy[IX(cx + 1, cy)] -= (double)sign * str * 0.5;
            g_vx[IX(cx, cy + 1)] -= (double)sign * str * 0.5;
            g_vx[IX(cx, cy - 1)] += (double)sign * str * 0.5;
        };

        k++;
    };
    return;
};

def vorticity_confinement(double* vx, double* vy) -> void
{
    int    i, j, base, idx;
    double curl, curl_l, curl_r, curl_d, curl_u,
           grad_x, grad_y, grad_len,
           fx, fy;

    // curl (vorticity) at each cell = dvy/dx - dvx/dy
    // store in g_vx_prev temporarily (unused at this point in vel_step)
    for (j = 1; j < SIM_H - 1; j++)
    {
        base = j * SIM_W;
        for (i = 1; i < SIM_W - 1; i++)
        {
            curl = (vy[base + i + 1] - vy[base + i - 1] -
                    vx[base + i + SIM_W] + vx[base + i - SIM_W]) * 0.5;
            // store absolute curl magnitude
            g_dens_prev[base + i] = curl < 0.0 ? (0.0 - curl) : curl;
            // store signed curl
            g_vx_prev[base + i] = curl;
        };
    };

    // confinement force: eta = grad(|curl|), normalized, cross curl
    for (j = 1; j < SIM_H - 1; j++)
    {
        base = j * SIM_W;
        for (i = 1; i < SIM_W - 1; i++)
        {
            grad_x  = (g_dens_prev[base + i + 1]       - g_dens_prev[base + i - 1])       * 0.5;
            grad_y  = (g_dens_prev[base + i + SIM_W]   - g_dens_prev[base + i - SIM_W])   * 0.5;
            grad_len = sqrt(grad_x * grad_x + grad_y * grad_y) + 0.0001;
            grad_x  = grad_x / grad_len;
            grad_y  = grad_y / grad_len;

            curl = g_vx_prev[base + i];

            // confinement force perpendicular to normalized gradient
            fx = grad_y * curl * (0.0 - 0.8);
            fy = grad_x * curl *        0.8;

            vx[base + i] += DT * fx;
            vy[base + i] += DT * fy;
        };
    };
    return;
};

def vel_step() -> void
{
    // Diffuse vx (pool1) and vy (pool2) concurrently - independent fields
    diffuse_concurrent(1, g_vx_prev, g_vx, VISCOSITY,
                       2, g_vy_prev, g_vy, VISCOSITY);

    project(g_vx_prev, g_vy_prev, g_vx, g_vy);

    dispatch_advect(g_vx, g_vx_prev, g_vx_prev, g_vy_prev);
    set_bnd(1, g_vx);
    dispatch_advect(g_vy, g_vy_prev, g_vx_prev, g_vy_prev);
    set_bnd(2, g_vy);

    // Vorticity confinement - amplifies existing rotation (turbulance=0.8)
    vorticity_confinement(g_vx, g_vy);

    project(g_vx, g_vy, g_vx_prev, g_vy_prev);
    return;
};

// ============================================================================
// DENSITY STEP
// ============================================================================

def dens_step() -> void
{
    int    i, j, base, pass;
    double excess, share;

    diffuse(0, g_dens_prev, g_dens, DIFFUSION);
    dispatch_advect(g_dens, g_dens_prev, g_vx, g_vy);
    set_bnd(0, g_dens);

    // Density cap at 88 - run cascade multiple passes per frame so it fully spreads
    pass = 0;
    while (pass < 2)
    {
        for (j = 1; j < SIM_H - 1; j++)
        {
            base = j * SIM_W;
            for (i = 1; i < SIM_W - 1; i++)
            {
                if (g_dens[base + i] > 88.0)
                {
                    excess = g_dens[base + i] - 88.0;
                    share  = excess * 0.22;
                    g_dens[base + i]          = 88.0;
                    g_dens[base + i + 1]     += share;
                    g_dens[base + i - 1]     += share;
                    g_dens[base + i + SIM_W] += share;
                    g_dens[base + i - SIM_W] += share;
                };
            };
        };
        pass++;
    };
    return;
};

// ============================================================================
// ADD SOURCE AT MOUSE
// ============================================================================

def add_source() -> void
{
    int    gx, gy, r, i, j;
    double raw_vx,
           raw_vy,
           dx, dy,
           dist, fall;

    if (!mouse_down)
    {
        // Decay smoothed velocity when not pressing so next press starts fresh
        g_smooth_vx = g_smooth_vx * 0.85;
        g_smooth_vy = g_smooth_vy * 0.85;
        return;
    };

    gx = mouse_x * SIM_W / cur_w;
    gy = (cur_h - 1 - mouse_y) * SIM_H / cur_h;

    if (gx < 1)       { gx = 1;       };
    if (gx > SIM_W-2) { gx = SIM_W-2; };
    if (gy < 1)       { gy = 1;       };
    if (gy > SIM_H-2) { gy = SIM_H-2; };

    // Raw delta scaled to grid space
    raw_vx = (double)(mouse_x - mouse_px) * (double)SIM_W / (double)cur_w;
    raw_vy = (double)(mouse_py - mouse_y) * (double)SIM_H / (double)cur_h;

    // Exponential moving average - smooths direction, follows gesture
    g_smooth_vx = g_smooth_vx * 0.8 + raw_vx * 0.2;
    g_smooth_vy = g_smooth_vy * 0.8 + raw_vy * 0.2;

    r = 3;

    for (j = gy - r; j <= gy + r; j++)
    {
        for (i = gx - r; i <= gx + r; i++)
        {
            if (i < 1 | i > SIM_W-2) { continue; };
            if (j < 1 | j > SIM_H-2) { continue; };

            dx   = (double)(i - gx);
            dy   = (double)(j - gy);
            dist = sqrt(dx * dx + dy * dy);
            fall = 1.0 - dist / (double)(r + 1);
            if (fall < 0.0) { fall = 0.0; };

            // Dense emission at source
            g_dens[IX(i,j)] += fall * 180.0;

            // Radial outward push from center - makes fluid bloom, not jet
            if (dist > 0.001)
            {
                g_vx[IX(i,j)] += fall * (dx / dist) * 0.8;
                g_vy[IX(i,j)] += fall * (dy / dist) * 0.8;
            };

            // Gentle directional bias from mouse movement - subtle, not dominant
            g_vx[IX(i,j)] += fall * g_smooth_vx * 0.3;
            g_vy[IX(i,j)] += fall * g_smooth_vy * 0.3;
        };
    };
    return;
};

// ============================================================================
// PADDLE
// ============================================================================

def paddle_update() -> void
{
    int    gy, jet_center, j, jstart, jend, jet_x, jitter;
    double dy, fall;
    float  paddle_face_x, ball_dx, ball_dy, ball_dist, pull;

    // Map mouse Y to grid Y (bottom-origin for sim grid)
    gy = (cur_h - 1 - mouse_y) * SIM_H / cur_h;
    if (gy < PADDLE_HALF_H + 1)         { gy = PADDLE_HALF_H + 1;         };
    if (gy > SIM_H - PADDLE_HALF_H - 2) { gy = SIM_H - PADDLE_HALF_H - 2; };
    g_paddle_gy = gy;

    // Suction mode - right click held
    if (g_sucking)
    {
        g_suck_charge = g_suck_charge + 0.018;
        if (g_suck_charge > 1.0) { g_suck_charge = 1.0; };

        // Pull ball toward the paddle face
        paddle_face_x = (float)((PADDLE_X + 2) * cur_w / SIM_W);
        ball_dx       = paddle_face_x - g_ball_x;
        ball_dy       = (float)(gy * cur_h / SIM_H) - g_ball_y;
        ball_dist     = sqrt(ball_dx * ball_dx + ball_dy * ball_dy);
        if (ball_dist > 1.0)
        {
            pull       = 0.6 + g_suck_charge * 1.2;
            g_ball_vx  = g_ball_vx + (ball_dx / ball_dist) * pull;
            g_ball_vy  = g_ball_vy + (ball_dy / ball_dist) * pull;
        };

        // Inject inward fluid suction toward paddle
        jet_x  = PADDLE_X + 2;
        jstart = gy - PADDLE_HALF_H;
        jend   = gy + PADDLE_HALF_H;
        if (jstart < 1)       { jstart = 1;       };
        if (jend   > SIM_H-2) { jend   = SIM_H-2; };
        for (j = jstart; j <= jend; j++)
        {
            dy   = (double)(j - gy);
            fall = 1.0 - (dy * dy) / (double)(PADDLE_HALF_H * PADDLE_HALF_H + 1);
            if (fall < 0.0) { fall = 0.0; };
            g_dens[IX(jet_x, j)] += fall * (PADDLE_DENS * 0.4);
            g_vx[IX(jet_x, j)]   -= fall * (PADDLE_JET_STR * 1.5);
        };

        return;
    };

    // Release: fire ball outward proportional to charge
    if (g_suck_charge > 0.0)
    {
        g_ball_vx     = g_ball_vx + g_suck_charge * 22.0;
        g_ball_vy     = g_ball_vy * 0.4;
        g_suck_charge = 0.0;
        return;
    };

    if (!g_jetting) { return; };

    // Jet rightward - small random offset for turbulence
    g_rand_seed  = g_rand_seed * 1664525 + 1013904223;
    jitter       = (g_rand_seed & 0x7) - 3;
    jet_center   = gy + jitter;

    jet_x  = PADDLE_X + 1;
    jstart = jet_center - PADDLE_HALF_H;
    jend   = jet_center + PADDLE_HALF_H;
    if (jstart < 1)       { jstart = 1;       };
    if (jend   > SIM_H-2) { jend   = SIM_H-2; };

    for (j = jstart; j <= jend; j++)
    {
        dy   = (double)(j - jet_center);
        fall = 1.0 - (dy * dy) / (double)(PADDLE_HALF_H * PADDLE_HALF_H + 1);
        if (fall < 0.0) { fall = 0.0; };

        g_dens[IX(jet_x, j)] += fall * PADDLE_DENS;
        g_vx[IX(jet_x, j)]   += fall * PADDLE_JET_STR;
    };

    return;
};

def cpu_paddle_update() -> void
{
    int    gy, ball_gy, diff, jet_center, j, jstart, jend, jet_x, jitter;
    double dy, fall;

    // Track ball Y - convert ball screen pos to grid Y
    ball_gy = (int)(g_ball_y / (float)cur_h * (float)SIM_H);
    if (ball_gy < 0)      { ball_gy = 0;      };
    if (ball_gy > SIM_H)  { ball_gy = SIM_H;  };

    // Move CPU paddle toward ball Y, capped by CPU_SPEED
    gy   = g_cpu_paddle_gy;
    diff = ball_gy - gy;
    if (diff > (int)CPU_SPEED)           { diff = (int)CPU_SPEED;           };
    if (diff < (0 - (int)CPU_SPEED))     { diff = (0 - (int)CPU_SPEED);     };
    gy = gy + diff;

    if (gy < PADDLE_HALF_H + 1)         { gy = PADDLE_HALF_H + 1;         };
    if (gy > SIM_H - PADDLE_HALF_H - 2) { gy = SIM_H - PADDLE_HALF_H - 2; };
    g_cpu_paddle_gy = gy;

    // Small random offset on jet center each frame for turbulence
    g_rand_seed  = g_rand_seed * 1664525 + 1013904223;
    jitter       = (g_rand_seed & 0x7) - 3;   // -3..+3 grid cells
    jet_center   = gy + jitter;

    jet_x  = PADDLE_X_CPU - 1;
    jstart = jet_center - PADDLE_HALF_H;
    jend   = jet_center + PADDLE_HALF_H;
    if (jstart < 1)       { jstart = 1;       };
    if (jend   > SIM_H-2) { jend   = SIM_H-2; };

    for (j = jstart; j <= jend; j++)
    {
        dy   = (double)(j - jet_center);
        fall = 1.0 - (dy * dy) / (double)(PADDLE_HALF_H * PADDLE_HALF_H + 1);
        if (fall < 0.0) { fall = 0.0; };

        g_dens[IX(jet_x, j)] += fall * PADDLE_DENS;
        g_vx[IX(jet_x, j)]   -= fall * PADDLE_JET_STR;
    };

    return;
};

// Draw a paddle given its grid x-left edge and grid center y
// jet_side: 1 = jet face on right, -1 = jet face on left
def draw_paddle(int w, int h, int grid_x, int center_gy) -> void
{
    int   cols, rows,
          ci, ri,
          cx_px, cy_px,
          paddle_left_px, paddle_bot_px, paddle_top_px,
          paddle_w_px, paddle_h_px,
          seg, num_seg;
    float inv_w, inv_h,
          cell_w, cell_h,
          radius,
          ox, oy,
          fx, fy,
          angle, step,
          ndcx, ndcy;

    cols    = 5;
    rows    = 20;
    num_seg = 16;

    inv_w = 2.0 / (float)w;
    inv_h = 2.0 / (float)h;

    paddle_left_px = grid_x         * w / SIM_W;
    paddle_bot_px  = (center_gy - PADDLE_HALF_H) * h / SIM_H;
    paddle_top_px  = (center_gy + PADDLE_HALF_H) * h / SIM_H;
    paddle_w_px    = (grid_x + 2)   * w / SIM_W - paddle_left_px;
    paddle_h_px    = paddle_top_px - paddle_bot_px;

    cell_w  = (float)paddle_w_px / (float)cols;
    cell_h  = (float)paddle_h_px / (float)rows;
    radius  = 5.0;

    glDisable(GL_TEXTURE_2D);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE);

    step = 6.28318530718 / (float)num_seg;

    ci = 0;
    while (ci < cols)
    {
        ri = 0;
        while (ri < rows)
        {
            cx_px = paddle_left_px + (int)((float)ci * cell_w + cell_w * 0.5);
            cy_px = paddle_bot_px  + (int)((float)ri * cell_h + cell_h * 0.5);

            ndcx = (float)cx_px * inv_w - 1.0;
            ndcy = (float)cy_px * inv_h - 1.0;

            ox = radius * inv_w;
            oy = radius * inv_h;

            glBegin(GL_TRIANGLE_FAN);
            glColor4f(0.6, 0.85, 1.0, 0.2);
            glVertex2f(ndcx, ndcy);
            glColor4f(0.3, 0.6, 1.0, 0.2);
            seg = 0;
            while (seg <= num_seg)
            {
                angle = (float)seg * step;
                fx    = ndcx + ox * cos(angle);
                fy    = ndcy + oy * sin(angle);
                glVertex2f(fx, fy);
                seg++;
            };
            glEnd();

            ri++;
        };
        ci++;
    };

    glDisable(GL_BLEND);
    glEnable(GL_TEXTURE_2D);

    return;
};

// ============================================================================
// BALL
// ============================================================================

def ball_reset(int w, int h) -> void
{
    g_ball_x        = (float)w * 0.5;
    g_ball_y        = (float)h * 0.5;
    // Intrinsic starting velocity - slight rightward bias, random vertical
    g_rand_seed     = g_rand_seed * 1664525 + 1013904223;
    g_ball_vx       = 1.3;
    g_ball_vy       = ((float)((g_rand_seed & 0xFF) - 128) / 128.0) * 1.3;
    g_cpu_paddle_gy = SIM_H / 2;
    g_suck_charge   = 0.0;
    g_sucking       = false;
    return;
};

def ball_update(int w, int h) -> void
{
    int   gx, gy, gx_l, gx_r;
    float fluid_vx, fluid_vy,
          radius,
          player_face_x, cpu_face_x,
          paddle_bot_px, paddle_top_px,
          left_press, right_press, speed;

    radius = BALL_RADIUS;

    // Map ball screen position to grid coords (bottom-origin matches)
    gx = (int)(g_ball_x / (float)w * (float)SIM_W);
    gy = (int)(g_ball_y / (float)h * (float)SIM_H);

    if (gx < 1)       { gx = 1;       };
    if (gx > SIM_W-2) { gx = SIM_W-2; };
    if (gy < 1)       { gy = 1;       };
    if (gy > SIM_H-2) { gy = SIM_H-2; };

    // Sample fluid velocity at ball position and apply as force
    fluid_vx = (float)(g_vx[gy * SIM_W + gx]);
    fluid_vy = (float)(g_vy[gy * SIM_W + gx]);

    g_ball_vx = g_ball_vx + fluid_vx * BALL_FLUID_K;
    g_ball_vy = g_ball_vy + fluid_vy * BALL_FLUID_K;

    // Deadlock detection: sample fluid pressure from left and right of ball
    // If both sides are pushing hard toward center and ball is nearly stationary,
    // eject vertically with a random kick
    gx_l = gx - 4;
    gx_r = gx + 4;
    if (gx_l < 1)       { gx_l = 1;       };
    if (gx_r > SIM_W-2) { gx_r = SIM_W-2; };

    left_press  =  (float)(g_vx[gy * SIM_W + gx_l]);  // positive = pushing right
    right_press = -float(g_vx[gy * SIM_W + gx_r]);  // negative vx = pushing left

    speed = g_ball_vx * g_ball_vx + g_ball_vy * g_ball_vy;

    if (left_press > 1.5 & right_press > 1.5 & speed < 4.0)
    {
        // Opposing jets - kick ball up or down based on random seed
        g_rand_seed  = g_rand_seed * 1664525 + 1013904223;
        if ((g_rand_seed & 1) == 0)
        {
            g_ball_vy = g_ball_vy + 5.5;
        }
        else
        {
            g_ball_vy = g_ball_vy - 5.5;
        };
    };

    // Drag
    g_ball_vx = g_ball_vx * BALL_DRAG;
    g_ball_vy = g_ball_vy * BALL_DRAG;

    // Integrate
    g_ball_x = g_ball_x + g_ball_vx;
    g_ball_y = g_ball_y + g_ball_vy;

    // Player paddle right face (jet side) collision
    player_face_x = (float)((PADDLE_X + 2) * w / SIM_W);
    paddle_bot_px = (float)((g_paddle_gy - PADDLE_HALF_H) * h / SIM_H);
    paddle_top_px = (float)((g_paddle_gy + PADDLE_HALF_H) * h / SIM_H);

    if (g_ball_x - radius < player_face_x &
        g_ball_x + radius > player_face_x - 4.0 &
        g_ball_y > paddle_bot_px &
        g_ball_y < paddle_top_px)
    {
        g_ball_x  = player_face_x + radius;
        g_ball_vx = g_ball_vx * (0.0 - BALL_BOUNCE);
    };

    // CPU paddle left face collision
    cpu_face_x    = (float)(PADDLE_X_CPU * w / SIM_W);
    paddle_bot_px = (float)((g_cpu_paddle_gy - PADDLE_HALF_H) * h / SIM_H);
    paddle_top_px = (float)((g_cpu_paddle_gy + PADDLE_HALF_H) * h / SIM_H);

    if (g_ball_x + radius > cpu_face_x &
        g_ball_x - radius < cpu_face_x + 4.0 &
        g_ball_y > paddle_bot_px &
        g_ball_y < paddle_top_px)
    {
        g_ball_x  = cpu_face_x - radius;
        g_ball_vx = g_ball_vx * (0.0 - BALL_BOUNCE);
    };

    // Top / bottom wall bounce
    if (g_ball_y - radius < 0.0)
    {
        g_ball_y  = radius;
        g_ball_vy = g_ball_vy * (0.0 - BALL_BOUNCE);
    };
    if (g_ball_y + radius > (float)h)
    {
        g_ball_y  = (float)h - radius;
        g_ball_vy = g_ball_vy * (0.0 - BALL_BOUNCE);
    };

    // Left wall - player loses a life
    if (g_ball_x - radius < 0.0)
    {
        g_lives = g_lives - 1;
        if (g_lives < 1)
        {
            g_lives      = 3;
            g_level      = 1;
            g_game_state = 0;
        };
        ball_reset(w, h);
        return;
    };

    // Right wall - player wins the round, level up
    if (g_ball_x + radius > (float)w)
    {
        g_level = g_level + 1;
        ball_reset(w, h);
        return;
    };

    return;
};

def draw_ball(int w, int h) -> void
{
    int   seg, num_seg;
    float inv_w, inv_h,
          ndcx, ndcy,
          ox, oy,
          box, boy,
          angle, step_b,
          fx, fy,
          radius, border;

    num_seg = 32;
    radius  = BALL_RADIUS;
    border  = 4.0;
    inv_w   = 2.0 / (float)w;
    inv_h   = 2.0 / (float)h;

    ndcx = g_ball_x * inv_w - 1.0;
    ndcy = g_ball_y * inv_h - 1.0;

    // Outer radius (ball + border) in NDC
    ox = (radius + border) * inv_w;
    oy = (radius + border) * inv_h;

    // Inner radius (black fill) in NDC
    box = radius * inv_w;
    boy = radius * inv_h;

    step_b = 6.28318530718 / (float)num_seg;

    glDisable(GL_TEXTURE_2D);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);

    // White border circle (drawn first, slightly larger)
    glBegin(GL_TRIANGLE_FAN);
    glColor3f(1.0, 1.0, 1.0);
    glVertex2f(ndcx, ndcy);
    seg = 0;
    while (seg <= num_seg)
    {
        angle = (float)seg * step_b;
        fx    = ndcx + ox * cos(angle);
        fy    = ndcy + oy * sin(angle);
        glVertex2f(fx, fy);
        seg++;
    };
    glEnd();

    // Black fill circle (drawn on top, radius only)
    glBegin(GL_TRIANGLE_FAN);
    glColor3f(0.0, 0.0, 0.0);
    glVertex2f(ndcx, ndcy);
    seg = 0;
    while (seg <= num_seg)
    {
        angle = (float)seg * step_b;
        fx    = ndcx + box * cos(angle);
        fy    = ndcy + boy * sin(angle);
        glVertex2f(fx, fy);
        seg++;
    };
    glEnd();

    glEnable(GL_TEXTURE_2D);

    return;
};

// ============================================================================
// HUD - lives and level display
// ============================================================================

// Write decimal integer into buf, returns character count, null terminates
def int_to_str(int val, byte* buf) -> int
{
    int  tmp, count, i, j, len;
    byte ch, t;

    if (val < 0) { val = 0; };
    if (val == 0)
    {
        buf[0] = 48;   // '0'
        buf[1] = 0;
        return 1;
    };

    // Write digits in reverse
    len = 0;
    tmp = val;
    while (tmp > 0)
    {
        buf[len] = (byte)(48 + (tmp % 10));
        tmp      = tmp / 10;
        len++;
    };
    buf[len] = 0;

    // Reverse in place
    i = 0;
    j = len - 1;
    while (i < j)
    {
        t       = buf[i];
        buf[i]  = buf[j];
        buf[j]  = t;
        i++;
        j--;
    };

    return len;
};

def draw_hud(int w, int h) -> void
{
    int   scale, tx, ty, tw, lv, li,
          hx, hy, hs;
    float inv_w, inv_h,
          fx0, fy0, fx1, fy1,
          fxm, fyt;
    byte[16] num_buf;

    scale = 2;
    inv_w = 2.0 / (float)w;
    inv_h = 2.0 / (float)h;

    glDisable(GL_TEXTURE_2D);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    // ---- LEVEL (top center) ----
    // Label "LEVEL" then number, centered at top
    int_to_str(g_level, @num_buf[0]);
    tw = text_width("LEVEL \0", scale) + text_width(@num_buf[0], scale);
    tx = w / 2 - tw / 2;
    ty = h - 28;   // near top in bottom-origin coords

    glColor4f(0.6, 0.8, 1.0, 0.9);
    draw_text("LEVEL \0", tx, ty, scale, inv_w, inv_h);
    tx = tx + text_width("LEVEL \0", scale);
    glColor4f(1.0, 1.0, 1.0, 1.0);
    draw_text(@num_buf[0], tx, ty, scale, inv_w, inv_h);

    // ---- LIVES (top left) ----
    // Draw heart diamonds then "LIVES" label
    hs = 7;   // half-size of diamond in pixels

    glColor4f(1.0, 0.28, 0.28, 0.95);

    li = 0;
    while (li < g_lives)
    {
        hx = 20 + li * (hs * 2 + 6);
        hy = h - 22;   // bottom-origin y near top

        // Diamond: 4 triangles from center
        fxm = (float)hx * inv_w - 1.0;
        fyt = (float)hy * inv_h - 1.0;
        fx0 = (float)(hx - hs) * inv_w - 1.0;
        fx1 = (float)(hx + hs) * inv_w - 1.0;
        fy0 = (float)(hy - hs) * inv_h - 1.0;
        fy1 = (float)(hy + hs) * inv_h - 1.0;

        glBegin(GL_QUADS);
        glVertex2f(fxm, fy1);   // top
        glVertex2f(fx1, fyt);   // right
        glVertex2f(fxm, fy0);   // bottom
        glVertex2f(fx0, fyt);   // left
        glEnd();

        li++;
    };

    // Draw empty outlines for lost lives
    glColor4f(0.5, 0.15, 0.15, 0.6);
    lv = 3;
    while (li < lv)
    {
        hx = 20 + li * (hs * 2 + 6);
        hy = h - 22;

        fxm = (float)hx * inv_w - 1.0;
        fyt = (float)hy * inv_h - 1.0;
        fx0 = (float)(hx - hs) * inv_w - 1.0;
        fx1 = (float)(hx + hs) * inv_w - 1.0;
        fy0 = (float)(hy - hs) * inv_h - 1.0;
        fy1 = (float)(hy + hs) * inv_h - 1.0;

        glLineWidth(1.0);
        glBegin(GL_LINE_LOOP);
        glVertex2f(fxm, fy1);
        glVertex2f(fx1, fyt);
        glVertex2f(fxm, fy0);
        glVertex2f(fx0, fyt);
        glEnd();

        li++;
    };

    // "LIVES" label under diamonds
    glColor4f(0.6, 0.8, 1.0, 0.7);
    ty = h - 44;
    draw_text("LIVES\0", 8, ty, scale, inv_w, inv_h);

    glDisable(GL_BLEND);
    glEnable(GL_TEXTURE_2D);

    return;
};

byte[] VERT_SRC = "#version 120
void main() {
    gl_TexCoord[0] = gl_MultiTexCoord0;
    gl_Position    = gl_Vertex;
}
\0";

byte[] FRAG_SRC = "#version 120
uniform sampler2D u_dens;
uniform sampler2D u_vel;
uniform vec2      u_res;
uniform int       u_palette;

void main() {
    vec2 uv = gl_TexCoord[0].xy;

    float d  = texture2D(u_dens, uv).r;
    vec2  v  = texture2D(u_vel,  uv).ra - 0.5;
    float vm = length(v) * 2.0;
    float t  = clamp(d, 0.0, 1.0);

    // Wide bloom - 8-tap gather at two radii
    vec2  px   = 1.0 / u_res;
    float blur = 0.0;
    blur += texture2D(u_dens, uv + vec2(-px.x,       0.0      )).r;
    blur += texture2D(u_dens, uv + vec2( px.x,       0.0      )).r;
    blur += texture2D(u_dens, uv + vec2( 0.0,       -px.y     )).r;
    blur += texture2D(u_dens, uv + vec2( 0.0,        px.y     )).r;
    blur += texture2D(u_dens, uv + vec2(-px.x*2.5,  -px.y*2.5 )).r;
    blur += texture2D(u_dens, uv + vec2( px.x*2.5,  -px.y*2.5 )).r;
    blur += texture2D(u_dens, uv + vec2(-px.x*2.5,   px.y*2.5 )).r;
    blur += texture2D(u_dens, uv + vec2( px.x*2.5,   px.y*2.5 )).r;
    blur *= 0.125;
    float glow = clamp(blur * 3.0 + vm * t * 0.5, 0.0, 1.0);

    vec3 col = vec3(0.0);

    // 1: Classic plasma - blue/cyan/magenta
    if (u_palette == 0) {
        col.r = 0.5 - 0.5 * cos(3.14159 * (t * 1.2 + 0.0));
        col.g = 0.5 - 0.5 * cos(3.14159 * (t * 1.2 + 0.4));
        col.b = 0.5 - 0.5 * cos(3.14159 * (t * 1.2 + 0.8));
    }
    // 2: Fire - black -> red -> orange -> yellow
    else if (u_palette == 1) {
        col.r = clamp(t * 3.0,       0.0, 1.0);
        col.g = clamp(t * 3.0 - 1.0, 0.0, 1.0);
        col.b = clamp(t * 3.0 - 2.0, 0.0, 1.0);
    }
    // 3: Toxic - green/yellow-green
    else if (u_palette == 2) {
        col.r = 0.5 - 0.5 * cos(3.14159 * (t * 1.2 + 0.9));
        col.g = 0.5 - 0.5 * cos(3.14159 * (t * 1.2 + 0.3));
        col.b = 0.5 - 0.5 * cos(3.14159 * (t * 1.2 + 1.3));
    }
    // 4: Ice - deep blue -> cyan -> white
    else if (u_palette == 3) {
        col.r = 0.5 - 0.5 * cos(3.14159 * (t * 1.0 + 1.0));
        col.g = 0.5 - 0.5 * cos(3.14159 * (t * 1.0 + 0.6));
        col.b = 0.5 - 0.5 * cos(3.14159 * (t * 1.0 + 0.1));
    }
    // 5: Sunset - purple -> magenta -> orange
    else if (u_palette == 4) {
        col.r = 0.5 - 0.5 * cos(3.14159 * (t * 1.1 + 0.1));
        col.g = 0.5 - 0.5 * cos(3.14159 * (t * 1.1 + 0.9));
        col.b = 0.5 - 0.5 * cos(3.14159 * (t * 1.1 + 0.5));
    }
    // 6: Deep ocean - navy -> teal -> seafoam
    else if (u_palette == 5) {
        col.r = 0.5 - 0.5 * cos(3.14159 * (t * 1.3 + 1.2));
        col.g = 0.5 - 0.5 * cos(3.14159 * (t * 1.3 + 0.7));
        col.b = 0.5 - 0.5 * cos(3.14159 * (t * 1.3 + 0.2));
    }
    // 7: Neon - hot pink -> purple -> electric blue
    else if (u_palette == 6) {
        col.r = 0.5 - 0.5 * cos(3.14159 * (t * 1.4 + 0.2));
        col.g = 0.5 - 0.5 * cos(3.14159 * (t * 1.4 + 1.1));
        col.b = 0.5 - 0.5 * cos(3.14159 * (t * 1.4 + 0.6));
    }
    // 8: Gold - brown -> gold -> bright yellow
    else if (u_palette == 7) {
        col.r = clamp(t * 2.5,       0.0, 1.0);
        col.g = clamp(t * 2.5 - 0.4, 0.0, 1.0);
        col.b = clamp(t * 3.0 - 2.2, 0.0, 0.3);
    }
    // 9: Monochrome - white core with soft halo
    else if (u_palette == 8) {
        float lum = t * t * 2.0;
        col = vec3(clamp(lum, 0.0, 1.0));
    }
    // 0: Rainbow - full hue cycle across density
    else {
        float h = t * 6.0;
        float f = clamp(h - floor(h), 0.0, 1.0);
        if      (h < 1.0) { col = vec3(1.0,     f,       0.0     ); }
        else if (h < 2.0) { col = vec3(1.0-f,   1.0,     0.0     ); }
        else if (h < 3.0) { col = vec3(0.0,     1.0,     f       ); }
        else if (h < 4.0) { col = vec3(0.0,     1.0-f,   1.0     ); }
        else if (h < 5.0) { col = vec3(f,       0.0,     1.0     ); }
        else              { col = vec3(1.0,     0.0,     1.0-f   ); }
        col *= t;
    }

    // Saturation boost
    float grey = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(grey), col, 1.8);

    // Additive glow halo
    col += col * glow * 1.4;

    // Velocity shimmer
    col += vec3(0.08, 0.2, 0.4) * vm * d * 0.6;

    col *= t;
    float alpha = clamp(t * 8.0, 0.0, 1.0);
    gl_FragColor = vec4(col, alpha);
}
\0";

// ============================================================================
// SYSTEM_INFO for core count
// ============================================================================

struct SYSTEM_INFO_PARTIAL
{
    u32   dwOemId,
          dwPageSize;
    void* lpMin,
          lpMax;
    u64   dwActiveProcessorMask;
    u32   dwNumberOfProcessors,
          dwProcessorType,
          dwAllocationGranularity;
    u16   wProcessorLevel,
          wProcessorRevision;
};

// ============================================================================
// GUI - Plasma Pong style parallelogram buttons + 5x7 pixel font
// ============================================================================

// All buttons use the same half-width/half-height as the main button for hit testing
def btn_hit_test(int mx, int my, int cx, int cy) -> bool
{
    int   half_w, half_h, local_y, x_offset, local_x;
    float fy;

    half_w  = BTN_W / 2;
    half_h  = BTN_H / 2;
    local_y = my - cy;

    if (local_y < (0 - half_h) | local_y > half_h) { return false; };

    fy       = (float)(local_y + half_h) / (float)BTN_H;
    x_offset = (int)((fy - 0.5) * (float)(BTN_SLANT * 2));
    local_x  = mx - cx - x_offset;

    if (local_x < (0 - half_w) | local_x > half_w) { return false; };

    return true;
};

// Parametric hit test for buttons with custom half-extents and slant
def btn_hit_test_ex(int mx, int my, int cx, int cy, int half_w, int half_h) -> bool
{
    int   local_y, x_offset, local_x, slant;
    float fy;

    slant   = BTN_SLANT / 2;
    local_y = my - cy;

    if (local_y < (0 - half_h) | local_y > half_h) { return false; };

    fy       = (float)(local_y + half_h) / (float)(half_h * 2);
    x_offset = (int)((fy - 0.5) * (float)(slant * 2));
    local_x  = mx - cx - x_offset;

    if (local_x < (0 - half_w) | local_x > half_w) { return false; };

    return true;
};

// 5x7 bitmap font - each character is 5 u32 columns, rows packed LSB=top
// Characters: space(32) through Z(90) - indices 0..58
// Each column is a 7-bit mask, bit 0 = top row, bit 6 = bottom row
u32[5] FONT_SPACE   = [0x00, 0x00, 0x00, 0x00, 0x00];
u32[5] FONT_EXCL    = [0x00, 0x00, 0x5F, 0x00, 0x00];
u32[5] FONT_QUOT    = [0x00, 0x07, 0x00, 0x07, 0x00];
u32[5] FONT_HASH    = [0x14, 0x7F, 0x14, 0x7F, 0x14];
u32[5] FONT_DOLL    = [0x24, 0x2A, 0x7F, 0x2A, 0x12];
u32[5] FONT_PERC    = [0x23, 0x13, 0x08, 0x64, 0x62];
u32[5] FONT_AMP     = [0x36, 0x49, 0x55, 0x22, 0x50];
u32[5] FONT_APOS    = [0x00, 0x05, 0x03, 0x00, 0x00];
u32[5] FONT_LPAREN  = [0x00, 0x1C, 0x22, 0x41, 0x00];
u32[5] FONT_RPAREN  = [0x00, 0x41, 0x22, 0x1C, 0x00];
u32[5] FONT_STAR    = [0x14, 0x08, 0x3E, 0x08, 0x14];
u32[5] FONT_PLUS    = [0x08, 0x08, 0x3E, 0x08, 0x08];
u32[5] FONT_COMMA   = [0x00, 0x50, 0x30, 0x00, 0x00];
u32[5] FONT_MINUS   = [0x08, 0x08, 0x08, 0x08, 0x08];
u32[5] FONT_PERIOD  = [0x00, 0x60, 0x60, 0x00, 0x00];
u32[5] FONT_SLASH   = [0x20, 0x10, 0x08, 0x04, 0x02];
u32[5] FONT_0       = [0x3E, 0x51, 0x49, 0x45, 0x3E];
u32[5] FONT_1       = [0x00, 0x42, 0x7F, 0x40, 0x00];
u32[5] FONT_2       = [0x42, 0x61, 0x51, 0x49, 0x46];
u32[5] FONT_3       = [0x21, 0x41, 0x45, 0x4B, 0x31];
u32[5] FONT_4       = [0x18, 0x14, 0x12, 0x7F, 0x10];
u32[5] FONT_5       = [0x27, 0x45, 0x45, 0x45, 0x39];
u32[5] FONT_6       = [0x3C, 0x4A, 0x49, 0x49, 0x30];
u32[5] FONT_7       = [0x01, 0x71, 0x09, 0x05, 0x03];
u32[5] FONT_8       = [0x36, 0x49, 0x49, 0x49, 0x36];
u32[5] FONT_9       = [0x06, 0x49, 0x49, 0x29, 0x1E];
u32[5] FONT_COLON   = [0x00, 0x36, 0x36, 0x00, 0x00];
u32[5] FONT_SEMIC   = [0x00, 0x56, 0x36, 0x00, 0x00];
u32[5] FONT_LT      = [0x08, 0x14, 0x22, 0x41, 0x00];
u32[5] FONT_EQ      = [0x14, 0x14, 0x14, 0x14, 0x14];
u32[5] FONT_GT      = [0x00, 0x41, 0x22, 0x14, 0x08];
u32[5] FONT_QUEST   = [0x02, 0x01, 0x51, 0x09, 0x06];
u32[5] FONT_AT      = [0x32, 0x49, 0x79, 0x41, 0x3E];
u32[5] FONT_A       = [0x7E, 0x11, 0x11, 0x11, 0x7E];
u32[5] FONT_B       = [0x7F, 0x49, 0x49, 0x49, 0x36];
u32[5] FONT_C       = [0x3E, 0x41, 0x41, 0x41, 0x22];
u32[5] FONT_D       = [0x7F, 0x41, 0x41, 0x22, 0x1C];
u32[5] FONT_E       = [0x7F, 0x49, 0x49, 0x49, 0x41];
u32[5] FONT_F       = [0x7F, 0x09, 0x09, 0x09, 0x01];
u32[5] FONT_G       = [0x3E, 0x41, 0x49, 0x49, 0x7A];
u32[5] FONT_H       = [0x7F, 0x08, 0x08, 0x08, 0x7F];
u32[5] FONT_I       = [0x00, 0x41, 0x7F, 0x41, 0x00];
u32[5] FONT_J       = [0x20, 0x40, 0x41, 0x3F, 0x01];
u32[5] FONT_K       = [0x7F, 0x08, 0x14, 0x22, 0x41];
u32[5] FONT_L       = [0x7F, 0x40, 0x40, 0x40, 0x40];
u32[5] FONT_M       = [0x7F, 0x02, 0x0C, 0x02, 0x7F];
u32[5] FONT_N       = [0x7F, 0x04, 0x08, 0x10, 0x7F];
u32[5] FONT_O       = [0x3E, 0x41, 0x41, 0x41, 0x3E];
u32[5] FONT_P       = [0x7F, 0x09, 0x09, 0x09, 0x06];
u32[5] FONT_Q       = [0x3E, 0x41, 0x51, 0x21, 0x5E];
u32[5] FONT_R       = [0x7F, 0x09, 0x19, 0x29, 0x46];
u32[5] FONT_S       = [0x46, 0x49, 0x49, 0x49, 0x31];
u32[5] FONT_T       = [0x01, 0x01, 0x7F, 0x01, 0x01];
u32[5] FONT_U       = [0x3F, 0x40, 0x40, 0x40, 0x3F];
u32[5] FONT_V       = [0x1F, 0x20, 0x40, 0x20, 0x1F];
u32[5] FONT_W       = [0x3F, 0x40, 0x38, 0x40, 0x3F];
u32[5] FONT_X       = [0x63, 0x14, 0x08, 0x14, 0x63];
u32[5] FONT_Y       = [0x07, 0x08, 0x70, 0x08, 0x07];
u32[5] FONT_Z       = [0x61, 0x51, 0x49, 0x45, 0x43];

// Lookup: map ASCII code to font data pointer
// Returns pointer to 5-u32 column array for a given character
def font_glyph(int c) -> u32*
{
    if (c == 32)  { return @FONT_SPACE[0];  };
    if (c == 33)  { return @FONT_EXCL[0];   };
    if (c == 34)  { return @FONT_QUOT[0];   };
    if (c == 35)  { return @FONT_HASH[0];   };
    if (c == 36)  { return @FONT_DOLL[0];   };
    if (c == 37)  { return @FONT_PERC[0];   };
    if (c == 38)  { return @FONT_AMP[0];    };
    if (c == 39)  { return @FONT_APOS[0];   };
    if (c == 40)  { return @FONT_LPAREN[0]; };
    if (c == 41)  { return @FONT_RPAREN[0]; };
    if (c == 42)  { return @FONT_STAR[0];   };
    if (c == 43)  { return @FONT_PLUS[0];   };
    if (c == 44)  { return @FONT_COMMA[0];  };
    if (c == 45)  { return @FONT_MINUS[0];  };
    if (c == 46)  { return @FONT_PERIOD[0]; };
    if (c == 47)  { return @FONT_SLASH[0];  };
    if (c == 48)  { return @FONT_0[0];      };
    if (c == 49)  { return @FONT_1[0];      };
    if (c == 50)  { return @FONT_2[0];      };
    if (c == 51)  { return @FONT_3[0];      };
    if (c == 52)  { return @FONT_4[0];      };
    if (c == 53)  { return @FONT_5[0];      };
    if (c == 54)  { return @FONT_6[0];      };
    if (c == 55)  { return @FONT_7[0];      };
    if (c == 56)  { return @FONT_8[0];      };
    if (c == 57)  { return @FONT_9[0];      };
    if (c == 58)  { return @FONT_COLON[0];  };
    if (c == 59)  { return @FONT_SEMIC[0];  };
    if (c == 60)  { return @FONT_LT[0];     };
    if (c == 61)  { return @FONT_EQ[0];     };
    if (c == 62)  { return @FONT_GT[0];     };
    if (c == 63)  { return @FONT_QUEST[0];  };
    if (c == 64)  { return @FONT_AT[0];     };
    if (c == 65)  { return @FONT_A[0];      };
    if (c == 66)  { return @FONT_B[0];      };
    if (c == 67)  { return @FONT_C[0];      };
    if (c == 68)  { return @FONT_D[0];      };
    if (c == 69)  { return @FONT_E[0];      };
    if (c == 70)  { return @FONT_F[0];      };
    if (c == 71)  { return @FONT_G[0];      };
    if (c == 72)  { return @FONT_H[0];      };
    if (c == 73)  { return @FONT_I[0];      };
    if (c == 74)  { return @FONT_J[0];      };
    if (c == 75)  { return @FONT_K[0];      };
    if (c == 76)  { return @FONT_L[0];      };
    if (c == 77)  { return @FONT_M[0];      };
    if (c == 78)  { return @FONT_N[0];      };
    if (c == 79)  { return @FONT_O[0];      };
    if (c == 80)  { return @FONT_P[0];      };
    if (c == 81)  { return @FONT_Q[0];      };
    if (c == 82)  { return @FONT_R[0];      };
    if (c == 83)  { return @FONT_S[0];      };
    if (c == 84)  { return @FONT_T[0];      };
    if (c == 85)  { return @FONT_U[0];      };
    if (c == 86)  { return @FONT_V[0];      };
    if (c == 87)  { return @FONT_W[0];      };
    if (c == 88)  { return @FONT_X[0];      };
    if (c == 89)  { return @FONT_Y[0];      };
    if (c == 90)  { return @FONT_Z[0];      };
    return @FONT_SPACE[0];
};

// Draw a null-terminated uppercase ASCII string as pixel quads
// px, py = top-left pixel origin of text; scale = pixel size of each font dot
// inv_w, inv_h = 2.0/screen_w and 2.0/screen_h for NDC conversion
def draw_text(byte* str, int px, int py, int scale, float inv_w, float inv_h) -> void
{
    int   ci,       // character index in string
          cx,       // current x pixel cursor
          col,      // column within glyph (0..4)
          row,      // row within glyph (0..6)
          mask,
          qx0, qy0,
          qx1, qy1,
          c;
    u32*  glyph;
    float fx0, fy0, fx1, fy1;

    ci = 0;
    cx = px;

    glBegin(GL_QUADS);

    while (true)
    {
        c = (int)str[ci];
        if (c == 0) { break; };

        // Uppercase fold
        if (c >= 97 & c <= 122) { c = c - 32; };

        glyph = font_glyph(c);

        col = 0;
        while (col < 5)
        {
            mask = (int)glyph[col];
            row  = 0;
            while (row < 7)
            {
                if (mask & (1 << row))
                {
                    qx0 = cx + col * scale;
                    qy0 = py + (6 - row) * scale;
                    qx1 = qx0 + scale;
                    qy1 = qy0 + scale;

                    fx0 = (float)qx0 * inv_w - 1.0;
                    fy0 = (float)qy0 * inv_h - 1.0;
                    fx1 = (float)qx1 * inv_w - 1.0;
                    fy1 = (float)qy1 * inv_h - 1.0;

                    glVertex2f(fx0, fy0);
                    glVertex2f(fx1, fy0);
                    glVertex2f(fx1, fy1);
                    glVertex2f(fx0, fy1);
                };
                row++;
            };
            col++;
        };

        cx  = cx + (5 + 1) * scale;  // 5 columns + 1 gap
        ci++;
    };

    glEnd();
    return;
};

// Measure text width in pixels for centering
def text_width(byte* str, int scale) -> int
{
    int ci, c, count;
    ci    = 0;
    count = 0;
    while (true)
    {
        c = (int)str[ci];
        if (c == 0) { break; };
        count++;
        ci++;
    };
    // Each char: 5 columns + 1 gap, last char has no trailing gap
    if (count == 0) { return 0; };
    return count * 6 * scale - scale;
};

// Draw a parallelogram button at pixel center (cx, cy) with given half-width and half-height
// highlight = 1 draws with a lighter fill (hover/active feel for dialog boxes)
def draw_parallelogram_btn(int cx, int cy, int half_w, int half_h, int slant, float inv_w, float inv_h) -> void
{
    int   bx0, bx1, tx0, tx1, by0, ty0;
    float ny_bot, ny_top;

    bx0 = cx - half_w - slant;
    bx1 = cx + half_w - slant;
    tx0 = cx - half_w + slant;
    tx1 = cx + half_w + slant;
    by0 = cy - half_h;
    ty0 = cy + half_h;

    ny_bot = (float)by0 * inv_h - 1.0;
    ny_top = (float)ty0 * inv_h - 1.0;

    // Drop shadow
    glBegin(GL_QUADS);
    glColor4f(0.0, 0.0, 0.0, 0.5);
    glVertex2f((float)bx0 * inv_w - 1.0 + 0.006, ny_bot - 0.01);
    glVertex2f((float)bx1 * inv_w - 1.0 + 0.006, ny_bot - 0.01);
    glVertex2f((float)tx1 * inv_w - 1.0 + 0.006, ny_top - 0.01);
    glVertex2f((float)tx0 * inv_w - 1.0 + 0.006, ny_top - 0.01);
    glEnd();

    // Fill - gradient dark navy bottom to slightly lighter top
    glBegin(GL_QUADS);
    glColor4f(0.04, 0.07, 0.18, 0.92);
    glVertex2f((float)bx0 * inv_w - 1.0, ny_bot);
    glColor4f(0.04, 0.07, 0.18, 0.92);
    glVertex2f((float)bx1 * inv_w - 1.0, ny_bot);
    glColor4f(0.08, 0.14, 0.34, 0.92);
    glVertex2f((float)tx1 * inv_w - 1.0, ny_top);
    glColor4f(0.08, 0.14, 0.34, 0.92);
    glVertex2f((float)tx0 * inv_w - 1.0, ny_top);
    glEnd();

    // Top highlight bevel
    glLineWidth(1.5);
    glBegin(GL_LINES);
    glColor4f(0.4, 0.7, 1.0, 0.8);
    glVertex2f((float)tx0 * inv_w - 1.0, ny_top);
    glVertex2f((float)tx1 * inv_w - 1.0, ny_top);
    glEnd();

    // Bottom shadow line
    glBegin(GL_LINES);
    glColor4f(0.0, 0.05, 0.15, 0.9);
    glVertex2f((float)bx0 * inv_w - 1.0, ny_bot);
    glVertex2f((float)bx1 * inv_w - 1.0, ny_bot);
    glEnd();

    // Outer border
    glLineWidth(1.8);
    glBegin(GL_LINE_LOOP);
    glColor4f(0.25, 0.55, 1.0, 0.95);
    glVertex2f((float)bx0 * inv_w - 1.0, ny_bot);
    glVertex2f((float)bx1 * inv_w - 1.0, ny_bot);
    glVertex2f((float)tx1 * inv_w - 1.0, ny_top);
    glVertex2f((float)tx0 * inv_w - 1.0, ny_top);
    glEnd();

    return;
};

def draw_gui(int w, int h) -> void
{
    int   cx, cy, tw, tx, ty, scale;
    float inv_w, inv_h;
    byte* labelx;

    inv_w = 2.0 / (float)w;
    inv_h = 2.0 / (float)h;
    cx    = w / 2;
    cy    = h / 2;
    scale = 2;

    glDisable(GL_TEXTURE_2D);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    // Start Game button
    draw_parallelogram_btn(cx, cy, BTN_W / 2, BTN_H / 2, BTN_SLANT, inv_w, inv_h);

    // Button labelx - centered inside button
    labelx = "START GAME\0";
    tw    = text_width(labelx, scale);
    tx    = cx - tw / 2;
    // Bottom-origin coords: center text vertically around cy
    ty    = cy - (7 * scale) / 2;
    glColor4f(0.75, 0.88, 1.0, 1.0);
    draw_text(labelx, tx, ty, scale, inv_w, inv_h);

    glDisable(GL_BLEND);
    glEnable(GL_TEXTURE_2D);

    return;
};

def draw_quit_dialog(int w, int h) -> void
{
    int   cx, cy,
          panel_w, panel_h,
          px0, py0, px1, py1,
          tw, tx, ty, scale;
    float inv_w, inv_h,
          fx0, fy0, fx1, fy1;
    byte* msg_str;
    byte* yes_str;
    byte* no_str;

    inv_w   = 2.0 / (float)w;
    inv_h   = 2.0 / (float)h;
    cx      = w / 2;
    cy      = h / 2;
    panel_w = 420;
    panel_h = 160;
    scale   = 2;

    px0 = cx - panel_w / 2;
    py0 = cy - panel_h / 2;
    px1 = cx + panel_w / 2;
    py1 = cy + panel_h / 2;

    glDisable(GL_TEXTURE_2D);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    // Dark panel fill
    fx0 = (float)px0 * inv_w - 1.0;
    fy0 = (float)py0 * inv_h - 1.0;
    fx1 = (float)px1 * inv_w - 1.0;
    fy1 = (float)py1 * inv_h - 1.0;

    glBegin(GL_QUADS);
    glColor4f(0.02, 0.04, 0.12, 0.96);
    glVertex2f(fx0, fy0);
    glVertex2f(fx1, fy0);
    glVertex2f(fx1, fy1);
    glVertex2f(fx0, fy1);
    glEnd();

    // Panel border
    glLineWidth(1.8);
    glBegin(GL_LINE_LOOP);
    glColor4f(0.25, 0.55, 1.0, 0.95);
    glVertex2f(fx0, fy0);
    glVertex2f(fx1, fy0);
    glVertex2f(fx1, fy1);
    glVertex2f(fx0, fy1);
    glEnd();

    // Top highlight line on panel
    glLineWidth(1.0);
    glBegin(GL_LINES);
    glColor4f(0.4, 0.7, 1.0, 0.6);
    glVertex2f(fx0, fy1);
    glVertex2f(fx1, fy1);
    glEnd();

    // Message text - "ARE YOU SURE YOU WANT TO QUIT?"
    msg_str = "ARE YOU SURE YOU WANT TO QUIT?\0";
    tw      = text_width(msg_str, scale);
    tx      = cx - tw / 2;
    // Upper portion of panel in bottom-origin coords
    ty      = cy + panel_h / 2 - 36;
    glColor4f(0.85, 0.92, 1.0, 1.0);
    draw_text(msg_str, tx, ty, scale, inv_w, inv_h);

    // Yes button - left of center, lower portion of panel
    yes_str = "YES\0";
    draw_parallelogram_btn(cx - 80, cy - 50, BTN_W / 4, BTN_H / 2, BTN_SLANT / 2, inv_w, inv_h);
    tw = text_width(yes_str, scale);
    tx = (cx - 80) - tw / 2;
    ty = (cy - 50) - (7 * scale) / 2;
    glColor4f(0.75, 0.88, 1.0, 1.0);
    draw_text(yes_str, tx, ty, scale, inv_w, inv_h);

    // No button - right of center, lower portion of panel
    no_str = "NO\0";
    draw_parallelogram_btn(cx + 80, cy - 50, BTN_W / 4, BTN_H / 2, BTN_SLANT / 2, inv_w, inv_h);
    tw = text_width(no_str, scale);
    tx = (cx + 80) - tw / 2;
    ty = (cy - 50) - (7 * scale) / 2;
    glColor4f(0.75, 0.88, 1.0, 1.0);
    draw_text(no_str, tx, ty, scale, inv_w, inv_h);

    glDisable(GL_BLEND);
    glEnable(GL_TEXTURE_2D);

    return;
};


def main() -> int
{
    size_t field_bytes, dens_tex_bytes, vel_tex_bytes;
    HINSTANCE hInstance;
    HWND hwnd;
    HDC  hdc;
    MSG  msg;
    bool running;
    int  tex_dens,
         tex_vel,
         vert_sh,
         frag_sh,
         prog,
         u_dens,
         u_vel, u_res,
         u_palette,
         t, i, seg;
    float px, py,
          ndcx, ndcy,
          pr, ox, oy,
          angle, step_a,
          dens_val, fx, fy;
    RECT client_rect;
    SYSTEM_INFO_PARTIAL sysinfo;

    GetSystemInfo((void*)@sysinfo);
    g_num_threads = (int)sysinfo.dwNumberOfProcessors;
    if (g_num_threads < 1)           { g_num_threads = 1;           };
    if (g_num_threads > MAX_THREADS) { g_num_threads = MAX_THREADS; };

    field_bytes    = (size_t)(SIM_W * SIM_H * 8);
    dens_tex_bytes = (size_t)(SIM_W * SIM_H * 4);        // 1 float per cell
    vel_tex_bytes  = (size_t)(SIM_W * SIM_H * 4 * 2);    // 2 floats per cell

    g_dens      = (double*)fmalloc(field_bytes);
    g_dens_prev = (double*)fmalloc(field_bytes);
    g_vx        = (double*)fmalloc(field_bytes);
    g_vy        = (double*)fmalloc(field_bytes);
    g_vx_prev   = (double*)fmalloc(field_bytes);
    g_vy_prev   = (double*)fmalloc(field_bytes);
    g_dens_tex  = (float*)fmalloc(dens_tex_bytes);
    g_vel_tex   = (float*)fmalloc(vel_tex_bytes);
    g_part_x    = (float*)fmalloc((size_t)(MAX_PARTICLES * 4));
    g_part_y    = (float*)fmalloc((size_t)(MAX_PARTICLES * 4));
    defer ffree((u64)g_dens);
    defer ffree((u64)g_dens_prev);
    defer ffree((u64)g_vx);
    defer ffree((u64)g_vy);
    defer ffree((u64)g_vx_prev);
    defer ffree((u64)g_vy_prev);
    defer ffree((u64)g_dens_tex);
    defer ffree((u64)g_vel_tex);
    defer ffree((u64)g_part_x);
    defer ffree((u64)g_part_y);

    particles_init();

    semaphore_init(@g_work_sem, 0);
    semaphore_init(@g_done_sem, 0);
    semaphore_init(@g_work_sem2, 0);
    semaphore_init(@g_done_sem2, 0);

    g_rows_per_thread = SIM_H / g_num_threads;
    if (g_rows_per_thread < 1) { g_rows_per_thread = 1; };

    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].row_start  = t * g_rows_per_thread;
        g_slices[t].row_end    = (t == g_num_threads - 1) ? SIM_H : (t + 1) * g_rows_per_thread;
        g_slices[t].phase      = PHASE_DECAY;
        g_slices2[t].row_start = t * g_rows_per_thread;
        g_slices2[t].row_end   = (t == g_num_threads - 1) ? SIM_H : (t + 1) * g_rows_per_thread;
        g_slices2[t].phase     = PHASE_DECAY;
        thread_create((void*)@worker,  (void*)@g_slices[t],  @g_threads[t]);
        thread_create((void*)@worker2, (void*)@g_slices2[t], @g_threads2[t]);
    };

    hInstance = GetModuleHandleA((LPCSTR)0);

    byte* class_name = "FluidSim\0",
          win_title  = "Fluid Simulation\0";

    WNDCLASSEXA wc;
    wc.cbSize        = (UINT)(sizeof(WNDCLASSEXA) / 8);
    wc.style         = CS_HREDRAW | CS_VREDRAW | CS_OWNDC;
    wc.lpfnWndProc   = (WNDPROC)@FluidWindowProc;
    wc.cbClsExtra    = 0;
    wc.cbWndExtra    = 0;
    wc.hInstance     = hInstance;
    wc.hIcon         = LoadIconA((HINSTANCE)0, (LPCSTR)32512);
    wc.hCursor       = LoadCursorA((HINSTANCE)0, (LPCSTR)32512);
    wc.hbrBackground = GetStockObject(BLACK_BRUSH);
    wc.lpszMenuName  = (LPCSTR)0;
    wc.lpszClassName = (LPCSTR)class_name;
    wc.hIconSm       = (HICON)0;

    RegisterClassExA(@wc);

    hwnd = CreateWindowExA(
        WS_EX_APPWINDOW,
        (LPCSTR)class_name,
        (LPCSTR)win_title,
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        100, 100, WIN_W, WIN_H,
        (HWND)0, (HMENU)0, hInstance, STDLIB_GVP);

    hdc = GetDC(hwnd);

    GLContext gl(hdc);
    gl.load_extensions();

    // Bind extension function pointers
    glCreateShader_fp       = _glCreateShader;
    glShaderSource_fp       = _glShaderSource;
    glCompileShader_fp      = _glCompileShader;
    glCreateProgram_fp      = _glCreateProgram;
    glAttachShader_fp       = _glAttachShader;
    glLinkProgram_fp        = _glLinkProgram;
    glUseProgram_fp         = _glUseProgram;
    glGetUniformLocation_fp = _glGetUniformLocation;
    glUniform1i_fp          = _glUniform1i;
    glUniform2f_fp          = _glUniform2f;
    glActiveTexture_fp      = _glActiveTexture;
    glDeleteShader_fp       = _glDeleteShader;
    glDeleteProgram_fp      = _glDeleteProgram;

    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_TEXTURE_2D);

    // Compile and link shader
    vert_sh = compile_shader(GL_VERTEX_SHADER,   @VERT_SRC[0]);
    frag_sh = compile_shader(GL_FRAGMENT_SHADER, @FRAG_SRC[0]);
    prog    = link_program(vert_sh, frag_sh);

    u_dens    = glGetUniformLocation_fp(prog, "u_dens\0");
    u_vel     = glGetUniformLocation_fp(prog, "u_vel\0");
    u_res     = glGetUniformLocation_fp(prog, "u_res\0");
    u_palette = glGetUniformLocation_fp(prog, "u_palette\0");

    // Density texture - single channel float
    tex_dens = 0;
    glGenTextures(1, @tex_dens);
    glBindTexture(GL_TEXTURE_2D, tex_dens);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, (i32)GL_LUMINANCE, SIM_W, SIM_H, 0,
                 (i32)GL_LUMINANCE, (i32)GL_FLOAT, (void*)g_dens_tex);

    // Velocity texture - two channel (vx=luminance, vy=alpha)
    tex_vel = 0;
    glGenTextures(1, @tex_vel);
    glBindTexture(GL_TEXTURE_2D, tex_vel);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, (i32)GL_LUMINANCE_ALPHA, SIM_W, SIM_H, 0,
                 (i32)GL_LUMINANCE_ALPHA, (i32)GL_FLOAT, (void*)g_vel_tex);

    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);

    running = true;

    while (running)
    {
        while (PeekMessageA(@msg, (HWND)0, 0, 0, PM_REMOVE))
        {
            if (msg.message == WM_QUIT) { running = false; };
            TranslateMessage(@msg);
            DispatchMessageA(@msg);
        };

        if (!running) { break; };

        GetClientRect(hwnd, @client_rect);
        cur_w = client_rect.right  - client_rect.left;
        cur_h = client_rect.bottom - client_rect.top;
        if (cur_w < 1) { cur_w = 1; };
        if (cur_h < 1) { cur_h = 1; };
        glViewport(0, 0, cur_w, cur_h);

        // Simulate
        if (g_game_state == 1)
        {
            if (g_ball_x < 0.0) { ball_reset(cur_w, cur_h); };
            paddle_update();
            cpu_paddle_update();
            ball_update(cur_w, cur_h);
            vel_step();
            dens_step();
            dispatch_decay();
        };

        // Update particles CPU-side
        if (g_game_state == 1)
        {
            particles_update();
        };

        // Convert double fields to float upload buffers
        upload_textures();

        // Upload density texture to unit 0
        glActiveTexture_fp(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, tex_dens);
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, SIM_W, SIM_H,
                        (i32)GL_LUMINANCE, (i32)GL_FLOAT, (void*)g_dens_tex);

        // Upload velocity texture to unit 1
        glActiveTexture_fp(GL_TEXTURE1);
        glBindTexture(GL_TEXTURE_2D, tex_vel);
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, SIM_W, SIM_H,
                        (i32)GL_LUMINANCE_ALPHA, (i32)GL_FLOAT, (void*)g_vel_tex);

        glClearColor(0.0, 0.0, 0.0, 1.0);
        glClear(GL_COLOR_BUFFER_BIT);

        // Draw fluid via shader - fullscreen triangle
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
        glUseProgram_fp(prog);
        glUniform1i_fp(u_dens, 0);
        glUniform1i_fp(u_vel,  1);
        glUniform2f_fp(u_res, (float)SIM_W, (float)SIM_H);
        glUniform1i_fp(u_palette, g_palette);

        glBegin(GL_TRIANGLES);
        glTexCoord2f(0.0, 0.0); glVertex2f(-1.0, -1.0);
        glTexCoord2f(2.0, 0.0); glVertex2f( 3.0, -1.0);
        glTexCoord2f(0.0, 2.0); glVertex2f(-1.0,  3.0);
        glEnd();

        glUseProgram_fp(0);
        glDisable(GL_BLEND);

        // Draw particles as soft glowing circles
        glActiveTexture_fp(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, 0);
        glActiveTexture_fp(GL_TEXTURE1);
        glBindTexture(GL_TEXTURE_2D, 0);
        glActiveTexture_fp(GL_TEXTURE0);
        glDisable(GL_TEXTURE_2D);
        glDisable(GL_DEPTH_TEST);
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE);

        step_a = 6.28318530718 / 12.0;

        for (i = 0; i < MAX_PARTICLES; i++)
        {
            px = g_part_x[i];
            py = g_part_y[i];

            dens_val = (float)g_dens[(int)py * SIM_W + (int)px];
            if (dens_val > 8.0)
            {
                // Scale particle radius with local density, clamped
                pr   = 1.5 + dens_val * 0.018;
                if (pr > 5.5) { pr = 5.5; };

                // NDC center
                ndcx = (px / (float)SIM_W) * 2.0 - 1.0;
                ndcy = (py / (float)SIM_H) * 2.0 - 1.0;

                // NDC radius (separate x/y for correct aspect)
                ox = pr * 2.0 / (float)cur_w;
                oy = pr * 2.0 / (float)cur_h;

                glBegin(GL_TRIANGLE_FAN);
                // Bright white core
                glColor4f(1.0, 1.0, 1.0, 0.55);
                glVertex2f(ndcx, ndcy);
                // Soft blue-white rim fading to transparent
                glColor4f(0.55, 0.75, 1.0, 0.0);
                seg = 0;
                while (seg <= 12)
                {
                    angle = (float)seg * step_a;
                    fx    = ndcx + ox * cos(angle);
                    fy    = ndcy + oy * sin(angle);
                    glVertex2f(fx, fy);
                    seg++;
                };
                glEnd();
            };
        };

        glDisable(GL_BLEND);
        glEnable(GL_TEXTURE_2D);

        // Draw paddle during gameplay
        if (g_game_state == 1)
        {
            draw_paddle(cur_w, cur_h, PADDLE_X,     g_paddle_gy);
            draw_paddle(cur_w, cur_h, PADDLE_X_CPU, g_cpu_paddle_gy);
            draw_ball(cur_w, cur_h);
            draw_hud(cur_w, cur_h);
        };

        // Draw main menu GUI overlay
        if (g_game_state == 0)
        {
            draw_gui(cur_w, cur_h);
        };

        // Draw quit confirmation dialog
        if (g_game_state == 2)
        {
            draw_quit_dialog(cur_w, cur_h);
        };

        gl.present();
    };

    // Shutdown
    for (t = 0; t < g_num_threads; t++)
    {
        g_slices[t].phase  = PHASE_EXIT;
        g_slices2[t].phase = PHASE_EXIT;
        semaphore_post(@g_work_sem);
        semaphore_post(@g_work_sem2);
    };
    for (t = 0; t < g_num_threads; t++)
    {
        thread_join(@g_threads[t]);
        thread_join(@g_threads2[t]);
    };

    semaphore_destroy(@g_work_sem);
    semaphore_destroy(@g_done_sem);
    semaphore_destroy(@g_work_sem2);
    semaphore_destroy(@g_done_sem2);

    glDeleteShader_fp(vert_sh);
    glDeleteShader_fp(frag_sh);
    glDeleteProgram_fp(prog);
    glDeleteTextures(1, @tex_dens);
    glDeleteTextures(1, @tex_vel);
    gl.__exit();


    ReleaseDC(hwnd, hdc);
    UnregisterClassA((LPCSTR)class_name, hInstance);

    return 0;
};
