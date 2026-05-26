"""Tool to inject or update French translations inside a ZIP file."""
from __future__ import annotations

import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

def inject_translation_to_zip(zip_path: Path, fr_text: str) -> bool:
    """Read a ZIP, update its modDesc.xml with <fr> tags, and write back.
    
    This target the <title> and <description> tags under <modDesc>.
    Returns True if updated.
    """
    if not zip_path.is_file():
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_zip = Path(tmpdir) / "output.zip"
        
        updated = False
        with zipfile.ZipFile(zip_path, 'r') as zin:
            with zipfile.ZipFile(tmp_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    content = zin.read(item.filename)
                    
                    if item.filename.lower() == "moddesc.xml":
                        new_content = _update_moddesc_xml(content, fr_text)
                        if new_content != content:
                            updated = True
                            zout.writestr(item.filename, new_content)
                            continue
                    
                    zout.writestr(item, content)
        
        if updated:
            # Atomic replace (as much as possible)
            tmp_zip.replace(zip_path)
            return True
            
    return False

def _update_moddesc_xml(raw_bytes: bytes, fr_text: str) -> bytes:
    """Parse modDesc and inject <fr> tags into <title> and <description>."""
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes # Safety

    # We use regex to preserve comments and formatting as much as possible
    # though injecting new tags is always a bit invasive.
    
    # 1. Update Title
    # Try to find <title> ... </title>
    title_match = re.search(r'(<title>)(.*?)(</title>)', text, re.DOTALL | re.IGNORECASE)
    if title_match:
        inner = title_match.group(2)
        if '<fr>' not in inner.lower():
            # Inject <fr> before </title> or after the last tag
            # For simplicity, we just append it inside <title>
            new_title = f"{title_match.group(1)}{inner}\n        <fr>{fr_text}</fr>{title_match.group(3)}"
            text = text.replace(title_match.group(0), new_title)

    # 2. Update Description
    desc_match = re.search(r'(<description>)(.*?)(</description>)', text, re.DOTALL | re.IGNORECASE)
    if desc_match:
        inner = desc_match.group(2)
        if '<fr>' not in inner.lower():
            new_desc = f"{desc_match.group(1)}{inner}\n        <fr>{fr_text}</fr>{desc_match.group(3)}"
            text = text.replace(desc_match.group(0), new_desc)

    return text.encode("utf-8")
