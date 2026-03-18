#!/bin/sh
set -e

echo "  Setting up ELA desktop application..."

if command -v update-desktop-database >/dev/null 2>&1; then
  echo "  Registering application shortcuts..."
  update-desktop-database -q /usr/share/applications || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  echo "  Refreshing application icons..."
  gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true
fi

echo "  ELA desktop installed successfully."
echo "  Launch with: ela  or search 'ELA' in your application menu."
