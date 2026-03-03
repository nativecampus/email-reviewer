# Testing Guide

This document defines what to test and what not to test in the SIDP codebase. Follow these rules when writing or modifying tests.

## Test

- **Behaviour, not implementation.** Test externally observable behaviour, not internals. If a pure refactor breaks your tests, the tests are coupled to implementation.
- **Public interfaces.** Inputs in, expected outputs out.
- **Edge cases in your logic.** Nulls, empty collections, boundary values — but only where your code makes decisions about them.
- **State transitions and their guards.**
- **Error paths.** Right exception, right fallback. Assert meaningful content in messages, not full string equality.
- **Conditional rendering.** If a component decides whether to show something based on state or props, that's logic. Test it.
- **User interaction flows.** Click, submit, display. Test what the user experiences.
- **Derived display state.** Formatting, computed values, status selection. Extract into pure functions where possible and test those.

## Do Not Test

- **Framework and library code.** You didn't write it.
- **Private methods directly.** They get covered through the public interface.
- **Implementation details.** Don't assert which internal methods were called or how data is structured internally.
- **Trivial code.** Getters, setters, pass-through assignments, constructors with no logic.
- **External systems in unit tests.** Mock the boundary. Integration tests are separate.
- **Static markup.** If nothing in your code decides whether or what to render, there's nothing to test.
- **Styling and layout.** Unit tests are the wrong tool. Use Playwright's screenshot comparison (`expect(page).to_have_screenshot()`) if you need visual regression coverage.
- **Component composition.** Don't test that Parent renders Child. Test what the user sees.
- **Snapshots as a default.** They pass on first run, break on every change, and get bulk-updated without review. Exception: tightly scoped snapshots for stable contracts like API schemas are legitimate.

## Stack-Specific Guidance

### FastAPI routes
Use `TestClient` from `starlette.testclient`. Test status codes, response shapes, and auth guards. Don't test that FastAPI parses JSON — it does.

### Pydantic models
Test custom validators only. Don't test that a field with `str` rejects an `int` — Pydantic handles that.

### SQLAlchemy
Integration-test your query logic — filters, joins, aggregations — against a real test database. Don't mock the ORM session.

### Alembic migrations
Test that upgrade then downgrade is reversible and that data survives the round trip. Just running without error proves the SQL is valid, not correct.

### Jinja2 templates
Test that your route passes the right context to the template. Asserting key content in rendered output is fine — don't test static markup or visual detail. Use Playwright for anything visual.

### Dependency injection
Override dependencies in tests using `app.dependency_overrides`. Don't mock FastAPI internals.

### Pydantic Settings
Don't test config loading. Set env vars in your test fixtures and move on.
