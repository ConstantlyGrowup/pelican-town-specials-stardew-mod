import type { CSSProperties } from "react";

const SPRING_OBJECTS_URL = "/assets/game/springobjects.png";
const CURSORS_URL = "/assets/game/Cursors.zh-CN.png";
const SPRING_OBJECTS_WIDTH = 384;
const SPRING_OBJECTS_HEIGHT = 624;
const CURSORS_WIDTH = 704;
const CURSORS_HEIGHT = 2256;
const TILE_SIZE = 16;
const SPRING_OBJECT_COLUMNS = SPRING_OBJECTS_WIDTH / TILE_SIZE;
const SPRING_OBJECT_ROWS = SPRING_OBJECTS_HEIGHT / TILE_SIZE;

type SpriteRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

/** These are fixed 16px UI tiles from the supplied Stardew Cursors atlas. */
const CURSOR_SPRITES = {
  recovery: { x: 0, y: 416, width: 16, height: 16 },
  health: { x: 16, y: 416, width: 16, height: 16 },
  energy: { x: 368, y: 16, width: 16, height: 16 },
  dish: { x: 688, y: 64, width: 16, height: 16 },
  collections: { x: 80, y: 368, width: 16, height: 16 },
  gift: { x: 48, y: 0, width: 16, height: 16 },
  gold: { x: 416, y: 464, width: 16, height: 16 },
} satisfies Record<string, SpriteRect>;

const SPECIFIC_ICON_URLS = {
  edibility: "/assets/game/specific-icons/饱腹度.png",
  createFirstDish: "/assets/game/specific-icons/创建第一道菜.png",
  blueprint: "/assets/game/specific-icons/料理蓝图.png",
  health: "/assets/game/specific-icons/生命恢复.png",
  sellPrice: "/assets/game/specific-icons/售价.png",
} as const;

function spriteStyle(
  source: string,
  sourceWidth: number,
  sourceHeight: number,
  rect: SpriteRect,
  size: number,
): CSSProperties {
  const scale = size / rect.width;
  return {
    width: size,
    height: size,
    flex: `0 0 ${size}px`,
    backgroundImage: `url("${source}")`,
    backgroundRepeat: "no-repeat",
    backgroundSize: `${sourceWidth * scale}px ${sourceHeight * scale}px`,
    backgroundPosition: `-${rect.x * scale}px -${rect.y * scale}px`,
    imageRendering: "pixelated",
  };
}

type GameObjectIconProps = {
  itemId: string | null | undefined;
  size?: number;
  alt?: string;
  className?: string;
};

/**
 * Renders one 16×16 object tile from the vanilla springobjects atlas. The
 * backend already validates itemId against the 1.6.15 catalog; the bounds
 * check here only keeps malformed fixture data from producing odd offsets.
 */
export function GameObjectIcon({
  itemId,
  size = 36,
  alt,
  className = "",
}: GameObjectIconProps) {
  const objectId = Number(itemId);
  const validObjectId =
    Number.isInteger(objectId) && objectId >= 0 && objectId < SPRING_OBJECT_COLUMNS * SPRING_OBJECT_ROWS;
  const classNames = `game-asset-icon game-object-icon${validObjectId ? "" : " game-object-icon--missing"}${className ? ` ${className}` : ""}`;
  const style = validObjectId
    ? spriteStyle(
        SPRING_OBJECTS_URL,
        SPRING_OBJECTS_WIDTH,
        SPRING_OBJECTS_HEIGHT,
        {
          x: (objectId % SPRING_OBJECT_COLUMNS) * TILE_SIZE,
          y: Math.floor(objectId / SPRING_OBJECT_COLUMNS) * TILE_SIZE,
          width: TILE_SIZE,
          height: TILE_SIZE,
        },
        size,
      )
    : { width: size, height: size, flex: `0 0 ${size}px` };

  return (
    <span
      className={classNames}
      style={style}
      role={alt ? "img" : undefined}
      aria-label={alt}
      aria-hidden={alt ? undefined : true}
    >
      {!validObjectId && <span aria-hidden="true">?</span>}
    </span>
  );
}

export type GameUiIconName = keyof typeof CURSOR_SPRITES;

type GameUiIconProps = {
  name: GameUiIconName;
  size?: number;
  alt?: string;
  className?: string;
};

/** Renders a small, fixed UI icon from the supplied localized Cursors atlas. */
export function GameUiIcon({
  name,
  size = 24,
  alt,
  className = "",
}: GameUiIconProps) {
  const classNames = `game-asset-icon game-ui-icon game-ui-icon--${name}${className ? ` ${className}` : ""}`;
  return (
    <span
      className={classNames}
      style={spriteStyle(CURSORS_URL, CURSORS_WIDTH, CURSORS_HEIGHT, CURSOR_SPRITES[name], size)}
      role={alt ? "img" : undefined}
      aria-label={alt}
      aria-hidden={alt ? undefined : true}
    />
  );
}

export type SpecificIconName = keyof typeof SPECIFIC_ICON_URLS;

type SpecificIconProps = {
  name: SpecificIconName;
  size?: number;
  alt?: string;
  className?: string;
};

/** Renders one of the user-supplied, individually extracted semantic icons. */
export function SpecificIcon({
  name,
  size = 32,
  alt,
  className = "",
}: SpecificIconProps) {
  return (
    <img
      className={`specific-icon specific-icon--${name}${className ? ` ${className}` : ""}`}
      src={SPECIFIC_ICON_URLS[name]}
      alt={alt ?? ""}
      width={size}
      height={size}
      aria-hidden={alt ? undefined : true}
      draggable="false"
    />
  );
}
