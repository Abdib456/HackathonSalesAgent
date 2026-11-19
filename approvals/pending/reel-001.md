# reel-001: Tim shows a real photo he loves, let down by a plain white t-shirt. Peitho layers a houndstooth jacket over it, and close-ups prove his face and watch are unchanged: change just the clothes, keep everything else.

**Hook (first 2s):** Same photo. Same face. New jacket.
**Call to action:** link in bio

## Hooks considered (Claude's scores; the top one is the suggestion)
| Score | Hook | Style | Why |
|-------|------|-------|-----|
| 8/10 | Same photo. Same face. New jacket. | before/after | A wipe reveal on the first frame stops the scroll, the copy is specific and 6 words long, and the close-ups prove it is true. |
| 7/10 | Love the photo, hate the outfit? | question | It names the exact problem in the audience's own words, but the visual hit is weaker and many fashion posts open with similar questions. |
| 7/10 | Change the clothes. Keep your face. | bold claim | Clear and true, and it speaks to the face-distortion fear, but without the reveal on screen it reads like a standard app ad. |
| 6/10 | 1 item changed. Face and watch untouched. | number | Specific and provable, but 7 dense words are slow to read in 2 seconds and the number gives little emotional pull. |
| 6/10 | POV: great photo, shame about the outfit | POV | Relatable, but the POV format is tired and the line does not say what the app does. |

## Shot list
A guide: adapt it freely. Photos are fine for static shots.

| # | Time | Shot | On-screen text | Voiceover |
|---|------|------|----------------|-----------|
| 01 | 0-2s | Full-screen real phone photo of Tim in a plain white crewneck. A same-position before/after wipe runs left to right and reveals the edited version: a houndstooth jacket layered over the same t-shirt. The pose, backdrop and framing are identical. Lots of white space. Inter text in stone-900 on a #fffbf7 band. | Same photo. Same face. New jacket. | Same photo. New jacket. |
| 02 | 2-5s | Tim films selfie-style in a plain room and holds up his phone showing the original photo. Original sound only, with no music. | Loved the photo. Not the outfit. | I loved this photo. The t-shirt let it down. |
| 03 | 5-9s | App screen recording. Tim uploads the photo and taps the t-shirt, then chooses to layer an item on top. The UI is kept minimal and cropped tight. | Pick the item to change | Upload your photo. Pick the item to change, or layer something on top. |
| 04 | 9-13s | Screen recording. Peitho outlines the t-shirt area. Tim adjusts the brush size and refines the edge near his collar. | Refine the outline with a brush | It outlines it. Tidy the edge with the brush if you want. |
| 05 | 13-16s | Screen recording. A split moment: Tim scrolls the trending catalogue and taps a houndstooth jacket with no visible logo. A small inset shows the option to upload your own clothing photo instead. | Your own clothing photo, or our catalogue | Upload your own clothing photo, or choose from the catalogue. |
| 06 | 16-21s | Screen recording of the result. Tim holds to compare, flicking between before and after. Then two quick punch-in close-ups, each shown before and after: his face, then the watch on his wrist. Both are visibly identical. | Face and watch: unchanged | Only the outlined area changes. Hold to compare. Face, watch, everything else, as shot. |
| 07 | 21-25s | Back to Tim on camera, holding the phone with the final photo on screen. Plain background, natural light. | Zero distortion. Unlike other AI editors. | Unlike other AI editors, zero distortion to your face and jewellery. Your photo, your best real self. |
| 08 | 25-29s | End card on a #fffbf7 background. The final after photo sits small in the centre with white space around it. The text is Inter in stone-900, and the CTA button is Peitho orange #c2410c, the only orange in the reel. | First try-on free. From £3.49 for 5. Tap the link in bio. | Your first try-on is free. No subscription. Tap the link in our bio to try it. |

## Full voiceover (AI voiceover: `voiceovers/reel-001.mp3` (made on the agent's next run), or record it yourself)
Same photo. New jacket. I loved this photo. The t-shirt let it down. Upload your photo. Pick the item to change, or layer something on top. It outlines it. Tidy the edge with the brush if you want. Upload your own clothing photo, or choose from the catalogue. Only the outlined area changes. Hold to compare. Face, watch, everything else, as shot. Unlike other AI editors, zero distortion to your face and jewellery. Your photo, your best real self. Your first try-on is free. No subscription. Tap the link in our bio to try it.

## Caption
Loved the photo. The t-shirt let it down. So I changed just the clothes and kept everything else: the pose, the backdrop, my face and my watch. Pick the item to change, then upload your own clothing photo or choose from our catalogue. Only the outlined area changes. Hold to compare. First try-on free, then from £3.49 for 5 try-ons or £9.99 for 20. No subscription. Tap the link in our bio to try it: peitho.app/?ref=reel-NNN. Edited with AI: the jacket in the after photo was added with Peitho, and this reel was planned with AI help.

## Next steps
1. **Film and edit** in Edits or CapCut, using the shot list and any hook above.
   Put an "AI-assisted" label on screen. Log it as a touch:
   `python -m agent.logger touch reel-001 "filmed and edited in CapCut"` (and `/touch` in Discord).
2. **Post** on Instagram with the caption below. Keep its AI note; turn on Instagram's
   AI label if it asks. Set the bio link to `https://peitho.app?ref=reel-001` (the `ref` lets the report credit sales to this reel).
3. **Move this file to `approvals/approved/`.** That tells the agent it's posted, frees a slot for
   the next plan, and logs the posting as a touch (mirror it with `/touch`).

Not worth filming? Move it to `approvals/rejected/` instead, optionally with a line
`Reason: ...` at the top. New plans will steer away from it.

<!-- machine-readable plan, don't edit below -->
```json
{
  "reel_id": "reel-001",
  "script": {
    "idea": "Tim shows a real photo he loves, let down by a plain white t-shirt. Peitho layers a houndstooth jacket over it, and close-ups prove his face and watch are unchanged: change just the clothes, keep everything else.",
    "hooks": [
      {
        "text": "Same photo. Same face. New jacket.",
        "style": "before/after",
        "score": 8,
        "reason": "A wipe reveal on the first frame stops the scroll, the copy is specific and 6 words long, and the close-ups prove it is true."
      },
      {
        "text": "Love the photo, hate the outfit?",
        "style": "question",
        "score": 7,
        "reason": "It names the exact problem in the audience's own words, but the visual hit is weaker and many fashion posts open with similar questions."
      },
      {
        "text": "Change the clothes. Keep your face.",
        "style": "bold claim",
        "score": 7,
        "reason": "Clear and true, and it speaks to the face-distortion fear, but without the reveal on screen it reads like a standard app ad."
      },
      {
        "text": "1 item changed. Face and watch untouched.",
        "style": "number",
        "score": 6,
        "reason": "Specific and provable, but 7 dense words are slow to read in 2 seconds and the number gives little emotional pull."
      },
      {
        "text": "POV: great photo, shame about the outfit",
        "style": "POV",
        "score": 6,
        "reason": "Relatable, but the POV format is tired and the line does not say what the app does."
      }
    ],
    "scenes": [
      {
        "seconds": "0-2",
        "shot": "Full-screen real phone photo of Tim in a plain white crewneck. A same-position before/after wipe runs left to right and reveals the edited version: a houndstooth jacket layered over the same t-shirt. The pose, backdrop and framing are identical. Lots of white space. Inter text in stone-900 on a #fffbf7 band.",
        "on_screen_text": "Same photo. Same face. New jacket.",
        "voiceover": "Same photo. New jacket."
      },
      {
        "seconds": "2-5",
        "shot": "Tim films selfie-style in a plain room and holds up his phone showing the original photo. Original sound only, with no music.",
        "on_screen_text": "Loved the photo. Not the outfit.",
        "voiceover": "I loved this photo. The t-shirt let it down."
      },
      {
        "seconds": "5-9",
        "shot": "App screen recording. Tim uploads the photo and taps the t-shirt, then chooses to layer an item on top. The UI is kept minimal and cropped tight.",
        "on_screen_text": "Pick the item to change",
        "voiceover": "Upload your photo. Pick the item to change, or layer something on top."
      },
      {
        "seconds": "9-13",
        "shot": "Screen recording. Peitho outlines the t-shirt area. Tim adjusts the brush size and refines the edge near his collar.",
        "on_screen_text": "Refine the outline with a brush",
        "voiceover": "It outlines it. Tidy the edge with the brush if you want."
      },
      {
        "seconds": "13-16",
        "shot": "Screen recording. A split moment: Tim scrolls the trending catalogue and taps a houndstooth jacket with no visible logo. A small inset shows the option to upload your own clothing photo instead.",
        "on_screen_text": "Your own clothing photo, or our catalogue",
        "voiceover": "Upload your own clothing photo, or choose from the catalogue."
      },
      {
        "seconds": "16-21",
        "shot": "Screen recording of the result. Tim holds to compare, flicking between before and after. Then two quick punch-in close-ups, each shown before and after: his face, then the watch on his wrist. Both are visibly identical.",
        "on_screen_text": "Face and watch: unchanged",
        "voiceover": "Only the outlined area changes. Hold to compare. Face, watch, everything else, as shot."
      },
      {
        "seconds": "21-25",
        "shot": "Back to Tim on camera, holding the phone with the final photo on screen. Plain background, natural light.",
        "on_screen_text": "Zero distortion. Unlike other AI editors.",
        "voiceover": "Unlike other AI editors, zero distortion to your face and jewellery. Your photo, your best real self."
      },
      {
        "seconds": "25-29",
        "shot": "End card on a #fffbf7 background. The final after photo sits small in the centre with white space around it. The text is Inter in stone-900, and the CTA button is Peitho orange #c2410c, the only orange in the reel.",
        "on_screen_text": "First try-on free. From £3.49 for 5. Tap the link in bio.",
        "voiceover": "Your first try-on is free. No subscription. Tap the link in our bio to try it."
      }
    ],
    "caption": "Loved the photo. The t-shirt let it down. So I changed just the clothes and kept everything else: the pose, the backdrop, my face and my watch. Pick the item to change, then upload your own clothing photo or choose from our catalogue. Only the outlined area changes. Hold to compare. First try-on free, then from £3.49 for 5 try-ons or £9.99 for 20. No subscription. Tap the link in our bio to try it: peitho.app/?ref=reel-NNN. Edited with AI: the jacket in the after photo was added with Peitho, and this reel was planned with AI help.",
    "hook": "Same photo. Same face. New jacket."
  }
}
```
