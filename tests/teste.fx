#import "standard.fx";

using standard::io::console;

// ─── Traits ───────────────────────────────────────────────────────────────────

trait Shape
{
    def area()     -> float;
    def perimeter() -> float;
    def describe() -> void;
};

trait Scalable
{
    def scale(float factor) -> void;
};

// ─── Circle ───────────────────────────────────────────────────────────────────

Shape Scalable object Circle
{
    float radius;

    def __init(float r) -> this
    {
        this.radius = r;
        return this;
    };

    def __exit() -> void { return; };

    def area() -> float
    {
        return 3.14159 * this.radius * this.radius;
    };

    def perimeter() -> float
    {
        return 2.0 * 3.14159 * this.radius;
    };

    def describe() -> void
    {
        print(f"Circle  | r={this.radius}  area={this.area()}  perim={this.perimeter()}\0");
    };

    def scale(float factor) -> void
    {
        this.radius *= factor;
    };
};

// ─── Rectangle ────────────────────────────────────────────────────────────────

Shape Scalable object Rectangle
{
    float width, height;

    def __init(float w, float h) -> this
    {
        this.width  = w;
        this.height = h;
        return this;
    };

    def __exit() -> void { return; };

    def area() -> float
    {
        return this.width * this.height;
    };

    def perimeter() -> float
    {
        return 2.0 * (this.width + this.height);
    };

    def describe() -> void
    {
        print(f"Rect    | w={this.width} h={this.height}  area={this.area()}  perim={this.perimeter()}\0");
    };

    def scale(float factor) -> void
    {
        this.width  *= factor;
        this.height *= factor;
    };
};

// ─── Triangle (right triangle) ────────────────────────────────────────────────

Shape Scalable object Triangle
{
    float base, height;

    def __init(float b, float h) -> this
    {
        this.base   = b;
        this.height = h;
        return this;
    };

    def __exit() -> void { return; };

    def area() -> float
    {
        return 0.5 * this.base * this.height;
    };

    def perimeter() -> float
    {
        // hypotenuse via sqrt approximation (Newton's method)
        float hyp = this.base * this.base + this.height * this.height;
        float x   = hyp;
        int   i   = 0;
        for (; i < 20; i++) { x = 0.5 * (x + hyp / x); };
        return this.base + this.height + x;
    };

    def describe() -> void
    {
        print(f"Triangle| b={this.base} h={this.height}  area={this.area()}  perim={this.perimeter()}\0");
    };

    def scale(float factor) -> void
    {
        this.base   *= factor;
        this.height *= factor;
    };
};

// ─── Generic functions that work on any Shape ─────────────────────────────────

def print_shape_info(Shape* s) -> void
{
    s.describe();
};

def total_area(Shape*[] shapes, int count) -> float
{
    float sum = 0.0;
    int   i   = 0;
    for (; i < count; i++)
    {
        sum += shapes[i].area();
    };
    return sum;
};

def scale_all(Scalable*[] shapes, int count, float factor) -> void
{
    int i = 0;
    for (; i < count; i++)
    {
        shapes[i].scale(factor);
    };
};

// ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> int
{
    Circle    c = 5.0;
    Rectangle r(4.0, 6.0);
    Triangle  t(3.0, 4.0);

    defer c.__exit();
    defer r.__exit();
    defer t.__exit();

    print("── Before scale ──\0");
    print_shape_info(@c);
    print_shape_info(@r);
    print_shape_info(@t);

    // Uniform array of Shape pointers — polymorphic dispatch
    Shape*[] shapes = [@c, @r, @t];
    print(f"\nTotal area: {total_area(shapes, 3)}\0");

    // Scale everything by 2x via Scalable trait
    Scalable*[] scalables = [@c, @r, @t];
    scale_all(scalables, 3, 2.0);

    print("\n── After 2x scale ──\0");
    print_shape_info(@c);
    print_shape_info(@r);
    print_shape_info(@t);

    print(f"\nTotal area after scale: {total_area(shapes, 3)}\0");

    return 0;
};