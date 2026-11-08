# Assistant core contract, initial version

Based on the approved Odoo assistant design and reviewed OpenCode task `ASISTENTE-NUCLEO-01`. Implementation and signatures will be tested locally; this document is not evidence of working software.

## Trust and identity

The server derives the authenticated Odoo user, active company and allowed companies from its own request environment, never from model-supplied identifiers. A conversation belongs to a user and a company; access and record rules are checked on every read and write. A tool request cannot supply a user, impersonate another employee, enable superuser mode or extend allowed companies.

## Capability calls

The model can propose a registered capability name and a structured argument object. The server rejects unknown names, unknown keys, invalid types, ambiguous entities and out-of-range values before dispatch. A registered server-side handler runs using the caller's Odoo environment and the registered schema. No model-generated Python, SQL, arbitrary domain or model method is executable. A restricted HR self-service helper may use narrowly scoped privilege only after server-side identity checks and must return only authorized balance fields.

Initial capabilities are own vacation balance, customer invoice count, supplier spending, product sales, stock transfer proposal and stock transfer confirmation. Each integration declares its own authorization, arguments and output schema. Proposals do not transfer stock. Confirmations refer to an immutable proposal bound to the current user and company, expire, are consumed once and are revalidated atomically before any stock operation.

## Result envelope

The server returns `status` (`ok`, `needs_clarification`, `needs_confirmation` or `error`), `capability`, structured `data`, explicit `criteria`, permitted Odoo references and a stable error `code` where applicable. Authorization failures and missing records must not reveal hidden records. Final numerical facts are rendered from the server result; model output is not evidence that any operation succeeded.

## Verification obligations

1. A caller cannot access another user's conversation, balance or company by changing parameters or invoking RPC directly.
2. Unknown tools, arguments, generated code and injected instructions embedded in record names cause no unauthorized operations.
3. No capability permits accounting or vacation writes; no assistant tool writes quants directly even if the user has native stock permissions.
4. A transfer confirmation cannot be reused or replayed concurrently; changed permissions, quantities or company invalidate or reject execution, with the actual outcome recorded.
5. Errors, partial availability, lots and Odoo wizards never produce a false successful-transfer message.
6. Conversation and audit data are isolated and minimized; fake inference covers timeout, invalid output and unavailable service without invoking an external provider.

All tests run on the user's PC, in an isolated Odoo database. The VPS is not a test target.
