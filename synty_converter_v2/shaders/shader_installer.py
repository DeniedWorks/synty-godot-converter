"""Shader installation utility - downloads shaders from godotshaders.com."""

import re
import urllib.request
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Shader URLs from godotshaders.com
SHADER_URLS = {
    "polygon_shader.gdshader": "https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/",
    "foliage.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-foliage-shader/",
    "water.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-water-shader/",
    "refractive_transparent.gdshader": "https://godotshaders.com/shader/synty-refractive_transparent-crystal-shader/",
    "clouds.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-clouds-shader/",
    "sky_dome.gdshader": "https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader/",
    "particles_unlit.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit/",
    "biomes_tree.gdshader": "https://godotshaders.com/shader/synty-biomes-tree-compatible-shader/",
}


def fetch_shader_from_url(url: str) -> Optional[str]:
    """
    Fetch shader code from a godotshaders.com page.

    Note: This scrapes the page which may break if the site changes.
    Manual download is recommended.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode('utf-8')

        # Try to extract shader code from the page
        # godotshaders.com typically has the code in a <pre> or <code> block
        # This is a best-effort extraction

        # Look for shader code block
        patterns = [
            r'<code[^>]*class="[^"]*gdshader[^"]*"[^>]*>(.*?)</code>',
            r'<pre[^>]*class="[^"]*shader[^"]*"[^>]*>(.*?)</pre>',
            r'shader_type\s+\w+;.*?(?=</)',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                code = match.group(1) if match.lastindex else match.group(0)
                # Clean up HTML entities
                code = code.replace('&lt;', '<')
                code = code.replace('&gt;', '>')
                code = code.replace('&amp;', '&')
                code = code.replace('&quot;', '"')
                code = code.replace('&#39;', "'")
                # Remove HTML tags
                code = re.sub(r'<[^>]+>', '', code)
                return code.strip()

        logger.warning(f"Could not extract shader code from {url}")
        return None

    except Exception as e:
        logger.error(f"Failed to fetch shader from {url}: {e}")
        return None


def install_shaders(output_dir: Path, overwrite: bool = False) -> dict[str, bool]:
    """
    Install shaders to the specified directory.

    Args:
        output_dir: Directory to install shaders
        overwrite: If True, overwrite existing shaders

    Returns:
        Dict mapping shader name to success status
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    for shader_name, url in SHADER_URLS.items():
        output_path = output_dir / shader_name

        if output_path.exists() and not overwrite:
            logger.info(f"Shader already exists: {shader_name}")
            results[shader_name] = True
            continue

        logger.info(f"Downloading {shader_name} from {url}")
        shader_code = fetch_shader_from_url(url)

        if shader_code:
            output_path.write_text(shader_code, encoding='utf-8')
            logger.info(f"Installed: {shader_name}")
            results[shader_name] = True
        else:
            logger.warning(f"Failed to download {shader_name}")
            logger.info(f"Please download manually from: {url}")
            results[shader_name] = False

    return results


def create_placeholder_shaders(output_dir: Path):
    """Create placeholder shader files with instructions."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for shader_name, url in SHADER_URLS.items():
        output_path = output_dir / shader_name

        if output_path.exists():
            continue

        placeholder = f"""// PLACEHOLDER SHADER - {shader_name}
// Please download the actual shader from:
// {url}
//
// Instructions:
// 1. Visit the URL above
// 2. Copy the shader code
// 3. Replace this file's contents with the shader code
//
// This placeholder will cause errors until replaced.

shader_type spatial;

void fragment() {{
    ALBEDO = vec3(1.0, 0.0, 1.0); // Magenta = missing shader
}}
"""
        output_path.write_text(placeholder, encoding='utf-8')
        logger.info(f"Created placeholder: {shader_name}")


def print_shader_urls():
    """Print all shader download URLs for manual download."""
    print("\nSynty Shader Download URLs:")
    print("=" * 60)
    for shader_name, url in SHADER_URLS.items():
        print(f"\n{shader_name}:")
        print(f"  {url}")
    print("\n" + "=" * 60)
    print("Download each shader and save to: assets/shaders/synty/")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    else:
        output_dir = Path("./shaders")

    print(f"Installing shaders to: {output_dir}")
    results = install_shaders(output_dir)

    failed = [name for name, success in results.items() if not success]
    if failed:
        print(f"\nFailed to download {len(failed)} shaders:")
        for name in failed:
            print(f"  - {name}: {SHADER_URLS[name]}")
