# Design System Strategy: The Synthetic Atelier

## 1. Overview & Creative North Star
**Creative North Star: "The Digital Curator"**

This design system is not a utility; it is a high-end workspace. To move beyond the generic "SaaS dashboard" look, we adopt the persona of a high-end editorial studio. The experience should feel like a physical atelier—spacious, quiet, and intentional. 

We break the "template" look by rejecting rigid, boxy grids. Instead, we use **intentional asymmetry** and **tonal depth**. Elements do not just sit on a page; they are curated within a space. By leveraging high-contrast typography (the pairing of the technical *Inter* with the architectural *Manrope*) and overlapping glass layers, we create a sense of sophisticated AI power that feels premium rather than "tech-heavy."

---

## 2. Color & Surface Architecture
The palette is rooted in `background: #0b1326` (Deep Indigo). This is our "void" from which content emerges.

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders to define sections or cards. 
Structure is created through:
- **Tonal Shifts:** Placing a `surface_container_high` (#222a3d) element against a `surface` (#0b1326) background.
- **Negative Space:** Using generous padding to imply boundaries.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers. Hierarchy is defined by "Lifting" or "Receding" surfaces using the Material container tiers:
*   **Deepest:** `surface_container_lowest` (#060e20) — Used for utility sidebars or "sunk" input areas.
*   **Base:** `surface` (#0b1326) — The main canvas.
*   **Raised:** `surface_container` (#171f33) — Standard content areas.
*   **Feature:** `surface_container_highest` (#2d3449) — Active workspace panels or floating inspectors.

### The "Glass & Gradient" Rule
To evoke a sense of modern AI fluidity:
- **Glassmorphism:** Use `surface_variant` at 60% opacity with a `24px` backdrop blur for floating overlays.
- **Signature Gradients:** Primary actions should use a linear gradient from `primary` (#b6c4ff) to `primary_container` (#004adf) at a 135-degree angle. This adds "soul" and a sense of energy to the studio’s output.

---

## 3. Typography: Architectural Contrast
We use a dual-font strategy to balance "Human Creativity" with "Machine Precision."

*   **Display & Headlines (Manrope):** These are our architectural anchors. Use `display-lg` to `headline-sm` for high-impact messaging. The wide apertures of Manrope feel sophisticated and expensive.
*   **Interface & Body (Inter):** Used for `title`, `body`, and `label` roles. Inter provides the technical "instrument" feel necessary for a content studio.

**Editorial Hierarchy:** Always maintain a minimum of two scale jumps between headers and body (e.g., pairing a `headline-lg` with a `body-md`) to ensure the layout feels "designed" rather than "filled."

---

## 4. Elevation & Depth
Depth is a functional tool, not a decoration.

### The Layering Principle
Achieve lift by stacking. Place a `surface_container_low` card inside a `surface_container_high` section to create a "recessed" slot for data entry. This "in-set" look feels more custom than standard drop-shadow cards.

### Ambient Shadows
For floating elements (Modals, Tooltips):
- **Blur:** 40px - 60px.
- **Color:** Use `on_surface` (#dae2fd) at 4% - 8% opacity. 
- **The Result:** A soft, atmospheric glow that feels like natural light scattering through the "Deep Indigo" atmosphere.

### The "Ghost Border" Fallback
If accessibility requires a container edge, use the `outline_variant` (#454652) at **15% opacity**. This creates a "Ghost Border"—a suggestion of a line that disappears upon focus, maintaining the sleek aesthetic.

---

## 5. Components

### Buttons (The "Precision Tool" Style)
*   **Primary:** `rounded-xl` (1rem). Gradient fill (`primary` to `primary_container`). Label in `on_primary_fixed`. 
*   **Secondary:** `rounded-xl`. Solid `secondary_container` (#343d96). No border.
*   **Tertiary:** Text-only in `primary`. Hover state triggers a `surface_variant` ghost background.
*   **Interaction:** On hover, buttons should subtly scale (1.02x) and increase shadow diffusion.

### Input Fields (The "Sunk" Field)
*   **Style:** Background `surface_container_lowest`. No border.
*   **Focus:** Transition background to `surface_container_high` and apply a 1px `primary` ghost border (20% opacity).
*   **Typography:** Labels must use `label-md` in `on_surface_variant` for a subtle, high-end feel.

### Chips & Tags
*   Use `rounded-full` (9999px).
*   **Selection:** Use `tertiary_container` with `on_tertiary_container` text for high-visibility AI "tags" or categories.

### Media Cards
*   **Strict Rule:** No dividers. Separate the image/preview from the metadata using a `1.5rem` (xl) vertical gap.
*   **Hover:** Image should subtly zoom while the card background shifts from `surface_container` to `surface_container_high`.

---

## 6. Do’s and Don’ts

### Do
*   **Do** use asymmetrical layouts (e.g., a wide 8-column content area paired with a narrow 3-column metadata rail).
*   **Do** use `tertiary` (#00daf3) sparingly for "AI Insights" or "Magic" features to differentiate them from standard UI actions.
*   **Do** embrace "Atmospheric Space." If a layout feels crowded, increase the spacing scale rather than adding lines.

### Don’t
*   **Don’t** use pure black (#000000). Always use `surface_container_lowest` (#060e20) to maintain tonal depth.
*   **Don’t** use 100% opaque borders. They break the "Glassmorphism" illusion.
*   **Don’t** use standard "Drop Shadows." If it looks like a default Photoshop shadow, it’s too heavy. It should look like a glow.