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
