"""AI Agent service — Gemini-powered recommendation assistant for CompanyFinder."""

import logging
from typing import Optional
from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.listing import Listing
from app.models.user import User, AgentProfile

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """\
You are CompanyFinder AI, a smart business acquisition assistant for the CompanyFinder marketplace.
You help buyers find businesses for sale in Albania and the UAE.

Your capabilities:
- Search and filter business listings by country, category, city, price range, and ROI
- Get detailed information about specific listings
- Provide market overview (available countries, cities, categories)
- Compare listings and make recommendations based on buyer preferences

Guidelines:
- Always use the tools to get real data. Never make up listings or prices.
- When the user asks about businesses, search first, then present results conversationally.
- If the user doesn't specify a country, ask them (Albania or UAE).
- Present prices in EUR. Include ROI when available.
- Be concise but helpful. Highlight key selling points.
- If no results match, suggest broadening the search criteria.
- You can compare multiple listings when asked.
- Respond in the user's language.

Available countries: Albania (al), United Arab Emirates (ae)
Categories: restaurant, bar, cafe, retail, hotel, manufacturing, services, technology, healthcare, education, real-estate, other
"""

# Tool function declarations for Gemini
TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="search_listings",
        description="Search for businesses for sale on CompanyFinder marketplace. Returns a list of matching listings with key details.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "country_code": {
                    "type": "string",
                    "description": "Country code: 'al' (Albania) or 'ae' (UAE). Required.",
                    "enum": ["al", "ae"],
                },
                "category": {
                    "type": "string",
                    "description": "Business category filter.",
                    "enum": ["restaurant", "bar", "cafe", "retail", "hotel", "manufacturing", "services", "technology", "healthcare", "education", "real-estate", "other"],
                },
                "city": {
                    "type": "string",
                    "description": "City filter. Albania: Tirana, Durres, Vlore, etc. UAE: Dubai, Abu Dhabi, Sharjah, etc.",
                },
                "min_price_eur": {
                    "type": "number",
                    "description": "Minimum asking price in EUR.",
                },
                "max_price_eur": {
                    "type": "number",
                    "description": "Maximum asking price in EUR.",
                },
                "min_roi": {
                    "type": "number",
                    "description": "Minimum ROI percentage.",
                },
                "search": {
                    "type": "string",
                    "description": "Free-text search across title, description, category, city.",
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort order.",
                    "enum": ["newest", "price_low", "price_high", "roi_high", "roi_low"],
                },
            },
            "required": ["country_code"],
        },
    ),
    types.FunctionDeclaration(
        name="get_listing_detail",
        description="Get detailed information about a specific business listing by its ID.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "listing_id": {
                    "type": "string",
                    "description": "The listing UUID.",
                },
            },
            "required": ["listing_id"],
        },
    ),
    types.FunctionDeclaration(
        name="get_market_info",
        description="Get available countries, cities, categories, and market overview. Use this to discover what's available before searching.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "country_code": {
                    "type": "string",
                    "description": "Optional. 'al' or 'ae' to get info for a specific country.",
                    "enum": ["al", "ae"],
                },
            },
        },
    ),
]

TOOLS = [types.Tool(function_declarations=TOOL_DECLARATIONS)]

# Static market data
MARKET_DATA = {
    "al": {
        "name": "Albania",
        "cities": ["Tirana", "Durres", "Vlore", "Shkoder", "Elbasan", "Fier", "Korce", "Berat", "Sarande", "Lushnje"],
    },
    "ae": {
        "name": "United Arab Emirates",
        "cities": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Umm Al Quwain", "Fujairah"],
    },
}
CATEGORIES = ["restaurant", "bar", "cafe", "retail", "hotel", "manufacturing", "services", "technology", "healthcare", "education", "real-estate", "other"]


def _get_client() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


async def _execute_search_listings(db: AsyncSession, args: dict) -> dict:
    """Execute search_listings tool against the database."""
    from sqlalchemy import desc, asc

    country_code = args.get("country_code", "al")
    category = args.get("category")
    city = args.get("city")
    min_price = args.get("min_price_eur")
    max_price = args.get("max_price_eur")
    min_roi = args.get("min_roi")
    search = args.get("search")
    sort_by = args.get("sort_by", "newest")

    query = (
        select(Listing, User)
        .join(User, Listing.agent_id == User.id)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .options(selectinload(User.agent_profile), selectinload(Listing.images))
        .where(
            and_(
                Listing.country_code == country_code,
                Listing.status == "active",
                AgentProfile.verification_status == "approved",
            )
        )
    )

    if category:
        query = query.where(Listing.category == category)
    if city:
        query = query.where(Listing.public_location_city_en.ilike(f"%{city}%"))
    if min_price:
        query = query.where(Listing.asking_price_eur >= min_price)
    if max_price:
        query = query.where(Listing.asking_price_eur <= max_price)
    if min_roi:
        query = query.where(Listing.roi >= min_roi)
    if search:
        term = f"%{search}%"
        from sqlalchemy import or_
        query = query.where(
            or_(
                Listing.public_title_en.ilike(term),
                Listing.public_description_en.ilike(term),
                Listing.category.ilike(term),
                Listing.public_location_city_en.ilike(term),
            )
        )

    sort_map = {
        "newest": desc(Listing.created_at),
        "price_low": asc(Listing.asking_price_eur),
        "price_high": desc(Listing.asking_price_eur),
        "roi_high": desc(Listing.roi),
        "roi_low": asc(Listing.roi),
    }
    query = query.order_by(sort_map.get(sort_by, desc(Listing.created_at)))
    query = query.limit(10)

    result = await db.execute(query)
    rows = result.all()

    listings = []
    for listing, agent in rows:
        # Get first image URL for card display
        first_image = None
        if listing.images:
            sorted_imgs = sorted(listing.images, key=lambda i: i.order)
            first_image = sorted_imgs[0].url if sorted_imgs else None

        item = {
            "id": str(listing.id),
            "title": listing.public_title_en,
            "category": listing.category,
            "city": listing.public_location_city_en,
            "area": listing.public_location_area,
            "country_code": country_code,
            "asking_price_eur": float(listing.asking_price_eur) if listing.asking_price_eur else None,
            "monthly_revenue_eur": float(listing.monthly_revenue_eur) if listing.monthly_revenue_eur else None,
            "roi": float(listing.roi) if listing.roi else None,
            "employee_count": listing.employee_count,
            "years_in_operation": listing.years_in_operation,
            "promotion_tier": listing.promotion_tier,
            "image_url": first_image,
            "agent_name": agent.name,
            "agent_agency": agent.company_name,
            "url": f"{settings.APP_URL}/{country_code}/listings/{listing.id}",
        }
        listings.append(item)

    return {"total": len(listings), "listings": listings}


async def _execute_get_listing_detail(db: AsyncSession, args: dict) -> dict:
    """Execute get_listing_detail tool against the database."""
    listing_id = args.get("listing_id")
    if not listing_id:
        return {"error": "listing_id is required"}

    result = await db.execute(
        select(Listing, User)
        .join(User, Listing.agent_id == User.id)
        .options(
            selectinload(Listing.images),
            selectinload(User.agent_profile),
        )
        .where(Listing.id == listing_id)
    )
    row = result.first()
    if not row:
        return {"error": "Listing not found"}

    listing, agent = row
    country_code = listing.country_code or "al"

    first_image = None
    if listing.images:
        sorted_imgs = sorted(listing.images, key=lambda i: i.order)
        first_image = sorted_imgs[0].url if sorted_imgs else None

    return {
        "id": str(listing.id),
        "title": listing.public_title_en,
        "description": listing.public_description_en,
        "category": listing.category,
        "city": listing.public_location_city_en,
        "area": listing.public_location_area,
        "country_code": country_code,
        "country": "Albania" if country_code == "al" else "United Arab Emirates",
        "status": listing.status,
        "asking_price_eur": float(listing.asking_price_eur) if listing.asking_price_eur else None,
        "monthly_revenue_eur": float(listing.monthly_revenue_eur) if listing.monthly_revenue_eur else None,
        "annual_revenue_eur": float(listing.monthly_revenue_eur) * 12 if listing.monthly_revenue_eur else None,
        "roi": float(listing.roi) if listing.roi else None,
        "employee_count": listing.employee_count,
        "years_in_operation": listing.years_in_operation,
        "is_physically_verified": listing.is_physically_verified,
        "promotion_tier": listing.promotion_tier,
        "view_count": listing.view_count,
        "image_url": first_image,
        "images": len(listing.images) if listing.images else 0,
        "agent_name": agent.name,
        "agent_agency": agent.company_name,
        "agent_phone": agent.phone_number,
        "agent_whatsapp": agent.agent_profile.whatsapp_number if agent.agent_profile else None,
        "agent_email": agent.email,
        "url": f"{settings.APP_URL}/{country_code}/listings/{listing.id}",
    }


def _execute_get_market_info(args: dict) -> dict:
    """Execute get_market_info tool (static data, no DB needed)."""
    country_code = args.get("country_code")
    if country_code and country_code in MARKET_DATA:
        return {
            "country": MARKET_DATA[country_code],
            "categories": CATEGORIES,
        }
    return {
        "countries": MARKET_DATA,
        "categories": CATEGORIES,
    }


async def execute_tool(db: AsyncSession, name: str, args: dict) -> dict:
    """Route a tool call to the correct handler."""
    if name == "search_listings":
        return await _execute_search_listings(db, args)
    elif name == "get_listing_detail":
        return await _execute_get_listing_detail(db, args)
    elif name == "get_market_info":
        return _execute_get_market_info(args)
    else:
        return {"error": f"Unknown tool: {name}"}


def build_history(messages: list) -> list[types.Content]:
    """Convert DB messages into Gemini Content objects for context."""
    history = []
    for msg in messages:
        if msg.role == "user":
            history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=msg.content)],
            ))
        elif msg.role == "model":
            history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=msg.content)],
            ))
    return history


async def chat(
    db: AsyncSession,
    user_message: str,
    conversation_messages: list,
    language: str = "en",
    user_context: Optional[dict] = None,
) -> tuple[str, Optional[list]]:
    """
    Send a message to the AI agent and get a response.

    Returns:
        tuple of (response_text, tool_calls_with_results)
    """
    client = _get_client()
    history = build_history(conversation_messages)

    history.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)],
    ))

    lang_instruction = f"\nThe user's preferred language is: {language}. Respond in that language." if language != "en" else ""

    # Inject user context so the AI knows who it's talking to
    context_instruction = ""
    if user_context:
        parts = []
        if user_context.get("country"):
            parts.append(f"- Preferred country: {user_context['country']}")
        if user_context.get("saved_listings"):
            titles = ", ".join(user_context["saved_listings"][:10])
            parts.append(f"- Saved/favorited listings: {titles}")
        if parts:
            context_instruction = "\n\nAbout this buyer:\n" + "\n".join(parts) + "\nUse this context to personalize your recommendations. If the user doesn't specify a country, default to their preferred country."

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION + lang_instruction + context_instruction,
        tools=TOOLS,
        temperature=0.7,
        max_output_tokens=2048,
    )

    all_tool_calls = []

    for _ in range(5):
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=history,
            config=config,
        )

        candidate = response.candidates[0] if response.candidates else None
        if not candidate:
            return "I'm sorry, I couldn't process that request. Please try again.", None

        function_calls = []
        text_parts = []
        for part in candidate.content.parts:
            if part.function_call:
                function_calls.append(part.function_call)
            if part.text:
                text_parts.append(part.text)

        if not function_calls:
            final_text = "".join(text_parts) if text_parts else "I couldn't generate a response. Please try again."
            return final_text, all_tool_calls if all_tool_calls else None

        history.append(candidate.content)

        function_response_parts = []
        for fc in function_calls:
            tool_args = dict(fc.args) if fc.args else {}

            logger.info(f"Agent tool call: {fc.name}({tool_args})")
            result = await execute_tool(db, fc.name, tool_args)

            # Store both args and results so the frontend can render listing cards
            all_tool_calls.append({
                "name": fc.name,
                "args": tool_args,
                "result": result,
            })

            function_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response=result,
                )
            )

        history.append(types.Content(
            role="tool",
            parts=function_response_parts,
        ))

    return "I ran into an issue processing your request. Could you try rephrasing?", all_tool_calls
