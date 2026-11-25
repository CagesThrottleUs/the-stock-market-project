# Scripts

| Script                                        | Purpose                                                            |
| --------------------------------------------- | ------------------------------------------------------------------ |
| `get_itch_data.py`                            | Download the Nasdaq ITCH captures into `data/`                     |
| `decompress.py`                               | `data/**/*.gz` → sibling `.bin` files                              |
| [`itch_story/itch_story.py`](itch_story/)     | Walk a `.bin` capture and tell its story, one message per log line |
| `pre-push.sh`                                 | Local quality gates, then `git push` (see the root README)         |

[`itch_story/README.md`](itch_story/README.md) also holds what we have learnt about ITCH so far.
