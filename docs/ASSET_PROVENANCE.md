# Image and font provenance

The built-in `image_gen` tool was used for three new project-bound raster images.
No CLI/API-key fallback was used. Generated PNG sources were copied into the
workspace and retained; Pillow encodes equivalent WebP delivery files without
changing their composition. These are concept/editorial images, not evidence of
actual inventory or laboratory authenticity. Packaging imagery is used only for
the clearly marked demo catalog. Live inventory requires actual product images.

## Saved assets and final prompts

1. Source `assets/source-images/jahantab-editorial.png`; delivery
   `static/images/jahantab-editorial.webp` (233,772 bytes).

   > Use case: photorealistic-natural. Create a premium editorial still life photograph for an Iranian saffron boutique website named Jahantab. Horizontal 3:2 composition. Warm ivory travertine table, a shallow handmade cream ceramic bowl brimming with fine crimson saffron strands in the lower center-right, a few delicate purple saffron crocus blossoms with orange-red stigmas on the table at left, one small clear glass vessel of golden saffron infusion at back right, fine scattered strands. Rich natural textile shadows and soft afternoon sunlight from the upper left, warm beige and wine-red accents, tactility, refined Iranian craft aesthetic, subtle film grain, expensive food magazine photography, beautifully restrained composition, no people, no text, no lettering, no label, no logos, no fake packaging or authenticity certificates. Art-direction image only, not a photograph of a specific sale item. Fill the frame, close-up with elegant negative space at top left. Output landscape image for website hero.

2. Source `assets/source-images/demo-jar.png`; delivery
   `static/images/demo-jar.webp` (202,492 bytes).

   > Use case product-mockup. One beautiful premium catalog photograph of saffron in a small clear cylindrical glass jar with a simple brushed brass lid, filled with vivid deep crimson saffron threads, beside a few loose strands and one delicate purple crocus blossom. Soft warm ivory studio backdrop and travertine plinth, natural window light with gentle long shadows. Refined Iranian artisanal food boutique, minimalist still life, tactile, authentic materials. Straight-on 3/4 view, product occupies central 65% of a square frame, generous breathing room, elegant calm warm cream and wine red color palette. No words, no text, no labels, no logos, no certificates. This is a conceptual demonstration packaging photo, not evidence of an actual product.

3. Source `assets/source-images/demo-box.png`; delivery
   `static/images/demo-box.webp` (294,164 bytes).

   > Use case product-mockup. Premium saffron boutique catalog photograph. A small round ivory ceramic bowl overflowing with fine dark red saffron threads, next to a warm walnut wood rectangular open presentation box holding a tiny clear glass saffron container, one purple crocus petal and delicate scattered crimson strands. Pale ivory linen and warm beige background, natural diffuse daylight, clean quiet luxurious Iranian food craft aesthetic, honest texture, carefully styled but not overly ornate. Square photo, main objects centered and completely visible, 70% frame occupancy, plenty of margin. Natural earthy wine red, ivory and walnut tones. No printed text, labels, logos or authenticity documents. Conceptual demonstration product image.

## Persian typography

`static/fonts/Vazirmatn-Variable.woff2` is the original Vazirmatn v33.003 variable
webfont (111,152 bytes), by the Vazirmatn Project Authors. It is licensed under
SIL Open Font License 1.1; the complete upstream copyright/license is preserved
in `static/fonts/OFL.txt`. Source:
[Vazirmatn v33.003](https://github.com/rastikerdar/vazirmatn/tree/v33.003).

The font is self-hosted and preloaded with `font-display: swap`. The storefront's
type scale, weights, spacing and wordmark treatment were customized for Jahantab;
the glyph family itself was not designed from scratch or misrepresented as a new
proprietary font. Icons and the crocus brand mark are code-native SVG assets.
