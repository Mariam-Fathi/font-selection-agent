# Font Selection Agent

An AI-powered assistant that helps you find the perfect font for your design projects by automatically searching fonts, taking screenshots, and providing visual comparisons.

## What It Does

The Font Selection Agent automates the font selection process:
1. **Asks for your file path**
2. **Shows font category options** (Handwriting, Serif, Sans-serif, Display, Monospace)
3. **Searches for matching fonts** from a curated list of 40 Google Fonts
4. **Takes screenshots automatically** of your design with different fonts
5. **Provides recommendations** with visual comparisons

## Features

- **User-Friendly Interface**: Simple step-by-step workflow
- **40 Curated Fonts**: Handpicked Google Fonts across 5 categories
- **Automatic Screenshots**: See fonts in your actual design context
- **Visual Comparison**: Side-by-side screenshots for easy decision-making
- **Safe Operations**: Automatically restores your original file

## Quick Start

### Prerequisites

- Python 3.9+
- Google ADK
- Google API Key (get from [Google AI Studio](https://aistudio.google.com/apikey))
- Playwright (for screenshots)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Mariam-Fathi/font-selection-agent.git
   cd font-selection-agent
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium
   ```

3. **Set up API key**
   Create a `.env` file in the project root:
   ```
   GOOGLE_API_KEY=your_google_api_key_here
   ```

### Usage

1. **Run the agent**
   ```bash
   python agent.py
   ```

2. **Follow the prompts**
   - Provide your HTML file path (e.g., `test-design.html`)
   - Choose a font category (1-5)
   - Wait for screenshots to be generated

3. **View results**
   - Screenshots are saved in `previews/screenshots/`
   - Open the images to compare fonts

## Available Font Categories

- **Handwriting** (14 fonts): Casual, script, handwritten styles
- **Serif** (8 fonts): Classic, traditional fonts with serifs
- **Sans-serif** (8 fonts): Modern, clean fonts without serifs
- **Display** (6 fonts): Bold, attention-grabbing fonts
- **Monospace** (4 fonts): Fixed-width fonts, great for code

## Example Usage

```
You: I want to test fonts

Agent: What is the path to your HTML file? (e.g., 'test-design.html')

You: test-design.html

Agent: Great! Now choose a font category:
       1. Handwriting (14 fonts) - Casual, script, handwritten styles
       2. Serif (8 fonts) - Classic, traditional fonts with serifs
       3. Sans-serif (8 fonts) - Modern, clean fonts without serifs
       4. Display (6 fonts) - Bold, attention-grabbing fonts
       5. Monospace (4 fonts) - Fixed-width fonts, great for code

You: 1

[Agent searches fonts, takes screenshots, and shows results]
```

## How It Works

1. **Font Search**: Searches curated list of 40 Google Fonts by category
2. **File Modification**: Temporarily modifies your HTML file to use different fonts
3. **Screenshot Capture**: Uses Playwright to take screenshots via local HTTP server
4. **File Restoration**: Automatically restores your original file
5. **Results**: Saves screenshots for visual comparison

## Requirements

- `google-adk>=0.1.0`
- `google-genai>=0.2.0`
- `requests>=2.31.0`
- `python-dotenv>=1.0.0`
- `playwright>=1.40.0`


