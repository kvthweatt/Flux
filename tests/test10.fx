#import "standard.fx";
#import "windows.fx";

using standard::system::windows;

def main() -> int
{
    Window win("Flux Window\0", 800, 600, CW_USEDEFAULT, CW_USEDEFAULT);
    SetForegroundWindow(win.handle);
    BringWindowToTop(win.handle);

    while (win.process_messages())
    {
        //print("In main loop!\n\0");
    };

    system("pause\0");

    return 0;
};
