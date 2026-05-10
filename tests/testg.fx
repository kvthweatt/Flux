// ============================================================
//  A small 2D physics particle simulation in Flux
// ============================================================

#import "standard.fx";

using standard::io::console;
using standard::math;
using standard::memory::allocators::stdheap;
using standard::memory::allocators::stdarena;

signed data{16} as fixed8_8;

struct Particle
{
    fixed8_8 px, py;
    fixed8_8 vx, vy;
    byte     r, g, b;
    byte     life;
    byte     age;       // frames since spawn, prevents instant merging
    byte     _pad2;
};

object ParticlePool
{
    Arena           arena;
    Particle*       particles;
    size_t          capacity;
    size_t          count;

    def __init(size_t max_particles) -> this
    {
        size_t total_bytes = max_particles * sizeof(Particle);
        arena_init_sized(@this.arena, total_bytes + 64);
        this.capacity = max_particles;
        this.particles = (Particle*)alloc(@this.arena, total_bytes);
        if ((u64)this.particles is 0)
        {
            this.capacity = 0;
            return this;
        };
        return this;
    };

    def __exit() -> void
    {
        arena_destroy(@this.arena);
    };

    def spawn(fixed8_8 x, fixed8_8 y,
              fixed8_8 vx, fixed8_8 vy,
              byte r, byte g, byte b) -> bool
    {
        if (this.count >= this.capacity) { return false; };

        Particle* p = this.particles + this.count;
        p.px = x;  p.py = y;
        p.vx = vx; p.vy = vy;
        p.r = r;  p.g = g;  p.b = b;
        p.life = 255;
        p.age  = 0;
        this.count++;
        return true;
    };

    def update() -> size_t
    {
        size_t alive;
        size_t i;
        Particle* p;

        while (i < this.count)
        {
            p = this.particles + i;

            if (p.life is 0)
            {
                if (i < this.count - 1)
                {
                    this.particles[i] = this.particles[this.count - 1];
                };
                this.count--;
                continue;
            };

            p.px = p.px + p.vx;
            p.py = p.py + p.vy;
            p.vy = p.vy + (fixed8_8)1;

            p.life = p.life - (byte)1;
            p.age  = p.age  + (byte)1;

            alive++;
            i++;
        };

        return alive;
    };

    def __expr() -> size_t
    {
        return this.count;
    };
};

// Much tighter threshold: ~0.25 units instead of 2.0
operator (Particle a, Particle b) [NEAR] -> bool
{
    fixed8_8 dx, dy, adx, ady;
    dx = a.px - b.px;
    dy = a.py - b.py;
    adx = dx < 0 ? -dx : dx;
    ady = dy < 0 ? -dy : dy;
    return (adx + ady) < (fixed8_8)64;
};

def clamp_byte(int value) -> byte
{
    if (value < 0)   { return (byte)0; };
    if (value > 255) { return (byte)255; };
    return (byte)value;
};

// Only merge particles that have been alive for at least 10 frames
def merge_nearby(ParticlePool* pool) -> void
{
    size_t i, j;
    Particle* a;
    Particle* b;

    while (i < pool.count)
    {
        a = pool.particles + i;

        // Don't merge young particles
        if (a.age < (byte)10) { i++; continue; };

        j = i + 1;
        while (j < pool.count)
        {
            b = pool.particles + j;

            if (b.age >= (byte)10 & a NEAR b)
            {
                a.r = clamp_byte(int(a.r) + int(b.r) / 2);
                a.g = clamp_byte(int(a.g) + int(b.g) / 2);
                a.b = clamp_byte(int(a.b) + int(b.b) / 2);
                a.vx = (a.vx + b.vx) / 2;
                a.vy = (a.vy + b.vy) / 2;
                a.life = 255;   // refresh life on merge
                b.life = 0;
            };
            j++;
        };
        i++;
    };
};

def main() -> int
{
    ParticlePool pool(1024);

    print("Spawning particles...\n\0");

    size_t i;
    fixed8_8 vx, vy;
    byte r, g, b;

    while (i < 200)
    {
        vx = (fixed8_8)((i * 173 + 89)  `& 0x07FF) - (fixed8_8)1024;
        vy = (fixed8_8)((i * 317 + 131) `& 0x07FF) - (fixed8_8)1024;

        r = clamp_byte(int((i * 67)  `& 0xFF));
        g = clamp_byte(int((i * 151) `& 0xFF));
        b = clamp_byte(int((i * 229) `& 0xFF));

        pool.spawn((fixed8_8)(128 * 256),
                   (fixed8_8)(20 * 256),
                   vx, vy, r, g, b);
        i++;
    };

    print(f"Spawned {pool.count} particles\n\0");
    print("Running simulation...\n\0");

    int frame;

    while (frame < 100)
    {
        size_t alive = pool.update();
        merge_nearby(@pool);

        if (frame % 5 is 0)
        {
            print(f"Frame {frame}: {alive} particles alive\n\0");
        };

        frame++;
    };

    print("Final frame (20x40 grid):\n\0");

    int gy;
    int gx;
    int world_x, world_y;
    bool drawn;
    size_t pi;
    Particle* p;
    int px, py;
    byte brightness;

    while (gy < 20)
    {
        gx = 0;
        while (gx < 40)
        {
            world_x = gx * 8;
            world_y = gy * 5;

            drawn = false;
            pi = 0;
            while (pi < pool.count & !drawn)
            {
                p = pool.particles + pi;
                px = p.px >> 8;
                py = p.py >> 8;

                if (px >= world_x & px < world_x + 8 &
                    py >= world_y & py < world_y + 5)
                {
                    brightness = (p.r + p.g + p.b) / 3;

                    if (brightness > 200)
                    {
                        print('#');
                    }
                    elif (brightness > 100)
                    {
                        print('*');
                    }
                    else
                    {
                        print('.');
                    };
                    drawn = true;
                };
                pi++;
            };

            if (!drawn) { print(' '); };
            gx++;
        };
        print('\n');
        gy++;
    };

    print(f"\nSimulation complete. Final count: {pool.count}\n\0");

    return 0;
};