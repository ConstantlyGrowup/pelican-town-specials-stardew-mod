import { useEffect, useId, useRef, type ReactNode } from "react";
import { PRODUCT_COPY } from "../../i18n/copy";

type PixelModalProps = {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
};

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** A small, keyboard-safe modal with the same hard-edged paper treatment as the app panels. */
export function PixelModal({
  title,
  description,
  onClose,
  children,
  footer,
}: PixelModalProps) {
  const copy = PRODUCT_COPY.zh;
  const titleId = useId();
  const descriptionId = useId();
  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousActiveElement.current = document.activeElement as HTMLElement | null;
    const modal = modalRef.current;
    const focusable = modal?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    (focusable ?? modal)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !modal) {
        return;
      }
      const elements = Array.from(
        modal.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (elements.length === 0) {
        event.preventDefault();
        modal.focus();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousActiveElement.current?.focus();
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation">
      <div
        ref={modalRef}
        className="pixel-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
      >
        <div className="pixel-modal__header">
          <div>
            <p className="eyebrow">PELican TOWN / NOTICE</p>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={onClose}
            aria-label={copy.pickClose}
          >
            ×
          </button>
        </div>
        {description && (
          <p id={descriptionId} className="pixel-modal__description">
            {description}
          </p>
        )}
        <div className="pixel-modal__body">{children}</div>
        {footer && <div className="pixel-modal__footer">{footer}</div>}
      </div>
    </div>
  );
}
