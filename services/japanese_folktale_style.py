"""Built-in visual direction for Japanese folktales."""

STYLE_KEY = "jidaigeki_cel"
STYLE_PROMPT = (
    "Japanese Jidaigeki Anime Style (時代劇アニメ風), traditional hand-drawn 2D cel animation "
    "(セル画風) with the serious yet warm storytelling of classic 1990s–2000s historical anime, "
    "classic Takahata films and World Masterpiece Theater. Crisp clean ink outlines, "
    "well-defined detailed line art with consistent line width; matte flat cel shading, "
    "restrained hard-edged shadows and minimal gradients. Limited subdued natural palette: "
    "indigo, umber, cream, muted wood and earth tones. Realistic human anatomy, adults around "
    "6–7 heads tall, age-appropriate child proportions, expressive but subdued faces, "
    "visible natural wrinkles on elders. Historically accurate Japanese clothing, hakama "
    "or yukata appropriate to the scene, traditional hairstyles and period props. Detailed "
    "Edo or Sengoku villages appropriate to the story's era: thatched roofs, wooden houses, "
    "bamboo fences, tatami and shoji screens; carefully illustrated foliage without photorealism. "
    "Warm paper-lantern or candle lighting for interior/night scenes, gentle natural daylight "
    "outdoors; calm readable compositions and a dignified nostalgic mood for senior audiences. "
    "Avoid 3D render, photorealistic imagery, glossy modern digital anime, crayon texture, "
    "soft watercolor bleeding, oversaturated or neon colors, complex gradient shading, "
    "chibi, childish cartoon proportions, heavy digital effects, captions and logos."
)


def category_style(category: str, configured: str = "") -> str:
    configured = str(configured or "").strip()
    if category == "日本昔話" and configured.lower() in {"", "realistic", "cinematic"}:
        return STYLE_KEY
    return configured or "realistic"
