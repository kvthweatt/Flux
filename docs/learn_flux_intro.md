# Intro to Programming with Flux

For the purposes of this document, it is assumed this is your first language.  
If it isn't, or if you're a pro, that's ok too!  

- **What is programming?**  
Programming is the art of writing software with a programming language like C, Haskell, Python, Fortran, and others. We say art because anyone can program, but it takes skill to write good code.  
Software is virtual, non-physical. You can't physically touch it. Software lives in and on hardware.  
Hardware is physical, like your hard drive, keyboard, or monitor.  
Firmware is a kind of software which lives *in* your hardware.  
Software, specifically applications, live *on* your hard drive.

- **How does code actually run?**  
To put it simply, all devices have a central processing unit (CPU).  
The CPU is responsible for decoding and executing instructions.  
Programs or applications are a collection of instructions.  
The operating system follows the rules of the CPU to create extended rules. The operating system uses the extended rules to execute programs. This is a simplified explanation and the reality is more nuanced than this.

- **How do you make programs?**  
Every program starts with source code. Source code is the human-readable code written in a programming language.  
If the language is a *compiled* language, you *compile* your source code into an executable program file.  
If the language is an *interpreted* language, you pass your source code to an *interpreter* which executes your program in memory.  
Programs written for one operating system will not work on a different operating system.  
A program compiled for Linux will not execute on Windows.  
CPU architecture also affects whether a program will run or not.  
A program compiled on a RISC CPU will not run on an ARM CPU.

- **Why won't Windows programs run on Linux?**  
Operating systems have different architectures, and as a result, different *system calls*.  
Every operating system does the same basic functions like reading and writing files, but have different function names for these tasks.  
Most languages have *libraries* which allow you to call these functions. They expose your kernel to the application binary interface or *ABI*.

If you're still keeping up, excellent. If not, [Google](https://google.com/) is your friend. Look up the italicized terms.

All of this information will become useful later. For now, let's begin learning how to program.

---

## 1 - Fundamentals  
Flux sits broadly between high and low level. What is that you ask?  
High level languages are languages that are very close to human language. A good example is Python.  
While Python isn't compiled, it still creates programs.
Python looks like:
```
if (user not in userlist):
    userlist.append(user)
```
It is almost like speaking.

Low level languages are more similar to machine code in regard to how it translates to machine code.  
There are still human-readable terms like `if` and `true`/`false` but how it relates to machine code will be explained later.  
C++ is a low level language, here's an example:
```
for (int x = 0; x < 100; x++)
{
    *ptr->value = x; foo(*ptr);
};
```

As you can see, Python and C++ are very different.  
Flux sits right between the two in terms of grammar and syntax, which we will see shortly.  

To work with a language like Flux you need to understand computer memory.  
We're going to start from the smallest unit and work our way up.

The smallest unit of memory (or data) is a bit. A bit is a single digit, 1 or 0.  
A group of 8 bits is called a byte. An example: `01000001` equals 65. Here's an example of a memory segment that is 8 bits long:

<table align="center">
  <tr>
    <th>2 ^ 8 (128)</th>
    <th>2 ^ 6 (64)</th>
    <th>2 ^ 5 (32)</th>
    <th>2 ^ 4 (16)</th>
    <th>2 ^ 3 (8)</th>
    <th>2 ^ 2 (4)</th>
    <th>2 ^ 1 (2)</th>
    <th>2 ^ 0 (1)</th>
  </tr>
  <tr>
    <td>0</td>
    <td>1</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>1</td>
  </tr>
  <tr>
    <td>0</td>
    <td><b>64</b> * 1 = 64</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td><b>1</b> * 1 = 1</td>
  </tr>
</table>

Above we see 1 in the 64's place, and a 1 in the 1's place. We add 64 + 1 and get 65.

- **What does `01000001` mean though?**  
All data is inherently meaningless. It is up to you, the programmer, to give meaning to data.  
- **How do we make `01000001` mean something?**  
We do something like this:  
`years_old = 65;` (remember it equals 65 so you can imagine binary here)  
`miles_per_hour = 65;`  
`percent_complete = 65;`  
Notice anything? We have variables that all equal 65. They're all the same data, but clearly they should be used differently. We're not going to say someone is 65 miles per hour, we say they're 65 years old.  

Some very smart people at **[NIST](https://www.nist.gov/)** (formerly known as **ASA**) engineered a way to represent characters on screens so you and I can read, known as **[ASCII](https://asciitable.com/)**. It is a table of values ranging 0-255. The value range of a byte is also 0-255.

<p align="center">
<img src="https://www.asciitable.com/asciifull.gif">
<img src="https://www.asciitable.com/extend.gif">
</p>

- **How does this relate to programming?**  
It's dangerous  to go alone, take this. Generally speaking you will not be needing this table, but it's a good thing to have. When you start to learn string manipulation this will become relevant again.

- **Diving into memory:**  
You can imagine computer memory to be linear. Whether you want to visualize it horizontally or vertically, it doesn't matter. What matters is understanding memory is made up of bits. If I have 1 GB of memory, that's 1 billion bytes; multiplied by 8 and you get 8 billion bits. We always count in bytes (groups of 8) when we count memory spaces.

<table align="center">
  <tr>
    <th>Address</th>
    <th>0</th>
    <th>1</th>
    <th>2</th>
    <th>3</th>
    <th>4</th>
    <th>5</th>
    <th>...</th>
    <th>1,073,741,824</th>
  </tr>
  <tr>
    <td>Value</td>
    <td>0xDE</td>
    <td>0xAD</td>
    <td>0xBE</td>
    <td>0xEF</td>
    <td>0xDE</td>
    <td>0xAD</td>
    <td>...</td>
    <td>0xEF</td>
  </tr>
</table>

- **Data types:**  
There is 1 byte per address. So now, say I want to get the value of some bytes. Welcome to data types.  
Integer (`int`) types in Flux are 32 bits by default. 32 divided by 8 equals 4, so an `int`  is 4 bytes long. Let's start at address 2 and read an integer, we get `0xBEEFDEAD`.  
When we convert to base 10 (what we can read) we get: **3,203,391,149**.  
Let's say we're using a half-sized `int` that is only 2 bytes, starting at address 2, we get `0xBEEF`.  
Converted to base 10: **48,879**. A much smaller number.

- **How did we convert 0xBEEFDEAD to a number? What even is that?**  
A value like 0x5A206AE0 (**0x** prefix) is known as a hexidecimal number, or base 16. Humans read numbers in decimal or base 10. Binary is base 2. The base number represents how many numbers are available to make other numbers. Binary has 2 numbers available, 0 and 1. Decimal has 10 numbers, 0 through 9. Hexadecimal uses 6 more values, we call them A, B, C, D, E and F. This means hexadecimal ranges from 0-F, or 0 1 2 3 4 5 6 7 8 9 A B C D E F. This is essentially 0-15 which if you include the 0, is 16 numbers. **The value 10 in any numbering system is equal to the base of the numbering system.** In binary, 10 equals 2, there's a 1 in the 2's place. In hexadecimal the number 10 equals 16, here's how:

<table align="center">
  <tr>
    <th>16 ^ 3 = <br>(4096)</th>
    <th>16 ^ 2 = <br>(256)</th>
    <th>16 ^ 1 = <br>(16)</th>
    <th>16 ^ 0 = <br>(1)</th>
  </tr>
  <tr>
    <td></td>
    <td></td>
    <td>1</td>
    <td>0</td>
  </tr>
  <tr>
    <td></td>
    <td></td>
    <td>1 * 16<br>= 16</td>
    <td>0 * 1<br>= 0</td>
  </tr>
</table>
Another example using 0xFF:
<table align="center">
  <tr>
    <th>16 ^ 3 = <br>(4096)</th>
    <th>16 ^ 2 = <br>(256)</th>
    <th>16 ^ 1 = <br>(16)</th>
    <th>16 ^ 0 = <br>(1)</th>
  </tr>
  <tr>
    <td></td>
    <td></td>
    <td>F</td>
    <td>F</td>
  </tr>
  <tr>
    <td></td>
    <td></td>
    <td>F * 16<br>=<br>15 * 16<br>= 240</td>
    <td>F * 1<br>=<br>15 * 1<br>= 15</td>
  </tr>
</table>

240 + 15 = 255, or the max value of a byte. Bytes in hexadecimal have 2 digits, like 0xFF or 0xA3.

In Flux there are 3 primitive types known as `int`, `float`, and `char`.  
- `int` types are 32 bits long (4 bytes)
- `float` types are 64 bits long (8 bytes)
- `char` types are 8 bits long (1 byte)

We also have a **super-primitive** known as `data`. Any primitive type can convert to `data` and back.  
We will go over the `data` keyword in depth later in this guide.

This is the fundamental understanding of data required going into Flux.   
If you're still following, congratulations. Now we get to actually learn to code.

---

## Your first program.

We're going to start off doing something very simple. We're not going to see anything happen, but the purpose of this excercise is to familiarize you with the process of compilation.

Flux program have a `main()` function. `main()` is called by your operating system automatically.  
Not having a `main()` function will result in a compilation error. Compiling programs without a `main()` function is how we create libraries. As far as we're concerned - and until we get to libraries - all programs we write **must** have a `main()` function.

#### f1.1:
```
def main() -> int
{
    return 0;
};
```
This program does nothing. It will start and immediately stop. If you compile and run this, you will think something is broken, or did not work. This is actually expected behavior, we shouldn't see anything because the program didn't do anything.

This is what you could call the skeleton of a Flux program. Any program you compile into an executable must have a main function defined in **global scope**.

- **What are *global* and *scope*? What is *global scope*?**  
A global is something that can be referred to anywhere in the program. It exists so long as it isn't destroyed or invalidated in some way. Imagine a tree:
 <ul id="myUL">
  <li><span class="caret">Program</span>
    <ul class="nested">
      <li>int a = 1</li>
      <li><span class="caret">myFunction()</span>
        <ul class="nested">
          <li>int b = 0</li>
        </ul>
      </li>
      <li><span class="caret">main()</span>
        <ul class="nested">
          <li>int c = a + b</li>
        </ul>
      </li>
    </ul>
  </li>
</ul>

If we look at this tree, we can see `int a`, `myFunction()` and `main()` exist at the same level as each other.  
Figure 1.2 demonstrates this program.

#### f1.2
```
// Double slashes are comments, the compiler ignores this as if it doesn't exist

int a = 1;      // This is in global scope.

def myFunction() -> int
{
    int b = 0;  // This is in myFunction's scope.
    return b;
};

def main() -> int
{
    int c = a + b;  // Error here
    return c;
};
```

If we try to compile this program, we will get an unknown identifier error at line 13 column 16. The unknown identifier is `b`.  
Why is `b` unknown? As far as `main()` is aware, the only things that exist to it are `a` and `myFunction`.  
`myFunction` is totally aware of `b` because it's in scope. How would we fix this? Like so,
#### f1.3
```
int a = 1;

def myFunction() -> int
{
    int b = 0;
    return b;
};

def main() -> int
{
    int c = a + myFunction();  // myFunction returns the value of b
    return c;
};
```

- **What exactly is a function?**  
A function is a section of your program which does something. A function might check if two things are equal to each other, or it might handle authorization. It does whatever you write the function to do. Algorithms are a collection of functions that when executed in a specific order achieve a desired result.

In figure 1.3 we see two functions, `main()` and `myFunction()`.

Program execution always begins at `main()`. The first thing that happens is we create a new integer variable named `c` and assign it the value `a + myFunction()`. In order to evaluate this, we need to know what `myFunction()` equals, so we call the function (execute it), and it returns the value `0`. Then `a + 0` is evaluated as `1 + 0` and becomes `1`. After evaluating everything to the right of the `=`, we assign the result to `c`.

Take the time to make your own functions, play around and name them whatever you like, then compile your program.

---

## 2 - Simple Functions

### Temperature Conversion (C / F)
We're going to write a program to convert centigrade to fahrenheit.  
The formula for fahrenheit is °F = (°C * 9/5) + 32  
The formula for centigrade is °C = (°F - 32) * 9/5

Here's how we implement this:
#### f2.1
```
def c_to_f(float temp) -> float
{
    return (temp * (9/5)) + 32;
};

def f_to_c(float temp) -> float
{
    return (temp - 32) * (9/5);
};

def main() -> int
{
    int c = -40;
    int f = c_to_f(c);  // -40 °C == -40 °F
    return 0;
};
```

### Calculating distance
#### f2.2
```
def get_distance(float speed, float time) -> float
{
    return speed * time;
};

def to_meters(float distance) -> float
{
    return distance / 3.28084;
};

def main() -> int
{
    float speed = 88;    // Calculating in feet per second
    float time = 60;     // 1 second
    float d = get_distance(speed, time);  // 5,280 feet = 1 mile
    float m = to_meters(d);               // 1,609.34 meters
    return 0;
};
```

### Performing logic
#### f2.3
```
int a = 0;
int b = 100;

def main() -> int
{
    if (a < b)
    {
        a = b;
    };

    return 0;
};
```

`if` statements evaluate truth. All that is really happening is the expression inside of the parenthesis is evaluated, and if it's true, we do the code inside the `if` block.
- Blocks are `{}` and the code within it. In figure 2.3 there are 2 blocks.  

### Logically performing logic
#### f2.4
```
int a, b, c = 0, 100, 1000;

def main() -> int
{
    if (a < b)
    {
        println(b);
    }
    elif (a < c)
    {
        println(c);
    };

    return 0;
};
```
Result:
`100`

#### f2.5
```
int a = 0,
    b = 100,
    c = 1000;

def main() -> int
{
    if (a < b)
    {
        println(b);
    };
    if (a < c)
    {
        println(c);
    };

    return 0;
};
```
Result:
```
100
1000
```
---

## 3 - Hello World
We now have a basic understanding of functions, and logical operations. Now it's time we see something happen on the screen.

#### f3.1 Hello World
```
#import "standard.fx";

using standard::io::console;   // Contains print()

def main() -> int
{
    print("Hello World!\0");
    return 0;
};
```
Result:  
`Hello World!`

The `print()` function will output a string to standard output. It takes 1 argument, the type of the argument is `unsigned data{8}[]` which is an unsigned byte array.

- **What's the difference between `signed` and `unsigned`?**  
Signed integers can have a positive or negative value. The *sign* is 0 for positive, 1 for negative. Typically the most significant bit (largest value) represent the signedness of an integer.  
Example if we have a binary value `10000000` and we treat it as signed it equals `-128`.  
If this value was unsigned, it would equal `128`.  
This means if we tried to interpret a character like the capital letter `A` as signed, we would still get A, but as soon as we go higher than `127` the value wraps around to the negatives and counts upwards towards zero. The ASCII table does not have negative values, only `0-255`.

#### f3.2 What's your name?
```
import "standard.fx";

using standard::io::console; // Also includes input()

def main() -> int
{
    int max = 32;
    byte[max] name;
    print("What's your name? \0");
    int bytes_read = input(@name, max);
    print(); // Empty prints perform newlines
    print("Hello, \0"); print(@name, bytes_read); print("!\0")
    return 0;
};
```
Result:
```
What's your name? John
Hello, John!
```

That code was a little ugly, don't you think? Hard to read unless you take the time to look.  
Also, what was that `\n` thing we printed? That is called an escape character. We "escape" the string with the backslash (`\`). There are a few escape characters to go over, but for now, `\n` is all we need.  
This character represents a new line, or "carriage return". In reality, no text file you have ever read actually breaks words onto a new line  
like this.  
What's actually happening is there is an invisible character which instructs a text editor to move to a new line. In memory, the file spans linearly, it doesn't break into lines. We write programs to show these line breaks.
#### f3.3 Introducing `f-strings`:
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int max = 32;
    byte[max] name;
    print("What's your name? ");
    int bytes_read = input(@name, max);
    println(f"Hello, {name}!");
    return 0;
};
```
Result:
```
What's your name? John
Hello, John!
```
That's better. Here we see a string `f"Hello, {name}!"` but it is prefixed with an `f`. This makes this string an `f-string`. Flux also has something called an `i-string` but those are more advanced, we'll save them for later.

---

## 4 - String Manipulation
We will now learn different ways we can play with strings, starting by slicing them up.
#### f4.1 Slices
```
#import "standard.fx";

using standard::io::console,
      standard::strings;

def main() -> int
{
    string s("Testing!");
    print(s.val()[0:3]);
    return 0;
};
```
Result:  
`Test`

What did we just do? What is that `[0:3]` notation?  
This is known as array slice notation.  
It translates to "start at position 0, end at position 3". That totals 4 bytes, or `"Test"`.  
- `[x:y]`  
**x** is the starting point, and **y** is the ending point. All slicing in Flux is inclusive.

The `standard::strings::string` type has a `length` attribute which you can use to make some things easier.

#### f4.2 Reverse a String
```
#import "standard.fx";

using standard::io::console,
      standard::string;

def main() -> int
{
    string s("Testing!\0");
    print(s.val()[s.length:0]);
    return 0;
};
```
Result:  
`!gnitseT`

To reverse an array, which is what a string is, we do `[len - 1:0]`.
If the first parameter is larger than the second, it means we're traversing the array in descending order.

- **Why do we subtract 1 from the length of the string?**  
Computers count starting at 0, meaning 9 is the 10th number when computers count. If my string length is 10, that means the last element is at position 9. Position 10 is outside of the array, and as far as the computer is concerned, position 10 is undefined. It's like saying:  
**`[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`** = 10 elements  
You can do this, but it may result in a crash or undefined behavior.  
This is why we must always be aware of our data types, sizes, and array lengths.

#### f4.3 The `sizeof()` Keyword
Characters are one byte in size. Strings are an array of bytes, interpreted as characters.  
If I have 40 characters, that's 40 bytes.  
`sizeof()` returns the size of something in bits, not bytes.  
This means we must be aware of the bit length of our types.

```
#import "standard.fx";

using standard::io::console,
      standard::strings;

def main() -> int
{
    string s("Testing!");
    print(f"The length of string s is {s.length} characters long.");
    return 0;
};
```
Result:  
`The size of string s is 8 characters long.`

#### f4.4 Constant Values
Sometimes we want to make sure there's no possible way a value can change.  
We do that by using the `const` keyword, like so:
```
const int myAge = 21;  // Forever 21!
```
If we try to change the value of `myAge` we will get a compile error. Example:
```
const bool authorized = false;

def main() -> int
{
    if (!authorized)    // false == false, therefore true
    {
        authorized = true;  // Compile error.
    };
    return 0;
};
```
---

## 5 - `data` and `struct`
Remember that `data` keyword from a few segments ago? Here's what it looks like:
```
data{32} as u32;
```
This new `u32` type is unsigned, and 32 bits wide.  
`data` is used to create new data types. These types are primitives, unsigned by default, and are not functional.  
We'll expand more about `data` after you learn about structures.

- **What exactly is a `struct`?**  
"struct" is short for structure. In other OOP languages, structs can be functional. In Flux, this is not the case. Structs are strictly data-only containers, bringing us back to the land of pure data structures.

#### f5.1 Primitive Data Structures in Flux
```
import "io.fx", "types.fx";

using standard::io::console, types::string;

struct Point
{
    float x, y, z;
};

def main() -> int
{
    int sizeitems = sizeof(Point) / sizeof(float);
    int sizebytes = (sizeof(Point) / sizeof(float)) * (sizeof(float) / 8);
    print(f"The size of the Point structure in bytes is {sizebytes}.");
    print(f"The size of the Point structure is {sizeitems} items.");
    return 0;
};
```
Result:  
```
The size of the Point structure in bytes is 24.
The size of the Point structure is 3 items.
```

Here we have a basic structure representing 3D point. We create 3 floats, `x`,`y`, and `z`.  
You do not need to initialize or create an instance of a struct to yield information about it.  
Struct sizes cannot be modified, meaning once we declare the struct we cannot add new members to it.

#### f5.2 Calculating the distance between two 3D points
```
import "io.fx", "types.fx";

using standard::io::console, types::string;

struct Point
{
    float x, y, z;
};

def sqrt(float x) -> float
{
    return x ^ 0.5;
};

def distance(Point a, Point b) -> float
{
    return sqrt( ((b.x - a.x) ^ 2) + ((b.y - a.y) ^ 2) + ((b.z - a.z) ^ 2) );
};

def main() -> int
{
    Point p1 = {x = 4.1, y = 5.05, z = -3.9};
    Point p2 = {x = 10, y = -7.33, z = 2.12};

    float dist = distance(p1, p2);
    
    print(f"The distance between p1 and p2 is {dist}");
    return 0;
};
```
Result:  
`The distance between p1 and p2 is 14.977142584618734`

Here we take `Point` and *instance* (*create*) two independent copies of it called `p1` and `p2`. Whenever we refer to an instance of something, we are talking about an independent copy that has the same attributes as the `struct` or `object` it was made from. Objects are too advanced yet, so let's continue with structures.

- **Why can't structures have new members added to them?**  
This has to do with how programs compile. In other languages, structs have a lot of functionality which makes them very similar to classes with some key changes. However, structs having functionality requires the compiler to generate **virtual call tables** or `vtables` for them. This increases complexity for the resulting executable. Flux's goal is to create fast, small executables; to do this, we made structures non-flexible data-only containers.

#### f5.3 Modelling a File Format Header with `struct`
For this example we will be modeling the [Bitmap File Format](https://www.ece.ualberta.ca/~elliott/ee552/studentAppNotes/2003_w/misc/bmp_file_format/bmp_file_format.htm).
##### f5.3.1
<p align="center">
<img src="https://upload.wikimedia.org/wikipedia/commons/7/75/BMPfileFormat.svg">
</p>

Using this schematic we will capture the header of a `.bmp` image but not the color table.  
```
#import "standard.fx";

using standard::io::console;

struct Header
{
    unsigned data{16} sig;  // Not a type declaration, sig is a variable of this type
    unsigned data{32} filesize, reserved, dataoffset;  // Structured in the order they appear
};

struct InfoHeader
{
    unsigned data{32} size, width, height;
    unsigned data{16} planes, bitsperpixel;
    unsigned data{32} compression, imagesize, xpixelsperm, ypixelsperm, colorsused, importantcolors;
};

struct BMP
{
    Header header;
    InfoHeader infoheader;
    // ...
};

def main() -> int
{
    File bmpfile = open("image.bmp", "r");
    bmpfile.seek(0);
    byte[bmpfile.length] buffer = bmpfile.readall();
    bmpfile.close();

    // We now have the file in the buffer. Time to capture that data.
    Header hdata;
    int hdlen = sizeof(hdata) / ( 2 + (4 * 3) );  // 2 bytes + 4x3 bytes
    InfoHeader ihdata;
    int ihdlen = sizeof(ihdata) / ( (4 * 9) + (2 * 2) ); // 9x4 bytes + 2x2 bytes

    hdata = (Header)buffer[0:hdlen - 1];            // Capture header
    ihdata = (InfoHeader)buffer[hdlen:ihdlen - 1];  // Capture info header
    print((char[2])hdata.sig);
    return 0;
};
```
Result:  
`BM`

Alternatively, on the lines we capture the data into our structs, if we had all the information about the file such as the file size, image size, etc, we could dynamically create the BMP struct, and capture like so:
```
BMP bitmap;
bitmap = (BMP)buffer;
```
Since the BMP struct would 100% reflect the file's dimensions, it perfectly captures all data into the members of the struct accordingly.

- **(What) is this? What's (that)thing there?**  
What you're seeing is called **cast notation**. Casting converts one type to another.  
In this case, casting data to a structure results in the data aligning to the struct - this is also known as **data structuring**.

#### f5.4 Restructuring
```
#import "standard.fx";

using standard::io::console;
using types::string;

struct Values32
{
    i32 a, b, c, d;
};

struct Values16
{
    i16 a, b, c, d, e, f, g, h;
};

def main() -> int
{
    Values32 v1 = {a=10, b=20, c=30, d=40};
    Values16 v2 from v1;    // Restructure

    print(f"{v2.a} {v2.b} {v2.c} {v2.d}\n");
    return 0;
};
```
Result:  
```
v2.a = 0
v2.b = 10
```

- **Why does v2.a equal 0?**  
We converted a struct that contained 32 bit integers into a struct of 16 bit integers.  
Here's what the value 10 looks like in 32 bits:

<table align="center">
  <tr>
    <th>(2,147,483,648)</th>
    <th>(1,073,741,824)</th>
    <th>(536,870,912)</th>
    <th>(268,435,456)</th>
    <th>(134,217,728)</th>
    <th>(67,108,864)</th>
    <th>(33,554,432)</th>
    <th>(16,777,216)</th>
    <th>(8,388,608)</th>
    <th>(4,194,304)</th>
    <th>(2,097,152)</th>
    <th>(1,048,576)</th>
    <th>(524,288)</th>
    <th>(262,144)</th>
    <th>(131,072)</th>
    <th>(65,536)</th>
    <th>(32,769)</th>
    <th>(16,384)</th>
    <th>(8,192)</th>
    <th>(4,096)</th>
    <th>(2,048)</th>
    <th>(1,024)</th>
    <th>(512)</th>
    <th>(256)</th>
    <th>(128)</th>
    <th>(64)</th>
    <th>(32)</th>
    <th>(16)</th>
    <th>(8)</th>
    <th>(4)</th>
    <th>(2)</th>
    <th>(1)</th>
  </tr>
  <tr>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>0</td>
    <td>1</td>
    <td>0</td>
    <td>1</td>
    <td>0</td>
  </tr>
</table>

What we're doing is splitting one 32 bit integer into two 16 bit integers.  
The first 16 bits of the array above are 0. The last are `0000000000001010`.  
So `v2.a` which is `i16` type (16 bits wide) gets all zeros, `v2.b` gets the remainder `0000000000001010`.

Say we use `Values16` to create a new instance called `v3`, and we swap the order of `a` and `b`. Then we cast it to a new instance `v4` which is type `Values32`.
```
#import "standard.fx";

using standard::io::console;

struct Values32
{
    i32 a, b, c, d;
};

struct Values16
{
    i16 a, b, c, d, e, f, g, h;
};

def main() -> int
{
    Values32 v1 = {a=10, b=20, c=30, d=40};
    Values16 v2 from v1;    // Restructure
    Values16 v3 = {a=v2.b, b=v2.a, c=v2.c, d=v2.d, e=v2.e, f=v2.f, g=v2.g, h=v2.h};
    Values32 v4 from v3;    // Restructure

    print(f"v4.a = {v4.a}\n");
    return 0;
};
```
Result:  
`v4.a = 655360`

- **Why is the value so much larger than 10?**  
We swapped the order of the bits, essentially rotating them left 16 spaces.

---

## 6 - Warming Up
Logical flow can be handled two ways. The slow way, or the fast way.  
What's the difference?

- `if` statements are extremely slow.  
Every condition of an `if/elif/else` chain needs to be evaluated. If there are 10 conditions, that requires 10 additional evaluations which consume CPU cycles. If you have some heavy duty algorithm, you should opt for `switch` statements.

- `switch` statements are extremely fast.  
Every condition is known at compile time, so a more optimized jump table can be created.

#### f6.1 A little game.
```
#import "standard.fx", "random.fx";

using standard::io::console,
      standard::strings,
      math::random;

def main() -> int
{
    string s = "";  // Syntactic sugar for single-parameter constructors like __init(byte*)
    int value,
        rand;

    while (true)
    {
        s = input("Enter a value from 0-10: ");
        value = s.as_int();
        rand = rand_int(0,10);

        switch (value)
        {
            case (rand)
            {
                print("You win! Keep going!");
                continue;
            }
            default
            {
                print(f"You lose! The value was {rand}. Game over.");
                break;
            };
        };
    };
    return 0;
};
```
Result:  
```
Enter a value from 0-10: 7
You win! Keep going!
Enter a value from 0-10: 9
You lose! The value was 2. Game over.
```

Here we're introduced to 2 new keywords, `switch` and `while`.

`while` is a keyword that means while the condition is true, execute this block repeatedly.  
`break` exits the loop immediately. You may use `break` in any loop.  
`continue` goes to the next iteration (cycle) of the loop.

`switch` statements have 2 sub-keywords, called `case` and `default`.  
All switches **must** have a default, the default branch executes when no cases match the condition.

#### f6.2 `for`, `do`, `while`, and `do`-`while` loops
We can do loops a few different ways. Loops repeat themselves until a condition is met.  

`while` is like an `if` statement + a loop, they continue to loop while the condition is true.  
A `while` loop will check the condition first, and if it's true it will execute the block.

A `do`-`while` loop will execute its block before checking the condition. Here's an example of the difference.

#### f6.2.1 `do`-`while`
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int start, end = 0, 3;

    do
    {
        if (start >= end)
        {
            print("You fell off the cliff!");
            break;
        };
        print("You take a step.\n");
        start++;
    }
    while (start < end);

    return 0;
};
```
Result:
```
You take a step.
You take a step.
You take a step.
```

#### f6.2.2 `while` without `do`
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int start = 0,
        end = 3;

    while (start < end)
    {
        if (start >= end)
        {
            print("You fell off the cliff!");
            break;
        };
        print("You take a step.\n");
        start++;
    };

    return 0;
};
```
Result:
```
You take a step.
You take a step.
You take a step.
```

As you can see, these programs run identically.  
In figure 6.2.1 we go past the end and fall off the imaginary cliff.  
In figure 6.2.2 we make sure we're not at the end before taking a step.  
`do`-`while` loops are guaranteed to execute their block **at least once**.  
A `while`-only loop may not execute at all in some circumstances.

#### f6.3.1 `for` Style 1: initializer, condition, expression
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    for (int counter; counter < 3; counter++)
    {
        print(f"All you're base are belong to us.\n");
    };
    return 0;
};
```
Result:
```
All you're base are belong to us.
All you're base are belong to us.
All you're base are belong to us.
```

#### f6.3.2 `for` Style 2: element in array
```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    int[10] int_array = [11, 22, 33, 44, 55, 66, 77, 88, 99, 00];

    for (x in int_array)
    {
        print(f"{x}\n");
    };
    return 0;
};
```
Result:
```
11
22
33
44
55
66
77
88
99
0
```

#### f6.4 Sizing an array of non-standard type width:
In Flux you are bound to come across an array like:  
```
signed data{20} as someType;
someType[50] someArray;
```
The reason we've been dividing `sizeof` results by `8` is because we've been sizing an array of bytes. In figure 6.4, `someType` is `20` bits wide so we divide the `sizeof(someArray)` by `sizeof(someType)` to get the number of elements.

---

## 7 - Object-Oriented Programming (OOP)
We're not burning rubber on the track yet, but we are at the races.

- **What is an `object`?**  
Objects in Flux are an imaginary container, like structures, but they can have functionality.  
They are used to model real-world things.  
We add attributes to change what these empty containers represent. Just like we add attributes to mirror the structure of a file, we add attributes to mirror the details of a real-life object or system. For example, a car object could have the attributes `paintColor`, `maxSpeed`, and `weight`, and functions like `accelerate()`, `applyBrake()`, `steer()` and `shiftGear()`.
- **What does it mean to "have functionality"?**  
Imagine teaching your dog to fetch a specific toy. You have added "that specific toy fetching"-functionality to your dog.  
A function of your smartphone is to make and receive calls.

What does an `object` look like?
#### f7.1
```
object myObject
{
    // Constructor Function - must be present
    def __init() -> this
    {
        // Can place any code you want in here.
        return this;  // Must be present.
    };

    // Destructor Function - must be present
    def __exit() -> void
    {
        // Can place any code you want in here.
        return void;  // Must be present.
    };
};
```
This is the minimum boilerplate for an object. It must have a constructor, and a destructor function defined exactly as so.  You can change the constructor or destructor definitions, but their signatures and return values must be the same.  
Without the comments (`//`) or delimeters (`{}`) an object is only 5 lines of code to prepare.  

Now that we see what objects look like, let's try doing something with them.

#### f7.2 Modeling a lock with `object`
```
#import "standard.fx";

using standard::io::console;

object Lock
{
    bool status = false;  // We'll treat false as unlocked, true as locked.

    def __init() -> this
    {
        print("Created a new lock.\n");
        return this;
    };

    def __exit() -> void
    {
        print("Lock destroyed.\n");
    };

    def doThis() -> void
    {
        switch (this.status())
        {
            case (true)
            {
                println("Error: Locked.");
            }
            default
            {
                println("Doing this!");
            };
        };
    };

    def status() -> bool
    {
        switch (this.status)
        {
            case (true)
            {
                println("Status: Locked.");
                return true;
            }
            default
            {
                println("Status: Unlocked.");
                return false;
            };
        };
        return false;
    };

    def lock() -> void
    {
        println("Locking...");
        this.status = true;
        println("Locked.");
    };

    def unlock() -> void
    {
        println("Unlocking...");
        this.status = false;
        println("Unlocked.");
    };
};

def main() -> int
{
    Lock lock();


    lock.doThis();
    lock.lock();
    lock.doThis();
    lock.unlock();
    lock.doThis();

    return 0;
};
```
Result:
```
Created a new lock.
Status: Unlocked.
Doing this!
Locking...
Locked.
Status: Locked.
Error: Locked.
Unlocking...
Unlocked.
Status: Unlocked.
Doing this!
```
The example above shows a very basic programmatic lock.  
`doThis()` checks the lock status before doing anything else, and shows us an error if it's locked.

#### f7.3 Inheritance
The concept of inheritance is all about reusability. It allows us to not have to write so much code depending on what we're trying to accomplish. We're going to look at `struct` inheritance first, then we'll do `object` inheritance.

#### f7.3.1 Struct Inheritance
We're going to re-use the BMP example, but slightly modified to demonstrate *how* inheritance for structs works. It's important to understand the semantics behind `struct` inheritance when dealing with complex structures and how they relate to `data`.
```
struct Header
{
    unsigned data{16} sig;
    unsigned data{32} filesize, reserved, dataoffset;
};

struct InfoHeader
{
    unsigned data{32} size, width, height;
    unsigned data{16} planes, bitsperpixel;
    unsigned data{32} compression, imagesize, xpixelsperm, ypixelsperm, colorsused, importantcolors;
};

struct BMP : Header, InfoHeader;
```
Here we see `:` after the struct name, this indicates inheritance. It's as if `BMP` is now defined as:
```
struct BMP
{
    unsigned data{16} sig;
    unsigned data{32} filesize, reserved, dataoffset;
    unsigned data{32} size, width, height;
    unsigned data{16} planes, bitsperpixel;
    unsigned data{32} compression, imagesize, xpixelsperm, ypixelsperm, colorsused, importantcolors;
};
```
Inheritance operates in the order the bases (inherited structs) appear. This is to maintain the 1:1 mapping to `data` and allow us to do *serialization/deserialization* without *marshalling*.

- **What are serialization and deserialization?**
Serialization in programming is the process of converting a data structure into a format that can be stored or transmitted and reconstructed later. This format is typically a sequence of bytes or characters. Deserialization is the reverse of this process, and in Flux is called **restructuring**. It is done by casting any arbitrary sequence of bits to a `struct` of equal bit length. If the bit-lengths are not equal, it will result in a runtime error and undefined behavior.

- **What is marshalling?**
This refers to the process of transforming data structures into a format suitable for transmission across different environments, such as over a network, between different processes, or between different programming languages. This process is often necessary when data needs to cross boundaries where direct memory access or shared object representations are not possible.

---

## 8 - Functions in Depth

We've been using functions throughout this guide - `main()`, `print()`, and methods inside objects. Now it's time to understand them fully. Functions are reusable blocks of code that perform specific tasks. Think of them as recipes: you define the steps once, then you can follow that recipe whenever you need it.

#### f8.1 Defining Your First Function

Let's start simple. A function needs:
1. A name (what it's called)
2. Parameters (what data it needs)
3. A return type (what data it gives back)
4. A body (the code it runs)

```
def add_nums(int x, int y) -> int
{
    return x + y;
};
```

This function is named `add_nums`. It takes two integers (`x` and `y`), adds them together, and returns the result.

Let's use it:
```
#import "standard.fx";

def add_nums(int x, int y) -> int
{
    return x + y;
};

def main() -> int
{
    int result = add_nums(5, 3);
    print("5 + 3 = \0");
    print(result);
    print("\n\0");
    return 0;
};
```
Result:
```
5 + 3 = 8
```

#### f8.2 Parameters and Arguments

**Parameters** are the variables you define in the function signature. **Arguments** are the actual values you pass when calling the function.

```
def greet(int age) -> void  // 'age' is a parameter
{
    print("You are \0");
    print(age);
    print(" years old!\n\0");
    return;
};

def main() -> int
{
    greet(25);  // 25 is an argument
    greet(30);  // 30 is an argument
    return 0;
};
```
Result:
```
You are 25 years old!
You are 30 years old!
```

Functions can have multiple parameters:
```
def introduce(int age, int height) -> void
{
    print("Age: \0");
    print(age);
    print(", Height: \0");
    print(height);
    print(" cm\n\0");
    return;
};

def main() -> int
{
    introduce(25, 175);
    introduce(30, 182);
    return 0;
};
```

#### f8.3 Return Values

The `return` statement does two things:
1. Exits the function immediately
2. Sends a value back to whoever called the function

```
def multiply(int a, int b) -> int
{
    int result = a * b;
    return result;       // Can do: return a * b;
};

def main() -> int
{
    int answer = multiply(7, 6;
)    print(f"7 * 6 = {answer}");
    return 0;
};
```

You can return early from a function:
```
def divide(int a, int b) -> int
{
    if (b == 0)
    {
        print("Error: Cannot divide by zero!\n\0");
        return 0;  // Exit early with a safe value
    };
    return a / b;
};

def main() -> int
{
    print(divide(10, 2));  // Prints 5
    print("\n\0");
    print(divide(10, 0));  // Prints error, returns 0
    print("\n\0");
    return 0;
};
```

#### f8.4 Void Functions

Sometimes a function doesn't need to return anything - it just performs an action. We use `void` as the return type:

```
def print_border() -> void
{
    print("====================\n\0");
    return;
};

def main() -> int
{
    print_border();
    print("Welcome to Flux!\n\0");
    print_border();
    return 0;
};
```
Result:
```
====================
Welcome to Flux!
====================
```

#### f8.5 Scope - Where Variables Live

Variables have a **scope** - they only exist in certain parts of your code. Think of scope like rooms in a house: what's in one room isn't automatically available in another.

```
int globalVar = 100;  // This exists everywhere

def some_func() -> void
{
    int localVar = 50;  // This only exists inside some_func
    print("Inside function: \0");
    print(localVar);
    print("\n\0");
    print("Global var: \0");
    print(globalVar);
    print("\n\0");
    return;
};

def main() -> int
{
    print("In main, global var: \0");
    print(globalVar);
    print("\n\0");
    
    some_func();
    
    // print(localVar);  // ERROR! localVar doesn't exist here
    
    return 0;
};
```

Variables defined inside a function are **local** to that function. Variables defined outside all functions are **global** and can be accessed anywhere.

#### f8.6 Function Overloading

Flux lets you create multiple functions with the same name, as long as they have different parameters:

```
def calculate(int x) -> int
{
    return x * 2;
};

def calculate(int x, int y) -> int
{
    return x * y;
};

def main() -> int
{
    print(calculate(5));      // Uses first version: 5 * 2 = 10
    print("\n\0");
    print(calculate(5, 3));   // Uses second version: 5 * 3 = 15
    print("\n\0");
    return 0;
};
```

The name, paramters, and return type form a function's `signature`. If the signatures are different, you're all set!  
The compiler picks the right function based on what - and how many - arguments you provide, and what the function call is returning to.

#### f8.7 Practical Examples

Let's make a simple calculator:
```
#import "standard.fx";

using standard::io::console;

def add(int a, int b) -> int
{
    return a + b;
};

def subtract(int a, int b) -> int
{
    return a - b;
};

def multiply(int a, int b) -> int
{
    return a * b;
};

def divide(int a, int b) -> int
{
    if (b == 0)
    {
        print("Error: Division by zero!\n\0");
        return 0;
    };
    return a / b;
};

def main() -> int
{
    int x, y = 20, 4; // x = 20, y = 4

    println("x + y = {add(x,y)}");
    println("x - y = {subtract(x,y)}");
    println("x * y = {multiply(x,y)}");
    println("x / y = {divide(x,y)}");

    return 0;
};
```
Result:
```
x + y = 24
x - y = 16
x * y = 80
x / y = 5
```

Here's a function that checks if a number is even:
```
#import "standard.fx";

using standard::io::console;

def isEven(int num) -> bool
{
    if (num % 2 == 0)
    {
        return true;
    };
    return false;
};

def main() -> int
{
    for (int i; i < 10; i++)
    {
        switch(isEven(i))
        {
            case (true) { println(f"{i} is even"); }
            default
            {
                println(f"{i} is odd");
            };
        };
    };
    return 0;
};
```
Result:
```
0 is even
1 is odd
2 is even
3 is odd
4 is even
5 is odd
6 is even
7 is odd
8 is even
9 is odd
```

#### f8.8 Building with Functions

Functions help you break down complex problems into smaller, manageable pieces. Each function should do one thing well.

```
def celsius_to_fahrenheit(float celsius) -> float
{
    return (celsius * 9.0 / 5.0) + 32.0;
};

def fahrenheit_to_celsius(float fahrenheit) -> float
{
    return (fahrenheit - 32.0) * 5.0 / 9.0;
};

def main() -> int
{
    float temp_c = 25.0;
    float temp_f = celsius_to_fahrenheit(temp_c);
    
    print("25°C = \0");
    print(temp_f);
    print("°F\n\0");
    
    float back_to_c = fahrenheit_to_celsius(temp_f);
    print("Converting back: \0");
    print(back_to_c);
    print("°C\n\0");
    
    return 0;
};
```

Functions make your code:
- **Reusable** - write once, use many times
- **Readable** - good function names explain what the code does
- **Testable** - you can test each function separately
- **Maintainable** - fix or improve one function without breaking others

---

## 9 - Working with Strings

Strings are how we work with text in programs. In Flux, strings are arrays of characters. We've used strings with `print()` throughout this guide, but now let's understand them properly.

#### f9.1 What is a String?

A string is a sequence of characters. Remember from Section 1 that characters are just numbers (ASCII values). A string is an array of these numbers:

```
char[] myString = ['H','e','l','l','o','\0'];
```

The `\0` at the end is the **null terminator** - it tells the computer where the string ends. In Flux, string literals need a null terminator `\0` unless you set your configuration to allow the compiler to null terminate your strings. The default setting is enabled.

#### f9.2 String Basics

```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    char[] greeting = ['H','e','l','l','o',',',' ','w','o','r','l','d','!','\0'];
    println(greeting);
    
    char[] name = ['A','l','i','c','e','\0'];
    println(f"My name is {name}.");
    
    return 0;
};
```
Result:
```
Hello, World!
My name is Alice.
```

#### f9.3 Accessing Individual Characters

Since strings are arrays, you can access individual characters:

```
#import "standard.fx";

using standard::io::console;

def main() -> int
{
    char[] word = ['F','l','u','x','\0'];
    

    println(f"First character value: {word[0]}");
    
    println(f"Second character value: {word[1]}");

    println(f"First character: {(byte[1])word[0]}");
    
    println(f"Second and third characters: {(byte[2])word[2:3]}");
    
    return 0;
};
```
Result:
```
First character value: 70
Second character value: 108
First character: F
Second character: ux
```

#### f9.4 String Length

To find how long a string is, we count characters until we hit the null terminator:

```
#import "standard.fx";

using standard::io::console,
      standard::strings;

def main() -> int
{
    noopstr text = "Programming!\0";
    int len = strlen(text);
    
    println(f"Length: {len}");
    
    return 0;
};
```
Result:
```
Length: 12
```

#### f9.5 Comparing Strings

To check if two strings are equal, you need to compare each character:

```
def compare_string_chars(char[] str1, char[] str2) -> bool
{
    int i = 0;
    for (i = 0; i < 1000; i++)
    {
        if (str1[i] != str2[i])
        {
            return false;  // Found a difference
        };
        
        if (str1[i] == 0)  // Both reached end at same time
        {
            return true;
        };
    };
    return false;
};

def main() -> int
{
    char[] word1 = "cat\0";
    char[] word2 = "cat\0";
    char[] word3 = "dog\0";
    
    if (compare_string_chars(word1, word2))
    {
        print("word1 and word2 are the same\n\0");
    };
    
    if (!compare_string_chars(word1, word3))
    {
        print("word1 and word3 are different\n\0");
    };
    
    return 0;
};
```

#### f9.6 Copying Strings

You can't just assign one string to another - you need to copy character by character:

```
def copyString(char[] dest, char[] src) -> void
{
    int i = 0;
    for (i = 0; i < 1000; i++)
    {
        dest[i] = src[i];
        if (src[i] == 0)  // Copied null terminator, we're done
        {
            return;
        };
    };
    return;
};

def main() -> int
{
    char[] original = "Hello!\0";
    char[100] copy;  // Make sure it's big enough
    
    copyString(copy, original);
    
    print("Original: \0");
    print(original);
    print("\n\0");
    
    print("Copy: \0");
    print(copy);
    print("\n\0");
    
    return 0;
};
```

#### f9.7 Building Strings

You can build strings by setting characters one at a time:

```
def main() -> int
{
    char[10] buffer;
    
    buffer[0] = 72;   // 'H'
    buffer[1] = 105;  // 'i'
    buffer[2] = 33;   // '!'
    buffer[3] = 0;    // Null terminator
    buffer[4] = 0;    // Second null
    
    print(buffer);
    print("\n\0");
    
    return 0;
};
```

#### f9.8 Practical String Example

Let's make a function that counts how many times a character appears in a string:

```
def count_chars(char[] str, char target) -> int
{
    int count = 0;
    for (int i = 0; i < 1000; i++)
    {
        if (str[i] == 0)  // End of string
        {
            return count;
        };
        
        if (str[i] == target)
        {
            count++;
        };
    };
    return count;
};

def main() -> int
{
    char[] sentence = "the quick brown fox\0";
    
    print("Counting 'o' in: \0");
    print(sentence);
    print("\n\0");
    
    int o = count_chars(sentence, 111);  // 111 is ASCII for 'o'
    print("Found \0");
    print(o);
    print(" letter 'o's\n\0");
    
    return 0;
};
```
Result:
```
Counting 'o' in: the quick brown fox
Found 2 letter 'o'
```

Strings are fundamental to most programs - user input, file names, messages, etc. Understanding how they work as character arrays is important for working with text effectively.

---

## 10 - Enums and Unions

#### f10.1 Enumerated Lists (Enums)

Sometimes you need to represent a set of named constants. For example, days of the week, colors, or states. Enums make this clean and readable.

Without enums, you might do this:
```
int MONDAY = 0;
int TUESDAY = 1;
int WEDNESDAY = 2;
// ... this gets tedious
```

With enums:
```
enum DayOfWeek
{
    MONDAY,
    TUESDAY,
    WEDNESDAY,
    THURSDAY,
    FRIDAY,
    SATURDAY,
    SUNDAY
};
```

Enums automatically assign values starting from 0:
```
#import "standard.fx";

enum TrafficLight
{
    RED,      // 0
    YELLOW,   // 1
    GREEN     // 2
};

def main() -> int
{
    TrafficLight light;
    light = TrafficLight.RED;
    
    if (light == TrafficLight.RED)
    {
        print("Stop!\n\0");
    };
    
    light = TrafficLight.GREEN;
    
    if (light == TrafficLight.GREEN)
    {
        print("Go!\n\0");
    };
    
    return 0;
};
```
Result:
```
Stop!
Go!
```

#### f10.2 Using Enums in Practice

Enums make your code more readable. Compare these two versions:

**Without enum:**
```
def process_status(int status) -> void
{
    if (status == 0)
    {
        print("Pending\n\0");
    }
    else if (status == 1)
    {
        print("Processing\n\0");
    }
    else if (status == 2)
    {
        print("Complete\n\0");
    };
    return;
};
```

**With enum:**
```
enum Status
{
    PENDING,
    PROCESSING,
    COMPLETE
};

def process_status(Status status) -> void
{
    if (status == Status.PENDING)
    {
        print("Pending\n\0");
    }
    else if (status == Status.PROCESSING)
    {
        print("Processing\n\0");
    }
    else if (status == Status.COMPLETE)
    {
        print("Complete\n\0");
    };
    return;
};
```

The second version is much clearer about what the values mean.

#### f10.3 Enum in Switch Statements

Enums work great with switch statements:

```
enum Direction
{
    NORTH,
    SOUTH,
    EAST,
    WEST
};

def move(Direction dir) -> void
{
    switch (dir)
    {
        case Direction.NORTH:
        {
            print("Moving North\n\0");
        };
        case Direction.SOUTH:
        {
            print("Moving South\n\0");
        };
        case Direction.EAST:
        {
            print("Moving East\n\0");
        };
        case Direction.WEST:
        {
            print("Moving West\n\0");
        };
    };
    return;
};

def main() -> int
{
    Direction heading = Direction.NORTH;
    move(heading);
    
    heading = Direction.WEST;
    move(heading);
    
    return 0;
};
```

#### f10.4 Unions - One Value at a Time

A **union** is like a struct, but it can only hold ONE of its members at a time. Think of it like a box that can hold different things, but only one thing at once.

```
union NumberHolder
{
    int as_int;
    float as_float;
};
```

This creates a union that can store EITHER an int OR a float, but not both simultaneously:

```
def main() -> int
{
    NumberHolder value;
    
    value.as_int = 42;
    print("As integer: \0");
    print(value.as_int);
    print("\n\0");
    
    // Now we change which member is active
    value.as_float = 3.14;
    print("As float: \0");
    print(value.as_float); // Printing a float by default goes 5 decimal places to the right
    print("\n\0");
    
    // WARNING: as_int is now undefined! Don't use it!
    
    return 0;
};
```

#### f10.5 Why Use Unions?

Unions save memory when you only need one type of data at a time:

```
union Data
{
    int error_code;
    float measurement;
    bool success;
};

def process_result(bool is_error, Data result) -> void
{
    if (is_error)
    {
        print("Error code: \0");
        print(result.error_code);
        print("\n\0");
    }
    else
    {
        print("Measurement: \0");
        print(result.measurement);
        print("\n\0");
    };
    return;
};

def main() -> int
{
    Data result1;
    result1.error_code = 404;
    process_result(true, result1);
    
    Data result2;
    result2.measurement = 98.6;
    process_result(false, result2);
    
    return 0;
};
```

#### f10.6 Important Union Rules

1. **Only one member is valid at a time** - accessing the wrong member gives undefined behavior
2. **You must remember which member is active** - the union doesn't track this for you
3. **All members share the same memory** - the union's size is the size of its largest member

Example of what NOT to do:
```
union BadExample
{
    int x;
    float y;
};

def main() -> int
{
    BadExample bad;
    bad.x = 100;
    
    // WRONG! y is not the active member!
    print(bad.y);  // This is undefined behavior!
    
    return 0;
};
```

#### f10.7 Practical Enum and Union Example

Here's a simple state machine using enums and a union:

```
enum State
{
    IDLE,
    RUNNING,
    ERROR
};

union StateData
{
    int idle_count;
    float run_speed;
    int error_code;
};

def main() -> int
{
    State current = State.IDLE;
    StateData data;
    
    // In IDLE state
    data.idle_count = 0;
    print("State: IDLE, Count: \0");
    print(data.idle_count);
    print("\n\0");
    
    // Transition to RUNNING
    current = State.RUNNING;
    data.run_speed = 5.5;
    print("State: RUNNING, Speed: \0");
    print(data.run_speed);
    print("\n\0");
    
    // Transition to ERROR
    current = State.ERROR;
    data.error_code = 123;
    print("State: ERROR, Code: \0");
    print(data.error_code);
    print("\n\0");
    
    return 0;
};
```

Enums help organize related constants, and unions help save memory when you need different types at different times.

---

## 11 - Structs

Structs are one of the most important features in Flux for organizing data. While objects have behavior (functions), structs are pure data containers. Think of a struct as a custom data type you create.

#### f11.1 Why Do We Need Structs?

Imagine you're making a program to track books. Each book has:
- A title
- An author
- A page count
- A price

You could use separate variables:
```
char[] book1_title = "1984\0",
       book1_author = "George Orwell\0";
int book1_pages = 328;
float book1_price = 15.99;

char[] book2_title = "Dune\0",
       book2_author = "Frank Herbert\0";
int book2_pages = 688;
float book2_price = 19.99;
```

This gets messy fast! Instead, we use a struct:

```
struct Book
{
    char[64] title;
    char[32] author;
    int pages;
    float price;
};
```

Now `Book` is a type, just like `int` or `float`.

#### f11.2 Creating and Using Structs

```
#import "standard.fx";

using standard::io::console;

struct Point
{
    int x,
        y;
};

def main() -> int
{
    Point p1;
    p1.x = 10;
    p1.y = 20;
    
    print(f"Point: ({p1.x},{p1.y})");

    return 0;
};
```
Result:
```
Point: (10,20)
```

You access struct members with the dot `.` operator.

#### f11.3 Initializing Structs

You can set values when you create a struct:

```
#import "standard.fx";

using standard::io::console;

struct Rectangle
{
    int width,
        height;
};

def main() -> int
{
    Rectangle rect = {width = 50, height = 30};
    
    print(f"Rectangle: {rect.width} x {rect.height}");

    return 0;
};
```

#### f11.4 Structs with Arrays

Structs can contain arrays:

```
#import "standard.fx";

using standard::io::console,
      standard::string;

struct Student
{
    char[50] name;
    int[5] grades;
};

def main() -> int
{
    Student s1;

    s1.name = "Alice";
    
    s1.grades[0] = 85;
    s1.grades[1] = 92;
    s1.grades[2] = 78;
    s1.grades[3] = 95;
    s1.grades[4] = 88;
    
    println(f"Student: {s1.name}");
    print("Grades: ");
    
    for (x in s1.grades)
    {
        print(f"{x} ");
    };
    
    return 0;
};
```

#### f11.5 Arrays of Structs

You can create arrays of structs:

```
#import "standard.fx";

using standard::io::console;

struct Temperature
{
    int day;
    float celsius;
};

def main() -> int
{
    Temperature[7] week;
    
    week[0] = {day = 1, celsius = 20.5};
    week[1] = {day = 2, celsius = 22.0};
    week[2] = {day = 3, celsius = 19.5};
    
    for (int i; i < 3; i++)
    {
        println(f"Day {week[i].day)}: {week[i].celsius}");
    };
    
    return 0;
};
```
Result:
```
Day 1: 20.500000
Day 2: 22.000000
Day 3: 19.500000
```

#### f11.6 Passing Structs to Functions

Structs can be passed to functions:

```
#import "standard.fx";

using standard::io::console;

struct Circle
{
    float radius;
};

def calc_area(Circle c) -> float
{
    return 3.14159 * (c.radius ^ 2f);
};

def main() -> int
{
    Circle myCircle = {5.0};
    
    float area = calc_area(myCircle);
    
    println(f"Circle with radius {myCircle.radius} has area {area}");
    
    return 0;
};
```
Result:
```
Circle with radius 5.000000 has area 78.539749
```

#### f11.7 Nested Structs

Structs can contain other structs:

```
#import "standard.fx";

using standard::io::console;

struct Date
{
    int day;
    int month;
    int year;
};

struct Event
{
    char[32] name;
    Date date;
};

def main() -> int
{
    Event e;
    e.name = "John's Birthday";
    
    e.date.day = 15;
    e.date.month = 7;
    e.date.year = 2024;
    
    println(f"Event:\t{e.name}");
    println(f"Date:\t{e.date.day}/{e.date.month}/{e.date.year}");
    
    return 0;
};
```
Result:
```
Event:  John's Birthday
Date:   15/7/2024
```

#### f11.8 Structs vs Objects - Key Differences

Remember these important differences:

**Structs:**
- Data only, no functions
- Cannot have methods like `__init()` or `__exit()`
- Non-executable
- Used for organizing related data
- Tightly packed in memory

**Objects:**
- Have both data AND functions (methods)
- Have constructors and destructors
- Executable
- Used for things with behavior
- Can contain structs

```
object Container
{
    struct Box
    {               // Struct definition disallowed inside object
        int value;
    };
    
    Box b;          // Struct instance allowed
};

// This is ILLEGAL - structs cannot contain objects!
struct BadExample
{
    object SomeObject;   // COMPILE ERROR!
    object* pSomeObject; // Legal, can contain pointers to objects.
};
```

#### f11.9 Practical Struct Example

Let's create a simple inventory system:

```
#import "standard.fx";

using standard::io::console;

struct Item
{
    char[50] name;
    int quantity;
    float price;
};

def printItem(Item item) -> void
{
    println(f"Item:\t\t{item.name}");
    println(f"Quantity:\t{item.quantity}");
    println(f"Price:\t\t${item.price}\0");
    return;
};

def totalValue(Item item) -> float
{
    return (float)item.quantity * item.price;
};

def main() -> int
{
    Item[3] inventory;
    
    // First item
    inventory[0].name[0] = 65; // 'A'
    inventory[0].name[1] = 112; // 'p'
    inventory[0].name[2] = 112; // 'p'
    inventory[0].name[3] = 108; // 'l'
    inventory[0].name[4] = 101; // 'e'
    inventory[0].name[5] = 0;   // null-terminate
    inventory[0].quantity = 50;
    inventory[0].price = 1.25;
    
    printItem(inventory[0]);
    println(f"Total value:\t${totalValue(inventory[0])}");
    
    return 0;
};
```
Result:
```
Item:           Apple
Quantity:       50
Price:          $1.250000
Total value:    $62.500000
```

Structs are essential for organizing complex data. They let you group related information together and treat it as a single unit.

---

## 12 - Putting It All Together

Congratulations! You've learned the fundamentals of programming with Flux. Let's review what you know and see how it all fits together.

#### f12.1 What You've Learned

**Core Concepts:**
- How computers store and interpret data (bits, bytes, memory)
- Variables and data types (`int`, `float`, `char`, `bool`)
- Operators for math, logic, and comparison
- Control flow (if/else, loops, switch)
- Arrays for storing collections of data
- Functions for organizing reusable code
- Strings for working with text
- Enums for named constants
- Unions for storing one of several types
- Structs for organizing related data
- Objects for combining data with behavior

**Programming Skills:**
- Breaking problems into smaller pieces
- Organizing code with functions
- Managing data with structs and objects
- Understanding scope and variable lifetime
- Reading and fixing compilation errors

#### f12.2 A Complete Example Program

Let's write a program that uses many of these concepts together:

```
#import "standard.fx";

// Enum for game states
enum GameState
{
    MENU,
    PLAYING,
    GAME_OVER
};

// Struct for player data
struct Player
{
    char[50] name;
    int score;
    int lives;
};

// Initialize a player
def createPlayer(char[] playerName) -> Player
{
    Player p;
    
    // Copy name
    for (int i = 0; i < 50; i++)
    {
        p.name[i] = playerName[i];
        if (playerName[i] == 0)
        {
            break;
        };
    };
    
    p.score = 0;
    p.lives = 3;
    
    return p;
};

// Print player info
def showPlayer(Player p) -> void
{
    print("Player: \0");
    print(p.name);
    print("\nScore: \0");
    print(p.score);
    print("\nLives: \0");
    print(p.lives);
    print();
    return;
};

// Add points to player
def addScore(Player* p, int points) -> void
{
    p.score = p.score + points;
    return;
};

// Remove a life
def loseLife(Player* p) -> bool
{
    if (p.lives > 0)
    {
        p.lives--;
        return true;  // Still alive
    };
    return false;  // Game over
};

def main() -> int
{
    GameState state = GameState.MENU;
    
    print("=== Simple Game Demo ===\n\n\0");
    
    // Create player
    char[] playerName = "Hero\0";
    Player player = createPlayer(playerName);
    
    print("Starting game...\n\0");
    state = GameState.PLAYING;
    
    showPlayer(player);
    print(); // Empty prints newline
    
    // Game loop simulation
    for (int turn = 1; turn <= 5; turn++)
    {
        print("--- Turn \0");
        print(turn);
        print(" ---\n\0");
        
        // Add some points
        addScore(@player, turn * 10);
        print("Gained \0");
        print(turn * 10);
        print(" points!\n\0");
        
        // Random life loss
        if (turn % 2 == 0)
        {
            print("Hit by enemy!\n\0");
            bool alive = loseLife(@player);
            
            if (!alive)
            {
                print("\n*** GAME OVER ***\n\0");
                state = GameState.GAME_OVER;
                break;
            };
        };
        
        showPlayer(player);
        print("\n\0");
    };
    
    // Final results
    if (state == GameState.PLAYING)
    {
        print("*** YOU WIN! ***\n\0");
    };
    
    print("\nFinal \0");
    showPlayer(player);
    
    return 0;
};
```

This program demonstrates:
- Enums for game states
- Structs for organizing player data
- Functions for different actions
- Pointers to modify data in-place
- Arrays (strings) for player names
- Loops and conditionals for game logic
- Boolean returns for game state

#### f12.3 Reading Compiler Errors

When something goes wrong, the compiler tells you. Learning to read these messages is crucial:

**Common Error Types:**

1. **Syntax Errors** - You wrote something the compiler doesn't understand
```
Expected ';' after statement
Expected ')' after expression
```

2. **Type Errors** - You tried to use the wrong type
```
Cannot assign float to int variable
Type mismatch in function call
```

3. **Name Errors** - You used a name that doesn't exist
```
'myVar' was not declared in this scope
Unknown function 'foo'
```

**How to Fix Errors:**
1. Read the error message carefully
2. Look at the line number it mentions
3. Check the lines just before and after too
4. Fix one error at a time (earlier errors can cause later ones)
5. Recompile and see if it helped

#### f12.4 Debugging Tips

When your program compiles but doesn't work right:

1. **Use print statements** to see what's happening:
```
def myFunction(int x) -> int
{
    print("myFunction called with x = \0");
    print(x);
    print("\n\0");
    
    int result = x * 2;
    
    print("Returning: \0");
    print(result);
    print("\n\0");
    
    return result;
};
```

2. **Check your assumptions** - print variable values:
```
print("Before loop: i = \0");
print(i);
print("\n\0");

for (i = 0; i < 10; i++)
{
    // ...
};

print("After loop: i = \0");
print(i);
print("\n\0");
```

3. **Simplify** - comment out code until it works, then add back piece by piece

4. **Test small pieces** - write functions that do one thing and test them separately

#### f12.5 Good Programming Practices

As you continue learning:

**1. Use meaningful names:**
```
// Bad
int x = 5;
def f(int a) -> int { return a * 2; };

// Good
int playerSpeed = 5;
def doubleValue(int value) -> int { return value * 2; };
```

**2. Write comments:**
```
// Calculate average of array
def average(int[] numbers, int count) -> float
{
    int sum = 0;
    
    // Add up all numbers
    for (int i = 0; i < count; i++)
    {
        sum = sum + numbers[i];
    };
    
    // Divide by count to get average
    return (float)sum / (float)count;
};
```

**3. Keep functions focused:**
```
// Each function should do ONE thing well
def readInput() -> int { /// ... /// };
def validateInput(int value) -> bool { /// ... /// };
def processInput(int value) -> void { /// ... /// };

// Not one giant function that does everything
```

#### f12.6 Next Steps

You now have a solid foundation in programming! Here's what to explore next:

**Practice Projects:**
1. Simple calculator with multiple operations
2. Text-based adventure game
3. Temperature converter
4. Todo list manager
5. Number guessing game

**Advanced Topics** (in the Adept document):
- The `data` type system for bit-level control
- Templates for generic code
- Namespaces for organization
- Advanced memory management
- Working with files
- Network programming basics
- Hardware interfacing

**Keep Learning:**
- Read other people's code
- Try to solve problems in multiple ways
- Don't be afraid to experiment
- Break things and fix them - that's how you learn
- Join the Flux community and ask questions

#### f12.7 Final Thoughts

Programming is a skill that improves with practice. The concepts you've learned here - variables, functions, structs, objects - are universal. They appear in almost every programming language, just with different syntax.

You're now ready to:
- Write complete programs
- Organize code into reusable pieces
- Manage data with structs and objects
- Solve problems by breaking them down
- Read and understand error messages
- Debug when things go wrong

Keep coding, keep learning, and most importantly - have fun building things!

The journey from beginner to adept programmer is all about practice. Write code every day, even if it's just a small function or a simple program. Every line of code teaches you something.

Welcome to the world of programming. The only limit is your imagination.

---

**Ready for more?** Check out the Flux Adept documentation to dive deeper into advanced features, optimization, and real-world systems programming.