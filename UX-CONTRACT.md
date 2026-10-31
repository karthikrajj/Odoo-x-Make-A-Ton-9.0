# UX contract
Shared forms, navigation, tables and feedback are owned by static/app.js. Native Select/Listbox and Date controls use platform popups. Form errors remain inline; feedback uses a live region. Server pagination is required. Currency en-IN / INR. Local demo stores no real financial credentials. Monetary values are integer paise; invoice snapshots immutable; payments allocated explicitly. Staff can operate billing, admin configures plans, customers see only owned records. No external charge execution. All mutation requests require a session and same-origin JSON.

## Canonical UI Map
| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Select/Listbox | static/app.js native select | UX-CONTRACT.md | native | browser review pending |
| Date | static/app.js input date | UX-CONTRACT.md | native | browser review pending |
| Form | static/app.js submit handler | UX-CONTRACT.md | create | unit tests and browser review pending |
| Scrollbar | static/style.css | DESIGN.md | global | static audit |
| Toast | static/app.js notice | UX-CONTRACT.md | status | browser review pending |
