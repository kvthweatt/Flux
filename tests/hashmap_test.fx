#import "standard.fx", "collections.fx";

using standard::io::console,
      standard::collections;

def main() -> int
{
	HashMap m(16);
	defer m.__exit();

	m.hm_set("hello\0", (void*)42);
	void* v = m.hm_get("hello\0");
	m.hm_remove("hello\0");

    print("Finished!\n\0");

	return 0;
};