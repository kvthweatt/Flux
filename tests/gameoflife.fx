#import "standard.fx", "math.fx", "windows.fx", "opengl.fx", "timing.fx", "threading.fx", "random.fx";

using standard::io::console,
      standard::math,
      standard::system::windows,
      standard::threading,
      standard::random;

// ============================================================================
// Conway's Game of Life - OpenGL Viewer
// Controls:
//   SPACE - Pause/Resume simulation
//   C     - Clear the grid
//   R     - Randomize the grid
//   S     - Single step (when paused)
//   +/-   - Increase/Decrease simulation speed
//   Mouse - Click to toggle cells (when paused)
// ============================================================================

const int WIN_W          = 1024,
          WIN_H          = 1024,
          CELL_SIZE      = 4,           // Pixels per cell
          GRID_W         = WIN_W / CELL_SIZE,
          GRID_H         = WIN_H / CELL_SIZE,
          MAX_THREADS    = 64,
          HISTORY_SIZE   = 10;          // Frames of history for stability detection

// Game state
struct GameState
{
    bool paused, running,
         dirty;
    int  generation,
         speed_ms,                       // Milliseconds between updates (lower = faster)
         living_count,
         stable_counter;                 // Counts how many frames with no change
};

// Grid buffers for double-buffering
struct Grid
{
    byte* front, back;
    int   width, height;
};

// Work slice for parallel processing
struct WorkSlice
{
    int row_start, row_end,
        width,height;
    byte* src, dst;
};

// ============================================================================
// Grid Management
// ============================================================================

def grid_alloc(int width, int height) -> Grid
{
    Grid g;
    g.width  = width;
    g.height = height;
    size_t bytes = width * height;
    g.front = (byte*)fmalloc(bytes);
    g.back  = (byte*)fmalloc(bytes);
    if (g.front == 0 | g.back == 0)
    {
        print("Failed to allocate grid buffers!\n\0");
        g.width = 0;
        g.height = 0;
    };
    return g;
};

def grid_free(Grid* g) -> void
{
    if (g.front != 0) { ffree((u64)g.front); };
    if (g.back != 0)  { ffree((u64)g.back);  };
    g.front = (byte*)0;
    g.back  = (byte*)0;
    g.width = 0;
    g.height = 0;
};

def grid_clear(Grid* g) -> void
{
    size_t total = (size_t)(g.width * g.height);
    for (size_t i = 0; i < total; i++)
    {
        g.front[i] = 0;
        g.back[i]  = 0;
    };
};

def grid_randomize(Grid* g, float density) -> void
{
    size_t total = (size_t)(g.width * g.height);
    PCG32 rng;
    pcg32_init(@rng);
    
    for (size_t i = 0; i < total; i++)
    {
        g.front[i] = (random_float(@rng) < density) ? 1 : 0;
    };
};

def grid_set_cell(Grid* g, int x, int y, bool alive) -> void
{
    if (x >= 0 & x < g.width & y >= 0 & y < g.height)
    {
        g.front[y * g.width + x] = alive ? 1 : 0;
    };
};

def grid_get_cell(Grid* g, int x, int y) -> bool
{
    if (x < 0) { x = x + g.width; };
    if (x >= g.width) { x = x - g.width; };
    if (y < 0) { y = y + g.height; };
    if (y >= g.height) { y = y - g.height; };
    return g.front[y * g.width + x] != 0;
};

def count_neighbors(Grid* g, int x, int y) -> int
{
    int count;
    for (int dy = -1; dy <= 1; dy++)
    {
        for (int dx = -1; dx <= 1; dx++)
        {
            if (dx == 0 & dy == 0) { continue; };
            if (grid_get_cell(g, x + dx, y + dy)) { count++; };
        };
    };
    return count;
};

// ============================================================================
// Game of Life Rules
// ============================================================================

def update_cell(Grid* g, int x, int y) -> bool
{
    bool alive = grid_get_cell(g, x, y);
    int neighbors = count_neighbors(g, x, y);
    
    // Conway's rules:
    // - Any live cell with 2 or 3 live neighbors survives.
    // - Any dead cell with exactly 3 live neighbors becomes alive.
    // - All other cells die or stay dead.
    if (alive)
    {
        return (neighbors == 2 | neighbors == 3);
    }
    else
    {
        return (neighbors == 3);
    };
    return false;
};

// ============================================================================
// Worker Thread - Updates a slice of the grid
// ============================================================================

def worker_update(void* arg) -> void*
{
    WorkSlice* sl = (WorkSlice*)arg;
    bool new_state;
    Grid temp;
    
    for (int y = sl.row_start; y < sl.row_end; y++)
    {
        for (int x; x < sl.width; x++)
        {
            // Temporarily copy src to a local grid for neighbor checks
            // (we need to read from src while writing to dst)
            temp.front = sl.src;
            temp.back  = (byte*)0;
            temp.width = sl.width;
            temp.height = sl.height;
            
            new_state = update_cell(@temp, x, y);
            sl.dst[y * sl.width + x] = new_state ? 1 : 0;
        };
    };
    
    return (void*)0;
};

def update_grid(Grid* g, int num_threads, int* changes) -> void
{
    // Swap buffers: compute next generation from front into back
    WorkSlice[64] slices;
    Thread[64] threads;
    
    int rows_per_thread = g.height / num_threads;
    if (rows_per_thread < 1) { rows_per_thread = 1; };
    
    // Launch workers
    for (int t = 0; t < num_threads; t++)
    {
        slices[t].row_start = t * rows_per_thread;
        slices[t].row_end   = (t == num_threads - 1) 
                              ? g.height 
                              : (t + 1) * rows_per_thread;
        slices[t].width     = g.width;
        slices[t].height    = g.height;
        slices[t].src       = g.front;
        slices[t].dst       = g.back;
        
        thread_create(@worker_update, (void*)@slices[t], @threads[t]);
    };
    
    // Wait for all workers
    for (int t = 0; t < num_threads; t++)
    {
        thread_join(@threads[t]);
    };
    
    // Count changes and swap buffers
    int change_count = 0;
    size_t total = (size_t)(g.width * g.height);
    for (size_t i = 0; i < total; i++)
    {
        if (g.front[i] != g.back[i]) { change_count++; };
        g.front[i] = g.back[i];
    };
    
    if (changes != 0) { *changes = change_count; };
};

// ============================================================================
// Rendering
// ============================================================================

def render_grid(Grid* g, i32 tex_id, int cols, int rows) -> void
{
    // Convert grid to RGB texture data
    // We'll use a simple palette: live cells are white, dead cells are black
    // But we can also color based on age or population
    
    size_t pixel_count = (size_t)(cols * rows),
           idx, pix_idx;
    float* pixels = (float*)fmalloc(pixel_count * 3 * 4);  // RGB floats
    float r, grn, b;
    bool alive;
    
    for (int y; y < rows; y++)
    {
        for (int x; x < cols; x++)
        {
            idx = (size_t)(y * cols + x);
            alive = grid_get_cell(g, x, y);

            if (alive)
            {
                // Living cells: bright green with slight glow
                r   = 0.2f;
                grn = 1.0f;
                b   = 0.2f;
            }
            else
            {
                // Dead cells: dark blue-black gradient
                r   = 0.05f;
                grn = 0.05f;
                b   = 0.1f;
            };
            
            pix_idx = idx * 3;
            pixels[pix_idx]     = r;
            pixels[pix_idx + 1] = grn;
            pixels[pix_idx + 2] = b;
        };
    };
    
    glBindTexture(GL_TEXTURE_2D, tex_id);
    glTexImage2D(GL_TEXTURE_2D, 0, (i32)GL_RGB, cols, rows, 0,
                 (i32)GL_RGB, (i32)GL_FLOAT, (void*)pixels);
    
    ffree((u64)pixels);
};

def draw_quad() -> void
{
    glBegin(GL_QUADS);
    glTexCoord2f(0.0, 1.0); glVertex2f(-1.0, -1.0);
    glTexCoord2f(1.0, 1.0); glVertex2f( 1.0, -1.0);
    glTexCoord2f(1.0, 0.0); glVertex2f( 1.0,  1.0);
    glTexCoord2f(0.0, 0.0); glVertex2f(-1.0,  1.0);
    glEnd();
};

// ============================================================================
// UI Helpers
// ============================================================================

def draw_overlay(GameState* state, int population) -> void
{
    // Disable textures for overlay text
    glDisable(GL_TEXTURE_2D);
    
    // Set up orthographic projection for overlay
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glOrtho(0.0, (float)WIN_W, (float)WIN_H, 0.0, -1.0, 1.0);
    
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();
    
    // Draw a semi-transparent background for text
    glColor4f(0.0, 0.0, 0.0, 0.7);
    glBegin(GL_QUADS);
    glVertex2f(10.0, 10.0);
    glVertex2f(300.0, 10.0);
    glVertex2f(300.0, 80.0);
    glVertex2f(10.0, 80.0);
    glEnd();
    
    // We'll use a simpler approach: just draw colored rectangles
    // since we don't have a font renderer in this example
    
    // Pop matrices
    glPopMatrix();
    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
    glMatrixMode(GL_MODELVIEW);
    
    glEnable(GL_TEXTURE_2D);
};

// ============================================================================
// Main
// ============================================================================

def main() -> int
{
    // Query core count for threading
    SYSTEM_INFO_PARTIAL sysinfo;
    GetSystemInfo((void*)@sysinfo);
    int num_threads = (int)sysinfo.dwNumberOfProcessors;
    if (num_threads < 1)           { num_threads = 1; };
    if (num_threads > MAX_THREADS) { num_threads = MAX_THREADS; };
    
    print("Game of Life starting...\n\0");
    print("Cores: \0"); print(num_threads); print("\n\0");
    print("Grid size: \0"); print(GRID_W); print(" x \0"); print(GRID_H); print("\n\0");
    print("Controls:\n\0");
    print("  SPACE - Pause/Resume\n\0");
    print("  C     - Clear grid\n\0");
    print("  R     - Randomize\n\0");
    print("  S     - Single step (paused)\n\0");
    print("  +/-   - Speed up/down\n\0");
    print("  Click - Toggle cells (paused)\n\0");
    
    // Create window and OpenGL context
    Window win("Conway's Game of Life", 100, 100, WIN_W, WIN_H);
    GLContext gl(win.device_context);
    
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_TEXTURE_2D);
    
    // Create texture
    i32 tex_id;
    glGenTextures(1, @tex_id);
    glBindTexture(GL_TEXTURE_2D, tex_id);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    
    // Initialize grid
    Grid grid = grid_alloc(GRID_W, GRID_H);
    if (grid.width == 0) { return 1; };
    
    grid_clear(@grid);
    
    // Initialize with a glider gun pattern for interesting behavior
    // Classic Gosper Glider Gun
    POINT[] glider_gun = [
        {1, 5}, {1, 6}, {2, 5}, {2, 6},
        {11, 5}, {11, 6}, {11, 7}, {12, 4}, {12, 8}, {13, 3}, {13, 9},
        {14, 3}, {14, 9}, {15, 6}, {16, 4}, {16, 8}, {17, 5}, {17, 6},
        {17, 7}, {18, 6}, {21, 3}, {21, 4}, {21, 5}, {22, 3}, {22, 4},
        {22, 5}, {23, 2}, {23, 6}, {25, 1}, {25, 2}, {25, 6}, {25, 7},
        {35, 3}, {35, 4}, {36, 3}, {36, 4}
    ];

    int x,y;
    
    for (int i = 0; i < sizeof(glider_gun) / sizeof(POINT); i++)
    {
        x = glider_gun[i].x + 50;
        y = glider_gun[i].y + 50;
        if (x < GRID_W & y < GRID_H)
        {
            grid.front[y * GRID_W + x] = 1;
        };
    };
    
    // Game state
    GameState state;
    state.paused = false;
    state.running = true;
    state.dirty = true;
    state.generation = 0;
    state.speed_ms = 50;           // 20 FPS simulation speed
    state.living_count = 0;
    state.stable_counter = 0;
    
    // Input state
    WORD space_state, c_state, r_state, s_state, plus_state, minus_state;
    bool mouse_clicked,
         clicked, alive;
    int last_mouse_x, last_mouse_y,
        cell_x, cell_y,
        changes,
        living;

    size_t total;
    
    // Timing
    DWORD t_last = GetTickCount(),
          t_sim_last = GetTickCount(),
          t_now, dt,
          t_sim_now;

    WORD lbutton;

    POINT cursor;
    
    while (win.process_messages())
    {
        // Get current time
        t_now = GetTickCount();
        dt = t_now - t_last;
        t_last = t_now;
        
        // Handle input
        space_state = GetAsyncKeyState(VK_SPACE);
        c_state     = GetAsyncKeyState(0x43);  // 'C'
        r_state     = GetAsyncKeyState(0x52);  // 'R'
        s_state     = GetAsyncKeyState(0x53);  // 'S'
        plus_state  = GetAsyncKeyState(VK_OEM_PLUS);
        minus_state = GetAsyncKeyState(VK_OEM_MINUS);
        
        // SPACE: pause/resume
        if ((space_state `& 0x8000) != 0)
        {
            state.paused = !state.paused;
            // Debounce - wait for key release
            while ((GetAsyncKeyState(VK_SPACE) `& 0x8000) != 0) { thread_sleep_ms(10); };
            state.dirty = true;
        };
        
        // 'C': clear grid
        if ((c_state `& 0x8000) != 0)
        {
            grid_clear(@grid);
            state.generation = 0;
            state.stable_counter = 0;
            state.dirty = true;
            while ((GetAsyncKeyState(0x43) `& 0x8000) != 0) { thread_sleep_ms(10); };
        };
        
        // 'R': randomize
        if ((r_state `& 0x8000) != 0)
        {
            grid_randomize(@grid, 0.15f);
            state.generation = 0;
            state.stable_counter = 0;
            state.dirty = true;
            while ((GetAsyncKeyState(0x52) `& 0x8000) != 0) { thread_sleep_ms(10); };
        };
        
        // 'S': single step (when paused)
        if ((s_state `& 0x8000) != 0 & state.paused)
        {
            update_grid(@grid, num_threads, @changes);
            state.generation++;
            state.dirty = true;
            while ((GetAsyncKeyState(0x53) `& 0x8000) != 0) { thread_sleep_ms(10); };
        };
        
        // '+': increase speed (decrease delay)
        if ((plus_state `& 0x8000) != 0)
        {
            if (state.speed_ms > 10) { state.speed_ms = state.speed_ms - 10; };
            while ((GetAsyncKeyState(VK_OEM_PLUS) `& 0x8000) != 0) { thread_sleep_ms(10); };
        };
        
        // '-': decrease speed (increase delay)
        if ((minus_state `& 0x8000) != 0)
        {
            if (state.speed_ms < 200) { state.speed_ms = state.speed_ms + 10; };
            while ((GetAsyncKeyState(VK_OEM_MINUS) `& 0x8000) != 0) { thread_sleep_ms(10); };
        };
        
        // Mouse input for toggling cells (when paused)
        // Get cursor position relative to window
        GetCursorPos(@cursor);
        ScreenToClient(@win.handle, @cursor);
        
        if (cursor.x >= 0 & cursor.x < WIN_W & cursor.y >= 0 & cursor.y < WIN_H)
        {
            cell_x = cursor.x / CELL_SIZE;
            cell_y = cursor.y / CELL_SIZE;
            
            // Check for left mouse button
            lbutton = GetAsyncKeyState(VK_LBUTTON);
            clicked = (lbutton `& 0x8000) != 0;
            
            if (clicked & !mouse_clicked & state.paused)
            {
                alive = grid_get_cell(@grid, cell_x, cell_y);
                grid_set_cell(@grid, cell_x, cell_y, !alive);
                state.dirty = true;
                mouse_clicked = true;
            }
            else if (!clicked)
            {
                mouse_clicked = false;
            };
        };
        
        // Update simulation (if not paused)
        if (!state.paused)
        {
            t_sim_now = GetTickCount();
            if (t_sim_now - t_sim_last >= (DWORD)state.speed_ms)
            {
                update_grid(@grid, num_threads, @changes);
                state.generation++;
                t_sim_last = t_sim_now;
                state.dirty = true;
                
                // Check for stability (no changes for multiple frames)
                if (changes == 0)
                {
                    state.stable_counter++;
                    if (state.stable_counter >= HISTORY_SIZE)
                    {
                        // Auto-pause on stability?
                        // state.paused = true;
                    };
                }
                else
                {
                    state.stable_counter = 0;
                };
            };
        };
        
        // Count living cells
        if (state.dirty)
        {
            living = 0;
            total = (size_t)(GRID_W * GRID_H);
            for (size_t i; i < total; i++)
            {
                if (grid.front[i]) { living++; };
            };
            state.living_count = living;
        };
        
        // Render
        render_grid(@grid, tex_id, GRID_W, GRID_H);
        
        gl.set_clear_color(0.0, 0.0, 0.0, 1.0);
        gl.clear();
        
        draw_quad();
        
        // Draw overlay using simple colored rectangles
        glDisable(GL_TEXTURE_2D);
        
        // Set up orthographic overlay
        glMatrixMode(GL_PROJECTION);
        glPushMatrix();
        glLoadIdentity();
        glOrtho(0.0, (float)WIN_W, (float)WIN_H, 0.0, -1.0, 1.0);
        glMatrixMode(GL_MODELVIEW);
        glPushMatrix();
        glLoadIdentity();
        
        // Background for stats
        glColor4f(0.0, 0.0, 0.0, 0.7);
        glBegin(GL_QUADS);
        glVertex2f(10.0, 10.0);
        glVertex2f(250.0, 10.0);
        glVertex2f(250.0, 80.0);
        glVertex2f(10.0, 80.0);
        glEnd();
        
        // We'll use colored rectangles to simulate text
        // In a real implementation you'd use a proper font renderer
        
        glPopMatrix();
        glMatrixMode(GL_PROJECTION);
        glPopMatrix();
        glMatrixMode(GL_MODELVIEW);
        
        glEnable(GL_TEXTURE_2D);
        
        gl.present();
        state.dirty = false;
        
        // Small sleep to prevent CPU spinning
        //thread_sleep_ms(10);
    };
    
    // Cleanup
    grid_free(@grid);
    glDeleteTextures(1, @tex_id);
    
    return 0;
};