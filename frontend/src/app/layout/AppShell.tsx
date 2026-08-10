import { Link, NavLink, Outlet } from "react-router-dom";
import { useCopy } from "../../i18n/locale";

export function AppShell() {
  const copy = useCopy();

  return (
    <div className="app-shell" data-theme="warm">
      <a className="skip-link" href="#main-content">
        {copy.skipToMainContent}
      </a>
      <header className="app-nav">
        <Link className="app-brand" to="/" aria-label={copy.productName}>
          <span className="brand-mark" aria-hidden="true">⚒</span>
          <span>{copy.productName}</span>
        </Link>
        <nav className="app-nav-links" aria-label={copy.primaryNavigation}>
          <NavLink to="/" end>
            {copy.home}
          </NavLink>
          <NavLink to="/create">{copy.create}</NavLink>
          <NavLink to="/cookbook">{copy.cookbook}</NavLink>
          <NavLink to="/settings">{copy.settings}</NavLink>
        </nav>
      </header>
      <div id="main-content" className="app-main" tabIndex={-1}>
        <Outlet />
      </div>
    </div>
  );
}
