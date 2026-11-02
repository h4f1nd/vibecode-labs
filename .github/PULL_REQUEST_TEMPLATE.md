## Summary

<!-- What changed, which project, and why. One or two sentences. -->

Project: <!-- thermal-dots | dotdat | repository root -->

## Checklist

- [ ] The change is scoped to one project unless it is root-level tooling.
- [ ] `pytest` passes in the affected project.
- [ ] `ruff check src tests benchmarks` passes.
- [ ] `mypy src` passes.
- [ ] `node --check` passes for the affected GUI (`src\thermaldots\ui\web\app.js` or `src\dotdat\ui\web\app.js`).
- [ ] Real-data tests run if the DOTDAT parser or codec changed.
- [ ] Source `.DAT` files were opened read-only; no data was modified.
- [ ] No Clarion Viewer code, assets, help text, icons or branding was copied.
- [ ] `dotdat/docs/CLAVIEW.md` updated if Clarion Viewer parity changed.
- [ ] Docs and the project's `AGENTS.md` updated if behaviour or an invariant changed.

## Tests

<!-- Which tests cover this? Synthetic fixture? Reference table? -->

## Notes

<!-- Known limits, follow-up work, or screenshots if the GUI changed. -->
