# Brainlink Protocol V0

An administrator creates a short-lived URL whose fragment contains a single-use invitation token. URL fragments do not reach the HTTP server or ordinary access logs. The static `/v1/brainlinks/connect` representation tells an agent how to connect.

1. The agent reads the token from the fragment and sends it in the JSON body of `POST /v1/brainlinks/claim` with display name, harness type, and requested scopes.
2. The server atomically consumes the unexpired token, creates a pending agent, and returns a request ID plus one-time claim secret.
3. The administrator lists pending requests and approves explicit scopes or denies the request.
4. The claimant sends request ID and claim secret in the JSON body of `POST /v1/brainlinks/exchange`.
5. After approval, the server generates an agent credential, stores only its hash, and returns the raw credential once. Repeated exchange is rejected.
6. The agent stores the credential outside the repository, uses it only in an authorization header, configures HTTP or MCP, and runs a harmless `get_context` call.

Invitation possession never reads data. Tokens and claim secrets are stored only as hashes. Expiration, replay, approval, denial, credential issuance, and revocation are audited without raw values.
