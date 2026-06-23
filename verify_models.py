"""
verify_models.py  --  Validate connectivity to all three Vertex AI models
===========================================================================
Tests the model names from .env and reports pass/fail for each.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from stickman_studio.config import settings, init_vertex
init_vertex()

PASS = 0; FAIL = 0

def test_gemini(name: str):
    global PASS, FAIL
    print(f"GEMINI  {name} ... ", end="")
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        resp = client.models.generate_content(
            model=name,
            contents="Write one word: hello",
            config=types.GenerateContentConfig(
                temperature=0.1, max_output_tokens=16,
            ),
        )
        print(f"OK ({resp.text.strip()[:60]})")
        PASS += 1
    except Exception as e:
        msg = str(e).replace("\n", " ")[:120]
        if "not found" in msg.lower() or "not have access" in msg.lower():
            print("NOT AVAILABLE")
        else:
            print(f"ERROR  {msg}")
        FAIL += 1

def test_imagen(name: str):
    global PASS, FAIL
    print(f"IMAGEN  {name} ... ", end="")
    try:
        from vertexai.preview.vision_models import ImageGenerationModel
        model = ImageGenerationModel.from_pretrained(name)
        images = model.generate_images(
            prompt="a simple stickman",
            number_of_images=1,
            aspect_ratio="16:9",
            add_watermark=False,
        )
        if images and images[0]:
            print("OK")
            PASS += 1
        else:
            print("EMPTY RESULT")
            FAIL += 1
    except Exception as e:
        msg = str(e).replace("\n", " ")[:120]
        if "not found" in msg.lower() or "not have access" in msg.lower():
            print("NOT AVAILABLE")
        else:
            print(f"ERROR  {msg}")
        FAIL += 1

def test_veo(name: str):
    global PASS, FAIL
    print(f"VEO     {name} ... ", end="")
    try:
        from google import genai
        from google.genai import types
        from PIL import Image
        from pathlib import Path

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        tmp = Path("_veo_test.png")
        Image.new("RGB", (64, 64), (255, 255, 255)).save(str(tmp))
        try:
            image = types.Image.from_file(location=str(tmp))
            config = types.GenerateVideosConfig(
                aspect_ratio="16:9", number_of_videos=1,
                duration_seconds=4, person_generation="allow_adult",
            )
            op = client.models.generate_videos(
                model=name, prompt="subtle motion",
                image=image, config=config,
            )
            if op and op.name:
                print("OK (job accepted)")
                PASS += 1
        finally:
            if tmp.exists():
                tmp.unlink()
    except Exception as e:
        msg = str(e).replace("\n", " ")[:120]
        if "not found" in msg.lower() or "not have access" in msg.lower():
            print("NOT AVAILABLE")
        else:
            print(f"ERROR  {msg}")
        FAIL += 1


print("=" * 50)
print("Vertex AI Model Verification")
print(f"Project: {settings.gcp_project_id}")
print(f"Region:  {settings.gcp_location}")
print("=" * 50)

test_gemini(settings.gemini_model)
test_imagen(settings.imagen_generate_model)
test_veo(settings.veo_model)

print("=" * 50)
print(f"  {PASS} passed, {FAIL} failed")
print("=" * 50)

if FAIL > 0:
    sys.exit(1)
