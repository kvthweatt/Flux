#import "standard.fx", "math.fx", "windows.fx", "opengl.fx";

using standard::system::windows;
using standard::math;

// ============================================================================
// Happy Birthday Shader - Festive GPU-rendered greeting!
// Features: Rainbow background, SDF text, confetti, sparkles, balloons
// ============================================================================

const int WIN_W = 900;
const int WIN_H = 600;

// ============================================================================
// GLSL SHADER SOURCES
// ============================================================================

// Vertex shader: pass-through, UV comes from glTexCoord2f
byte[] VERT_SRC = "#version 120
void main() {
    gl_TexCoord[0] = gl_MultiTexCoord0;
    gl_Position = gl_Vertex;
}
\0";

// Fragment shader: Happy Birthday with all the bells and whistles
byte[] FRAG_SRC = "#version 120
uniform vec2 u_res;
uniform float u_time;

// ---------- Utility Functions ----------

// HSL to RGB conversion
vec3 hsl2rgb(float h, float s, float l) {
    vec3 rgb = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return l + s * (rgb - 0.5) * (1.0 - abs(2.0 * l - 1.0));
}

// Smooth noise
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

// ---------- SDF Font Functions ----------

// SDF for individual characters (simplified block letters)
float sdBox(vec2 p, vec2 b) {
    vec2 d = abs(p) - b;
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}

// Letter H
float sdH(vec2 p) {
    float d = min(sdBox(p - vec2(-0.25, 0.0), vec2(0.1, 0.5)),
                  sdBox(p - vec2(0.25, 0.0), vec2(0.1, 0.5)));
    d = min(d, sdBox(p, vec2(0.25, 0.1)));
    return d;
}

// Letter A
float sdA(vec2 p) {
    float d = sdBox(p - vec2(-0.2, 0.0), vec2(0.1, 0.5));
    d = min(d, sdBox(p - vec2(0.2, 0.0), vec2(0.1, 0.5)));
    d = min(d, sdBox(p - vec2(0.0, 0.15), vec2(0.2, 0.1)));
    d = min(d, sdBox(p - vec2(0.0, 0.35), vec2(0.15, 0.1)));
    return d;
}

// Letter P
float sdP(vec2 p) {
    float d = sdBox(p - vec2(-0.15, 0.0), vec2(0.1, 0.5));
    d = min(d, sdBox(p - vec2(0.1, 0.25), vec2(0.15, 0.1)));
    d = min(d, sdBox(p - vec2(0.1, 0.15), vec2(0.1, 0.1)));
    d = min(d, sdBox(p - vec2(0.15, 0.2), vec2(0.05, 0.15)));
    return d;
}

// Letter Y
float sdY(vec2 p) {
    float d = sdBox(p - vec2(0.0, -0.2), vec2(0.1, 0.3));
    d = min(d, sdBox(p - vec2(-0.15, 0.3), vec2(0.1, 0.2)));
    d = min(d, sdBox(p - vec2(0.15, 0.3), vec2(0.1, 0.2)));
    return d;
}

// Letter B
float sdB(vec2 p) {
    float d = sdBox(p - vec2(-0.15, 0.0), vec2(0.1, 0.5));
    d = min(d, sdBox(p - vec2(0.05, 0.25), vec2(0.15, 0.1)));
    d = min(d, sdBox(p - vec2(0.1, 0.35), vec2(0.1, 0.1)));
    d = min(d, sdBox(p - vec2(0.05, -0.15), vec2(0.15, 0.1)));
    d = min(d, sdBox(p - vec2(0.1, -0.25), vec2(0.1, 0.1)));
    return d;
}

// Letter I
float sdI(vec2 p) {
    return sdBox(p, vec2(0.1, 0.5));
}

// Letter R
float sdR(vec2 p) {
    float d = sdBox(p - vec2(-0.15, 0.0), vec2(0.1, 0.5));
    d = min(d, sdBox(p - vec2(0.1, 0.25), vec2(0.15, 0.1)));
    d = min(d, sdBox(p - vec2(0.15, 0.2), vec2(0.05, 0.15)));
    d = min(d, sdBox(p - vec2(0.1, -0.15), vec2(0.1, 0.25)));
    return d;
}

// Letter T
float sdT(vec2 p) {
    float d = sdBox(p - vec2(0.0, 0.35), vec2(0.35, 0.1));
    d = min(d, sdBox(p, vec2(0.1, 0.45)));
    return d;
}

// Letter D
float sdD(vec2 p) {
    float d = sdBox(p - vec2(-0.15, 0.0), vec2(0.1, 0.5));
    d = min(d, sdBox(p - vec2(0.0, 0.0), vec2(0.2, 0.4)));
    return d;
}

// Exclamation mark
float sdExclaim(vec2 p) {
    float d = sdBox(p, vec2(0.08, 0.35));
    d = min(d, sdBox(p - vec2(0.0, -0.4), vec2(0.08, 0.08)));
    return d;
}

// Get SDF for character at index
float getCharSDF(vec2 p, int idx) {
    if (idx == 0) return sdH(p);      // H
    if (idx == 1) return sdA(p);      // A
    if (idx == 2) return sdP(p);      // P
    if (idx == 3) return sdP(p);      // P
    if (idx == 4) return sdY(p);      // Y
    if (idx == 5) return sdB(p);      // B
    if (idx == 6) return sdI(p);      // I
    if (idx == 7) return sdR(p);      // R
    if (idx == 8) return sdT(p);      // T
    if (idx == 9) return sdH(p);      // H
    if (idx == 10) return sdD(p);     // D
    if (idx == 11) return sdA(p);     // A
    if (idx == 12) return sdY(p);     // Y
    if (idx == 13) return sdExclaim(p); // !
    return 1.0;
}

// ---------- Confetti Particle System ----------

float confetti(vec2 uv, float time) {
    float col = 0.0;
    for (int i = 0; i < 40; i++) {
        float fi = float(i);
        vec2 pos = vec2(
            hash(vec2(fi, 0.0)) * 2.4 - 1.2,
            mod(hash(vec2(fi, 1.0)) - time * (0.1 + hash(vec2(fi, 2.0)) * 0.15), 2.4) - 1.2
        );
        float size = 0.01 + hash(vec2(fi, 3.0)) * 0.02;
        float rot = time * (hash(vec2(fi, 4.0)) - 0.5) * 3.0;
        vec2 diff = uv - pos;
        float c = cos(rot), s = sin(rot);
        vec2 rdiff = vec2(diff.x * c - diff.y * s, diff.x * s + diff.y * c);
        float d = sdBox(rdiff, vec2(size, size * 0.6));
        if (d < 0.0) {
            col += 0.8 * (1.0 - d / (-size));
        }
    }
    return col;
}

// ---------- Sparkle System ----------

float sparkles(vec2 uv, float time) {
    float s = 0.0;
    for (int i = 0; i < 25; i++) {
        float fi = float(i);
        vec2 pos = vec2(
            sin(fi * 123.456) * 1.2,
            cos(fi * 789.012) * 0.8
        );
        float phase = fi * 2.5 + time * 2.0;
        float brightness = pow(sin(phase) * 0.5 + 0.5, 4.0);
        float dist = length(uv - pos);
        s += brightness * 0.02 / (dist * dist + 0.002);
    }
    return s;
}

// ---------- Balloon System ----------

float balloons(vec2 uv, float time) {
    float b = 0.0;
    for (int i = 0; i < 8; i++) {
        float fi = float(i);
        vec2 pos = vec2(
            -1.0 + fi * 0.3 + sin(time * 0.5 + fi) * 0.1,
            -0.6 + mod(fi * 0.3 + time * 0.08, 2.0) - 0.5
        );
        float size = 0.08 + hash(vec2(fi, 99.0)) * 0.04;
        float d = length(uv - pos) - size;
        
        // Balloon shape (ellipse)
        vec2 euv = (uv - pos) / vec2(1.0, 1.2);
        float ed = length(euv) - size;
        
        if (ed < 0.0) {
            // Balloon gradient
            float grad = 1.0 - length(euv) / size;
            float h = hash(vec2(fi, 0.0));
            vec3 bcol = hsl2rgb(h, 0.8, 0.5 + grad * 0.3);
            b = max(b, 0.7 * (1.0 - ed / (-size)));
        }
        
        // String
        vec2 suv = uv - vec2(pos.x, pos.y - size * 1.2);
        float sd = abs(suv.x) - 0.003;
        if (sd < 0.0 && suv.y < 0.0 && suv.y > -0.15) {
            b = max(b, 0.3);
        }
    }
    return b;
}

// ---------- Main Text SDF ----------

float textSDF(vec2 p) {
    // HAPPY (centered, top line)
    float scale = 0.12;
    float spacing = 0.7;
    float d = 1.0;
    
    vec2 tp = p - vec2(-spacing * 2.0, 0.25);
    for (int i = 0; i < 5; i++) {
        vec2 cp = tp - vec2(float(i) * spacing, 0.0);
        cp /= scale;
        d = min(d, getCharSDF(cp, i) * scale);
    }
    
    // BIRTHDAY (centered, bottom line)
    tp = p - vec2(-spacing * 2.5, -0.3);
    for (int i = 0; i < 6; i++) {
        vec2 cp = tp - vec2(float(i) * spacing, 0.0);
        cp /= scale;
        d = min(d, getCharSDF(cp, i + 5) * scale);
    }
    
    // Extra letters: DAY
    tp = p - vec2(spacing * 1.5, -0.3);
    for (int i = 0; i < 3; i++) {
        vec2 cp = tp - vec2(float(i) * spacing, 0.0);
        cp /= scale;
        d = min(d, getCharSDF(cp, i + 10) * scale);
    }
    
    // Exclamation
    tp = p - vec2(spacing * 4.0, -0.3);
    tp /= scale;
    d = min(d, getCharSDF(tp, 13) * scale);
    
    return d;
}

// ---------- Main ----------

void main() {
    vec2 uv = gl_TexCoord[0].xy;
    uv.x *= u_res.x / u_res.y;
    
    float time = u_time;
    
    // Rainbow gradient background
    float hue = uv.x * 0.15 + time * 0.05;
    hue += sin(uv.y * 2.0 + time) * 0.05;
    vec3 bg = hsl2rgb(hue, 0.6, 0.35);
    
    // Add subtle noise texture
    bg += noise(uv * 50.0 + time * 0.5) * 0.08;
    
    // Pulsing radial glow from center
    float radial = length(uv) * 0.5;
    float pulse = sin(time * 2.0) * 0.5 + 0.5;
    bg = mix(bg, hsl2rgb(0.9, 0.5, 0.4), radial * (0.3 + pulse * 0.2));
    
    // Confetti
    float conf = confetti(uv, time);
    vec3 confCol = hsl2rgb(time * 0.3 + uv.x, 0.9, 0.6);
    bg = mix(bg, confCol, conf);
    
    // Balloons
    float b = balloons(uv, time);
    bg = mix(bg, vec3(1.0), b * 0.6);
    
    // Text SDF
    float td = textSDF(uv);
    
    // Text color with rainbow effect
    vec3 textCol = hsl2rgb(time * 0.2, 0.9, 0.6);
    
    // Glow layers
    float glow1 = 0.02 / (abs(td) + 0.02);
    float glow2 = 0.005 / (abs(td) + 0.005);
    vec3 glowCol = hsl2rgb(time * 0.15 + 0.1, 0.8, 0.7);
    
    // Chromatic glow (RGB offset)
    float tdR = textSDF(uv + vec2(0.003, 0.0));
    float tdG = textSDF(uv);
    float tdB = textSDF(uv - vec2(0.003, 0.0));
    vec3 chromGlow = vec3(
        0.02 / (abs(tdR) + 0.02),
        0.02 / (abs(tdG) + 0.02),
        0.02 / (abs(tdB) + 0.02)
    );
    
    bg += chromGlow * 0.4 * glowCol;
    
    // Solid text
    if (td < 0.0) {
        // Animated text gradient
        float textHue = 0.05 + sin(time + uv.x * 3.0) * 0.1;
        textCol = hsl2rgb(textHue, 0.95, 0.65);
        
        // Shimmer effect
        textCol += noise(uv * 30.0 + time * 5.0) * 0.15;
        
        // Edge highlight
        float edge = smoothstep(0.0, -0.02, td);
        textCol = mix(vec3(1.0), textCol, edge);
        
        bg = textCol;
    }
    
    // Sparkles on top
    float sp = sparkles(uv, time);
    bg += vec3(1.0, 0.95, 0.8) * sp;
    
    // Vignette
    float vign = 1.0 - length(uv) * 0.3;
    bg *= vign;
    
    // Gamma correction
    bg = pow(clamp(bg, 0.0, 1.0), vec3(0.4545));
    
    gl_FragColor = vec4(bg, 1.0);
}
\0";

// ============================================================================
// FUNCTION POINTER TYPEDEFS
// ============================================================================
///
def{}* glCreateShader_fp(int)                -> int;
def{}* glShaderSource_fp(int,int,byte**,int*)-> void;
def{}* glCompileShader_fp(int)               -> void;
def{}* glCreateProgram_fp()                  -> int;
def{}* glAttachShader_fp(int,int)            -> void;
def{}* glLinkProgram_fp(int)                 -> void;
def{}* glUseProgram_fp(int)                  -> void;
def{}* glGetUniformLocation_fp(int,byte*)    -> int;
///
def{}* glUniform1f_fp(int,float)             -> void;
def{}* glUniform2f_fp(int,float,float)       -> void;
///
def{}* glDeleteShader_fp(int)                -> void;
def{}* glDeleteProgram_fp(int)               -> void;
///
// ============================================================================
// SHADER HELPERS
// ============================================================================

def get_uniform(int prog, byte* name) -> int
{
    return glGetUniformLocation_fp(prog, name);
};

extern def !!GetTickCount() -> DWORD;

// ============================================================================
// MAIN
// ============================================================================

def main() -> int
{
    Window win("Happy Birthday!", 100, 100, WIN_W, WIN_H);
    GLContext gl(win.device_context);
    gl.load_extensions();

    // Bind function pointers
    glCreateShader_fp       = _glCreateShader;
    glShaderSource_fp       = _glShaderSource;
    glCompileShader_fp      = _glCompileShader;
    glCreateProgram_fp      = _glCreateProgram;
    glAttachShader_fp       = _glAttachShader;
    glLinkProgram_fp        = _glLinkProgram;
    glUseProgram_fp         = _glUseProgram;
    glGetUniformLocation_fp = _glGetUniformLocation;
    glUniform1f_fp          = _glUniform1f;
    glUniform2f_fp          = _glUniform2f;
    glDeleteShader_fp       = _glDeleteShader;
    glDeleteProgram_fp      = _glDeleteProgram;

    glDisable(GL_DEPTH_TEST);

    // Build shader program
    int vert_sh = compile_shader(GL_VERTEX_SHADER,   @VERT_SRC[0]);
    int frag_sh = compile_shader(GL_FRAGMENT_SHADER, @FRAG_SRC[0]);
    int prog    = link_program(vert_sh, frag_sh);

    // Uniform locations
    int u_res  = get_uniform(prog, "u_res\0");
    int u_time = get_uniform(prog, "u_time\0");

    // Timing
    DWORD t_now, t_last;
    float elapsed = 0.0;
    t_last = GetTickCount();

    RECT client_rect;
    int cur_w, cur_h;

    // Render loop
    while (win.process_messages())
    {
        // Delta time
        t_now  = GetTickCount();
        elapsed += (float)(t_now - t_last) / 1000.0;
        t_last = t_now;

        // Query actual client area
        GetClientRect(win.handle, @client_rect);
        cur_w = client_rect.right  - client_rect.left;
        cur_h = client_rect.bottom - client_rect.top;
        if (cur_w < 1) { cur_w = 1; };
        if (cur_h < 1) { cur_h = 1; };

        glViewport(0, 0, cur_w, cur_h);

        // Clear
        gl.set_clear_color(0.0, 0.0, 0.0, 1.0);
        gl.clear();

        // Use shader
        glUseProgram_fp(prog);
        glUniform2f_fp(u_res, (float)cur_w, (float)cur_h);
        glUniform1f_fp(u_time, elapsed);

        // Fullscreen triangle via immediate mode
        glBegin(GL_TRIANGLES);
        glTexCoord2f(-1.0, -1.0); glVertex2f(-1.0, -1.0);
        glTexCoord2f( 3.0, -1.0); glVertex2f( 3.0, -1.0);
        glTexCoord2f(-1.0,  3.0); glVertex2f(-1.0,  3.0);
        glEnd();

        gl.present();
    };

    // Cleanup
    glDeleteShader_fp(vert_sh);
    glDeleteShader_fp(frag_sh);
    glDeleteProgram_fp(prog);
    gl.__exit();
    win.__exit();

    return 0;
};