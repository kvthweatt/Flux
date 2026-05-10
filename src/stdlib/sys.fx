// Author: Karac V. Thweatt

// OS Detection Library
#ifndef FLUX_STANDARD
#def FLUX_STANDARD 1;
#endif;

#ifndef FLUX_STANDARD_SYSTEM
#def FLUX_STANDARD_SYSTEM 1;
#endif;

///
global const int OS_UNKNOWN = 0;
global const int OS_WINDOWS = 1;
global const int OS_LINUX = 2;
global const int OS_MACOS = 3;
///
#ifdef __WINDOWS__
#def CURRENT_OS 1;
extern
{
    def !!
        system(byte*) -> int,
        LoadLibraryA(byte*) -> void*,
        GetProcAddress(void*, byte*) -> void*,
        GetSystemInfo(void*) -> void;
};


// SYSTEM_INFO layout on x64 Windows:
//   0  DWORD  dwOemId
//   4  DWORD  dwPageSize
//   8  void*  lpMinimumApplicationAddress
//  16  void*  lpMaximumApplicationAddress
//  24  u64    dwActiveProcessorMask
//  32  DWORD  dwNumberOfProcessors
struct SYSTEM_INFO_PARTIAL
{
    u32   dwOemId,
          dwPageSize;
    void* lpMin,
          lpMax;
    u64   dwActiveProcessorMask;
    u32   dwNumberOfProcessors,
          dwProcessorType,
          dwAllocationGranularity;
    u16   wProcessorLevel,
          wProcessorRevision;
};
#endif;

#ifdef __LINUX__
#def CURRENT_OS 2;
#endif;

#ifdef __MACOS__
#def CURRENT_OS 3;
#endif;

namespace standard
{
    namespace system
    {
        namespace Windows
        {
        };
    };
};