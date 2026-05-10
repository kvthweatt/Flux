// Author: Karac V. Thweatt

// Flux OpenGL Library
// Provides OpenGL context setup and rendering helpers via Win32 WGL
#ifndef __WIN32_INTERFACE__
#import "windows.fx";
#endif;

#ifndef __REDOPENGL__
#def __REDOPENGL__ 1;

namespace standard
{
    namespace system
    {
        namespace windows
        {
            // ============================================================================
            // PIXELFORMATDESCRIPTOR - required for OpenGL context creation
            // ============================================================================

            // PIXELFORMATDESCRIPTOR for OpenGL
            struct PIXELFORMATDESCRIPTOR
            {
                WORD nSize,
                     nVersion;
                DWORD dwFlags;
                BYTE iPixelType,
                     cColorBits,
                     cRedBits,
                     cRedShift,
                     cGreenBits,
                     cGreenShift,
                     cBlueBits,
                     cBlueShift,
                     cAlphaBits,
                     cAlphaShift,
                     cAccumBits,
                     cAccumRedBits,
                     cAccumGreenBits,
                     cAccumBlueBits,
                     cAccumAlphaBits,
                     cDepthBits,
                     cStencilBits,
                     cAuxBuffers,
                     iLayerType,
                     bReserved;
                DWORD dwLayerMask,
                      dwVisibleMask,
                      dwDamageMask;
            };

            // ============================================================================
            // OPENGL / PFD CONSTANTS
            // ============================================================================

            // Pixel Format Descriptor flags
            global DWORD PFD_DRAW_TO_WINDOW = 0x00000004,
                         PFD_SUPPORT_OPENGL = 0x00000020,
                         PFD_DOUBLEBUFFER   = 0x00000001;
            global BYTE PFD_TYPE_RGBA  = 0,
                        PFD_MAIN_PLANE = 0;

            // ============================================================================
            // OPENGL EXTERN FUNCTION DECLARATIONS
            // ============================================================================

            extern
            {
                def !!
                    ChoosePixelFormat(HDC, PIXELFORMATDESCRIPTOR*) -> int,
                    SetPixelFormat(HDC, int, PIXELFORMATDESCRIPTOR*) -> bool,
                    wglCreateContext(HDC) -> HGLRC,
                    wglMakeCurrent(HDC, HGLRC) -> bool,
                    wglDeleteContext(HGLRC) -> bool,
                    wglGetProcAddress(LPCSTR) -> void*,
                    SwapBuffers(HDC) -> bool;
            };

            // ============================================================================
            // OPENGL CONTEXT HELPERS
            // ============================================================================

            // Create and activate an OpenGL context for the given device context
            def setup_opengl(HDC device_context) -> HGLRC
            {
                PIXELFORMATDESCRIPTOR pfd;
                pfd.nSize = (WORD)(sizeof(PIXELFORMATDESCRIPTOR) / 8); // sizeof returns bits, nSize needs bytes
                pfd.nVersion = 1;
                pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
                pfd.iPixelType = PFD_TYPE_RGBA;
                pfd.cColorBits = 32;
                pfd.cDepthBits = 24;
                pfd.cStencilBits = 8;
                pfd.iLayerType = PFD_MAIN_PLANE;

                int pixel_format = ChoosePixelFormat(device_context, @pfd);
                SetPixelFormat(device_context, pixel_format, @pfd);

                HGLRC gl_context = wglCreateContext(device_context);
                wglMakeCurrent(device_context, gl_context);

                return gl_context;
            };

            // Swap front/back buffers for double-buffered OpenGL rendering
            def swap_buffers(HDC device_context) -> void
            {
                SwapBuffers(device_context);
                return;
            };
        };
    };
};

// ============================================================================
// GL EXTENSION FUNCTION POINTERS
// ============================================================================

def{}* glCreateShader_fp(int)                 -> int,
       glShaderSource_fp(int,int,byte**,int*) -> void,
       glCompileShader_fp(int)                -> void,
       glCreateProgram_fp()                   -> int,
       glAttachShader_fp(int,int)             -> void,
       glLinkProgram_fp(int)                  -> void,
       glUseProgram_fp(int)                   -> void,
       glGetUniformLocation_fp(int,byte*)     -> int,
       glUniform1i_fp(int,int)                -> void,
       glUniform2f_fp(int,float,float)        -> void,
       glActiveTexture_fp(int)                -> void,
       glDeleteShader_fp(int)                 -> void,
       glDeleteProgram_fp(int)                -> void;

def compile_shader(int shader_type, byte* src) -> int
{
    int shader = glCreateShader_fp(shader_type);
    byte[1]* src_arr = [src];
    int[1]   len_arr = [-1];
    glShaderSource_fp(shader, 1, @src_arr[0], @len_arr[0]);
    glCompileShader_fp(shader);
    return shader;
};

def link_program(int vert, int frag) -> int
{
    int prog = glCreateProgram_fp();
    glAttachShader_fp(prog, vert);
    glAttachShader_fp(prog, frag);
    glLinkProgram_fp(prog);
    return prog;
};

// ============================================================================
// OPENGL TYPES
// ============================================================================

// OpenGL base types
byte              as GLenum;     // Enumeration values (GL_*)
byte              as GLboolean;  // Boolean (GL_TRUE / GL_FALSE)
uint              as GLbitfield; // Bitfield for glClear etc.
signed byte       as GLbyte;     // Signed 8-bit
byte              as GLubyte;    // Unsigned 8-bit
i16               as GLshort;    // Signed 16-bit
u16               as GLushort;   // Unsigned 16-bit
int               as GLint;      // Signed 32-bit
uint              as GLuint;     // Unsigned 32-bit (handles: textures, VBOs, VAOs, shaders, programs)
int               as GLsizei;    // Size parameter (non-negative)
float             as GLfloat;     // 32-bit float (mapped via u64 placeholder like redtypes.fx)
u64               as GLdouble;    // 64-bit double
u64               as GLclampf;    // float clamped [0,1]

// ============================================================================
// OPENGL CONSTANTS
// ============================================================================

// Boolean
GLboolean GL_FALSE = 0,
                 GL_TRUE  = 1;

// Error codes
GLenum GL_NO_ERROR          = 0x00,
              GL_INVALID_ENUM      = 0x00,
              GL_INVALID_VALUE     = 0x00,
              GL_INVALID_OPERATION = 0x00,
              GL_OUT_OF_MEMORY     = 0x00;

int GL_NO_ERROR_INT          = 0x0000,
           GL_INVALID_ENUM_INT      = 0x0500,
           GL_INVALID_VALUE_INT     = 0x0501,
           GL_INVALID_OPERATION_INT = 0x0502,
           GL_STACK_OVERFLOW_INT    = 0x0503,
           GL_STACK_UNDERFLOW_INT   = 0x0504,
           GL_OUT_OF_MEMORY_INT     = 0x0505;

// Clear buffer bits
int GL_COLOR_BUFFER_BIT   = 0x00004000,
           GL_DEPTH_BUFFER_BIT   = 0x00000100,
           GL_STENCIL_BUFFER_BIT = 0x00000400,
           GL_ACCUM_BUFFER_BIT   = 0x00000200;

// Primitives
int GL_POINTS         = 0x0000,
           GL_LINES          = 0x0001,
           GL_LINE_LOOP      = 0x0002,
           GL_LINE_STRIP     = 0x0003,
           GL_TRIANGLES      = 0x0004,
           GL_TRIANGLE_STRIP = 0x0005,
           GL_TRIANGLE_FAN   = 0x0006,
           GL_QUADS          = 0x0007,
           GL_QUAD_STRIP     = 0x0008,
           GL_POLYGON        = 0x0009;

// Data types
int GL_BYTE           = 0x1400,
           GL_UNSIGNED_BYTE  = 0x1401,
           GL_SHORT          = 0x1402,
           GL_UNSIGNED_SHORT = 0x1403,
           GL_INT            = 0x1404,
           GL_UNSIGNED_INT   = 0x1405,
           GL_FLOAT          = 0x1406,
           GL_DOUBLE         = 0x140A;

// Matrix modes
int GL_MODELVIEW  = 0x1700,
           GL_PROJECTION = 0x1701,
           GL_TEXTURE    = 0x1702;

// Depth / comparison functions
int GL_NEVER    = 0x0200,
           GL_LESS      = 0x0201,
           GL_EQUAL     = 0x0202,
           GL_LEQUAL    = 0x0203,
           GL_GREATER   = 0x0204,
           GL_NOTEQUAL  = 0x0205,
           GL_GEQUAL    = 0x0206,
           GL_ALWAYS    = 0x0207;

// Blend factors
int GL_ZERO                 = 0x0000,
           GL_ONE                  = 0x0001,
           GL_SRC_COLOR            = 0x0300,
           GL_ONE_MINUS_SRC_COLOR  = 0x0301,
           GL_SRC_ALPHA            = 0x0302,
           GL_ONE_MINUS_SRC_ALPHA  = 0x0303,
           GL_DST_ALPHA            = 0x0304,
           GL_ONE_MINUS_DST_ALPHA  = 0x0305,
           GL_DST_COLOR            = 0x0306,
           GL_ONE_MINUS_DST_COLOR  = 0x0307;

// Capability flags (for glEnable / glDisable)
int GL_DEPTH_TEST           = 0x0B71,
           GL_BLEND                = 0x0BE2,
           GL_CULL_FACE            = 0x0B44,
           GL_LIGHTING             = 0x0B50,
           GL_TEXTURE_2D           = 0x0DE1,
           GL_SCISSOR_TEST         = 0x0C11,
           GL_LINE_SMOOTH          = 0x0B20,
           GL_POINT_SMOOTH         = 0x0B10,
           GL_NORMALIZE            = 0x0BA1,
           GL_FOG                  = 0x0B60,
           GL_STENCIL_TEST         = 0x0B90,
           GL_ALPHA_TEST           = 0x0BC0,
           GL_COLOR_LOGIC_OP       = 0x0BF2,
           GL_POLYGON_OFFSET_FILL  = 0x8037,
           GL_MULTISAMPLE          = 0x809D;

// Cull face / winding
int GL_FRONT          = 0x0404,
           GL_BACK           = 0x0405,
           GL_FRONT_AND_BACK = 0x0408,
           GL_CW             = 0x0900,
           GL_CCW            = 0x0901;

// Polygon fill mode
int GL_POINT = 0x1B00,
           GL_LINE  = 0x1B01,
           GL_FILL  = 0x1B02;

// Shade model
int GL_FLAT   = 0x1D00,
           GL_SMOOTH = 0x1D01;

// Texture parameters
int GL_TEXTURE_MAG_FILTER      = 0x2800,
           GL_TEXTURE_MIN_FILTER      = 0x2801,
           GL_TEXTURE_WRAP_S          = 0x2802,
           GL_TEXTURE_WRAP_T          = 0x2803,
           GL_NEAREST                 = 0x2600,
           GL_LINEAR                  = 0x2601,
           GL_NEAREST_MIPMAP_NEAREST  = 0x2700,
           GL_LINEAR_MIPMAP_NEAREST   = 0x2701,
           GL_NEAREST_MIPMAP_LINEAR   = 0x2702,
           GL_LINEAR_MIPMAP_LINEAR    = 0x2703,
           GL_CLAMP                   = 0x2900,
           GL_REPEAT                  = 0x2901,
           GL_CLAMP_TO_EDGE           = 0x812F;

// Texture formats / internal formats
int GL_RGB             = 0x1907,
           GL_RGBA            = 0x1908,
           GL_LUMINANCE       = 0x1909,
           GL_LUMINANCE_ALPHA = 0x190A,
           GL_DEPTH_COMPONENT = 0x1902,
           GL_ALPHA           = 0x1906,
           GL_RGB8            = 0x8051,
           GL_RGBA8           = 0x8058,
           GL_DEPTH_COMPONENT16 = 0x81A5,
           GL_DEPTH_COMPONENT24 = 0x81A6;

// Buffer object targets
int GL_ARRAY_BUFFER         = 0x8892,
           GL_ELEMENT_ARRAY_BUFFER = 0x8893,
           GL_UNIFORM_BUFFER       = 0x8A11;

// Buffer usage hints
int GL_STREAM_DRAW  = 0x88E0,
           GL_STREAM_READ  = 0x88E1,
           GL_STATIC_DRAW  = 0x88E4,
           GL_STATIC_READ  = 0x88E5,
           GL_DYNAMIC_DRAW = 0x88E8,
           GL_DYNAMIC_READ = 0x88E9;

// Shader types
int GL_FRAGMENT_SHADER = 0x8B30,
           GL_VERTEX_SHADER   = 0x8B31,
           GL_GEOMETRY_SHADER = 0x8DD9;

// Shader / program status query tokens
int GL_COMPILE_STATUS  = 0x8B81,
           GL_LINK_STATUS     = 0x8B82,
           GL_INFO_LOG_LENGTH = 0x8B84,
           GL_SHADER_TYPE     = 0x8B4F,
           GL_DELETE_STATUS   = 0x8B80;

// Framebuffer targets and attachment points
int GL_FRAMEBUFFER              = 0x8D40,
           GL_RENDERBUFFER             = 0x8D41,
           GL_COLOR_ATTACHMENT0        = 0x8CE0,
           GL_DEPTH_ATTACHMENT         = 0x8D00,
           GL_STENCIL_ATTACHMENT       = 0x8D20,
           GL_FRAMEBUFFER_COMPLETE     = 0x8CD5,
           GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT       = 0x8CD6,
           GL_FRAMEBUFFER_INCOMPLETE_MISSING_ATTACHMENT = 0x8CD7,
           GL_FRAMEBUFFER_UNSUPPORTED  = 0x8CDD;

// String query tokens
int GL_VENDOR     = 0x1F00,
           GL_RENDERER   = 0x1F01,
           GL_VERSION    = 0x1F02,
           GL_EXTENSIONS = 0x1F03;

// Active texture units
int GL_TEXTURE0  = 0x84C0,
           GL_TEXTURE1  = 0x84C1,
           GL_TEXTURE2  = 0x84C2,
           GL_TEXTURE3  = 0x84C3,
           GL_TEXTURE4  = 0x84C4,
           GL_TEXTURE5  = 0x84C5,
           GL_TEXTURE6  = 0x84C6,
           GL_TEXTURE7  = 0x84C7;

// Fixed-function lighting constants
int GL_LIGHT0     = 0x4000,
           GL_LIGHT1     = 0x4001,
           GL_LIGHT2     = 0x4002,
           GL_LIGHT3     = 0x4003,
           GL_AMBIENT    = 0x1200,
           GL_DIFFUSE    = 0x1201,
           GL_SPECULAR   = 0x1202,
           GL_POSITION   = 0x1203,
           GL_SHININESS  = 0x1601,
           GL_EMISSION   = 0x1600;

// Misc get tokens
int GL_VIEWPORT          = 0x0BA2,
           GL_MAX_TEXTURE_SIZE  = 0x0D33,
           GL_MAX_VIEWPORT_DIMS = 0x0D3A;

// ============================================================================
// OPENGL CORE FUNCTION DECLARATIONS (opengl32.dll - always available)
// ============================================================================

extern
{
    def !!
        // State management
        glEnable(int) -> void,
        glDisable(int) -> void,
        glIsEnabled(int) -> GLboolean,
        glGetError() -> int,
        glGetIntegerv(int, int*) -> void,
        glGetFloatv(int, float*) -> void,
        glGetString(int) -> byte*,
        glFinish() -> void,
        glFlush() -> void,

        // Clearing
        glClear(int) -> void,
        glClearColor(float, float, float, float) -> void,
        glClearDepth(float) -> void,
        glClearStencil(int) -> void,

        // Viewport and scissor
        glViewport(int, int, int, int) -> void,
        glScissor(int, int, int, int) -> void,

        // Depth
        glDepthFunc(int) -> void,
        glDepthMask(GLboolean) -> void,
        glDepthRange(float, float) -> void,

        // Blending
        glBlendFunc(int, int) -> void,
        glBlendEquation(int) -> void,

        // Face culling and winding
        glCullFace(int) -> void,
        glFrontFace(int) -> void,

        // Polygon
        glPolygonMode(int, int) -> void,
        glPolygonOffset(float, float) -> void,
        glLineWidth(float) -> void,
        glPointSize(float) -> void,

        // Color / shading
        glColor4f(float, float, float, float) -> void,
        glColor3f(float, float, float) -> void,
        glColor4ub(byte, byte, byte, byte) -> void,
        glShadeModel(int) -> void,

        // Matrix stack (fixed-function pipeline)
        glMatrixMode(int) -> void,
        glLoadIdentity() -> void,
        glLoadMatrixf(float*) -> void,
        glMultMatrixf(float*) -> void,
        glPushMatrix() -> void,
        glPopMatrix() -> void,
        glTranslatef(float, float, float) -> void,
        glRotatef(float, float, float, float) -> void,
        glScalef(float, float, float) -> void,
        glOrtho(float, float, float, float, float, float) -> void,
        glFrustum(float, float, float, float, float, float) -> void,

        // Immediate mode geometry
        glBegin(int) -> void,
        glEnd() -> void,
        glVertex2f(float, float) -> void,
        glVertex3f(float, float, float) -> void,
        glVertex4f(float, float, float, float) -> void,
        glVertex2i(int, int) -> void,
        glVertex3i(int, int, int) -> void,
        glNormal3f(float, float, float) -> void,
        glTexCoord2f(float, float) -> void,

        // Textures
        glGenTextures(int, int*) -> void,
        glDeleteTextures(int, int*) -> void,
        glBindTexture(int, int) -> void,
        glTexImage2D(int, int, int, int, int, int, int, int, void*) -> void,
        glTexSubImage2D(int, int, int, int, int, int, int, int, void*) -> void,
        glTexParameteri(int, int, int) -> void,
        glTexParameterf(int, int, float) -> void,

        // Display lists (fixed-function)
        glNewList(int, int) -> void,
        glEndList() -> void,
        glCallList(int) -> void,
        glGenLists(int) -> int,
        glDeleteLists(int, int) -> void,

        // Stencil
        glStencilFunc(int, int, int) -> void,
        glStencilOp(int, int, int) -> void,
        glStencilMask(int) -> void,

        // Color write mask
        glColorMask(GLboolean, GLboolean, GLboolean, GLboolean) -> void,

        // Reading pixels
        glReadPixels(int, int, int, int, int, int, void*) -> void,

        // Fixed-function lighting
        glLightfv(int, int, float*) -> void,
        glLightf(int, int, float) -> void,
        glMaterialfv(int, int, float*) -> void,
        glMaterialf(int, int, float) -> void;
};

// ============================================================================
// OPENGL EXTENSION FUNCTION POINTERS
// Loaded at runtime via wglGetProcAddress.
// Call gl_load_extensions() after context creation before using any of these.
// ============================================================================

global void* _glGenBuffers              = STDLIB_GVP,
             _glDeleteBuffers           = STDLIB_GVP,
             _glBindBuffer              = STDLIB_GVP,
             _glBufferData              = STDLIB_GVP,
             _glBufferSubData           = STDLIB_GVP,
             _glMapBuffer               = STDLIB_GVP,
             _glUnmapBuffer             = STDLIB_GVP,

             _glGenVertexArrays         = STDLIB_GVP,
             _glDeleteVertexArrays      = STDLIB_GVP,
             _glBindVertexArray         = STDLIB_GVP,

             _glEnableVertexAttribArray  = STDLIB_GVP,
             _glDisableVertexAttribArray = STDLIB_GVP,
             _glVertexAttribPointer      = STDLIB_GVP,

             _glCreateShader            = STDLIB_GVP,
             _glDeleteShader            = STDLIB_GVP,
             _glShaderSource            = STDLIB_GVP,
             _glCompileShader           = STDLIB_GVP,
             _glGetShaderiv             = STDLIB_GVP,
             _glGetShaderInfoLog        = STDLIB_GVP,

             _glCreateProgram           = STDLIB_GVP,
             _glDeleteProgram           = STDLIB_GVP,
             _glAttachShader            = STDLIB_GVP,
             _glDetachShader            = STDLIB_GVP,
             _glLinkProgram             = STDLIB_GVP,
             _glUseProgram              = STDLIB_GVP,
             _glGetProgramiv            = STDLIB_GVP,
             _glGetProgramInfoLog       = STDLIB_GVP,
             _glBindAttribLocation      = STDLIB_GVP,

             _glGetUniformLocation      = STDLIB_GVP,
             _glUniform1i               = STDLIB_GVP,
             _glUniform1f               = STDLIB_GVP,
             _glUniform2f               = STDLIB_GVP,
             _glUniform3f               = STDLIB_GVP,
             _glUniform4f               = STDLIB_GVP,
             _glUniform1iv              = STDLIB_GVP,
             _glUniform2fv              = STDLIB_GVP,
             _glUniform3fv              = STDLIB_GVP,
             _glUniform4fv              = STDLIB_GVP,
             _glUniformMatrix4fv        = STDLIB_GVP,

             _glGenFramebuffers         = STDLIB_GVP,
             _glDeleteFramebuffers      = STDLIB_GVP,
             _glBindFramebuffer         = STDLIB_GVP,
             _glFramebufferTexture2D    = STDLIB_GVP,
             _glCheckFramebufferStatus  = STDLIB_GVP,
             _glGenRenderbuffers        = STDLIB_GVP,
             _glDeleteRenderbuffers     = STDLIB_GVP,
             _glBindRenderbuffer        = STDLIB_GVP,
             _glRenderbufferStorage     = STDLIB_GVP,
             _glFramebufferRenderbuffer = STDLIB_GVP,

             _glGenerateMipmap          = STDLIB_GVP,
             _glActiveTexture           = STDLIB_GVP,

             _glDrawArrays              = STDLIB_GVP,
             _glDrawElements            = STDLIB_GVP,
             _glDrawArraysInstanced     = STDLIB_GVP,
             _glDrawElementsInstanced   = STDLIB_GVP;

namespace standard
{
    namespace system
    {
        namespace windows
        {
            // ============================================================================
            // EXTENSION LOADER
            // Must be called once after a valid GL context is current.
            // ============================================================================

            def gl_load_extensions() -> void
            {
                _glGenBuffers              = wglGetProcAddress("glGenBuffers\0");
                _glDeleteBuffers           = wglGetProcAddress("glDeleteBuffers\0");
                _glBindBuffer              = wglGetProcAddress("glBindBuffer\0");
                _glBufferData              = wglGetProcAddress("glBufferData\0");
                _glBufferSubData           = wglGetProcAddress("glBufferSubData\0");
                _glMapBuffer               = wglGetProcAddress("glMapBuffer\0");
                _glUnmapBuffer             = wglGetProcAddress("glUnmapBuffer\0");

                _glGenVertexArrays         = wglGetProcAddress("glGenVertexArrays\0");
                _glDeleteVertexArrays      = wglGetProcAddress("glDeleteVertexArrays\0");
                _glBindVertexArray         = wglGetProcAddress("glBindVertexArray\0");

                _glEnableVertexAttribArray  = wglGetProcAddress("glEnableVertexAttribArray\0");
                _glDisableVertexAttribArray = wglGetProcAddress("glDisableVertexAttribArray\0");
                _glVertexAttribPointer      = wglGetProcAddress("glVertexAttribPointer\0");

                _glCreateShader            = wglGetProcAddress("glCreateShader\0");
                _glDeleteShader            = wglGetProcAddress("glDeleteShader\0");
                _glShaderSource            = wglGetProcAddress("glShaderSource\0");
                _glCompileShader           = wglGetProcAddress("glCompileShader\0");
                _glGetShaderiv             = wglGetProcAddress("glGetShaderiv\0");
                _glGetShaderInfoLog        = wglGetProcAddress("glGetShaderInfoLog\0");

                _glCreateProgram           = wglGetProcAddress("glCreateProgram\0");
                _glDeleteProgram           = wglGetProcAddress("glDeleteProgram\0");
                _glAttachShader            = wglGetProcAddress("glAttachShader\0");
                _glDetachShader            = wglGetProcAddress("glDetachShader\0");
                _glLinkProgram             = wglGetProcAddress("glLinkProgram\0");
                _glUseProgram              = wglGetProcAddress("glUseProgram\0");
                _glGetProgramiv            = wglGetProcAddress("glGetProgramiv\0");
                _glGetProgramInfoLog       = wglGetProcAddress("glGetProgramInfoLog\0");
                _glBindAttribLocation      = wglGetProcAddress("glBindAttribLocation\0");

                _glGetUniformLocation      = wglGetProcAddress("glGetUniformLocation\0");
                _glUniform1i               = wglGetProcAddress("glUniform1i\0");
                _glUniform1f               = wglGetProcAddress("glUniform1f\0");
                _glUniform2f               = wglGetProcAddress("glUniform2f\0");
                _glUniform3f               = wglGetProcAddress("glUniform3f\0");
                _glUniform4f               = wglGetProcAddress("glUniform4f\0");
                _glUniform1iv              = wglGetProcAddress("glUniform1iv\0");
                _glUniform2fv              = wglGetProcAddress("glUniform2fv\0");
                _glUniform3fv              = wglGetProcAddress("glUniform3fv\0");
                _glUniform4fv              = wglGetProcAddress("glUniform4fv\0");
                _glUniformMatrix4fv        = wglGetProcAddress("glUniformMatrix4fv\0");

                _glGenFramebuffers         = wglGetProcAddress("glGenFramebuffers\0");
                _glDeleteFramebuffers      = wglGetProcAddress("glDeleteFramebuffers\0");
                _glBindFramebuffer         = wglGetProcAddress("glBindFramebuffer\0");
                _glFramebufferTexture2D    = wglGetProcAddress("glFramebufferTexture2D\0");
                _glCheckFramebufferStatus  = wglGetProcAddress("glCheckFramebufferStatus\0");
                _glGenRenderbuffers        = wglGetProcAddress("glGenRenderbuffers\0");
                _glDeleteRenderbuffers     = wglGetProcAddress("glDeleteRenderbuffers\0");
                _glBindRenderbuffer        = wglGetProcAddress("glBindRenderbuffer\0");
                _glRenderbufferStorage     = wglGetProcAddress("glRenderbufferStorage\0");
                _glFramebufferRenderbuffer = wglGetProcAddress("glFramebufferRenderbuffer\0");

                _glGenerateMipmap          = wglGetProcAddress("glGenerateMipmap\0");
                _glActiveTexture           = wglGetProcAddress("glActiveTexture\0");

                _glDrawArrays              = wglGetProcAddress("glDrawArrays\0");
                _glDrawElements            = wglGetProcAddress("glDrawElements\0");
                _glDrawArraysInstanced     = wglGetProcAddress("glDrawArraysInstanced\0");
                _glDrawElementsInstanced   = wglGetProcAddress("glDrawElementsInstanced\0");

                return;
            };

            // ============================================================================
            // MATRIX4 - Column-major 4x4 float matrix (OpenGL convention)
            // ============================================================================

            struct Matrix4
            {
                float[16] m; // column-major: m[col*4 + row]
            };

            // Load identity into a Matrix4
            def mat4_identity(Matrix4* out) -> void
            {
                out.m[0]  = 1.0; out.m[1]  = 0.0; out.m[2]  = 0.0; out.m[3]  = 0.0;
                out.m[4]  = 0.0; out.m[5]  = 1.0; out.m[6]  = 0.0; out.m[7]  = 0.0;
                out.m[8]  = 0.0; out.m[9]  = 0.0; out.m[10] = 1.0; out.m[11] = 0.0;
                out.m[12] = 0.0; out.m[13] = 0.0; out.m[14] = 0.0; out.m[15] = 1.0;
                return;
            };

            // Multiply two Matrix4 values: out = a * b
            def mat4_mul(Matrix4* a, Matrix4* b, Matrix4* out) -> void
            {
                int row, col, k;

                float sum;

                while (row < 4)
                {
                    col = 0;
                    while (col < 4)
                    {
                        sum = 0.0;
                        k = 0;
                        while (k < 4)
                        {
                            sum = sum + a.m[k * 4 + row] * b.m[col * 4 + k];
                            k = k + 1;
                        };
                        out.m[col * 4 + row] = sum;
                        col = col + 1;
                    };
                    row = row + 1;
                };
                return;
            };

            // Build a perspective projection matrix
            // fovy_rad: vertical field of view in radians, aspect: width/height
            def mat4_perspective(float fovy_rad, float aspect, float near_z, float far_z, Matrix4* out) -> void
            {
                float f  = 1.0 / tan(fovy_rad / 2.0),
                      nf = 1.0 / (near_z - far_z);

                out.m[0]  = f / aspect; out.m[1]  = 0.0; out.m[2]  = 0.0;                              out.m[3]  = 0.0;
                out.m[4]  = 0.0;        out.m[5]  = f;   out.m[6]  = 0.0;                              out.m[7]  = 0.0;
                out.m[8]  = 0.0;        out.m[9]  = 0.0; out.m[10] = (far_z + near_z) * nf;            out.m[11] = -1.0;
                out.m[12] = 0.0;        out.m[13] = 0.0; out.m[14] = 2.0 * far_z * near_z * nf;        out.m[15] = 0.0;

                return;
            };

            // Build an orthographic projection matrix
            def mat4_ortho(float left, float right, float bottom, float top, float near_z, float far_z, Matrix4* out) -> void
            {
                float rl = 1.0 / (right - left),
                      tb = 1.0 / (top - bottom),
                      fn = 1.0 / (far_z - near_z);

                out.m[0]  = 2.0 * rl; out.m[1]  = 0.0;      out.m[2]  = 0.0;       out.m[3]  = 0.0;
                out.m[4]  = 0.0;      out.m[5]  = 2.0 * tb; out.m[6]  = 0.0;       out.m[7]  = 0.0;
                out.m[8]  = 0.0;      out.m[9]  = 0.0;      out.m[10] = -2.0 * fn; out.m[11] = 0.0;
                out.m[12] = (0.0 - (right + left)) * rl;
                out.m[13] = (0.0 - (top + bottom)) * tb;
                out.m[14] = (0.0 - (far_z + near_z)) * fn;
                out.m[15] = 1.0;

                return;
            };

            // Build a translation matrix
            def mat4_translate(float tx, float ty, float tz, Matrix4* out) -> void
            {
                mat4_identity(out);
                out.m[12] = tx;
                out.m[13] = ty;
                out.m[14] = tz;
                return;
            };

            // Build a uniform scale matrix
            def mat4_scale(float sx, float sy, float sz, Matrix4* out) -> void
            {
                mat4_identity(out);
                out.m[0]  = sx;
                out.m[5]  = sy;
                out.m[10] = sz;
                return;
            };

            // Build a rotation matrix around an arbitrary normalised axis
            def mat4_rotate(float ax, float ay, float az, float angle_rad, Matrix4* out) -> void
            {
                float c  = cos(angle_rad),
                      s  = sin(angle_rad);
                float ic = 1.0 - c;

                out.m[0]  = ax * ax * ic + c;          out.m[1]  = ay * ax * ic + az * s;     out.m[2]  = az * ax * ic - ay * s;     out.m[3]  = 0.0;
                out.m[4]  = ax * ay * ic - az * s;     out.m[5]  = ay * ay * ic + c;          out.m[6]  = az * ay * ic + ax * s;     out.m[7]  = 0.0;
                out.m[8]  = ax * az * ic + ay * s;     out.m[9]  = ay * az * ic - ax * s;     out.m[10] = az * az * ic + c;          out.m[11] = 0.0;
                out.m[12] = 0.0;                        out.m[13] = 0.0;                        out.m[14] = 0.0;                        out.m[15] = 1.0;

                return;
            };

            // ============================================================================
            // GLVEC3 - 3-component float vector with common operations
            // ============================================================================

            struct GLVec3
            {
                float x, y, z;
            };

            // Dot product
            def vec3_dot(GLVec3* a, GLVec3* b) -> float
            {
                return a.x * b.x + a.y * b.y + a.z * b.z;
            };

            // Cross product: out = a x b
            def vec3_cross(GLVec3* a, GLVec3* b, GLVec3* out) -> void
            {
                out.x = a.y * b.z - a.z * b.y;
                out.y = a.z * b.x - a.x * b.z;
                out.z = a.x * b.y - a.y * b.x;
                return;
            };

            // Length of a vector
            def vec3_length(GLVec3* v) -> float
            {
                return sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
            };

            // Normalize a vector in-place (no-op if near-zero length)
            def vec3_normalize(GLVec3* v) -> void
            {
                float len = vec3_length(v);
                if (len < 0.000001) { return; };
                v.x = v.x / len;
                v.y = v.y / len;
                v.z = v.z / len;
                return;
            };

            // Subtract: out = a - b
            def vec3_sub(GLVec3* a, GLVec3* b, GLVec3* out) -> void
            {
                out.x = a.x - b.x;
                out.y = a.y - b.y;
                out.z = a.z - b.z;
                return;
            };

            // Add: out = a + b
            def vec3_add(GLVec3* a, GLVec3* b, GLVec3* out) -> void
            {
                out.x = a.x + b.x;
                out.y = a.y + b.y;
                out.z = a.z + b.z;
                return;
            };

            // Scale: out = v * s
            def vec3_scale(GLVec3* v, float s, GLVec3* out) -> void
            {
                out.x = v.x * s;
                out.y = v.y * s;
                out.z = v.z * s;
                return;
            };

            // Build a look-at view matrix
            def mat4_lookat(GLVec3* eye, GLVec3* target, GLVec3* up, Matrix4* out) -> void
            {
                GLVec3 f,s,u;
                f.x = target.x - eye.x;
                f.y = target.y - eye.y;
                f.z = target.z - eye.z;
                vec3_normalize(@f);

                vec3_cross(@f, up, @s);
                vec3_normalize(@s);

                vec3_cross(@s, @f, @u);

                out.m[0]  =  s.x; out.m[1]  =  u.x; out.m[2]  = -f.x; out.m[3]  = 0.0;
                out.m[4]  =  s.y; out.m[5]  =  u.y; out.m[6]  = -f.y; out.m[7]  = 0.0;
                out.m[8]  =  s.z; out.m[9]  =  u.z; out.m[10] = -f.z; out.m[11] = 0.0;
                out.m[12] = (0.0 - vec3_dot(@s, eye));
                out.m[13] = (0.0 - vec3_dot(@u, eye));
                out.m[14] =  vec3_dot(@f, eye);
                out.m[15] = 1.0;

                return;
            };

            // ============================================================================
            // GLCONTEXT OBJECT - Wraps a Window's GL lifecycle
            // ============================================================================

            object GLContext
            {
                HDC  dc;
                HGLRC rc;
                bool extensions_loaded;

                // Create a GL context from a Window's device context
                def __init(HDC device_context) -> this
                {
                    this.dc  = device_context;
                    this.rc  = setup_opengl(device_context);
                    this.extensions_loaded = false;
                    return this;
                };

                // Destroy GL context and release
                def __exit() -> void
                {
                    if (this.rc != (HGLRC)0)
                    {
                        wglMakeCurrent((HDC)0, (HGLRC)0);
                        wglDeleteContext(this.rc);
                    };
                    return;
                };

                def __expr() -> HDC
                {
                    return this.dc;
                };

                // Load extension function pointers - call once after init
                def load_extensions() -> void
                {
                    gl_load_extensions();
                    this.extensions_loaded = true;
                    return;
                };

                // Present the rendered frame (swap buffers)
                def present() -> void
                {
                    swap_buffers(this.dc);
                    return;
                };

                // Set the clear colour (0.0 - 1.0 per channel)
                def set_clear_color(float r, float g, float b, float a) -> void
                {
                    glClearColor(r, g, b, a);
                    return;
                };

                // Clear colour and depth buffers
                def clear() -> void
                {
                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
                    return;
                };

                // Set the OpenGL viewport
                def set_viewport(int x, int y, int w, int h) -> void
                {
                    glViewport(x, y, w, h);
                    return;
                };
            };
        };
    };
};

#endif;
