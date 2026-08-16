from fastmcp import FastMCP
import aiosqlite
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio


# --------------------------------------------------
# File locations
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "expenses.db"
CATEGORIES_PATH = BASE_DIR / "categories.json"


# --------------------------------------------------
# Database Connection
# --------------------------------------------------

async def get_connection():
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


# --------------------------------------------------
# Database Setup
# --------------------------------------------------

async def init_db():

    conn = await get_connection()

    # Expenses table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            expense_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Credits / income table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            source TEXT NOT NULL,
            description TEXT,
            credit_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    await conn.commit()
    await conn.close()


# --------------------------------------------------
# FastMCP Startup / Shutdown
# --------------------------------------------------

@asynccontextmanager
async def app_lifespan(server):
    print("Initializing expense database...", flush=True)

    await init_db()

    print("Expense database initialized.", flush=True)

    yield


# --------------------------------------------------
# MCP Server
# --------------------------------------------------

mcp = FastMCP(
    "Expense Tracker",
    lifespan=app_lifespan
)


# --------------------------------------------------
# Tool: Add Expense
# --------------------------------------------------

@mcp.tool
async def add_expense(
    amount: float,
    category: str,
    description: str = "",
    expense_date: str = ""
) -> str:
    """
    Add a new expense to the expense tracker.

    Args:
        amount: Amount spent.
        category: Expense category such as food, travel, shopping, bills.
        description: Optional description of the expense.
        expense_date: Date of expense in YYYY-MM-DD format.
                       If omitted, today's date is used.
    """

    if amount <= 0:
        return "Error: amount must be greater than 0."

    if not expense_date:
        expense_date = datetime.now().strftime("%Y-%m-%d")

    try:
        datetime.strptime(expense_date, "%Y-%m-%d")
    except ValueError:
        return "Error: expense_date must be in YYYY-MM-DD format."

    conn = await get_connection()

    cursor = await conn.execute(
        """
        INSERT INTO expenses
        (amount, category, description, expense_date, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            amount,
            category.lower(),
            description,
            expense_date,
            datetime.now().isoformat()
        )
    )

    expense_id = cursor.lastrowid

    await conn.commit()
    await conn.close()

    return (
        f"Expense added successfully.\n"
        f"ID: {expense_id}\n"
        f"Amount: ₹{amount:.2f}\n"
        f"Category: {category}\n"
        f"Description: {description or 'None'}\n"
        f"Date: {expense_date}"
    )


# --------------------------------------------------
# Tool: Delete Expense
# --------------------------------------------------

@mcp.tool
async def delete_expense(expense_id: int) -> str:
    """
    Delete an expense using its ID.

    Args:
        expense_id: ID of the expense to delete.
    """

    conn = await get_connection()

    # Check whether expense exists
    cursor = await conn.execute(
        """
        SELECT *
        FROM expenses
        WHERE id = ?
        """,
        (expense_id,)
    )

    expense = await cursor.fetchone()

    if not expense:
        await conn.close()
        return f"Error: No expense found with ID {expense_id}."

    # Delete expense
    await conn.execute(
        """
        DELETE FROM expenses
        WHERE id = ?
        """,
        (expense_id,)
    )

    await conn.commit()
    await conn.close()

    return (
        f"Expense deleted successfully.\n"
        f"ID: {expense_id}\n"
        f"Amount: ₹{expense['amount']:.2f}\n"
        f"Category: {expense['category']}\n"
        f"Description: {expense['description'] or 'None'}\n"
        f"Date: {expense['expense_date']}"
    )


# --------------------------------------------------
# Tool: Add Credit
# --------------------------------------------------

@mcp.tool
async def add_credit(
    amount: float,
    source: str,
    description: str = "",
    credit_date: str = ""
) -> str:
    """
    Add a credit/income to the expense tracker.

    Args:
        amount: Amount received.
        source: Source of the credit, such as salary, freelance,
                refund, gift, or other income.
        description: Optional description.
        credit_date: Date of credit in YYYY-MM-DD format.
                     If omitted, today's date is used.
    """

    if amount <= 0:
        return "Error: credit amount must be greater than 0."

    if not credit_date:
        credit_date = datetime.now().strftime("%Y-%m-%d")

    try:
        datetime.strptime(credit_date, "%Y-%m-%d")
    except ValueError:
        return "Error: credit_date must be in YYYY-MM-DD format."

    conn = await get_connection()

    cursor = await conn.execute(
        """
        INSERT INTO credits
        (amount, source, description, credit_date, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            amount,
            source.lower(),
            description,
            credit_date,
            datetime.now().isoformat()
        )
    )

    credit_id = cursor.lastrowid

    await conn.commit()
    await conn.close()

    return (
        f"Credit added successfully.\n"
        f"ID: {credit_id}\n"
        f"Amount: ₹{amount:.2f}\n"
        f"Source: {source}\n"
        f"Description: {description or 'None'}\n"
        f"Date: {credit_date}"
    )


# --------------------------------------------------
# Tool: Summary
# --------------------------------------------------

@mcp.tool
async def summary(
    category: str = "",
    start_date: str = "",
    end_date: str = ""
) -> str:
    """
    Get an expense and credit summary.

    Args:
        category: Optional expense category filter.
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.

    Returns:
        Total expenses, credits, balance and expense breakdown.
    """

    conn = await get_connection()

    # --------------------------------------------------
    # Expense filters
    # --------------------------------------------------

    expense_conditions = []
    expense_params = []

    if category:
        expense_conditions.append("category = ?")
        expense_params.append(category.lower())

    if start_date:
        expense_conditions.append("expense_date >= ?")
        expense_params.append(start_date)

    if end_date:
        expense_conditions.append("expense_date <= ?")
        expense_params.append(end_date)

    expense_where = ""

    if expense_conditions:
        expense_where = "WHERE " + " AND ".join(expense_conditions)

    # --------------------------------------------------
    # Expense Total
    # --------------------------------------------------

    cursor = await conn.execute(
        f"""
        SELECT
            COUNT(*) AS count,
            COALESCE(SUM(amount), 0) AS total
        FROM expenses
        {expense_where}
        """,
        expense_params
    )

    expense_result = await cursor.fetchone()

    expense_total = expense_result["total"]
    expense_count = expense_result["count"]

    # --------------------------------------------------
    # Expense Category Breakdown
    # --------------------------------------------------

    cursor = await conn.execute(
        f"""
        SELECT
            category,
            COUNT(*) AS count,
            SUM(amount) AS total
        FROM expenses
        {expense_where}
        GROUP BY category
        ORDER BY total DESC
        """,
        expense_params
    )

    category_results = await cursor.fetchall()

    # --------------------------------------------------
    # Credit filters
    # --------------------------------------------------

    credit_conditions = []
    credit_params = []

    if start_date:
        credit_conditions.append("credit_date >= ?")
        credit_params.append(start_date)

    if end_date:
        credit_conditions.append("credit_date <= ?")
        credit_params.append(end_date)

    credit_where = ""

    if credit_conditions:
        credit_where = "WHERE " + " AND ".join(credit_conditions)

    # --------------------------------------------------
    # Credit Total
    # --------------------------------------------------

    cursor = await conn.execute(
        f"""
        SELECT
            COUNT(*) AS count,
            COALESCE(SUM(amount), 0) AS total
        FROM credits
        {credit_where}
        """,
        credit_params
    )

    credit_result = await cursor.fetchone()

    credit_total = credit_result["total"]
    credit_count = credit_result["count"]

    await conn.close()

    # --------------------------------------------------
    # Calculate Balance
    # --------------------------------------------------

    balance = credit_total - expense_total

    # --------------------------------------------------
    # Format Result
    # --------------------------------------------------

    result = []

    result.append("Expense Tracker Summary")
    result.append("=======================")

    result.append("")
    result.append("Credits / Income")
    result.append("----------------")
    result.append(f"Number of credits: {credit_count}")
    result.append(f"Total credits: ₹{credit_total:.2f}")

    result.append("")
    result.append("Expenses")
    result.append("--------")
    result.append(f"Number of expenses: {expense_count}")
    result.append(f"Total expenses: ₹{expense_total:.2f}")

    result.append("")
    result.append("Balance")
    result.append("-------")
    result.append(f"₹{balance:.2f}")

    if start_date:
        result.append("")
        result.append(f"From: {start_date}")

    if end_date:
        result.append(f"To: {end_date}")

    if category:
        result.append(f"Category: {category}")

    result.append("")
    result.append("Expense Category Breakdown")
    result.append("--------------------------")

    if not category_results:
        result.append("No expenses found.")
    else:
        for row in category_results:
            result.append(
                f"{row['category']}: "
                f"₹{row['total']:.2f} "
                f"({row['count']} expenses)"
            )

    return "\n".join(result)


# --------------------------------------------------
# Resource: Categories
# --------------------------------------------------

@mcp.resource(
    "expense://categories",
    name="Expense Categories",
    description="Available expense categories and subcategories",
    mime_type="application/json"
)
async def categories():

    print(
        "RESOURCE READ: expense://categories",
        flush=True
    )

    return await asyncio.to_thread(
        CATEGORIES_PATH.read_text,
        encoding="utf-8"
    )


# --------------------------------------------------
# Run MCP Server
# --------------------------------------------------

if __name__ == "__main__":

    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000
    )