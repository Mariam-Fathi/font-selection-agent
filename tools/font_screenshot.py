"""General font screenshot tool - works with any HTML file"""

import os
import shutil
import subprocess
import time
import sys
import http.server
import socketserver
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path
from google.adk.tools import ToolContext


def take_font_screenshots(
    font_names: List[str],
    file_path: str,
    text: str = "Sample Text",
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """
    Take screenshots of an HTML file with different fonts applied.
    
    This is a general-purpose tool that works with any HTML file.
    It modifies the HTML file to use different fonts and takes screenshots.
    
    Args:
        font_names: List of font names to test (e.g., ["Comforter Brush", "Dancing Script"])
        file_path: Path to the HTML file (e.g., "test-design.html" or full path)
        text: Text content to display (default: "Sample Text")
        tool_context: Tool context (automatically provided by ADK)
    
    Returns:
        Dictionary with screenshot information:
        {
            "status": "success",
            "font_names": ["Comforter Brush", "Dancing Script"],
            "screenshots": [
                {
                    "font": "Comforter Brush",
                    "path": "previews/screenshots/comforter_brush.png"
                }
            ],
            "screenshots_folder": "previews/screenshots"
        }
    
    Example:
        take_font_screenshots(
            font_names=["Comforter Brush", "Dancing Script", "Caveat"],
            file_path="test-design.html",
            text="Sample Text"
        )
    """
    try:
        # Resolve file path (can be relative or absolute)
        file_path_obj = Path(file_path)
        if not file_path_obj.is_absolute():
            # If relative, assume it's in the project root
            file_path_obj = Path.cwd() / file_path
        
        if not file_path_obj.exists():
            return {
                "status": "error",
                "message": f"File not found at {file_path_obj}. Please check the file_path parameter.",
                "font_names": font_names
            }
        
        # Create screenshots directory
        screenshots_dir = Path("previews") / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Read original file
        with open(file_path_obj, "r", encoding="utf-8") as f:
            original_content = f.read()
        
        screenshots = []
        
        # Start a simple HTTP server to serve the HTML file
        port = 8000
        server_thread = _start_local_server(file_path_obj.parent, port)
        time.sleep(1)  # Give server time to start
        
        # Process each font
        for font_name in font_names:
            try:
                # Modify file with new font
                modified_content = _replace_font_in_html(original_content, font_name, text)
                
                # Write modified version
                with open(file_path_obj, "w", encoding="utf-8") as f:
                    f.write(modified_content)
                
                # Wait a moment for file to be written
                time.sleep(0.5)
                
                # Take screenshot
                screenshot_path = screenshots_dir / f"{font_name.lower().replace(' ', '_')}.png"
                
                sys.stdout.write(f"Taking screenshot with {font_name}...\n")
                sys.stdout.flush()
                
                screenshot_result = _take_screenshot(f"http://localhost:{port}/{file_path_obj.name}", str(screenshot_path), font_name)
                
                if screenshot_result.get("success"):
                    if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
                        screenshots.append({
                            "font": font_name,
                            "path": str(screenshot_path),
                            "url": f"file:///{screenshot_path.absolute()}"
                        })
                        sys.stdout.write(f"[OK] Screenshot saved: {screenshot_path.name}\n")
                        sys.stdout.flush()
                    else:
                        screenshots.append({
                            "font": font_name,
                            "path": "error",
                            "error": "Screenshot file was not created or is empty"
                        })
                        sys.stdout.write(f"[ERROR] Screenshot failed\n")
                        sys.stdout.flush()
                else:
                    screenshots.append({
                        "font": font_name,
                        "path": "error",
                        "error": screenshot_result.get("message", "Unknown error")
                    })
                    sys.stdout.write(f"[ERROR] Screenshot failed: {screenshot_result.get('message', 'Unknown error')}\n")
                    sys.stdout.flush()
                
                # Restore original file
                with open(file_path_obj, "w", encoding="utf-8") as f:
                    f.write(original_content)
                
                time.sleep(0.3)
                
            except Exception as e:
                # Restore original file on error
                try:
                    with open(file_path_obj, "w", encoding="utf-8") as f:
                        f.write(original_content)
                except:
                    pass
                
                screenshots.append({
                    "font": font_name,
                    "path": "error",
                    "error": str(e)
                })
        
        # Count successful screenshots
        successful_screenshots = [s for s in screenshots if s.get("path") and s.get("path") != "error" and Path(s.get("path")).exists()]
        
        # Build summary message
        if successful_screenshots:
            screenshot_list = "\n".join([f"  - {s['font']}: {Path(s['path']).name}" for s in successful_screenshots])
            message = f"Successfully captured {len(successful_screenshots)}/{len(font_names)} screenshots:\n{screenshot_list}\n\nScreenshots saved to: {screenshots_dir}\nOpen these images to compare fonts!"
        else:
            message = f"WARNING: No screenshots were captured. Check the errors above. Screenshots folder: {screenshots_dir}"
        
        return {
            "status": "success" if successful_screenshots else "partial",
            "font_names": font_names,
            "text": text,
            "file_path": str(file_path_obj),
            "screenshots": screenshots,
            "screenshots_folder": str(screenshots_dir),
            "successful_count": len(successful_screenshots),
            "total_count": len(font_names),
            "message": message
        }
        
    except Exception as e:
        # Try to restore original file
        try:
            if 'original_content' in locals() and 'file_path_obj' in locals():
                with open(file_path_obj, "w", encoding="utf-8") as f:
                    f.write(original_content)
        except:
            pass
        
        return {
            "status": "error",
            "message": f"Error taking screenshots: {str(e)}",
            "font_names": font_names
        }


def _start_local_server(directory: Path, port: int) -> threading.Thread:
    """Start a local HTTP server in a separate thread"""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
    
    def run_server():
        with socketserver.TCPServer(("", port), Handler) as httpd:
            httpd.serve_forever()
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread


def _replace_font_in_html(content: str, font_name: str, text: str) -> str:
    """Replace font in HTML file - works with various font declaration patterns"""
    import re
    
    # Add Google Fonts import for the font
    font_family_encoded = font_name.replace(" ", "+")
    font_import = f'<link href="https://fonts.googleapis.com/css2?family={font_family_encoded}:wght@400&display=swap" rel="stylesheet">'
    
    # Check if Google Fonts preconnect exists, add import after it
    if 'fonts.googleapis.com' in content and font_import not in content:
        # Insert font import after existing Google Fonts links
        content = content.replace(
            '</head>',
            f'    {font_import}\n</head>'
        )
    elif 'fonts.googleapis.com' not in content:
        # Add preconnect and font import if not present
        preconnect = '''    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    ''' + font_import + '\n'
        content = content.replace('</head>', preconnect + '</head>')
    
    # Pattern 1: Match font-family in .title class (most specific)
    # Matches: font-family: 'Arial', sans-serif;
    pattern1 = r'(\.title\s*\{[^}]*font-family:\s*)([^;]+)(;)'
    replacement1 = f'\\1"{font_name}", cursive\\3'
    modified = re.sub(pattern1, replacement1, content, flags=re.IGNORECASE | re.DOTALL)
    
    # Pattern 2: Match any font-family in CSS
    pattern2 = r"(font-family:\s*)(['\"]?)([^;'\"]+)(['\"]?\s*,\s*(?:sans-serif|serif|cursive|monospace))"
    replacement2 = f'\\1"{font_name}", cursive'
    modified = re.sub(pattern2, replacement2, modified, flags=re.IGNORECASE)
    
    # Pattern 3: Update text content if it matches the default
    if "Sample Text" in modified:
        modified = modified.replace("Sample Text", text)
    
    return modified


async def _take_screenshot_async(url: str, screenshot_path: str, font_name: str) -> Dict[str, Any]:
    """Take screenshot using Playwright async API"""
    try:
        from playwright.async_api import async_playwright
        
        screenshot_path_obj = Path(screenshot_path)
        screenshot_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                # Navigate to the HTML file
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Wait for fonts to load
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(2000)  # Extra time for font rendering
                
                # Take full page screenshot
                await page.screenshot(path=str(screenshot_path), full_page=True)
                
                # Verify screenshot was created
                if not screenshot_path_obj.exists():
                    raise Exception("Screenshot file was not created")
                
                if screenshot_path_obj.stat().st_size == 0:
                    raise Exception("Screenshot file is empty")
                
            finally:
                await browser.close()
        
        return {
            "success": True,
            "path": str(screenshot_path)
        }
        
    except ImportError:
        return {
            "success": False,
            "message": "Playwright not installed. Install with: pip install playwright && python -m playwright install chromium"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Screenshot failed: {str(e)}"
        }


def _take_screenshot(url: str, screenshot_path: str, font_name: str) -> Dict[str, Any]:
    """Take screenshot - wrapper that handles async/sync contexts"""
    import asyncio
    
    # Check if we're in an async context
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, use async version
        # Run in a new thread to avoid blocking
        import concurrent.futures
        import threading
        
        result = None
        exception = None
        
        def run_async():
            nonlocal result, exception
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(
                    _take_screenshot_async(url, screenshot_path, font_name)
                )
                new_loop.close()
            except Exception as e:
                exception = e
        
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=60)  # 60 second timeout
        
        if exception:
            raise exception
        
        if result is None:
            return {
                "success": False,
                "message": "Screenshot operation timed out or failed"
            }
        
        return result
        
    except RuntimeError:
        # No running event loop, use sync API
        try:
            from playwright.sync_api import sync_playwright
            
            screenshot_path_obj = Path(screenshot_path)
            screenshot_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                try:
                    # Navigate to the HTML file
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    # Wait for fonts to load
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(2000)  # Extra time for font rendering
                    
                    # Take full page screenshot
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    
                    # Verify screenshot was created
                    if not screenshot_path_obj.exists():
                        raise Exception("Screenshot file was not created")
                    
                    if screenshot_path_obj.stat().st_size == 0:
                        raise Exception("Screenshot file is empty")
                    
                finally:
                    browser.close()
            
            return {
                "success": True,
                "path": str(screenshot_path)
            }
            
        except ImportError:
            return {
                "success": False,
                "message": "Playwright not installed. Install with: pip install playwright && python -m playwright install chromium"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Screenshot failed: {str(e)}"
            }

