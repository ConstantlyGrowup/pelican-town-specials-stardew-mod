import { Link, NavLink, Outlet } from "react-router-dom";
import { PRODUCT_COPY } from "../../i18n/copy";

export function AppShell() {
  const copy = PRODUCT_COPY.zh;

  return (
    <div className="app-shell" data-theme="warm">
      <a className="skip-link" href="#main-content">
        跳到主要内容
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
