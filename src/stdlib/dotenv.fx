// Author: reinitd <molliver@aurictradecollective.org>

///
dotenv.fx - a simple .env manager

Loads key=value pairs from a .env file into the process environment,
where they can be read with getenv and modified with fsetenv.

Functions:
    loadenv(file, overwrite, verbose) -> int
        Loads the given .env file. If `overwrite` is true, existing
        environment variables will be replaced. If `verbose` is true,
        parsing details are printed to stdout. Returns dotenv::err::OK
        on success, or an error code otherwise.

    setenv(name, value, overwrite) -> int
        Sets an environment variable. If `overwrite` is falsey, then
        an existing variable with the same name will be replaced.

Error codes (dotenv::err):
    OK                 :  0   success
    ERR_FILE_NOT_FOUND : -1   fopen returned 0
    ERR_ALLOC_FAILED   : -2   fmalloc or frealloc returned 0
    ERR_SETENV_FAILED  : -3   _putenv_s or setenv failed
    ERR_INVALID_FORMAT : -4   .env file contains a malformed line
    ERR_NULL_POINTER   : -5   passed a null pointer for path or buffer
    ERR_READ_FAILED    : -6   .env file exists but could not be read

Example:
    #import "standard.fx";
    #import "dotenv.fx";

    extern {
        def !!getenv(byte* name) -> byte*;
    };

    // args: file, overwrite, verbose
    int result = dotenv::loadenv(".env\0", true, false);
    if (result != dotenv::err::OK) {
        // Handle error
    };

    byte* host = getenv("DB_HOST\0");
    if ((u64)host != 0) {
        print("DB_HOST = \0");
        println(host);
    };

    dotenv::setenv("BASE_PATH\0", "/tmp\0", 1);
///
#ifndef FLUX_STANDARD
#import "standard.fx";
#endif;

#import "string_utilities.fx";

#ifndef FLUX_DOTENV
#def FLUX_DOTENV 1;
#def DEBUG 0;

#def _DE_OK                  0;
#def _DE_ERR_FILE_NOT_FOUND -1;     // fopen returned 0
#def _DE_ERR_ALLOC_FAILED   -2;     // fmalloc or frealloc returned 0
#def _DE_ERR_SETENV_FAILED  -3;     // _putenv_s or setenv failed
#def _DE_ERR_INVALID_FORMAT -4;     // .env file contains a malformed line
#def _DE_ERR_NULL_POINTER   -5;     // Passed a null pointer for path or buffer
#def _DE_ERR_READ_FAILED    -6;     // .env file exists but couldn't be read

extern
{
    // Standard C
    def !!
        getenv(byte* name) -> byte*,
        fgets(byte* str, int n, byte* stream) -> byte*,
        strtok(byte* str, byte* delim) -> byte*,
        fopen(byte* filename, byte* mode) -> byte*,
        fclose(byte* stream) -> int;
};

using standard::io::file;
using standard::strings;

#ifdef __WINDOWS__
    extern
    {
        def !!
            getenv_s(u64* pReturnValue, byte* buf, u64 numOfElements, byte* name) -> int,
            _putenv_s(byte* name, byte* value) -> int,
            strtok_s(byte* str, byte* delim, byte** saveptr) -> byte*,
            _strdup(byte* str) -> byte*;
    };

    #def strdup _strdup;

    def _setenv(byte* name, byte* value, bool overwrite) -> int
    {
        int errcode = 0;
        if (overwrite is 0) {
            u64 envsize = 0;
            if (getenv_s(@envsize, NULL, 0, name) != 0 | envsize != 0) {
                return _DE_OK;
            };
        };

        if (_putenv_s(name, value) != 0) {
            return _DE_ERR_SETENV_FAILED;
        };

        return _DE_OK;
    };

    // Derived from https://dev.w3.org/libwww/Library/src/vms/getline.c
    byte[256] _win_line_buffer;
    def _getline(byte** lineptr, u64* n, byte* stream) -> int
    {
        byte* new_ptr;
        u64 len;

        if ((u64)lineptr == 0 | (u64)n == 0 | (u64)stream == 0) {
            return _DE_ERR_NULL_POINTER;
        };

        if ((u64)fgets(@_win_line_buffer[0], 256, stream) == 0) {
            return _DE_ERR_READ_FAILED;
        };

        byte* newline_ptr = strchr(@_win_line_buffer[0], '\n');
        if ((u64)newline_ptr != 0) {
            newline_ptr[0] = 0;
        };

        byte* cr_ptr = strchr(@_win_line_buffer[0], '\r');
        if ((u64)cr_ptr != 0) {
            cr_ptr[0] = 0;
        };

        len = strlen(@_win_line_buffer[0]);

        if (n[0] < (len + 1)) {
            if ((u64)lineptr[0] == 0) {
                new_ptr = (byte*)fmalloc(len + 1);
            } else {
                new_ptr = (byte*)frealloc((u64)lineptr[0], len + 1);
            };

            if ((u64)new_ptr == 0) {
                return _DE_ERR_ALLOC_FAILED;
            };
            
            lineptr[0] = new_ptr;
            n[0] = len + 1;
        };

        strcpy(lineptr[0], @_win_line_buffer[0]);
        
        return (int)len;
    };
#else
    // Linux/macOS (POSIX)
    extern
    {
        def !!
            setenv(byte* name, byte* value, bool overwrite) -> int,
            getline(byte** lineptr, u64* n, byte* stream) -> i64,
            strtok_r(byte* str, byte* delim, byte** saveptr) -> byte*,
            strdup(byte* str) -> byte*;
    };

    #def strdup strdup;
    #def strtok_s strtok_r;

    def _setenv(byte* name, byte* value, bool overwrite) -> int
    {
        if (setenv(name, value, overwrite) != 0) {
            return _DE_ERR_SETENV_FAILED;
        };
        return _DE_OK;
    };

    def _getline(byte** lineptr, u64* n, byte* stream) -> int
    {
        if ((u64)lineptr == 0 | (u64)n == 0 | (u64)stream == 0) {
            return _DE_ERR_NULL_POINTER;
        };

        i64 result = getline(lineptr, n, stream);
        
        if (result == (i64)-1) {
            return _DE_ERR_READ_FAILED;
        };
        return (int)result;
    };
#endif;

namespace dotenv
{   
    namespace err
    {
        global const int OK                 = _DE_OK;
        global const int ERR_FILE_NOT_FOUND = _DE_ERR_FILE_NOT_FOUND;
        global const int ERR_ALLOC_FAILED   = _DE_ERR_ALLOC_FAILED;
        global const int ERR_SETENV_FAILED  = _DE_ERR_SETENV_FAILED;
        global const int ERR_INVALID_FORMAT = _DE_ERR_INVALID_FORMAT;
        global const int ERR_NULL_POINTER   = _DE_ERR_NULL_POINTER;
        global const int ERR_READ_FAILED    = _DE_ERR_READ_FAILED;
    };
    namespace internal
    {
        def remove_space(byte* value) -> byte* {
            int offset = helpers::skip_whitespace(value, 0);
            return value + offset;
        };

        def safe_concat(byte* buffer, byte* string) -> byte* {
            if ((u64)buffer == 0) {
                return manip::copy_string(string);
            };

            if ((u64)string != 0) {
                byte* new_ptr = manip::concat(buffer, string);
                ffree(buffer);
                return new_ptr;
            };

            return buffer;
        };

        def is_nested(byte* value) -> bool {
            if ((u64)strstr(value, "${\0") != 0) {
                if ((u64)strstr(value, "}\0") != 0) {
                    return true;
                };
            };
            return false;
        };

        def prepare_value(byte* value) -> byte* {
            return safe_concat(" \0", value);
        };

        def parse_value(byte* value) -> byte* {
            value = prepare_value(value);
            byte* search = value;
            byte* parsed = (byte*)0;
            byte* name = (byte*)0;

            byte** pTokPtr = (byte**)fmalloc(8);
            if ((u64)pTokPtr == 0) { return value; };
            pTokPtr[0] = (byte*)0;

            if ((u64)value != 0) {
                if (is_nested(value)) {
                    while (true) {
                        parsed = safe_concat(parsed, strtok_s(search, "$\0", pTokPtr));
                        name = strtok_s((byte*)0, "{}\0", pTokPtr);

                        if ((u64)name == 0) {
                            break;
                        };

                        parsed = safe_concat(parsed, getenv(name));
                        search = (byte*)0;
                    };

                    ffree(value);
                    ffree((byte*)pTokPtr);
                    return parsed;
                };
            };
                
            ffree((byte*)pTokPtr);
            return value;
        };

        def is_commented(byte* line) -> bool {
            int i = helpers::skip_whitespace(line, 0);
                
            byte c = line[i];
            if (c == '#' | c == ';' | c == 0 | c == '\r' | c == '\n') {
                return true;
            };

            return false;
        };

        def set_variable(byte* name, byte* original, bool overwrite) -> void {
            byte* parsed;

            if ((u64)original != 0) {
                parsed = parse_value(original);
                byte* clean_value = remove_space(parsed);

                #ifdef DEBUG
                    standard::io::console::print("Setting [ \0");
                    standard::io::console::print(name);
                    standard::io::console::print(" ] to [ \0");
                    standard::io::console::print(clean_value);
                    standard::io::console::println(" ]\0");
                #endif;

                _setenv(name, clean_value, overwrite);

                ffree(parsed);
            };
        };

        def parse(byte* file, bool overwrite) -> int {
            byte* name = (byte*)0;
            byte* original = (byte*)0;
            u64 len = 0;
            int status = err::OK;

            byte** pLineBuf = (byte**)fmalloc(8);
            if ((u64)pLineBuf == 0) { return err::ERR_ALLOC_FAILED; };
            pLineBuf[0] = (byte*)0;

            #ifdef DEBUG
                standard::io::console::println("Starting to parse .env file...\0");
            #endif;
                
            int read_result;
            while((read_result = _getline(pLineBuf, @len, file)) >= 0) {
                byte* line_buf = pLineBuf[0];
                    
                #ifdef DEBUG
                    standard::io::console::print("Read line: [ \0");
                    standard::io::console::print(line_buf);
                    standard::io::console::println(" ]\0");
                #endif;

                if (!is_commented(line_buf)) {
                    name = strtok(line_buf, "= \t\0"); 
                    original = strtok((byte*)0, "\n\0");

                    if ((u64)name != 0) {
                        if ((u64)original != 0) {
                            set_variable(name, original, overwrite);
                        } else {
                            // Key was found, but no '=' or value
                            status = err::ERR_INVALID_FORMAT;
                            break;
                        };
                    };
                };
            };

            if (read_result < 0 & read_result != err::ERR_READ_FAILED) {
                status = read_result;
            };

            if ((u64)pLineBuf[0] != 0) {
                ffree(pLineBuf[0]);
            };
            ffree((byte*)pLineBuf); 

            return status;
        };
    };

    def loadenv(byte* path, bool overwrite, bool verbose) -> int {
        using dotenv::internal;
        using dotenv::err;

        if ((u64)path == 0) {
            return dotenv::err::ERR_NULL_POINTER;
        };

        byte* file = fopen(path, "rt\0");

        if ((u64)file == 0) {
            return dotenv::err::ERR_FILE_NOT_FOUND;
        };

        if (verbose) {
            standard::io::console::println("File opened successfully...\0");
        };

        int result = parse(file, overwrite);
        fclose(file);

        return result;
    };

    def setenv(byte* name, byte* value, bool overwrite) -> int {
        return _setenv(name, value, overwrite);
    };
};

#endif;
