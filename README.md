# SM64 × Minecraft Crossmod

## Ziel

Das Projekt ist **kein Minecraft-Block-Nachbau von Super Mario 64**.

Die sichtbare Welt bleibt der echte Super-Mario-64-PC-Port mit originalen
Leveln, Texturen, Gegnern, Musik, Missionen, Warps und allen 120 Sternen.
Minecraft 1.21.1 läuft gleichzeitig als echter Fabric-Client + integrierter
Server im Hintergrund und liefert das Minecraft-Spielsystem in diese Welt.

Referenzarchitektur:

```
git clone https://github.com/rehan-remade/universal-modder
```

Verwendetes Referenzbeispiel:

`examples/minecraft-gta5-passthrough`

## Ein sichtbares Spiel

`sm64.us.exe` ist das einzige sichtbare und fokussierte Spielfenster.

Minecraft wird nach dem Weltbeitritt off-screen verschoben und läuft weiter als
Hintergrund-Engine. Es wird nicht minimiert, damit OpenGL-Rendering und der
Shared-Memory-Export weiterlaufen.

SM64 rendert das Endbild mit Direct3D 11:

```
echtes SM64 Color + Depth
          +
Minecraft Color + Depth
          +
Minecraft Hand/HUD/GUI
          =
ein sichtbares SM64-Fenster
```

## Originales SM64 bleibt vollständig

SM64 bleibt Autorität für:

- Peach's Castle
- alle Hauptkurse und Secret Stages
- 120 Sterne
- Missionen/Akte
- Red Coins und 100-Coin-Stars
- Bowser-Stages, Schlüssel und Grand Star
- Türen, Gemälde und Warps
- Kanonen und Caps
- originale Gegner/Bosse
- Wasser, Treibsand, Rutschen, Moving Platforms
- originale SM64-Levelgeometrie und Missions-/Objektlogik
- Tod/Respawn/Leben
- Save-Daten und Progression
- Musik und Sounds

Mario bleibt intern als unsichtbarer originaler SM64-Spielkörper erhalten.
Steve ist die sichtbare Minecraft-Darstellung desselben Spielers.

## Echtes Minecraft-System

Minecraft läuft nicht nur als HUD.

Der aktuelle Hybrid benutzt echte Minecraft-Systeme für:

- Steve/Alex/custom Skin
- First-Person-Hand
- gehaltene Items
- Third Person hinten und vorne
- Hotbar
- echtes Inventar
- normale Minecraft-Screens und Texteingabe
- Chat
- echte ItemStacks
- BlockStates
- BlockEntities
- Blockplatzierung
- Mining
- Tools/Waffen
- Offhand
- Droppen
- Essen/Hunger
- Minecraft-Schaden/Heilung
- Minecraft-Mobs und Projektile im Overlay-Level
- normale Client-/Integrated-Server-Logik

Die Minecraft-Welt dafür ist die leere Dimension:

`sm64cross:sm64_overlay`

Sie enthält keine normale Overworld-Landschaft. Der originale SM64-Level bleibt
die sichtbare Umgebung.

## First Person / Third Person

Standard ist jetzt **First Person**.

`F5` schaltet wie Minecraft:

1. First Person
2. Third Person hinten
3. Third Person vorne
4. zurück zu First Person

In First Person wird der echte Minecraft-`ItemInHandRenderer` verwendet.
Dadurch kommen Steve-Hand und das ausgewählte Item direkt aus Minecraft.

In Third Person wird der vollständige lokale Minecraft-Spieler mit Skin und
gehaltenem Item gerendert.

Die Third-Person-Kamera wird im SM64-Host gegen echte SM64-Wände, Böden und
Decken geprüft, damit sie nicht einfach durch Levelgeometrie clippt.

SM64-Cutscenes werden nicht ersetzt. Star-Sequenzen, Türen, Bowser-Szenen und
andere originale Cutscenes behalten ihre native Kamera.

## Steuerung im sichtbaren SM64-Fenster

- Maus = echte Minecraft-Maussteuerung inklusive Minecraft-Sensitivity/Invert-Y
- WASD = echte Minecraft-Bewegung
- Leertaste = echter Minecraft-Sprung
- Linksklick = Minecraft Angriff / Mining
- Rechtsklick = Minecraft Benutzen / Block platzieren
- Shift = echtes Minecraft-Schleichen
- Ctrl = echtes Minecraft-Sprinten
- 1..9 = Minecraft-Hotbar
- E = Inventar / Container schließen
- Q = Item droppen
- Ctrl+Q = Stack droppen
- F = Offhand tauschen
- F5 = Perspektive wechseln
- T = Minecraft-Chat
- Slash-Taste = Command-Chat
- Escape = aktiven Minecraft-Screen schließen
- V = direkte originale SM64-B-Aktion für Spezialinteraktionen
- P = SM64 Start/Pause
- I/J/K/L = SM64 C-Tasten
- O/U = SM64 R/L

Wenn ein Minecraft-Screen offen ist, werden Maus und Tastatur aus dem
SM64-Fenster an diesen echten Minecraft-Screen weitergereicht. Text wird unter
Windows mit `ToUnicode` erzeugt, damit die aktive Tastaturbelegung verwendet
wird.

## Echte Minecraft-Blöcke auf SM64

Beim Platzieren raycastet SM64 vom Fadenkreuz gegen seine echten
Dreiecks-Surfaces:

- Floor
- Ceiling
- Wall

Der Trefferpunkt und die Surface-Normale gehen an Minecraft.
Minecraft führt anschließend die normale `MultiPlayerGameMode.useItemOn`-
Logik mit dem echten ausgewählten Item aus.

Die platzierten Blöcke sind echte Minecraft-Blöcke im integrierten Server:
keine SM64-Imitation und keine Fake-Meshes.

Mining benutzt ebenfalls Minecrafts normale Destroy-Block-Logik.

## Zwei-Wege-Kollision

### Minecraft -> SM64

Nahe Minecraft-`VoxelShape`-CollisionBoxes werden an SM64 geschickt.

Das gilt auch für Formen wie:

- Slabs
- Treppen
- Fences
- andere nicht volle Blockformen

SM64 baut daraus native dynamische Collision-Surfaces. Der originale
SM64-Spielkörper kann dadurch auf Minecraft-Blöcken stehen und gegen sie
laufen.

### SM64 -> Minecraft

Minecraft bekommt lokal um den Spieler eine unsichtbare dynamische
`VoxelShape`-Kollisionsschicht direkt aus der echten SM64-Kollision:

- Böden werden pro Block in 2x2 Teilflächen mit ihrer tatsächlichen Höhe
  gesampelt, sodass Schrägen nicht mehr auf volle Würfel gerundet werden;
- Wände werden als dünne Kollisionsflächen auf der tatsächlichen
  SM64-Wandebene gespiegelt;
- niedrige Decken behalten ihre genaue Höhe.

Diese Proxy-Blöcke haben **kein sichtbares Modell und keine Auswahlbox**.
Minecraft berechnet darauf trotzdem seine normale Bewegung, Gravitation,
Sprint-/Sneak-/Sprungphysik sowie Entity-Kollision. Echte vom Spieler gesetzte
Minecraft-Blöcke haben immer Vorrang.

Der SM64-Level wird weiterhin **nicht optisch in Minecraft-Blöcke
umgewandelt**; nur seine Physik fließt in Minecraft ein.

## Gemeinsames Health-/Hunger-System

SM64 bleibt Autorität für Tod und Respawn, damit originale Course-/Life-Logik
erhalten bleibt.

Minecraft-Schaden wird aber zurück in Marios echtes Health-System übertragen:

- Minecraft verarbeitet zuerst DamageSource, Rüstung, Verzauberungen und Effekte
- die tatsächliche Health-Differenz wird an SM64 geschickt
- Schaden wird zu SM64-`hurtCounter`
- Heilung wird zu SM64-`healCounter`
- SM64 sendet den resultierenden Lebensstand wieder an Minecraft

Minecraft Food/Saturation wird nicht jeden Tick auf voll gesetzt.
Weil Minecraft selbst die Bewegung simuliert, entstehen Sprint-, Sprung- und
Bewegungs-Exhaustion über die normalen Vanilla-Systeme.

## Player-/Aim-Sync

Minecraft-Client und integrierter Server besitzen die laufende
Spielerposition. SM64 übernimmt diese Position nur für seinen unsichtbaren
Mario-Proxy, damit Sterne, Türen, Warps, Gegner und Missionen weiter reagieren.

Das ist wichtig für:

- Vanilla Reach Checks
- Container
- Projektile
- Entity Interaction
- Item Use
- Mobs
- Block Interaction

Körper- und Blickrichtung sind getrennt:

- Steve-Körper = Minecraft-Bewegung
- Kopf/Aim = Minecraft-Yaw/Pitch; die sichtbare SM64-Kamera folgt diesem Aim

Bögen, Tridents und andere gerichtete Minecraft-Aktionen zielen dadurch nach
der Kamera statt nur in Marios Laufrichtung.

## Universal-Modder-Transport

### WebSocket

`127.0.0.1:25599`

Für kleine Zustände und Events:

- Kamera
- Spielerpose
- SM64-Progression
- Minecraft Item/Slot
- Input
- GUI
- Block-Collision
- Health
- lokale Terrain-Proxy-Daten

Die Windows-`ws.h`/`ws.cpp` werden beim Setup direkt aus
`rehan-remade/universal-modder` übernommen.

### Shared Memory

`Local\MCPassthroughFrame`

MCPT-Ring mit drei Slots für:

- Minecraft world RGBA8
- Minecraft depth float32
- transparentes Minecraft HUD/Hand/GUI RGBA8
- Kamera/FOV/Pose pro Frame

Minecraft nutzt einen asynchronen OpenGL-PBO-Ring mit GPU-Fences. Der
Renderthread wartet nicht synchron auf jeden Readback.

## D3D11 Depth-Compositor

SM64 mischt Minecraft direkt in seinen nativen D3D11-Frame.

Dadurch können unter anderem:

- Minecraft-Blöcke in der echten SM64-Welt stehen
- Steve durch echte SM64-Geometrie verdeckt werden
- Minecraft-HUD/Hand screen-space bleiben
- Minecraft-Sky/Vanilla-Terrain aus dem finalen Bild verschwinden

Zusätzlich läuft 6-DoF Depth-Reprojection nach dem Universal-Modder-Prinzip, um
das Alter eines bereits fertig exportierten Minecraft-Frames gegen die aktuelle
SM64-Kamera auszugleichen.

## Whole-Game-Schutz

`tools/verify_whole_game.py` prüft bei jedem CI-Build, dass originale
SM64-Level-/Progressionsdateien nicht versehentlich durch den Hybrid ersetzt
werden.

Unter anderem geschützt:

- 15 Hauptkurse
- Bonus-/End-Kurse
- 33 originale Level-Verzeichnisse
- Level Scripts
- Star Select
- Save-System
- Progression

## Anforderungen

- Windows
- JDK 21
- Git
- Python 3
- MSYS2 MinGW64
- `git`, `make`, `python3`
- `mingw-w64-x86_64-gcc`
- SDL2/GLEW Development-Pakete

Eigene saubere SM64-USA-ROM:

`rom\baserom.us.z64`

SHA-1:

`9bef1128717f958171a4afac3ed78ee2bb4e86ce`

## Bauen

```bat
git pull
setup-windows.bat
```

## Starten

```bat
start-test.bat
```

Minecraft ist zuerst kurz sichtbar. Eine Welt öffnen. Sobald Host + Guest
verbunden sind, wird Minecraft off-screen verschoben und SM64 übernimmt
Fenster, Kamera und Eingabe.

## Sicherungs-Branches

- `legacy-block-prototype` – alter Minecraft-Block-Nachbau
- `legacy-visible-minecraft-overlay` – alter sichtbarer Zwei-Fenster-Modus
- `working-sm64-host-single-window` – erster funktionierender Single-Window-Stand
- `working-blocks-single-window` – funktionierender Single-Window-Stand vor
  dem großen Full-Minecraft-Gameplay-Umbau

## Aktueller technischer Stand

Automatisch geprüft werden:

- Fabric Build
- SM64-C-Bridge gegen aktuelle Upstream-Headers
- gepatchte SM64-Core-Collision
- D3D11-Compositor
- eingebetteter HLSL-Shader via `D3DCompile`
- Whole-Game-Integrität

Ein grüner CI-Build ersetzt den echten Lauf auf dem Ziel-PC nicht. Besonders
Treiberverhalten, Kamera-/Depth-Toleranzen und die große Menge möglicher
Minecraft-Items/BlockEntities müssen zusätzlich im laufenden Hybrid getestet
werden.

Der Ansatz versucht nicht, die komplette Java Edition in die C-Dateien des
SM64-Ports zu kopieren. Stattdessen laufen die echten Minecraft-Client- und
Server-Systeme parallel und werden so tief in den sichtbaren SM64-Host
eingebunden, dass der Benutzer nur ein gemeinsames Spiel sieht.
