# Checkout Site Example

This is a dependency-free localhost target for `uxtest` development. It serves a
small product and checkout flow with two variants:

- `/?variant=clear` has straightforward labels and errors.
- `/?variant=confusing` has competing CTAs, vague copy, and less helpful form
  feedback.

Run it with:

```sh
python examples/checkout_site/server.py
```

Then open:

```text
http://127.0.0.1:8765/?variant=confusing
```

