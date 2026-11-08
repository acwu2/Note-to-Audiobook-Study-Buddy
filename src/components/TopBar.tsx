import { BookIcon, ShareIcon } from './Icons';

export default function TopBar({ title }: { title: string }) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">
          <BookIcon size={20} />
        </span>
        <span className="brand-name">Study Buddy</span>
      </div>
      <span className="topbar-divider" aria-hidden="true" />
      <h1 className="topbar-title">{title}</h1>
      <button type="button" className="btn btn-outline">
        <ShareIcon size={16} />
        Share
      </button>
      <span className="avatar" role="img" aria-label="Your account">
        D
      </span>
    </header>
  );
}
