#!/bin/sh
set -eu
# Produit une application locale ; aucune donnée personnelle n'est copiée.
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir=${1:?Indiquer le dossier de sortie}
app="$output_dir/Polytech Sync privé.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/engine/data"
/usr/bin/swiftc -swift-version 5 -target arm64-apple-macosx14.0 -framework AppKit -framework EventKit -framework Security \
  "$project_dir/macos/PrivateSync.swift" -o "$app/Contents/MacOS/PolytechPrivateSync"
cp "$project_dir/polyflex_sync.py" "$project_dir/generate_ics.py" "$app/Contents/Resources/engine/"
cp "$project_dir/data/alternance-info-2026-2027.json" "$app/Contents/Resources/engine/data/"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Polytech Sync privé</string>
<key>CFBundleDisplayName</key><string>Polytech Sync privé</string>
<key>CFBundleIdentifier</key><string>fr.polytech.calendar.private</string>
<key>CFBundleExecutable</key><string>PolytechPrivateSync</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSCalendarsFullAccessUsageDescription</key><string>Polytech Sync privé met à jour uniquement son calendrier iCloud dédié. Il utilise les identifiants des événements pour éviter les doublons et retirer les cours annulés. Ton mot de passe Polyflex reste dans le trousseau du Mac.</string>
</dict></plist>
PLIST
/usr/bin/codesign --force --deep --sign - --identifier fr.polytech.calendar.private "$app"
/usr/bin/codesign --verify --deep --strict "$app"
printf '%s\n' "$app"
