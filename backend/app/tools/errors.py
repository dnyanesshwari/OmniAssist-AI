class ToolError(Exception):
    """Business-rule failure. `code` is machine-readable so the agent (step 2) can react safely."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message

    def to_dict(self) -> dict:
        return {"ok": False, "error": self.code, "message": self.message}
