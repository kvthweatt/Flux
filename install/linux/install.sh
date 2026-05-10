
set -e

clear

echo
echo "========================================================="
echo "              Flux Installer"
echo "========================================================="
echo

echo "[*] Detecting Linux distribution..."

if command -v apt >/dev/null 2>&1; then
    PKG_MANAGER="apt"

elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"

elif command -v pacman >/dev/null 2>&1; then
    PKG_MANAGER="pacman"

elif command -v zypper >/dev/null 2>&1; then
    PKG_MANAGER="zypper"

elif command -v emerge >/dev/null 2>&1; then
    PKG_MANAGER="portage"

elif command -v apk >/dev/null 2>&1; then
    PKG_MANAGER="apk"

elif command -v xbps-install >/dev/null 2>&1; then
    PKG_MANAGER="xbps"

else
    echo "[!] Unsupported Linux distribution."
    exit 1
fi

echo "[✓] Detected package manager: $PKG_MANAGER"
echo

echo "[*] Installing system dependencies..."
echo

case $PKG_MANAGER in

    apt)
        sudo apt update

        sudo apt install -y \
            python3 \
            python3-pip \
            python3-venv \
            llvm \
            clang \
            git \
            wget \
            curl \
            gpg
        ;;

    dnf)
        sudo dnf install -y \
            python3 \
            python3-pip \
            llvm \
            clang \
            git \
            wget \
            curl \
            gnupg2
        ;;

    pacman)
        sudo pacman -Sy --noconfirm \
            python \
            python-pip \
            llvm \
            clang \
            git \
            wget \
            curl \
            gnupg
        ;;

    zypper)
        sudo zypper install -y \
            python3 \
            python3-pip \
            llvm \
            clang \
            git \
            wget \
            curl \
            gpg2
        ;;

    portage)
        sudo emerge \
            dev-lang/python \
            llvm-core/llvm \
            sys-devel/clang \
            dev-vcs/git \
            net-misc/wget \
            net-misc/curl
        ;;

    apk)
        sudo apk add \
            python3 \
            py3-pip \
            llvm \
            clang \
            git \
            wget \
            curl \
            gnupg
        ;;

    xbps)
        sudo xbps-install -Sy \
            python3 \
            python3-pip \
            llvm \
            clang \
            git \
            wget \
            curl \
            gnupg
        ;;

esac

echo
echo "[✓] System dependencies installed."
echo


echo "[*] Installing Python dependencies..."
echo

python3 -m pip install --upgrade pip || true

python3 -m pip install \
    llvmlite==0.41.0 \
    dataclasses \
    --break-system-packages || \
python3 -m pip install \
    --user \
    llvmlite==0.41.0 \
    dataclasses

echo
echo "[✓] Python dependencies installed."
echo

echo "[*] Installing Flux..."
echo

if [ -d "$HOME/FluxLang" ]; then
    echo "[*] Existing FluxLang installation detected."
    echo "[*] Pulling latest changes..."

    cd "$HOME/FluxLang"
    git pull

else
    cd "$HOME"

    git clone https://github.com/kvthweatt/FluxLang.git

    cd FluxLang
fi

echo
echo "[✓] Flux installed."
echo


echo "[*] Configuring environment..."
echo

FLUX_PATH="$HOME/FluxLang"

# Detect shell config
SHELL_CONFIG=""

if [ -n "$BASH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.bashrc"

elif [ -n "$ZSH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.zshrc"

else
    SHELL_CONFIG="$HOME/.profile"
fi

# Add environment variable
if ! grep -q "FLUXC_SRCDIR" "$SHELL_CONFIG"; then

    echo "" >> "$SHELL_CONFIG"
    echo "# FluxLang" >> "$SHELL_CONFIG"
    echo "export FLUXC_SRCDIR=\"$FLUX_PATH\"" >> "$SHELL_CONFIG"

fi

# Add alias
if ! grep -q "alias fluxc=" "$SHELL_CONFIG"; then

    echo "alias fluxc='python3 $FLUX_PATH/fxc.py'" >> "$SHELL_CONFIG"

fi

export FLUXC_SRCDIR="$FLUX_PATH"

echo "[✓] Environment configured."
echo


echo "[*] Running verification checks..."
echo

echo "---------------------------------------------------------"
echo "Python:"
python3 --version

echo
echo "Clang:"
clang --version | head -n 1

echo
echo "LLVM:"
llvm-config --version

echo
echo "Git:"
git --version

echo
echo "llvmlite:"
python3 -c "import llvmlite; print('llvmlite OK')"

echo "---------------------------------------------------------"
echo

 
echo "[*] Testing Flux compilation..."
echo

cd "$FLUX_PATH"

python3 fxc.py tests/test.fx --log-level 3 || {
    echo
    echo "[!] Flux test compilation failed."
    exit 1
}

echo
echo "[✓] Flux test compilation successful."
echo

read -p "Install Sublime Text? (y/N): " INSTALL_SUBLIME

if [[ "$INSTALL_SUBLIME" =~ ^[Yy]$ ]]; then

    echo
    echo "[*] Installing Sublime Text..."
    echo

    case $PKG_MANAGER in

        apt)
            wget -qO - https://download.sublimetext.com/sublimehq-pub.gpg | \
                gpg --dearmor | \
                sudo tee /etc/apt/trusted.gpg.d/sublimehq-archive.gpg >/dev/null

            echo "deb https://download.sublimetext.com/ apt/stable/" | \
                sudo tee /etc/apt/sources.list.d/sublime-text.list

            sudo apt update
            sudo apt install -y sublime-text
            ;;

        dnf)
            sudo rpm -v --import \
                https://download.sublimetext.com/sublimehq-rpm-pub.gpg

            sudo dnf config-manager --add-repo \
                https://download.sublimetext.com/rpm/stable/x86_64/sublime-text.repo

            sudo dnf install -y sublime-text
            ;;

        pacman)
            echo
            echo "[!] Sublime Text installation on Arch requires an AUR helper."
            echo "[!] Install manually with:"
            echo "    yay -S sublime-text-4"
            ;;

        *)
            echo
            echo "[!] Automatic Sublime installation not supported for this distro."
            ;;

    esac

    echo
    echo "[✓] Sublime Text installation completed."
    echo

fi


echo "========================================================="
echo "           Flux Installed Successfully"
echo "========================================================="
echo

echo "Flux Directory:"
echo "  $FLUX_PATH"
echo

echo "Environment File:"
echo "  $SHELL_CONFIG"
echo

echo "Next Steps:"
echo

echo "  1. Reload your shell:"
echo "     source $SHELL_CONFIG"
echo

echo "  2. Compile a Flux program:"
echo "     fluxc examples/hello.fx"
echo

echo "  3. Run the executable:"
echo "     ./hello"
echo

echo "Happy Flux development!"
echo