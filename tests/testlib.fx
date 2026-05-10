export
{
    def !!foo() -> int
    {
        int a = 1, b = 10;
        int[10] x = [y for (int y in a..b)];
        return x[5];
    };
};