#import "standard.fx";

using standard::io::console;

#ifndef __FLUX_TEST__
def main() -> int
{
	byte[20] buf;

	u64 test1 = (u64)0xFFFFFFFFu;           // Store first
	u64 test2 = test1 / (u64)256u;          // Then divide
	// vs
	u64 test3 = (u64)0xFFFFFFFFu / (u64)256u;  // Direct division

	(void)buf; // Reset buffer
	byte[20] buf;

	print("u64 test1 = (u64)0xFFFFFFFFu; / == / \0");
	u64str(test1,buf);
	print(buf);
    print();

	(void)buf; // Reset buffer
	byte[20] buf;

	print("u64 test2 = test1 / (u64)256u; / == / \0");
	u64str(test2,buf);
	print(buf);
    print();

	(void)buf; // Reset buffer
	byte[20] buf;

	print("u64 test3 = (u64)0xFFFFFFFFu / (u64)256u; / == / \0");
	u64str(test3,buf);
	print(buf);
    print();

	return 0;
};
#endif;