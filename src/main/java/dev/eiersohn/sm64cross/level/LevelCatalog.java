package dev.eiersohn.sm64cross.level;

import java.util.List;
import java.util.Locale;
import java.util.Optional;

import static dev.eiersohn.sm64cross.level.Sm64Level.LevelKind.*;

public final class LevelCatalog {
    public static final List<Sm64Level> LEVELS = List.of(
            new Sm64Level("peachs_castle", "Peach's Castle", 0, 0, CASTLE),
            new Sm64Level("bob_omb_battlefield", "Bob-omb Battlefield", 1, 7, COURSE),
            new Sm64Level("whomps_fortress", "Whomp's Fortress", 2, 7, COURSE),
            new Sm64Level("jolly_roger_bay", "Jolly Roger Bay", 3, 7, COURSE),
            new Sm64Level("cool_cool_mountain", "Cool, Cool Mountain", 4, 7, COURSE),
            new Sm64Level("big_boos_haunt", "Big Boo's Haunt", 5, 7, COURSE),
            new Sm64Level("hazy_maze_cave", "Hazy Maze Cave", 6, 7, COURSE),
            new Sm64Level("lethal_lava_land", "Lethal Lava Land", 7, 7, COURSE),
            new Sm64Level("shifting_sand_land", "Shifting Sand Land", 8, 7, COURSE),
            new Sm64Level("dire_dire_docks", "Dire, Dire Docks", 9, 7, COURSE),
            new Sm64Level("snowmans_land", "Snowman's Land", 10, 7, COURSE),
            new Sm64Level("wet_dry_world", "Wet-Dry World", 11, 7, COURSE),
            new Sm64Level("tall_tall_mountain", "Tall, Tall Mountain", 12, 7, COURSE),
            new Sm64Level("tiny_huge_island", "Tiny-Huge Island", 13, 7, COURSE),
            new Sm64Level("tick_tock_clock", "Tick Tock Clock", 14, 7, COURSE),
            new Sm64Level("rainbow_ride", "Rainbow Ride", 15, 7, COURSE),
            new Sm64Level("bowser_dark_world", "Bowser in the Dark World", 0, 0, BOWSER),
            new Sm64Level("bowser_fire_sea", "Bowser in the Fire Sea", 0, 0, BOWSER),
            new Sm64Level("bowser_sky", "Bowser in the Sky", 0, 0, BOWSER)
    );

    private LevelCatalog() {}

    public static Optional<Sm64Level> find(String id) {
        String normalized = id.toLowerCase(Locale.ROOT);
        return LEVELS.stream().filter(level -> level.id().equals(normalized)).findFirst();
    }
}
