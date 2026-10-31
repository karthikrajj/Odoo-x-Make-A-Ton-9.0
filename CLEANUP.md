# Production cleanup report

## 1. Files removed or relocated
Removed obsolete root legacy.py, domain.py, services.py and delivery.py after moving active code into renewsure/. The old duplicate HTTP server, billing preview/run and date-advance implementations were unused by the active platform. Root server.py remains the supported launcher.

Moved test_server.py to tests/test_domain.py, test_forms.cjs to tests/test_forms.cjs, and frontend handler tests into tests/. Generated verification/performance/email evidence now lives under reports/ rather than the source root.

Removed development-only invoice-qa.pdf/png and stale premium-audit.json/premium-ui.json after checking references. Existing recovery databases and active logs are retained. upgrade.py was already deleted before this cleanup and is not counted as a cleanup removal.

## 2. Dead code removed
Removed unreachable public-demo-mailbox UI remnants, verified unused CSS selectors and unused Python imports. Removed transient refactoring scripts after use. Kept uncertain files and supported terminal/GUI Gmail setup entry points.

## 3. Dependencies removed
None. There is no package.json or lockfile and the application uses Python's standard library. Ruff, ESLint and Prettier are development checks, not runtime dependencies. No major runtime upgrades were performed.

## 4. Refactoring
Separated configuration, SQLite ownership/schema, demo seeding, password handling, money calculations, billing, service routes, PDF documents, email delivery and HTTP handling into renewsure/. Extracted focused route helpers. Shared monthly-value calculations and Gmail connection validation/persistence. Removed the email-to-HTTP circular dependency. Configuration is loaded explicitly at startup rather than as an import side effect. Formatting and lint configuration make future checks repeatable.

## 5. Performance
The same frontend handler journey now requires 75 HTTP requests versus 171 before cleanup by refreshing only affected catalogs. Targeted billing previews query the selected subscription rather than unrelated lines/invoices. A composite bank-transaction identity index supports duplicate checks. Seed generation preloads plans rather than repeating thousands of identical lookups. Four-client checks over 10,050 subscriptions and a 9,459-invoice batch completed 34 requests with a maximum of 982.76 ms. This is a local benchmark, not a production capacity guarantee.

## 6. Security
No exposed provider credentials or private keys were found by the repository scan. The scan also checked for the actual configured SMTP secret without printing it. .env is ignored and excluded from release packaging. Removed personal sender defaults from source; configured senders still populate locally. Gmail configuration saves atomically through a private temporary file, and setup tests reject header injection and preserve configuration on failed authentication. No real emails were sent by this cleanup's tests.

Public-hosting limitations remain: seeded demo credentials, a loopback standard-library HTTP server, localhost cookie/transport assumptions and local file-based secret storage. These require deployment review; this pass does not certify public production security. Any normal account password previously shared in chat should be changed by its owner.

## 7. Checks performed
93 unit/regression tests; 12 JavaScript form checks; actual frontend handlers against real HTTP and an isolated DOM adapter; ten API demo journeys; role/ownership/reset checks; full billing batch; injected rollback and retry; concurrent HTTP reads; Python compilation; Ruff lint and format checks; ESLint 10.14.0; Prettier 3.6.2; import/cycle/secret scan. All passed. The source uses Python and JavaScript without static typing; no static type-checker result is claimed.

## 8. Build result
The allowlisted dist/renewsure-release.zip passed compilation, ZIP integrity and extraction/bootstrap checks. It excludes .env, customer databases, reports, logs and caches. The app needs Python 3.12; Node is used for development checks only. The local app was restarted on port 8766; six authenticated endpoint smoke checks passed and financial-record fingerprints were identical before and after restart.

## 9. Remaining technical debt
The large frontend rendering/action module could be split incrementally in later work. Some workflow/service modules remain substantial; further decomposition should have separate regression coverage. Public hosting, operational backup scheduling, secret management and deployment monitoring remain separate work. Existing financial policies, demo workflows and authentication behavior were intentionally preserved.

## 10. Manual review
Complete a real browser/mobile/accessibility walkthrough; the DOM adapter cannot verify layout or keyboard behavior. Review recovery-backup retention before deleting historical databases. Review seeded accounts before any public deployment. Configure HTTPS and a hardened hosting stack before public exposure. Confirm target-host capacity with realistic load tests. Gmail Inbox receipt was confirmed previously; this cleanup preserved its configuration rather than sending another message.

Machine-readable evidence is under reports/. Run python verify_all.py, python scripts/check_repository.py and python scripts/build_release.py to regenerate it.
