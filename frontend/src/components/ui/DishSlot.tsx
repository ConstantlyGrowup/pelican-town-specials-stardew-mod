import { Link } from "react-router-dom";

type DishSlotProps = {
  label: string;
  imageUrl?: string | null;
  selected?: boolean;
  empty?: boolean;
  meta?: string;
  href?: string;
  active?: boolean;
  onClick?: () => void;
  ariaLabel?: string;
};

export function DishSlot({
  label,
  imageUrl,
  selected = false,
  empty = false,
  meta,
  href,
  active = false,
  onClick,
  ariaLabel,
}: DishSlotProps) {
  if (empty) {
    return (
      <div className="dish-slot empty" aria-hidden="true">
        <span className="dish-slot__empty-mark">✣</span>
      </div>
    );
  }

  const className = `dish-slot${selected ? " selected" : ""}${active ? " active" : ""}`;
  const content = (interactive = false) => (
    <>
      {selected && (
        <span className="slot-marker" aria-hidden="true">
          ✓
        </span>
      )}
      {imageUrl ? (
        <img src={imageUrl} alt="" />
      ) : (
        <span className="dish-slot__image-placeholder" aria-hidden="true">
          ✣
        </span>
      )}
      {interactive ? (
        <span className="dish-slot__name" role="heading" aria-level={2}>
          {label}
        </span>
      ) : (
        <h2>{label}</h2>
      )}
      {meta && <small>{meta}</small>}
    </>
  );

  if (onClick) {
    return (
      <button
        className={className}
        type="button"
        onClick={onClick}
        aria-label={ariaLabel ?? `查看${label}预览`}
        aria-pressed={active}
      >
        {content(true)}
      </button>
    );
  }

  if (href) {
    return (
      <Link className={className} to={href}>
        {content()}
      </Link>
    );
  }

  return <div className={className}>{content()}</div>;
}
