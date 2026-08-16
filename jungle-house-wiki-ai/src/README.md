# Jungle House CSS Split

This is a safe first-stage refactor of the original `styles.css`.

## How to use it

1. Replace your existing `src/styles.css` with the new `styles.css`.
2. Copy the included `styles/` folder into `src/styles/`.
3. Keep your current React import unchanged if it already imports `styles.css`.

Example:

```js
import './styles.css';
```

## Important

The files are imported in the same cascade order as the original stylesheet.
That is intentional because the original CSS contains many later sidebar and AI-chat override sections using `!important`.

This package separates the file without aggressively deleting or merging those overrides yet, which reduces the chance of breaking the current UI.

## Structure

- 01-05: theme, global base, layout, sidebar base, shared components
- 06-17: page/module styles
- 18: base responsive/mobile rules
- 19-24: topbar/sidebar and first-generation override layers
- 25-33: later AI-chat, sidebar, article/editor, and client-feedback layers
- 34-36: quiz feedback, knowledge base, and dashboard

## Recommended next cleanup

After confirming that the UI looks identical, the next step should be consolidating:
- sidebar rules
- AI Chat rules
- mobile media queries
- repeated `!important` overrides

Do that one feature at a time rather than deleting override sections all at once.
