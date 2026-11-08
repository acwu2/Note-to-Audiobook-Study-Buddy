import { BookIcon } from './Icons';

/**
 * The reference's navy bar. Nav items are presentational for now: "My notes"
 * has an endpoint but no screen, and Courses has no backend at all, so neither
 * pretends to be a working link.
 */
export default function TopBar({ crumb }: { crumb?: string }) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <span className="brand-mark" aria-hidden="true"><BookIcon /></span>
        <span className="brand-word">Study Buddy</span>
        <nav className="topnav" aria-label="Sections">
          <span className="topnav-item is-current" aria-current="page">Upload</span>
          <span className="topnav-item is-soon" title="Not built yet">My notes</span>
          <span className="topnav-item is-soon" title="Not built yet">Courses</span>
        </nav>
        {crumb && <span className="topcrumb">{crumb}</span>}
        <span className="avatar" aria-hidden="true">D</span>
      </div>
    </header>
  );
}
