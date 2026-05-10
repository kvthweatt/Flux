// Author: Karac V. Thweatt

// redtime.fx - Timing & Benchmarking Library
// Provides high-resolution timestamps, timers, and benchmarking utilities.
// Basic usage: t1 = time_now(); ... t2 = time_now(); elapsed_ns = t2 - t1;

#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#ifndef FLUX_STANDARD_TIME
#def FLUX_STANDARD_TIME 1;

#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_SYSTEM
#import "sys.fx";
#endif;

// ============ PLATFORM FFI ============

#ifdef __WINDOWS__
extern
{
    def !!
        QueryPerformanceCounter(i64*) -> bool,
        QueryPerformanceFrequency(i64*) -> bool,
        GetTickCount() -> u32,
        Sleep(u32) -> void;
};
#endif;

#ifdef __LINUX__
extern
{
    def !!
        clock_gettime(int, void*) -> int,
        nanosleep(void*, void*) -> int;
};
#endif;

#ifdef __MACOS__
extern
{
    def !!
        clock_gettime(int, void*) -> int,
        nanosleep(void*, void*) -> int;
};
#endif;

// ============ STRUCTS (top-level) ============

struct timespec
{
    i64 tv_sec, tv_nsec;
};

// ============ NAMESPACE ============

namespace standard
{
    namespace time
    {
        // ============ CONSTANTS ============

        global const i64 TIME_NS_PER_US  = 1000,
                         TIME_NS_PER_MS  = 1000000,
                         TIME_NS_PER_SEC = 1000000000;

        // ============ FORWARD DECLARATIONS ============

#ifdef __WINDOWS__
        def win_time_now() -> i64,
            win_sleep_ms(u32) -> void,
            win_sleep_us(u32) -> void;
#endif;

#ifdef __LINUX__
        def nix_time_now() -> i64,
            nix_sleep_ms(u32) -> void,
            nix_sleep_us(u32) -> void;
#endif;

#ifdef __MACOS__
        def mac_time_now() -> i64,
            mac_sleep_ms(u32) -> void,
            mac_sleep_us(u32) -> void;
#endif;

        // ============ PLATFORM IMPLEMENTATIONS ============

#ifdef __WINDOWS__
        def win_time_now() -> i64
        {
            i64 counter, freq;
            QueryPerformanceCounter(@counter);
            QueryPerformanceFrequency(@freq);
            if (freq == 0)
            {
                return 0;
            };
            return (counter / freq) * TIME_NS_PER_SEC
                 + ((counter % freq) * TIME_NS_PER_SEC) / freq;
        };

        def win_sleep_ms(u32 ms) -> void
        {
            Sleep(ms);
        };

        def win_sleep_us(u32 us) -> void
        {
            // Windows Sleep granularity is 1ms; round up.
            u32 ms = (us + 999) / 1000;
            if (ms == 0)
            {
                ms = 1;
            };
            Sleep(ms);
        };
#endif;

#ifdef __LINUX__
        def nix_time_now() -> i64
        {
            timespec ts;
            clock_gettime(1, @ts);  // CLOCK_MONOTONIC = 1
            return ts.tv_sec * TIME_NS_PER_SEC + ts.tv_nsec;
        };

        def nix_sleep_ms(u32 ms) -> void
        {
            timespec req;
            req.tv_sec  = ms / 1000;
            req.tv_nsec = (ms % 1000) * TIME_NS_PER_MS;
            nanosleep(@req, (void*)0);
        };

        def nix_sleep_us(u32 us) -> void
        {
            timespec req;
            req.tv_sec  = us / 1000000;
            req.tv_nsec = (us % 1000000) * TIME_NS_PER_US;
            nanosleep(@req, (void*)0);
        };
#endif;

#ifdef __MACOS__
        def mac_time_now() -> i64
        {
            timespec ts;
            ts.tv_sec  = 0;
            ts.tv_nsec = 0;
            clock_gettime(1, @ts);  // CLOCK_MONOTONIC = 1
            return ts.tv_sec * TIME_NS_PER_SEC + ts.tv_nsec;
        };

        def mac_sleep_ms(u32 ms) -> void
        {
            timespec req;
            req.tv_sec  = ms / 1000;
            req.tv_nsec = (ms % 1000) * TIME_NS_PER_MS;
            nanosleep(@req, (void*)0);
            return;
        };

        def mac_sleep_us(u32 us) -> void
        {
            timespec req;
            req.tv_sec  = us / 1000000;
            req.tv_nsec = (us % 1000000) * TIME_NS_PER_US;
            nanosleep(@req, (void*)0);
            return;
        };
#endif;

        // ============ GENERIC API ============

        // Returns current monotonic time in nanoseconds.
        // Subtract two results to get elapsed time: elapsed_ns = t2 - t1
        def time_now() -> i64
        {
            switch (CURRENT_OS)
            {
#ifdef __WINDOWS__
                case (1)
                {
                    return win_time_now();
                }
#endif;
#ifdef __LINUX__
                case (2)
                {
                    return nix_time_now();
                }
#endif;
#ifdef __MACOS__
                case (3)
                {
                    return mac_time_now();
                }
#endif;
                default { return (i64)0; };
            };
            return 0;
        };

        def sleep_ms(u32 ms) -> void
        {
            switch (CURRENT_OS)
            {
#ifdef __WINDOWS__
                case (1)
                {
                    win_sleep_ms(ms);
                }
#endif;
#ifdef __LINUX__
                case (2)
                {
                    nix_sleep_ms(ms);
                }
#endif;
#ifdef __MACOS__
                case (3)
                {
                    mac_sleep_ms(ms);
                }
#endif;
                default {};
            };
        };

        def sleep_us(u32 us) -> void
        {
            switch (CURRENT_OS)
            {
#ifdef __WINDOWS__
                case (1)
                {
                    win_sleep_us(us);
                }
#endif;
#ifdef __LINUX__
                case (2)
                {
                    nix_sleep_us(us);
                }
#endif;
#ifdef __MACOS__
                case (3)
                {
                    mac_sleep_us(us);
                }
#endif;
                default {};
            };
        };

        // ============ CONVERSIONS ============

        def ns_to_us(i64 ns) -> i64
        {
            return ns / TIME_NS_PER_US;
        };

        def ns_to_ms(i64 ns) -> i64
        {
            return ns / TIME_NS_PER_MS;
        };

        def ns_to_sec(i64 ns) -> i64
        {
            return ns / TIME_NS_PER_SEC;
        };

        def us_to_ns(i64 us) -> i64
        {
            return us * TIME_NS_PER_US;
        };

        def ms_to_ns(i64 ms) -> i64
        {
            return ms * TIME_NS_PER_MS;
        };

        def sec_to_ns(i64 s) -> i64
        {
            return s * TIME_NS_PER_SEC;
        };

        // ============ TIMER ============

        struct Timer
        {
            i64 start, stop;
            bool running;
        };

        def timer_start(Timer* t) -> void
        {
            t.start   = time_now();
            t.stop    = 0;
            t.running = true;
        };

        // Stops the timer and returns elapsed nanoseconds.
        def timer_stop(Timer* t) -> i64
        {
            t.stop    = time_now();
            t.running = false;
            return t.stop - t.start;
        };

        // Read elapsed nanoseconds without stopping the timer.
        def timer_read(Timer* t) -> i64
        {
            if (t.running)
            {
                return time_now() - t.start;
            };
            return t.stop - t.start;
        };

        def timer_reset(Timer* t) -> void
        {
            t.start   = 0;
            t.stop    = 0;
            t.running = false;
        };

    };  // namespace time
};  // namespace standard

#endif;  // FLUX_STANDARD_TIME
