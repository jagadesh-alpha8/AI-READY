import React, { useEffect, useRef, useState } from 'react';

/**
 * Wraps a wide table in the `.table-shell.table-scroll` box and adds a second
 * horizontal scrollbar ABOVE the table, kept in sync with the box's own.
 *
 * The box is height-capped, so its native horizontal scrollbar sits at its
 * bottom edge -- usually below the fold on a long table, where nobody finds
 * it. The top bar is visible as soon as the table is, and only renders when
 * the table is actually wider than the box.
 */
export const ScrollableTable: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const topRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [scrollWidth, setScrollWidth] = useState(0);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const measure = () => {
      setScrollWidth(body.scrollWidth);
      setOverflowing(body.scrollWidth > body.clientWidth + 1);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(body);
    if (body.firstElementChild) observer.observe(body.firstElementChild);
    return () => observer.disconnect();
  }, []);

  const mirror = (source: 'top' | 'body') => {
    const from = source === 'top' ? topRef.current : bodyRef.current;
    const to = source === 'top' ? bodyRef.current : topRef.current;
    // Only write when they differ: the mirrored bar's own scroll event then
    // finds them equal and stops, so the two never bounce back and forth.
    if (!from || !to || to.scrollLeft === from.scrollLeft) return;
    to.scrollLeft = from.scrollLeft;
  };

  return (
    <div>
      {overflowing && (
        <div
          ref={topRef}
          onScroll={() => mirror('top')}
          className="table-hscroll-top"
          aria-hidden="true"
        >
          <div style={{ width: scrollWidth, height: 1 }} />
        </div>
      )}
      <div ref={bodyRef} onScroll={() => mirror('body')} className="table-shell table-scroll">
        {children}
      </div>
    </div>
  );
};
