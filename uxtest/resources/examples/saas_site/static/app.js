const params = new URLSearchParams(window.location.search);
const variant = params.get("variant") === "clear" ? "clear" : "flawed";
const flawed = variant === "flawed";

document.body.classList.toggle("flawed", flawed);

const app = document.querySelector("#app");
const productMenu = document.querySelector("#product-menu");
const productsButton = document.querySelector("#products-button");
const mobileMenu = document.querySelector("#mobile-menu");

if (!flawed) {
  mobileMenu.setAttribute("aria-label", "Open navigation menu");
}

productsButton.addEventListener("click", () => toggleMenu());
mobileMenu.addEventListener("click", () => toggleMenu());

document.querySelectorAll("[data-route]").forEach((link) => {
  link.addEventListener("click", (event) => {
    const route = link.getAttribute("data-route");
    if (flawed && (route === "docs" || route === "pricing")) {
      event.preventDefault();
      flashMessage(route === "docs" ? "Docs are loading..." : "Pricing is being updated.");
      return;
    }
    event.preventDefault();
    navigate(route);
  });
});

function toggleMenu() {
  productMenu.classList.toggle("hidden");
  productsButton.setAttribute("aria-expanded", productMenu.classList.contains("hidden") ? "false" : "true");
}

function navigate(route) {
  history.pushState({}, "", route === "home" ? "/" : `/${route}${window.location.search}`);
  productMenu.classList.add("hidden");
  render(route);
}

window.addEventListener("popstate", () => render(currentRoute()));

function currentRoute() {
  const path = window.location.pathname.replace("/", "") || "home";
  return path;
}

function render(route = currentRoute()) {
  const pages = {
    home: homePage,
    pricing: pricingPage,
    docs: docsPage,
    security: securityPage,
    designer: designerPage,
    "interview-lab": interviewPage,
    examples: examplesPage,
    quickstart: quickstartPage,
    login: loginPage,
  };
  app.innerHTML = (pages[route] || homePage)();
  app.focus();
  bindPageActions();
}

function homePage() {
  return `
    <section class="hero">
      <p class="eyebrow">Synthetic research operations</p>
      <h1>Test research decisions before fieldwork starts.</h1>
      <p>Northstar helps teams design studies, interview simulated customers, and inspect evidence before spending fielding budget.</p>
      <div class="actions">
        <a class="button" href="${flawed ? "/login" : "/designer"}" data-route="${flawed ? "login" : "designer"}">${flawed ? "Get started" : "Explore products"}</a>
        <a class="button secondary" href="/examples" data-route="examples">View examples</a>
      </div>
    </section>
    <section class="band three">
      <article><h2>Design</h2><p>Turn goals into testable studies.</p></article>
      <article><h2>Interview</h2><p>Run AI interviews before human research.</p></article>
      <article><h2>Validate</h2><p>Compare responses and inspect evidence.</p></article>
    </section>
  `;
}

function pricingPage() {
  return page(
    "Pricing",
    flawed ? "Pricing is temporarily being updated. Contact us for details." : "Starter, Team, and Enterprise plans with transparent credit usage.",
    flawed ? "Contact sales" : "Review docs",
    flawed ? "login" : "docs",
  );
}

function docsPage() {
  return page("Documentation", "Install the SDK, create agents, run studies, and export reports.", "Start quickstart", "quickstart");
}

function securityPage() {
  return page("Security", "Data controls, audit logs, and team governance for enterprise research.", flawed ? "Contact security" : "Read security docs", flawed ? "login" : "docs");
}

function designerPage() {
  return page("Study Designer", "Create surveys, experiments, and interview guides from a research goal.", flawed ? "Continue" : "Create a study", flawed ? "login" : "quickstart");
}

function interviewPage() {
  return page("Interview Lab", "Configure AI interviewers, test probes, and review transcripts.", flawed ? "Continue" : "See interview examples", "examples");
}

function examplesPage() {
  return page("Examples", "Read notebooks for pricing research, landing-page tests, and message validation.", flawed ? "Open example" : "Open notebook", flawed ? "login" : "quickstart");
}

function quickstartPage() {
  return page("Quickstart", "Copy a working SDK example and run your first simulated study.", "Copy starter code", "docs");
}

function loginPage() {
  return `
    <section class="auth">
      <h1>Log in</h1>
      <p>${flawed ? "Use your account to continue." : "Create an account when you are ready. You can still explore products from the menu."}</p>
      <button type="button">Continue with Google</button>
      <button type="button">Continue with Microsoft</button>
      <label>Email address<input placeholder="Enter your email address" /></label>
      <label>Password<input placeholder="Enter your password" type="password" /></label>
      <button type="button">Continue</button>
    </section>
  `;
}

function page(title, body, cta, route = "login") {
  return `
    <section class="page">
      <p class="eyebrow">Northstar Research</p>
      <h1>${title}</h1>
      <p>${body}</p>
      <a class="button" href="/${route}" data-route="${route}">${cta}</a>
    </section>
  `;
}

function bindPageActions() {
  app.querySelectorAll("[data-route]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(link.getAttribute("data-route"));
    });
  });
}

function flashMessage(text) {
  let message = document.querySelector("#flash");
  if (!message) {
    message = document.createElement("div");
    message.id = "flash";
    message.className = "flash";
    document.body.append(message);
  }
  message.textContent = text;
  setTimeout(() => message.remove(), 1800);
}

render();
