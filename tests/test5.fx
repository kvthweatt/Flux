#import "standard.fx";
#import "cryptography.fx";

using standard::crypto::hashing::SHA256,
      standard::io::console;

def byte_to_hex(byte b, byte* out) -> void
{
    byte[16] hex_chars = [
        '0', '1', '2', '3', '4', '5', '6', '7',
        '8', '9', 'a', 'b', 'c', 'd', 'e', 'f'
    ];
    
    out[0] = hex_chars[(b >> 4) & 0x0F];
    out[1] = hex_chars[b & 0x0F];
};

def main() -> int
{
    print("SHA256 Crypto Demo\n\0");
    print("==================\n\n\0");
    
    // The message we want to hash
    byte[] message = "Hello, Flux!\0";
    
    print("Message: \0");
    print(message);
    print("\n\0");
    
    // Create SHA256 context
    SHA256_CTX ctx;
    
    // Initialize SHA256
    sha256_init(@ctx);
    
    // Calculate message length (without null terminator)
    u64 msg_len = (u64)0;
    while (message[msg_len] != (byte)0)
    {
        msg_len++;
    };
    
    print("Message length: \0");
    print((int)msg_len);
    print(" bytes\n\0");
    
    // Update with our message
    sha256_update(@ctx, message, msg_len);
    
    // Finalize and get hash
    byte[32] hash;
    sha256_final(@ctx, hash);
    
    // Print the hash in hexadecimal
    print("\nSHA256 Hash: \0");
    
    byte[3] hex_out;
    hex_out[2] = (byte)0;
    
    for (u32 i = (u32)0; i < (u32)32; i++)
    {
        byte_to_hex(hash[i], hex_out);
        print(hex_out);
    };
    
    print("\n\0");
    
    return 0;
};
