#!/bin/bash
APP_NAME="Dockpanel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "Creating portable executable (no AppImage)..."

# Clean
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

# Create a self-contained executable
cat > "${BUILD_DIR}/${APP_NAME,,}" << 'EOF'
#!/bin/bash
# Dockpanel Portable Application

# Get the directory where this script is located
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if dockpanel.py exists
if [ ! -f "$HERE/dockpanel.py" ]; then
    # Extract the Python script from this file
    sed -n '1,/^# PYTHON_SCRIPT_BELOW$/p' "$0" > /dev/null
    sed -n '/^# PYTHON_SCRIPT_BELOW$/,$p' "$0" | tail -n +2 > "$HERE/dockpanel.py"
    chmod +x "$HERE/dockpanel.py"
fi

# Set environment variables
export PATH="$HERE:$PATH"
export LD_LIBRARY_PATH="$HERE/lib:$LD_LIBRARY_PATH"
export XDG_DATA_DIRS="$HERE/share:$XDG_DATA_DIRS"
export GI_TYPELIB_PATH="$HERE/lib/girepository-1.0:$GI_TYPELIB_PATH"

# Run the application
if command -v python3 &> /dev/null; then
    exec python3 "$HERE/dockpanel.py" "$@"
elif command -v python &> /dev/null; then
    exec python "$HERE/dockpanel.py" "$@"
else
    echo "Error: Python not found. Please install Python 3."
    exit 1
fi

# PYTHON_SCRIPT_BELOW
EOF

# Append the Python script
cat "${SCRIPT_DIR}/dockpanel.py" >> "${BUILD_DIR}/${APP_NAME,,}"

# Make it executable
chmod +x "${BUILD_DIR}/${APP_NAME,,}"

# Create an AppImage-like wrapper
cat > "${BUILD_DIR}/make-appimage.sh" << 'EOF'
#!/bin/bash
APP_NAME="Dockpanel"
BUILD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Creating AppImage wrapper..."

# Create AppDir
APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"
mkdir -p "${APPDIR}/usr/bin"

# Copy the portable executable
cp "${BUILD_DIR}/${APP_NAME,,}" "${APPDIR}/usr/bin/"

# Create AppRun
cat > "${APPDIR}/AppRun" << 'APPRUN_EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/dockpanel" "$@"
APPRUN_EOF
chmod +x "${APPDIR}/AppRun"

# Create desktop file
mkdir -p "${APPDIR}/usr/share/applications"
cat > "${APPDIR}/usr/share/applications/dockpanel.desktop" << 'DESKTOP_EOF'
[Desktop Entry]
Type=Application
Name=Dockpanel
Exec=dockpanel
Terminal=false
DESKTOP_EOF

# Download runtime
cd "${BUILD_DIR}"
if [ ! -f "runtime-x86_64" ]; then
    wget -q -O runtime-x86_64 \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/runtime-x86_64"
fi

# Create AppImage
OUTPUT="Dockpanel-x86_64.AppImage"
cat runtime-x86_64 > "$OUTPUT"
mksquashfs "${APPDIR}" - -noappend -no-recovery >> "$OUTPUT" 2>/dev/null
chmod +x "$OUTPUT"

echo "AppImage created: $OUTPUT"
EOF
chmod +x "${BUILD_DIR}/make-appimage.sh"

echo "✓ Portable executable created: ${BUILD_DIR}/${APP_NAME,,}"
echo "✓ Run with: ${BUILD_DIR}/${APP_NAME,,}"
echo "✓ To create AppImage: ${BUILD_DIR}/make-appimage.sh"
