# Vault Direct-Use Credentials

Direct use allows a trusted adapter to perform one narrow operation without returning the credential to the model or chat. It is capability-based, not arbitrary command execution.

An owner-local grant binds one credential resource to:

- a structured capability ID;
- one reviewed adapter ID;
- one exact host;
- one exact operation;
- an exact set of existing credential fields;
- a timeout from one to 30 seconds.

The model still submits only `action`, `resource`, `fields`, and `purpose`. It cannot select a host, URL, adapter, command, executable, environment, timeout, or approval mode. The trusted harness resolves a capability from owner configuration and signs its complete descriptor into the destination binding. Vault requires the requested fields to equal, not merely overlap, the capability field set.

The protocol does not offer a shell adapter. Secret material must not enter `argv`, an environment mapping, a temporary file, stdout, stderr, a tool result, or a session record. An adapter receives a transient in-memory field mapping and a bounded timeout. Its receipt is recursively checked against every selected value; a value-bearing receipt fails with `ADAPTER_OUTPUT_SECRET`.

The reference `synthetic.token-check` adapter is deliberately no-network and recognizes only host `api.example.invalid`, operation `token-check`, and the `password` field. It proves the direct-use boundary in tests without contacting a real provider or using a real credential. Production provider adapters are future reviewed integrations; this release does not ship arbitrary HTTP, OAuth, browser, or command adapters.

Capability revocation blocks future attestations immediately. It cannot cancel a provider operation already completed or erase provider-side effects.
