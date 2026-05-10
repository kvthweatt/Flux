#import "standard.fx";
#import "dotenv.fx";

extern {
    def !!getenv(byte* name) -> byte*;
};

using standard::io::console;

def main(int argc, byte** argv) -> int 
{
    println("Attempting to load .env file...\0");

    int result = dotenv::loadenv(".env\0", true, true);

    if (result != dotenv::err::OK) {
        if (result == dotenv::err::ERR_FILE_NOT_FOUND) {
            println("Failed to load .env: File not found.\0");
        } 
        elif (result == dotenv::err::ERR_INVALID_FORMAT) {
            println("Failed to load .env: Malformed line detected.\0");
        }
        elif (result == dotenv::err::ERR_READ_FAILED) {
            println("Failed to load .env: Could not read file.\0");
        }
        else {
            println("Failed to load .env.\0");
        };
        return -1;
    };

    println("Successfully loaded .env!\0");
    println("------------------------------------\0");

    byte* host = getenv("DB_HOST\0");
    if ((u64)host == 0) {
        println("DB_HOST not found.\0");
    } else {
        print("DB_HOST = \0");
        println(host);
    };

    byte* full_path = getenv("FULL_PATH\0");
    if ((u64)full_path == 0) {
        println("FULL_PATH not found.\0");
    } else {
        print("FULL_PATH = \0");
        println(full_path);
    };

    println("Setting BASE_PATH to /tmp... \0");
    dotenv::setenv("BASE_PATH\0", "/tmp\0", 1);

    byte* base_path = getenv("BASE_PATH\0");
    if ((u64)base_path == 0) {
        println("BASE_PATH not found.\0");
    } else {
        print("BASE_PATH = \0");
        println(base_path);
    };

    return 0;
};
