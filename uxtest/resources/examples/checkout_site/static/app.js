const params = new URLSearchParams(window.location.search);
const variant = params.get("variant") === "clear" ? "clear" : "confusing";
const isConfusing = variant === "confusing";

document.body.classList.toggle("confusing", isConfusing);

const cartCount = document.querySelector("#cart-count");
const cartStatus = document.querySelector("#cart-status");
const cartPanel = document.querySelector("#cart-panel");
const cartActions = document.querySelector("#cart-actions");
const checkout = document.querySelector("#checkout");
const checkoutHelp = document.querySelector("#checkout-help");
const form = document.querySelector("#checkout-form");
const formError = document.querySelector("#form-error");
const confirmation = document.querySelector("#confirmation");
const variantLabel = document.querySelector("#variant-label");

variantLabel.textContent = isConfusing
  ? "Variant: competing calls to action"
  : "Variant: clear checkout";

checkoutHelp.textContent = isConfusing
  ? "Continue with the details below."
  : "Enter guest checkout details. Use card number 4242424242424242.";

document.querySelector("#add-to-cart").addEventListener("click", () => {
  cartCount.textContent = "1";
  cartStatus.textContent = "Breakfast Bundle is ready for checkout.";
  cartPanel.classList.remove("hidden");
  renderCartActions();
  document.querySelector("#cart").scrollIntoView({ behavior: "smooth" });
});

function renderCartActions() {
  cartActions.replaceChildren();

  if (isConfusing) {
    const continueButton = button("Continue", "primary-alt", () => {
      checkout.classList.remove("hidden");
      checkout.scrollIntoView({ behavior: "smooth" });
    });
    const expressButton = button("Express Pay", "", () => {
      formError.textContent = "Something went wrong.";
      checkout.classList.remove("hidden");
      checkout.scrollIntoView({ behavior: "smooth" });
    });
    const detailsButton = button("Review details", "secondary", () => {
      cartStatus.textContent = "The item is still in your cart.";
    });
    cartActions.append(continueButton, expressButton, detailsButton);
    return;
  }

  cartActions.append(
    button("Checkout as guest", "", () => {
      checkout.classList.remove("hidden");
      checkout.scrollIntoView({ behavior: "smooth" });
    }),
  );
}

function button(label, className, onClick) {
  const el = document.createElement("button");
  el.type = "button";
  el.textContent = label;
  if (className) el.className = className;
  el.addEventListener("click", onClick);
  return el;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form).entries());
  const missing = ["email", "name", "card", "zip"].filter((key) => !values[key]?.trim());

  if (missing.length) {
    formError.textContent = isConfusing
      ? "Check the fields."
      : `Missing ${missing.map((key) => fieldLabel(key)).join(", ")}.`;
    document.querySelector(`#${missing[0]}`).focus();
    return;
  }

  if (!values.email.includes("@")) {
    formError.textContent = isConfusing ? "Not valid." : "Enter a valid email address.";
    document.querySelector("#email").focus();
    return;
  }

  if (values.card.replace(/\s/g, "") !== "4242424242424242") {
    formError.textContent = isConfusing
      ? "Payment problem."
      : "Use the test card number 4242424242424242.";
    document.querySelector("#card").focus();
    return;
  }

  formError.textContent = "";
  checkout.classList.add("hidden");
  confirmation.classList.remove("hidden");
  confirmation.scrollIntoView({ behavior: "smooth" });
});

function fieldLabel(key) {
  return {
    email: "email",
    name: "shipping name",
    card: "card number",
    zip: "ZIP code",
  }[key];
}

