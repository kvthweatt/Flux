#import <standard.fx>;

using standard::io::console;

comptime
{
	byte* s = "Hello world!";

	for (x in s)
	{
		compiler.io.console.print(f"{(char)x}");
	};
	compiler.io.console.print("\n");

	byte[2] x = [0b11011011, 0b00100100];

	data{5} as i5;

	i5 y = x[6``10];

	compiler.io.console.print(f"{uint(y)}\n");
};

def foo(byte* x, byte* y) -> byte*
{
	return f"{x} {y}";
};

object Test
{
	byte* val;
	def __init(byte* x) -> this
	{
		this.val = x;
		return this;
	};
	def __expr() -> Test* { return this; };
	def __exit() -> void { return; };
};

operator(byte* L, byte* R)[\] -> byte*
{
	return f"{L}\\{R}";
};

operator(byte* L, byte* R)[/] -> byte*
{
	return f"{L}/{R}";
};

operator(Test L, Test R)[\] -> byte*
{
	return f"{L.val}\\{R.val}";
};

operator(Test L, Test R)[/] -> byte*
{
	return f"{L.val}/{R.val}";
};

def main() -> int
{
	Test t("ABCDEFG");
	Test u("HIJKLMNOP");
	println(foo("Hello","world!"));
	println("Hello" \ "world!");
	println("Hello" / "world!");
	println(t \ u);
	println(t / u);
	return 0;
};