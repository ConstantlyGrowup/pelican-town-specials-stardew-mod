import { NavLink, Outlet } from "react-router-dom";
import { PRODUCT_COPY } from "../../i18n/copy";

export function AppShell() {
  const copy = PRODUCT_COPY.zh;

  return (
    <div className="app-shell">
      <nav className="app-nav" aria-label={copy.primaryNavigation}>
        <NavLink to="/" end>
          {copy.home}
        </NavLink>
        <NavLink to="/create">{copy.create}</NavLink>
        <NavLink to="/cookbook">{copy.cookbook}</NavLink>
        <NavLink to="/settings">{copy.settings}</NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
