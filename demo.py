from fastmcp import FastMCP
import random

mcp = FastMCP("Utility Server")


@mcp.tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers and return the result."""
    return a + b


@mcp.tool
def random_number(min_value: int = 1, max_value: int = 100) -> int:
    """Generate a random integer between min_value and max_value."""
    if min_value > max_value:
        raise ValueError("min_value must be less than or equal to max_value")

    return random.randint(min_value, max_value)


if __name__ == "__main__":
    mcp.run()