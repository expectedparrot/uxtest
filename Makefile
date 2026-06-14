DOCS_HTML_DIR ?= .docs-html
DOCS_MD := $(shell find README.md SPEC.md examples -name '*.md' -type f | sort)
DOCS_HTML := $(patsubst %.md,$(DOCS_HTML_DIR)/%.html,$(DOCS_MD))

.PHONY: docs-html docs-open docs-clean

docs-html: $(DOCS_HTML)
	@printf 'Wrote docs HTML to %s\n' "$(DOCS_HTML_DIR)"
	@printf 'Open %s\n' "$(DOCS_HTML_DIR)/README.html"

$(DOCS_HTML_DIR)/%.html: %.md
	@mkdir -p "$(@D)"
	pandoc "$<" \
		--standalone \
		--metadata "title=$(basename $(notdir $<))" \
		-o "$@"
	perl -0pi -e 's/href="([^"#]+)\.md(#[^"]*)?"/href="$$1.html$$2"/g' "$@"

docs-open: docs-html
	open "$(DOCS_HTML_DIR)/README.html"

docs-clean:
	rm -rf "$(DOCS_HTML_DIR)"
