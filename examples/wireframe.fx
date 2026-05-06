#import "standard.fx", "vectors.fx", "windows.fx", "opengl.fx", "allocators.fx";

using standard::system::windows,
      standard::vectors,
      standard::math,
      standard::io::console,
      standard::io::file;

// ============================================================================
// MESH TYPES
// ============================================================================

#def MAX_VERTS 8192;
#def MAX_FACES 16384;

struct Mesh
{
    Vec3* verts;
    Face* faces;
    int   vert_count, face_count;
};

// ============================================================================
// OBJ LOADER
// ============================================================================

def load_obj(byte* path, Mesh* mesh) -> bool
{
    print("Loading object ...\n\0");
    noopstr f = "\\Users\\kvthw\\Flux\\examples\\Lowpoly_Notebook_2.obj\0";
    int size = get_file_size(f);
    if (size <= 0)
    {
        print("Error: file not found or empty.\n\0");
        return false;
    };
    byte* buffer = fmalloc((u64)size + 1);
    if (buffer == 0)
    {
        print("Error: out of memory.\n\0");
        return false;
    };
    int bytes_read = read_file(f, buffer, size);
    if (bytes_read <= 0)
    {
        print("Error: could not read file.\n\0");
        ffree((u64)buffer);
        return false;
    };
    buffer[bytes_read] = (byte)0;
    print("File loaded, initializing arrays...\n\0");
    print(buffer);

    mesh.verts      = (Vec3*)fmalloc((u64)MAX_VERTS * 12);
    mesh.faces      = (Face*)fmalloc((u64)MAX_FACES * 12);
    mesh.vert_count = 0;
    mesh.face_count = 0;

    byte[512] line;
    byte ch;
    int pos, line_len, read_pos, matched,
        fa, fb, fc, dummy1, dummy2, si;
    float vx, vy, vz;
    print("Before loop...\n\0");

    while (pos < bytes_read)
    {
        line_len = 0;
        read_pos = pos;
        while (read_pos < bytes_read & buffer[read_pos] != '\n' & line_len < 511)
        {
            ch = buffer[read_pos];
            if (ch != '\r')
            {
                line[line_len] = ch;
                line_len = line_len + 1;
            };
            read_pos = read_pos + 1;
        };
        line[line_len] = (byte)0;
        pos = read_pos;
        if (pos < bytes_read) { pos = pos + 1; };

        if (line[0] == 'v' & line[1] == ' ')
        {
            if (mesh.vert_count < MAX_VERTS)
            {
                vx = 0.0;
                vy = 0.0;
                vz = 0.0;
                sscanf(line, "v %f %f %f\0", @vx, @vy, @vz);
                mesh.verts[mesh.vert_count].x = vx;
                mesh.verts[mesh.vert_count].y = vy;
                mesh.verts[mesh.vert_count].z = vz;
                mesh.vert_count = mesh.vert_count + 1;
            };
        };

        if (line[0] == 'f' & line[1] == ' ')
        {
            if (mesh.face_count < MAX_FACES)
            {
                fa = 0;
                fb = 0;
                fc = 0;
                dummy1 = 0;
                dummy2 = 0;

                matched = sscanf(line, "f %d/%d/%d\0", @fa, @dummy1, @dummy2);
                if (matched < 1)
                {
                    matched = sscanf(line, "f %d\x2F\x2F%d\0", @fa, @dummy1, @dummy2);
                };
                if (matched < 1)
                {
                    sscanf(line, "f %d %d %d\0", @fa, @fb, @fc);
                }
                else
                {
                    si = 2;
                    while (line[si] != ' ' & line[si] != (byte)0) { si = si + 1; };
                    if (line[si] == ' ')
                    {
                        si = si + 1;
                        dummy1 = 0;
                        dummy2 = 0;
                        matched = sscanf(@line[si], "%d/%d/%d\0", @fb, @dummy1, @dummy2);
                        if (matched < 1) { matched = sscanf(@line[si], "%d\x2F\x2F%d\0", @fb, @dummy1, @dummy2); };
                        if (matched < 1) { sscanf(@line[si], "%d\0", @fb, @dummy1, @dummy2); };
                        while (line[si] != ' ' & line[si] != (byte)0) { si = si + 1; };
                        if (line[si] == ' ')
                        {
                            si = si + 1;
                            dummy1 = 0;
                            dummy2 = 0;
                            matched = sscanf(@line[si], "%d/%d/%d\0", @fc, @dummy1, @dummy2);
                            if (matched < 1) { matched = sscanf(@line[si], "%d\x2F\x2F%d\0", @fc, @dummy1, @dummy2); };
                            if (matched < 1) { sscanf(@line[si], "%d\0", @fc, @dummy1, @dummy2); };
                        };
                    };
                };

                mesh.faces[mesh.face_count].a = fa - 1;
                mesh.faces[mesh.face_count].b = fb - 1;
                mesh.faces[mesh.face_count].c = fc - 1;
                mesh.face_count = mesh.face_count + 1;
            };
        };
    };

    ffree((u64)buffer);
    return true;
};

// ============================================================================
// MAIN
// ============================================================================

def main(int argc, byte** argv) -> int
{
    Mesh mesh;
    bool loaded;

    const int LINE_WIDTH = 2,     // Pixels
              SLEEP_MS   = 5,
              WIN_WIDTH  = 1280,
              WIN_HEIGHT = 1024,
              RED =   0,
              GREEN = 0,
              BLUE =  255;

    const float CAM_FOV  = 360.0,
                CAM_Z    = 3.0;     // Distance from origin

    if (argc == 2)
    {
        loaded = load_obj(@argv[1], @mesh);
    }
    else
    {
        print("Flux 3D Wireframe Renderer (.OBJ)\nUsage: wireframe <file>.obj\n\0");
        loaded = false;
    };
    Window win("Flux 3D Wireframe\0", WIN_WIDTH, WIN_HEIGHT, CW_USEDEFAULT, CW_USEDEFAULT);
    SetForegroundWindow(win.handle);

    if (!loaded)
    {
        print("Falling back to spinning cube ...\n\0");
        // Fallback: spinning cube
        mesh.vert_count = 8;
        mesh.face_count = 12;
        mesh.verts      = (Vec3*)fmalloc((u64)8  * 12);
        mesh.faces      = (Face*)fmalloc((u64)12 * 12);

        mesh.verts[0].x = -1.0; mesh.verts[0].y = -1.0; mesh.verts[0].z = -1.0;
        mesh.verts[1].x =  1.0; mesh.verts[1].y = -1.0; mesh.verts[1].z = -1.0;
        mesh.verts[2].x =  1.0; mesh.verts[2].y =  1.0; mesh.verts[2].z = -1.0;
        mesh.verts[3].x = -1.0; mesh.verts[3].y =  1.0; mesh.verts[3].z = -1.0;
        mesh.verts[4].x = -1.0; mesh.verts[4].y = -1.0; mesh.verts[4].z =  1.0;
        mesh.verts[5].x =  1.0; mesh.verts[5].y = -1.0; mesh.verts[5].z =  1.0;
        mesh.verts[6].x =  1.0; mesh.verts[6].y =  1.0; mesh.verts[6].z =  1.0;
        mesh.verts[7].x = -1.0; mesh.verts[7].y =  1.0; mesh.verts[7].z =  1.0;

        mesh.faces[0].a  = 0; mesh.faces[0].b  = 1; mesh.faces[0].c  = 2;
        mesh.faces[1].a  = 0; mesh.faces[1].b  = 2; mesh.faces[1].c  = 3;
        mesh.faces[2].a  = 4; mesh.faces[2].b  = 6; mesh.faces[2].c  = 5;
        mesh.faces[3].a  = 4; mesh.faces[3].b  = 7; mesh.faces[3].c  = 6;
        mesh.faces[4].a  = 0; mesh.faces[4].b  = 3; mesh.faces[4].c  = 7;
        mesh.faces[5].a  = 0; mesh.faces[5].b  = 7; mesh.faces[5].c  = 4;
        mesh.faces[6].a  = 1; mesh.faces[6].b  = 5; mesh.faces[6].c  = 6;
        mesh.faces[7].a  = 1; mesh.faces[7].b  = 6; mesh.faces[7].c  = 2;
        mesh.faces[8].a  = 0; mesh.faces[8].b  = 4; mesh.faces[8].c  = 5;
        mesh.faces[9].a  = 0; mesh.faces[9].b  = 5; mesh.faces[9].c  = 1;
        mesh.faces[10].a = 3; mesh.faces[10].b = 2; mesh.faces[10].c = 6;
        mesh.faces[11].a = 3; mesh.faces[11].b = 6; mesh.faces[11].c = 7;
    };

    POINT* proj = (POINT*)fmalloc((u64)mesh.vert_count * 16);

    float angle_x = 0.0;
    float angle_y = 0.0;
    float fov     = CAM_FOV;
    float cam_z   = CAM_Z;
    int   cx      = WIN_WIDTH / 2;
    int   cy      = WIN_HEIGHT / 2;

    enum dc_enum
    {
        BLACK,
        RED,
        GREEN,
        BLUE
    };

    //dc_enum dce;

    DWORD[4] draw_colors = [RGB(  0, 0, 0), // Black
                            RGB(255, 0, 0), // Red
                            RGB(0, 255, 0), // Green
                            RGB(0, 0, 255)  // Blue
                           ];

    DWORD draw_color = draw_colors[dc_enum.BLUE];
    DWORD bg_color = draw_colors[dc_enum.BLACK];

    float sx, sy, cxr, cyr;
    int a, b, i, fi, fv;
    Vec3 v, rx, ry;
    Canvas c(win.handle, win.device_context);

    while (win.process_messages())
    {
        sx  = sin(angle_x);
        cxr = cos(angle_x);
        sy  = sin(angle_y);
        cyr = cos(angle_y);

        i = 0;
        while (i < mesh.vert_count)
        {
            v.x = mesh.verts[i].x;
            v.y = mesh.verts[i].y;
            v.z = mesh.verts[i].z;
            rx = rotate_x(@v,  sx,  cxr);
            ry = rotate_y(@v, sy,  cyr);
            proj[i] = project(@ry, cx, cy, fov, cam_z);
            i = i + 1;
        };

        c.clear(bg_color);
        c.set_pen(draw_color, LINE_WIDTH);

        fi = 0;
        while (fi < mesh.face_count)
        {
            a  = mesh.faces[fi].a;
            b  = mesh.faces[fi].b;
            fv = mesh.faces[fi].c;
            c.line(proj[a].x,  proj[a].y,  proj[b].x,  proj[b].y);
            c.line(proj[b].x,  proj[b].y,  proj[fv].x, proj[fv].y);
            c.line(proj[fv].x, proj[fv].y, proj[a].x,  proj[a].y);
            fi = fi + 1;
        };

        angle_x = angle_x + 0.014;
        angle_y = angle_y + 0.020;

        if (angle_x > PIF) { angle_x = angle_x - 2.0 * PIF; };
        if (angle_y > PIF) { angle_y = angle_y - 2.0 * PIF; };

        Sleep(SLEEP_MS);
    };

    ffree((u64)proj);
    ffree((u64)mesh.verts);
    ffree((u64)mesh.faces);

    win.__exit();

    return 0;
};
