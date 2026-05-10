#import "standard.fx";

using standard::io::console;

// --- Templated struct: fixed-size ring buffer descriptor ---
struct Ring<T>
{
    T[8] buf;
    int  head, tail, count;
};

// --- Macros ---
macro RING_FULL(r)  { r.count == 8 };
macro RING_EMPTY(r) { r.count == 0 };
macro RING_NEXT(i)  { (i + 1) % 8 };

// --- Contracts ---
contract NotFull(r)
{
    assert(!RING_FULL(r), "ring is full\0");
};

contract NotEmpty(r)
{
    assert(!RING_EMPTY(r), "ring is empty\0");
};

// --- push: pre-contract guards capacity, post-contract confirms count grew ---
def push<T>(Ring<T>* r, T val) -> void : NotFull(r)
{
    r.buf[r.tail] = val;
    r.tail        = RING_NEXT(r.tail);
    r.count       = r.count + 1;
};

// --- pop: pre-contract guards non-empty ---
def pop<T>(Ring<T>* r) -> T : NotEmpty(r)
{
    T   val;
    val    = r.buf[r.head];
    r.head = RING_NEXT(r.head);
    r.count = r.count - 1;
    return val;
};

// --- Operator overload: merge two rings by draining src into dst ---
operator<T>(Ring<T>* dst, Ring<T>* src)[<<] -> Ring<T>*
{
    T val;
    do
    {
        switch (!RING_EMPTY(*src) & !RING_FULL(*dst))
        {
            case (1)
            {
                val = pop(src);
                push(dst, val);
            }
            default { break; };
        };
    };
    return dst;
};

// --- Program ---
def main() -> int
{
    Ring<int> a, b;
    Ring<int>* pa, pb;
    int        i, v;
    pa = @a;
    pb = @b;

    i = 0;
    do
    {
        switch (i < 4)
        {
            case (1) { push(pa, i + 1); push(pb, (i + 1) * 10); i = i + 1; }
            default  { break; };
        };
    };

    pa << pb;   // drain b into a

    print("merged: \0");
    do
    {
        switch (!RING_EMPTY(a))
        {
            case (1) { v = pop(pa); print(f"{v} \0"); }
            default  { break; };
        };
    };
    print("\n\0");

    return 0;
};