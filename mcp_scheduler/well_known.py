"""
HTTP endpoint for /.well-known/mcp-schema.json for MCP auto-discovery.
"""
import json
from aiohttp import web
import inspect

def tool_to_schema(tool):
    # Extract parameters and types from the tool function
    sig = getattr(tool, 'signature', None)
    params = {}
    required = []
    if sig:
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            # Type and basic description
            param_type = 'string'
            if param.annotation != inspect._empty:
                if param.annotation == int:
                    param_type = 'integer'
                elif param.annotation == float:
                    param_type = 'number'
                elif param.annotation == bool:
                    param_type = 'boolean'
                elif param.annotation == dict or param.annotation == dict[str, str]:
                    param_type = 'object'
                elif param.annotation == list or param.annotation == list[str]:
                    param_type = 'array'
            params[name] = {"type": param_type}
            if param.default == inspect._empty:
                required.append(name)
    return {
        "name": tool.name,
        "description": tool.description or "",
        "endpoint": tool.name,  # By default, the tool's name
        "method": "POST",      # MCP tools are usually POST
        "parameters": {
            "type": "object",
            "properties": params,
            "required": required if required else [],
            "additionalProperties": False
        }
    }

async def well_known_handler(request):
    # Import server and tools at runtime to avoid circular imports
    from .server import SchedulerServer
    from main import server
    
    # Collect tool info from the MCP server
    mcp_tools = [tool_to_schema(tool) for tool in server.mcp.tools]
    schema = {"tools": mcp_tools}
    return web.json_response(schema)

def setup_well_known(app):
    app.router.add_get("/.well-known/mcp-schema.json", well_known_handler)
