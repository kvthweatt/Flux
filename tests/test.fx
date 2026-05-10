#import "standard.fx", "dotenv.fx";

using standard::io::console;

def main(int argc, byte** argv) -> int 
{
    println("Attempting to load .env file... \0");

    // Call your loader
    int result = dotenv::env_load(".env\0", true, true);

    if (result == -1) {
        println("Failed to load .env. Check file path and permissions. \0");
        return -1;
    };

    println("Successfully loaded .env! \0");
    println("--------------------------- \0");

    // DOESN'T WORK
    // byte* host = getenv("DB_HOST\0");
    // if (host) {
    //     print("DB_HOST =  \0");
    //     println(host);
    // } else {
    //     println("DB_HOST not found. \0");
    // };

    // DOESN'T WORK
    // byte* host = getenv("DB_HOST\0");
    // if (host == 1) {
    //     print("DB_HOST =  \0");
    //     println(host);
    // } else {
    //     println("DB_HOST not found. \0");
    // };

    // DOESN'T WORK
    // byte* host = getenv("DB_HOST\0");
    // if ((u64)host == 1) {
    //     print("DB_HOST =  \0");
    //     println(host);
    // } else {
    //     println("DB_HOST not found. \0");
    // };

    // WORKS
    byte* host = getenv("DB_HOST\0");
    if ((u64)host == 0) {
        println("DB_HOST not found. \0");
    } else {
        print("DB_HOST =  \0");
        println(host);
    };

    // WORKS. But same thing happens for full_path as the not working examples above.
    byte* full_path = getenv("FULL_PATH\0");
    if ((u64)full_path == 0) {
        println("FULL_PATH not found. \0");
    } else {
        print("FULL_PATH =  \0");
        println(full_path);
    };

    return 0;
};
