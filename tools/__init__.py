"""Custom tools — the agents' role-specific capabilities, each wrapped behind the
scope guard. Each factory takes the shared Engagement and returns a list of
(PydanticInputModel, handler) CustomToolDef tuples for the Band adapter."""
