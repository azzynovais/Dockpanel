#!/bin/bash
set -e

APP_NAME="Dockpanel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "Building ${APP_NAME} AppImage (simple method)..."

# Clean and create build directory
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

# Create AppDir
APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"
mkdir -p "${APPDIR}/"{usr/bin,usr/share/applications,usr/share/icons/hicolor/256x256/apps}

# Copy Python script
echo "Copying application..."
cp "${SCRIPT_DIR}/dockpanel.py" "${APPDIR}/usr/bin/dockpanel"
chmod +x "${APPDIR}/usr/bin/dockpanel"

# Create desktop file
echo "Creating desktop file..."
cat > "${APPDIR}/usr/share/applications/${APP_NAME,,}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Universal System Management Tool
Exec=dockpanel
Icon=${APP_NAME,,}
Categories=System;Settings;
Terminal=false
EOF

# Create simple icon
echo "Creating icon..."
cat > "${APPDIR}/icon.svg" << 'EOSVG'
<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" rx="32" fill="#4a90e2"/>
    <rect x="32" y="64" width="192" height="128" rx="8" fill="white" opacity="0.9"/>
    <rect x="48" y="80" width="160" height="8" rx="4" fill="#4a90e2"/>
    <rect x="48" y="96" width="120" height="8" rx="4" fill="#4a90e2"/>
    <rect x="48" y="112" width="140" height="8" rx="4" fill="#4a90e2"/>
    <rect x="48" y="128" width="100" height="8" rx="4" fill="#4a90e2"/>
    <rect x="48" y="144" width="130" height="8" rx="4" fill="#4a90e2"/>
</svg>
EOSVG

cp "${APPDIR}/icon.svg" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME,,}.png"

# Create AppRun
echo "Creating AppRun..."
cat > "${APPDIR}/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/dockpanel" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

# Download appimagetool
echo "Downloading appimagetool..."
cd "${BUILD_DIR}"
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    wget -c "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x appimagetool-x86_64.AppImage
fi

# Create AppImage
echo "Creating AppImage..."
ARCH=x86_64 ./appimagetool-x86_64.AppImage "${APPDIR}"

if [ -f "${APP_NAME,,}-x86_64.AppImage" ]; then
    echo "✓ AppImage created: ${BUILD_DIR}/${APP_NAME,,}-x86_64.AppImage"
else
    echo "✗ Failed to create AppImage"
    exit 1
fi
