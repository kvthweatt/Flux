#import "standard.fx";

using standard::io::console;

def main() -> int
{
	int a = 5;         // Initialize a

	int* pa = @a;      // Point to a

	ulong x = pa;      // Take pointer as integer

	int* pb = (@)x;    // Cast integer to new pointer

	if (*pb == 5)  // Dereference new pointer
	{
		print("Success!\0");
	};
	return 0;
};