"""Model-visible schema for the MegaBrain Vault Hermes tool."""

MEGABRAIN_VAULT = {
    "name": "megabrain_vault",
    "description": (
        "Request masked MegaBrain Vault metadata or an owner-approved private delivery/direct use. "
        "Supply only the action, provider-independent logical resource, exact field names, and a "
        "structured purpose code. Never include values, destination identifiers, private-context "
        "claims, approval flags, hosts, commands, signatures, keys, or attestations."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {
                "type": "string",
                "enum": ["locate", "metadata", "deliver", "use"],
            },
            "resource": {
                "type": "string",
                "maxLength": 512,
                "pattern": "^[a-z][a-z0-9+.-]{0,31}://[A-Za-z0-9][A-Za-z0-9._~/-]{0,477}$",
            },
            "fields": {
                "type": "array",
                "maxItems": 32,
                "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
            },
            "purpose": {
                "type": "string",
                "pattern": "^[a-z0-9][a-z0-9._-]{0,63}$",
            },
        },
        "required": ["action", "resource", "fields", "purpose"],
    },
}
