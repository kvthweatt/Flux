// typeof() test on generic struct type

#import <standard.fx>;
 
using standard::io::console;

struct A<T,U>
{
	T x;
	U y;
};

def main() -> int
{
	A<int,long>     ax;
	A<float,double> ay;

	if (typeof(ax) == typeof(A<int,long>))
	{
		println("ax is type A<int,long>");
	};
	if (typeof(byte[4]) == typeof("hello"))
	{
		println("byte[4] == \"\" == byte*");
	};
	return 0;
};