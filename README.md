# SM64 × Minecraft Crossmod

## Ziel

Das ist **kein Minecraft-Block-Nachbau** von Super Mario 64.

Super Mario 64 bleibt das echte Spiel und die echte 3D-Welt. Minecraft läuft als Hintergrund-Engine für Steve, Skin, Hotbar, Inventar und Minecraft-Items.

Die Architektur folgt konkret:

```
git clone https://github.com/rehan-remade/universal-modder
```

Referenz:

`examples/minecraft-gta5-passthrough`

Der frühere Block-Prototyp liegt auf `legacy-block-prototype`. Der vorherige sichtbare Minecraft/SM64-Overlay-Modus liegt auf `legacy-visible-minecraft-overlay`.

## Ein sichtbares Spiel

Im aktuellen `main` ist **SM64 das einzige sichtbare und fokussierte Spielfenster**.

Ablauf:

1. `start-test.bat` startet SM64 und Minecraft.
2. Minecraft ist kurz sichtbar, damit eine Welt geöffnet werden kann.
3. Sobald Spieler + Host verbunden sind, verschiebt die Mod das Minecraft-Fenster aus dem sichtbaren Desktop.
4. Minecraft rendert dort weiter off-screen.
5. SM64 liest Minecraft-Color/Depth/HUD aus Shared Memory und setzt alles in sein eigenes D3D11-Bild.
6. Tastatur und Maus gehören danach direkt dem sichtbaren SM64-Fenster.

Minecraft wird absichtlich nicht minimiert, sondern off-screen weitergerendert, damit die GPU-Ausgabe nicht durch einen minimierten/inaktiven Swapchain-Pfad ausgebremst wird. `pauseOnLostFocus` wird deaktiviert.

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

Mario bleibt intern als SM64-Spielkörper erhalten, wird bei aktiver Verbindung aber unsichtbar. Seine echte SM64-Physik/Interaktion bleibt erhalten; Steve wird an dieser autoritativen Pose gerendert.

### Minecraft 1.21.1 + Fabric

Minecraft liefert:

- Steve/Alex oder deinen Skin
- sichtbares Minecraft-Spielermodell
- gehaltenes Minecraft-Item
- Hotbar
- Inventar
- Minecraft-HUD
- Item-/Waffen-Metadaten
- Crossmod-Effekte für Nahkampf, Bogen/Crossbow, Trident und TNT

Minecraft ist dabei ein echter Client, aber kein zweites sichtbares Spiel.

## Eingabe im SM64-Fenster

Die Eingabe wird unter Windows direkt vom sichtbaren SM64-Prozess gelesen:

- WASD = Analogstick
- Leertaste = A
- Linksklick = B + Minecraft-Waffenangriff
- Rechtsklick = B / Minecraft-Item benutzen
- Shift = Z
- P = Start/Pause
- I/J/K/L = C-Up/C-Left/C-Down/C-Right
- O = R
- U = L
- 1..9 = Minecraft-Hotbar-Slot
- E = echtes Minecraft-Inventar öffnen/schließen

Wenn ein Minecraft-GUI offen ist, pausiert die Bridge SM64-Bewegung/Combat und leitet Cursorposition sowie Mausklicks aus dem SM64-Fenster an das versteckte Minecraft-GUI weiter. Das GUI wird über den normalen Minecraft-HUD-Layer wieder im SM64-Fenster angezeigt.

## Universal-Modder-Passthrough

### WebSocket

`127.0.0.1:25599`

- Minecraft ist der WebSocket-Server.
- SM64 ist der Host-Client.
- SM64 sendet Kamera, Spielerpose, Level, Kurs, Akt, Sterne, Coins, Leben, Health, Save-Flags und Missionstimer.
- Minecraft sendet den ausgewählten Slot, Itemtyp und Item-/GUI-Zustand.
- SM64 sendet Hotbar-/Inventar-/Pointer-Befehle an den versteckten Minecraft-Client.

Die Windows-WebSocket-Dateien `ws.h` und `ws.cpp` werden beim Setup direkt aus dem geklonten Universal-Modder-Repo übernommen.

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

### Asynchroner Minecraft-Readback

Minecraft 1.21.1 nutzt OpenGL, SM64 D3D11.

Der Frame-Export benutzt deshalb einen Ring aus OpenGL Pixel Buffer Objects und GPU-Fences. Color, Depth und HUD werden asynchron in PBOs geschrieben; nur bereits fertige GPU-Frames werden in `Local\MCPassthroughFrame` kopiert.

Wenn alle Readback-Slots beschäftigt sind, wird lieber ein Minecraft-Frame übersprungen als der Minecraft-Renderthread anzuhalten. Die Kamera-Reprojection gleicht das Alter des letzten fertigen Frames aus.

### Depth-Compositor

Der gepatchte SM64-D3D11-Renderer liest den neuesten fertigen Minecraft-Slot und mischt ihn direkt in das native SM64-Bild.

Dadurch soll:

- SM64 die echte Hintergrundwelt bleiben;
- Steve in der SM64-Welt stehen;
- eine SM64-Wand Steve wirklich verdecken können;
- Minecraft-Hotbar/Inventar/HUD darüber sichtbar bleiben;
- die normale Minecraft-Landschaft nicht das SM64-Bild ersetzen.

Zusätzlich ist die 6-DoF-Depth-Reprojection aus dem Universal-Modder-Prinzip portiert: ein Minecraft-Frame wird anhand seiner gespeicherten Kamera auf die aktuelle SM64-Kamera zurückgerechnet.

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
5. übernimmt die Universal-Modder-WebSocket-Quellen;
6. patcht den nativen SM64-D3D11-Renderer;
7. baut Fabric;
8. baut den SM64-Host.

## Test starten

```bat
start-test.bat
```

Dann einmal in Minecraft eine Welt öffnen. Nach erfolgreicher Verbindung verschwindet das Minecraft-Fenster vom sichtbaren Desktop und SM64 übernimmt Fokus/Eingabe.

## Status

Implementiert und in CI geprüft:

- Original-SM64 Whole-Game-Progression
- 120-Star-/Mission-Schutz
- Universal-Modder-WebSocket
- `MCPT` Named Shared Memory
- D3D11 Depth-Compositor
- Kamera-Pose-Reprojection
- transparenter Minecraft-HUD-Layer
- sichtbarer SM64-Host + off-screen Minecraft-Guest
- Host-seitige WASD/Maus/Hotbar-/Inventar-Eingabe
- asynchroner OpenGL-PBO-Readback

Ein CI-Build ersetzt keinen echten Lauf auf der Zielmaschine. Kameraausrichtung, Depth-Thresholds, GPU-Treiberverhalten und konkrete Minecraft-Item-Interaktionen müssen zusätzlich im laufenden SM64 + Minecraft geprüft werden.
