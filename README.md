# SM64 × Minecraft Crossmod

## Ziel

Das ist **kein Minecraft-Block-Nachbau** von Super Mario 64.

Super Mario 64 bleibt das echte Spiel und die echte 3D-Welt. Minecraft liefert den sichtbaren Spieler, Skin, Hotbar, Inventar und Minecraft-Items.

Die Architektur folgt jetzt konkret dem Passthrough-Beispiel aus:

```
git clone https://github.com/rehan-remade/universal-modder
```

Referenz:

`examples/minecraft-gta5-passthrough`

Der frühere Block-Prototyp liegt auf `legacy-block-prototype`. Der alte eigene Position/UDP-Passthrough ist ebenfalls nicht mehr die Architektur von `main`.

## Wer macht was?

### Super Mario 64

Der originale SM64-PC-Port ist für das eigentliche Spiel zuständig:

- Peach's Castle
- alle 15 Hauptkurse
- Secret Stages
- alle 120 Sterne
- Missionen/Akte
- Red Coins und 100-Coin-Stars
- Bowser-Stages, Schlüssel und Grand Star
- Türen, Gemälde und Warps
- Kanonen, Caps und Cap-Switches
- Gegner und Bosse
- Wasser, Treibsand, Rutschen und bewegliche Plattformen
- originale Physik und Kollision
- Tod/Respawn
- Save-Daten und Progression
- Musik und Sounds

Mario bleibt intern als SM64-Spielkörper erhalten, wird bei aktiver Verbindung aber unsichtbar. Minecraft steuert den echten SM64-Controller; die Position wird nicht mehr künstlich aus Minecraft in Mario hineingeschrieben.

### Minecraft 1.21.1 + Fabric

Minecraft liefert:

- Steve/Alex oder deinen Skin
- sichtbares Minecraft-Spielermodell
- gehaltenes Minecraft-Item
- Hotbar
- Inventar
- Minecraft-HUD
- Waffen-/Item-Events
- Crossmod-Effekte für Nahkampf, Bogen/Crossbow, Trident und TNT

## Universal-Modder-Passthrough

Die beiden Prozesse benutzen dieselbe Grundaufteilung wie das Minecraft × GTA-V-Beispiel.

### WebSocket

`127.0.0.1:25599`

- Minecraft ist der WebSocket-Server.
- SM64 verbindet sich als Host-Client.
- SM64 sendet Kamera, Spielerpose, Level, Kurs, Akt, Sterne, Coins, Leben, Health, Save-Flags und Missionstimer.
- Minecraft sendet Eingabe, ausgewähltes Item und Angriffs-/Benutzen-Events.

Die Windows-WebSocket-Dateien `ws.h` und `ws.cpp` werden beim Setup **direkt aus dem geklonten Universal-Modder-Repo** übernommen.

### Shared Memory

Named mapping:

`Local\MCPassthroughFrame`

Format:

- Magic `MCPT`
- 3 rotierende Slots
- odd/even sequence guard
- Minecraft world RGBA8
- Minecraft depth float32
- separates transparentes HUD/Overlay RGBA8
- Kamera/FOV/near/far pro Frame

### Depth-Compositor

Der gepatchte SM64-D3D11-Renderer liest den neuesten fertigen Minecraft-Slot und mischt ihn direkt in das native SM64-Bild.

Dadurch soll:

- SM64 die echte Hintergrundwelt bleiben;
- Steve in der SM64-Welt stehen;
- eine SM64-Wand Steve wirklich verdecken können;
- Minecraft-Hotbar/HUD darüber sichtbar bleiben;
- die normale Minecraft-Landschaft nicht das SM64-Bild ersetzen.

Zusätzlich ist die 6-DoF-Depth-Reprojection aus dem Universal-Modder-Prinzip portiert: ein Minecraft-Frame wird anhand seiner gespeicherten Kamera auf die neuere SM64-Kamera zurückgerechnet, um sichtbares Hinterherziehen beim Drehen der Kamera zu reduzieren.

## Whole-Game-Schutz

`tools/verify_whole_game.py` bricht den Build ab, falls der Crossmod versehentlich originale SM64-Level-/Progressionsdateien überschreibt.

Geprüft werden unter anderem:

- 15 Hauptkurse
- 10 Bonus-/End-Kurseinträge
- 33 originale Level-Verzeichnisse
- Level-Scripts
- Save-System
- Star-Select
- Progressionscode

So kommen die Missionen und 120 Sterne aus dem echten SM64 statt aus einzeln nachgebauten Minecraft-Missionen.

## Anforderungen

- Windows
- JDK 21
- Git
- Python 3
- MSYS2 MinGW64
- `git`, `make`, `python3`
- `mingw-w64-x86_64-gcc`
- SDL2/GLEW Development-Pakete

Eigene saubere Super Mario 64 USA-ROM:

`rom\baserom.us.z64`

Erwartete SHA-1:

`9bef1128717f958171a4afac3ed78ee2bb4e86ce`

ROM, SM64-Checkout, Universal-Modder-Checkout und extrahierte Retail-Assets werden nicht committed.

## Bauen

Nach einem `git pull`:

```bat
setup-windows.bat
```

Das Setup:

1. prüft Java/Python/Git;
2. prüft die eigene ROM;
3. klont/bereitet `sm64-port` vor;
4. klont exakt `https://github.com/rehan-remade/universal-modder`;
5. übernimmt die Passthrough-WebSocket-Quellen;
6. patcht den nativen SM64-Renderer;
7. baut Fabric;
8. baut den SM64-Host.

## Test starten

```bat
start-test.bat
```

Dann in Minecraft eine Welt öffnen.

Der Test startet Minecraft zunächst mit 1280×720. Sobald WebSocket + Shared Memory aktiv sind, wird das SM64-Bild über die Minecraft-Spielfläche gelegt. Minecraft bleibt für Tastatur, Maus, Hotbar und Inventar zuständig.

### SM64-Steuerung

- WASD = Analogstick
- Leertaste = A
- Linksklick/Rechtsklick = B / Angriff / Benutzen
- Shift = Z
- P = Start/Pause
- I/J/K/L = C-Up/C-Left/C-Down/C-Right
- O = R
- U = L

## Status

Der Codepfad für Whole-Game-SM64, Universal-Modder-WebSocket, MCPT-Shared-Memory, D3D11-Depth-Compositing und Kamera-Reprojection ist implementiert und wird in CI kompiliert.

Das ersetzt keinen echten Lauf auf der Zielmaschine: Kameraausrichtung, Depth-Thresholds, Fensterpositionierung und Item-Interaktionen müssen zusätzlich im laufenden SM64 + Minecraft geprüft werden.
