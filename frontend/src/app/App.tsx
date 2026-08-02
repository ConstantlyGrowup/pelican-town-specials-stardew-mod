import { PRODUCT_COPY } from "../i18n/copy";

export function App() {
  const copy = PRODUCT_COPY.zh;

  return (
    <main>
      <section aria-labelledby="app-title">
        <p lang="en">Pelican Town Specials</p>
        <h1 id="app-title">{copy.productName}</h1>
        <p>{copy.tagline}</p>
      </section>
    </main>
  );
}
