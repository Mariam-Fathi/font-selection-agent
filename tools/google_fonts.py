"""Google Fonts API integration for font search"""

import requests
from typing import Dict, List, Optional, Any
from google.adk.tools import ToolContext


def search_google_fonts(
    query: str,
    category: Optional[str] = None,
    style: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """
    Search Google Fonts for fonts matching the query.
    
    This tool searches the Google Fonts directory for fonts that match
    your search criteria. It's perfect for finding handwritten, script,
    or display fonts for design projects.
    
    Args:
        query: Search query (e.g., "handwritten", "script", "casual")
        category: Optional category filter. Options:
            - "handwriting" - Handwritten/script fonts
            - "display" - Display fonts (headings, titles)
            - "serif" - Serif fonts
            - "sans-serif" - Sans-serif fonts
            - "monospace" - Monospace fonts
        style: Optional style filter (e.g., "casual", "formal", "playful")
        tool_context: Tool context (automatically provided by ADK)
    
    Returns:
        Dictionary with search results:
        {
            "status": "success",
            "count": 5,
            "fonts": [
                {
                    "name": "Comforter Brush",
                    "category": "handwriting",
                    "family": "Comforter Brush",
                    "variants": ["400"],
                    "subsets": ["latin", "latin-ext"],
                    "files": {
                        "400": "https://fonts.gstatic.com/..."
                    },
                    "description": "A casual handwritten font..."
                }
            ]
        }
    
    Example:
        search_google_fonts(
            query="handwritten",
            category="handwriting",
            style="casual"
        )
    """
    try:
        # For MVP: Use a curated list of popular Google Fonts
        # This avoids API key requirements and is more reliable
        curated_fonts = [
            # Handwriting fonts
            {"family": "Comforter Brush", "category": "handwriting", "variants": ["400"], "subsets": ["latin", "latin-ext"]},
            {"family": "Dancing Script", "category": "handwriting", "variants": ["400", "500", "600", "700"], "subsets": ["latin", "latin-ext", "vietnamese"]},
            {"family": "Caveat", "category": "handwriting", "variants": ["400", "500", "600", "700"], "subsets": ["latin", "latin-ext", "cyrillic"]},
            {"family": "Kalam", "category": "handwriting", "variants": ["300", "400", "700"], "subsets": ["latin", "latin-ext", "devanagari"]},
            {"family": "Permanent Marker", "category": "handwriting", "variants": ["400"], "subsets": ["latin"]},
            {"family": "Indie Flower", "category": "handwriting", "variants": ["400"], "subsets": ["latin"]},
            {"family": "Shadows Into Light", "category": "handwriting", "variants": ["400"], "subsets": ["latin"]},
            {"family": "Satisfy", "category": "handwriting", "variants": ["400"], "subsets": ["latin"]},
            {"family": "Amatic SC", "category": "handwriting", "variants": ["400", "700"], "subsets": ["latin", "hebrew", "latin-ext"]},
            {"family": "Pacifico", "category": "handwriting", "variants": ["400"], "subsets": ["latin", "latin-ext", "cyrillic"]},
            {"family": "Shadows Into Light Two", "category": "handwriting", "variants": ["400"], "subsets": ["latin", "latin-ext"]},
            {"family": "Caveat Brush", "category": "handwriting", "variants": ["400"], "subsets": ["latin", "latin-ext"]},
            {"family": "Gloria Hallelujah", "category": "handwriting", "variants": ["400"], "subsets": ["latin"]},
            {"family": "Handlee", "category": "handwriting", "variants": ["400"], "subsets": ["latin"]},
            # Serif fonts
            {"family": "Playfair Display", "category": "serif", "variants": ["400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            {"family": "Merriweather", "category": "serif", "variants": ["300", "400", "700", "900"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            {"family": "Lora", "category": "serif", "variants": ["400", "500", "600", "700"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            {"family": "PT Serif", "category": "serif", "variants": ["400", "700"], "subsets": ["latin", "latin-ext", "cyrillic"]},
            {"family": "Crimson Text", "category": "serif", "variants": ["400", "600", "700"], "subsets": ["latin"]},
            {"family": "Libre Baskerville", "category": "serif", "variants": ["400", "700"], "subsets": ["latin", "latin-ext"]},
            {"family": "Source Serif Pro", "category": "serif", "variants": ["400", "600", "700"], "subsets": ["latin", "latin-ext"]},
            {"family": "Bitter", "category": "serif", "variants": ["100", "200", "300", "400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            # Sans-serif fonts
            {"family": "Roboto", "category": "sans-serif", "variants": ["100", "300", "400", "500", "700", "900"], "subsets": ["latin", "latin-ext", "cyrillic", "greek", "vietnamese"]},
            {"family": "Open Sans", "category": "sans-serif", "variants": ["300", "400", "500", "600", "700", "800"], "subsets": ["latin", "latin-ext", "cyrillic", "greek", "vietnamese"]},
            {"family": "Lato", "category": "sans-serif", "variants": ["100", "300", "400", "700", "900"], "subsets": ["latin", "latin-ext"]},
            {"family": "Montserrat", "category": "sans-serif", "variants": ["100", "200", "300", "400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            {"family": "Poppins", "category": "sans-serif", "variants": ["100", "200", "300", "400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext", "devanagari"]},
            {"family": "Raleway", "category": "sans-serif", "variants": ["100", "200", "300", "400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext"]},
            {"family": "Inter", "category": "sans-serif", "variants": ["100", "200", "300", "400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext", "cyrillic"]},
            {"family": "Nunito", "category": "sans-serif", "variants": ["200", "300", "400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            # Display fonts
            {"family": "Oswald", "category": "display", "variants": ["200", "300", "400", "500", "600", "700"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            {"family": "Bebas Neue", "category": "display", "variants": ["400"], "subsets": ["latin", "latin-ext"]},
            {"family": "Righteous", "category": "display", "variants": ["400"], "subsets": ["latin", "latin-ext"]},
            {"family": "Bangers", "category": "display", "variants": ["400"], "subsets": ["latin"]},
            {"family": "Fredoka One", "category": "display", "variants": ["400"], "subsets": ["latin", "latin-ext"]},
            {"family": "Lobster", "category": "display", "variants": ["400"], "subsets": ["latin", "latin-ext", "cyrillic", "vietnamese"]},
            # Monospace fonts
            {"family": "Roboto Mono", "category": "monospace", "variants": ["100", "200", "300", "400", "500", "600", "700"], "subsets": ["latin", "latin-ext", "cyrillic", "greek", "vietnamese"]},
            {"family": "Source Code Pro", "category": "monospace", "variants": ["200", "300", "400", "500", "600", "700", "800", "900"], "subsets": ["latin", "latin-ext", "cyrillic", "greek", "vietnamese"]},
            {"family": "Fira Code", "category": "monospace", "variants": ["300", "400", "500", "600", "700"], "subsets": ["latin", "latin-ext", "cyrillic"]},
            {"family": "Courier Prime", "category": "monospace", "variants": ["400", "700"], "subsets": ["latin", "latin-ext"]},
        ]
        
        all_fonts = curated_fonts
        
        # Filter fonts based on query and category
        query_lower = query.lower() if query else ""
        filtered_fonts = []
        
        # Map common query terms to categories
        query_to_category = {
            "handwriting": "handwriting",
            "handwritten": "handwriting",
            "script": "handwriting",
            "casual": "handwriting",
            "display": "display",
            "serif": "serif",
            "sans-serif": "sans-serif",
            "sans serif": "sans-serif",
            "monospace": "monospace",
            "mono": "monospace",
        }
        
        # If query maps to a category and no category specified, use it
        if query_lower in query_to_category and not category:
            category = query_to_category[query_lower]
        
        # Also normalize category if it's provided
        if category and category.lower() in query_to_category:
            category = query_to_category[category.lower()]
        
        for font in all_fonts:
            font_name = font.get("family", "").lower()
            font_category = font.get("category", "").lower()
            
            # Check if font matches query
            # If query is a category keyword, match by category
            matches_query = True
            if query:
                if query_lower in query_to_category:
                    # Query is a category keyword, will be handled by category match
                    # Don't filter by query name, just by category
                    matches_query = True
                else:
                    # Regular query - match in font name
                    matches_query = query_lower in font_name
            
            # Check category match (this is the main filter)
            matches_category = True
            if category:
                # Normalize category
                category_normalized = category.lower()
                if category_normalized in query_to_category:
                    category_normalized = query_to_category[category_normalized]
                matches_category = category_normalized == font_category
            
            # Additional filtering for style keywords
            matches_style = True
            if style:
                style_lower = style.lower()
                # Check in font name or category
                matches_style = (
                    style_lower in font_name or
                    style_lower in font_category
                )
            
            if matches_query and matches_category and matches_style:
                # Extract relevant font information
                font_info = {
                    "name": font.get("family", ""),
                    "category": font.get("category", ""),
                    "family": font.get("family", ""),
                    "variants": font.get("variants", []),
                    "subsets": font.get("subsets", []),
                    "files": {},  # Not needed for MVP
                    "description": f"{font.get('category', 'Unknown')} font - {font.get('family', 'Unknown')}",
                }
                filtered_fonts.append(font_info)
        
        # Limit results to top 20 for performance
        filtered_fonts = filtered_fonts[:20]
        
        return {
            "status": "success",
            "count": len(filtered_fonts),
            "query": query,
            "category": category,
            "fonts": filtered_fonts
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Network error: {str(e)}",
            "fonts": []
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "fonts": []
        }

