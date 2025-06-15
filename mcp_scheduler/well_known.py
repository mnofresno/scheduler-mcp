"""Well-known endpoint for MCP Scheduler."""
import inspect
from aiohttp import web


def tool_to_schema(tool):
    """Convert a tool function to a JSON schema fragment."""
    sig = getattr(tool, "signature", None)
    params = {}
    required = []
    if sig:
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            param_type = "string"
            if param.annotation != inspect._empty:
                if param.annotation in (int,):
                    param_type = "integer"
                elif param.annotation in (float,):
                    param_type = "number"
                elif param.annotation in (bool,):
                    param_type = "boolean"
                elif param.annotation in (dict, dict[str, str]):
                    param_type = "object"
                elif param.annotation in (list, list[str]):
                    param_type = "array"
            params[name] = {"type": param_type}
            if param.default == inspect._empty:
                required.append(name)
    return {
        "name": tool.name,
        "description": tool.description or "",
        "endpoint": tool.name,
        "method": "POST",
        "parameters": {
            "type": "object",
            "properties": params,
            "required": required if required else [],
            "additionalProperties": False,
        },
    }


async def well_known_handler(request):
    from main import server  # imported at runtime to avoid circular deps
    mcp_tools = [tool_to_schema(t) for t in getattr(server.mcp, "tools", [])]
    schema = {
        "name": server.config.server_name,
        "version": server.config.server_version,
        "tools": mcp_tools,
        "mcp_endpoint": "/mcp",
    }
    return web.json_response(schema)


def setup_well_known(app: web.Application) -> None:
    """Register the well-known handler on the given aiohttp app."""
    app.router.add_get("/.well-known/mcp-schema.json", well_known_handler)
