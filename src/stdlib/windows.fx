// Author: Karac V. Thweatt

// Flux Windows GUI Library
// Provides clean wrapper around Win32 API for window creation and management
#ifndef FLUX_STANDARD_TYPES
#import "types.fx";
#endif;

#ifndef FLUX_STANDARD_MATH
#import "math.fx";
#endif;

using standard::math;

#ifndef __WIN32_INTERFACE__
#def __WIN32_INTERFACE__ 1;

namespace standard
{
    namespace system
    {
        namespace windows
        {
            // ============================================================================
            // WIN32 TYPE DEFINITIONS
            // ============================================================================

            // Handle types
            unsigned data{64} as HWND,      // Window handle
                                 HINSTANCE, // Instance handle
                                 HMENU,     // Menu handle
                                 HICON,     // Icon handle
                                 HCURSOR,   // Cursor handle
                                 HBRUSH,    // Brush handle
                                 HDC,       // Device context handle
                                 HGLRC;     // OpenGL rendering context handle

            // Basic Win32 types
            unsigned data{32} as UINT,
                                 DWORD,
                                 BYTE;

            unsigned data{16} as WORD;

            signed data{32} as LONG;

            // Pointer-sized types - must be 64-bit on x64
            unsigned data{64} as LONG_PTR,
                                 UINT_PTR,
                                 WPARAM,
                                 LPARAM,
                                 LRESULT;
            
            // HRESULT - standard COM return code
            signed data{32} as HRESULT;

            unsigned data{64} as HFONT;

            // String types
            byte* as LPCSTR,      // Pointer to const string
                     LPSTR;       // Pointer to string

            // Window procedure callback type (opaque function pointer - same size as void*)
            u64* as WNDPROC;

            // ============================================================================
            // WIN32 STRUCTURES
            // ============================================================================

            // MSG structure for message loop
            struct MSG
            {
                HWND hwnd;
                UINT message;
                WPARAM wParam;
                LPARAM lParam;
                DWORD time;
                POINT pt;
            };

            // WNDCLASSEXA structure for window class registration
            struct WNDCLASSEXA
            {
                UINT cbSize,style;
                WNDPROC lpfnWndProc;
                int cbClsExtra,cbWndExtra;
                HINSTANCE hInstance;
                HICON hIcon;
                HCURSOR hCursor;
                HBRUSH hbrBackground;
                LPCSTR lpszMenuName,lpszClassName;
                HICON hIconSm;
            };

            // RECT structure
            struct RECT
            {
                LONG left, top, right, bottom;
            };

            // PAINTSTRUCT for WM_PAINT
            struct PAINTSTRUCT
            {
                HDC hdc;              // 8 bytes, offset 0
                LONG fErase,          // 4 bytes, offset 8
                     _pad;            // 4 bytes padding, offset 12 -> RECT at 16
                RECT rcPaint;         // 16 bytes, offset 16
                LONG fRestore,        // 4 bytes, offset 32
                     fIncUpdate;      // 4 bytes, offset 36
                BYTE[32] rgbReserved; // 32 bytes, offset 40
            };            // total = 72 bytes

            // ============================================================================
            // WIN32 CONSTANTS
            // ============================================================================

            // Window Styles (WS_*)
            global DWORD WS_OVERLAPPED       = 0x00000000,
                         WS_POPUP            = 0x80000000,
                         WS_CHILD            = 0x40000000,
                         WS_MINIMIZE         = 0x20000000,
                         WS_VISIBLE          = 0x10000000,
                         WS_DISABLED         = 0x08000000,
                         WS_CLIPSIBLINGS     = 0x04000000,
                         WS_CLIPCHILDREN     = 0x02000000,
                         WS_MAXIMIZE         = 0x01000000,
                         WS_CAPTION          = 0x00C00000,
                         WS_BORDER           = 0x00800000,
                         WS_DLGFRAME         = 0x00400000,
                         WS_VSCROLL          = 0x00200000,
                         WS_HSCROLL          = 0x00100000,
                         WS_SYSMENU          = 0x00080000,
                         WS_THICKFRAME       = 0x00040000,
                         WS_GROUP            = 0x00020000,
                         WS_TABSTOP          = 0x00010000,
                         WS_MINIMIZEBOX      = 0x00020000,
                         WS_MAXIMIZEBOX      = 0x00010000,
                         WS_OVERLAPPEDWINDOW = 0x00CF0000; // WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX

            // Extended Window Styles (WS_EX_*)
            global DWORD WS_EX_DLGMODALFRAME = 0x00000001,
                         WS_EX_TOPMOST       = 0x00000008,
                         WS_EX_ACCEPTFILES   = 0x00000010,
                         WS_EX_TRANSPARENT   = 0x00000020,
                         WS_EX_CLIENTEDGE    = 0x00000200,
                         WS_EX_APPWINDOW     = 0x00040000;

            // Window Class Styles (CS_*)
            global UINT CS_VREDRAW = 0x0001,
                        CS_HREDRAW = 0x0002,
                        CS_OWNDC   = 0x0020;

            // ShowWindow Commands (SW_*)
            global int SW_HIDE            = 0,
                       SW_SHOWNORMAL      = 1,
                       SW_NORMAL          = 1,
                       SW_SHOWMINIMIZED   = 2,
                       SW_SHOWMAXIMIZED   = 3,
                       SW_MAXIMIZE        = 3,
                       SW_SHOWNOACTIVATE  = 4,
                       SW_SHOW            = 5,
                       SW_MINIMIZE        = 6,
                       SW_SHOWMINNOACTIVE = 7,
                       SW_SHOWNA          = 8,
                       SW_RESTORE         = 9;

            // Window Messages (WM_*)
            global UINT WM_NULL        = 0x0000,
                        WM_CREATE      = 0x0001,
                        WM_DESTROY     = 0x0002,
                        WM_MOVE        = 0x0003,
                        WM_SIZE        = 0x0005,
                        WM_ACTIVATE    = 0x0006,
                        WM_PAINT       = 0x000F,
                        WM_ERASEBKGND  = 0x0014,
                        WM_CLOSE       = 0x0010,
                        WM_QUIT        = 0x0012,
                        WM_KEYDOWN     = 0x0100,
                        WM_KEYUP       = 0x0101,
                        WM_CHAR        = 0x0102,
                        WM_MOUSEMOVE   = 0x0200,
                        WM_LBUTTONDOWN = 0x0201,
                        WM_LBUTTONUP   = 0x0202,
                        WM_RBUTTONDOWN = 0x0204,
                        WM_RBUTTONUP   = 0x0205;

            // PeekMessage flags (PM_*)
            global UINT PM_NOREMOVE = 0x0000,
                        PM_REMOVE   = 0x0001,
                        PM_NOYIELD  = 0x0002;

            // GetStockObject constants
            global int NULL_BRUSH  = 5,
                       WHITE_BRUSH = 0,
                       BLACK_BRUSH = 4,
                       BLACK_BRUSH = 4,
                       NULL_PEN    = 8;

            // CW_USEDEFAULT
            global int CW_USEDEFAULT = 0x80000000;

            // Virtual Key Codes
            global int VK_ESCAPE   = 0x1B,
                       VK_SPACE   = 0x20,
                       VK_BACK    = 0x08,
                       VK_TAB     = 0x09,
                       VK_DELETE  = 0x2E,
                       VK_LEFT    = 0x25,
                       VK_RIGHT   = 0x27,
                       VK_UP      = 0x26,
                       VK_DOWN    = 0x28,
                       VK_LBUTTON = 0x01,
                       VK_HOME    = 0x24,
                       VK_END     = 0x23,
                       VK_PRIOR   = 0x21,
                       VK_NEXT    = 0x22,
                       VK_RETURN  = 0x0D,
                       VK_SHIFT   = 0x10,
                       VK_CONTROL = 0x11,
                       VK_OEM_PLUS  = 0x0BB,
                       VK_OEM_MINUS = 0xBD;

            // Pen styles (CreatePen)
            global int PS_SOLID      = 0,
                       PS_DASH       = 1,
                       PS_DOT        = 2,
                       PS_DASHDOT    = 3,
                       PS_DASHDOTDOT = 4,
                       PS_NULL       = 5;

            // Background modes (SetBkMode)
            global int TRANSPARENT = 1,
                       OPAQUE      = 2;

            // RGB color helper - packs R,G,B into a COLORREF (0x00BBGGRR)
            def RGB(byte r, byte g, byte b) -> DWORD
            {
                return (DWORD)r | ((DWORD)g << 8) | ((DWORD)b << 16);
            };

            // ============================================================================
            // WIN32 FUNCTION DECLARATIONS (EXTERN)
            // ============================================================================

            extern
            {
                def !!
                    GetModuleHandleA(LPCSTR) -> HINSTANCE,
                
                // Window Class functions
                    RegisterClassExA(WNDCLASSEXA*) -> WORD,
                    UnregisterClassA(LPCSTR, HINSTANCE) -> bool,
                
                // Window Creation/Destruction
                    CreateWindowExA(DWORD, LPCSTR, LPCSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, void*) -> HWND,
                    DestroyWindow(HWND) -> bool,
                
                // Window Display
                    ShowWindow(HWND, int) -> bool,
                    UpdateWindow(HWND) -> bool,
                
                // Window Properties
                    SetWindowTextA(HWND, LPCSTR) -> bool,
                    GetWindowTextA(HWND, LPSTR, int) -> int,
                    SetWindowPos(HWND, HWND, int, int, int, int, UINT) -> bool,
                    SetForegroundWindow(HWND) -> bool,
                    BringWindowToTop(HWND) -> bool,
                    SetFocus(HWND) -> HWND,
                    InvalidateRect(HWND, RECT*, bool) -> bool,
                    GetClientRect(HWND, RECT*) -> bool,
                    GetWindowRect(HWND, RECT*) -> bool,
                
                // Message Loop
                    GetMessageA(MSG*, HWND, UINT, UINT) -> bool,
                    PeekMessageA(MSG*, HWND, UINT, UINT, UINT) -> bool,
                    TranslateMessage(MSG*) -> bool,
                    DispatchMessageA(MSG*) -> LRESULT,
                    PostQuitMessage(int) -> void,
                
                // Window Procedure
                    DefWindowProcA(HWND, UINT, WPARAM, LPARAM) -> LRESULT,
                
                // GDI functions
                    BeginPaint(HWND, PAINTSTRUCT*) -> HDC,
                    EndPaint(HWND, PAINTSTRUCT*) -> bool,
                    GetDC(HWND) -> HDC,
                    ReleaseDC(HWND, HDC) -> int,

                // GDI drawing
                    MoveToEx(HDC, int, int, POINT*) -> bool,
                    LineTo(HDC, int, int) -> bool,
                    Ellipse(HDC, int, int, int, int) -> bool,
                    Rectangle(HDC, int, int, int, int) -> bool,
                    FillRect(HDC, RECT*, HBRUSH) -> int,
                    SetPixel(HDC, int, int, DWORD) -> DWORD,
                    Arc(HDC, int, int, int, int, int, int, int, int) -> bool,
                    Polyline(HDC, POINT*, int) -> bool,
                    Polygon(HDC, POINT*, int) -> bool,

                // GDI pen and brush
                    CreatePen(int, int, DWORD) -> HDC,
                    CreateSolidBrush(DWORD) -> HBRUSH,
                    SelectObject(HDC, HDC) -> HDC,
                    DeleteObject(HDC) -> bool,

                // GDI back-buffer (double buffering)
                    CreateCompatibleDC(HDC) -> HDC,
                    CreateCompatibleBitmap(HDC, int, int) -> HDC,
                    BitBlt(HDC, int, int, int, int, HDC, int, int, DWORD) -> bool,
                    DeleteDC(HDC) -> bool,

                // GDI color and mode
                    SetBkMode(HDC, int) -> int,
                    SetBkColor(HDC, DWORD) -> DWORD,
                    SetTextColor(HDC, DWORD) -> DWORD,
                    TextOutA(HDC, int, int, LPCSTR, int) -> bool,

                // Console window access
                    GetConsoleWindow() -> HWND,

                // Stock Objects
                    GetStockObject(int) -> HBRUSH,
                
                // Cursor and Icon
                    GetCursorPos(POINT*) -> bool,
                    LoadCursorA(HINSTANCE, LPCSTR) -> HCURSOR,
                    LoadIconA(HINSTANCE, LPCSTR) -> HICON,
                    GetAsyncKeyState(int) -> WORD,

                // Menu GUI
                    ScreenToClient(void*, POINT*) -> bool,
                    CreateMenu() -> HMENU,
                    CreatePopupMenu() -> HMENU,
                    AppendMenuA(HMENU, UINT, UINT_PTR, LPCSTR) -> bool,
                    SetMenu(HWND, HMENU) -> bool,
                    SendMessageA(HWND, UINT, WPARAM, LPARAM) -> LRESULT,
                    GetWindowTextLengthA(HWND) -> int,
                    MoveWindow(HWND, int, int, int, int, bool) -> bool,
                    MessageBoxA(HWND, LPCSTR, LPCSTR, UINT) -> int,
                    GetOpenFileNameA(void*) -> bool,
                    GetSaveFileNameA(void*) -> bool,
                    CreateFileA(LPCSTR, DWORD, DWORD, void*, DWORD, DWORD, HWND) -> HWND,
                    ReadFile(HWND, void*, DWORD, DWORD*, void*) -> bool,
                    WriteFile(HWND, void*, DWORD, DWORD*, void*) -> bool,
                    CloseHandle(HWND) -> bool,
                    GetFileSizeEx(HWND, i64*) -> bool,
                    GetSystemMetrics(int) -> int,
                    FreeConsole() -> bool,
                    CreateFontA(int, int, int, int, int, DWORD, DWORD, DWORD,
                                DWORD, DWORD, DWORD, DWORD, DWORD, LPCSTR) -> HFONT,
                    SetWindowTheme(HWND, LPCSTR, LPCSTR) -> HRESULT,
                    DwmSetWindowAttribute(HWND, DWORD, void*, DWORD) -> HRESULT,
                    GetTextMetricsA(HDC, void*) -> bool,
                    SetScrollInfo(HWND, int, void*, bool) -> int,
                    GetScrollInfo(HWND, int, void*) -> bool,
                    SetCapture(HWND) -> HWND,
                    ReleaseCapture() -> bool,
                    ExtTextOutA(HDC, int, int, UINT, RECT*, LPCSTR, UINT, void*) -> bool,
                    OpenClipboard(HWND) -> bool,
                    CloseClipboard() -> bool,
                    EmptyClipboard() -> bool,
                    SetClipboardData(UINT, HWND) -> HWND,
                    GetClipboardData(UINT) -> HWND,
                    GlobalAlloc(UINT, size_t) -> HWND,
                    GlobalLock(HWND) -> void*,
                    GlobalUnlock(HWND) -> bool,
                    GlobalSize(HWND) -> size_t,
                    CreateCompatibleDC(HDC) -> HDC,
                    CreateCompatibleBitmap(HDC, int, int) -> HDC,
                    BitBlt(HDC, int, int, int, int, HDC, int, int, DWORD) -> bool,
                    DeleteDC(HDC) -> bool,
                    DeleteObject(HDC) -> bool,
                    BeginPaint(HWND, void*) -> HDC,
                    EndPaint(HWND, void*) -> bool,
                    FillRect(HDC, RECT*, HBRUSH) -> int,
                    SetTextColor(HDC, DWORD) -> DWORD,
                    SetBkColor(HDC, DWORD) -> DWORD,
                    SetBkMode(HDC, int) -> int,
                    snprintf(byte*, size_t, byte*, int) -> int;
            };

            // ============================================================================
            // CONSTANTS
            // ============================================================================

            global DWORD ES_MULTILINE         = 0x0004,
                         ES_AUTOVSCROLL       = 0x0040,
                         ES_AUTOHSCROLL       = 0x0080,
                         ES_NOHIDESEL         = 0x0100,
                         ES_WANTRETURN        = 0x1000,
                         OFN_FILEMUSTEXIST    = 0x00001000,
                         OFN_PATHMUSTEXIST    = 0x00000800,
                         OFN_OVERWRITEPROMPT  = 0x00000002,
                         OFN_HIDEREADONLY     = 0x00000004;

            global UINT WM_SETFOCUS        = 0x0007,
                        WM_KILLFOCUS       = 0x0008,
                        WM_ERASEBKGND      = 0x0014,
                        WM_LBUTTONDOWN     = 0x0201,
                        WM_LBUTTONUP       = 0x0202,
                        WM_MOUSEMOVE       = 0x0200,
                        WM_COMMAND         = 0x0111,
                        WM_CUT             = 0x0300,
                        WM_COPY            = 0x0301,
                        WM_PASTE           = 0x0302,
                        WM_UNDO            = 0x0304,
                        WM_SETFONT         = 0x0030,
                        WM_CHAR            = 0x0102,
                        WM_VSCROLL         = 0x0115,
                        WM_HSCROLL         = 0x0114,
                        EN_CHANGE     = 0x0300,
                        EM_SETSEL     = 0x00B1,
                        MF_STRING     = 0x0000,
                        MF_SEPARATOR  = 0x0800,
                        MF_POPUP      = 0x0010,
                        MB_YESNOCANCEL  = 0x0003,
                        MB_ICONQUESTION = 0x0020;

            global int IDM_NEW = 1001, IDM_OPEN    = 1002, IDM_SAVE  = 1003,
                       IDM_SAVEAS = 1004, IDM_EXIT = 1005, IDM_UNDO  = 2001,
                       IDM_CUT  = 2002, IDM_COPY   = 2003, IDM_PASTE = 2004,
                       IDM_SELECTALL = 2005, IDM_ABOUT = 3001,
                       IDM_EDIT_CTRL = 100,
                       IDYES = 6, IDNO = 7, IDCANCEL = 2;

            // ============================================================================
            // OPENFILENAME STRUCT
            // ============================================================================

            struct OPENFILENAMEA
            {
                DWORD  lStructSize;
                DWORD  _pad0;
                HWND   hwndOwner, hInstance;
                LPCSTR lpstrFilter;
                LPSTR  lpstrCustomFilter;
                DWORD  nMaxCustFilter, nFilterIndex;
                LPSTR  lpstrFile;
                DWORD  nMaxFile;
                DWORD  _pad1;
                LPSTR  lpstrFileTitle;
                DWORD  nMaxFileTitle;
                DWORD  _pad2;
                LPCSTR lpstrInitialDir, lpstrTitle;
                DWORD  Flags;
                WORD   nFileOffset, nFileExtension;
                LPCSTR lpstrDefExt;
                LPARAM lCustData;
                HWND   lpfnHook;
                LPCSTR lpTemplateName;
                void*  pvReserved;
                DWORD  dwReserved, FlagsEx;
            };

            // ============================================================================
            // DEFAULT WINDOW PROCEDURE
            // ============================================================================

            // Default window procedure - handles basic messages
            def DefaultWindowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) -> LRESULT
            {
                if (msg == WM_CLOSE)
                {
                    DestroyWindow(hwnd);
                    return 0;
                };
                
                if (msg == WM_DESTROY)
                {
                    PostQuitMessage(0);
                    return 0;
                };

                if (msg == WM_ERASEBKGND)
                {
                    return 1;
                };

                if (msg == WM_PAINT)
                {
                    PAINTSTRUCT ps;
                    BeginPaint(hwnd, @ps);
                    EndPaint(hwnd, @ps);
                    return 0;
                };

                
                return DefWindowProcA(hwnd, msg, wParam, lParam);
            };

            // ============================================================================
            // WINDOW OBJECT
            // ============================================================================

            object Window
            {
                HWND handle;
                HINSTANCE instance;
                HDC device_context;
                int width,
                    height,
                    x_pos,
                    y_pos;
                bool is_visible;
                byte[256] class_name;
                
                // Constructor - creates and shows window
                def __init(byte* title, int w, int h, int x, int y) -> this
                {
                    this.width = w;
                    this.height = h;
                    this.x_pos = x;
                    this.y_pos = y;
                    this.is_visible = false;
                    
                    // Get instance handle
                    this.instance = GetModuleHandleA((LPCSTR)0);
                    
                    // Generate unique class name
                    noopstr fwindow = "Flux Window\0";
                    this.class_name = fwindow;
                    
                    // Set up window class
                    WNDCLASSEXA wc;
                    wc.cbSize        = (UINT)(sizeof(WNDCLASSEXA) / 8); // sizeof returns bits, cbSize needs bytes
                    wc.style         = CS_HREDRAW | CS_VREDRAW | CS_OWNDC;
                    wc.lpfnWndProc   = (WNDPROC)@DefaultWindowProc;
                    wc.cbClsExtra    = 0;
                    wc.cbWndExtra    = 0;
                    wc.hInstance     = this.instance;
                    wc.hIcon         = LoadIconA((HINSTANCE)0, (LPCSTR)32512); // IDI_APPLICATION
                    wc.hCursor       = LoadCursorA((HINSTANCE)0, (LPCSTR)32512); // IDC_ARROW
                    wc.hbrBackground = GetStockObject(BLACK_BRUSH);
                    wc.lpszMenuName  = (LPCSTR)0;
                    wc.lpszClassName = (LPCSTR)this.class_name;
                    wc.hIconSm       = (HICON)0;
                    
                    // Register window class
                    RegisterClassExA(@wc);
                    
                    // Create window
                    this.handle = CreateWindowExA(WS_EX_APPWINDOW,
                                                  (LPCSTR)this.class_name,
                                                  (LPCSTR)title,
                                                  WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                                  x, y, w, h,
                                                  (HWND)0,
                                                  (HMENU)0,
                                                  this.instance,
                                                  STDLIB_GVP);
                    
                    // Get device context
                    this.device_context = GetDC(this.handle);
                    
                    // Show and update window
                    ShowWindow(this.handle, SW_SHOW);
                    UpdateWindow(this.handle);
                    this.is_visible = true;
                    
                    return this;
                };
                
                // Destructor
                def __exit() -> void
                {
                    if (this.device_context != 0)
                    {
                        ReleaseDC(this.handle, this.device_context);
                    };
                    
                    UnregisterClassA((LPCSTR)this.class_name, this.instance);
                    return;
                };

                // Return window handle
                def __expr() -> HWND
                {
                    return this.handle;
                };
                
                // Show window
                def show() -> void
                {
                    ShowWindow(this.handle, SW_SHOW);
                    this.is_visible = true;
                    return;
                };
                
                // Hide window
                def hide() -> void
                {
                    ShowWindow(this.handle, SW_HIDE);
                    this.is_visible = false;
                    return;
                };
                
                // Set window title
                def set_title(byte* title) -> void
                {
                    SetWindowTextA(this.handle, (LPCSTR)title);
                    return;
                };
                
                // Process messages (non-blocking)
                def process_messages() -> bool
                {
                    MSG msg;
                    
                    while (PeekMessageA(@msg, (HWND)0, 0, 0, PM_REMOVE))
                    {
                        if (msg.message == WM_QUIT)
                        {
                            return false;
                        };
                        
                        TranslateMessage(@msg);
                        DispatchMessageA(@msg);
                    };
                    
                    return true;
                };
                
            };
            // ============================================================================
            // CANVAS - GDI drawing surface over the console window
            // ============================================================================

            object Canvas
            {
                HWND  hwnd;
                HDC   hdc,
                      back_dc,
                      back_bmp;
                RECT  bounds;
                HDC   active_pen;

                // Attach to a Window's HDC for drawing
                def __init(HWND hwnd, HDC hdc) -> this
                {
                    this.hwnd = hwnd;
                    this.hdc  = hdc;
                    GetClientRect(this.hwnd, @this.bounds);
                    this.active_pen = (HDC)0;
                    int w = this.bounds.right  - this.bounds.left;
                    int h = this.bounds.bottom - this.bounds.top;
                    this.back_dc  = CreateCompatibleDC(hdc);
                    this.back_bmp = CreateCompatibleBitmap(hdc, w, h);
                    SelectObject(this.back_dc, this.back_bmp);
                    return this;
                };

                // Release DC when done
                def __exit() -> void
                {
                    if (this.active_pen != (HDC)0)
                    {
                        SelectObject(this.back_dc, GetStockObject(NULL_PEN));
                        DeleteObject(this.active_pen);
                    };
                    DeleteObject(this.back_bmp);
                    DeleteDC(this.back_dc);
                    return;
                };

                // Returns this.hwnd
                def __expr() -> HWND
                {
                    return this.hwnd;
                };

                // Clear the canvas with a solid color
                def clear(DWORD color) -> void
                {
                    int w = this.bounds.right  - this.bounds.left;
                    int h = this.bounds.bottom - this.bounds.top;
                    BitBlt(this.hdc, 0, 0, w, h, this.back_dc, 0, 0, (DWORD)0x00CC0020);
                    HBRUSH brush = CreateSolidBrush(color);
                    FillRect(this.back_dc, @this.bounds, brush);
                    SelectObject(this.back_dc, GetStockObject(NULL_BRUSH));
                    DeleteObject(brush);
                    return;
                };

                // Set the active pen color and width
                def set_pen(DWORD color, int width) -> void
                {
                    if (this.active_pen != (HDC)0)
                    {
                        SelectObject(this.back_dc, GetStockObject(NULL_PEN));
                        DeleteObject(this.active_pen);
                    };
                    this.active_pen = CreatePen(PS_SOLID, width, color);
                    SelectObject(this.back_dc, this.active_pen);
                    return;
                };

                // Draw a line between two points
                def line(int x1, int y1, int x2, int y2) -> void
                {
                    MoveToEx(this.back_dc, x1, y1, (POINT*)0);
                    LineTo(this.back_dc, x2, y2);
                    return;
                };

                // Draw a circle by bounding box center+radius
                def circle(int cx, int cy, int r) -> void
                {
                    Ellipse(this.back_dc, cx - r, cy - r, cx + r, cy + r);
                    return;
                };

                // Draw an ellipse by bounding box
                def ellipse(int x1, int y1, int x2, int y2) -> void
                {
                    Ellipse(this.back_dc, x1, y1, x2, y2);
                    return;
                };

                // Draw a rectangle
                def rect(int x1, int y1, int x2, int y2) -> void
                {
                    Rectangle(this.back_dc, x1, y1, x2, y2);
                    return;
                };

                // Set a single pixel
                def pixel(int x, int y, DWORD color) -> void
                {
                    SetPixel(this.back_dc, x, y, color);
                    return;
                };

                // Refresh bounds (call if console is resized)
                def refresh_bounds() -> void
                {
                    GetClientRect(this.hwnd, @this.bounds);
                    return;
                };

                // Width and height helpers
                def width() -> int
                {
                    return this.bounds.right - this.bounds.left;
                };

                def height() -> int
                {
                    return this.bounds.bottom - this.bounds.top;
                };
            };
        };
    };
};

#endif;