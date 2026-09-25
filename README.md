# Precept

**Content moderation by one public rule, the same for everyone, with an auditable appeal.** A moderation primitive for GenLayer, with a live board.

Most moderation is a black box: a post disappears and nobody outside the room knows which rule it broke, whether the rule was applied evenly, or how to contest it. Precept turns the rule into the contract. A space is opened with one rule in plain words. Anyone posts content into it, and anyone can report a post. The contract fetches the post itself and a round of GenLayer validators reads it against that one published rule and decides whether it breaks it. The rule is the space's, not the reporter's, so the same standard is applied to everyone and no one can attach a rule of convenience to remove a post they dislike.

## How it works

1. **`open_space(name, rule)`** — a moderator opens a space with one rule in plain words. Bound to `gl.message.sender_address`.
2. **`post(space_id, content_url)`** — anyone posts content into a space; it starts `LISTED`. Bound to the caller. The space's rule is copied onto the post, so it is always judged against the rule in force when it was filed.
3. **`report(item_id)`** — open to anybody. The contract **fetches the post** and a GenLayer round reads it against the space's rule: `VIOLATES` removes it, `ALLOWED` dismisses the report and the post stays listed, `UNCLEAR` changes nothing.
4. **`appeal(item_id)`** — only the author of a removed post may appeal; a fresh round re-reads it against the same rule, and if it now reads `ALLOWED` the post is restored and the author's record corrected.

Reads: `space(id)`, `item(id)`, `history(id)`, `record(address)`, `size()`, `page(start, count)`.

## Why it is fair, not a black box

- **One rule, applied evenly.** The rule belongs to the space and is copied onto every post; a reporter cannot supply a rule of convenience, and the round always judges against the published rule.
- **An auditable appeal.** A removal is not final: the author appeals, a fresh round re-reads the post, and a successful appeal restores it and undoes the mark on the record.
- **A paper trail.** Every report and appeal is kept on the post, append-only: who raised it, the verdict, and the passage the round cited. Nothing is overwritten.
- **No-evidence never removes.** An unrelated, unreadable, or not-found page is `UNCLEAR`, never a violation; a post is removed only on a real `VIOLATES`.

## Why it needs GenLayer

Whether a post breaks a rule stated in words is a judgement over real-world text that no ordinary contract can make and no single moderator should be trusted with unaccountably. GenLayer validators each fetch the post and reach consensus on one categorical field; the removal is built from the published rule and the post's own words, and it can be appealed.

## Tests

`python tests/precept_rules.py` — the moderation rules exercised through the real `open_space()`, `post()`, `report()` and `appeal()` on a Precept built against a stub of the runtime, with the page and verdict controlled. It proves the rule judged is the space's own, only a `VIOLATES` removes a post, an unrelated or not-found page never does, only the author can appeal, a successful appeal restores the post and corrects the record, and history is preserved. 23 checks.

## Live

- **Contract (GenLayer Asimov):** `0x2e268d8E0891B6506805Ce03e2AD208f187C4c93`
- Explorer: https://explorer-asimov.genlayer.com/address/0x2e268d8E0891B6506805Ce03e2AD208f187C4c93
- **App:** https://jspiiv.github.io/precept/ — reads the board from chain without a wallet; opening, posting, reporting and appealing are transactions on Asimov.

## Proven on Asimov

`scripts/prove.mjs`, `results/proved.json`. In a space whose rule bans advertising:
- an advertisement (`docs/spam-post.txt`) is reported → **VIOLATES** → `REMOVED`, and the author's record gains a removed.
- an on-topic comment (`docs/ontopic-post.txt`) is reported → **ALLOWED** → stays `LISTED`.
- an unreadable post → `UNCLEAR` → stays `LISTED`.
- the author appeals the removed ad; still `VIOLATES` → the removal is upheld; the full log keeps both the report and the appeal.

The appeal-restore path (an `ALLOWED` appeal restoring a post and correcting the record) is proved deterministically in the tests.

## Where it stops, plainly

It judges a post against a rule in words, which is a judgement, not a proof: name a rule a stranger could apply the same way twice, and a post a third party controls. It records a standing and a history, not a punishment; what a removal costs is left to the space.

## Licence

AGPL-3.0-or-later.
