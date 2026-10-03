package dev.eiersohn.sm64cross.level;

public record Sm64Level(
        String id,
        String displayName,
        int courseNumber,
        int normalStars,
        LevelKind kind
) {
    public enum LevelKind {
        CASTLE,
        COURSE,
        SECRET,
        BOWSER
    }
}
